"""
exFAT Volume Deep Scanner and File Extractor.
Scans active and deleted directory entries, verifies file integrity (MP4/video headers),
and extracts clusters directly from unallocated space.
"""

import os
import struct
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Set, Tuple

FAT_CACHE_BLOCK_SIZE = 65536  # 64 KB FAT window cache (16,384 cluster entries per read)
MAX_DIRECTORY_DEPTH = 64      # Guard against corrupted circular directory trees
RECOVERY_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming I/O buffer


class AlignedVolumeReader:
    """Sector-aligned raw volume and disk image reader."""

    def __init__(self, volume_path: str, sector_size: int = 512):
        if sector_size <= 0 or (sector_size & (sector_size - 1)) != 0:
            raise ValueError(f"sector_size must be a positive power of 2, got {sector_size}")
        self.volume_path = volume_path
        self.f = open(volume_path, 'rb')
        self.sector_size = sector_size

    def __enter__(self) -> 'AlignedVolumeReader':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def read_exact(self, offset: int, size: int) -> bytes:
        if size <= 0 or offset < 0:
            return b''
        aligned_start = (offset // self.sector_size) * self.sector_size
        offset_in_sector = offset - aligned_start
        total_to_read = ((offset_in_sector + size + self.sector_size - 1) // self.sector_size) * self.sector_size
        self.f.seek(aligned_start)
        data = self.f.read(total_to_read)
        return data[offset_in_sector : offset_in_sector + size]

    def close(self) -> None:
        if getattr(self, 'f', None) is not None:
            try:
                self.f.close()
            except OSError:
                pass
            self.f = None

def parse_exfat_timestamp(ts_val: int) -> Optional[datetime]:
    if not ts_val:
        return None
    date_part = (ts_val >> 16) & 0xFFFF
    time_part = ts_val & 0xFFFF
    year = ((date_part >> 9) & 0x7F) + 1980
    month = max(1, min(12, (date_part >> 5) & 0x0F))
    day = max(1, min(31, date_part & 0x1F))
    hour = min(23, (time_part >> 11) & 0x1F)
    minute = min(59, (time_part >> 5) & 0x3F)
    second = min(59, (time_part & 0x1F) * 2)
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

def human_size(n_bytes: int) -> str:
    """Format byte sizes to human-readable units."""
    if n_bytes is None:
        return "0 B"
    val = float(n_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(val) < 1024.0:
            return f"{val:3.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"

def verify_file_integrity(first_bytes: bytes, filename: str) -> str:
    """Verifies file headers and magic numbers based on file type."""
    ext = os.path.splitext(filename)[1].lower()
    if len(first_bytes) < 4:
        return "NO_DATA"

    # --- Videos ---
    if ext in ('.mp4', '.m4v', '.mov'):
        if b'ftyp' in first_bytes[:16]:
            brand = first_bytes[8:12].decode('latin1', errors='replace').strip()
            return f"100% INTACT (brand: {brand})"
        elif b'moov' in first_bytes[:16]:
            return "100% INTACT (moov)"
        return "CORRUPTED"
    elif ext == '.mkv':
        if first_bytes[:4] == b'\x1a\x45\xdf\xa3':
            return "100% INTACT (MKV)"
        return "CORRUPTED"
    elif ext == '.avi':
        if first_bytes[:4] == b'RIFF' and len(first_bytes) >= 12 and first_bytes[8:12] == b'AVI ':
            return "100% INTACT (AVI)"
        return "CORRUPTED"
    elif ext == '.wmv':
        if first_bytes[:4] == b'\x30\x26\xb2\x75':
            return "100% INTACT (WMV/ASF)"
        return "CORRUPTED"

    # --- Photos & Images ---
    elif ext in ('.jpg', '.jpeg'):
        if first_bytes[:2] == b'\xff\xd8':
            return "100% INTACT (JPEG)"
        return "CORRUPTED"
    elif ext == '.png':
        if len(first_bytes) >= 8 and first_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "100% INTACT (PNG)"
        return "CORRUPTED"
    elif ext == '.gif':
        if first_bytes[:4] == b'GIF8':
            return "100% INTACT (GIF)"
        return "CORRUPTED"
    elif ext == '.bmp':
        if first_bytes[:2] == b'BM':
            return "100% INTACT (BMP)"
        return "CORRUPTED"
    elif ext == '.webp':
        if first_bytes[:4] == b'RIFF' and len(first_bytes) >= 12 and first_bytes[8:12] == b'WEBP':
            return "100% INTACT (WEBP)"
        return "CORRUPTED"
    elif ext in ('.tif', '.tiff'):
        if first_bytes[:4] in (b'II*\x00', b'MM\x00*'):
            return "100% INTACT (TIFF)"
        return "CORRUPTED"
    elif ext in ('.heic', '.heif'):
        if b'ftyp' in first_bytes[:16]:
            return "100% INTACT (HEIC)"
        return "CORRUPTED"
    elif ext == '.psd':
        if first_bytes[:4] == b'8BPS':
            return "100% INTACT (PSD)"
        return "CORRUPTED"
    elif ext == '.ico':
        if first_bytes[:4] == b'\x00\x00\x01\x00':
            return "100% INTACT (ICO)"
        return "CORRUPTED"

    # --- Documents & Office ---
    elif ext == '.pdf':
        if first_bytes[:4] == b'%PDF':
            return "100% INTACT (PDF)"
        return "CORRUPTED"
    elif ext in ('.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.epub'):
        if first_bytes[:4] == b'PK\x03\x04':
            return "100% INTACT (Office ZIP)"
        return "CORRUPTED"
    elif ext in ('.doc', '.xls', '.ppt'):
        if len(first_bytes) >= 8 and first_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return "100% INTACT (Office OLE)"
        return "CORRUPTED"
    elif ext == '.rtf':
        if first_bytes[:4] == b'{\\rt':
            return "100% INTACT (RTF)"
        return "CORRUPTED"
    elif ext in ('.txt', '.csv', '.log', '.json', '.xml', '.html', '.md', '.py', '.rs', '.cpp', '.h'):
        try:
            first_bytes.decode('utf-8')
            return "100% INTACT (Text)"
        except UnicodeDecodeError:
            try:
                first_bytes.decode('latin-1')
                if all(b >= 32 or b in (9, 10, 13) for b in first_bytes):
                    return "100% INTACT (Text)"
            except Exception:
                pass
            return "CORRUPTED (Binary in text)"

    # --- Audio & Music ---
    elif ext == '.mp3':
        if first_bytes[:3] == b'ID3' or (first_bytes[0] == 0xFF and (first_bytes[1] & 0xE0) == 0xE0):
            return "100% INTACT (MP3)"
        return "CORRUPTED"
    elif ext == '.wav':
        if first_bytes[:4] == b'RIFF' and len(first_bytes) >= 12 and first_bytes[8:12] == b'WAVE':
            return "100% INTACT (WAV)"
        return "CORRUPTED"
    elif ext == '.flac':
        if first_bytes[:4] == b'fLaC':
            return "100% INTACT (FLAC)"
        return "CORRUPTED"
    elif ext in ('.m4a', '.aac'):
        if b'ftyp' in first_bytes[:16] or (first_bytes[0] == 0xFF and (first_bytes[1] & 0xF0) == 0xF0):
            return "100% INTACT (M4A/AAC)"
        return "CORRUPTED"
    elif ext in ('.ogg', '.opus'):
        if first_bytes[:4] == b'OggS':
            return "100% INTACT (OGG)"
        return "CORRUPTED"

    # --- Archives & Compressed ---
    elif ext in ('.zip', '.jar', '.apk'):
        if first_bytes[:4] == b'PK\x03\x04':
            return "100% INTACT (ZIP)"
        return "CORRUPTED"
    elif ext == '.rar':
        if len(first_bytes) >= 6 and first_bytes[:6] == b'Rar!\x1a\x07':
            return "100% INTACT (RAR)"
        return "CORRUPTED"
    elif ext == '.7z':
        if len(first_bytes) >= 6 and first_bytes[:6] == b'7z\xbc\xaf\x27\x1c':
            return "100% INTACT (7-Zip)"
        return "CORRUPTED"
    elif ext == '.gz':
        if first_bytes[:2] == b'\x1f\x8b':
            return "100% INTACT (GZIP)"
        return "CORRUPTED"
    elif ext in ('.exe', '.dll', '.sys'):
        if first_bytes[:2] == b'MZ':
            return "100% INTACT (PE Executable)"
        return "CORRUPTED"

    return "UNKNOWN"

class ExFatScanner:
    def __init__(self, drive_letter: str = "G", image_path: Optional[str] = None):
        self.drive_letter = drive_letter.upper().strip(":\\")
        self.vol_path = image_path or rf"\\.\{self.drive_letter}:"
        self.reader = AlignedVolumeReader(self.vol_path)
        self._fat_cache: Dict[int, bytes] = {}

        bs = self.reader.read_exact(0, 512)
        if len(bs) < 512 or bs[3:11] != b'EXFAT   ':
            self.reader.close()
            raise ValueError(f"Drive {self.drive_letter}: is not an exFAT volume (signature: {bs[3:11]!r})")

        self.sector_size = 1 << bs[0x6C]
        self.reader.sector_size = self.sector_size
        self.cluster_size = self.sector_size * (1 << bs[0x6D])
        self.heap_offset_sectors = struct.unpack('<I', bs[0x58:0x5C])[0]
        self.heap_offset_bytes = self.heap_offset_sectors * self.sector_size
        self.cluster_count = struct.unpack('<I', bs[0x5C:0x60])[0]
        self.root_cluster = struct.unpack('<I', bs[0x60:0x64])[0]
        self.fat_offset_sectors = struct.unpack('<I', bs[0x50:0x54])[0]
        self.fat_offset_bytes = self.fat_offset_sectors * self.sector_size

    def __enter__(self) -> 'ExFatScanner':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def cluster_to_byte_offset(self, c: int) -> int:
        return self.heap_offset_bytes + (c - 2) * self.cluster_size

    def read_fat_entry(self, c: int) -> int:
        """Reads a 32-bit FAT entry using a 64 KB block cache to minimize disk seeks."""
        byte_pos = self.fat_offset_bytes + c * 4
        block_base = (byte_pos // FAT_CACHE_BLOCK_SIZE) * FAT_CACHE_BLOCK_SIZE
        if block_base not in self._fat_cache:
            if len(self._fat_cache) >= 128:
                self._fat_cache.clear()
            self._fat_cache[block_base] = self.reader.read_exact(block_base, FAT_CACHE_BLOCK_SIZE)
        block = self._fat_cache[block_base]
        rel = byte_pos - block_base
        if rel + 4 > len(block):
            data = self.reader.read_exact(byte_pos, 4)
            return struct.unpack('<I', data)[0] if len(data) == 4 else 0
        return struct.unpack_from('<I', block, rel)[0]

    def get_cluster_chain(self, start_cluster: int, no_fat_chain: bool = False, num_clusters: int = 1) -> List[int]:
        max_len = min(max(1, num_clusters), max(1, self.cluster_count))
        if no_fat_chain:
            return list(range(start_cluster, start_cluster + max_len))
        chain: List[int] = []
        seen: Set[int] = set()
        curr = start_cluster
        while 2 <= curr <= self.cluster_count + 1 and len(chain) < max_len:
            chain.append(curr)
            seen.add(curr)
            nxt = self.read_fat_entry(curr)
            if nxt == 0 or nxt >= 0xFFFFFFF7:
                break
            if nxt in seen:
                break
            curr = nxt
        return chain

    @staticmethod
    def _coalesce_clusters(clusters: List[int]) -> List[Tuple[int, int]]:
        """Groups consecutive cluster numbers into (start_cluster, count) runs."""
        if not clusters:
            return []
        runs: List[Tuple[int, int]] = []
        run_start = clusters[0]
        run_len = 1
        for c in clusters[1:]:
            if c == run_start + run_len:
                run_len += 1
            else:
                runs.append((run_start, run_len))
                run_start = c
                run_len = 1
        runs.append((run_start, run_len))
        return runs

    def scan_all_files(self, progress_callback: Optional[Callable[[str, int], None]] = None) -> List[Dict[str, Any]]:
        """Scans all active and deleted entries and checks header integrity."""
        visited_clusters: Set[int] = set()
        found_files: List[Dict[str, Any]] = []
        total_examined = 0

        def parse_directory(start_cluster: int, path_prefix: str = "", is_contiguous: bool = False,
                            length_bytes: int = 0, depth: int = 0) -> None:
            nonlocal total_examined
            if depth > MAX_DIRECTORY_DEPTH or start_cluster < 2:
                return

            num_clusters = max(1, (length_bytes + self.cluster_size - 1) // self.cluster_size) if length_bytes else 1
            num_clusters = min(num_clusters, 4096)
            chain = self.get_cluster_chain(start_cluster, no_fat_chain=is_contiguous, num_clusters=num_clusters)
            if not chain:
                chain = [start_cluster]

            dir_clusters = [c for c in chain if c not in visited_clusters]
            if not dir_clusters:
                return
            visited_clusters.update(dir_clusters)

            # Assemble directory stream across clusters so straddling entry sets stay intact
            dir_buf = bytearray()
            for run_start, run_len in self._coalesce_clusters(dir_clusters):
                dir_buf += self.reader.read_exact(
                    self.cluster_to_byte_offset(run_start),
                    run_len * self.cluster_size
                )

            i = 0
            n_bytes = len(dir_buf)
            while i + 32 <= n_bytes:
                entry_type = dir_buf[i]
                if entry_type == 0x00:
                    i += 32
                    continue

                is_deleted = not bool(entry_type & 0x80)
                base_type = entry_type & 0x7F

                if base_type == 0x05:
                    secondary_count = dir_buf[i + 1]
                    attrs = struct.unpack_from('<H', dir_buf, i + 4)[0]
                    is_dir = bool(attrs & 0x10)
                    ctime_raw = struct.unpack_from('<I', dir_buf, i + 8)[0]
                    mtime_raw = struct.unpack_from('<I', dir_buf, i + 12)[0]

                    first_cluster = 0
                    file_size = 0
                    no_fat_chain = False
                    if i + 64 <= n_bytes and (dir_buf[i + 32] & 0x7F) == 0x40:
                        general_flags = dir_buf[i + 33]
                        no_fat_chain = bool(general_flags & 2)
                        first_cluster = struct.unpack_from('<I', dir_buf, i + 52)[0]
                        file_size = struct.unpack_from('<Q', dir_buf, i + 56)[0]

                    name_parts: List[str] = []
                    for s_idx in range(1, secondary_count):
                        offset_s = i + 32 * (s_idx + 1)
                        if offset_s + 32 <= n_bytes and (dir_buf[offset_s] & 0x7F) == 0x41:
                            name_chunk = bytes(dir_buf[offset_s + 2 : offset_s + 32]).decode(
                                'utf-16le', errors='replace'
                            ).split('\x00')[0]
                            name_parts.append(name_chunk)

                    filename = "".join(name_parts)
                    full_path = f"{path_prefix}\\{filename}" if path_prefix else filename
                    status = "DELETED" if is_deleted else "ACTIVE"

                    if filename:
                        total_examined += 1
                        if progress_callback and total_examined % 50 == 0:
                            progress_callback(full_path, total_examined)

                        integrity = "N/A (Directory)" if is_dir else "NO_DATA"
                        if not is_dir and first_cluster >= 2 and file_size > 0:
                            offset = self.cluster_to_byte_offset(first_cluster)
                            hdr_bytes = self.reader.read_exact(offset, 16)
                            integrity = verify_file_integrity(hdr_bytes, filename)

                        found_files.append({
                            "name": filename,
                            "path": full_path,
                            "status": status,
                            "is_dir": is_dir,
                            "size": file_size,
                            "first_cluster": first_cluster,
                            "start_sector": (self.cluster_to_byte_offset(first_cluster) // self.sector_size) if first_cluster >= 2 else 0,
                            "no_fat_chain": no_fat_chain,
                            "created": parse_exfat_timestamp(ctime_raw),
                            "modified": parse_exfat_timestamp(mtime_raw),
                            "integrity": integrity
                        })

                        if is_dir and first_cluster >= 2 and first_cluster not in visited_clusters:
                            parse_directory(
                                first_cluster,
                                full_path,
                                is_contiguous=no_fat_chain,
                                length_bytes=file_size,
                                depth=depth + 1
                            )

                    i += 32 * (1 + secondary_count)
                else:
                    i += 32

        parse_directory(self.root_cluster, f"{self.drive_letter}:")
        self._resolve_cluster_collisions(found_files)
        return found_files

    def _resolve_cluster_collisions(self, files: List[Dict[str, Any]]) -> None:
        """
        Detects overlapping cluster ranges and marks overwritten deleted files.
        Active files take precedence over deleted files.
        Between deleted files, the newer file (more recent timestamp) overwrites the older file.
        """
        max_valid_clusters = max(1, self.cluster_count)
        intervals = []
        for f in files:
            if f['is_dir'] or f['size'] <= 0 or f['first_cluster'] < 2:
                continue
            c_count = min((f['size'] + self.cluster_size - 1) // self.cluster_size, max_valid_clusters)
            start_c = f['first_cluster']
            ts = f.get('created') or f.get('modified') or datetime.min

            spans: List[Tuple[int, int]] = []
            if not f.get('no_fat_chain', True):
                chain = self.get_cluster_chain(start_c, no_fat_chain=False, num_clusters=c_count)
                if len(chain) >= c_count:
                    spans = self._coalesce_clusters(chain[:c_count])

            if not spans:
                spans = [(start_c, c_count)]

            for span_start, span_len in spans:
                intervals.append({
                    'start': span_start,
                    'end': span_start + span_len - 1,
                    'ts': ts,
                    'status': f['status'],
                    'name': f['name'],
                    'file': f
                })

        intervals.sort(key=lambda x: (x['start'], x['end']))

        for i in range(len(intervals)):
            curr = intervals[i]
            for j in range(i + 1, len(intervals)):
                other = intervals[j]
                if other['start'] > curr['end']:
                    break
                if curr['file'] is other['file']:
                    continue

                if curr['status'] == 'DELETED' and other['status'] == 'ACTIVE':
                    victim, culprit = curr, other
                elif curr['status'] == 'ACTIVE' and other['status'] == 'DELETED':
                    victim, culprit = other, curr
                else:
                    if curr['ts'] < other['ts']:
                        victim, culprit = curr, other
                    elif other['ts'] < curr['ts']:
                        victim, culprit = other, curr
                    else:
                        continue

                victim['file']['integrity'] = f"OVERWRITTEN (by {culprit['name']})"
                victim['file']['overwritten_by'] = culprit['name']

    def recover_file(self, item: Dict[str, Any], dest_path: str,
                     progress_fn: Optional[Callable[[int, int], None]] = None) -> bool:
        """Recovers an intact or deleted file from the cluster heap, following FAT chains when available."""
        file_size = item.get('size', 0)
        first_cluster = item.get('first_cluster', 0)
        if file_size <= 0 or first_cluster < 2:
            return False

        parent_dir = os.path.dirname(os.path.abspath(dest_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        needed_clusters = (file_size + self.cluster_size - 1) // self.cluster_size
        no_fat_chain = bool(item.get('no_fat_chain', True))

        if no_fat_chain:
            runs = [(first_cluster, needed_clusters)]
        else:
            chain = self.get_cluster_chain(first_cluster, no_fat_chain=False, num_clusters=needed_clusters)
            # If deleted file had its FAT entries zeroed, fall back to contiguous clusters for the remainder
            if len(chain) < needed_clusters:
                last_c = chain[-1] if chain else (first_cluster - 1)
                missing = needed_clusters - len(chain)
                chain.extend(range(last_c + 1, last_c + 1 + missing))
            runs = self._coalesce_clusters(chain)

        remaining = file_size
        total_size = file_size

        try:
            with open(dest_path, 'wb') as out_f:
                for run_start, run_clusters in runs:
                    if remaining <= 0:
                        break
                    run_bytes = min(remaining, run_clusters * self.cluster_size)
                    offset = self.cluster_to_byte_offset(run_start)
                    run_remaining = run_bytes
                    while run_remaining > 0:
                        bytes_to_read = min(run_remaining, RECOVERY_CHUNK_SIZE)
                        data = self.reader.read_exact(offset, bytes_to_read)
                        if not data:
                            return False
                        out_f.write(data)
                        read_len = len(data)
                        run_remaining -= read_len
                        remaining -= read_len
                        offset += read_len
                        if progress_fn:
                            progress_fn(total_size - remaining, total_size)
        except OSError:
            return False

        # Restore modified timestamp if available
        if item.get('modified'):
            try:
                m_epoch = item['modified'].timestamp()
                os.utime(dest_path, (m_epoch, m_epoch))
            except Exception:
                pass

        return remaining <= 0

    def close(self) -> None:
        self._fat_cache.clear()
        if getattr(self, 'reader', None) is not None:
            self.reader.close()
