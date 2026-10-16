"""
Unit tests for ChronoRecovery Session (RSF) capture and restore system.
"""

import os
import tempfile
import unittest
from recovery_session import (
    RSFHeader,
    RSFChunk,
    MAGIC_GUID,
    GUID_PARTITION_INFO,
    GUID_SCAN_CONFIG,
    GUID_FILE_TREE,
    calculate_header_crc,
    PartitionInfo,
    ScanConfig,
    FileNode,
    RecoverySession
)

class TestRSFFormat(unittest.TestCase):
    def test_header_crc_and_serialization(self):
        desc = "Test Recovery Session 123"
        hdr = RSFHeader(block_size=8000, version=1, flags=0, description=desc)
        raw = hdr.serialize()
        self.assertEqual(len(raw), 132)
        self.assertEqual(raw[:16], MAGIC_GUID)
        
        # Verify CRC calculation
        crc = calculate_header_crc(raw)
        self.assertEqual(crc, hdr.checksum)
        
        # Deserialization test
        loaded_hdr = RSFHeader.deserialize(raw)
        self.assertEqual(loaded_hdr.magic, MAGIC_GUID)
        self.assertEqual(loaded_hdr.block_size, 8000)
        self.assertEqual(loaded_hdr.version, 1)
        self.assertEqual(loaded_hdr.description, desc)
        self.assertEqual(loaded_hdr.checksum, hdr.checksum)

    def test_corrupted_crc_fails(self):
        hdr = RSFHeader(description="Valid Session")
        raw = bytearray(hdr.serialize())
        # Corrupt one byte in the description
        raw[40] ^= 0xFF
        with self.assertRaises(ValueError):
            RSFHeader.deserialize(bytes(raw))

    def test_partition_info(self):
        parts = ["Partition1", "Partition2", "VolumeC"]
        p_info = PartitionInfo(parts)
        data = p_info.serialize()
        restored = PartitionInfo.deserialize(data)
        self.assertEqual(restored.partitions, parts)

    def test_scan_config(self):
        cfg = ScanConfig(scan_mode=2)
        data = cfg.serialize()
        restored = ScanConfig.deserialize(data)
        self.assertEqual(restored.scan_mode, 2)

    def test_file_node_hierarchy(self):
        root = FileNode(node_id=1, name="RootFolder", is_directory=True)
        child1 = FileNode(node_id=2, name="document.docx", is_directory=False, size=15420, start_sector=4096)
        child2 = FileNode(node_id=3, name="SubFolder", is_directory=True)
        subchild = FileNode(node_id=4, name="photo.jpg", is_directory=False, size=2048576, start_sector=5000)
        
        child2.add_child(subchild)
        root.add_child(child1)
        root.add_child(child2)
        
        raw_tree = root.serialize()
        import io
        stream = io.BytesIO(raw_tree)
        loaded_root = FileNode.deserialize_from_stream(stream)
        
        self.assertEqual(loaded_root.name, "RootFolder")
        self.assertTrue(loaded_root.is_directory)
        self.assertEqual(len(loaded_root.children), 2)
        self.assertEqual(loaded_root.children[0].name, "document.docx")
        self.assertEqual(loaded_root.children[0].size, 15420)
        self.assertEqual(loaded_root.children[0].start_sector, 4096)
        self.assertEqual(loaded_root.children[1].name, "SubFolder")
        self.assertEqual(len(loaded_root.children[1].children), 1)
        self.assertEqual(loaded_root.children[1].children[0].name, "photo.jpg")
        self.assertEqual(loaded_root.children[1].children[0].size, 2048576)

    def test_end_to_end_capture_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp_src:
            # Create sample files
            os.makedirs(os.path.join(tmp_src, "folder1", "subfolder"), exist_ok=True)
            with open(os.path.join(tmp_src, "test1.txt"), "w") as f:
                f.write("Hello World Data Recovery")
            with open(os.path.join(tmp_src, "folder1", "data.bin"), "wb") as f:
                f.write(b"\x00\xFF" * 512)
            with open(os.path.join(tmp_src, "folder1", "subfolder", "deep.txt"), "w") as f:
                f.write("Deep scan item")

            with tempfile.TemporaryDirectory() as tmp_out:
                rsf_path = os.path.join(tmp_out, "session.rsf")
                
                # 1. Capture
                session = RecoverySession.capture_from_path(tmp_src, description="Automated Unit Test")
                session.save_rsf(rsf_path)
                self.assertTrue(os.path.exists(rsf_path))
                self.assertGreater(os.path.getsize(rsf_path), 132)

                # 2. Restore
                restored = RecoverySession.load_rsf(rsf_path)
                self.assertEqual(restored.header.description, "Automated Unit Test")
                self.assertEqual(len(restored.root_nodes), 1)

                # Search
                results = restored.search("deep.txt")
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0][0].endswith("deep.txt"))

    def test_corrupted_chunk_size_rejected(self):
        import io
        import struct
        bad_chunk = io.BytesIO(GUID_FILE_TREE + struct.pack('<Q', 999_999_999_999))
        with self.assertRaises(ValueError):
            RSFChunk.read_next_chunk(bad_chunk)

    def test_corrupted_filenode_bounds_rejected(self):
        import io
        import struct
        # Node with bogus filename length > 64KB
        bad_node = struct.pack('<QBQQQQII', 1, 0, 0, 0, 0, 0, 100_000, 0)
        with self.assertRaises(ValueError):
            FileNode.deserialize_from_stream(io.BytesIO(bad_node))


