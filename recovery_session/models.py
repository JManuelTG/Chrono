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

    def add_child(self, child: 'FileNode'):
        self.children.append(child)

    def total_descendants(self) -> int:
        count = len(self.children)
        for c in self.children:
            count += c.total_descendants()
        return count

    def serialize(self) -> bytes:
        """
        Serializes node according to CFileSystemNode::Serialize:
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
        out = bytearray()
        # 1. Node type (1 = CFileSystemNode)
        out += struct.pack('<I', 1)
        # 2. Node ID
        out += struct.pack('<Q', self.node_id)
        
        # 3. 40-byte properties struct:
        # [0x00..0x07] Size (uint64)
        # [0x08..0x0F] Creation time (uint64)
        # [0x10..0x17] Modified time (uint64)
        # [0x18..0x1B] Attributes (uint32, e.g. 0x10 for dir, 0x20 for archive)
        # [0x1C..0x1F] Deleted / state flags (uint32)
        # [0x20..0x27] Reserved / padding (8 bytes)
        prop_bytes = bytearray(40)
        struct.pack_into('<Q', prop_bytes, 0, self.size)
        struct.pack_into('<Q', prop_bytes, 8, self.creation_time)
        struct.pack_into('<Q', prop_bytes, 16, self.modified_time)
        struct.pack_into('<I', prop_bytes, 24, self.attributes | (0x10 if self.is_directory else 0))
        struct.pack_into('<I', prop_bytes, 28, 1 if self.deleted else 0)
        out += prop_bytes
        
        # 4. Sector / cluster offset
        out += struct.pack('<Q', self.start_sector)
        # 5. Extra flags
        out += struct.pack('<I', 0)
        # 6. Extra flags
        out += struct.pack('<I', 0)
        
        # 7-9. Filename
        name_bytes = self.name.encode('utf-16le')
        out += struct.pack('<I', len(name_bytes))
        out += struct.pack('<I', 1)  # UTF-16LE indicator
        out += name_bytes
        
        # 10. Children
        out += struct.pack('<I', self.fs_type)
        out += struct.pack('<I', len(self.children))
        for child in self.children:
            out += child.serialize()
            
        return bytes(out)

    @classmethod
    def deserialize_from_stream(cls, stream) -> 'FileNode':
        """Deserializes a FileNode and all its descendants from a binary stream."""
        # 1. Node type
        type_bytes = stream.read(4)
        if not type_bytes or len(type_bytes) < 4:
            raise ValueError("Unexpected EOF reading node type")
        node_type = struct.unpack('<I', type_bytes)[0]
        
        # 2. Node ID
        node_id = struct.unpack('<Q', stream.read(8))[0]
        
        # 3. 40 bytes properties
        prop_bytes = stream.read(40)
        size, ctime, mtime, attrs, state_flags = struct.unpack('<QQQII', prop_bytes[:32])
        is_dir = bool(attrs & 0x10)
        deleted = bool(state_flags & 1)
        
        # 4. Start sector
        start_sector = struct.unpack('<Q', stream.read(8))[0]
        # 5 & 6. Reserved
        stream.read(8)
        
        # 7-9. Filename
        name_len, enc_flags = struct.unpack('<II', stream.read(8))
        raw_name = stream.read(name_len)
        if enc_flags == 1:
            name = raw_name.decode('utf-16le', errors='replace')
        else:
            name = raw_name.decode('utf-8', errors='replace')
            
        # 10. Children
        fs_type, child_count = struct.unpack('<II', stream.read(8))
        
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
            child = cls.deserialize_from_stream(stream)
            node.add_child(child)
            
        return node
