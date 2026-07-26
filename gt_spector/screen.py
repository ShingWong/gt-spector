import struct

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
        return (int(self.frame[y, x, 0]), int(self.frame[y, x, 1]), int(self.frame[y, x, 2]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()


class ShmScreen:
    def __init__(self, shm_id: str):
        self._path = f"/dev/shm/gt-spector-{shm_id}-frame"
        self._frame: np.ndarray | None = None
        self._last_counter = 0

    def refresh(self) -> np.ndarray:
        try:
            with open(self._path, "rb") as f:
                data = f.read(16)
                if len(data) < 16:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                counter, w, h = struct.unpack("<QII", data)
                if counter == self._last_counter:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                self._last_counter = counter
                pixel_data = f.read(w * h * 4)
                if len(pixel_data) < w * h * 4:
                    return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)
                arr = np.frombuffer(pixel_data, dtype=np.uint8).reshape((h, w, 4))
                self._frame = arr[:, :, [2, 1, 0]].copy()
                return self._frame
        except FileNotFoundError:
            return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            return self.refresh()
        return self._frame

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return (int(self.frame[y, x, 0]), int(self.frame[y, x, 1]), int(self.frame[y, x, 2]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()
