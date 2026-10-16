"""
Windows Drive Utilities for Enumerating Physical and Logical Drives.
Uses native Windows API calls via ctypes.
"""

import string
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any

DRIVE_TYPE_NAMES: Dict[int, str] = {
    0: 'Unknown',
    1: 'No Root Dir',
    2: 'Removable (USB)',
    3: 'Fixed Disk',
    4: 'Network Drive',
    5: 'CD-ROM',
    6: 'RAM Disk'
}

SEM_FAILCRITICALERRORS = 0x0001
MAX_VOLUME_NAME = 261


def get_system_drives() -> List[Dict[str, Any]]:
    """Enumerates all logical drives and returns their specifications."""
    if not hasattr(ctypes, 'windll'):
        return []

    kernel32 = ctypes.windll.kernel32

    # Explicitly configure Win32 API signatures for 64-bit pointer safety
    GetLogicalDrives = kernel32.GetLogicalDrives
    GetLogicalDrives.argtypes = []
    GetLogicalDrives.restype = wintypes.DWORD

    GetDriveTypeW = kernel32.GetDriveTypeW
    GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    GetDriveTypeW.restype = wintypes.UINT

    GetVolumeInformationW = kernel32.GetVolumeInformationW
    GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD
    ]
    GetVolumeInformationW.restype = wintypes.BOOL

    GetDiskFreeSpaceExW = kernel32.GetDiskFreeSpaceExW
    GetDiskFreeSpaceExW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong)
    ]
    GetDiskFreeSpaceExW.restype = wintypes.BOOL

    # Suppress Windows modal error boxes for unmounted card readers / optical drives
    old_err_mode = kernel32.SetErrorMode(SEM_FAILCRITICALERRORS)
    drives: List[Dict[str, Any]] = []
    try:
        bitmask = GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                root = f"{letter}:\\"
                dtype = GetDriveTypeW(root)
                vol_name_buf = ctypes.create_unicode_buffer(MAX_VOLUME_NAME)
                fs_name_buf = ctypes.create_unicode_buffer(MAX_VOLUME_NAME)
                serial = wintypes.DWORD()
                max_len = wintypes.DWORD()
                flags = wintypes.DWORD()

                res = GetVolumeInformationW(
                    root, vol_name_buf, MAX_VOLUME_NAME,
                    ctypes.byref(serial), ctypes.byref(max_len), ctypes.byref(flags),
                    fs_name_buf, MAX_VOLUME_NAME
                )
                label = vol_name_buf.value if res else ""
                fs = fs_name_buf.value if res else "Unknown"

                free_bytes = ctypes.c_ulonglong()
                total_bytes = ctypes.c_ulonglong()
                total_free = ctypes.c_ulonglong()
                sz_res = GetDiskFreeSpaceExW(
                    root, ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free)
                )

                total_gb = total_bytes.value / (1024 ** 3) if sz_res else 0.0
                free_gb = free_bytes.value / (1024 ** 3) if sz_res else 0.0

                drives.append({
                    'letter': letter,
                    'path': f"{letter}:",
                    'root': root,
                    'label': label,
                    'type': DRIVE_TYPE_NAMES.get(dtype, 'Unknown'),
                    'is_removable': (dtype == 2),
                    'fs': fs,
                    'total_bytes': total_bytes.value if sz_res else 0,
                    'free_bytes': free_bytes.value if sz_res else 0,
                    'total_gb': total_gb,
                    'free_gb': free_gb
                })
            bitmask >>= 1
    finally:
        kernel32.SetErrorMode(old_err_mode)

    return drives
