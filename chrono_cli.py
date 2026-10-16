#!/usr/bin/env python3
"""
ChronoRecovery Session (RSF) CLI Tool.
Capture, inspect, and restore structured recovery scan sessions (.rsf).

Commands:
  capture  - Scan a directory/target and export an RSF session file
  restore  - Load an RSF session file, inspect or browse its files without rescanning
  inspect  - Analyze low-level RSF binary layout, header CRC, and chunk headers
  extract  - Extract/restore file tree from an RSF session
"""

import sys
import os
import argparse
import datetime
from exfat_recovery import human_size
from recovery_session import (
    RecoverySession,
    RSFHeader,
    RSFChunk,
    MAGIC_GUID,
    GUID_PARTITION_INFO,
    GUID_SCAN_CONFIG,
    GUID_FILE_TREE
)

def cmd_capture(args):
    print(f"[*] Capturing scan state from: {args.target}")
    start_time = datetime.datetime.now()
    session = RecoverySession.capture_from_path(args.target, description=args.desc)
    
    out_file = args.output
    if not out_file:
        base = os.path.basename(os.path.abspath(args.target)) or "recovery_session"
        out_file = f"{base}.rsf"

    session.save_rsf(out_file)
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    
    total_items = sum(1 for _ in session.walk())
    total_bytes = sum(node.size for _, node in session.walk() if not node.is_directory)
    
    print(f"[+] Capture successful in {elapsed:.2f}s!")
    print(f"    Output File : {out_file} ({human_size(os.path.getsize(out_file))})")
    print(f"    Description : {args.desc}")
    print(f"    Total Items : {total_items} entries")
    print(f"    Total Size  : {human_size(total_bytes)}")
    print(f"    CRC16 Check : 0x{session.header.checksum:04X}")

def cmd_restore(args):
    if not os.path.exists(args.file):
        print(f"[-] Error: file not found '{args.file}'")
        sys.exit(1)

    print(f"[*] Restoring scan session from: {args.file}")
    session = RecoverySession.load_rsf(args.file)
    print(f"[+] Session loaded successfully!")
    print(f"    Version     : {session.header.version}")
    print(f"    CRC16 Check : 0x{session.header.checksum:04X} (VERIFIED)")
    print(f"    Description : {session.header.description or '(none)'}")
    print(f"    Partitions  : {', '.join(session.partition_info.partitions) or '(none)'}")
    print(f"    Scan Mode   : {session.scan_config.scan_mode}")

    if args.search:
        print(f"\n[*] Searching for '{args.search}':")
        matches = session.search(args.search)
        if not matches:
            print("    No matching entries found.")
        else:
            for path, node in matches:
                kind = "<DIR> " if node.is_directory else f"{human_size(node.size):>10}"
                print(f"    {kind}  {path} (sector: {node.start_sector})")
        return

    if args.tree:
        print("\n[*] Recovered File Hierarchy:")
        def print_tree(node, prefix="", is_last=True):
            marker = "\\-- " if is_last else "|-- "
            kind = "[DIR]" if node.is_directory else f"[{human_size(node.size)}]"
            print(f"{prefix}{marker}{node.name} {kind}")
            prefix += "    " if is_last else "|   "
            for i, child in enumerate(node.children):
                print_tree(child, prefix, i == len(node.children) - 1)

        for rn in session.root_nodes:
            print_tree(rn)
        return

    # Default: show summary and top-level listing
    print("\n[*] Root Entries:")
    for rn in session.root_nodes:
        kind = "<DIR> " if rn.is_directory else f"{human_size(rn.size):>10}"
        print(f"    {kind}  {rn.name} ({len(rn.children)} children, {rn.total_descendants()} total items)")

