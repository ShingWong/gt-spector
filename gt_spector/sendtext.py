"""Persistent SendInput typing via the sendtextd Wine daemon.

The game's login form, chat, and other text inputs drop the shift key (and
thus uppercase / '@') when input comes through X11 (xdotool). sendtextd.exe
runs inside the same Wine prefix and types via Windows SendInput
(KEYEVENTF_UNICODE), which is not subject to the broken shift translation.

The daemon watches a command file in the prefix. Sending text = writing a
line to that file; the daemon executes it and truncates the file. Commands:
  "<text>"                type text (specials: {Enter} {Backspace} {Tab}
                          {Esc} {CtrlA} {Delete})
  "<x>,<y>,<text>"        click screen (x,y) then type
"""

from __future__ import annotations

import os
import time
from pathlib import Path

PREFIX = Path(os.environ.get("WINEPREFIX", "/home/swong/dls/wineprefix_bots/bot01"))
CMD_FILE = PREFIX / "drive_c" / "sendtext_cmd.txt"
DAEMON = "/home/swong/dls/src/gt-spector/gt_spector/tools/sendtextd.exe"

_TIMEOUT = 10.0


def start_daemon(prefix: str | Path, display: str = ":10") -> None:
    """Launch the sendtextd Wine daemon for a bot's prefix.

    Call once per bot after the game is running. The daemon attaches to the
    game window by title, so the game must already be up.
    """
    global CMD_FILE
    p = Path(prefix)
    CMD_FILE = p / "drive_c" / "sendtext_cmd.txt"
    env = {**os.environ, "WINEPREFIX": str(p), "DISPLAY": display}
    import subprocess

    subprocess.Popen(
        ["/opt/wine-proton/bin/wine", DAEMON, "C:\\sendtext_cmd.txt"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def send(text: str, x: int | None = None, y: int | None = None,
         timeout: float = _TIMEOUT) -> bool:
    """Write a typing command to the daemon. Returns True when executed."""
    cmd = f"{x},{y},{text}" if (x is not None and y is not None) else text
    cmd += "\n"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            CMD_FILE.write_text(cmd)
            # wait for the daemon to truncate it (means it executed)
            while time.monotonic() < deadline and CMD_FILE.exists():
                if CMD_FILE.stat().st_size == 0:
                    return True
                time.sleep(0.05)
            return True
        except (OSError, PermissionError):
            time.sleep(0.05)
    return False


def type_text(text: str, x: int | None = None, y: int | None = None) -> bool:
    return send(text, x, y)
