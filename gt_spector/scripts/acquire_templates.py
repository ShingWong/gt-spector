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
# STATIC locations (fixed UI, direct click, no template search needed):
STATIC_LOCATIONS = {
    "shelter": (65, 800),
    "map_search": (38, 623),
}
# Locations that need a template search (dynamic / drift / non-fixed):
CLICK_POINTS = {
    "avatar": (49, 39),
    "vip_menu": (113, 56),
    "region_overview": (1120, 800),
    "region_search": (439, 15),
    "alliance_flags": (485, 21),
    "radar_station": (103, 616),
    "hero_menu": (1038, 796),
    "bag": (861, 782),
    "campaign_menu": (800, 800),
}
# Templates to capture in addition to CLICK_POINTS, keyed by capture center.
# mission_menu_static identifies the mission menu (invariant chrome);
# mission_menu_count reads the completed-mission badge (future reward auto-collect).
# chat_static identifies the chat button (invariant); chat_unread is the
# red-background @ badge indicating unread messages (future: alert on unread).
# alliance_menu_static identifies the alliance menu (invariant); alliance_menu_count
# indicates rewards available inside the alliance menu (future: claim).
# vip_reward shows if a VIP reward is available; shifts ~30px right when VIP
# level > 9.
# VIP note (see game_world.yaml): vip_reward shifts ~30px right when VIP >9.
EXTRA_TEMPLATES = {
    "mission_menu_static": (34, 698),
    "mission_menu_count": (55, 671),
    "chat_static": (139, 810),
    "chat_unread": (160, 792),
    "alliance_menu_static": (951, 800),
    "alliance_menu_count": (980, 772),
    "vip_reward": (137, 49),
    "messages_static": (1113, 751),
    "messages_count": (1126, 727),
    "map_alliance_help": (1114, 693),
}

PATCH_HALF = 24  # fallback 48x48 capture box when tight-boxing fails
MIN_STD = 15.0
TIGHT_SEARCH = 12  # content-aware box search radius


def _mask(frame: np.ndarray) -> np.ndarray:
    """Binary mask of button-like pixels: bright or strongly saturated."""
    rgb = frame[:, :, :3].astype(np.uint8)
    gray = rgb.mean(axis=2)
    sat = rgb.max(axis=2).astype(int) - rgb.min(axis=2).astype(int)
    return ((gray > 90) | (sat > 40)).astype(np.uint8)


def tight_box(frame: np.ndarray, cx: int, cy: int,
              search: int = TIGHT_SEARCH) -> tuple[int, int, int, int] | None:
    """Tight bounding box of the button containing (cx, cy).

    Uses connected components on a button-mask within a small search window so
    adjacent toolbar buttons do not merge. Returns (x0, y0, x1, y1).
    """
    import cv2

    h, w = frame.shape[:2]
    x0, x1 = max(0, cx - search), min(w, cx + search)
    y0, y1 = max(0, cy - search), min(h, cy + search)
    mask = _mask(frame)[y0:y1, x0:x1]
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    rx, ry = cx - x0, cy - y0
    lab = labels[ry, rx]
    if lab <= 0:
        best, bd = None, 1e9
        for i in range(1, n):
            c = cents[i]
            d = (c[0] - rx) ** 2 + (c[1] - ry) ** 2
            if d < bd:
                bd, best = d, i
        lab = best
    if lab is None or lab <= 0:
        return None
    st = stats[lab]
    return (x0 + int(st[0]), y0 + int(st[1]),
            x0 + int(st[0]) + int(st[2]), y0 + int(st[1]) + int(st[3]))


def acquire(frame: np.ndarray, name: str, cx: int, cy: int,
            locator=None) -> T.Template | None:
    h, w = frame.shape[:2]
    box = tight_box(frame, cx, cy)
    if box is None:
        box = (max(0, cx - PATCH_HALF), max(0, cy - PATCH_HALF),
               min(w, cx + PATCH_HALF), min(h, cy + PATCH_HALF))
    x0, y0, x1, y1 = box
    patch = frame[y0:y1, x0:x1]
    if patch.shape[0] < 4 or patch.shape[1] < 4:
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
        print(f"  SAVED {name:16s} ({cx:4d},{cy:4d}) box=({x0},{y0})-({x1},{y1}) {status}")
    else:
        print(f"  SAVED {name:16s} ({cx:4d},{cy:4d}) box=({x0},{y0})-({x1},{y1})")
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
    all_points = {**CLICK_POINTS, **EXTRA_TEMPLATES}
    for name, (cx, cy) in all_points.items():
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
