"""HelpBot: navigate to the alliance help dialog and run the help loop.

Runs its own daemon thread polling at 100ms (cheap: ~0.06ms/cycle), so it does
not depend on the console's 2s UI tick. The console is only a master
controller: start(), stop(), and read help_clicks for display.

Navigation uses the deterministic game-world identification system (no VLM):
from any screen -> alliance_menu via GameWorld.navigate, then click the red
help trigger to open the dialog, then poll the gold help button and click.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from gt_spector.locator import Locator
from gt_spector.scripts.help_loop import HelpLoop

# The help trigger on the alliance menu (red when a request is active).
TRIGGER_X = 1097
TRIGGER_Y = 431

POLL_INTERVAL = 0.1  # 100ms


class HelpBot:
    name = "help-bot"
    expected_screen = "ALLIANCE"

    def __init__(self) -> None:
        self._display = 0
        self._gw = None
        self._session = None
        self._locator = Locator()
        self._loop = HelpLoop()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._status = "idle"

    @property
    def help_clicks(self) -> int:
        return self._loop.help_clicks

    @property
    def status(self) -> str:
        return self._status

    # ScriptRunner-compatible: code does runner.script.name / runner.script.
    @property
    def script(self) -> HelpBot:
        return self

    def on_start(self, display: int) -> None:
        from gt_spector.game_world import GameWorld
        from gt_spector.session import Session

        self._display = display
        self._gw = GameWorld()
        self._gw.set_locator(self._locator)
        self._session = Session(f":{display}", source=f"shm://{display}")
        self._loop = HelpLoop()
        self._status = "starting"

    def on_stop(self, display: int) -> None:
        self._stop.set()

    def start(self, display: int) -> None:
        """Start the background help loop thread."""
        self.on_start(display)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._status = "stopped"

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001, S110
                pass
            self._stop.wait(POLL_INTERVAL)

    def _tick(self) -> None:
        if self._loop.help_clicks == 0 and self._status != "navigated":
            # First: get to the help dialog.
            self._navigate_to_help_dialog()
            return
        result = self._loop.run(self._session)
        if result == "clicked":
            self._status = f"clicked_{self._loop.help_clicks}"
            # Re-navigate: dialog may close after a click.
            self._navigate_to_help_dialog()
        else:
            self._status = result

    def _navigate_to_help_dialog(self) -> None:
        self._session.refresh()
        screen = self._gw.identify(self._session)
        if screen is None:
            self._status = "unknown_screen"
            return

        if screen != "alliance_menu":
            if not self._gw.navigate(self._session, "alliance_menu"):
                self._status = "nav_failed"
                return
            time.sleep(1)
            self._session.refresh()

        r, g, b = self._session.get_pixel(TRIGGER_X, TRIGGER_Y)
        if r >= 120 and g <= 90 and b <= 90:
            self._session.click(TRIGGER_X, TRIGGER_Y)
            time.sleep(0.5)
            self._session.refresh()
        self._status = "navigated"

    # Compatibility with ScriptRunner tick(frame) signature.
    def tick(self, frame: Any = None) -> str | None:
        return self._status
