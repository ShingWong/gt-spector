"""Popup / screen-saver exit handler.

Bots can be interrupted by popup screens. Each popup type has one exit:

- Screen-saver popups appear over any screen and dismiss with a single ESC
  (or any click): resouce_reaping, another_login_disconnect.
- Back-button popups do NOT dismiss with ESC; they require clicking the
  common back button at its fixed location: road_to_conquest_menu,
  unknown_screen_with_back_button.

`exit_popups(session, locator, screen)` is the single entry point. It looks
up the screen name and performs the exit, returning True if it acted. Call
it from navigation and the help loop BEFORE deciding where to navigate next.

Adding a new popup type:
1. If it is a real identifiable screen, add it to game_world.yaml with its
   template (so identify() returns its name).
2. Add its name to the correct tuple below (SCREENSAVER_SCREENS for ESC
   exit, BACK_BUTTON_SCREENS for back-button exit).
3. It is now handled everywhere automatically.
"""

from __future__ import annotations

from typing import Any

# Screens that dismiss with a single ESC (screen-saver style).
SCREENSAVER_SCREENS = ("resouce_reaping", "another_login_disconnect")

# Screens that require clicking the common back button to exit.
BACK_BUTTON_SCREENS = ("road_to_conquest_menu", "unknown_screen_with_back_button")

# Fixed-position template for the shared back-button UI element.
BACK_BUTTON_TEMPLATE = "common_back_button_detect_static"


def exit_popups(session: Any, locator: Any, screen: str | None) -> bool:
    """Exit the popup/screen-saver `screen` if it is a known one.

    Returns True if an exit action was performed (caller should re-navigate /
    re-identify), False if nothing was done.
    """
    if screen in SCREENSAVER_SCREENS:
        session.key_press("Escape")
        return True
    if screen in BACK_BUTTON_SCREENS:
        r = locator.find(session.frame, BACK_BUTTON_TEMPLATE)
        if r.found:
            session.click(r.cx, r.cy)
            return True
        return False
    return False
