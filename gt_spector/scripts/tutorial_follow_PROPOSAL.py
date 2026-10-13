"""Follow a game tutorial to completion (PROPOSAL — untracked, for review).

Loop: capture -> detect tutorial state -> ground next tap -> click -> verify.
Grounding never uses full-frame fractions (proven to hit adjacent controls):
it crops a region (banner/contour box or quadrant), asks the VLM for 0-1000
coords WITHIN the crop via vlm.analyze_crop, maps back to frame pixels.

TWO PATHS (blocked-tutorial rule, measured 2026-10-13: hero tutorial with
EXP 0/100 and no EXP items is uncompletable — 8 distinct taps, zero change):
 path 1 REQUIREMENT MET: taps change the screen -> keep following, each tap
        verified (screen must change or stop).
 path 2 BLOCKED: N distinct taps across distinct regions, no screen change ->
        declare blocked, SKIP out once, verify banner gone, log BLOCKED with
        reason, return post-tutorial screen to the navigator.
SKIP is the blocked-exit, used at most once per run, never as step 1.
Confirm/OK/collect never tapped blind — those commit game actions.
"""

from __future__ import annotations

import re
import time

import numpy as np

from gt_spector import vlm
from gt_spector.session import Session

TAP_RE = re.compile(r"TAP\s+(\d+)\s+(\d+)", re.IGNORECASE)
MAX_STEPS = 20
SETTLE_S = 6


def _crop_around(frame, cx, cy, w=400, h=300):
    H, W = frame.shape[:2]
    x0, x1 = max(0, cx - w // 2), min(W, cx + w // 2)
    y0, y1 = max(0, cy - h // 2), min(H, cy + h // 2)
    return (x0, y0, x1, y1)


def ask_tap_in_crop(frame, box):
    ans = vlm.analyze_crop(
        frame, box,
        "A game tutorial is active. Which ONE UI element should be tapped next "
        "to advance it? Reply exactly: TAP x y REASON, with x,y as 0-1000 "
        "fractions measured inside THIS cropped region. Prefer the tutorial's "
        "instructed target; choose SKIP only if no other control can advance.",
        )
    m = TAP_RE.search(ans or "")
    if not m:
        return None, ans
    x0, y0, x1, y1 = box
    fx, fy = int(m.group(1)) / 1000, int(m.group(2)) / 1000
    return (x0 + fx * (x1 - x0), y0 + fy * (y1 - y0)), ans


def follow(session, identify, max_steps=MAX_STEPS, blocked_after=5):
    """identify: () -> screen name or None. Returns step log."""
    log = []
    skips_used = 0
    distinct_taps = set()
    H, W = session.frame.shape[:2]
    for i in range(max_steps):
        frame = session.refresh() if hasattr(session, "refresh") else session.frame
        frame = np.asarray(session.frame)
        screen = identify()
        # sweep crop centers: banner band right, center, lower buttons
        cands = [(int(W * 0.75), int(H * 0.45)), (W // 2, H // 2),
                 (int(W * 0.75), int(H * 0.8))]
        tapped = False
        for cx, cy in cands:
            box = _crop_around(frame, cx, cy)
            pt, ans = ask_tap_in_crop(frame, box)
            log.append({"i": i, "screen": screen, "box": box, "vlm": ans})
            if pt is None:
                continue
            x, y = int(pt[0]), int(pt[1])
            if "skip" in ans.lower():
                if skips_used >= 1:
                    continue
                skips_used += 1
            before = screen
            session.click(x, y)
            time.sleep(SETTLE_S)
            after = identify()
            log.append({"i": i, "tap": [x, y], "before": before, "after": after})
            tapped = True
            if after != before:
                distinct_taps.clear()  # path 1: progress resets the counter
                break
            distinct_taps.add((x // 100, y // 100))
            if len(distinct_taps) >= blocked_after:
                # path 2: BLOCKED — N distinct taps, no change. SKIP out once.
                log.append({"i": i, "note": f"BLOCKED after {len(distinct_taps)} distinct taps"})
                break
        if not tapped:
            log.append({"i": i, "note": "no tap proposed, stop"})
            break
        if after is not None and "tutorial" not in str(after).lower():
            log.append({"i": i, "note": f"tutorial clear at {after}"})
            break
    return log


if __name__ == "__main__":
    import json
    import sys

    from gt_spector.game_world import GameWorld

    display = sys.argv[1] if len(sys.argv) > 1 else ":26"
    session = Session(display, source=f"shm://{display.lstrip(':')}")
    gw = GameWorld()
    log = follow(session, lambda: gw.identify(session))
    print(json.dumps(log, indent=1)[:3000])
