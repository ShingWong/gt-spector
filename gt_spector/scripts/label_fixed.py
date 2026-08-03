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
    # All templates that have a location on this screen; color by fixed status.
    templates = {t.name: t for t in T.load_templates()}
    labeled = 0
    for name in screen_locs:
        t = templates.get(name)
        if t is None:
            continue
        color = (255, 0, 0) if t.fixed else (0, 200, 255)
        overlay.add_marker(display, t.x, t.y, t.name, r=color[0], g=color[1],
                           b=color[2], shape="box", w=t.w, h=t.h)
        labeled += 1
        tag = "fixed" if t.fixed else "dynamic"
        print(f"  {t.name} @ ({t.x},{t.y}) {t.w}x{t.h} [{tag}]")
    print(f"labeled {labeled} templates for {screen}")


def main() -> None:
    display = int(sys.argv[1])
    screen = sys.argv[2] if len(sys.argv) > 2 else None
    main_args(display, screen)


if __name__ == "__main__":
    main()
