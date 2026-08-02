#!/usr/bin/env python3
"""CLI tool to create and manage isolated game prefixes for bot instances.

Each prefix is a clean game install (game + DXVK + browser DLL + fonts +
resolution). Accounts log in directly through the game's embedded browser
— no registry/appdata/VITAL copying is needed; the game writes its own
session after login.

Usage:
  provision.py init <name> [--account <email>]   Create a fresh prefix
  provision.py destroy <name>                     Remove a prefix
  provision.py list                               List all prefixes
  provision.py update                             Update game files from base
"""
import argparse
import os
import shutil
import subprocess
import tempfile
import time

BASE_DIR = "/home/swong/dls/wineprefix_bots"
GAME_BASE = "/home/swong/dls/game-base/Doomsday_1.59.0"
WINE_BIN = "/opt/wine-proton/bin/wine"
WINEBOOT = "/opt/wine-proton/bin/wineboot"
PROTON_SRC = "/home/swong/dls/wineprefix_proton"
DXVK_SRC = "/home/swong/dls/dxvk/dxvk-source-2.5.3/build-win64/src"

def main():
    parser = argparse.ArgumentParser(description="Bot prefix provisioner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create a new prefix")
    init.add_argument("name", help="Prefix name (e.g. bot01)")
    init.add_argument("--account", help="Account email (informational only)")

    sub.add_parser("destroy", help="Remove a prefix").add_argument("name")
    sub.add_parser("list", help="List all prefixes")
    sub.add_parser("update", help="Update game files from game-base")

    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init(args.name, args.account)
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

_GAME_SETTINGS_REG = r"""Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\Software\IGG\Doomsday: Last Survivors]
"Screenmanager Resolution Width Default_h680557497"=dword:00000500
"Screenmanager Resolution Height Default_h1380706816"=dword:000002d0
"Screenmanager Resolution Use Native Default_h1405981789"=dword:00000001
"Screenmanager Fullscreen mode Default_h401710285"=dword:00000003
"Screenmanager Resolution Width_h182942802"=dword:00000480
"Screenmanager Resolution Window Width_h2524650974"=dword:00000480
"Screenmanager Resolution Height_h2627697771"=dword:00000360
"Screenmanager Resolution Window Height_h1684712807"=dword:00000360
"Screenmanager Resolution Use Native_h1405027254"=dword:00000000
"Screenmanager Fullscreen mode_h3630240806"=dword:00000003
"UnityGraphicsQuality_h1669003810"=dword:00000000
"PCResolution_h240614520"=hex:31,31,35,32,7c,38,36,34,7c,30,00
"""


def _force_resolution(dest: str) -> None:
    """Force the game to 1152x864, low graphics, windowed — the settings
    from the working Windows 10 VM.

    Unity saves its resolution in the registry and overrides the
    -screen-height launch arg. If a copied session registry has a different
    height (e.g. 720), the frame is shorter than 864 and every coordinate
    below y=720 is off-frame — clicks don't register. This imports the
    exact values from the Windows VM (resolution 1152x864, quality low).
    """
    reg_path = os.path.join(tempfile.gettempdir(), f"gt_game_settings_{os.getpid()}.reg")
    with open(reg_path, "w") as f:
        f.write(_GAME_SETTINGS_REG)
    try:
        subprocess.run([WINE_BIN, "reg", "import", reg_path],
                       env={"WINEPREFIX": dest}, capture_output=True, check=False)
    finally:
        try:
            os.remove(reg_path)
        except OSError:
            pass
    print("Applied game settings (1152x864, low quality)")


def cmd_init(name: str, account: str | None = None):
    dest = _prefix_path(name)
    if os.path.exists(os.path.join(dest, "drive_c")):
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

    _force_resolution(dest)
    _install_fonts(dest)

    print(f"✓ Prefix {name} ready (login via the in-game browser)")
    return {
        "name": name,
        "account": account,
        "prefix": dest,
        "display": _display_num(name),
    }


def _install_fonts(dest: str) -> None:
    """Install fonts so the embedded browser renders text.

    The browser's login form needs real Windows fonts (Arial/Segoe UI/Tahoma/
    Verdana); metric-compatible substitutes (DejaVu/Liberation) resolve via
    fontconfig but Chromium's placeholder/label text still fails without the
    real files. Copy host fonts plus the Windows core fonts from the VM and
    register them in the prefix registry.
    """
    fonts_dir = os.path.join(dest, "drive_c", "windows", "Fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"):
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(fonts_dir, os.path.basename(f)))

    # Windows core fonts from the login VM (Arial, Segoe UI, Tahoma, Verdana,
    # Calibri). Fall back to host copies if the VM is unreachable.
    vm_fonts = {
        "arial.ttf": "Arial", "arialbd.ttf": "Arial Bold",
        "ariali.ttf": "Arial Italic", "arialbi.ttf": "Arial Bold Italic",
        "segoeui.ttf": "Segoe UI", "segoeuib.ttf": "Segoe UI Bold",
        "segoeuii.ttf": "Segoe UI Italic",
        "tahoma.ttf": "Tahoma", "tahomabd.ttf": "Tahoma Bold",
        "verdana.ttf": "Verdana", "verdanab.ttf": "Verdana Bold",
        "calibri.ttf": "Calibri", "calibrib.ttf": "Calibri Bold",
    }
    for fname, fname_reg in vm_fonts.items():
        dst = os.path.join(fonts_dir, fname)
        if os.path.exists(dst):
            continue
        got = False
        for src in (f"/usr/share/fonts/truetype/{fname}",
                    f"/usr/share/fonts/truetype/msttcorefonts/{fname}"):
            if os.path.exists(src):
                shutil.copy2(src, dst)
                got = True
                break
        if not got:
            try:
                import subprocess
                subprocess.run(
                    ["scp", "-q", f"techno@10.8.2.11:C:/Windows/Fonts/{fname}", dst],
                    capture_output=True, timeout=30, check=False)
                got = os.path.exists(dst) and os.path.getsize(dst) > 1000
            except (OSError, subprocess.SubprocessError):
                got = False
        if got:
            subprocess.run(
                [WINE_BIN, "reg", "add",
                 "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts",
                 "/v", fname_reg, "/t", "REG_SZ", "/d", fname, "/f"],
                env={"WINEPREFIX": dest}, capture_output=True, check=False)
    print(f"Installed fonts into {fonts_dir}")

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
