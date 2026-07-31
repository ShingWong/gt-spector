import time
from typing import Any, Protocol


class BotScript(Protocol):
    name: str

    def on_start(self, display: int) -> None:
        ...

    def on_stop(self, display: int) -> None:
        ...

    def tick(self, frame: Any) -> str | None:
        """Process one poll cycle. Return status string or None."""
        ...


class ScriptRunner:
    def __init__(self, display: int, shm: Any, inp: Any, vlm: Any) -> None:
        self.display = display
        self.shm = shm
        self.inp = inp
        self.vlm = vlm
        self.script: BotScript | None = None
        self._last_verify = 0.0
        self._verify_interval = 30.0
        self._check_pixels: list[tuple[int, int, int, int, int, int]] = []

    def start(self, script: BotScript) -> None:
        self.script = script
        script.on_start(self.display)

    def run_script(self, script: BotScript) -> None:
        self.start(script)

    def stop(self) -> None:
        if self.script:
            self.script.on_stop(self.display)
        self.script = None

    def set_verify(self, pixels: list[tuple[int, int, int, int, int, int]]) -> None:
        """pixels: [(x, y, r_min, r_max, g_max, b_max), ...]"""
        self._check_pixels = pixels

    def verify_screen(self, frame: Any) -> bool:
        if not self._check_pixels:
            return True
        for x, y, r_min, r_max, g_max, b_max in self._check_pixels:
            r, g, b = frame[y, x, :3]
            if not (r_min <= r <= r_max and g <= g_max and b <= b_max):
                return False
        return True

    def tick(self, frame: Any) -> str | None:
        if not self.script:
            return None

        now = time.monotonic()
        if now - self._last_verify > self._verify_interval:
            self._last_verify = now
            if not self.verify_screen(frame):
                return "WRONG_SCREEN"

        return self.script.tick(frame)
