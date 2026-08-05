# Popup Exit Handler (exit_popups) — Design

## Problem

Bots can get stuck on unexpected screens that interrupt normal operation:

- **Screen-saver type popups** that appear over any screen and dismiss with a
  single ESC (or any click): `resouce_reaping_detect_static`.
- **Back-button popups** that do NOT dismiss with ESC or a click-anywhere;
  they require clicking a common back button at a fixed location:
  `road_to_conquest_menu` (a "Road to Conquest" menu) and generic screens that
  only identify as having a back button (`unknown_screen_with_back_button`).

Currently popup dismissal is scattered: `HelpBot` special-cases the
resource-reaping screen, the login flow handles `another_login_disconnect`,
and there is no shared way for navigation or the help loop to clear "exit via
back button" popups. Bots 12/13/14 were observed stuck on
`road_to_conquest_menu` because nothing knew how to exit it.

## Goal

A single, well-documented popup-exit capability that:

1. Knows how to exit every popup/screen-saver screen type (ESC vs. back
   button).
2. Is called from normal navigation AND from the help loop's stuck path.
3. Is easy for future coding agents to extend when a new popup screen is
   discovered.

## Popup screen taxonomy

Every screen that can interrupt normal play is one of:

| Type | Exit action | Example screens |
|------|-------------|-----------------|
| Screen saver | press ESC | `resouce_reaping`, `another_login_disconnect` |
| Back button | click common back button (fixed pos) | `road_to_conquest_menu`, `unknown_screen_with_back_button` |

The exit action is decided by a registry keyed by screen name, so adding a new
popup = adding one line to a registry + (if new) a game-world screen entry.

## Identification changes

- New screen `road_to_conquest_menu` in `game_world.yaml`:
  `templates: [popup_road_to_conquest_detect_static]` (fixed template).
- New screen `resouce_reaping` in `game_world.yaml`:
  `templates: [resouce_reaping_detect_static]` (fixed template). This makes
  the screen-saver popup identifiable by name (it is currently only detected
  via the raw template in `HelpBot`).
- `GameWorld.identify()` gains a **last-resort fallback**: after every known
  screen fails to match, locate `common_back_button_detect_static`; if found,
  return `unknown_screen_with_back_button`. This is the FINAL attempt —
  `road_to_conquest_menu` is matched normally (it is a real screen); the
  fallback catches generic "some unknown screen that still has a back button".

## New module: `gt_spector/popups.py`

Central, documented registry + dispatcher.

```python
BACK_BUTTON_SCREENS = ("road_to_conquest_menu", "unknown_screen_with_back_button")
SCREENSAVER_SCREENS = ("resouce_reaping", "another_login_disconnect")

BACK_BUTTON_TEMPLATE = "common_back_button_detect_static"

def exit_popups(session, screen: str | None) -> bool:
    """Exit the popup/screen-saver `screen` if it is a known one.

    Returns True if an exit action was performed (caller should re-navigate /
    re-identify), False if nothing was done.
    """
```

Every screen named in `SCREENSAVER_SCREENS` / `BACK_BUTTON_SCREENS` must be a
registered screen in `game_world.yaml` (so `identify()` returns its name). The
screen-saver popup `resouce_reaping` needs a game-world entry
(`templates: [resouce_reaping_detect_static]`) so its name flows through
`identify()`; currently `HelpBot` detects it via the raw template. The
`road_to_conquest_menu` screen is registered with
`templates: [popup_road_to_conquest_detect_static]`.

Behavior:

- `screen in SCREENSAVER_SCREENS` → `session.key_press("Escape")`, return True.
- `screen in BACK_BUTTON_SCREENS` → locate `common_back_button_detect_static`
  (fixed pos), click its center, return True.
- Otherwise → return False (no action).

## Integration points

- **`HelpBot._tick`**: after `identify()`, call `exit_popups(session, screen)`
  BEFORE the help-dialog check. If it returns True, the popup was dismissed;
  set status and re-navigate.
- **`HelpBot` stuck path**: when `HelpLoop.run()` returns `stuck` (help button
  pixel neither gold nor dim), identify the screen and call `exit_popups`. If
  it acted, continue; else fall back to existing behavior.
- **`help_nav.navigate_to_help_dialog`**: call `exit_popups` on the identified
  screen so normal navigation also clears popups.

## Agent-facing documentation

The registry and dispatcher must be documented where agents will look:

- **`gt_spector/popups.py` module docstring**: the taxonomy table above, how to
  add a new popup, and the exact contract (`exit_popups` returns bool).
- **`AGENTS.md`**: a "Popup & screen-saver handling" subsection under CLI /
  agentic docs: when a bot is stuck, `exit_popups` is the single entry point;
  how to add a new popup type (add to game_world.yaml if a real screen, add the
  name to the correct registry tuple); the back-button template is shared and
  must NOT be used for screen-saver types.
- **`docs/cli.md`**: note that navigation and the help loop automatically clear
  popups via `exit_popups`.

## Testing

- `test_popups.py`: `exit_popups` returns True and presses ESC for a
  screen-saver; returns True and clicks back-button center for a back-button
  screen; returns False for an unknown screen.
- `test_game_world.py`: identify returns `road_to_conquest_menu` when the popup
  template matches; returns `resouce_reaping` when that template matches;
  returns `unknown_screen_with_back_button` only after all known screens fail;
  returns None when no back button either.
- `test_help_bot.py`: `_tick` calls `exit_popups` and re-navigates on a popup
  screen; stuck path exits popups.
- Live verification on bots 12/13/14 (currently stuck on road_to_conquest).

## Out of scope

- Handling non-popup modal dialogs with their own exit (e.g. settings,
  exit-dialog) — those have existing game-world navigation.
- VLM-based popup detection.
