import subprocess


class Input:
    def __init__(self, display: str):
        self._env = {"DISPLAY": display}
        self._wid = None

    def _find_window(self) -> str:
        if self._wid:
            return self._wid
        r = subprocess.run(
            ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
            capture_output=True, text=True, env=self._env, timeout=5, check=False
        )
        wins = r.stdout.strip().split()
        self._wid = wins[0] if wins else ""
        return self._wid

    def _xd(self, a: list[str]) -> None:
        subprocess.run(["xdotool"] + a, env=self._env, timeout=5, check=False)

    def _mw(self, x: int, y: int) -> list[str]:
        w = self._find_window()
        if w:
            return ["mousemove", "--window", w, str(x), str(y)]
        return ["mousemove", str(x), str(y)]

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._xd(self._mw(x, y))

    def mouse_down(self) -> None:
        self._xd(["mousedown", "1"])

    def mouse_up(self) -> None:
        self._xd(["mouseup", "1"])

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._xd(self._mw(x, y))
        self._xd(["click", "1"])

    def click_right(self, x: int, y: int) -> None:
        self._xd(self._mw(x, y))
        self._xd(["mousedown", "3"])
        import time
        time.sleep(0.8)
        self._xd(["mouseup", "3"])

    def double_click(self, x: int, y: int) -> None:
        self._xd(self._mw(x, y))
        self._xd(["click", "--repeat", "2", "--delay", "40", "1"])

    def middle_click(self, x: int, y: int) -> None:
        self._xd(self._mw(x, y))
        self._xd(["click", "2"])

    def drag_right(self, x1: int, y1: int, x2: int, y2: int,
                   speed: float = 400) -> None:
        self._xd(self._mw(x1, y1))
        self._xd(["mousedown", "3"])
        import time
        dx = x2 - x1
        dy = y2 - y1
        d = (dx * dx + dy * dy) ** 0.5
        steps = max(1, int(d / 10))
        step_delay = d / (steps * speed) if speed > 0 else 0
        for i in range(1, steps + 1):
            t = i / steps
            self._xd(self._mw(int(x1 + dx * t), int(y1 + dy * t)))
            if step_delay > 0:
                time.sleep(step_delay)
        self._xd(["mouseup", "3"])

    def scroll(self, direction: int, amount: int = 1) -> None:
        btn = "4" if direction > 0 else "5"
        self._xd(["click", "--repeat", str(amount), "--delay", "1", btn])

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             speed: float = 400) -> None:
        self._xd(self._mw(x1, y1))
        self._xd(["mousedown", "1"])
        dx = x2 - x1
        dy = y2 - y1
        d = (dx * dx + dy * dy) ** 0.5
        steps = max(1, int(d / 10))
        step_delay = d / (steps * speed) if speed > 0 else 0
        import time
        for i in range(1, steps + 1):
            t = i / steps
            self._xd(self._mw(int(x1 + dx * t), int(y1 + dy * t)))
            if step_delay > 0:
                time.sleep(step_delay)
        self._xd(["mouseup", "1"])

    def key_press(self, key: str) -> None:
        self._xd(["key", key])

    def type_text(self, text: str) -> None:
        self._xd(["type", text])
