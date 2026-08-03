"""Automate template acquisition from the user's known click points.

Captures a clean 48x48 patch around each named click point from a live
world-map frame, saves it as a version-tagged template, verifies it is
locatable, and prints a summary. Run on a bot that is on the world map.

Usage:
  python -m gt_spector.scripts.acquire_templates <display>
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from gt_spector import templates as T

# User-provided click points (world map / regional). Names are the canonical
# snake_case labels used across the game-world KB.
CLICK_POINTS = {
    "player_avatar": (48, 44),
    "shelter": (65, 800),
    "map_search": (38, 623),
    "chat": (150, 800),
    "vip_menu": (113, 56),
    "region_overview": (1120, 800),
    "messages": (1120, 745),
    "region_search": (439, 15),
    "alliance_flags": (485, 21),
    "mission_menu": (40, 680),
    "radar_station": (103, 616),
    "alliance_menu": (960, 800),
    "hero_menu": (1040, 800),
    "bag_menu": (975, 800),
    "campaign_menu": (800, 800),
}

PATCH_HALF = 24  # 48x48 capture box
MIN_STD = 25.0


def acquire(frame: np.ndarray, name: str, cx: int, cy: int,
            locator=None) -> T.Template | None:
    h, w = frame.shape[:2]
    x0, x1 = max(0, cx - PATCH_HALF), min(w, cx + PATCH_HALF)
    y0, y1 = max(0, cy - PATCH_HALF), min(h, cy + PATCH_HALF)
    patch = frame[y0:y1, x0:x1]
    if patch.shape[0] < 10 or patch.shape[1] < 10:
        print(f"  SKIP {name}: patch too small {patch.shape}")
        return None
    if patch.std() < MIN_STD:
        print(f"  SKIP {name}: low texture std={patch.std():.1f}")
        return None
    t = T.Template(name=name, shape="rect", x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                   game_version=T.GAME_VERSION, score_threshold=0.75)
    T.save_template(t, patch)
    if locator is not None:
        r = locator.find(frame, name)
        status = f"locatable score={r.score:.3f} @({r.cx},{r.cy})" if r.found else "NOT locatable"
        print(f"  SAVED {name:16s} ({cx:4d},{cy:4d}) patch={patch.shape} {status}")
    else:
        print(f"  SAVED {name:16s} ({cx:4d},{cy:4d}) patch={patch.shape}")
    return t


def main() -> None:
    parser = argparse.ArgumentParser(description="acquire UI templates from click points")
    parser.add_argument("display", help="X display, e.g. :10")
    parser.add_argument("--verify", action="store_true", help="locate each saved template back")
    args = parser.parse_args()

    from gt_spector.session import Session

    session = Session(args.display, source=f"shm://{args.display.lstrip(':')}")
    session.refresh()
    frame = session.frame
    print(f"frame: {frame.shape}")

    locator = None
    if args.verify:
        from gt_spector.locator import Locator

        locator = Locator()

    store_dir = T.template_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    print(f"store: {store_dir}")

    ok, skipped = 0, 0
    for name, (cx, cy) in CLICK_POINTS.items():
        if acquire(frame, name, cx, cy, locator):
            ok += 1
        else:
            skipped += 1
    print(f"\n{ok} templates saved, {skipped} skipped")
    if args.verify:
        # summary of all saved templates and their verify scores
        from gt_spector.locator import Locator

        v = Locator()
        print("\n=== verification summary ===")
        for t in T.load_templates():
            r = v.find(frame, t.name)
            print(f"  {t.name:16s} found={r.found} score={r.score:.3f} center=({r.cx},{r.cy})")


if __name__ == "__main__":
    sys.exit(main())
