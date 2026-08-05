# Console Full Provisioning (Provision + Start + Login) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the console's provision flow fully provision a bot: create the prefix (`provision init`), start the game, wait for boot, and run the IGG login (`expired_login` with auto-confirm) — reporting each stage's progress.

**Architecture:** `_provision_n`'s worker, after a successful `provision init`, starts the bot via `BotManager.start_game`, polls until the game reaches the expired-session/login screen, then calls `gt_spector.login_flow.expired_login(email, password, session, gw, locator, prefix, display)` with the default auto-confirm. Status bar updates each stage via `_tk.after`.

**Tech Stack:** Python, `viewer/bot_console.py`, `gt_spector/bot_manager.py` (`BotManager.start_game`), `gt_spector/login_flow.py` (`expired_login`), `gt_spector/session.py` (`Session`), `GameWorld`/`Locator`.

## Global Constraints

- After `provision init` succeeds, the flow: `start_game(bot)` → wait for boot (poll `identify` until a login-ish screen: `startup_expired`, `game_login`, `igg_login`, `another_login_disconnect`, or `in_game` if already logged in) → `expired_login(email, password, ...)` with auto-confirm (default).
- Account password: read from the accounts file (`email:password`). The `_provision_n` worker has the `email`; extract the password from `ACCOUNTS_FILE` line matching the email.
- The login runs on the SAME background thread as provisioning (sequential, one bot at a time). All UI updates via `_tk.after`.
- On login success (final identify is an in-game screen), report "botX: logged in"; on failure, report "botX: login failed (<result>)" and stop.
- Timeouts: provision `timeout=600`, boot-wait bounded (e.g. up to ~120s), login bounded by its internal 20-iteration loop.
- The helpbot is NOT started automatically (out of scope for this change).
- Existing `_provision_n` unit tests must be updated (provisioning now also starts + logs in); tests mock the new dependencies (BotManager.start_game, expired_login, sleep).

---
### Task 1: Full provisioning (provision + start + login)

