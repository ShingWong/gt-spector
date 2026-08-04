"""NavigateBot: move a bot to the alliance help dialog, then stop.

One-shot navigation: from any screen, navigate to the alliance_menu, open
the help dialog, and report the final screen. Unlike HelpBot it does not run
the help-click loop. Useful to stage bots for the help flow or to verify
navigation works.
"""

from __future__ import annotations

from typing import Any

from gt_spector.locator import Locator
from gt_spector.navigator import Navigator

# The help trigger on the alliance menu (red when a request is active).
TRIGGER_X = 1097
TRIGGER_Y = 431


class NavigateBot:
    name = "navigate-help-dialog"

    def __init__(self) -> None:
        self._display = 0
        self._gw: Any = None
        self._session: Any = None
        self._locator = Locator()
        self._navigator: Navigator | None = None
        self._status = "idle"

    @property
    def status(self) -> str:
        return self._status

    # ScriptRunner-compatible: code does runner.script.name / runner.script.
    @property
    def script(self) -> NavigateBot:
        return self

    def on_start(self, display: int) -> None:
        from gt_spector.game_world import GameWorld
        from gt_spector.session import Session

        self._display = display
        self._gw = GameWorld()
        self._gw.set_locator(self._locator)
        self._session = Session(f":{display}", source=f"shm://{display}")
        self._navigator = Navigator(self._gw, self._locator, self._session)
        self._status = "starting"

    def on_stop(self, display: int) -> None:
        pass

    def start(self, display: int) -> None:
        """Navigate once to the help dialog and record the final status."""
        self.on_start(display)
        self._navigate()

    def stop(self) -> None:
        self._status = "stopped"

    def _navigate(self) -> None:
        nav = self._navigator
        if nav is None:
            return
        self._session.refresh()
        screen = self._gw.identify(self._session)
        if screen == "help_dialog":
            self._status = "already_at_help_dialog"
            return
        if screen is None:
            self._status = "unknown_screen"
            return
        if screen != "alliance_menu":
            result = nav.goto("alliance_menu")
            if result != "alliance_menu":
                self._status = f"nav_failed:{result}"
                return
            import time
            time.sleep(0.5)
            self._session.refresh()
        r, g, b = self._session.get_pixel(TRIGGER_X, TRIGGER_Y)
        if r >= 120 and g <= 90 and b <= 90:
            self._session.click(TRIGGER_X, TRIGGER_Y)
            import time
            time.sleep(0.3)
            self._session.refresh()
        final = self._gw.identify(self._session)
        self._status = f"navigated:{final or '?'}"

    # Compatibility with ScriptRunner tick(frame) signature.
    def tick(self, frame: Any = None) -> str | None:
        return self._status