class TestExFatScanner(unittest.TestCase):
    """Tests ExFatScanner on a synthetic exFAT disk image (headless, no hardware needed)."""

    def _build_synthetic_exfat_image(self, path: str):
        import struct
        # Layout parameters:
        # 512 bytes/sector (shift=9), 8 sectors/cluster = 4096 bytes/cluster (shift=3)
        # fat_offset = 32 sectors (offset 16384)
        # fat_length = 8 sectors (4096 bytes)
        # cluster_heap_offset = 64 sectors (offset 32768)
        # cluster_count = 64 clusters
        # root_dir_cluster = 2
        sector_size = 512
        cluster_size = 4096
        heap_offset_bytes = 64 * sector_size
        total_bytes = heap_offset_bytes + (64 * cluster_size)
        img = bytearray(total_bytes)

        # Boot sector
        img[3:11] = b'EXFAT   '
        struct.pack_into('<I', img, 64, 0)    # partition_offset
        struct.pack_into('<Q', img, 72, total_bytes // sector_size)
        struct.pack_into('<I', img, 80, 32)   # fat_offset (sectors)
        struct.pack_into('<I', img, 84, 8)    # fat_length (sectors)
        struct.pack_into('<I', img, 88, 64)   # cluster_heap_offset (sectors)
        struct.pack_into('<I', img, 92, 64)   # cluster_count
        struct.pack_into('<I', img, 96, 2)    # root_dir_cluster
        img[108] = 9                          # bytes_per_sector_shift (512)
        img[109] = 3                          # sectors_per_cluster_shift (8 -> 4096B)
        img[110] = 1                          # num_fats

        # FAT entries at offset 32 * 512 = 16384:
        # Cluster 2: Root directory (EOF = 0xFFFFFFFF)
        # Cluster 3 -> Cluster 5 (fragmented deleted MP4 file!)
        # Cluster 4: Active file colliding with another deleted file
        fat_base = 32 * sector_size
        struct.pack_into('<I', img, fat_base + 2 * 4, 0xFFFFFFFF)
        struct.pack_into('<I', img, fat_base + 3 * 4, 5)
        struct.pack_into('<I', img, fat_base + 4 * 4, 0xFFFFFFFF)
        struct.pack_into('<I', img, fat_base + 5 * 4, 0xFFFFFFFF)

        def write_dir_entry_set(dir_offset: int, slot: int, is_deleted: bool, is_dir: bool,
                                name: str, first_cluster: int, size: int, no_fat_chain: bool) -> int:
            name_utf16 = name.encode('utf-16le')
            name_Entries = (len(name_utf16) + 29) // 30
            sec_count = 1 + name_Entries

            # 1. File entry
            pos = dir_offset + slot * 32
            img[pos] = 0x05 if is_deleted else 0x85
            img[pos + 1] = sec_count
            struct.pack_into('<H', img, pos + 4, 0x10 if is_dir else 0x20)
            struct.pack_into('<I', img, pos + 8, (1 << 25) | (1 << 21) | (1 << 16))  # 1981-01-01
            struct.pack_into('<I', img, pos + 12, (1 << 25) | (1 << 21) | (1 << 16))

            # 2. Stream extension
            pos_s = dir_offset + (slot + 1) * 32
            img[pos_s] = 0x40 if is_deleted else 0xC0
            img[pos_s + 1] = 0x03 if no_fat_chain else 0x01
            img[pos_s + 3] = len(name)
            struct.pack_into('<Q', img, pos_s + 8, size)
            struct.pack_into('<I', img, pos_s + 20, first_cluster)
            struct.pack_into('<Q', img, pos_s + 24, size)

            # 3. File name entries
            for idx in range(name_Entries):
                pos_n = dir_offset + (slot + 2 + idx) * 32
                img[pos_n] = 0x41 if is_deleted else 0xC1
                chunk = name_utf16[idx * 30:(idx + 1) * 30]
                img[pos_n + 2:pos_n + 2 + len(chunk)] = chunk

            return slot + 1 + sec_count

        root_off = heap_offset_bytes + (2 - 2) * cluster_size
        slot = 0
        # Entry 1: Fragmented deleted MP4 across clusters 3 and 5 (size 5000 bytes, no_fat_chain=False)
        slot = write_dir_entry_set(root_off, slot, True, False, "clip_frag.mp4", 3, 5000, False)
        # Entry 2: Active file at cluster 4 (size 2048 bytes)
        slot = write_dir_entry_set(root_off, slot, False, False, "new_doc.pdf", 4, 2048, True)
        # Entry 3: Deleted file also pointing to cluster 4 (overwritten by new_doc.pdf)
        slot = write_dir_entry_set(root_off, slot, True, False, "old_overwritten.mp4", 4, 2048, True)

        # Write payload to cluster 3 (first 4096B of clip_frag.mp4) and cluster 5 (remaining 904B)
        c3_off = heap_offset_bytes + (3 - 2) * cluster_size
        c5_off = heap_offset_bytes + (5 - 2) * cluster_size
        mp4_hdr = b'\x00\x00\x00\x18ftypmp42' + (b'A' * (4096 - 12))
        mp4_tail = b'B' * 904
        img[c3_off:c3_off + 4096] = mp4_hdr
        img[c5_off:c5_off + 904] = mp4_tail

        # Write PDF header to cluster 4
        c4_off = heap_offset_bytes + (4 - 2) * cluster_size
        img[c4_off:c4_off + 10] = b'%PDF-1.7\r\n'

        with open(path, 'wb') as f:
            f.write(img)

    def test_exfat_scan_fat_chain_and_collision(self):
        from exfat_recovery import ExFatScanner
        with tempfile.TemporaryDirectory() as tmp:
            img_path = os.path.join(tmp, "synthetic_exfat.img")
            self._build_synthetic_exfat_image(img_path)

            with ExFatScanner(image_path=img_path) as scanner:
                results = scanner.scan_all_files()
                by_name = {r['name']: r for r in results}

                self.assertIn("clip_frag.mp4", by_name)
                self.assertIn("new_doc.pdf", by_name)
                self.assertIn("old_overwritten.mp4", by_name)

                # Verify fragmented deleted MP4 is 100% intact and recovers across non-contiguous clusters 3 -> 5
                frag = by_name["clip_frag.mp4"]
                self.assertEqual(frag['status'], 'DELETED')
                self.assertTrue(frag['integrity'].startswith("100% INTACT"))

                recovered_mp4 = os.path.join(tmp, "out", "clip_frag.mp4")
                self.assertTrue(scanner.recover_file(frag, recovered_mp4))
                with open(recovered_mp4, "rb") as rf:
                    data = rf.read()
                self.assertEqual(len(data), 5000)
                self.assertTrue(data.startswith(b'\x00\x00\x00\x18ftypmp42'))
                self.assertEqual(data[4096:], b'B' * 904)

                # Verify cluster collision detection on old_overwritten.mp4
                overwritten = by_name["old_overwritten.mp4"]
                self.assertIn("OVERWRITTEN", overwritten['integrity'])
                self.assertIn("new_doc.pdf", overwritten['integrity'])

    def test_drive_utils_enumeration(self):
        from drive_utils import get_system_drives
        drives = get_system_drives()
        self.assertIsInstance(drives, list)
        if os.name == 'nt':
            self.assertGreaterEqual(len(drives), 1)
            self.assertIn('letter', drives[0])


if __name__ == '__main__':
    unittest.main()

