from __future__ import annotations

from typing import Protocol

import numpy as np

from gt_spector import templates as _templates
from gt_spector import vlm
from gt_spector.locator import Locator


class Reader(Protocol):
    def read(self, frame: np.ndarray, name: str, center: tuple[int, int],
             value_hint: str = "") -> dict[str, str]:
        ...


class VlmReader:
    def __init__(self, locator: Locator) -> None:
        self._locator = locator

    def read(self, frame: np.ndarray, name: str, center: tuple[int, int],
             value_hint: str = "") -> dict[str, str]:
        t = next((x for x in _templates.load_templates() if x.name == name), None)
        box = self._box_around(center, t.w, t.h) if t else None
        if box is None:
            return {"value": "", "conf": "0"}
        prompt = f"Read the value shown in this region of a game UI. {value_hint}".strip()
        text = vlm.analyze_crop(frame, box, prompt)
        r = self._locator.find(frame, name)
        return {"value": text, "conf": f"{r.score:.2f}"}

    def _box_around(self, center: tuple[int, int], w: int, h: int,
                    scale: float = 2.0) -> tuple[int, int, int, int]:
        cx, cy = center
        hw, hh = int(w * scale / 2), int(h * scale / 2)
        return max(0, cx - hw), max(0, cy - hh), cx + hw, cy + hh
