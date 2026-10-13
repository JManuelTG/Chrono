# ChronoRecovery

**Next-Gen Deep Filesystem Inspector & Data Recovery Suite**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)]()

ChronoRecovery is a lightweight, high-performance data recovery tool and raw filesystem analyzer. It performs deep sector-aligned scans of raw block devices (such as USB flash drives and external hard drives), parses low-level filesystem directory records to uncover deleted files, and verifies physical cluster integrity across timelines.

---

## 🌟 Key Features

- **Direct Sector-Aligned Volume I/O**: Performs raw sector reads directly from storage devices (`\\.\X:`) with automatic 512-byte boundary bounding boxes to bypass Windows parameter constraints.
- **Deep exFAT Deletion Discovery**: Scans primary, stream extension, and filename directory records across directory cluster chains, detecting unlinked files where entry type flags have been cleared.
- **Sweep-Line Cluster Collision & Overwrite Detection**: Resolves the classic data recovery problem of cluster reuse. Compares temporal intervals and timestamps to accurately identify which files were physically overwritten on flash memory and which remain 100% intact.
- **Multi-Format Magic Header Verification**:
  - **Photos & Images**: JPEG, PNG, GIF, BMP, WEBP, TIFF, HEIC, PSD, ICO.
  - **Documents & Office**: PDF, modern Office ZIP formats (`.docx`, `.xlsx`, `.pptx`), legacy OLE2 (`.doc`, `.xls`), RTF, and UTF-8/ASCII text/code.
  - **Videos**: MP4/M4V (FTYP/MOOV/MDAT container atoms), MKV, AVI, WMV.
  - **Audio & Music**: MP3 (ID3 & frame sync), WAV, FLAC, M4A, OGG.
  - **Archives**: ZIP, RAR, 7-Zip, GZIP, Executables (PE/MZ).
- **Structured Binary Session Management (`.rsf`)**: Export complete scan hierarchies with CRC-16 checksums and reload prior sessions instantly without rescanning physical storage devices.
- **Human-Friendly Desktop GUI**: High-DPI Windows Tkinter interface with storage drive selectors, live search, quick category filter buttons, sortable table views, and destination safety guards.

---

## 📁 Project Architecture

```
Data Recovery/
├── assets/
│   └── icons/
│       ├── app_icon.png        # 512x512 High-res icon source
│       └── app_icon.ico        # Multi-resolution Windows ICO (16x16 to 256x256)
├── recovery_session/           # Binary session serialization package (.rsf)
│   ├── __init__.py
│   ├── engine.py               # Session capture, walk, and restoration engine
│   ├── models.py               # PartitionInfo, ScanConfig, and FileNode data models
│   └── rsf_format.py           # CRC-16 (IBM) and chunk container specifications
├── drive_utils.py              # Win32 ctypes storage device enumerator
├── exfat_recovery.py           # Raw sector reader, deep exFAT parser & collision detector
├── recovery_gui.py             # Desktop graphical user interface
├── chrono_cli.py               # Command-line interface for session capture & restore
└── test_recovery_session.py    # Automated test suite
```

---

## 🚀 Quick Start

### Prerequisites

- Windows 10 or 11
- Python 3.10+
- Dependencies:

```powershell
pip install Pillow
```

### Launch the GUI

```powershell
python recovery_gui.py
```

1. Select your target drive from the dropdown (e.g. `G: [USB]`).
2. Click **⚡ Scan Drive**.
3. Use the **Quick Filter** buttons (`🖼️ Photos`, `📄 Docs`, `🎬 Videos`, `📦 Archives`) to browse discovered files.
4. Select files and click **📥 Recover Selected** or click **⭐ Recover All Intact (In View)**.
5. Save your session to a `.rsf` file anytime using **💾 Save Session (.rsf)**.

---

### Command-Line Interface (CLI)

ChronoRecovery also provides a dedicated CLI for automated pipelines:

```powershell
# Capture an active filesystem tree into an RSF session
python chrono_cli.py capture "C:\Path\To\Scan" -o session.rsf

# Inspect an existing RSF session and browse its hierarchy
python chrono_cli.py restore session.rsf --tree

# Low-level binary verification (CRC-16 checksum and chunk headers)
python chrono_cli.py inspect session.rsf

# Reconstruct and extract files from a session
python chrono_cli.py extract session.rsf -o ".\output_folder"
```

---

## 🧪 Running Tests

To run the automated test suite:

```powershell
python -m unittest test_recovery_session.py
```

---

## 📄 License

MIT License. Free for personal and educational use.
