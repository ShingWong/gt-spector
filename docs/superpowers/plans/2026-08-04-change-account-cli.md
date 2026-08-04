# change-account CLI Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `change-account` command to the interactive CLI that drives the full IGG browser login flow (verified live on bot04), pausing for human confirmation at each step.

**Architecture:** A new `gt_spector/login_flow.py` module encapsulates the 10-step login sequence, using the existing `Navigator` for screen-to-screen movement, template/fingerprint identification for verification (no VLM), and the one-shot `sendtext.exe` Wine helper for reliable typing. The CLI `CliSession.do_change_account` wires the flow's `confirm` hook to an interactive prompt.

**Tech Stack:** Python, existing `game_world.yaml` + `locator.py` + `navigator.py`, the pre-built `sendtext.exe` Windows helper, `subprocess`.

## Global Constraints

- Line length 100 (ruff). mypy strict.
- No comments unless a public API needs a docstring.
- Test with `pytest tests/` from `/home/swong/dls/src/gt-spector`; lint `ruff check gt_spector/ tests/`.
- Window offset for clicks: game window is at screen `(3,29)`, so a window-relative `(x,y)` = screen click `(x+3, y+29)`.
- Typing MUST use the one-shot `sendtext.exe`, never the `sendtextd` daemon (daemon clicks are unreliable).
- No VLM anywhere in the flow.
- All farm accounts have exactly one IGG ID; no multi-ID logic.

---

### Task 1: sendtext.exe wrapper for click+type

**Files:**
- Create: `gt_spector/typing.py`
- Test: `tests/test_typing.py`

**Interfaces:**
- Consumes: nothing (standalone; uses prebuilt `gt_spector/tools/sendtext.exe`).
- Produces: `type_at(prefix: str, display: str, text: str, x: int, y: int) -> bool` and `click_at(prefix: str, display: str, x: int, y: int) -> bool`. Later tasks use these.

- [ ] **Step 1: Write the failing test**

```python
import subprocess

import pytest


class FakeResult:
    returncode = 0


def test_type_at_invokes_sendtext(monkeypatch):
    from gt_spector import typing as T

    calls = []
    def fake_run(cmd, env=None, **kw):
        calls.append((cmd, env))
        return FakeResult()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ok = T.type_at("/home/swong/dls/wineprefix_bots/bot04", ":13",
                   "{CtrlA}sr02-07@mx1.us", 365, 156)
    assert ok is True
    assert len(calls) == 1
    cmd, env = calls[0]
    assert cmd[0] == "/opt/wine-proton/bin/wine"
    assert cmd[-1].endswith("sendtext.exe")
    assert "{CtrlA}sr02-07@mx1.us" in cmd
    assert "365" in cmd and "156" in cmd
    assert env["WINEPREFIX"] == "/home/swong/dls/wineprefix_bots/bot04"
    assert env["DISPLAY"] == ":13"


def test_click_at_uses_empty_text(monkeypatch):
    from gt_spector import typing as T

    calls = []
    def fake_run(cmd, env=None, **kw):
        calls.append(cmd)
        return FakeResult()
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert T.click_at("/p", ":13", 700, 560) is True
    assert calls[0][-3] == ""  # empty text arg


def test_type_at_reports_failure(monkeypatch):
    from gt_spector import typing as T

    class FailResult:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FailResult())
    assert T.type_at("/p", ":13", "x", 1, 2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_typing.py -v`
Expected: FAIL with "cannot import name 'type_at'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Reliable SendInput typing via the one-shot sendtext.exe Wine helper.

