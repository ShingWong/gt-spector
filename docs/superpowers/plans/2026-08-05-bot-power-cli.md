# Bot Power CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `start`/`stop`/`restart` subcommands to `python -m gt_spector` so agents can power bots on/off/all, reusing `BotManager`.

**Architecture:** A new `gt_spector/power.py` module exposes `run_power_command(manager, action, target) -> int` (testable with a fake manager). `__main__.py` gains a thin dispatch that handles the new subcommands before the existing argparse flags. It reuses `BotManager.start_game`/`stop_game`/`restart_game`, then reports each bot's state via `_refresh_state`.

**Tech Stack:** Python, existing `BotManager`/`Bot`/`BotState` in `gt_spector/bot_manager.py`.

## Global Constraints

- Bots discovered via `BotManager.load_from_prefixes()` from `wineprefix_bots/` (BASE_DIR).
- Actions: `start`, `stop`, `restart`. Target: `all` or a bot name (e.g. `bot07`).
- Aliases `start_all` / `stop_all` / `restart_all` are equivalent to `start all` etc.
- `start` and `restart` do a short fixed wait (~5s) after launching, then report state via `_refresh_state`. No long polling.
- Unknown bot name → print error to stderr, exit 1.
- Errors from `start_game`/`stop_game` (`RuntimeError`, `OSError`) → print message, exit 1.
- Exit 0 on success.
- No real wine/Xvfb in unit tests.

---
### Task 1: power.py with run_power_command

**Files:**
- Create: `gt_spector/power.py`
- Test: `tests/test_power.py`

**Interfaces:**
- Consumes: `BotManager` (`.bots: list[Bot]`, `.get(name) -> Bot | None`, `.start_game(bot)`, `.stop_game(bot)`, `.restart_game(bot)`, `._refresh_state(bot)`), `Bot.state`, `BotState` (from `gt_spector.bot_manager`).
- Produces: `run_power_command(manager, action: str, target: str) -> int` — the exit code for the CLI. Later tasks and `__main__.py` depend on this exact signature.

- [ ] **Step 1: Write the failing test**

Create `tests/test_power.py`:

```python
import sys

from gt_spector.power import run_power_command


class _Bot:
    def __init__(self, name, state):
        self.name = name
        self.state = state
        self.started = 0
        self.stopped = 0


class _FakeManager:
    def __init__(self, bots):
        self.bots = bots

    def get(self, name):
        for b in self.bots:
            if b.name == name:
                return b
        return None

    def start_game(self, bot):
        bot.started += 1
        bot.state = "Running"

    def stop_game(self, bot):
        bot.stopped += 1
        bot.state = "Offline"

    def restart_game(self, bot):
        bot.stopped += 1
        bot.started += 1
        bot.state = "Running"

    def _refresh_state(self, bot):
        return bot.state


def test_start_unknown_bot_returns_1(capsys):
    m = _FakeManager([])
    assert run_power_command(m, "start", "bot99") == 1
    assert "bot99" in capsys.readouterr().err


def test_start_single_bot(capsys):
    b = _Bot("bot07", "Offline")
    m = _FakeManager([b])
    assert run_power_command(m, "start", "bot07") == 0
    assert b.started == 1
    assert "Running" in capsys.readouterr().out


def test_stop_single_bot(capsys):
    b = _Bot("bot07", "Running")
    m = _FakeManager([b])
    assert run_power_command(m, "stop", "bot07") == 0
    assert b.stopped == 1
    assert "Offline" in capsys.readouterr().out


def test_restart_single_bot():
    b = _Bot("bot07", "Offline")
    m = _FakeManager([b])
    assert run_power_command(m, "restart", "bot07") == 0
    assert b.stopped == 1 and b.started == 1


def test_all_target_acts_on_every_bot(capsys):
    b1 = _Bot("bot01", "Offline")
    b2 = _Bot("bot02", "Offline")
    m = _FakeManager([b1, b2])
    assert run_power_command(m, "start", "all") == 0
    assert b1.started == 1 and b2.started == 1


def test_all_target_one_failure_returns_1(capsys):
    b1 = _Bot("bot01", "Offline")
    m = _FakeManager([b1])
    orig = m.start_game

    def boom(bot):
        raise RuntimeError("xvfb failed")
    m.start_game = boom

    assert run_power_command(m, "start", "all") == 1
    assert "bot01" in capsys.readouterr().err


def test_invalid_action_returns_2():
    m = _FakeManager([])
    assert run_power_command(m, "fly", "all") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_power.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gt_spector.power'`

- [ ] **Step 3: Write minimal implementation**

