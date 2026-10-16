#!/usr/bin/env python3
"""
ChronoRecovery — Standalone Executable Build Script.
Compiles ChronoRecovery GUI and chrono CLI into standalone Windows executables using PyInstaller.
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icons", "app_icon.ico")


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"[*] PyInstaller {PyInstaller.__version__} is available.")
        return True
    except ImportError:
        print("[!] PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        return True


def build_gui(onefile=True):
    print("\n" + "=" * 60)
    print("  Building ChronoRecovery GUI Executable...")
    print("=" * 60)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ChronoRecovery",
        "--noconsole",
        f"--icon={ICON_PATH}",
        f"--add-data=assets;assets",
        "--clean",
        "recovery_gui.py"
    ]
    if onefile:
        cmd.insert(4, "--onefile")
    else:
        cmd.insert(4, "--onedir")

    print("[*] Running:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode == 0:
        print("[+] ChronoRecovery GUI build succeeded!")
        exe_path = os.path.join(DIST_DIR, "ChronoRecovery.exe" if onefile else os.path.join("ChronoRecovery", "ChronoRecovery.exe"))
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"[+] Output: {exe_path} ({size_mb:.2f} MB)")
        return True
    else:
        print(f"[-] GUI build failed with code {res.returncode}")
        return False


def build_cli():
    print("\n" + "=" * 60)
    print("  Building chrono CLI Executable...")
    print("=" * 60)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=chrono",
        "--console",
        "--onefile",
        f"--icon={ICON_PATH}",
        "--clean",
        "chrono_cli.py"
    ]
    print("[*] Running:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode == 0:
        print("[+] chrono CLI build succeeded!")
        exe_path = os.path.join(DIST_DIR, "chrono.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"[+] Output: {exe_path} ({size_mb:.2f} MB)")
        return True
    else:
        print(f"[-] CLI build failed with code {res.returncode}")
        return False


def main():
    print("============================================================")
    print("       ChronoRecovery Executable Builder")
    print("============================================================")
    check_pyinstaller()
    gui_ok = build_gui(onefile=True)
    cli_ok = build_cli()

    print("\n" + "=" * 60)
    if gui_ok and cli_ok:
        print("  [SUCCESS] All ChronoRecovery executables compiled successfully!")
        print(f"  Binaries located in: {DIST_DIR}")
    else:
        print("  [WARNING] One or more builds failed. Check logs above.")
    print("=" * 60)


if __name__ == '__main__':
    main()
