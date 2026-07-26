from .source import parse_source, SourceKind
from .screen import Screen

class Session:
    def __init__(self, display: str, source: str = "file:///tmp/test-frame.png", fps: int = 5):
        self.display = display
        self.fps = fps
        spec = parse_source(source)
        if spec.kind == SourceKind.FILE:
            self._screen = Screen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind} not implemented")

    @property
    def frame(self):
        return self._screen.frame

    def refresh(self):
        return self._screen.refresh()

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return self._screen.get_pixel(x, y)

    def capture_area(self, x1: int, y1: int, x2: int, y2: int):
        return self._screen.capture_area(x1, y1, x2, y2)
