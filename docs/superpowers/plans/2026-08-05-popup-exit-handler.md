# Popup Exit Handler (exit_popups) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared `exit_popups(session, screen)` dispatcher that exits every popup/screen-saver screen type (ESC vs. back-button), called from normal navigation and the help loop's stuck path, so bots never get stuck on screens like `road_to_conquest_menu`.

**Architecture:** A new `gt_spector/popups.py` module holds the registry (`SCREENSAVER_SCREENS`, `BACK_BUTTON_SCREENS`, `BACK_BUTTON_TEMPLATE`) and `exit_popups(session, screen) -> bool`. Two new screens (`road_to_conquest_menu`, `resouce_reaping`) are registered in `game_world.yaml` with fixed templates; `GameWorld.identify()` gets a last-resort `common_back_button_detect_static` fallback returning `unknown_screen_with_back_button`. `HelpBot._tick`, the stuck path, and `help_nav.navigate_to_help_dialog` all call `exit_popups` first.

**Tech Stack:** Python, `game_world.yaml`, `templates.json`, `help_bot.py`, `help_nav.py`, `game_world.py`.

## Global Constraints

- Templates `popup_road_to_conquest_detect_static` (pos 88,20) and `common_back_button_detect_static` (pos 22,21) are registered in `templates.json` with `fixed: True`. Template `resouce_reaping_detect_static` is already `fixed: True`.
- `exit_popups(session, screen: str | None) -> bool` — True if an exit action was performed, False otherwise. Exact signature used by all callers.
- Screen names in the registries MUST exist in `game_world.yaml` (so `identify()` returns them): `road_to_conquest_menu`, `resouce_reaping`, `unknown_screen_with_back_button` (fallback label, no game-world entry needed).
- `BACK_BUTTON_SCREENS = ("road_to_conquest_menu", "unknown_screen_with_back_button")` — exit by clicking the common back button (locate `common_back_button_detect_static`, click its center).
- `SCREENSAVER_SCREENS = ("resouce_reaping", "another_login_disconnect")` — exit by ESC.
- `identify()` fallback is the FINAL attempt, after all known screens fail: locate `common_back_button_detect_static`; if found return `unknown_screen_with_back_button`, else None.
- No VLM in this flow.
- Unit tests use fake sessions (no real wine/Xvfb).

---
### Task 1: popups.py with exit_popups

**Files:**
- Create: `gt_spector/popups.py`
- Test: `tests/test_popups.py`

**Interfaces:**
- Consumes: `session` (`.key_press(str)`, `.click(x, y)`, `.refresh()`, `.frame`), `locator` (`.find(frame, name) -> result` with `.found`, `.cx`, `.cy`).
- Produces: `exit_popups(session, locator, screen: str | None) -> bool` — the module all later tasks call. Note: the dispatcher needs the locator to click the back button, so the signature includes `locator`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_popups.py`:

```python
from gt_spector.popups import (
    BACK_BUTTON_SCREENS,
    SCREENSAVER_SCREENS,
    exit_popups,
)


class _FakeLocate:
    def __init__(self, found=True):
        self.found = found
        self.cx = 22
        self.cy = 21


class _FakeLocator:
    def find(self, frame, name):
        return _FakeLocate()


class _FakeSession:
    def __init__(self):
        self.keys = []
        self.clicks = []
        self.refreshed = 0

    def key_press(self, key):
        self.keys.append(key)

    def click(self, x, y):
        self.clicks.append((x, y))

    def refresh(self):
        self.refreshed += 1


def test_exit_popups_esc_for_screensaver():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "resouce_reaping") is True
    assert "Escape" in s.keys


def test_exit_popups_esc_for_another_login():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "another_login_disconnect") is True
    assert "Escape" in s.keys


def test_exit_popups_back_button_for_road_to_conquest():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "road_to_conquest_menu") is True
    assert s.clicks == [(22, 21)]


def test_exit_popups_back_button_for_unknown_with_back():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "unknown_screen_with_back_button") is True
    assert s.clicks == [(22, 21)]


def test_exit_popups_no_action_for_unknown_screen():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "shelter_view") is False
    assert s.keys == [] and s.clicks == []


def test_exit_popups_none_screen_no_action():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), None) is False