Create `gt_spector/power.py`:

```python
"""Bot power CLI: start/stop/restart bots via BotManager."""

from __future__ import annotations

import time
from typing import Any

from gt_spector.bot_manager import BotManager

ACTIONS = ("start", "stop", "restart")
START_WAIT = 5.0


def run_power_command(manager: BotManager, action: str, target: str) -> int:
    """Run start/stop/restart on a bot or all bots. Returns the exit code."""
    if action not in ACTIONS:
        print(f"error: unknown action '{action}'", file=__import__("sys").stderr)
        return 2
    targets = list(manager.bots) if target == "all" else [manager.get(target)]
    if targets[0] is None:
        print(f"error: unknown bot '{target}'", file=__import__("sys").stderr)
        return 1
    failed = False
    for bot in targets:
        if bot is None:
            continue
        try:
            _do(manager, action, bot)
        except (OSError, RuntimeError) as e:
            print(f"error: {bot.name}: {e}", file=__import__("sys").stderr)
            failed = True
            continue
        print(f"{bot.name}: {_state(manager, bot, action)}")
    return 1 if failed else 0


def _do(manager: BotManager, action: str, bot: Any) -> None:
    if action == "start":
        manager.start_game(bot)
    elif action == "stop":
        manager.stop_game(bot)
    else:
        manager.restart_game(bot)


def _state(manager: BotManager, bot: Any, action: str) -> str:
    if action in ("start", "restart"):
        time.sleep(START_WAIT)
    manager._refresh_state(bot)
    return bot.state.value if hasattr(bot.state, "value") else str(bot.state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_power.py -v`
Expected: PASS (7 tests). Note: `test_start_single_bot` waits 5s via `time.sleep(START_WAIT)`.

- [ ] **Step 5: Fix test speed (mock sleep)**

Patch `tests/test_power.py` to inject a short wait and add a module-level constant the tests can patch:

```python
import gt_spector.power as P
```

Then at the top of each of `test_start_single_bot`, `test_restart_single_bot`, `test_all_target_acts_on_every_bot`, `test_all_target_one_failure_returns_1`, `test_stop_single_bot` add `P.START_WAIT = 0` after the imports (set inside each test before calling, or via `monkeypatch`). Use `monkeypatch`:

```python
def test_start_single_bot(capsys, monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    ...
```

Apply `monkeypatch.setattr(P, "START_WAIT", 0)` to every test that triggers a start/restart (not `test_start_unknown_bot_returns_1` or `test_invalid_action_returns_2`).

Run: `pytest tests/test_power.py -v`
Expected: PASS fast (no 5s sleeps).

- [ ] **Step 6: Commit**

```bash
git add gt_spector/power.py tests/test_power.py
git commit -m "feat: bot power CLI core (start/stop/restart)"
```

---
### Task 2: Wire subcommands into __main__.py

**Files:**
- Modify: `gt_spector/__main__.py` (add dispatch before the argparse section)
- Test: `tests/test_main_power.py`

**Interfaces:**
- Consumes: `run_power_command(manager, action, target) -> int` from `gt_spector.power` (Task 1), `BotManager`.
- Produces: nothing for later tasks (terminal wiring).

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_power.py`:

```python
import sys

from gt_spector import __main__ as M


def _fake_manager():
    class _Bot:
        def __init__(self, name):
            self.name = name
            self.state = "Offline"
            self.started = 0
            self.stopped = 0

    class _Manager:
        def __init__(self):
            self.bots = [_Bot("bot01"), _Bot("bot02")]

        def get(self, name):
            return next((b for b in self.bots if b.name == name), None)

        def start_game(self, bot):
            bot.started += 1
            bot.state = "Running"

        def stop_game(self, bot):
            bot.stopped += 1
            bot.state = "Offline"

        def restart_game(self, bot):
            bot.stopped += 1
            bot.started += 1
            bot.state = "Running"

        def _refresh_state(self, bot):
            return bot.state

    return _Manager()


def test_parse_power_args_basic():
    action, target = M._parse_power_args(["start", "bot01"])
    assert (action, target) == ("start", "bot01")


def test_parse_power_args_all_aliases():
    assert M._parse_power_args(["start_all"]) == ("start", "all")
    assert M._parse_power_args(["stop_all"]) == ("stop", "all")
    assert M._parse_power_args(["restart_all"]) == ("restart", "all")


def test_parse_power_args_no_target():
    assert M._parse_power_args(["start"]) is None


