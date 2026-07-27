import os
import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}
        d = os.path.dirname(__file__)
        self._winmouse = os.path.join(d, "winmouse.exe")
        self._wine_env = {**self._env,
                          "WINEPREFIX": "/home/swong/dls/wineprefix_dls"}

    def _sendinput(self, x: int, y: int, action: int) -> None:
        try:
            subprocess.run(
                ["/usr/bin/wine", self._winmouse, str(x), str(y), str(action)],
                env=self._wine_env, timeout=10, check=False,
                capture_output=True
            )
        except Exception:
            pass

    def _xdo(self, args: list[str]) -> None:
        subprocess.run(["xdotool"] + args, env=self._env,
                       timeout=5, check=False)

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._xdo(["mousemove", str(x), str(y)])

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._xdo(["mousemove", str(x), str(y)])
        self._xdo(["click", "1"])

    def click_right(self, x: int, y: int) -> None:
        self._sendinput(x, y, 7)
        time.sleep(0.05)
        self._sendinput(x, y, 4)

    def double_click(self, x: int, y: int) -> None:
        self._xdo(["mousemove", str(x), str(y)])
        self._xdo(["click", "--repeat", "2", "--delay", "50", "1"])

    def middle_click(self, x: int, y: int) -> None:
        self._xdo(["mousemove", str(x), str(y)])
        self._xdo(["click", "2"])

    def scroll(self, direction: int, amount: int = 1) -> None:
        btn = "4" if direction > 0 else "5"
        for _ in range(amount):
            self._sendinput(0, 0, 6 if direction > 0 else 5)

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             speed: float = 400) -> None:
        self._xdo(["mousemove", str(x1), str(y1)])
        time.sleep(0.05)
        self._xdo(["mousedown", "1"])
        self._xdo(["mousemove", str(x2), str(y2)])
        dx = x2 - x1
        dy = y2 - y1
        d = (dx * dx + dy * dy) ** 0.5
        if d > 0 and speed > 0:
            time.sleep(d / speed)
        self._xdo(["mouseup", "1"])

    def key_press(self, key: str) -> None:
        self._xdo(["key", key])

    def type_text(self, text: str) -> None:
        self._xdo(["type", text])
