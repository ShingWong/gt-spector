"""Help loop: deterministic pixel checks for the alliance help flow.

Two pixel-color checks (no VLM, no template locator - mirrors the original
AHK help loop in dls-startup.ahk):
  - TRIGGER: the alliance-menu help indicator turns RED when a member has
    requested help. Click it to open the help dialog.
  - CONFIRM: the help-dialog send button turns GOLD/YELLOW when a help can be
    sent. Click it to send help.

Both are per-cycle pixel matches; the loop cycles through bots.
"""

from __future__ import annotations

# Trigger: alliance-menu help indicator (red = request available).
TRIGGER_X = 1097
TRIGGER_Y = 431
RED_R_MIN = 120
RED_G_MAX = 90
RED_B_MAX = 90

# Confirm: help-dialog send button (gold/yellow = clickable).
HELP_X = 491
HELP_Y = 685
HELP_COLOR = 0xE1AB45
VARIANCE = 0.20
CLICK_X = 491
CLICK_Y = 685


def is_red(r: int, g: int, b: int) -> bool:
    return r >= RED_R_MIN and g <= RED_G_MAX and b <= RED_B_MAX


def color_match(c1: int, c2: int, variance: float = VARIANCE) -> bool:
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    md = 255 * variance
    return (
        abs(r1 - r2) <= md
        and abs(g1 - g2) <= md
        and abs(b1 - b2) <= md
    )


def run(session, bot):
    """One iteration: if the gold help button is active, click it.

    Returns True if clicked.
    """
    try:
        r, g, b = session.get_pixel(HELP_X, HELP_Y)
        pixel_color = (r << 16) | (g << 8) | b
        if color_match(pixel_color, HELP_COLOR, VARIANCE):
            session.click(CLICK_X, CLICK_Y)
            return True
    except Exception:  # noqa: BLE001, S110
        pass
    return False
