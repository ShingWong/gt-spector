from __future__ import annotations

import numpy as np

from .screen import Screen, ShmScreen
from .source import SourceKind, parse_source


class Session:
    def __init__(self, display: str, source: str = "file:///tmp/test-frame.png", fps: int = 5):
        self.display = display
        self.fps = fps
        spec = parse_source(source)
        if spec.kind == SourceKind.FILE:
            self._screen: Screen | ShmScreen | None = Screen(spec.path)
        elif spec.kind == SourceKind.SHM:
            self._screen = ShmScreen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind} not implemented")
        from .input import Input
        self._input: Input | None = Input(display)

    def _check_attached(self) -> None:
        if self._screen is None or self._input is None:
            raise RuntimeError("Session detached")

    @property
    def frame(self) -> np.ndarray:
        self._check_attached()
        return self._screen.frame

    def refresh(self) -> np.ndarray:
        self._check_attached()
        return self._screen.refresh()

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        self._check_attached()
        return self._screen.get_pixel(x, y)

    def capture_area(self, x1: int, y1: int, x2: int, y2: int):
        self._check_attached()
        return self._screen.capture_area(x1, y1, x2, y2)

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._check_attached()
        self._input.move_mouse(x, y, speed)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._check_attached()
        self._input.click(x, y, speed)

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        self._check_attached()
        self._input.drag(x1, y1, x2, y2, speed)

    def key_press(self, key: str) -> None:
        self._check_attached()
        self._input.key_press(key)

    def type_text(self, text: str) -> None:
        self._check_attached()
        self._input.type_text(text)

    def attach(self, display: str, source: str = "") -> None:
        spec = parse_source(source)
        if spec.kind == SourceKind.FILE:
            self._screen = Screen(spec.path)
        elif spec.kind == SourceKind.SHM:
            self._screen = ShmScreen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind}")
        self.display = display
        from .input import Input
        self._input = Input(display)

    @property
    def triggers(self):
        from .triggers import Triggers
        return Triggers(self)

    def detach(self) -> None:
        self.display = ""
        self._screen = None
        self._input = None

    @staticmethod
    def list_sessions() -> list[dict]:
        import glob, struct
        sessions = []
        for path in glob.glob("/dev/shm/gt-spector-*-frame"):
            try:
                with open(path, "rb") as f:
                    data = f.read(16)
                    if len(data) >= 16:
                        counter, w, h = struct.unpack("<QII", data)
                        shm_id = path.split("-")[-1].replace("-frame", "")
                        sessions.append({
                            "id": shm_id,
                            "path": path,
                            "frame": counter,
                            "width": w,
                            "height": h,
                        })
            except Exception:
                pass
        return sessions
