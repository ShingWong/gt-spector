"""Help loop: deterministic gold-pixel click for the alliance help flow.

State machine (mirrors the original AHK help loop):
  - When the help button pixel is GOLD, a help request can be sent: click it.
  - After clicking, the button turns GRAY (help sent / request consumed).
  - Wait for it to return to GOLD (a new request arrives) before clicking
    again. This prevents re-clicking the same completed help.

No VLM, no template locator - just per-cycle pixel matches.
"""

from __future__ import annotations

import time

# Per-request help button (gold when a help can be sent, gray after sending).
HELP_X = 495
HELP_Y = 682
HELP_COLOR = 0xE1AB45
VARIANCE = 0.18
CLICK_X = 495
CLICK_Y = 682

# After a click, require this many idle seconds with a non-gold pixel before
# considering the help processed (prevents rapid re-clicks).
COOLDOWN_AFTER_CLICK = 2.0


def color_match(c1: int, c2: int, variance: float = VARIANCE) -> bool:
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    md = 255 * variance
    return (
        abs(r1 - r2) <= md
        and abs(g1 - g2) <= md
        and abs(b1 - b2) <= md
    )


def _pixel(session) -> int:
    r, g, b = session.get_pixel(HELP_X, HELP_Y)
    return (r << 16) | (g << 8) | b


class HelpLoop:
    def __init__(self) -> None:
        self.help_clicks = 0
        self._cooldown_until = 0.0

    def run(self, session, bot=None) -> str | None:
        """One poll cycle. Returns 'clicked' / 'cooldown' / 'idle'."""
        try:
            now = time.monotonic()
            if now < self._cooldown_until:
                return "cooldown"
            if color_match(_pixel(session), HELP_COLOR):
                session.click(CLICK_X, CLICK_Y)
                self.help_clicks += 1
                self._cooldown_until = now + COOLDOWN_AFTER_CLICK
                return "clicked"
        except Exception:  # noqa: BLE001, S110
            pass
        return "idle"
