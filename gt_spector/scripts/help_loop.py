"""Help loop: pixel check + click, cycles through running bots.

Checks pixel at (525, 680) against target color (0xDEA342).
If match, clicks at (527, 682) via xdotool --window.
"""
import time

HELP2_X = 525
HELP2_Y = 680
HELP2_COLOR = 0xDEA342
VARIANCE = 0.20
CLICK_X = 527
CLICK_Y = 682


def color_match(c1: int, c2: int, variance: float = 0.20) -> bool:
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    md = 255 * variance
    return abs(r1 - r2) <= md and abs(g1 - g2) <= md and abs(b1 - b2) <= md


def run(session, bot):
    """One iteration: check pixel, click if match. Returns True if clicked."""
    try:
        r, g, b = session.get_pixel(HELP2_X, HELP2_Y)
        pixel_color = (r << 16) | (g << 8) | b
        if color_match(pixel_color, HELP2_COLOR, VARIANCE):
            session.click(CLICK_X, CLICK_Y)
            return True
    except Exception:
        pass
    return False
