# Bot State Detection Fix (Require Game Process) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `BotManager._refresh_state` so a bot is only reported RUNNING when its actual game process exists — a live Xvfb alone must not imply RUNNING.

**Architecture:** Remove the `bot.xvfb_pid and self._pid_alive(bot.xvfb_pid)` branch from `_refresh_state` (or demote it). RUNNING requires either a live `bot.pid` (the start.exe wrapper) or a detected `Doomsday.exe` via `_find_game_pid`. A live Xvfb with no game → STARTING or OFFLINE, so the console lets the user start/stop the bot again.

**Tech Stack:** Python, `gt_spector/bot_manager.py`, `BotState`.

## Global Constraints

- `_refresh_state` returns RUNNING only when: (a) `bot.pid` is alive, or (b) `_find_game_pid(bot)` returns a pid. A live `bot.xvfb_pid` alone must NOT yield RUNNING.
- A live Xvfb with no game → the bot is STARTING (if a start was recently attempted) or OFFLINE. Concretely: if `bot.xvfb_pid` is alive but no game, report STARTING (so the console shows it as transitional and allows restart), and clear `bot.pid`.
- `start_game` must still set `bot.xvfb_pid` and `bot.pid` as today.
- `stop_game` must clean up the game AND the Xvfb (kill `bot.xvfb_pid`) so a stopped bot has neither — preventing the stale-Xvfb scenario.
- Existing tests updated; new tests cover the stale-Xvfb case (Xvfb alive, no game → not RUNNING).

---
### Task 1: _refresh_state requires the game process

**Files:**
- Modify: `gt_spector/bot_manager.py` (`_refresh_state`)
- Test: `tests/test_bot_manager.py`

**Interfaces:**
- Consumes: `bot.pid`, `_pid_alive`, `_find_game_pid`, `bot.xvfb_pid`.
- Produces: `_refresh_state(bot)` — RUNNING only with a live game (bot.pid or _find_game_pid); Xvfb-only → STARTING.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_manager.py`:

```python
def test_refresh_state_not_running_when_only_xvfb_alive(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager, BotState

    m = BotManager()
    bot = Bot(name="bot10", xvfb_pid=99999)  # fake alive xvfb

    def fake_find_game_pid(b):
        return None  # no game process

    monkeypatch.setattr(m, "_find_game_pid", fake_find_game_pid)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: True)  # xvfb "alive"

    m._refresh_state(bot)
    # Xvfb alive but no game -> NOT Running (STARTING or OFFLINE)
    assert bot.state != BotState.RUNNING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_manager.py::test_refresh_state_not_running_when_only_xvfb_alive -v`
Expected: FAIL — state is RUNNING (the xvfb branch fires).

- [ ] **Step 3: Implement**

Modify `_refresh_state` in `gt_spector/bot_manager.py`:

```python
    def _refresh_state(self, bot: Bot) -> None:
        if bot.state == BotState.ERROR:
            return
        if bot.pid and self._pid_alive(bot.pid):
            bot.state = BotState.RUNNING
            return
        game_pid = self._find_game_pid(bot)
        if game_pid is not None:
            bot.pid = game_pid
            bot.state = BotState.RUNNING
            return
        if bot.xvfb_pid and self._pid_alive(bot.xvfb_pid):
            # Xvfb alone is not a running game; the game may have crashed
            # or exited after the display started. Report transitional so the
            # console allows a start/stop.
            bot.state = BotState.STARTING
            return
        bot.state = BotState.OFFLINE
        bot.pid = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_manager.py::test_refresh_state_not_running_when_only_xvfb_alive -v`
Expected: PASS.

- [ ] **Step 5: Check for other tests relying on the old xvfb-RUNNING behavior**

Run: `grep -rn "xvfb_pid" tests/test_bot_manager.py tests/test_bot_console.py`
If any test asserts `bot.xvfb_pid` → RUNNING, update it to expect STARTING.

- [ ] **Step 6: Run the full test suite + lint**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures (test_shm_screen, test_input_interactive).

Run: `ruff check gt_spector/bot_manager.py tests/test_bot_manager.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add gt_spector/bot_manager.py tests/test_bot_manager.py
git commit -m "fix: bot not RUNNING when only Xvfb is alive (require game process)"
```

---
### Task 2: stop_game cleans up Xvfb

**Files:**
- Modify: `gt_spector/bot_manager.py` (`stop_game`)
- Test: `tests/test_bot_manager.py`

**Interfaces:**
- Consumes: `bot.xvfb_pid`, `_find_game_pids_by_display`, `_pid_alive`.
- Produces: `stop_game` kills the game AND the bot's Xvfb (if `bot.xvfb_pid` is set and alive), preventing stale-Xvfb false-running.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_manager.py`:

