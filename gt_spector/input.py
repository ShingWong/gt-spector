import os
import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}
        d = os.path.dirname(__file__)
        self._wm = os.path.join(d, "winmouse.exe")
        self._we = {**self._env,
                    "WINEPREFIX": "/home/swong/dls/wineprefix_dls"}

    def _si(self, x: int, y: int, a: int) -> None:
        try:
            subprocess.run(
                ["/usr/bin/wine", self._wm, str(x), str(y), str(a)],
                env=self._we, timeout=10, check=False, capture_output=True
            )
        except Exception:
            pass

    def _xd(self, a: list[str]) -> None:
        subprocess.run(["xdotool"] + a, env=self._env, timeout=5, check=False)

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._xd(["mousemove", str(x), str(y)])

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._xd(["mousemove", str(x), str(y)])
        self._xd(["click", "1"])

    def click_right(self, x: int, y: int) -> None:
        self._xd(["mousemove", str(x), str(y)])
        self._si(x, y, 4)

    def double_click(self, x: int, y: int) -> None:
        self._xd(["mousemove", str(x), str(y)])
        self._xd(["click", "--repeat", "2", "--delay", "40", "1"])

    def middle_click(self, x: int, y: int) -> None:
        self._xd(["mousemove", str(x), str(y)])
        self._xd(["click", "2"])

    def scroll(self, direction: int, amount: int = 1) -> None:
        for _ in range(amount):
            self._si(0, 0, 6 if direction > 0 else 5)
            time.sleep(0.05)

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             speed: float = 400) -> None:
        self._xd(["mousemove", str(x1), str(y1)])
        self._xd(["mousedown", "1"])
        self._xd(["mousemove", str(x2), str(y2)])
        dx = x2 - x1
        dy = y2 - y1
        d = (dx * dx + dy * dy) ** 0.5
        if d > 0 and speed > 0:
            time.sleep(d / speed)
        self._xd(["mouseup", "1"])

    def key_press(self, key: str) -> None:
        self._xd(["key", key])

    def type_text(self, text: str) -> None:
        self._xd(["type", text])