def test_exit_popups_no_action_when_back_button_missing():
    class _NoBack(_FakeLocator):
        def find(self, frame, name):
            return _FakeLocate(found=False)

    s = _FakeSession()
    assert exit_popups(s, _NoBack(), "road_to_conquest_menu") is False
    assert s.clicks == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_popups.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gt_spector.popups'`

- [ ] **Step 3: Write minimal implementation**

Create `gt_spector/popups.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_popups.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check gt_spector/popups.py tests/test_popups.py`
Expected: no errors.

```bash
git add gt_spector/popups.py tests/test_popups.py
git commit -m "feat: exit_popups registry for screen-saver and back-button popups"
```

---
### Task 2: Register road_to_conquest_menu and resouce_reaping screens

**Files:**
- Modify: `gt_spector/game_world.yaml` (add two screens near `another_login_disconnect`, ~line 283)
- Modify: `gt_spector/templates_store/templates.json` (set `fixed: True` for `popup_road_to_conquest_detect_static` and `common_back_button_detect_static`)
- Test: `tests/test_game_world.py`

**Interfaces:**
- Consumes: templates already present in `templates.json` and patch files.
- Produces: screens `road_to_conquest_menu` and `resouce_reaping` identifiable by `GameWorld.identify()`. Later tasks and `exit_popups` rely on these names.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_game_world.py`:

```python
def test_road_to_conquest_screen_registered():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    spec = gw.screens["road_to_conquest_menu"]
    assert spec["templates"] == ["popup_road_to_conquest_detect_static"]


def test_resouce_reaping_screen_registered():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    spec = gw.screens["resouce_reaping"]
    assert spec["templates"] == ["resouce_reaping_detect_static"]


def test_popup_templates_fixed():
    from gt_spector import templates as _t
    by_name = {t.name: t for t in _t.load_templates()}
    assert by_name["popup_road_to_conquest_detect_static"].fixed is True
    assert by_name["common_back_button_detect_static"].fixed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_game_world.py::test_road_to_conquest_screen_registered tests/test_game_world.py::test_resouce_reaping_screen_registered tests/test_game_world.py::test_popup_templates_fixed -v`
Expected: FAIL — KeyError `road_to_conquest_menu` (and `fixed` False for the templates).

- [ ] **Step 3: Add screens to game_world.yaml**

Insert after the `another_login_disconnect` screen block (line ~288):

```yaml
  road_to_conquest_menu:
    description: '"Road to Conquest" menu popup. Does NOT dismiss with ESC
      or a click-anywhere; must click the common back button
      (common_back_button_detect_static) to return to the previous screen.'
    templates: [popup_road_to_conquest_detect_static]
  resouce_reaping:
    description: '"Resource Reaping" screen-saver popup that appears over any
      screen during inactivity. Dismiss with a single ESC (or any click).'
    templates: [resouce_reaping_detect_static]
    advance: esc
```

- [ ] **Step 4: Set fixed=True on the two templates**

Run a Python one-liner to flip `fixed` to `True` for `popup_road_to_conquest_detect_static` and `common_back_button_detect_static` in `gt_spector/templates_store/templates.json`:

```python
import json
p = 'gt_spector/templates_store/templates.json'
d = json.load(open(p))
for t in d:
    if t['name'] in ('popup_road_to_conquest_detect_static', 'common_back_button_detect_static'):
        t['fixed'] = True
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
```

Verify: `python3 -c "import json; d=json.load(open('gt_spector/templates_store/templates.json')); print([(t['name'],t['fixed']) for t in d if 'road' in t['name'] or 'back_button' in t['name']])"` shows both True.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_game_world.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gt_spector/game_world.yaml gt_spector/templates_store/templates.json tests/test_game_world.py
git commit -m "feat: register road_to_conquest_menu and resouce_reaping screens as fixed templates"
```

---
### Task 3: identify() last-resort back-button fallback

**Files:**
- Modify: `gt_spector/game_world.py` (`identify()`, ~line 61)
- Test: `tests/test_game_world.py`

**Interfaces:**
- Consumes: `self._locator` (`.find(frame, name)`), `self.screens`.
- Produces: `identify(session)` now returns `unknown_screen_with_back_button` when no known screen matches but `common_back_button_detect_static` is found. `exit_popups` (Task 1) and `HelpBot` (Task 4) rely on this label.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_game_world.py`:

```python
def test_identify_returns_unknown_with_back_button_as_last_resort(monkeypatch):
    from gt_spector import game_world as gw_mod
    from gt_spector.game_world import GameWorld

    class _Locate:
        def __init__(self, found):
            self.found = found

    class _Locator:
        def find(self, frame, name):
            if name == "common_back_button_detect_static":
                return _Locate(True)
            return _Locate(False)

    gw = GameWorld()
    gw.set_locator(_Locator())
    session = type("S", (), {"frame": object()})()
    assert gw.identify(session) == "unknown_screen_with_back_button"


