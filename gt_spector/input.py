import math
import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        dx = 0
        dy = 0
        try:
            out = subprocess.run(
                ["xdotool", "getmouselocation"],
                capture_output=True, text=True, env=self._env, timeout=5,
                check=False
            ).stdout
            parts = out.strip().split()
            cx = int(parts[0].split(":")[1])
            cy = int(parts[1].split(":")[1])
            dx = x - cx
            dy = y - cy
        except (OSError, ValueError, IndexError):
            pass
        try:
            subprocess.run(
                ["xdotool", "mousemove", "--sync", str(x), str(y)],
                env=self._env, timeout=3, check=False
            )
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["xdotool", "mousemove", str(x), str(y)],
                env=self._env, timeout=3, check=False
            )
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self.move_mouse(x, y, speed)
        subprocess.run(["xdotool", "click", "1"], env=self._env, timeout=5, check=False)

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        try:
            subprocess.run(
                ["xdotool", "mousemove", "--sync", str(x1), str(y1)],
                env=self._env, timeout=3, check=False
            )
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["xdotool", "mousemove", str(x1), str(y1)],
                env=self._env, timeout=3, check=False
            )
        subprocess.run(["xdotool", "mousedown", "1"], env=self._env, timeout=5, check=False)
        try:
            subprocess.run(
                ["xdotool", "mousemove", "--sync", str(x2), str(y2)],
                env=self._env, timeout=3, check=False
            )
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["xdotool", "mousemove", str(x2), str(y2)],
                env=self._env, timeout=3, check=False
            )
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)
        subprocess.run(["xdotool", "mouseup", "1"], env=self._env, timeout=5, check=False)

    def key_press(self, key: str) -> None:
        subprocess.run(["xdotool", "key", key], env=self._env, timeout=5, check=False)

    def type_text(self, text: str) -> None:
        subprocess.run(["xdotool", "type", text], env=self._env, timeout=30, check=False)
