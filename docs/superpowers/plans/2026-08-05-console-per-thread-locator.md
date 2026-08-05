# Console Per-Thread Locator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the shared-mutable-Locator race between the console's UI thread and the background monitor worker, which makes `_update_rows` (and bot selection) ~3x slower (~4s).

**Architecture:** The monitor worker thread gets its OWN `GameWorld` + `Locator` (fresh per worker), and `_detect_location` accepts an optional `gw`/`locator` so the worker passes its own. The UI thread keeps the shared `self._gw`/`self._locator`. This removes concurrent access to the mutable `Locator._gray_cache`.

**Tech Stack:** Python, `gt_spector/locator.py` (`Locator`), `gt_spector/game_world.py` (`GameWorld`), tkinter console.

## Global Constraints

- The monitor worker thread uses its OWN `GameWorld`/`Locator`, never the console's shared `self._gw`/`self._locator`.
- `_detect_location(bot, frame, gw=None, locator=None)` — defaults to the shared `self._gw`/`self._locator`; callers on the UI thread unchanged; the worker passes its own.
- The UI thread (`_update_rows`) keeps using the shared Locator (single-threaded there).
- No new locking; the fix is per-thread instances.
- Unit tests: verify `_detect_location` accepts explicit gw/locator, and the worker creates its own instances.

---
### Task 1: _detect_location accepts per-thread gw/locator

**Files:**
- Modify: `viewer/bot_console.py` (`_detect_location`, `_monitor_one`, `_start_monitor_worker`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `self._gw`, `self._locator`, `monitor.detect_screen`, `_FrameSession`.
- Produces: `_detect_location(bot, frame, gw=None, locator=None) -> str | None` — uses `gw or self._gw` and `locator or self._locator`. The monitor worker creates and passes its own instances.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_detect_location_accepts_explicit_gw_and_locator():
    c = make_console()
    calls = {}

    class FakeLoc:
        def find(self, frame, name):
            return type("R", (), {"found": False})()

    class FakeGW:
        def identify(self, session):
            calls["identified"] = True
            return "custom_screen"

    c._nav_table = lambda: {"states": {}}
    c._gw = object()  # would fail if used
    c._locator = object()
    loc = c._detect_location(make_bot(), object(), gw=FakeGW(), locator=FakeLoc())
    assert loc == "custom_screen"
    assert calls["identified"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_detect_location_accepts_explicit_gw_and_locator -v`
Expected: FAIL — `_detect_location` does not accept `gw`/`locator` kwargs.

- [ ] **Step 3: Implement**

Modify `_detect_location`:

```python
    def _detect_location(self, bot: Bot, frame: Any,
                         gw: Any = None, locator: Any = None) -> str | None:
        if frame is None:
            return "?"
        if monitor.frame_is_blank(frame):
            return "blank"
        loc = monitor.detect_screen(frame, self._nav_table())
        if loc is not None:
            return loc
        gw = gw or self._gw
        locator = locator or self._locator
        try:
            identified = gw.identify(_FrameSession(frame))
            if identified:
                return identified
        except Exception:  # noqa: BLE001, S110
            pass
        screens = cast(dict[str, str] | None, getattr(self, "_vlm_screens", None))
        if screens:
            return screens.get(bot.name)
        return None
```

Note: `monitor.detect_screen` uses only the frame and nav_table (no Locator), so it is safe to call before the gw/locator swap. `gw.identify` internally uses `gw._locator` (set via `gw.set_locator(locator)`), so `_FrameSession` + `gw.identify` uses the passed `gw`/`locator` — verify `FakeGW.identify` receives the session only.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_detect_location_accepts_explicit_gw_and_locator -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: _detect_location accepts per-thread gw/locator"
```

---
### Task 2: Monitor worker uses its own GameWorld/Locator

**Files:**
- Modify: `viewer/bot_console.py` (`_start_monitor_worker`, `_monitor_one`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_detect_location(bot, frame, gw=..., locator=...)` (Task 1), `GameWorld`, `Locator`.
- Produces: the monitor worker creates its own `GameWorld`/`Locator` and passes them to `_detect_location`; `_monitor_one` forwards them.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_monitor_one_uses_worker_locator_for_detect(monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", "/tmp/gtsp")
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    c._runners = {}
    c._frames = {"bot01": None}
    seen = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame, gw=None, locator=None: (
        seen.update({"gw": gw, "locator": locator}) or None)
    c._monitor_one(bot)
    assert seen["gw"] is not None and seen["locator"] is not None
```

(This test asserts `_monitor_one` forwards non-None gw/locator into `_detect_location` — i.e., the worker-provided instances.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_monitor_one_uses_worker_locator_for_detect -v`
Expected: FAIL — `_monitor_one` calls `_detect_location` without gw/locator (seen values None).

- [ ] **Step 3: Implement**

In `_start_monitor_worker`, give the worker its own GameWorld/Locator:

```python
    def _start_monitor_worker(self) -> None:
        import threading

        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator

        def worker() -> None:
            # Own GameWorld/Locator: the UI thread shares self._gw/_locator
            # (whose mutable _gray_cache would race if accessed concurrently).
            gw = GameWorld()
            locator = Locator()
            gw.set_locator(locator)
            while not self._vlm_stop:
                time.sleep(MONITOR_INTERVAL)
                try:
                    self._monitor_tick(gw, locator)
                except Exception as e:  # noqa: BLE001 - never kill the worker
                    logs.log_system(f"monitor worker error: {e}")

        threading.Thread(target=worker, daemon=True).start()
```

Change `_monitor_tick` and `_monitor_one` to accept and forward gw/locator:

```python
    def _monitor_tick(self, gw: Any = None, locator: Any = None) -> None:
        for bot in self._manager.bots:
            try:
                self._monitor_one(bot, gw, locator)
            except Exception:  # noqa: BLE001 - one bot must not kill the poll
                logs.log_bot(bot.name, "monitor error, continuing")

    def _monitor_one(self, bot: Bot, gw: Any = None, locator: Any = None) -> None:
        ...
        if runner and runner.script:
            if getattr(runner.script, "self_healing", False):
                return
            expected = getattr(runner.script, "expected_screen", None)
            if expected:
                loc = self._detect_location(bot, self._frames.get(bot.name), gw=gw, locator=locator)
                ...
```

The UI thread's `_poll` no longer calls `_monitor_tick`, so the shared `self._gw`/`self._locator` remain UI-thread-only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_console.py::test_monitor_one_uses_worker_locator_for_detect -v` then `pytest tests/test_bot_console.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "perf: monitor worker uses per-thread GameWorld/Locator (no shared _gray_cache race)"
```

---
### Task 3: Live verification

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the feature from Tasks 1-2.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/ -q`
Expected: PASS except the 2 pre-existing unrelated failures (test_shm_screen, test_input_interactive).

- [ ] **Step 2: Reproduce the contention measurement is gone**

Run the concurrent measurement from the debugging session: with a worker thread calling `_detect_location` while the UI thread runs `_update_rows`, `_update_rows` should return to ~1.4s (not ~4s) for 8 bots.

- [ ] **Step 3: Confirm selection is responsive**

Restart the console with a display, select bots repeatedly; each selection's visual feedback should be immediate (well under 1s).

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from per-thread locator verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
