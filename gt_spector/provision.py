#!/usr/bin/env python3
"""CLI tool to create and manage isolated game prefixes for bot instances.

Usage:
  provision.py init <name> --account <email>   Create prefix with game + session
  provision.py destroy <name>                   Remove a prefix
  provision.py list                              List all prefixes
  provision.py update                            Update game files from base
"""
import argparse
import os
import shutil
import subprocess
import time

BASE_DIR = "/home/swong/dls/wineprefix_bots"
GAME_BASE = "/home/swong/dls/game-base/Doomsday_1.59.0"
WINE_BIN = "/opt/wine-proton/bin/wine"
WINEBOOT = "/opt/wine-proton/bin/wineboot"
SESSION_TEMPLATE = "/home/swong/dls/tmp/sr02-05/full.reg"
PROTON_SRC = "/home/swong/dls/wineprefix_proton"
DXVK_SRC = "/tmp/dxvk-source-2.5.3/build-win64/src"

def main():
    parser = argparse.ArgumentParser(description="Bot prefix provisioner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create a new prefix")
    init.add_argument("name", help="Prefix name (e.g. bot01)")
    init.add_argument("--account", required=True, help="Account email")
    init.add_argument("--reg", help="Path to .reg session file (optional)")

    sub.add_parser("destroy", help="Remove a prefix").add_argument("name")
    sub.add_parser("list", help="List all prefixes")
    sub.add_parser("update", help="Update game files from game-base")

    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init(args.name, args.account, args.reg)
    elif args.cmd == "destroy":
        cmd_destroy(args.name)
    elif args.cmd == "list":
        cmd_list()
    elif args.cmd == "update":
        cmd_update()

def _prefix_path(name: str) -> str:
    return os.path.join(BASE_DIR, name)

def _display_num(name: str) -> int:
    try:
        return int(name.replace("bot", ""))
    except ValueError:
        return hash(name) % 1000 + 100

def cmd_init(name: str, account: str, reg_path: str | None):
    dest = _prefix_path(name)
    already = os.path.exists(os.path.join(dest, "drive_c"))
    if already and reg_path:
        # Re-apply session
        subprocess.run([WINE_BIN, "reg", "delete", "HKCU\\Software\\IGG", "/f"],
                       env={"WINEPREFIX": dest}, capture_output=True, check=False)
        subprocess.run([WINE_BIN, "reg", "import", reg_path],
                       env={"WINEPREFIX": dest}, capture_output=True, check=False)
        print(f"Session applied to {name}")
        return
    elif already:
        print(f"Prefix {name} already exists")
        return

    os.makedirs(dest, exist_ok=True)
    print(f"Creating prefix {name}...")

    subprocess.run([WINEBOOT, "-u"], env={"WINEPREFIX": dest},
                   capture_output=True, timeout=120, check=False)
    time.sleep(3)

    game_dir = os.path.join(dest, "drive_c", "Program Files", "DoomsdayLastSurvivors")
    os.makedirs(game_dir, exist_ok=True)
    ver_dir = os.path.join(game_dir, "Doomsday_1.59.0")

    print("Copying game files...")
    shutil.copytree(GAME_BASE, ver_dir, symlinks=True, dirs_exist_ok=True)

    src_x86 = os.path.join(DXVK_SRC, "d3d11", "d3d11.dll"), os.path.join(DXVK_SRC, "dxgi", "dxgi.dll")
    dst_x86 = os.path.join(dest, "drive_c", "windows", "system32")
    for dll in src_x86:
        if not os.path.exists(dll):
            print(f"WARNING: {dll} not found (DXVK not built?)")
            continue
        shutil.copy2(dll, os.path.join(dst_x86, os.path.basename(dll)))

    subprocess.run([WINE_BIN, "reg", "add", "HKCU\\Software\\Wine\\DllOverrides",
                    "/v", "d3d11", "/t", "REG_SZ", "/d", "native", "/f"],
                   env={"WINEPREFIX": dest}, capture_output=True, check=False)
    subprocess.run([WINE_BIN, "reg", "add", "HKCU\\Software\\Wine\\DllOverrides",
                    "/v", "dxgi", "/t", "REG_SZ", "/d", "native", "/f"],
                   env={"WINEPREFIX": dest}, capture_output=True, check=False)

    if reg_path and os.path.exists(reg_path):
        subprocess.run([WINE_BIN, "reg", "import", reg_path],
                       env={"WINEPREFIX": dest}, capture_output=True, check=False)
        print(f"Session applied from {reg_path}")
    else:
        print("No session reg provided — game will start as guest")

    print(f"✓ Prefix {name} ready")
    return {
        "name": name,
        "account": account,
        "prefix": dest,
        "display": _display_num(name),
    }

def cmd_destroy(name: str):
    dest = _prefix_path(name)
    if not os.path.exists(dest):
        print(f"Prefix {name} not found")
        return
    shutil.rmtree(dest)
    print(f"✗ Prefix {name} removed")

def cmd_list():
    if not os.path.exists(BASE_DIR):
        print("No prefixes")
        return
    for entry in sorted(os.listdir(BASE_DIR)):
        path = os.path.join(BASE_DIR, entry)
        if os.path.isdir(path):
            size = subprocess.run(["du", "-sh", path], capture_output=True,
                                  text=True, check=False).stdout.split()[0]
            print(f"{entry:12s} {size}")

def cmd_update():
    for entry in os.listdir(BASE_DIR):
        ver = os.path.join(BASE_DIR, entry, "drive_c", "Program Files",
                           "DoomsdayLastSurvivors", "Doomsday_1.59.0")
        if os.path.exists(ver):
            shutil.rmtree(ver)
            shutil.copytree(GAME_BASE, ver, symlinks=True, dirs_exist_ok=True)
            print(f"Updated {entry}")
    print("✓ All prefixes updated")

if __name__ == "__main__":
    main()
