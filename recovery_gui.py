#!/usr/bin/env python3
"""
ChronoRecovery — Advanced Deep Filesystem & File Recovery GUI.
Allows selecting storage drives (e.g. G: USB), scanning active and deleted files,
inspecting cluster/sector integrity, searching/filtering, and recovering intact files.
Also supports exporting and importing structured .rsf scan sessions.
"""

import sys
import os
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

# High DPI awareness for crisp text on Windows
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from drive_utils import get_system_drives
from exfat_recovery import ExFatScanner, human_size, verify_file_integrity
from recovery_session import (
    RecoverySession,
    RSFHeader,
    PartitionInfo,
    FileNode
)

FILE_CATEGORIES = {
    "All Files & Folders (*.*)": None,
    "Photos & Images (*.jpg, *.png, *.raw, *.heic)": {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif',
        '.tif', '.tiff', '.raw', '.dng', '.cr2', '.nef', '.arw', '.psd', '.ai',
        '.svg', '.ico', '.eps'
    },
    "Documents & Office (*.pdf, *.docx, *.xlsx)": {
        '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.txt',
        '.csv', '.rtf', '.odt', '.ods', '.odp', '.epub', '.md', '.log',
        '.tex', '.pages', '.numbers', '.key', '.json', '.xml', '.html'
    },
    "All Videos (*.mp4, *.mkv, *.mov, *.avi)": {
        '.mp4', '.m4v', '.mov', '.mkv', '.avi', '.wmv', '.flv', '.webm',
        '.ts', '.3gp', '.vob', '.mts', '.m2ts'
    },
    "MP4 Videos Only (*.mp4)": {
        '.mp4', '.m4v'
    },
    "Audio & Music (*.mp3, *.wav, *.flac)": {
        '.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma',
        '.mid', '.midi', '.aif', '.aiff'
    },
    "Archives & Compressed (*.zip, *.rar, *.7z)": {
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.dmg',
        '.cab', '.jar', '.apk'
    },
    "Executables & Programs (*.exe, *.msi)": {
        '.exe', '.msi', '.dll', '.sys', '.bat', '.cmd', '.ps1', '.sh'
    }
}

class DataRecoveryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ChronoRecovery — Advanced Deep Filesystem & File Recovery Suite")
        self.geometry("1180x720")
        self.minsize(950, 580)

        # Setup Window & Taskbar Icon
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_ico = os.path.join(self.base_dir, "assets", "icons", "app_icon.ico")
        icon_png = os.path.join(self.base_dir, "assets", "icons", "app_icon.png")

        self.icon_img_18 = None
        self.icon_img_24 = None
        self._window_icon = None

        if os.path.exists(icon_ico):
            try:
                self.iconbitmap(icon_ico)
            except Exception:
                pass

        if os.path.exists(icon_png):
            try:
                pil_img = Image.open(icon_png)
                self._window_icon = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, self._window_icon)
                self.icon_img_18 = ImageTk.PhotoImage(pil_img.resize((18, 18), Image.Resampling.LANCZOS))
                self.icon_img_24 = ImageTk.PhotoImage(pil_img.resize((24, 24), Image.Resampling.LANCZOS))
            except Exception:
                pass

        # State
        self.drives = []
        self.current_scanner = None
        self.all_files = []      # Raw scanned items
        self.displayed_files = [] # Filtered view
        self.is_scanning = False
        self.is_recovering = False
        self.last_recovered_dir = ""

        # Setup Styles
        self.setup_styles()
        
        # Build UI
        self.build_ui()

        # Load drives on startup
        self.refresh_drives()

    def setup_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use('vista')
        except Exception:
            pass

        self.style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        self.style.configure("Title.TLabel", font=("Segoe UI", 11, "bold"))
        self.style.configure("Stat.TLabel", font=("Segoe UI", 9))

    def build_ui(self):
        # App Header Banner with Icon
        header = ttk.Frame(self, padding=(14, 8, 14, 2))
        header.pack(fill="x")
        if self.icon_img_24:
            ttk.Label(header, image=self.icon_img_24).pack(side="left", padx=(0, 8))
        ttk.Label(header, text="ChronoRecovery", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Label(header, text=" — Advanced Deep Filesystem & File Recovery Suite", font=("Segoe UI", 9), foreground="#555555").pack(side="left")

        # 1. Top Panel: Drive & Filter Controls
        top_frame = ttk.LabelFrame(self, text=" Storage & Scan Configuration ", padding=10)
        top_frame.pack(fill="x", padx=12, pady=(4, 6))

        # Row 1: Drive selection and Scan button
        r1 = ttk.Frame(top_frame)
        r1.pack(fill="x", pady=2)

        ttk.Label(r1, text="Select Drive:").pack(side="left", padx=(0, 6))
        self.drive_combo = ttk.Combobox(r1, state="readonly", width=62)
        self.drive_combo.pack(side="left", padx=(0, 8))
        self.drive_combo.bind("<<ComboboxSelected>>", self.on_drive_selected)

        self.btn_refresh = ttk.Button(r1, text="🔄 Refresh", command=self.refresh_drives, width=10)
        self.btn_refresh.pack(side="left", padx=(0, 16))

        self.btn_scan = ttk.Button(r1, text="⚡ Scan Drive", style="Accent.TButton", command=self.start_scan)
        self.btn_scan.pack(side="right", padx=4)

        # Row 2: Category and Quick Filters
        r2 = ttk.Frame(top_frame)
        r2.pack(fill="x", pady=(6, 2))

        ttk.Label(r2, text="Category:").pack(side="left", padx=(0, 6))
        self.category_combo = ttk.Combobox(r2, state="readonly", width=38, values=list(FILE_CATEGORIES.keys()))
        self.category_combo.current(0)
        self.category_combo.pack(side="left", padx=(0, 10))
        self.category_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        def set_cat(cat_key):
            self.category_combo.set(cat_key)
            self.apply_filters()

        ttk.Label(r2, text="Quick:").pack(side="left", padx=(4, 2))
        quick_categories = [
            ("📁 All", "All Files & Folders (*.*)"),
            ("🖼️ Photos", "Photos & Images (*.jpg, *.png, *.raw, *.heic)"),
            ("📄 Docs", "Documents & Office (*.pdf, *.docx, *.xlsx)"),
            ("🎬 Videos", "All Videos (*.mp4, *.mkv, *.mov, *.avi)"),
            ("🎵 Audio", "Audio & Music (*.mp3, *.wav, *.flac)"),
            ("📦 Archives", "Archives & Compressed (*.zip, *.rar, *.7z)"),
        ]
        for label, cat_key in quick_categories:
            b = ttk.Button(r2, text=label, command=lambda k=cat_key: set_cat(k))
            b.pack(side="left", padx=2)

        # 2. Filter & Stats Bar
        filter_frame = ttk.Frame(self, padding=(12, 4))
        filter_frame.pack(fill="x")

        # Stats labels
        self.lbl_stats_total = ttk.Label(filter_frame, text="Total: 0 files", style="Stat.TLabel")
        self.lbl_stats_total.pack(side="left", padx=(0, 12))

        self.lbl_stats_deleted = ttk.Label(filter_frame, text="Deleted: 0", font=("Segoe UI", 9, "bold"), foreground="#c0392b")
        self.lbl_stats_deleted.pack(side="left", padx=(0, 12))

        self.lbl_stats_intact = ttk.Label(filter_frame, text="Intact: 0", font=("Segoe UI", 9, "bold"), foreground="#27ae60")
        self.lbl_stats_intact.pack(side="left", padx=(0, 20))

        # Checkboxes
        self.var_deleted_only = tk.BooleanVar(value=True)
        self.chk_deleted = ttk.Checkbutton(filter_frame, text="Deleted only", variable=self.var_deleted_only, command=self.apply_filters)
        self.chk_deleted.pack(side="left", padx=(0, 10))

        self.var_intact_only = tk.BooleanVar(value=False)
        self.chk_intact = ttk.Checkbutton(filter_frame, text="100% Intact only", variable=self.var_intact_only, command=self.apply_filters)
        self.chk_intact.pack(side="left", padx=(0, 20))

        # Live search box
        ttk.Label(filter_frame, text="🔍 Search:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filters())
        self.search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=28)
        self.search_entry.pack(side="left")

        # 3. Main Results Table
        table_frame = ttk.Frame(self, padding=(12, 4))
        table_frame.pack(fill="both", expand=True)

        columns = ("status", "integrity", "name", "size", "cluster", "modified", "path")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("status", text="Status", command=lambda: self.sort_column("status", False))
        self.tree.heading("integrity", text="Integrity / Health", command=lambda: self.sort_column("integrity", False))
        self.tree.heading("name", text="Filename", command=lambda: self.sort_column("name", False))
        self.tree.heading("size", text="Size", command=lambda: self.sort_column("size", False))
        self.tree.heading("cluster", text="Cluster / Sector", command=lambda: self.sort_column("cluster", False))
        self.tree.heading("modified", text="Date Modified", command=lambda: self.sort_column("modified", False))
        self.tree.heading("path", text="Original Path", command=lambda: self.sort_column("path", False))

        self.tree.column("status", width=85, anchor="center")
        self.tree.column("integrity", width=170, anchor="w")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("size", width=95, anchor="e")
        self.tree.column("cluster", width=110, anchor="center")
        self.tree.column("modified", width=140, anchor="center")
        self.tree.column("path", width=330, anchor="w")

        # Tags for colored items
        self.tree.tag_configure("deleted_intact", foreground="#1e8449")
        self.tree.tag_configure("deleted_corrupt", foreground="#888888")
        self.tree.tag_configure("active", foreground="#2c3e50")

        # Scrollbars
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 4. Status and Progress Bar
        progress_frame = ttk.Frame(self, padding=(12, 2))
        progress_frame.pack(fill="x")

        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=2)

        self.lbl_status = ttk.Label(progress_frame, text="Ready. Choose a drive and click 'Scan Drive'.", font=("Segoe UI", 9))
        self.lbl_status.pack(side="left")

        # 5. Bottom Actions Toolbar
        actions_frame = ttk.Frame(self, padding=(12, 10))
        actions_frame.pack(fill="x")

        # Left action buttons: Session persistence
        self.btn_save_rsf = ttk.Button(actions_frame, text="💾 Save Session (.rsf)", command=self.save_rsf_session)
        self.btn_save_rsf.pack(side="left", padx=(0, 6))

        self.btn_load_rsf = ttk.Button(actions_frame, text="📂 Load Session (.rsf)", command=self.load_rsf_session)
        self.btn_load_rsf.pack(side="left", padx=(0, 6))

        # Right action buttons: Recovery
        open_kw = {"command": self.open_recovery_folder}
        if self.icon_img_18:
            open_kw["image"] = self.icon_img_18
            open_kw["compound"] = "left"
            open_kw["text"] = " Open Recovery Folder"
        else:
            open_kw["text"] = "📁 Open Recovery Folder"
        self.btn_open_folder = ttk.Button(actions_frame, **open_kw)
        self.btn_open_folder.pack(side="right", padx=(6, 0))

        self.btn_recover_all = ttk.Button(actions_frame, text="⭐ Recover All Intact (In View)", style="Accent.TButton", command=self.recover_all_intact)
        self.btn_recover_all.pack(side="right", padx=(6, 0))

        self.btn_recover_selected = ttk.Button(actions_frame, text="📥 Recover Selected", command=self.recover_selected)
        self.btn_recover_selected.pack(side="right", padx=(6, 0))

    def refresh_drives(self):
        """Scans and populates available system drives."""
        self.drives = get_system_drives()
        options = []
        default_index = 0

        for idx, d in enumerate(self.drives):
            label_part = f"[{d['label']}]" if d['label'] else "[No Label]"
            removable_tag = " (USB)" if d['is_removable'] else ""
            desc = f"{d['letter']}: {label_part} — {d['type']}{removable_tag} ({d['fs']}) — {d['total_gb']:.1f} GB ({d['free_gb']:.1f} GB free)"
            options.append(desc)
            # Default to G: if connected, or first removable drive
            if d['letter'] == 'G' or (d['is_removable'] and default_index == 0):
                default_index = idx

        self.drive_combo['values'] = options
        if options:
            self.drive_combo.current(default_index)

    def on_drive_selected(self, event=None):
        pass

    def get_selected_drive(self):
        idx = self.drive_combo.current()
        if 0 <= idx < len(self.drives):
            return self.drives[idx]
        return None

    def start_scan(self):
        drive = self.get_selected_drive()
        if not drive:
            messagebox.showwarning("No Drive", "Please select a storage drive first.")
            return

        if self.is_scanning:
            return

        self.is_scanning = True
        self.btn_scan.config(state="disabled")
        self.btn_refresh.config(state="disabled")
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.lbl_status.config(text=f"Scanning {drive['letter']}: ({drive['fs']}) for directory entries and files...")

        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.all_files = []
        self.displayed_files = []

        thread = threading.Thread(target=self._scan_worker, args=(drive['letter'], drive['fs']), daemon=True)
        thread.start()

    def _scan_worker(self, drive_letter, fs_type):
        try:
            if fs_type.lower() == 'exfat':
                if self.current_scanner:
                    try: self.current_scanner.close()
                    except Exception: pass

                scanner = ExFatScanner(drive_letter)
                self.current_scanner = scanner

                def progress_fn(path, count):
                    self.after(0, lambda: self.lbl_status.config(text=f"Scanning {drive_letter}:... Found {count} items"))

                results = scanner.scan_all_files(progress_callback=progress_fn)
                self.after(0, lambda: self._scan_completed(results, None))
            else:
                # Fallback for standard filesystem
                self.after(0, lambda: self._scan_completed([], f"Direct cluster scanning currently optimized for exFAT (Drive is {fs_type})."))
        except Exception as e:
            self.after(0, lambda: self._scan_completed([], str(e)))

    def _scan_completed(self, results, error):
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate", value=100)
        self.btn_scan.config(state="normal")
        self.btn_refresh.config(state="normal")

        if error:
            messagebox.showerror("Scan Error", f"Failed to complete scan: {error}")
            self.lbl_status.config(text="Scan failed.")
            return

        self.all_files = results
        self.lbl_status.config(text=f"Scan complete. Discovered {len(self.all_files)} total items.")
        self.apply_filters()

    def apply_filters(self):
        """Filters the scanned files based on user category, deleted-only, intact-only, and search query."""
        category = self.category_combo.get()
        allowed_exts = FILE_CATEGORIES.get(category)
        deleted_only = self.var_deleted_only.get()
        intact_only = self.var_intact_only.get()
        query = self.search_var.get().strip().lower()

        filtered = []

        for f in self.all_files:
            if f['is_dir']:
                continue

            ext = os.path.splitext(f['name'])[1].lower()
            is_del = (f['status'] == 'DELETED')
            is_intact = f['integrity'].startswith("100% INTACT")

            # Category filter
            if allowed_exts is not None and ext not in allowed_exts:
                continue

            # Deleted filter
            if deleted_only and not is_del:
                continue

            # Intact filter
            if intact_only and not is_intact:
                continue

            # Search query
            if query and (query not in f['name'].lower() and query not in f['path'].lower()):
                continue

            filtered.append(f)

        self.displayed_files = filtered

        # Update stats labels based on filtered results
        tot_del = sum(1 for f in filtered if f['status'] == 'DELETED')
        tot_intact = sum(1 for f in filtered if f['integrity'].startswith("100% INTACT"))

        self.lbl_stats_total.config(text=f"Showing: {len(filtered)} / {len(self.all_files)} items")
        self.lbl_stats_deleted.config(text=f"Deleted: {tot_del}")
        self.lbl_stats_intact.config(text=f"100% Intact: {tot_intact}")

        # Populate tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, f in enumerate(filtered):
            tag = "active"
            if f['status'] == 'DELETED':
                tag = "deleted_intact" if f['integrity'].startswith("100% INTACT") else "deleted_corrupt"

            mod_str = f['modified'].strftime("%Y-%m-%d %H:%M") if f.get('modified') else "-"
            cluster_str = f"Cluster {f['first_cluster']}" if f.get('first_cluster') else "-"

            self.tree.insert("", "end", iid=str(idx), values=(
                f['status'],
                f['integrity'],
                f['name'],
                human_size(f['size']),
                cluster_str,
                mod_str,
                f['path']
            ), tags=(tag,))

    def sort_column(self, col, reverse):
        """Sorts TreeView by column values."""
        items = []
        for iid in self.tree.get_children():
            val = self.tree.set(iid, col)
            idx = int(iid)
            f_obj = self.displayed_files[idx]
            # Use raw size or cluster for numeric sorting
            if col == "size":
                sort_val = f_obj['size']
            elif col == "cluster":
                sort_val = f_obj.get('first_cluster', 0)
            elif col == "modified":
                sort_val = f_obj['modified'].timestamp() if f_obj.get('modified') else 0
            else:
                sort_val = val.lower()
            items.append((sort_val, iid))

        items.sort(reverse=reverse)
        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def recover_selected(self):
        selected_iids = self.tree.selection()
        if not selected_iids:
            messagebox.showinfo("No Selection", "Please select one or more files in the list to recover.")
            return

        items_to_recover = [self.displayed_files[int(iid)] for iid in selected_iids]
        self._prompt_and_run_recovery(items_to_recover)

    def recover_all_intact(self):
        intact_items = [f for f in self.displayed_files if not f['is_dir'] and f['integrity'].startswith("100% INTACT")]
        if not intact_items:
            messagebox.showinfo("No Intact Files", "No 100% intact files found in the current view.")
            return

        cat_title = self.category_combo.get().split('(')[0].strip()
        total_bytes = sum(f['size'] for f in intact_items)
        confirm = messagebox.askyesno(
            "Confirm Recovery",
            f"Found {len(intact_items)} intact {cat_title.lower()} ({human_size(total_bytes)} total).\n\n"
            "Would you like to recover all of them now?"
        )
        if confirm:
            self._prompt_and_run_recovery(intact_items)

    def _prompt_and_run_recovery(self, items):
        if not self.current_scanner:
            messagebox.showwarning("Scanner Missing", "Cannot recover without an active scanner. Please rescan the drive.")
            return

        # Check if any selected items were physically overwritten
        overwritten = [it for it in items if "OVERWRITTEN" in it.get('integrity', '')]
        if overwritten:
            details = "\n".join(f"• {it['name']}\n  -> {it['integrity']}" for it in overwritten[:4])
            if len(overwritten) > 4:
                details += f"\n... and {len(overwritten) - 4} more files"
            proceed = messagebox.askyesno(
                "Overwritten Data Warning",
                f"Warning: {len(overwritten)} selected file(s) have been physically overwritten on disk by newer files:\n\n"
                f"{details}\n\n"
                "Their original data was replaced when newer files were saved to the same sectors. "
                "Recovering them will extract the newer file's contents.\n\n"
                "Do you still want to proceed?"
            )
            if not proceed:
                return

        dest_dir = filedialog.askdirectory(title="Choose Destination Folder (Save to C: or D:, NEVER to G:)")
        if not dest_dir:
            return

        # Check safety: Destination must not be the drive being scanned!
        selected_drive = self.get_selected_drive()
        if selected_drive and dest_dir.upper().startswith(selected_drive['letter'].upper() + ":"):
            messagebox.showerror(
                "Unsafe Destination",
                f"CAUTION: You selected drive {selected_drive['letter']}: as destination!\n"
                "Writing recovered files to the same drive will permanently overwrite lost data.\n"
                "Please choose a different drive (such as C: or D:)."
            )
            return

        self.last_recovered_dir = dest_dir
        self.is_recovering = True
        self.progress_bar.config(mode="determinate", value=0)
        self.lbl_status.config(text=f"Recovering {len(items)} files to {dest_dir}...")

        thread = threading.Thread(target=self._recovery_worker, args=(items, dest_dir), daemon=True)
        thread.start()

    def _recovery_worker(self, items, dest_dir):
        total_count = len(items)
        success_count = 0
        failed_count = 0

        for i, item in enumerate(items):
            # Target path
            rel_name = os.path.basename(item['name'])
            target_path = os.path.join(dest_dir, item['status'].lower(), rel_name)

            self.after(0, lambda name=rel_name, num=i+1: self.lbl_status.config(
                text=f"Recovering [{num}/{total_count}] {name}..."
            ))

            ok = self.current_scanner.recover_file(item, target_path)
            if ok:
                success_count += 1
            else:
                failed_count += 1

            progress_pct = int(((i + 1) / total_count) * 100)
            self.after(0, lambda val=progress_pct: self.progress_bar.config(value=val))

        self.after(0, lambda: self._recovery_completed(success_count, failed_count, dest_dir))

    def _recovery_completed(self, success, failed, dest_dir):
        self.is_recovering = False
        self.lbl_status.config(text=f"Recovery finished! {success} files recovered successfully to {dest_dir}")
        messagebox.showinfo(
            "Recovery Complete",
            f"Successfully recovered {success} files.\n"
            f"Failed: {failed}\n\n"
            f"Files saved in: {dest_dir}"
        )

    def open_recovery_folder(self):
        target = self.last_recovered_dir if (self.last_recovered_dir and os.path.exists(self.last_recovered_dir)) else os.path.abspath(".")
        subprocess.Popen(f'explorer "{target}"')

    def save_rsf_session(self):
        """Exports current scan state to a binary .rsf session file."""
        if not self.all_files:
            messagebox.showinfo("No Scan Results", "Please run a scan first before saving a session.")
            return

        drive = self.get_selected_drive()
        default_name = f"Scan_{drive['letter'] if drive else 'USB'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.rsf"
        save_path = filedialog.asksaveasfilename(
            title="Save Scan Session (.rsf)",
            defaultextension=".rsf",
            initialfile=default_name,
            filetypes=[("Recovery Scan File", "*.rsf"), ("All Files", "*.*")]
        )
        if not save_path:
            return

        try:
            # Build RecoverySession
            part_info = PartitionInfo([f"Volume:{drive['letter'] if drive else 'USB'};Label:{drive['label'] if drive else ''};FS:{drive['fs'] if drive else 'exFAT'}"])
            scan_cfg = ScanConfig(scan_mode=0)
            hdr = RSFHeader(description=f"Exported Scan Session: {drive['letter'] if drive else ''} ({len(self.all_files)} items)")

            root = FileNode(node_id=1, name="DiscoveredFiles", is_directory=True)
            for idx, f in enumerate(self.all_files):
                node = FileNode(
                    node_id=idx + 2,
                    name=f['name'],
                    is_directory=f['is_dir'],
                    size=f['size'],
                    start_sector=f.get('start_sector', 0),
                    creation_time=int(f['created'].timestamp()) if f.get('created') else 0,
                    modified_time=int(f['modified'].timestamp()) if f.get('modified') else 0,
                    attributes=0x10 if f['is_dir'] else 0x20,
                    deleted=(f['status'] == 'DELETED')
                )
                root.add_child(node)

            session = RecoverySession(header=hdr, partition_info=part_info, scan_config=scan_cfg, root_nodes=[root])
            session.save_rsf(save_path)
            messagebox.showinfo("Session Saved", f"Session saved successfully to:\n{save_path}\n(CRC-16: 0x{hdr.checksum:04X})")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save session: {e}")

    def load_rsf_session(self):
        """Loads and restores an existing .rsf session file."""
        rsf_path = filedialog.askopenfilename(
            title="Load Scan Session (.rsf)",
            filetypes=[("Recovery Scan File", "*.rsf"), ("All Files", "*.*")]
        )
        if not rsf_path:
            return

        try:
            session = RecoverySession.load_rsf(rsf_path)
            self.all_files = []

            for path, node in session.walk():
                if node.name == "DiscoveredFiles":
                    continue
                # Verify header integrity if file
                status = "DELETED" if node.deleted else "ACTIVE"
                integrity = "RESTORED FROM RSF"
                self.all_files.append({
                    "name": node.name,
                    "path": path,
                    "status": status,
                    "is_dir": node.is_directory,
                    "size": node.size,
                    "first_cluster": node.start_sector // 256 if node.start_sector else 0,
                    "start_sector": node.start_sector,
                    "modified": datetime.fromtimestamp(node.modified_time) if node.modified_time else None,
                    "integrity": integrity
                })

            self.lbl_status.config(text=f"Loaded session '{os.path.basename(rsf_path)}' ({len(self.all_files)} items, CRC: 0x{session.header.checksum:04X})")
            self.apply_filters()
            messagebox.showinfo("Session Restored", f"Successfully restored session with {len(self.all_files)} entries.")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to restore session: {e}")

def main():
    app = DataRecoveryApp()
    app.mainloop()

if __name__ == '__main__':
    main()
