"""
Data models representing Partition Info, Scan Configuration, and Recovered File Tree.
Implements high-performance recursive node serialization and deserialization for RSF sessions.
"""

import struct
from typing import List, Optional, Dict, Any
from datetime import datetime

class PartitionInfo:
    def __init__(self, partitions: Optional[List[str]] = None):
        self.partitions = partitions or []

    def serialize(self) -> bytes:
        content = ";".join(self.partitions)
        if self.partitions and not content.endswith(";"):
            content += ";"
        content_bytes = content.encode('utf-8')
        return struct.pack('<I', len(content_bytes)) + content_bytes

    @classmethod
    def deserialize(cls, data: bytes) -> 'PartitionInfo':
        if len(data) < 4:
            return cls([])
        str_len = struct.unpack('<I', data[:4])[0]
        content = data[4 : 4 + str_len].decode('utf-8', errors='replace')
        parts = [p.strip() for p in content.split(';') if p.strip()]
        return cls(parts)

class ScanConfig:
    def __init__(self, scan_mode: int = 0):
        self.scan_mode = scan_mode  # 0 = Normal, 1 = Formatted, 2 = Raw, etc.

    def serialize(self) -> bytes:
        return struct.pack('<I', self.scan_mode)

    @classmethod
    def deserialize(cls, data: bytes) -> 'ScanConfig':
        if len(data) < 4:
            return cls(0)
        mode = struct.unpack('<I', data[:4])[0]
        return cls(mode)

MAX_TREE_DEPTH = 256
MAX_FILENAME_BYTES = 65536
MAX_NODE_CHILDREN = 1_000_000


class FileNode:
    """
    Represents a file or directory node in the recovery scan tree.
    Directly reflects CFileSystemNode / CFileNode serialized records.
    """
    def __init__(
        self,
        node_id: int,
        name: str,
        is_directory: bool = False,
        size: int = 0,
        start_sector: int = 0,
        creation_time: int = 0,
        modified_time: int = 0,
        attributes: int = 0,
        fs_type: int = 0,  # 0=NTFS, 1=FAT, 2=ExFAT, 3=Ext, 4=HFS+, 5=ReFS, 6=RAW
        deleted: bool = False,
    ):
        self.node_id = node_id
        self.name = name
        self.is_directory = is_directory
        self.size = size
        self.start_sector = start_sector
        self.creation_time = creation_time
        self.modified_time = modified_time
        self.attributes = attributes
        self.fs_type = fs_type
        self.deleted = deleted
        self.children: List['FileNode'] = []

    def add_child(self, child: 'FileNode') -> None:
        self.children.append(child)

    def total_descendants(self) -> int:
        count = len(self.children)
        for c in self.children:
            count += c.total_descendants()
        return count

    def serialize_to_buffer(self, out: bytearray) -> None:
        """
        Appends serialized node and descendants directly into `out` in O(N) time:
        1. Node Type: uint32 = 1
        2. Node ID: uint64 (8 bytes)
        3. 40-byte File Properties record (size, timestamps, attributes, flags)
        4. Start sector: uint64 (8 bytes)
        5. uint32 (4 bytes)
        6. uint32 (4 bytes)
        7. Filename length: uint32 (4 bytes)
        8. Filename encoding/flags: uint32 (4 bytes)
        9. Filename bytes (N bytes)
        10. Children header:
            - uint32 fs_type
            - uint32 child_count
            - Serialized children
        """
        name_bytes = self.name.encode('utf-16le')
        attrs = self.attributes | (0x10 if self.is_directory else 0)
        state_flags = 1 if self.deleted else 0

        # Pack fixed 68-byte prefix + variable name + 8-byte children header
        out += struct.pack(
            '<IQQQQII8xQIIII',
            1,                  # Node type (1 = CFileSystemNode)
            self.node_id,       # Node ID
            self.size,          # [0x00..0x07] Size
            self.creation_time, # [0x08..0x0F] Creation time
            self.modified_time, # [0x10..0x17] Modified time
            attrs,              # [0x18..0x1B] Attributes
            state_flags,        # [0x1C..0x1F] Deleted / state flags (+ 8x reserved)
            self.start_sector,  # Start sector
            0,                  # Extra flags 1
            0,                  # Extra flags 2
            len(name_bytes),    # Filename byte length
            1                   # UTF-16LE encoding indicator
        )
        out += name_bytes
        out += struct.pack('<II', self.fs_type, len(self.children))

        for child in self.children:
            child.serialize_to_buffer(out)

    def serialize(self) -> bytes:
        """Serializes node and all descendants into a bytes object."""
        out = bytearray()
        self.serialize_to_buffer(out)
        return bytes(out)

    @classmethod
    def deserialize_from_stream(cls, stream, _depth: int = 0) -> 'FileNode':
        """Deserializes a FileNode and all its descendants from a binary stream."""
        if _depth > MAX_TREE_DEPTH:
            raise ValueError(f"Maximum directory nesting depth ({MAX_TREE_DEPTH}) exceeded")

        # 1. Node type
        type_bytes = stream.read(4)
        if len(type_bytes) < 4:
            raise ValueError("Unexpected EOF reading node type")

        # 2. Node ID (8B) + 3. Properties (40B) + 4. Start sector (8B) + 5&6. Reserved (8B) + 7&8. Name header (8B) = 72 bytes
        fixed_hdr = stream.read(72)
        if len(fixed_hdr) < 72:
            raise ValueError("Unexpected EOF reading node header")

        node_id, size, ctime, mtime, attrs, state_flags, start_sector, name_len, enc_flags = struct.unpack(
            '<QQQQII8xQ8xII', fixed_hdr
        )
        if name_len > MAX_FILENAME_BYTES:
            raise ValueError(f"Corrupted filename length: {name_len} bytes")

        is_dir = bool(attrs & 0x10)
        deleted = bool(state_flags & 1)

        # 9. Filename
        raw_name = stream.read(name_len)
        if len(raw_name) < name_len:
            raise ValueError("Unexpected EOF reading node filename")
        if enc_flags == 1:
            name = raw_name.decode('utf-16le', errors='replace')
        else:
            name = raw_name.decode('utf-8', errors='replace')

        # 10. Children
        child_hdr = stream.read(8)
        if len(child_hdr) < 8:
            raise ValueError("Unexpected EOF reading node children header")
        fs_type, child_count = struct.unpack('<II', child_hdr)
        if child_count > MAX_NODE_CHILDREN:
            raise ValueError(f"Corrupted child count: {child_count}")

        node = cls(
            node_id=node_id,
            name=name,
            is_directory=is_dir,
            size=size,
            start_sector=start_sector,
            creation_time=ctime,
            modified_time=mtime,
            attributes=attrs,
            fs_type=fs_type,
            deleted=deleted
        )

        for _ in range(child_count):
            child = cls.deserialize_from_stream(stream, _depth=_depth + 1)
            node.add_child(child)

        return node
