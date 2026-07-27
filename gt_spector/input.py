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

    def _wine(self, x: int, y: int, action: int) -> None:
        try:
            subprocess.run(
                ["/usr/bin/wine", self._winmouse, str(x), str(y), str(action)],
                env=self._wine_env, timeout=10, check=False,
                capture_output=True
            )
        except Exception:
            pass

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._wine(x, y, 7)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._wine(x, y, 1)

    def click_right(self, x: int, y: int) -> None:
        self._wine(x, y, 4)

    def double_click(self, x: int, y: int) -> None:
        self._wine(x, y, 1)
        time.sleep(0.1)
        self._wine(x, y, 1)

    def middle_click(self, x: int, y: int) -> None:
        subprocess.run(
            ["xdotool", "mousemove", str(x), str(y)],
            env=self._env, timeout=2, check=False
        )
        subprocess.run(
            ["xdotool", "click", "2"],
            env=self._env, timeout=5, check=False
        )

    def scroll(self, direction: int, amount: int = 1) -> None:
        btn = 6 if direction > 0 else 5
        for _ in range(amount):
            self._wine(0, 0, btn)

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             speed: float = 400) -> None:
        self._wine(x1, y1, 2)
        time.sleep(0.1)
        self._wine(x2, y2, 8)
        dx = x2 - x1
        dy = y2 - y1
        d = (dx * dx + dy * dy) ** 0.5
        if d > 0 and speed > 0:
            time.sleep(d / speed)
        self._wine(x2, y2, 3)

    def key_press(self, key: str) -> None:
        subprocess.run(
            ["xdotool", "key", key],
            env=self._env, timeout=5, check=False
        )

    def type_text(self, text: str) -> None:
        subprocess.run(
            ["xdotool", "type", text],
            env=self._env, timeout=30, check=False
        )
