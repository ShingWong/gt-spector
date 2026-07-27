import math
import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}
        self._window = ""
        try:
            r = subprocess.run(
                ["xdotool", "search", "--name", "Doomsday"],
                capture_output=True, text=True, env=self._env, timeout=3, check=False
            )
            if r.returncode == 0 and r.stdout.strip():
                self._window = r.stdout.strip().split("\n")[0]
        except Exception:
            pass

    def _wid_args(self):
        return ["--window", self._window] if self._window else []

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        args = ["xdotool", "mousemove"] + self._wid_args() + [str(x), str(y)]
        subprocess.run(args, env=self._env, timeout=2, check=False)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        args = ["xdotool", "mousemove"] + self._wid_args() + [str(x), str(y)]
        subprocess.run(args, env=self._env, timeout=2, check=False)
        time.sleep(0.05)
        subprocess.run(["xdotool", "click"] + self._wid_args() + ["1"],
                       env=self._env, timeout=5, check=False)

    def double_click(self, x: int, y: int) -> None:
        args = ["xdotool", "mousemove"] + self._wid_args() + [str(x), str(y)]
        subprocess.run(args, env=self._env, timeout=2, check=False)
        subprocess.run(
            ["xdotool", "click", "--repeat", "2", "--delay", "30", "1"] + self._wid_args(),
            env=self._env, timeout=5, check=False
        )

    def middle_click(self, x: int, y: int) -> None:
        args = ["xdotool", "mousemove"] + self._wid_args() + [str(x), str(y)]
        subprocess.run(args, env=self._env, timeout=2, check=False)
        subprocess.run(["xdotool", "click"] + self._wid_args() + ["2"],
                       env=self._env, timeout=5, check=False)

    def scroll(self, direction: int, amount: int = 1) -> None:
        btn = "4" if direction > 0 else "5"
        for _ in range(amount):
            subprocess.run(["xdotool", "click"] + self._wid_args() + [btn],
                           env=self._env, timeout=5, check=False)

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        args1 = ["xdotool", "mousemove"] + self._wid_args() + [str(x1), str(y1)]
        subprocess.run(args1, env=self._env, timeout=2, check=False)
        time.sleep(0.05)
        subprocess.run(["xdotool", "mousedown"] + self._wid_args() + ["1"],
                       env=self._env, timeout=5, check=False)
        time.sleep(0.05)
        args2 = ["xdotool", "mousemove"] + self._wid_args() + [str(x2), str(y2)]
        subprocess.run(args2, env=self._env, timeout=2, check=False)
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)
        subprocess.run(["xdotool", "mouseup"] + self._wid_args() + ["1"],
                       env=self._env, timeout=5, check=False)

    def key_press(self, key: str) -> None:
        subprocess.run(["xdotool", "key", key], env=self._env, timeout=5, check=False)

    def type_text(self, text: str) -> None:
        subprocess.run(["xdotool", "type", text], env=self._env, timeout=30, check=False)
