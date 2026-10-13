#!/usr/bin/env python3
"""
USB exFAT MP4 Analyzer & Recovery Tool for drive G:.
Scans exFAT directory tables for active and deleted MP4 files and can recover them directly.
"""

import sys
import os
import struct
import argparse
from datetime import datetime

class AlignedVolumeReader:
    def __init__(self, volume_path, sector_size=512):
        self.f = open(volume_path, 'rb')
        self.sector_size = sector_size

    def read_exact(self, offset, size):
        aligned_start = (offset // self.sector_size) * self.sector_size
        offset_in_sector = offset - aligned_start
        total_to_read = ((offset_in_sector + size + self.sector_size - 1) // self.sector_size) * self.sector_size
        self.f.seek(aligned_start)
        data = self.f.read(total_to_read)
        return data[offset_in_sector : offset_in_sector + size]

    def close(self):
        self.f.close()

def parse_exfat_timestamp(ts_val):
    if not ts_val:
        return None
    # 32-bit exFAT DOS timestamp: [year-1980:7][month:4][day:5][hour:5][minute:6][second/2:5]
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

def scan_exfat_volume(drive_letter="G"):
    vol_path = rf"\\.\{drive_letter}:"
    reader = AlignedVolumeReader(vol_path)
    bs = reader.read_exact(0, 512)
    if bs[3:11] != b'EXFAT   ':
        raise ValueError(f"Drive {drive_letter}: is not an exFAT volume")

    sector_size = 1 << bs[0x6C]
    cluster_size = sector_size * (1 << bs[0x6D])
    heap_offset_bytes = struct.unpack('<I', bs[0x58:0x5C])[0] * sector_size
    cluster_count = struct.unpack('<I', bs[0x5C:0x60])[0]
    root_cluster = struct.unpack('<I', bs[0x60:0x64])[0]
    fat_offset_bytes = struct.unpack('<I', bs[0x50:0x54])[0] * sector_size

    def cluster_to_byte_offset(c):
        return heap_offset_bytes + (c - 2) * cluster_size

    def read_fat_entry(c):
        data = reader.read_exact(fat_offset_bytes + c * 4, 4)
        return struct.unpack('<I', data)[0]

    def get_cluster_chain(start_cluster, no_fat_chain=False, num_clusters=1):
        if no_fat_chain:
            return list(range(start_cluster, start_cluster + num_clusters))
        chain = []
        curr = start_cluster
        while 2 <= curr <= cluster_count + 1:
            chain.append(curr)
            nxt = read_fat_entry(curr)
            if nxt >= 0xFFFFFFF8 or nxt == 0xFFFFFFF7:
                break
            if nxt == curr or nxt in chain:
                break
            curr = nxt
        return chain

    visited_clusters = set()
    found_files = []

    def parse_directory(start_cluster, path_prefix="", is_contiguous=False, length_bytes=0):
        num_clusters = max(1, (length_bytes + cluster_size - 1) // cluster_size) if length_bytes else 1
        chain = get_cluster_chain(start_cluster, no_fat_chain=is_contiguous, num_clusters=num_clusters)
        if not chain and start_cluster >= 2:
            chain = [start_cluster]

        for c in chain:
            if c in visited_clusters:
                continue
            visited_clusters.add(c)
            cluster_bytes = reader.read_exact(cluster_to_byte_offset(c), cluster_size)

            i = 0
            while i < len(cluster_bytes):
                entry = cluster_bytes[i:i+32]
                entry_type = entry[0]
                if entry_type == 0x00:
                    i += 32
                    continue

                is_deleted = not bool(entry_type & 0x80)
                base_type = entry_type & 0x7F

                if base_type == 0x05:
                    secondary_count = entry[1]
                    attrs = struct.unpack('<H', entry[4:6])[0]
                    is_dir = bool(attrs & 0x10)
                    ctime_raw = struct.unpack('<I', entry[8:12])[0]
                    mtime_raw = struct.unpack('<I', entry[12:16])[0]

                    stream_entry = cluster_bytes[i+32 : i+64] if i+32 < len(cluster_bytes) else None
                    first_cluster = 0
                    file_size = 0
                    no_fat_chain = False
                    if stream_entry and (stream_entry[0] & 0x7F) == 0x40:
                        general_flags = stream_entry[1]
                        no_fat_chain = bool(general_flags & 2)
                        first_cluster = struct.unpack('<I', stream_entry[20:24])[0]
                        file_size = struct.unpack('<Q', stream_entry[24:32])[0]

                    name_parts = []
                    for s_idx in range(1, secondary_count):
                        offset_s = i + 32 * (s_idx + 1)
                        if offset_s + 32 <= len(cluster_bytes):
                            n_entry = cluster_bytes[offset_s : offset_s + 32]
                            if (n_entry[0] & 0x7F) == 0x41:
                                name_chunk = n_entry[2:32].decode('utf-16le', errors='replace').split('\x00')[0]
                                name_parts.append(name_chunk)

                    filename = "".join(name_parts)
                    full_path = f"{path_prefix}\\{filename}" if path_prefix else filename
                    status = "DELETED" if is_deleted else "ACTIVE"

                    if filename:
                        found_files.append({
                            "name": filename,
                            "path": full_path,
                            "status": status,
                            "is_dir": is_dir,
                            "size": file_size,
                            "first_cluster": first_cluster,
                            "no_fat_chain": no_fat_chain,
                            "created": parse_exfat_timestamp(ctime_raw),
                            "modified": parse_exfat_timestamp(mtime_raw),
                        })

                        if is_dir and first_cluster >= 2 and first_cluster not in visited_clusters:
                            parse_directory(first_cluster, full_path, is_contiguous=no_fat_chain, length_bytes=file_size)

                    i += 32 * (1 + secondary_count)
                else:
                    i += 32

    parse_directory(root_cluster, f"{drive_letter}:")
    return reader, heap_offset_bytes, cluster_size, found_files

def recover_file(reader, heap_offset_bytes, cluster_size, item, dest_path):
    if item['size'] <= 0 or item['first_cluster'] < 2:
        return False

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    cluster_num = item['first_cluster']
    remaining = item['size']
    offset = heap_offset_bytes + (cluster_num - 2) * cluster_size

    # In exFAT, if no_fat_chain is true, it is stored in contiguous clusters
    chunk_to_read = min(remaining, cluster_size * 32)
    with open(dest_path, 'wb') as out_f:
        while remaining > 0:
            bytes_to_read = min(remaining, 1024 * 1024)
            data = reader.read_exact(offset, bytes_to_read)
            if not data:
                break
            out_f.write(data)
            remaining -= len(data)
            offset += len(data)
    return True

def human_size(n_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n_bytes) < 1024.0:
            return f"{n_bytes:3.1f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:.1f} PB"

def main():
    parser = argparse.ArgumentParser(description="Analyze and recover MP4 files from G: USB")
    parser.add_argument("--drive", default="G", help="Drive letter (default: G)")
    parser.add_argument("--recover-all", action="store_true", help="Recover all intact MP4 files")
    parser.add_argument("--recover-index", type=int, help="Recover a specific file by its index number")
    parser.add_argument("--output-dir", default="./recovered_mp4", help="Directory where recovered files are saved")
    args = parser.parse_args()

    print(f"[*] Scanning exFAT filesystem on {args.drive}:...")
    reader, heap_offset_bytes, cluster_size, files = scan_exfat_volume(args.drive)

    mp4_files = [f for f in files if f['name'].lower().endswith('.mp4')]
    print(f"[+] Total files in directory records: {len(files)}")
    print(f"[+] Total MP4 files discovered     : {len(mp4_files)}")

    print("\n" + "="*110)
    print(f"{'Idx':<4} | {'Status':<7} | {'Size':>10} | {'Cluster':<8} | {'Integrity':<20} | {'Filename'}")
    print("="*110)

    repertoire = []
    for idx, item in enumerate(mp4_files):
        integrity = "UNKNOWN"
        if item['first_cluster'] >= 2 and item['size'] > 0:
            offset = heap_offset_bytes + (item['first_cluster'] - 2) * cluster_size
            first_bytes = reader.read_exact(offset, 16)
            if b'ftyp' in first_bytes:
                brand = first_bytes[8:12].decode('latin1', errors='replace').strip()
                integrity = f"VALID (brand: {brand})"
            elif b'moov' in first_bytes:
                integrity = "VALID (moov first)"
            else:
                integrity = "OVERWRITTEN"
        else:
            integrity = "NO_DATA"

        item['integrity'] = integrity
        item['index'] = idx
        repertoire.append(item)
        print(f"{idx:<4} | {item['status']:<7} | {human_size(item['size']):>10} | {item['first_cluster']:<8} | {integrity:<20} | {item['path']}")

    print("="*110)

    # Recover all intact
    if args.recover_all:
        intact = [item for item in repertoire if item['integrity'].startswith("VALID")]
        print(f"\n[*] Recovering {len(intact)} intact MP4 files to {args.output_dir}...")
        for item in intact:
            # Flatten or keep rel path
            rel_name = os.path.basename(item['name'])
            target_path = os.path.join(args.output_dir, item['status'].lower(), rel_name)
            print(f"  -> Recovering [{item['index']}] {item['name']} ({human_size(item['size'])})...", end=" ")
            ok = recover_file(reader, heap_offset_bytes, cluster_size, item, target_path)
            print("DONE" if ok else "FAILED")
        print(f"[+] All {len(intact)} intact files recovered to: {os.path.abspath(args.output_dir)}")

    elif args.recover_index is not None:
        idx = args.recover_index
        if 0 <= idx < len(repertoire):
            item = repertoire[idx]
            target_path = os.path.join(args.output_dir, item['status'].lower(), os.path.basename(item['name']))
            print(f"\n[*] Recovering [{idx}] {item['name']} ({human_size(item['size'])})...", end=" ")
            ok = recover_file(reader, heap_offset_bytes, cluster_size, item, target_path)
            print(f"DONE -> Saved to: {os.path.abspath(target_path)}" if ok else "FAILED")
        else:
            print(f"[-] Invalid index {idx}. Choose between 0 and {len(repertoire)-1}.")

    reader.close()

if __name__ == '__main__':
    main()
