"""NavigateBot: move a bot to the alliance help dialog, then stop.

One-shot navigation: from any screen, navigate to the alliance_menu, open
the help dialog, and report the final screen. Unlike HelpBot it does not run
the help-click loop. Useful to stage bots for the help flow or to verify
navigation works.
"""

from __future__ import annotations

from typing import Any

from gt_spector.locator import Locator


class NavigateBot:
    name = "navigate-help-dialog"

    def __init__(self) -> None:
        self._display = 0
        self._gw: Any = None
        self._session: Any = None
        self._locator = Locator()
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
        self._status = "starting"

    def on_stop(self, display: int) -> None:
        pass

    def start(self, display: int) -> None:
        """Navigate once to the help dialog and record the final status."""
        self.on_start(display)
        from gt_spector.scripts.help_nav import navigate_to_help_dialog
        self._status = navigate_to_help_dialog(self._gw, self._locator, self._session)

    def stop(self) -> None:
        self._status = "stopped"

    # Compatibility with ScriptRunner tick(frame) signature.
    def tick(self, frame: Any = None) -> str | None:
        return self._status
