#!/usr/bin/env python3
"""
USB exFAT MP4 Analyzer & Recovery Tool for drive G:.
Scans exFAT directory tables for active and deleted MP4 files and can recover them directly.
"""

import os
import argparse
from typing import Tuple, List, Dict, Any
from exfat_recovery import (
    AlignedVolumeReader,
    ExFatScanner,
    parse_exfat_timestamp,
    human_size,
    RECOVERY_CHUNK_SIZE,
)


def scan_exfat_volume(drive_letter: str = "G") -> Tuple[AlignedVolumeReader, int, int, List[Dict[str, Any]]]:
    """Scans an exFAT volume using ExFatScanner and returns reader metadata and discovered files."""
    scanner = ExFatScanner(drive_letter)
    found_files = scanner.scan_all_files()
    return scanner.reader, scanner.heap_offset_bytes, scanner.cluster_size, found_files


def recover_file(reader: AlignedVolumeReader, heap_offset_bytes: int,
                 cluster_size: int, item: Dict[str, Any], dest_path: str) -> bool:
    """Recovers a single file from the exFAT cluster heap."""
    if item.get('size', 0) <= 0 or item.get('first_cluster', 0) < 2:
        return False

    parent_dir = os.path.dirname(os.path.abspath(dest_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    cluster_num = item['first_cluster']
    remaining = item['size']
    offset = heap_offset_bytes + (cluster_num - 2) * cluster_size

    try:
        with open(dest_path, 'wb') as out_f:
            while remaining > 0:
                bytes_to_read = min(remaining, RECOVERY_CHUNK_SIZE)
                data = reader.read_exact(offset, bytes_to_read)
                if not data:
                    return False
                out_f.write(data)
                remaining -= len(data)
                offset += len(data)
        return remaining <= 0
    except OSError:
        return False

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
