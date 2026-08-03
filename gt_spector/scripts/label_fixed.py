"""Label fixed-location templates for a given screen on the overlay.

Usage:
  python -m gt_spector.scripts.label_fixed <display> <screen>
"""
from __future__ import annotations

import sys

from gt_spector import overlay
from gt_spector import templates as T
from gt_spector.game_world import GameWorld


def main_args(display: int, screen: str | None) -> None:
    gw = GameWorld()
    if screen is None:
        screen = next(iter(gw.screens))  # pragma: no cover
    print(f"screen: {screen}")
    # Which location entries mention this screen
    screen_locs = {n: v for n, v in gw.locations.items()
                   if screen in v.get("screens", [])}
    # Filter to templates that are marked fixed
    fixed_templates = {t.name: t for t in T.load_templates() if t.fixed}
    labeled = 0
    for name in screen_locs:
        t = fixed_templates.get(name)
        if t is None:
            continue
        overlay.add_marker(display, t.x, t.y, t.name, r=255, g=0, b=0,
                           shape="box", w=t.w, h=t.h)
        labeled += 1
        print(f"  {t.name} @ ({t.x},{t.y}) {t.w}x{t.h}")
    print(f"labeled {labeled} fixed templates for {screen}")


def main() -> None:
    display = int(sys.argv[1])
    screen = sys.argv[2] if len(sys.argv) > 2 else None
    main_args(display, screen)


if __name__ == "__main__":
    main()
