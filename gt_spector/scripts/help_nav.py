"""Shared navigation to the alliance help dialog.

Both HelpBot (continuous loop) and NavigateBot (one-shot) navigate to the
alliance menu and open the help dialog. This single function is the one
source of truth for that flow.
"""

from __future__ import annotations

import time

from gt_spector.navigator import Navigator
from gt_spector.popups import exit_popups

# The help trigger on the alliance menu (red when a request is active).
TRIGGER_X = 1097
TRIGGER_Y = 431


def navigate_to_help_dialog(gw, locator, session) -> str:
    """Navigate `session` to the alliance help dialog.

    Returns a status string: "help_dialog" on success, or one of
    "unknown_screen", "nav_failed:<screen>", "alliance_menu" when no help
    trigger is active.
    """
    nav = Navigator(gw, locator, session)
    session.refresh()
    screen = gw.identify(session)
    if exit_popups(session, locator, screen):
        time.sleep(0.5)
        session.refresh()
        screen = gw.identify(session)
    if screen == "help_dialog":
        return "help_dialog"
    if screen is None:
        return "unknown_screen"
    if screen != "alliance_menu":
        result = nav.goto("alliance_menu")
        if result != "alliance_menu":
            return f"nav_failed:{result}"
        time.sleep(0.5)
        session.refresh()
    # Open the alliance help dialog regardless of the trigger color. The red
    # trigger indicates an active request, but the dialog itself is always
    # openable and the help loop waits in it for the button pixel to change.
    session.click(TRIGGER_X, TRIGGER_Y)
    time.sleep(0.3)
    session.refresh()
    return gw.identify(session) or "alliance_menu"
