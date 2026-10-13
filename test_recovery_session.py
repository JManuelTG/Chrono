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

if __name__ == '__main__':
    unittest.main()