```python
def test_stop_game_kills_xvfb(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager

    m = BotManager()
    bot = Bot(name="bot10", xvfb_pid=12345, display=19)
    killed = []

    def fake_find_game_pids_by_display(display):
        return []

    def fake_pid_alive(pid):
        return True

    def fake_killpg(pgid, sig):
        killed.append(pgid)

    monkeypatch.setattr(m, "_find_game_pids_by_display", fake_find_game_pids_by_display)
    monkeypatch.setattr(m, "_pid_alive", fake_pid_alive)
    monkeypatch.setattr("gt_spector.bot_manager.os.killpg", fake_killpg)

    m.stop_game(bot)
    # the xvfb_pid must have been killed
    assert 12345 in killed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_manager.py::test_stop_game_kills_xvfb -v`
Expected: FAIL — `stop_game` does not kill `bot.xvfb_pid`.

- [ ] **Step 3: Implement**

Modify `stop_game` in `gt_spector/bot_manager.py` to kill the bot's Xvfb after killing the game:

```python
    def stop_game(self, bot: Bot) -> None:
        """Kill every Doomsday.exe on the bot's display, then its Xvfb."""
        if bot.pid and self._pid_alive(bot.pid):
            os.killpg(os.getpgid(bot.pid), signal.SIGTERM)
            time.sleep(1)
        for pid in self._find_game_pids_by_display(bot.display):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        time.sleep(2)
        for pid in self._find_game_pids_by_display(bot.display):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        if bot.pid and self._pid_alive(bot.pid):
            os.killpg(os.getpgid(bot.pid), signal.SIGKILL)
        # Clean up the display so a stale Xvfb can't look like a running game.
        if bot.xvfb_pid and self._pid_alive(bot.xvfb_pid):
            try:
                os.killpg(os.getpgid(bot.xvfb_pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            bot.xvfb_pid = None
        bot.pid = None
        bot.state = BotState.OFFLINE
```

(Note: `start_xvfb` uses `start_new_session=True`, so `os.killpg(os.getpgid(bot.xvfb_pid), ...)` is the right kill. Verify against the existing pattern.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_manager.py::test_stop_game_kills_xvfb -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite + lint**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures.

Run: `ruff check gt_spector/bot_manager.py tests/test_bot_manager.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add gt_spector/bot_manager.py tests/test_bot_manager.py
git commit -m "fix: stop_game cleans up the bot's Xvfb display"
```

---
### Task 3: Live verification on bot10

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the features from Tasks 1-2.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures.

- [ ] **Step 2: Kill the stale bot10 Xvfb and confirm BotManager reports Offline**

The current stale Xvfb :19 (PID 1609752) exists. After the fix, `_refresh_state(bot10)` with that xvfb_pid but no game should report STARTING (not RUNNING). Verify:
`python3 -c "from gt_spector.bot_manager import BotManager; m=BotManager(); m.load_from_prefixes(); b=m.get('bot10'); b.xvfb_pid=1609752; m._refresh_state(b); print(b.state.value)"`
Expected: Starting (not Running).

- [ ] **Step 3: Stop the stale Xvfb, then start bot10 cleanly**

Kill the leftover Xvfb (or rely on `start_xvfb`'s fuser cleanup), then `python3 -m gt_spector start bot10`. Confirm it reaches Running with a real game process.

- [ ] **Step 4: Run the expired-login script on bot10**

The user unlinked bot10's account, so it should boot to expired-session. Run `expired_login sr02-13@mx1.us` via the CLI and confirm the login completes (or capture where it fails — the user wants to see what broke).

- [ ] **Step 5: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from bot state verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
