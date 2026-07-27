import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}

    def _click_btn(self, btn: str, x: int, y: int) -> None:
        subprocess.run(
            ["xdotool", "mousemove", "--clearmodifiers", str(x), str(y)],
            env=self._env, timeout=2, check=False
        )
        time.sleep(0.05)
        subprocess.run(
            ["xdotool", "click", "--clearmodifiers", btn],
            env=self._env, timeout=5, check=False
        )

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        subprocess.run(
            ["xdotool", "mousemove", "--clearmodifiers", str(x), str(y)],
            env=self._env, timeout=2, check=False
        )

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._click_btn("1", x, y)

    def click_right(self, x: int, y: int) -> None:
        self._click_btn("3", x, y)

    def double_click(self, x: int, y: int) -> None:
        subprocess.run(
            ["xdotool", "mousemove", "--clearmodifiers", str(x), str(y)],
            env=self._env, timeout=2, check=False
        )
        subprocess.run(
            ["xdotool", "click", "--clearmodifiers", "--repeat", "2", "--delay", "30", "1"],
            env=self._env, timeout=5, check=False
        )

    def middle_click(self, x: int, y: int) -> None:
        self._click_btn("2", x, y)

    def scroll(self, direction: int, amount: int = 1) -> None:
        btn = "4" if direction > 0 else "5"
        for _ in range(amount):
            subprocess.run(
                ["xdotool", "click", "--clearmodifiers", btn],
                env=self._env, timeout=5, check=False
            )

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        subprocess.run(
            ["xdotool", "mousemove", "--clearmodifiers", str(x1), str(y1)],
            env=self._env, timeout=2, check=False
        )
        time.sleep(0.05)
        subprocess.run(["xdotool", "mousedown", "1"], env=self._env, timeout=5, check=False)
        time.sleep(0.05)
        subprocess.run(
            ["xdotool", "mousemove", str(x2), str(y2)],
            env=self._env, timeout=2, check=False
        )
        dx = x2 - x1
        dy = y2 - y1
        distance = (dx * dx + dy * dy) ** 0.5
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)
        subprocess.run(["xdotool", "mouseup", "1"], env=self._env, timeout=5, check=False)

    def key_press(self, key: str) -> None:
        subprocess.run(["xdotool", "key", key], env=self._env, timeout=5, check=False)

    def type_text(self, text: str) -> None:
        subprocess.run(["xdotool", "type", text], env=self._env, timeout=30, check=False)
