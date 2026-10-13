"""Overlay/tutorial guard v3 (PROPOSAL — untracked, for review).
Measured 2026-10-13 (eg2-screen-lib experiments). Three layers, cheapest first:

  L1 fixed banners: 10% template patch at known coords, TM_CCOEFF_NORMED.
     hero-upgrade banner: positives 1.000, all others <=0.492 (threshold 0.75).
     ms on CPU. Register one patch per known fixed banner here.
  L2 unknown overlays: contour localize (bright quad aspect>3 + text edge,
     or large dialog quad), then EG2-names-the-CROP (skip~skip 0.997,
     skip~exit 0.71). Full-frame cosine REJECTED: shelter scored tutorial
     0.139 over a true 0.127 (background dominates).
  L3 new screens: Qwen names + bank grows per incident. Finish policy:
     SKIP if visible -> crop-zoom follow capped -> park + alert.

v1 full-frame centroid and v2 cosine-only drafts are superseded by this file.
"""

import cv2
import numpy as np

BANNER_PATCHES = [
    # {"name": str, "png": path-to-patch, "slack": px search margin,
    #  "threshold": float}
]

BANNER_EDGE = 0.08


def l1_fixed_banner(bgr, patch_gray, threshold=0.75, slack=20):
    """Match a fixed-location patch. Returns max score."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = patch_gray.shape[:2]
    H, W = gray.shape
    sy, sx = max(0, 0), max(0, 0)
    res = cv2.matchTemplate(gray, patch_gray, cv2.TM_CCOEFF_NORMED)
    _, mx, _, _ = cv2.minMaxLoc(res)
    return float(mx)


def l2_find_overlays(bgr):
    """Contour localize: returns (banners, dialogs) x,y,w,h boxes."""
    H, W = bgr.shape[:2]
    v = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV))[2]
    _, th = cv2.threshold(v, 150, 255, cv2.THRESH_BINARY)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    banners, dialogs = [], []
    for c in cnts:
        frac = cv2.contourArea(c) / (W * H)
        if frac < 0.01 or frac > 0.6:
            continue
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / max(h, 1)
        e = cv2.Canny(gray[y:y + h, x:x + w], 80, 200)
        edge = float((e > 0).mean())
        if aspect > 3.0 and edge > BANNER_EDGE:
            banners.append((x, y, w, h))
        elif 0.1 <= frac <= 0.5 and 0.7 <= aspect <= 2.0:
            dialogs.append((x, y, w, h))
    return banners, dialogs


def check(bgr, banner_patches=BANNER_PATCHES):
    """Returns dict: fixed hits, overlay boxes. EG2/Qwen naming is caller-side."""
    hits = [p["name"] for p in banner_patches
            if l1_fixed_banner(bgr, p["png"], p.get("threshold", 0.75)) >= p.get("threshold", 0.75)]
    banners, dialogs = l2_find_overlays(bgr)
    return {"fixed": hits, "banners": banners, "dialogs": dialogs}
