"""Reliable SendInput typing via the one-shot sendtext.exe Wine helper.

The game's browser login form drops '@'/uppercase under X11 typing, so text
must go through the Windows SendInput (KEYEVENTF_UNICODE) helper. The
one-shot binary (not the sendtextd daemon) does SetForegroundWindow ->
click(x,y) -> type reliably.
"""

from __future__ import annotations

import subprocess

WINE = "/opt/wine-proton/bin/wine"
SENDTEXT = "/home/swong/dls/src/gt-spector/gt_spector/tools/sendtext.exe"


def _run(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    env = {"WINEPREFIX": prefix, "DISPLAY": display}
    r = subprocess.run(
        [WINE, SENDTEXT, text, str(x), str(y)],
        env=env, capture_output=True, timeout=30, check=False,
    )
    return r.returncode == 0


def type_at(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    """Click (x,y) window-relative and type `text` via sendtext.exe."""
    return _run(prefix, display, text, x, y)


def click_at(prefix: str, display: str, x: int, y: int) -> bool:
    """Click (x,y) window-relative via sendtext.exe (empty text)."""
    return _run(prefix, display, "", x, y)