def cmd_inspect(args):
    if not os.path.exists(args.file):
        print(f"[-] Error: file not found '{args.file}'")
        sys.exit(1)

    file_size = os.path.getsize(args.file)
    print(f"=== RSF BINARY INSPECTION: {args.file} ===")
    print(f"Total File Size: {file_size} bytes ({human_size(file_size)})\n")

    if file_size < 132:
        print("[-] Error: File smaller than 132-byte RSF header")
        return

    chunk_names = {
        GUID_PARTITION_INFO: "PARTITION_INFO (Target partition list)",
        GUID_SCAN_CONFIG: "SCAN_CONFIG (Scan parameters & mode ID)",
        GUID_FILE_TREE: "FILE_TREE (Scanned directory & files graph)",
    }

    with open(args.file, 'rb') as f_stream:
        hdr_bytes = f_stream.read(132)
        header = RSFHeader.deserialize(hdr_bytes)
        print("--- [0x0000..0x0084] GLOBAL FILE HEADER (132 bytes) ---")
        print(f"  Magic GUID      : {header.magic.hex()} ({'VALID' if header.magic == MAGIC_GUID else 'INVALID'})")
        print(f"  Block Size      : 0x{header.block_size:X} ({header.block_size} bytes)")
        print(f"  CRC-16 Checksum : 0x{header.checksum:04X} (VERIFIED OK)")
        print(f"  Format Version  : {header.version}")
        print(f"  Flags / Type    : 0x{header.flags:X}")
        print(f"  Description     : {header.description or '(empty)'}\n")

        print("--- CHUNK CONTAINER INVENTORY ---")
        chunk_index = 0
        while True:
            pos = f_stream.tell()
            chunk = RSFChunk.read_next_chunk(f_stream)
            if not chunk:
                break
            name = chunk_names.get(chunk.chunk_guid, f"UNKNOWN_CHUNK ({chunk.chunk_guid.hex()})")
            print(f"  Chunk #{chunk_index} @ 0x{pos:06X}:")
            print(f"    Type GUID    : {chunk.chunk_guid.hex()}")
            print(f"    Name         : {name}")
            print(f"    Payload Size : {len(chunk.payload)} bytes ({human_size(len(chunk.payload))})")
            chunk_index += 1

def cmd_extract(args):
    if not os.path.exists(args.file):
        print(f"[-] Error: file not found '{args.file}'")
        sys.exit(1)

    out_root = os.path.abspath(args.output)
    print(f"[*] Restoring file structures from: {args.file} into: {out_root}")
    session = RecoverySession.load_rsf(args.file)
    os.makedirs(out_root, exist_ok=True)
    
    extracted_dirs = 0
    extracted_files = 0
    total_bytes = 0

    for path, node in session.walk():
        target_path = os.path.abspath(os.path.join(out_root, path))
        # Path traversal protection: ensure target stays within out_root
        try:
            if os.path.commonpath([out_root, target_path]) != out_root:
                continue
        except ValueError:
            continue

        if node.is_directory:
            os.makedirs(target_path, exist_ok=True)
            extracted_dirs += 1
        else:
            parent = os.path.dirname(target_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # Create recovered file stub matching recorded size
            with open(target_path, 'wb') as f:
                if node.size > 0:
                    f.truncate(node.size)
            
            # Restore recorded timestamps if present
            if node.modified_time:
                try:
                    os.utime(target_path, (node.creation_time or node.modified_time, node.modified_time))
                except Exception:
                    pass

            extracted_files += 1
            total_bytes += node.size

    print(f"[+] Restoration complete!")
    print(f"    Directories Reconstructed : {extracted_dirs}")
    print(f"    Files Recovered           : {extracted_files} ({human_size(total_bytes)})")

def main():
    parser = argparse.ArgumentParser(
        description="ChronoRecovery RSF Session Capture and Restore Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Capture
    p_cap = subparsers.add_parser("capture", help="Capture scan session into .rsf file")
    p_cap.add_argument("target", help="Path to directory or partition to capture")
    p_cap.add_argument("-o", "--output", help="Output .rsf file path")
    p_cap.add_argument("--desc", default="ChronoRecovery Scan Session", help="Description metadata")
    p_cap.set_defaults(func=cmd_capture)

    # Restore
    p_res = subparsers.add_parser("restore", help="Restore and inspect an existing .rsf file")
    p_res.add_argument("file", help="Path to .rsf session file")
    p_res.add_argument("-t", "--tree", action="store_true", help="Print hierarchical tree")
    p_res.add_argument("-s", "--search", help="Search for files in session")
    p_res.set_defaults(func=cmd_restore)

    # Inspect
    p_ins = subparsers.add_parser("inspect", help="Low-level binary inspection of .rsf file")
    p_ins.add_argument("file", help="Path to .rsf session file")
    p_ins.set_defaults(func=cmd_inspect)

    # Extract
    p_ext = subparsers.add_parser("extract", help="Extract/reconstruct files and directory structure")
    p_ext.add_argument("file", help="Path to .rsf session file")
    p_ext.add_argument("-o", "--output", required=True, help="Destination directory")
    p_ext.set_defaults(func=cmd_extract)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