**Files:**
- Modify: `viewer/bot_console.py` (`_provision_n`, add `_boot_and_login`, `_login_password`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_unprovisioned_accounts()` (returns `(name, email)`), `ACCOUNTS_FILE`, `BotManager.start_game`, `gt_spector.login_flow.expired_login`, `Session`, `GameWorld`/`Locator`.
- Produces: `_provision_n(count)` provisions, starts, and logs in each of the first `count` unprovisioned bots. Helpers `_login_password(email) -> str` and `_boot_and_login(bot, email, password) -> str` (returns final screen name).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_provision_n_starts_and_logs_in_after_init(monkeypatch):
    import sys

    from viewer import bot_console as bc

    c = make_console()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(("run", cmd[0], cmd[cmd.index("init") + 1]))
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(bc.subprocess, "run", fake_run)
    c._unprovisioned_accounts = lambda: [("bot09", "sr02-12@mx1.us")]
    c._login_password = lambda email: "bamboo-H4"
    bot_obj = type("B", (), {"name": "bot09", "display": 18})()
    c._manager = type("M", (), {
        "get": lambda self, n: bot_obj,
        "start_game": lambda self, b: calls.append(("start", b.name)),
    })()
    c._boot_and_login = lambda bot, email, password: (
        calls.append(("login", bot.name, email, password)) or "shelter_view")
    c._refresh_bots = lambda: None
    c._status = type("S", (), {"config": lambda s, **k: None})()
    c._tk = type("Tk", (), {"after": lambda s, ms, fn: None})()

    c._provision_n(1)
    time.sleep(0.2)
    assert ("run", bc.sys.executable, "bot09") in calls
    assert ("start", "bot09") in calls
    assert ("login", "bot09", "sr02-12@mx1.us", "bamboo-H4") in calls


def test_login_password_reads_accounts_file(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    acct = tmp_path / "accounts"
    acct.write_text("sr02-12@mx1.us:bamboo-H4\nother@x:pw2\n")
    monkeypatch.setattr(bc, "ACCOUNTS_FILE", acct)
    assert bc.BotConsole._login_password(None, "sr02-12@mx1.us") == "bamboo-H4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_provision_n_starts_and_logs_in_after_init tests/test_bot_console.py::test_login_password_reads_accounts_file -v`
Expected: FAIL — `_login_password` doesn't exist; `_provision_n` doesn't start/login.

- [ ] **Step 3: Implement**

Add a module-level import at the top of `viewer/bot_console.py` (near the existing imports):

```python
from gt_spector import login_flow
```

Add helpers and rewrite `_provision_n`'s worker:

```python
    def _login_password(self, email: str) -> str:
        """Password for an account email from the accounts file."""
        try:
            for line in ACCOUNTS_FILE.read_text().splitlines():
                if line.startswith(email + ":"):
                    return line.split(":", 1)[1].strip()
        except (FileNotFoundError, OSError):
            pass
        return ""

    def _boot_and_login(self, bot, email: str, password: str) -> str:
        """Start the bot, wait for boot, and log it in. Returns final screen."""
        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator
        from gt_spector.session import Session

        gw = GameWorld()
        locator = Locator()
        gw.set_locator(locator)
        self._manager.start_game(bot)

        import time as _t
        session = Session(f":{bot.display}", source=f"shm://{bot.display}")
        boot_deadline = _t.monotonic() + 120
        screen = None
        while _t.monotonic() < boot_deadline:
            _t.sleep(3)
            try:
                session.refresh()
                screen = gw.identify(session)
            except Exception:  # noqa: BLE001 - boot in progress
                screen = None
            if screen in ("startup_expired", "game_login", "igg_login",
                          "another_login_disconnect") or screen is not None:
                break
        if screen is None:
            return "error: no login screen after boot"
        return login_flow.expired_login(
            email, password, session, gw, locator,
            bot.prefix, f":{bot.display}",
        )
```

Note: `expired_login` default `confirm` is auto-True, so it runs non-interactively. `bot.prefix` is the Wine prefix path; `session`/`gw`/`locator` are fresh per bot. The boot-wait breaks when the screen is a known login screen OR any non-None screen (some boots land directly in-game; `expired_login`/the state machine handles that by returning `in_game`).

Rewrite `_provision_n`'s `worker`:

```python
        def worker() -> None:
            for name, email in pending:
                _set_status(f"Provisioning {name} ({email})...")
                try:
                    r = subprocess.run(
                        [sys.executable, "-m", "gt_spector.provision", "init",
                         name, "--account", email],
                        capture_output=True, text=True, timeout=600, check=False)
                except (OSError, subprocess.TimeoutExpired) as e:
                    _set_status(f"{name}: FAILED ({e})")
                    return
                if r.returncode != 0:
                    tail = (r.stderr or r.stdout or "").strip()[-60:]
                    _set_status(f"{name}: FAILED ({tail})")
                    return
                _set_status(f"{name}: provisioned, starting...")
                bot = self._manager.get(name)
                if bot is None:
                    _set_status(f"{name}: FAILED (no bot)")
                    return
                password = self._login_password(email)
                result = self._boot_and_login(bot, email, password)
                if result in ("in_game", "shelter_view", "world_map",
                              "start_norah", "glory_league_event", None):
                    _set_status(f"{name}: logged in")
                else:
                    _set_status(f"{name}: login failed ({result})")
                    return
            self._tk.after(0, self._refresh_bots)
            _set_status(f"Provisioned {len(pending)} bot(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_console.py::test_provision_n_starts_and_logs_in_after_init tests/test_bot_console.py::test_login_password_reads_accounts_file -v`
Expected: PASS.

Note: the pre-existing `test_provision_n_sequential_and_stops_on_failure` and the other `_provision_n` tests stub `_unprovisioned_accounts` and mock `subprocess.run` — they now need `_login_password` and `_boot_and_login` stubbed too (or `_provision_n` will try to start/login). Update them: add `c._login_password = lambda email: "pw"` and `c._boot_and_login = lambda bot, email, password: "shelter_view"` to each. Preserve their original assertions.

- [ ] **Step 5: Run the full console suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS.

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: console provisioning starts and logs in each bot"
```

---
### Task 2: Live verification

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the feature from Task 1.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures (test_shm_screen, test_input_interactive).

- [ ] **Step 2: Verify login works programmatically**

Run the same `expired_login` the console will call, against a freshly provisioned bot, and confirm it reaches an in-game screen. (This is the previously verified `expired_login` path.)

- [ ] **Step 3: Live provision 1 bot through the console**

Launch the console, open Provision, select 1, Provision. Confirm status shows: "Provisioning bot10...", "provisioned, starting...", and then either "logged in" or a login-failure message.

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from full-provision verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
