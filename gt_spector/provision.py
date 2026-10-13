#!/usr/bin/env python3
"""CLI tool to create and manage isolated game prefixes for bot instances.

Each prefix is a clean game install (game + DXVK + browser DLL + fonts +
resolution) plus the master IGG appdata (asset cache + tutorial-complete
registry state). The game boots to an expired-session/login screen; log the
bot into its real account via the embedded browser (change_account).

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
MASTER_APPDATA = "/home/swong/dls/game-base/IGG-appdata-master"
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


def _copy_game_tree(src: str, dst: str) -> None:
    """Clone the game install into a prefix, sharing data via btrfs reflink.

    The game files are ~4.5G; a normal copy would use 4.5G per bot (135G for
    30 bots). Reflink (CoW) shares the data blocks with GAME_BASE until a file
    is written, so 30 bots use ~0 added disk while each can still write safely
    (CoW handles diverging files). Falls back to a normal copy if reflink is
    unsupported.
    """
    r = subprocess.run(["cp", "-a", "--reflink=always", src, dst],
                       capture_output=True, check=False)
    if r.returncode != 0:
        # Fallback: plain copy (cross-device / non-CoW filesystems)
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)


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
    _copy_game_tree(GAME_BASE, ver_dir)

    _copy_master_appdata(dest)

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
    os.makedirs(os.path.join(dest, "dxvk-cache"), exist_ok=True)

    print(f"✓ Prefix {name} ready (boots to expired-session; log in via the in-game browser)")
    return {
        "name": name,
        "account": account,
        "prefix": dest,
        "display": _display_num(name),
    }


def _copy_master_appdata(dest: str) -> None:
    """Copy the master IGG appdata (asset bundles + tutorial-complete state).

    New prefixes get bot06's appdata: the full `ab/` asset cache (so the game
    does not re-download ~3GB), plus the tutorial-complete/guest-unlinked
    registry state. The game then boots to the expired-session/login screen,
    ready for a browser login to the bot's real account.
    """
    src = os.path.join(MASTER_APPDATA, "Doomsday_ Last Survivors")
    if not os.path.exists(src):
        print(f"WARNING: master appdata not found at {src}, starting fresh")
        return
    appdata = os.path.join(
        dest, "drive_c", "users", "steamuser",
        "AppData", "LocalLow", "IGG", "Doomsday_ Last Survivors",
    )
    os.makedirs(appdata, exist_ok=True)
    r = subprocess.run(["cp", "-a", "--reflink=always", src + "/.", appdata + "/"],
                       capture_output=True, check=False)
    if r.returncode != 0:
        shutil.copytree(src, appdata, dirs_exist_ok=True)
    reg_src = os.path.join(MASTER_APPDATA, "user.reg")
    if os.path.exists(reg_src):
        shutil.copy2(reg_src, os.path.join(dest, "user.reg"))
        print("Copied master appdata (asset cache + tutorial-complete registry)")
    _clear_master_session(os.path.join(dest, "user.reg"))
    _clear_master_cookies(appdata)


# Registry keys that hold the master account's saved login session. The master
# appdata ships a valid session (gpcid 2156987937) so the game auto-logs-in the
# WRONG account on a fresh prefix. Removing them makes the game boot to the
# browser login form for the bot's own account. Kept: tutorial-complete state
# (LoginState per-account, agreements) which should survive.
_SESSION_REG_PATTERNS = (
    "_PRE_LOGIN_TYPE__",
    "gpc.sdk.account.gpcid.on.first.logined_",
    "gpc.sdk.account.gpcid_",
    "gpc.sdk.account.last.refresh.session.timestamp_",
    "gpc.sdk.account.login.type.on.first.logined_",
    "gpc.sdk.account.login.type_",
    "gpc.sdk.account.ssotoken.time.to.create_",
    "gpc.sdk.account.ssotoken.time.to.verify_",
    "gpc.sdk.account.third.platform.id_",
    "gpc.sdk.account.time.to.verify_",
    "gpc.sdk.device.bind.userid.state_",
    "gpc.sdk.last_login.userid_",
    "gpc.sdk.payment.is.not.first.send.device.info_",
    "gpc.sdk.udid_",
    "PreLoginUserId_",
)


def _clear_master_session(reg_path: str) -> None:
    """Strip the master account's saved-session keys from a copied user.reg.

    Without this, a fresh prefix auto-logs-in the master account (whose valid
    session ships in the master appdata) and the provision flow reports success
    for the wrong account. Removing the session keys forces the game to show
    the browser login form so the correct account is used.
    """
    if not os.path.exists(reg_path):
        return
    with open(reg_path) as f:
        lines = f.read().splitlines()
    out: list[str] = []
    removed = 0
    for line in lines:
        if any(p in line for p in _SESSION_REG_PATTERNS):
            removed += 1
            continue
        out.append(line)
    if removed:
        with open(reg_path, "w") as f:
            f.write("\n".join(out) + "\n")
        print(f"Cleared {removed} master-session registry keys")


def _clear_master_cookies(appdata: str) -> None:
    """Remove the master account's browser SSO session from the appdata.

    The embedded browser persists its IGG login in several places that ship
    with the master appdata: the CEF Cookies file (`accounts.igg.com_account_sso_token`),
    the Local Storage leveldb (holds the logged-in account email), Session
    Storage, and the device identity caches (`udid_cache`/`guestid_cache`) that
    the server uses to restore the master login on a known device. Copying
    these lets the game auto-login the master account no matter what user.reg
    says. Deleting them forces the browser login form on the first boot of a
    new prefix.
    """
    import shutil as _shutil

    targets = [
        os.path.join(appdata, name)
        for name in ("Cookies", "Cookies-journal", "Local Storage",
                     "Session Storage", "udid_cache", "guestid_cache")
    ]
    for path in targets:
        if not os.path.exists(path):
            continue
        try:
            if os.path.isdir(path):
                _shutil.rmtree(path)
            else:
                os.remove(path)
            print(f"Cleared {os.path.basename(path)} (master SSO session)")
        except OSError as e:
            print(f"WARNING: could not clear {path}: {e}")


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
