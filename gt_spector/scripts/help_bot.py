import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

TABLE_PATH = Path(os.path.expanduser("~/.config/gt-spector/nav_table.json"))


class HelpBot:
    name = "help-bot"
    expected_screen = "ALLIANCE"

    def __init__(self) -> None:
        self._badge_buttons: list[dict[str, Any]] = []
        self._n_cycles = 0
        self._display = 0

    def _load_badges(self) -> None:
        try:
            data = json.loads(TABLE_PATH.read_text())
            btns = data.get("states", {}).get("ALLIANCE", {}).get("buttons", [])
            self._badge_buttons = [b for b in btns if b.get("badge")]
        except (FileNotFoundError, json.JSONDecodeError):
            self._badge_buttons = []

    def on_start(self, display: int) -> None:
        self._display = display
        self._n_cycles = 0
        self._load_badges()

    def on_stop(self, display: int) -> None:
        pass

    def tick(self, frame: np.ndarray) -> str | None:
        if not self._badge_buttons:
            return "no_badges"

        for btn in self._badge_buttons:
            x, y = btn["x"], btn["y"]
            r, g, b = frame[y, x, :3]
            if r > 150 and g < 100 and b < 100:
                return f"badge_{btn['label']}"

        self._n_cycles += 1
        return None

    @staticmethod
    def navigate_to_alliance(display: int) -> bool:
        """Navigate from any screen to alliance. Relies on hardcoded ESC chain + clicks."""
        disp_str = f":{display}"

        def wid() -> str | None:
            r = subprocess.run(
                ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
                capture_output=True, text=True, env={"DISPLAY": disp_str},
                check=False,
            )
            for l in r.stdout.strip().splitlines():
                if l.strip().isdigit():
                    return l.strip()
            return None

        def click(x: int, y: int) -> None:
            w = wid()
            if w:
                subprocess.run(["xdotool", "mousemove", "--window", w, str(x), str(y)],
                               capture_output=True, env={"DISPLAY": disp_str}, check=False)
                subprocess.run(["xdotool", "click", "--window", w, "1"],
                               capture_output=True, env={"DISPLAY": disp_str}, check=False)

        def esc() -> None:
            w = wid()
            if w:
                subprocess.run(["xdotool", "key", "--window", w, "Escape"],
                               capture_output=True, env={"DISPLAY": disp_str}, check=False)

        # ESC chain: any screen → settlement
        for _ in range(8):
            esc()
            time.sleep(2)

        # Click alliance button in bottom toolbar
        click(847, 740)
        time.sleep(3)

        # If exit dialog appeared, cancel and retry
        click(300, 630)
        time.sleep(1)
        click(847, 740)
        time.sleep(3)
        return True