The game's browser login form drops '@'/uppercase under X11 typing, so text
must go through the Windows SendInput (KEYEVENTF_UNICODE) helper. The
one-shot binary (not the sendtextd daemon) does SetForegroundWindow ->
click(x,y) -> type reliably.
"""

from __future__ import annotations

import subprocess

WINE = "/opt/wine-proton/bin/wine"
SENDTEXT = "/home/swong/dls/src/gt-spector/gt_spector/tools/sendtext.exe"


def _run(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    env = {"WINEPREFIX": prefix, "DISPLAY": display}
    r = subprocess.run(
        [WINE, SENDTEXT, text, str(x), str(y)],
        env=env, capture_output=True, timeout=30, check=False,
    )
    return r.returncode == 0


def type_at(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    """Click (x,y) window-relative and type `text` via sendtext.exe."""
    return _run(prefix, display, text, x, y)


def click_at(prefix: str, display: str, x: int, y: int) -> bool:
    """Click (x,y) window-relative via sendtext.exe (empty text)."""
    return _run(prefix, display, "", x, y)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_typing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gt_spector/typing.py tests/test_typing.py
git commit -m "feat: sendtext.exe click+type wrapper"
```

---

### Task 2: Game world locations for login fields

**Files:**
- Modify: `gt_spector/game_world.yaml` (locations section, ~line 166)
- Test: `tests/test_game_world.py` (add a loader assertion)

**Interfaces:**
- Consumes: nothing.
- Produces: locations `login_enter_email_static`, `login_enter_password`, `login_eye_static`, `login_login_static` (window-relative coords) and confirmed `igg_login` / `select_igg_id` screen templates. Later tasks locate these.

- [ ] **Step 1: Write the failing test**

```python
def test_login_field_locations_present():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    for name, coords in {
        "login_enter_email_static": (365, 156),
        "login_enter_password": (365, 226),
        "login_eye_static": (885, 195),
        "login_login_static": (462, 258),
    }.items():
        loc = gw.locations.get(name)
        assert loc is not None, f"missing {name}"
        assert (loc["x"], loc["y"]) == coords, f"{name} at {coords}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_game_world.py::test_login_field_locations_present -v`
Expected: FAIL (locations missing or coords wrong)

- [ ] **Step 3: Update game_world.yaml**

In the locations block (near `login_current_static` ~line 172), add or correct:

```yaml
  login_current_static: {x: 323, y: 125, screens: [igg_login]}
  login_use_another_static: {x: 518, y: 369, screens: [igg_login]}
  igg_login_exit_static: {x: 1050, y: 17, screens: [igg_login]}
  login_enter_email_static: {x: 365, y: 156, screens: [igg_login]}
  login_enter_password: {x: 365, y: 226, screens: [igg_login]}
  login_eye_static:    {x: 885, y: 195, screens: [igg_login]}
  login_login_static:  {x: 462, y: 258, screens: [igg_login]}
```

Ensure `igg_login` screen `templates:` is `[igg_login_exit_static]` and `select_igg_id` templates is `[login_select_igg_id_static]` (both already set). Ensure `login_ok_currently_static` is `fixed: true` in `templates_store/templates.json` (done in the live fix; verify).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_game_world.py::test_login_field_locations_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gt_spector/game_world.yaml gt_spector/templates_store/templates.json tests/test_game_world.py
git commit -m "feat: login field locations in game world"
```

---

### Task 3: LoginFlow module

**Files:**
- Create: `gt_spector/login_flow.py`
- Test: `tests/test_login_flow.py`

**Interfaces:**
- Consumes: `typing.type_at`, `typing.click_at` (Task 1); `GameWorld`, `Locator`, `Navigator`; `BotManager` for prefix-from-display.
- Produces: `LoginFlow(session, gw, locator, prefix, display, confirm=...)` with `change_account(email, password) -> str` and `_window_click(x, y) -> None` (screen coords = window + 3, +29). `confirm: Callable[[str], bool]`. Constants `EMAIL=(365,156)`, `PASSWORD=(365,226)`, `EYE=(885,195)`, `LOGIN_BTN=(462,258)`, `CONTINUE=(500,300)`, `SELECT_ID=(350,165)`, `OK=(700,560)`. Returns final screen name, or "error".

- [ ] **Step 1: Write the failing test**

```python
import numpy as np

from gt_spector.login_flow import LoginFlow


class FakeGW:
    def __init__(self):
        self.screens = {}
        self.navigation = {}
        self._locator = None
        self._screen = "settings"
    def identify(self, session):
        return self._screen
    def set_locator(self, loc):
        pass


class FakeSession:
    def __init__(self):
        self.clicks = []
        self.display = ":13"
    def refresh(self):
        pass
    def get_pixel(self, x, y):
        return (255, 255, 255)


def test_window_click_offsets_by_3_29():
    s = FakeSession()
    gw = FakeGW()
    flow = LoginFlow(s, gw, None, "/p", ":13", confirm=lambda m: True)
    flow._window_click(100, 200)
    assert s.clicks == [(103, 229)]


def test_change_account_stops_on_rejected_confirm(monkeypatch):
    import gt_spector.typing as T
    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return msg == "navigate"  # only first step accepted
    flow = LoginFlow(s, gw, None, "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    result = flow.change_account("a@b.c", "pw")
    assert result == "cancelled"
    assert seen == ["navigate", "open igg browser"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_login_flow.py -v`
Expected: FAIL with "cannot import name 'LoginFlow'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Automated IGG browser login for a bot (change account).

Verified live on bot04 (2026-08-04). Coordinates are window-relative;
screen clicks add the (+3,+29) window offset. Typing uses the one-shot
sendtext.exe helper. Each step can be confirmed/rejected via the `confirm`
hook; during development the CLI wires it to a prompt.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gt_spector import typing

EMAIL = (365, 156)
PASSWORD = (365, 226)
EYE = (885, 195)
LOGIN_BTN = (462, 258)
CONTINUE = (500, 300)
SELECT_ID = (350, 165)
OK = (700, 560)
WIN_OFFSET = (3, 29)


class LoginFlow:
    def __init__(
        self,
        session: Any,
        gw: Any,
        locator: Any,
        prefix: str,
        display: str,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._session = session
        self._gw = gw
        self._locator = locator
        self._prefix = prefix
        self._display = display
        self._confirm = confirm or (lambda _msg: True)

    def _window_click(self, x: int, y: int) -> None:
        self._session.click(x + WIN_OFFSET[0], y + WIN_OFFSET[1])

    def _type(self, text: str, x: int, y: int) -> bool:
        return typing.type_at(self._prefix, self._display, f"{{CtrlA}}{text}", x, y)

    def _wait(self, seconds: float = 4.0) -> None:
        time.sleep(seconds)
        self._session.refresh()

    def change_account(self, email: str, password: str) -> str:
        gw = self._gw
        from gt_spector.navigator import Navigator
        nav = Navigator(gw, self._locator, self._session)

        steps = [
            ("navigate", lambda: nav.goto("change_account") is not None),
            ("open igg browser", self._open_igg_browser),
            ("enter email", lambda: self._type(email, *EMAIL)),
            ("enter password", lambda: self._type(password, *PASSWORD)),
            ("reveal password", lambda: self._window_click(*EYE) or True),
            ("submit login", self._submit_login),
            ("select id", self._select_id),
            ("confirm ok", lambda: self._window_click(*OK) or True),
        ]
        for label, fn in steps:
            if not self._confirm(label):
                return "cancelled"
            if not fn():
                return "error"
            self._wait()
        return gw.identify(self._session) or "unknown"

    def _open_igg_browser(self) -> bool:
        # on change_account state 2, IGG icon at (735,262) window-relative
        self._window_click(735, 262)
        self._wait(6)
        return True

    def _submit_login(self) -> bool:
        self._window_click(*LOGIN_BTN)
        self._wait(5)
        return True

    def _select_id(self) -> bool:
        self._window_click(*SELECT_ID)
        self._wait(5)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_login_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gt_spector/login_flow.py tests/test_login_flow.py
git commit -m "feat: LoginFlow module for IGG account switching"
```

---

### Task 4: CLI command `change-account`

**Files:**
- Modify: `viewer/cli.py` (CliSession, near `do_type` ~line 249)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `LoginFlow` (Task 3); `BotManager` for prefix-from-display.
- Produces: `CliSession.do_change_account(self, arg)` command.

- [ ] **Step 1: Write the failing test**

```python
def test_do_change_account_wires_flow(monkeypatch):
    from viewer import cli as cli_mod

    calls = {}
    class FakeFlow:
        def __init__(self, *a, **k):
            calls["kwargs"] = k
        def change_account(self, email, password):
            calls["account"] = (email, password)
            return "shelter_view"

    monkeypatch.setattr(cli_mod, "LoginFlow", FakeFlow)
    s = object.__new__(cli_mod.CliSession)
    s._session = type("S", (), {"display": ":13"})()
    s._display = 13
    s._gw = object()
    s._locator = object()
    monkeypatch.setattr(s, "_bot_prefix", lambda: "/home/swong/dls/wineprefix_bots/bot04")
    s.do_change_account("sr02-07@mx1.us bamboo-H4")
    assert calls["account"] == ("sr02-07@mx1.us", "bamboo-H4")
    assert "confirm" in calls["kwargs"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_do_change_account_wires_flow -v`
Expected: FAIL (no `do_change_account`, or no `LoginFlow` imported)

- [ ] **Step 3: Implement the command**

In `viewer/cli.py`:

- Add imports at top: `from gt_spector.login_flow import LoginFlow` and `from gt_spector.bot_manager import BotManager`.
- Add a helper to resolve the bot prefix from this display:

```python
    def _bot_prefix(self) -> str:
        m = BotManager()
        m.load_from_prefixes()
        for b in m.bots:
            if b.display == self._display:
                return b.prefix
        raise RuntimeError(f"no bot for display :{self._display}")
```

- Add the command method:

```python
    def do_change_account(self, arg: str) -> None:
        """change-account <email> [password] — log this bot into an IGG account.

        Drives the full embedded-browser login flow, pausing to confirm each
        step. Password defaults to the farm default if not given.
        """
        args = shlex.split(arg)
        if not args:
            print("Usage: change-account <email> [password]")
            return
        email = args[0]
        password = args[1] if len(args) > 1 else "bamboo-H4"

        def confirm(msg: str) -> bool:
            ans = input(f"  [confirm] {msg}? [y/N] ").strip().lower()
            return ans in ("y", "yes")

        try:
            prefix = self._bot_prefix()
        except RuntimeError as e:
            print(f"error: {e}")
            return
        flow = LoginFlow(
            self._session, self._gw, self._locator,
            prefix, f":{self._display}", confirm=confirm,
        )
        result = flow.change_account(email, password)
        print(f"change-account result: {result}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_do_change_account_wires_flow -v`
Expected: PASS

- [ ] **Step 5: Full suite + lint**

Run: `pytest tests/ -q`
Expected: 2 known env failures only.
Run: `ruff check viewer/cli.py gt_spector/login_flow.py gt_spector/typing.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add viewer/cli.py tests/test_cli.py
git commit -m "feat: change-account CLI command"
```

---

### Task 5: Agent-facing documentation

**Files:**
- Modify: `docs/cli.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add the Change Account section to docs/cli.md**

Append after the "Standard Bot Configuration" section:

```markdown
## Change Account

Switch a bot to a specific IGG account via the embedded browser login.

  python -m gt_spector --session :<display> --cli
  > change-account sr02-07@mx1.us

The command walks the full login flow: Settings -> Account -> Change Account
-> IGG Account -> browser login form. It pauses at each step and asks you to
confirm the screen before continuing. Type the password when prompted, or
pass it as the second argument.

Relies on deterministic template identification (no VLM) and the
sendtext.exe Wine helper for reliable typing of '@' and uppercase.
Account passwords are in /home/swong/dls/src/ahk/accounts
(email:password per line).
```

- [ ] **Step 2: Add a note to AGENTS.md**

Under the "CLI navigation" section, add:

```markdown
To switch a bot's IGG account:
`change-account <email> [password]` in the CLI (see docs/cli.md "Change Account").
```

- [ ] **Step 3: Commit**

```bash
git add docs/cli.md AGENTS.md
git commit -m "docs: change-account usage for agents"
```