def test_identify_returns_none_when_no_back_button(monkeypatch):
    from gt_spector.game_world import GameWorld

    class _Locate:
        def __init__(self, found):
            self.found = found

    class _Locator:
        def find(self, frame, name):
            return _Locate(False)

    gw = GameWorld()
    gw.set_locator(_Locator())
    session = type("S", (), {"frame": object()})()
    assert gw.identify(session) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_game_world.py::test_identify_returns_unknown_with_back_button_as_last_resort tests/test_game_world.py::test_identify_returns_none_when_no_back_button -v`
Expected: FAIL — identify returns None (no fallback yet).

- [ ] **Step 3: Add the fallback to identify()**

Modify the end of `identify()` in `gt_spector/game_world.py`:

```python
        for name, spec in self.screens.items():
            if spec.get("templates"):
                if self._locator is not None and self._templates_match(session, spec["templates"]):
                    return name
                continue
            fp = spec.get("fingerprint")
            if not fp:
                continue
            if self._matches(session, fp):
                return name
        # Last resort: an unknown screen that still has the shared back
        # button UI element. The caller can exit it via exit_popups.
        if self._locator is not None:
            r = self._locator.find(session.frame, "common_back_button_detect_static")
            if r.found:
                return "unknown_screen_with_back_button"
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_game_world.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check gt_spector/game_world.py tests/test_game_world.py`
Expected: no errors.

```bash
git add gt_spector/game_world.py tests/test_game_world.py
git commit -m "feat: identify() last-resort common back-button fallback"
```

---
### Task 4: HelpBot uses exit_popups in _tick and stuck path

**Files:**
- Modify: `gt_spector/scripts/help_bot.py` (`_tick`, `_reaping_popup_up`, `_dismiss_popup`, ~line 95-130)
- Test: `tests/test_help_bot.py`

**Interfaces:**
- Consumes: `exit_popups(session, locator, screen) -> bool` from `gt_spector.popups` (Task 1), `self._gw.identify`, `self._session`, `self._locator`, `self._loop.run`.
- Produces: `HelpBot._tick` exits popups before navigating; the stuck path uses `exit_popups` instead of the ad-hoc `_reaping_popup_up`/`_dismiss_popup` ESC-only handling. `help_nav` (Task 5) shares `exit_popups`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_help_bot.py`:

```python
def test_help_bot_tick_exits_popup_and_navigates(monkeypatch):
    from gt_spector.scripts.help_bot import HelpBot

    b = HelpBot()
    b._session = _TickSession(screen="road_to_conquest_menu", pixel=(71, 72, 71))
    b._gw = _TickGW()
    b._loop = type("L", (), {"run": lambda self, s: "idle", "help_clicks": 0})()
    exited = []
    monkeypatch.setattr(b, "_exit_popups",
                        lambda: exited.append(True) or True)
    monkeypatch.setattr(b, "_navigate_to_help_dialog",
                        lambda: setattr(b, "_status", "re-navigated"))
    b._tick()
    assert exited == [True]
    assert b._status == "re-navigated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_help_bot.py::test_help_bot_tick_exits_popup_and_navigates -v`
Expected: FAIL — `AttributeError: 'HelpBot' object has no attribute '_exit_popups'`

- [ ] **Step 3: Implement exit_popups usage in HelpBot**

Modify `gt_spector/scripts/help_bot.py`:

Replace `_tick`:

```python
    def _tick(self) -> None:
        self._session.refresh()
        screen = self._gw.identify(self._session)
        if self._exit_popups(screen):
            return
        if screen != "help_dialog":
            # Not in the dialog: navigate to it (re-opens after it closes).
            self._navigate_to_help_dialog()
            return
        result = self._loop.run(self._session)
        if result == "clicked":
            self._status = f"clicked_{self._loop.help_clicks}"
        elif result == "stuck":
            self._status = "stuck, re-navigating"
            self._navigate_to_help_dialog()
        else:
            self._status = result or "idle"

    def _exit_popups(self, screen: str | None) -> bool:
        """Dismiss a popup/screen-saver if one is up. True if it acted."""
        from gt_spector.popups import exit_popups

        if exit_popups(self._session, self._locator, screen):
            self._status = f"dismissed {screen}, re-navigating"
            self._navigate_to_help_dialog()
            return True
        return False
```

