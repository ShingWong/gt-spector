import numpy as np
from PIL import Image


class Screen:
    def __init__(self, source_path: str):
        self._source_path = source_path
        self._frame: np.ndarray | None = None

    def refresh(self) -> np.ndarray:
        with Image.open(self._source_path) as img:
            self._frame = np.asarray(img.convert("RGB"))
        return self._frame

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            return self.refresh()
        return self._frame

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return tuple(map(int, self.frame[y, x]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()
