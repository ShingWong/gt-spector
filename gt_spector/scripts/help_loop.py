"""Help loop: deterministic gold-pixel click for the alliance help flow.

State machine (mirrors the original AHK help loop):
  - When the help button pixel is GOLD, a help request can be sent: click it.
  - After clicking, the button turns GRAY (help sent / request consumed).
  - Wait for it to return to GOLD (a new request arrives) before clicking
    again. This prevents re-clicking the same completed help.
  - When the pixel is NEITHER gold nor gray (e.g. a popup covers the help
    button), report "stuck" so the HelpBot can dismiss the popup and recover.

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

# Dim/gray state: help sent, waiting for a new request. Channels near-equal.
DIM_MAX_CHANNEL_SPREAD = 40

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
        """One poll cycle. Returns 'clicked' / 'cooldown' / 'idle' / 'stuck'."""
        try:
            now = time.monotonic()
            if now < self._cooldown_until:
                return "cooldown"
            r, g, b = session.get_pixel(HELP_X, HELP_Y)
            if color_match((r << 16) | (g << 8) | b, HELP_COLOR):
                session.click(CLICK_X, CLICK_Y)
                self.help_clicks += 1
                self._cooldown_until = now + COOLDOWN_AFTER_CLICK
                return "clicked"
            # Dim/gray: help sent, waiting. Anything else is a covering popup.
            spread = max(r, g, b) - min(r, g, b)
            if spread <= DIM_MAX_CHANNEL_SPREAD:
                return "idle"
            return "stuck"
        except Exception:  # noqa: BLE001, S110
            pass
        return "idle"