Remove `_reaping_popup_up` and `_dismiss_popup` (their role is now covered by
`exit_popups` via the `resouce_reaping` screen name).

- [ ] **Step 4: Update the reaping-dismiss test**

The existing `test_help_bot_tick_dismisses_reaping_screen` asserted an ESC key
was pressed via `_dismiss_popup`. Rewrite it to assert `_exit_popups` is
called (see Step 1's pattern), OR update it to use the new flow. Update it:

```python
def test_help_bot_tick_dismisses_reaping_screen(monkeypatch):
    b = HelpBot()
    b._session = _TickSession(screen="resouce_reaping", pixel=(71, 72, 71))
    b._gw = _TickGW()
    b._loop = type("L", (), {"run": lambda self, s: "idle", "help_clicks": 0})()
    exited = []
    monkeypatch.setattr(b, "_exit_popups", lambda: exited.append(True) or True)
    monkeypatch.setattr(b, "_navigate_to_help_dialog",
                        lambda: setattr(b, "_status", "re-navigated"))
    b._tick()
    assert exited == [True]
```

- [ ] **Step 5: Run the full help-bot test suite**

Run: `pytest tests/test_help_bot.py -v`
Expected: all pass. If `test_help_bot_tick_dismisses_stuck_popup` or
`test_help_bot_tick_clicks_gold_and_updates_status` break (they referenced the
old `_dismiss_popup`), update them to the new `_exit_popups` flow.

- [ ] **Step 6: Lint and commit**

Run: `source .venv/bin/activate && ruff check gt_spector/scripts/help_bot.py tests/test_help_bot.py`
Expected: no errors.

```bash
git add gt_spector/scripts/help_bot.py tests/test_help_bot.py
git commit -m "feat: HelpBot exits popups via exit_popups (ESC and back-button)"
```

---
### Task 5: help_nav clears popups during navigation

**Files:**
- Modify: `gt_spector/scripts/help_nav.py` (`navigate_to_help_dialog`, ~line 19)
- Test: `tests/test_help_bot.py` (add a navigation test)

**Interfaces:**
- Consumes: `exit_popups(session, locator, screen) -> bool` from `gt_spector.popups` (Task 1).
- Produces: `navigate_to_help_dialog(gw, locator, session) -> str` now clears popups it encounters.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_help_bot.py`:

```python
def test_navigate_to_help_dialog_exits_popup(monkeypatch):
    calls = {}

    class FakeSession:
        def refresh(self):
            calls["refresh"] = True

        def get_pixel(self, x, y):
            return (47, 44, 44)

        def click(self, x, y):
            calls["click"] = (x, y)

    class FakeGW:
        def identify(self, session):
            return "road_to_conquest_menu"

    monkeypatch.setattr(
        "gt_spector.scripts.help_nav.exit_popups",
        lambda session, locator, screen: calls.setdefault("exit", []).append(screen) or True,
    )
    monkeypatch.setattr("gt_spector.scripts.help_nav.time.sleep", lambda s: None)
    result = navigate_to_help_dialog(FakeGW(), object(), FakeSession())
    assert calls["exit"] == ["road_to_conquest_menu"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_help_bot.py::test_navigate_to_help_dialog_exits_popup -v`
Expected: FAIL — `exit_popups` is not imported/called in help_nav.

- [ ] **Step 3: Implement popup exit in help_nav**

Modify `navigate_to_help_dialog` in `gt_spector/scripts/help_nav.py` — after
identifying the screen, before navigating, clear popups:

```python
    nav = Navigator(gw, locator, session)
    session.refresh()
    screen = gw.identify(session)
    from gt_spector.popups import exit_popups
    if exit_popups(session, locator, screen):
        time.sleep(0.5)
        session.refresh()
        screen = gw.identify(session)
    if screen == "help_dialog":
        return "help_dialog"
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_help_bot.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check gt_spector/scripts/help_nav.py tests/test_help_bot.py`
Expected: no errors.

```bash
git add gt_spector/scripts/help_nav.py tests/test_help_bot.py
git commit -m "feat: help_nav clears popups via exit_popups during navigation"
```

---
### Task 6: Agent-facing documentation

**Files:**
- Modify: `AGENTS.md` (add "Popup & screen-saver handling" subsection)
- Modify: `docs/cli.md` (note popup auto-clear)
- Verify: `gt_spector/popups.py` module docstring already documents the taxonomy (from Task 1)

**Interfaces:**
- Consumes: the `exit_popups` API and screen taxonomy from Tasks 1-5.

- [ ] **Step 1: Add AGENTS.md subsection**

In `AGENTS.md`, under the "CLI Reference (agentic use)" section (after the
"One-shot initialization" subsection), add:

```markdown
### Popup & screen-saver handling

Bots can be interrupted by popup screens. `gt_spector/popups.py` provides the
single entry point `exit_popups(session, locator, screen) -> bool` and is
called automatically by navigation (`help_nav`) and the help loop
(`HelpBot._tick`), including when the help-button pixel is stuck (neither gold
nor dim).

Popup types and their exit:
- Screen saver (dismiss with ESC): `resouce_reaping`, `another_login_disconnect`.
- Back button (click `common_back_button_detect_static`): `road_to_conquest_menu`,
  `unknown_screen_with_back_button`.

`unknown_screen_with_back_button` is what `identify()` returns as a LAST
resort when no known screen matches but the shared back button is present.

To add a NEW popup type:
1. If it's a real identifiable screen, add it to `game_world.yaml` with its
   template (so `identify()` returns its name).
2. Add its name to `SCREENSAVER_SCREENS` (ESC exit) or `BACK_BUTTON_SCREENS`
   (back-button exit) in `gt_spector/popups.py`.
3. It is now handled everywhere automatically — no other call sites.
```

- [ ] **Step 2: Add docs/cli.md note**

In `docs/cli.md`, in the "Change Account" section's input-sequence paragraph
(after the eye-derived-positions note), append:

```markdown
Navigation and the help loop automatically dismiss popups and screen-saver
screens via `exit_popups` (see AGENTS.md "Popup & screen-saver handling").
```

- [ ] **Step 3: Verify docs render**

Run: `grep -n "exit_popups\|Popup & screen-saver" AGENTS.md docs/cli.md`
Expected: the new lines are present.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md docs/cli.md
git commit -m "docs: popup exit handler usage for agents (exit_popups)"
```

---
### Task 7: Live verification on bot03 / bot04 / bot05

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the full feature from Tasks 1-6.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/test_popups.py tests/test_game_world.py tests/test_help_bot.py -q`
Expected: PASS. (The full suite has 2 pre-existing unrelated failures:
`tests/test_shm_screen.py` and `tests/test_input_interactive.py`.)

Run: `ruff check gt_spector/popups.py gt_spector/game_world.py gt_spector/scripts/help_bot.py gt_spector/scripts/help_nav.py tests/test_popups.py tests/test_game_world.py tests/test_help_bot.py`
Expected: no errors.

- [ ] **Step 2: Confirm bots 03/04/05 identify road_to_conquest_menu**

bot03=:12, bot04=:13, bot05=:14 (display = 9 + bot number). Run:

```python
from gt_spector.game_world import GameWorld
from gt_spector.locator import Locator
from gt_spector import Session
gw = GameWorld(); loc = Locator(); gw.set_locator(loc)
for disp in (12, 13, 14):
    s = Session(f':{disp}', source=f'shm://{disp}')
    s.refresh()
    print(disp, gw.identify(s))
```

Expected: each prints `road_to_conquest_menu`.

- [ ] **Step 3: Drive exit_popups live on bot03**

Run:

```python
from gt_spector.popups import exit_popups
from gt_spector.locator import Locator
from gt_spector import Session
loc = Locator(); s = Session(':12', source='shm://12')
s.refresh()
print(exit_popups(s, loc, 'road_to_conquest_menu'))
```

Expected: prints True, then the screen is no longer `road_to_conquest_menu`
(re-identify to confirm it returned to the previous screen).

- [ ] **Step 4: Re-arm help bots and confirm they sit in the help dialog**

Restart the persistent help-bot runner (or rely on the console), then confirm
bots 03/04/05 navigate to `help_dialog` and stay there (status `idle`).

- [ ] **Step 5: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from popup exit verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
