import mmap
import os
import struct

import numpy as np
from PIL import Image


class Screen:
    def __init__(self, source_path: str):
        self._source_path = source_path
        self._frame: np.ndarray | None = None

    def refresh(self) -> bool:
        try:
            with Image.open(self._source_path) as img:
                self._frame = np.asarray(img.convert("RGB"))
            return True
        except Exception:
            return False

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            self.refresh()
        return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return (int(self.frame[y, x, 0]), int(self.frame[y, x, 1]), int(self.frame[y, x, 2]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()


class ShmScreen:
    def __init__(self, shm_id: str):
        self._path = f"/dev/shm/gt-spector-{shm_id}-frame"
        self._frame: np.ndarray | None = None
        self._last_counter = 0
        self._mmap: mmap.mmap | None = None

    def _ensure_mmap(self) -> bool:
        try:
            fd = os.open(self._path, os.O_RDONLY)
            size = os.lseek(fd, 0, os.SEEK_END)
            if size < 16:
                os.close(fd)
                return False
            buf = mmap.mmap(fd, size, access=mmap.ACCESS_READ)
            os.close(fd)
            self._mmap = buf
            return True
        except (FileNotFoundError, OSError):
            self._mmap = None
            return False

    def refresh(self) -> bool:
        try:
            if self._mmap is None and not self._ensure_mmap():
                return False

            header = bytes(self._mmap[:16])
            if len(header) < 16:
                return self._recover()
            counter0, w, h = struct.unpack("<QII", header)

            if counter0 == self._last_counter:
                return False

            pixel_count = w * h * 4
            if len(self._mmap) < 16 + pixel_count:
                return self._recover()

            arr = np.frombuffer(self._mmap, dtype=np.uint8, offset=16, count=pixel_count)
            arr = arr.reshape((h, w, 4))

            header2 = bytes(self._mmap[:16])
            counter1, _, _ = struct.unpack("<QII", header2)
            if counter0 != counter1:
                return False

            self._last_counter = counter0
            self._frame = arr[:, :, [0, 1, 2]]
            return True

        except (ValueError, OSError, struct.error):
            return self._recover()

    def _recover(self) -> bool:
        self._mmap = None
        return False

    def __del__(self):
        if self._mmap is not None:
            self._mmap.close()

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            self.refresh()
        return self._frame if self._frame is not None else np.zeros((1, 1, 3), dtype=np.uint8)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return (int(self.frame[y, x, 0]), int(self.frame[y, x, 1]), int(self.frame[y, x, 2]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()
