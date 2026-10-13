"""
ChronoRecovery Binary Scan Session (RSF) package.
"""

from .rsf_format import (
    RSFHeader,
    RSFChunk,
    MAGIC_GUID,
    GUID_PARTITION_INFO,
    GUID_SCAN_CONFIG,
    GUID_FILE_TREE,
    calculate_header_crc
)
from .models import PartitionInfo, ScanConfig, FileNode
from .engine import RecoverySession

__all__ = [
    "RSFHeader",
    "RSFChunk",
    "MAGIC_GUID",
    "GUID_PARTITION_INFO",
    "GUID_SCAN_CONFIG",
    "GUID_FILE_TREE",
    "calculate_header_crc",
    "PartitionInfo",
    "ScanConfig",
    "FileNode",
    "RecoverySession",
]
