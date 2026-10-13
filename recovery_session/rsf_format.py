"""
RSF (Recovery Scan File) Format Specification and Serializer/Deserializer
Structured binary container format for filesystem scan results.

Binary Specifications:
1. Global File Header (132 bytes / 0x84):
   - 0x00..0x0F (16 bytes): Magic GUID (EA F4 B3 1B 05 43 B6 4A B4 B8 24 4A 33 D9 13 BB)
   - 0x10..0x13 (4 bytes):  Block / Buffer size (uint32, default 0x1F40 = 8000)
   - 0x14..0x17 (4 bytes):  CRC-16 Checksum (uint16 stored as uint32, poly 0x8005)
   - 0x18..0x1B (4 bytes):  Format Version (uint32, valid: 1, 2, 3, 4)
   - 0x1C..0x1F (4 bytes):  Flags / Scan Target Type (uint32)
   - 0x20..0x23 (4 bytes):  Description String Length N (uint32, max 100)
   - 0x24..0x83 (96 bytes): Description text buffer (total description field 100 bytes)

2. Chunk Structure:
   - Chunk Header (36 bytes / 0x24):
     - 0x00..0x0F (16 bytes): Magic GUID (same as file header)
     - 0x10..0x1F (16 bytes): Chunk Type GUID
     - 0x20..0x23 (4 bytes):  Chunk Payload Length (uint32)
   - Chunk Payload (variable length)

Known Chunk Types:
- GUID_PARTITION_INFO: F1 44 AE 6E A7 5C F8 49 BD 8D 71 26 D4 46 AA CA
- GUID_SCAN_CONFIG:    25 65 C0 7D 8A 63 8C 4A B7 D1 64 19 64 12 47 DB
- GUID_FILE_TREE:      6C F2 08 D2 8C 07 34 4E 9D 71 D9 1F 53 5F 7B 57
"""

import struct
from typing import List, Dict, Optional, Tuple, Any

# Magic and Section GUIDs
MAGIC_GUID = bytes.fromhex("eaf4b31b0543b64ab4b8244a33d913bb")
GUID_PARTITION_INFO = bytes.fromhex("f144ae6ea75cf849bd8d7126d446aaca")
GUID_SCAN_CONFIG    = bytes.fromhex("2565c07d8a638c4ab7d16419641247db")
GUID_FILE_TREE      = bytes.fromhex("6cf208d28c07344e9d71d91f535f7b57")

HEADER_SIZE = 132       # 0x84 bytes
CHUNK_HEADER_SIZE = 36 # 0x24 bytes

# Precomputed CRC-16 table with poly 0x8005 (IBM / BUYPASS)
def _build_crc16_table(poly: int = 0x8005) -> List[int]:
    table = []
    for i in range(256):
        r8w = (i << 8) & 0xFFFF
        cx = 0
        for _ in range(8):
            ax = (cx ^ r8w) & 0xFFFF
            cx = (cx << 1) & 0xFFFF
            if ax & 0x8000:
                cx ^= poly
            r8w = (r8w << 1) & 0xFFFF
        table.append(cx)
    return table

_CRC16_TABLE = _build_crc16_table(0x8005)

def calculate_header_crc(header_bytes: bytes) -> int:
    """Calculates CRC-16 over the 132-byte header with checksum field at offset 0x14 set to 0."""
    if len(header_bytes) != HEADER_SIZE:
        raise ValueError(f"Header must be exactly {HEADER_SIZE} bytes")
    # Zero out checksum field (offset 0x14 to 0x18)
    buf = bytearray(header_bytes)
    buf[0x14:0x18] = b'\x00\x00\x00\x00'
    bx = 0
    for b in buf:
        idx = ((bx >> 8) ^ b) & 0xFF
        bx = ((bx << 8) ^ _CRC16_TABLE[idx]) & 0xFFFF
    return bx

class RSFHeader:
    def __init__(self, block_size: int = 0x1F40, version: int = 1, flags: int = 0, description: str = ""):
        self.magic = MAGIC_GUID
        self.block_size = block_size
        self.version = version
        self.flags = flags
        self.description = description
        self.checksum = 0

    def serialize(self) -> bytes:
        desc_bytes = self.description.encode('utf-8')[:96]
        desc_len = len(desc_bytes)
        desc_field = (desc_bytes + b'\x00' * 96)[:96]
        
        # Build 132-byte block with checksum = 0
        raw = bytearray(HEADER_SIZE)
        raw[0x00:0x10] = self.magic
        struct.pack_into('<I', raw, 0x10, self.block_size)
        struct.pack_into('<I', raw, 0x14, 0) # Checksum placeholder
        struct.pack_into('<I', raw, 0x18, self.version)
        struct.pack_into('<I', raw, 0x1C, self.flags)
        struct.pack_into('<I', raw, 0x20, desc_len)
        raw[0x24:0x84] = desc_field
        
        # Calculate CRC-16
        self.checksum = calculate_header_crc(bytes(raw))
        struct.pack_into('<I', raw, 0x14, self.checksum)
        return bytes(raw)

    @classmethod
    def deserialize(cls, data: bytes) -> 'RSFHeader':
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Insufficient data for RSF header: got {len(data)}, expected {HEADER_SIZE}")
        magic = data[0x00:0x10]
        if magic != MAGIC_GUID:
            raise ValueError(f"Invalid RSF magic GUID: {magic.hex()}")
        
        block_size, stored_crc, version, flags, desc_len = struct.unpack('<IIIII', data[0x10:0x24])
        computed_crc = calculate_header_crc(data[:HEADER_SIZE])
        if stored_crc != computed_crc:
            raise ValueError(f"Header CRC checksum mismatch: stored=0x{stored_crc:04X}, computed=0x{computed_crc:04X}")
        
        desc_bytes = data[0x24 : 0x24 + min(desc_len, 96)].split(b'\x00')[0]
        description = desc_bytes.decode('utf-8', errors='replace')
        
        header = cls(block_size=block_size, version=version, flags=flags, description=description)
        header.checksum = stored_crc
        return header

class RSFChunk:
    def __init__(self, chunk_guid: bytes, payload: bytes):
        self.magic = MAGIC_GUID
        self.chunk_guid = chunk_guid
        self.payload = payload

    def serialize(self) -> bytes:
        hdr = bytearray(CHUNK_HEADER_SIZE)
        hdr[0x00:0x10] = self.magic
        hdr[0x10:0x20] = self.chunk_guid
        struct.pack_into('<I', hdr, 0x20, len(self.payload))
        return bytes(hdr) + self.payload

    @classmethod
    def read_next_chunk(cls, stream) -> Optional['RSFChunk']:
        hdr_bytes = stream.read(CHUNK_HEADER_SIZE)
        if not hdr_bytes:
            return None
        if len(hdr_bytes) < CHUNK_HEADER_SIZE:
            raise ValueError("Unexpected EOF while reading chunk header")
        
        magic = hdr_bytes[0x00:0x10]
        if magic != MAGIC_GUID:
            raise ValueError(f"Corrupted chunk magic: {magic.hex()}")
        
        chunk_guid = hdr_bytes[0x10:0x20]
        payload_len = struct.unpack('<I', hdr_bytes[0x20:0x24])[0]
        payload = stream.read(payload_len)
        if len(payload) < payload_len:
            raise ValueError(f"Truncated chunk payload: expected {payload_len} bytes, got {len(payload)}")
        return cls(chunk_guid, payload)
