"""
ChronoRecovery Capture and Restore Session Engine.
Structured scan state management:
- Capture: Scan target directory/partition, build recovery tree, and export RSF file.
- Restore: Import RSF file, verify integrity, reconstruct filesystem hierarchy, and extract files.
"""

import os
import io
import time
import struct
from typing import List, Optional, Generator, Tuple
from .rsf_format import (
    RSFHeader, RSFChunk, MAGIC_GUID,
    GUID_PARTITION_INFO, GUID_SCAN_CONFIG, GUID_FILE_TREE
)
from .models import PartitionInfo, ScanConfig, FileNode

class RecoverySession:
    def __init__(
        self,
        header: Optional[RSFHeader] = None,
        partition_info: Optional[PartitionInfo] = None,
        scan_config: Optional[ScanConfig] = None,
        root_nodes: Optional[List[FileNode]] = None
    ):
        self.header = header or RSFHeader()
        self.partition_info = partition_info or PartitionInfo()
        self.scan_config = scan_config or ScanConfig()
        self.root_nodes = root_nodes or []

    @classmethod
    def capture_from_path(cls, path: str, description: str = "Capture Session", sector_size: int = 512) -> 'RecoverySession':
        """
        Scans a local path/volume and captures its state into a RecoverySession.
        Simulates partition discovery, filesystem cataloging, and sector mapping.
        """
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Source path not found: {path}")

        # 1. Infer Partition / Volume Info
        drive, rest = os.path.splitdrive(abs_path)
        part_name = f"Volume:{drive or 'Root'};Target:{os.path.basename(abs_path)};FS:NTFS"
        part_info = PartitionInfo([part_name])
        scan_cfg = ScanConfig(scan_mode=0)

        # 2. Build File Tree
        node_counter = 1
        current_sector = 2048  # Simulating standard 1MB partition alignment

        def scan_dir(dir_path: str, depth: int = 0) -> FileNode:
            nonlocal node_counter, current_sector
            try:
                stat = os.stat(dir_path, follow_symlinks=False)
                ctime = int(stat.st_ctime)
                mtime = int(stat.st_mtime)
            except OSError:
                ctime = 0
                mtime = 0

            node = FileNode(
                node_id=node_counter,
                name=os.path.basename(dir_path) or dir_path,
                is_directory=True,
                size=0,
                start_sector=current_sector,
                creation_time=ctime,
                modified_time=mtime,
                attributes=0x10,
                fs_type=0
            )
            node_counter += 1
            current_sector += 8  # 8 sectors per directory index record

            if depth >= 128:
                return node

            try:
                with os.scandir(dir_path) as it:
                    entries = sorted(it, key=lambda e: e.name)
            except OSError:
                return node

            dir_size = 0
            for entry in entries:
                try:
                    # Do not follow symlinks or Windows junctions to prevent infinite loops
                    if entry.is_symlink():
                        continue
                    item_stat = entry.stat(follow_symlinks=False)
                    if entry.is_dir(follow_symlinks=False):
                        child = scan_dir(entry.path, depth + 1)
                        node.add_child(child)
                        dir_size += child.size
                    else:
                        f_size = item_stat.st_size
                        f_node = FileNode(
                            node_id=node_counter,
                            name=entry.name,
                            is_directory=False,
                            size=f_size,
                            start_sector=current_sector,
                            creation_time=int(item_stat.st_ctime),
                            modified_time=int(item_stat.st_mtime),
                            attributes=0x20,
                            fs_type=0
                        )
                        node_counter += 1
                        sectors = max(1, (f_size + sector_size - 1) // sector_size)
                        current_sector += sectors
                        node.add_child(f_node)
                        dir_size += f_size
                except OSError:
                    continue

            node.size = dir_size
            return node

        root_node = scan_dir(abs_path)
        hdr = RSFHeader(
            block_size=0x1F40,
            version=1,
            flags=0,
            description=description
        )
        return cls(header=hdr, partition_info=part_info, scan_config=scan_cfg, root_nodes=[root_node])

    def save_rsf(self, output_path: str) -> None:
        """Serializes session to a binary .rsf file."""
        parent_dir = os.path.dirname(os.path.abspath(output_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(output_path, 'wb') as f:
            # 1. Write Header (132 bytes)
            f.write(self.header.serialize())

            # 2. Write Partition Info Chunk
            part_payload = self.partition_info.serialize()
            part_chunk = RSFChunk(GUID_PARTITION_INFO, part_payload)
            f.write(part_chunk.serialize())

            # 3. Write Scan Config Chunk
            cfg_payload = self.scan_config.serialize()
            cfg_chunk = RSFChunk(GUID_SCAN_CONFIG, cfg_payload)
            f.write(cfg_chunk.serialize())

            # 4. Write File Tree Chunk
            tree_buf = bytearray()
            tree_buf += struct.pack('<B', 0)  # is_filter_scan (uint8 = 0)

            total_dirs = 0
            total_files = 0
            stack = list(self.root_nodes)
            while stack:
                n = stack.pop()
                if n.is_directory:
                    total_dirs += 1
                else:
                    total_files += 1
                stack.extend(n.children)

            # directory count, reserved, raw/deep count, root items count
            tree_buf += struct.pack('<IIII', total_dirs, 0, total_files, len(self.root_nodes))
            for rn in self.root_nodes:
                rn.serialize_to_buffer(tree_buf)

            tree_chunk = RSFChunk(GUID_FILE_TREE, bytes(tree_buf))
            f.write(tree_chunk.serialize())

    @classmethod
    def load_rsf(cls, rsf_path: str) -> 'RecoverySession':
        """Loads and restores session from an RSF file."""
        with open(rsf_path, 'rb') as f:
            header_bytes = f.read(132)
            header = RSFHeader.deserialize(header_bytes)

            part_info = None
            scan_cfg = None
            root_nodes = []

            while True:
                chunk = RSFChunk.read_next_chunk(f)
                if not chunk:
                    break

                if chunk.chunk_guid == GUID_PARTITION_INFO:
                    part_info = PartitionInfo.deserialize(chunk.payload)
                elif chunk.chunk_guid == GUID_SCAN_CONFIG:
                    scan_cfg = ScanConfig.deserialize(chunk.payload)
                elif chunk.chunk_guid == GUID_FILE_TREE:
                    stream = io.BytesIO(chunk.payload)
                    is_filter_scan = struct.unpack('<B', stream.read(1))[0]
                    if is_filter_scan == 0:
                        total_dirs, _, total_files, root_count = struct.unpack('<IIII', stream.read(16))
                    else:
                        total_files, root_count = struct.unpack('<II', stream.read(8))
                    
                    for _ in range(root_count):
                        node = FileNode.deserialize_from_stream(stream)
                        root_nodes.append(node)

            return cls(
                header=header,
                partition_info=part_info or PartitionInfo(),
                scan_config=scan_cfg or ScanConfig(),
                root_nodes=root_nodes
            )

    def walk(self) -> Generator[Tuple[str, FileNode], None, None]:
        """Yields (path, FileNode) for every entry in the tree."""
        def _walk_node(prefix: str, node: FileNode):
            curr_path = os.path.join(prefix, node.name) if prefix else node.name
            yield curr_path, node
            for child in node.children:
                yield from _walk_node(curr_path, child)

        for rn in self.root_nodes:
            yield from _walk_node("", rn)

    def search(self, query: str) -> List[Tuple[str, FileNode]]:
        """Finds all files/folders matching a query substring."""
        query_l = query.lower()
        results = []
        for path, node in self.walk():
            if query_l in node.name.lower():
                results.append((path, node))
        return results
