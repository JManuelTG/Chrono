"""
Windows Drive Utilities for Enumerating Physical and Logical Drives.
Uses native Windows API calls via ctypes.
"""

import string
import ctypes
from typing import List, Dict, Any

DRIVE_TYPE_NAMES = {
    0: 'Unknown',
    1: 'No Root Dir',
    2: 'Removable (USB)',
    3: 'Fixed Disk',
    4: 'Network Drive',
    5: 'CD-ROM',
    6: 'RAM Disk'
}

def get_system_drives() -> List[Dict[str, Any]]:
    """Enumerates all logical drives and returns their specifications."""
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    GetVolumeInformationW = ctypes.windll.kernel32.GetVolumeInformationW
    GetDriveTypeW = ctypes.windll.kernel32.GetDriveTypeW
    
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            root = f"{letter}:\\"
            dtype = GetDriveTypeW(root)
            vol_name_buf = ctypes.create_unicode_buffer(261)
            fs_name_buf = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_ulong()
            max_len = ctypes.c_ulong()
            flags = ctypes.c_ulong()
            
            res = GetVolumeInformationW(
                root, vol_name_buf, 261,
                ctypes.byref(serial), ctypes.byref(max_len), ctypes.byref(flags),
                fs_name_buf, 261
            )
            label = vol_name_buf.value if res else ""
            fs = fs_name_buf.value if res else "Unknown"
            
            free_bytes = ctypes.c_ulonglong()
            total_bytes = ctypes.c_ulonglong()
            total_free = ctypes.c_ulonglong()
            sz_res = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                root, ctypes.byref(free_bytes), ctypes.byref(total_bytes), ctypes.byref(total_free)
            )
            
            total_gb = total_bytes.value / (1024**3) if sz_res else 0.0
            free_gb = free_bytes.value / (1024**3) if sz_res else 0.0
            
            drives.append({
                'letter': letter,
                'path': f"{letter}:",
                'root': root,
                'label': label,
                'type': DRIVE_TYPE_NAMES.get(dtype, 'Unknown'),
                'is_removable': (dtype == 2),
                'fs': fs,
                'total_bytes': total_bytes.value,
                'free_bytes': free_bytes.value,
                'total_gb': total_gb,
                'free_gb': free_gb
            })
        bitmask >>= 1
    return drives