def test_parse_power_args_unknown():
    assert M._parse_power_args(["launch", "bot01"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_power.py -v`
Expected: FAIL — `AttributeError: module 'gt_spector.__main__' has no attribute '_parse_power_args'`

- [ ] **Step 3: Implement dispatch in __main__.py**

Add near the top of `main()` (after the `--list-sessions` block, before `parser = argparse.ArgumentParser(...)`), a subcommand check:

```python
POWER_ACTIONS = {"start", "stop", "restart", "start_all", "stop_all", "restart_all"}


def _parse_power_args(argv: list[str]) -> tuple[str, str] | None:
    """Return (action, target) for power subcommands, else None."""
    if len(argv) < 2:
        return None
    token = argv[1]
    if token in ("start_all", "stop_all", "restart_all"):
        return (token[:-4], "all")
    if token in ("start", "stop", "restart"):
        if len(argv) < 3:
            return None
        return (token, argv[2])
    return None
```

In `main()`:

```python
def main() -> None:
    from .session import Session

    if "--list-sessions" in sys.argv:
        ...

    power = _parse_power_args(sys.argv)
    if power is not None:
        from gt_spector.bot_manager import BotManager
        from gt_spector.power import run_power_command

        manager = BotManager()
        manager.load_from_prefixes()
        action, target = power
        sys.exit(run_power_command(manager, action, target))

    parser = argparse.ArgumentParser(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_power.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add gt_spector/__main__.py tests/test_main_power.py
git commit -m "feat: wire bot power subcommands into the CLI entrypoint"
```

---
### Task 3: Documentation

**Files:**
- Modify: `docs/cli.md` (add a "Bot Power" section)
- Modify: `AGENTS.md` (add power commands to the agent-facing CLI docs)

**Interfaces:**
- Consumes: the commands defined in Tasks 1-2.

- [ ] **Step 1: Add documentation**

Append a "## Bot Power" section to `docs/cli.md` after the "Change Account" section:

```markdown
## Bot Power

Start, stop, or restart bots (individual or all) from the command line for
agentic/scripted use. Reuses the same BotManager the console's Start/Stop
buttons use.

  python -m gt_spector start bot07
  python -m gt_spector start all
  python -m gt_spector stop bot07
  python -m gt_spector stop all
  python -m gt_spector restart bot07
  python -m gt_spector restart all

`start_all`, `stop_all`, and `restart_all` are aliases for the `all` forms.

`start`/`restart` wait a few seconds after launching, then report the bot's
state (Running/Starting/Offline). `stop` reports Offline once killed.
Unknown bot names or launch failures exit non-zero.
```

Update `AGENTS.md` — in the "CLI navigation" section, after the `change_account`
line, add:

```markdown
To power bots on/off/all without the GUI console (agentic use):
`python -m gt_spector start bot07`, `stop bot07`, `restart bot07`,
or `start all` / `stop all` / `restart all` (aliases `start_all` etc.).
```

- [ ] **Step 2: Verify docs render**

Run: `grep -A2 "## Bot Power" docs/cli.md && grep -n "power bots" AGENTS.md`
Expected: the new section and line are present.

- [ ] **Step 3: Commit**

```bash
git add docs/cli.md AGENTS.md
git commit -m "docs: bot power CLI commands"
```

---
### Task 4: Manual verification on bot07

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the CLI from Tasks 1-3.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/test_power.py tests/test_main_power.py -q`
Expected: PASS.

Run: `ruff check gt_spector/power.py gt_spector/__main__.py tests/test_power.py tests/test_main_power.py`
Expected: no errors (ruff auto-fix if only import-sort issues: `ruff check --fix`).

- [ ] **Step 2: Start bot07**

Run: `python -m gt_spector start bot07`
Expected: exit 0, prints `bot07: Running` (or Starting/Offline). Verify a game process appears: `ps aux | grep Doomsday.exe | grep -i "DISPLAY=:16"` (bot07 → display :16).

- [ ] **Step 3: Test expired login on bot07 (smoke)**

Run: `DISPLAY=:16 python -m gt_spector --session :16 --cli` then at the prompt `expired_login sr02-09@mx1.us` with confirm prompts answered `y`.
Expected: navigates the expired-session → game login → IGG browser → types credentials → logged in.

- [ ] **Step 4: Stop bot07**

Run: `python -m gt_spector stop bot07`
Expected: exit 0, prints `bot07: Offline`. Verify the game process is gone: `ps aux | grep Doomsday.exe | grep -i "DISPLAY=:16"` → no output.

- [ ] **Step 5: Commit any docs/driven fixes from verification**

```bash
git add -u
git commit -m "fix: adjustments from bot07 power CLI verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
