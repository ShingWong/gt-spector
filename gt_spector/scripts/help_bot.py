"""HelpBot: navigate to the alliance help dialog and run the help loop.

Uses the deterministic game-world identification system (no VLM, no hardcoded
ESC chains). Navigation: from any screen -> alliance_menu (via GameWorld.navigate),
then click the help trigger to open the help dialog, then poll the gold help
button pixel and click while it is active.
"""

from __future__ import annotations

import time
from typing import Any

from gt_spector.locator import Locator
from gt_spector.scripts import help_loop

# The help trigger on the alliance menu (red when a request is active).
TRIGGER_X = 1097
TRIGGER_Y = 431


class HelpBot:
    name = "help-bot"
    expected_screen = "ALLIANCE"

    def __init__(self) -> None:
        self._display = 0
        self._gw = None
        self._session = None
        self._locator = Locator()
        self._n_cycles = 0
        self.help_clicks = 0

    def on_start(self, display: int) -> None:
        from gt_spector.game_world import GameWorld
        from gt_spector.session import Session

        self._display = display
        self._gw = GameWorld()
        self._gw.set_locator(self._locator)
        self._session = Session(f":{display}", source=f"shm://{display}")
        self._n_cycles = 0
        self.help_clicks = 0

    def on_stop(self, display: int) -> None:
        pass

    def navigate_to_help_dialog(self) -> str | None:
        """Navigate to the alliance menu, then click the help trigger."""
        self._session.refresh()
        screen = self._gw.identify(self._session)
        if screen is None:
            return "unknown_screen"

        # From a known screen, walk the graph to alliance_menu.
        if screen != "alliance_menu":
            if not self._gw.navigate(self._session, "alliance_menu"):
                return "nav_failed"
            time.sleep(2)
            self._session.refresh()

        # Click the help trigger (red indicator / help menu) to open the dialog.
        r, g, b = self._session.get_pixel(TRIGGER_X, TRIGGER_Y)
        if help_loop.is_red(r, g, b):
            self._session.click(TRIGGER_X, TRIGGER_Y)
            time.sleep(1)
            self._session.refresh()
            return "help_dialog_opened"
        return "no_help_trigger"

    def tick(self, frame: Any) -> str | None:
        if self._n_cycles == 0:
            status = self.navigate_to_help_dialog()
            self._n_cycles += 1
            return status

        clicked = help_loop.run(self._session, None)
        if clicked:
            self.help_clicks += 1
            self._n_cycles = 0  # re-navigate next cycle (help sent, dialog may close)
            return f"help_clicked_{self.help_clicks}"
        self._n_cycles += 1
        return None
