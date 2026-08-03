from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np

from gt_spector import templates as _templates


@dataclass
class LocateResult:
    cx: int
    cy: int
    score: float
    found: bool


class Locator:
    def __init__(self) -> None:
        self._vlm_fallback: Callable[[np.ndarray, str, float], LocateResult | None] | None = None

    def set_vlm_fallback(self, fn: Callable[[np.ndarray, str, float], LocateResult | None]) -> None:
        self._vlm_fallback = fn

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 2:
            return frame
        rgb = frame[:, :, :3]
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    def _match_one(self, frame: np.ndarray, name: str) -> LocateResult:
        t = next((x for x in _templates.load_templates() if x.name == name), None)
        if t is None:
            return LocateResult(0, 0, 0.0, False)
        patch = _templates.get_patch(name)
        if patch is None:
            return LocateResult(0, 0, 0.0, False)
        gray = self._gray(frame)
        pgray = self._gray(patch)
        th, tw = pgray.shape
        fh, fw = gray.shape
        if th > fh or tw > fw:
            return LocateResult(0, 0, 0.0, False)
        mask = _templates.get_mask(name)
        if mask is not None:
            res = cv2.matchTemplate(gray, pgray, cv2.TM_CCOEFF_NORMED, mask=mask)
        else:
            res = cv2.matchTemplate(gray, pgray, cv2.TM_CCOEFF_NORMED)
        _, score, _, maxloc = cv2.minMaxLoc(res)
        cx = maxloc[0] + tw // 2
        cy = maxloc[1] + th // 2
        return LocateResult(cx, cy, float(score), True)

    def find(self, frame: np.ndarray, name: str) -> LocateResult:
        r = self._match_one(frame, name)
        t = next((x for x in _templates.load_templates() if x.name == name), None)
        threshold = t.score_threshold if t else 0.8
        if r.found and r.score >= threshold:
            return r
        if self._vlm_fallback is not None:
            fb = self._vlm_fallback(frame, name, r.score)
            if fb is not None:
                return fb
        return LocateResult(0, 0, r.score, False)

    def find_all(self, frame: np.ndarray, names: list[str], threshold: float | None = None) -> dict[str, LocateResult]:
        return {name: self.find(frame, name) for name in names}
