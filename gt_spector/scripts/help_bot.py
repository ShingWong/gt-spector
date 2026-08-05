"""HelpBot: navigate to the alliance help dialog and run the help loop.

Runs its own daemon thread polling at 100ms (cheap: ~0.06ms/cycle), so it does
not depend on the console's 2s UI tick. The console is only a master
controller: start(), stop(), and read help_clicks for display.

Navigation uses the deterministic game-world identification system (no VLM):
via Navigator from any screen -> alliance_menu, then click the red help
trigger to open the dialog, then poll the gold help button and click.
"""

from __future__ import annotations

import threading
from typing import Any

from gt_spector.locator import Locator
from gt_spector.scripts.help_loop import HelpLoop

POLL_INTERVAL = 0.1  # 100ms


class HelpBot:
    name = "help-bot"
    expected_screen = "ALLIANCE"
    # HelpBot re-navigates to the help dialog in its own thread on every tick.
    # The console's recovery path (ESC-to-shelter + run_script) is redundant
    # and disruptive, so the console skips it for self-healing runners.
    self_healing = True

    def __init__(self) -> None:
        self._display = 0
        self._gw: Any = None
        self._session: Any = None
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

    def run_script(self, script: Any = None) -> None:
        """Restart the help loop. ScriptRunner-compatible recovery entry."""
        self.stop()
        self.start(self._display)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001, S110
                pass
            self._stop.wait(POLL_INTERVAL)

    def _tick(self) -> None:
        self._session.refresh()
        if self._reaping_popup_up():
            self._dismiss_popup()
            return
        screen = self._gw.identify(self._session)
        if screen != "help_dialog":
            # Not in the dialog: navigate to it (re-opens after it closes).
            self._navigate_to_help_dialog()
            return
        result = self._loop.run(self._session)
        if result == "clicked":
            self._status = f"clicked_{self._loop.help_clicks}"
            # Dialog may close after a click; re-navigate next tick.
        elif result == "stuck":
            # Help button pixel is neither gold nor dim: a popup is covering
            # it. Dismiss with ESC and re-navigate.
            self._dismiss_popup()
        else:
            self._status = result or "idle"

    def _reaping_popup_up(self) -> bool:
        """True when the resource-reaping screen-saver popup is visible.

        It can appear over any screen; any click or ESC dismisses it.
        """
        try:
            r = self._locator.find(self._session.frame, "resouce_reaping_detect_static")
            return bool(r.found)
        except Exception:  # noqa: BLE001
            return False

    def _dismiss_popup(self) -> None:
        self._session.key_press("Escape")
        self._status = "dismissed_popup, re-navigating"
        self._navigate_to_help_dialog()

    def _navigate_to_help_dialog(self) -> None:
        from gt_spector.scripts.help_nav import navigate_to_help_dialog
        self._status = navigate_to_help_dialog(self._gw, self._locator, self._session)

    # Compatibility with ScriptRunner tick(frame) signature.
    def tick(self, frame: Any = None) -> str | None:
        return self._status
