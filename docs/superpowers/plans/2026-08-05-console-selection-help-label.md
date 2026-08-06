# Console Selection Buttons + Alliance Help Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Select All / Unselect All toolbar buttons and show "Alliance Help" in the Loc column for bots running the help loop.

**Architecture:** Two small changes to `viewer/bot_console.py`: (1) add `☑ All` / `☐ None` buttons to `_setup_toolbar` calling the existing `_check_all`/`_uncheck_all`; (2) in `_update_rows`, remap the Loc label to "Alliance Help" when a self-healing (HelpBot) runner is active and the detected location is a help-area name.

**Tech Stack:** Python, tkinter/ttk, `viewer/bot_console.py`.

## Global Constraints

- Toolbar gains a selection group after the Help buttons: `☑ All` → `_check_all()`, `☐ None` → `_uncheck_all()`. Existing Selection menu items stay.
- Loc label: `loc = "Alliance Help"` only when `runner` exists, `runner.script.self_healing` is True, AND `loc in ("EVENT", "help_dialog", "ALLIANCE_HELP")`. Otherwise `loc` unchanged.
- The tooltip (`_status_tooltip`) still uses the raw loc — unchanged.
- Tests use `make_console()` (`object.__new__(BotConsole)`) fakes.

---
### Task 1: Toolbar buttons + Alliance Help label

**Files:**
- Modify: `viewer/bot_console.py` (`_setup_toolbar`, `_update_rows`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_check_all`, `_uncheck_all`, `_runners`, `_detect_location`, `getattr(runner.script, "self_healing", False)`.
- Produces: toolbar buttons wired to selection; Loc remap in `_update_rows`. Nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_loc_label_alliance_help_when_help_runner_active():
    c = make_console()
    runner = type("R", (), {"script": type("S", (), {"self_healing": True})()})()
    c._runners = {"bot01": runner}
    assert c._loc_label("EVENT") == "Alliance Help"
    assert c._loc_label("help_dialog") == "Alliance Help"
    assert c._loc_label("ALLIANCE_HELP") == "Alliance Help"


def test_loc_label_unchanged_without_help_runner():
    c = make_console()
    c._runners = {}
    assert c._loc_label("EVENT") == "EVENT"
    assert c._loc_label("shelter_view") == "shelter_view"


def test_loc_label_unchanged_when_runner_not_self_healing():
    c = make_console()
    runner = type("R", (), {"script": type("S", (), {"self_healing": False})()})()
    c._runners = {"bot01": runner}
    assert c._loc_label("EVENT") == "EVENT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_loc_label_alliance_help_when_help_runner_active tests/test_bot_console.py::test_loc_label_unchanged_without_help_runner tests/test_bot_console.py::test_loc_label_unchanged_when_runner_not_self_healing -v`
Expected: FAIL — `_loc_label` doesn't exist.

- [ ] **Step 3: Implement**

Add a helper and wire it into `_update_rows`:

```python
    @staticmethod
    def _loc_label(loc: str | None, runner: Any = None) -> str | None:
        """Friendly Loc label: 'Alliance Help' when a help loop is active on
        the help area; otherwise the raw location name."""
        if (runner is not None
                and getattr(runner.script, "self_healing", False)
                and loc in ("EVENT", "help_dialog", "ALLIANCE_HELP")):
            return "Alliance Help"
        return loc
```

In `_update_rows`, replace the Loc computation (around line 503):

```python
            loc = self._detect_location(bot, frame)
            runner = self._runners.get(bot.name)
            loc = self._loc_label(loc, runner)
```

(The `runner` variable is already fetched at line 504; reorder so `loc` uses `runner`.)

Add the toolbar buttons in `_setup_toolbar` after the Help buttons (after `Stop Help`):

```python
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="☑ All", command=self._check_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="☐ None", command=self._uncheck_all).pack(side=tk.LEFT, padx=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_loc_label_alliance_help_when_help_runner_active tests/test_bot_console.py::test_loc_label_unchanged_without_help_runner tests/test_bot_console.py::test_loc_label_unchanged_when_runner_not_self_healing -v`
Expected: PASS.

- [ ] **Step 5: Run the full console suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS.

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: select-all toolbar buttons + Alliance Help loc label"
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

- [ ] **Step 2: Visual confirmation via screen buffer**

Launch the console, verify the toolbar now shows `☑ All` / `☐ None` after the Help buttons, and that bots with a running HelpBot show "Alliance Help" in the Loc column while others keep their raw names.

- [ ] **Step 3: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from console selection/label verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
