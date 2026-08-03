"""Help loop: deterministic pixel check + click for the alliance help flow.

Mirrors the original AHK help loop (dls-startup.ahk runHelpLoop):
- Continuously checks a help-request pixel.
- When its color matches the target (gold/yellow), click it to send help.
- The original used help2 (525,680) color 0xDEA342; our marked confirm point
  is (491,685) which reads ~0xE1AB45 (same gold family).

No VLM, no template locator - just a fast pixel-color match per cycle,
cycling through bots.
"""

from __future__ import annotations

# Per-request help button (gold/yellow when a help can be sent).
HELP_X = 491
HELP_Y = 685
HELP_COLOR = 0xE1AB45
VARIANCE = 0.20
CLICK_X = 491
CLICK_Y = 685


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
    """One iteration: if the help pixel is gold, click it. Returns True if clicked."""
    try:
        r, g, b = session.get_pixel(HELP_X, HELP_Y)
        pixel_color = (r << 16) | (g << 8) | b
        if color_match(pixel_color, HELP_COLOR, VARIANCE):
            session.click(CLICK_X, CLICK_Y)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False
