# Console Background Monitor Thread Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bot console UI responsive by moving the blocking `_monitor_tick` (0.4s/bot responsiveness sleep) off the Tk main thread onto a background daemon thread.

**Architecture:** `_poll` (the 2s Tk callback) keeps only the quick `_update_rows()` (frame reads + row refresh, ~0.5s). A new background worker thread runs `_monitor_tick()` on its own cadence (default every 2s), so the 3.2s of responsiveness sleeps no longer freeze the UI.

**Tech Stack:** Python, tkinter, `threading` (daemon thread, same pattern as the existing `_start_vlm_worker`).

## Global Constraints

- `_poll` must NOT call `_monitor_tick()` — only `_update_rows()` and the `after(2000, self._poll)` reschedule.
- A background daemon thread runs `_monitor_tick()` in a loop with a configurable interval (default 2.0s).
- The worker thread is a daemon (does not block exit) and stops when the console closes (`_vlm_stop` pattern or a dedicated stop flag).
- `_monitor_one`/`_monitor_tick` logic is unchanged — only its invocation moves off the UI thread.
- The monitor worker must not start before `self._runners`/`self._frames` exist (start it at the end of `__init__`, after `_setup_bot_list`/`_build_rows`).
- Thread-safety: the worker reads `self._frames` (written by `_update_rows` on the UI thread) and mutates `bot.state` / `_runners` — the same shared state the existing VLM worker already reads concurrently; no new locking is required (consistent with existing design), but note the VLM worker already reads `self._frames` concurrently (precedent).

---
### Task 1: Background monitor thread

**Files:**
- Modify: `viewer/bot_console.py` (`__init__`, `_poll`, add `_start_monitor_worker`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_monitor_tick()`, `self._tk`, `settings.vlm_interval` (or a new `MONITOR_INTERVAL`).
- Produces: `_start_monitor_worker() -> None` — starts the daemon thread; `_poll` no longer calls `_monitor_tick()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_poll_does_not_run_monitor_tick(monkeypatch):
    """The UI poll must not block on the monitor (it runs on a background thread)."""
    c = make_console()
    c._nav_cache = None
    calls = []
    c._update_rows = lambda: calls.append("rows")
    c._tk = type("Tk", (), {"after": lambda self, ms, fn: None})()
    c._monitor_tick = lambda: calls.append("tick")
    c._poll()
    assert calls == ["rows"]  # tick must NOT be called from the UI poll
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_poll_does_not_run_monitor_tick -v`
Expected: FAIL — `calls == ["rows", "tick"]` (monitor_tick currently runs in `_poll`).

- [ ] **Step 3: Implement**

Add a module constant near the top (after `PREFIXES_DIR`):

```python
MONITOR_INTERVAL = 2.0
```

Add to `BotConsole.__init__` (after `self._setup_bot_list()` and `self._build_rows()`, before `self._poll()`):

```python
        self._build_rows()
        self._start_monitor_worker()
        self._poll()
```

Add the worker method (near `_start_vlm_worker`):

```python
    def _start_monitor_worker(self) -> None:
        """Background daemon thread running the monitor tick.

        check_responsiveness sleeps ~0.4s per running bot (sampling SHM
        counters), which would freeze the Tk UI if run on the main thread.
        Run it on a daemon thread so the UI poll only does the quick row
        update. Stops when the console closes (via _vlm_stop).
        """
        import threading

        def worker() -> None:
            while not self._vlm_stop:
                time.sleep(MONITOR_INTERVAL)
                try:
                    self._monitor_tick()
                except Exception as e:  # noqa: BLE001 - never kill the worker
                    logs.log_system(f"monitor worker error: {e}")

        threading.Thread(target=worker, daemon=True).start()
```

Change `_poll`:

```python
    def _poll(self) -> None:
        self._nav_cache = None
        self._update_rows()
        self._tk.after(2000, self._poll)
```

Note: `_on_close` already sets `self._vlm_stop = True`; add `self._vlm_stop = False` in `__init__` if it is not already set before `_start_monitor_worker` is called (check — it is set in `__init__` at line ~68). Verify the existing `_vlm_stop` attribute is initialized before the worker starts.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_poll_does_not_run_monitor_tick -v`
Expected: PASS.

- [ ] **Step 5: Run the full console test suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS (all existing monitor_tick tests still pass since `_monitor_tick` itself is unchanged).

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "perf: run console monitor tick on a background thread (UI no longer blocks)"
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

- [ ] **Step 2: Confirm the console process no longer pegs a thread in sleeps**

Launch the console with a display, let it run ~30s, then check:
`ps -p <console-pid> -L -o pid,tid,pcpu,comm | sort -k3 -nr | head -5`
Expected: the Tk main thread is low CPU; the monitor thread may show CPU but the UI stays responsive (user can move/click the window).

- [ ] **Step 3: Confirm monitoring still works**

Verify a bot crash/restart is still detected (the background worker runs `_monitor_tick` unchanged). If a bot is non-responsive, the log should show the recovery message as before.

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from monitor thread verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
