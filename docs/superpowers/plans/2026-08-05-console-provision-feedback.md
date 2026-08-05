# Console Provision Feedback Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix console bot provisioning so it (1) actually runs (use the venv python, not system `python3`) and (2) gives live feedback instead of freezing the UI.

**Architecture:** `_provision_n` uses `sys.executable` for the subprocess. Provisioning runs on a background thread; progress updates are posted to the Tk UI thread via `self._tk.after(0, ...)` (thread-safe), so the user sees "Provisioning bot09 (sr02-12@mx1.us)...", "bot09: provisioned", etc., as each bot completes, without freezing.

**Tech Stack:** Python, tkinter (`after`), `threading`, `subprocess`, `viewer/bot_console.py`.

## Global Constraints

- The provision subprocess uses `sys.executable` (the venv python), NOT `"python3"` — system python cannot import `gt_spector`.
- Provisioning runs on a background daemon thread; the Tk UI thread is never blocked by a provision subprocess.
- All UI updates (status bar text) from the background thread go through `self._tk.after(0, lambda: ...)` — never direct `_status.config` from the worker.
- The dialog's Provision button closes the dialog, then starts the background provision and returns immediately.
- Existing `_provision_n(count)` semantics preserved: first `count` unprovisioned, sequential, stop on failure, refresh on completion.
- Tests use mocked subprocess/threading; no real provisioning in unit tests.

---
### Task 1: Fix python path + background provisioning

**Files:**
- Modify: `viewer/bot_console.py` (`_provision_n`, `_provision_dialog`'s `run`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_unprovisioned_accounts()`, `sys.executable`, `subprocess.run`, `self._tk.after`, `self._refresh_bots()`.
- Produces: `_provision_n(count: int) -> None` — starts a background thread; returns immediately. Progress via `_status.config` marshalled through `_tk.after`. The dialog's `run()` calls it then returns.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_provision_n_uses_sys_executable(monkeypatch):
    import sys
    import threading

    from viewer import bot_console as bc

    c = make_console()
    called = {}
    monkeypatch.setattr(bc, "sys", type("S", (), {"executable": "/venv/bin/python3"})())

    def fake_run(cmd, **kw):
        called["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(bc.subprocess, "run", fake_run)
    c._unprovisioned_accounts = lambda: [("bot09", "a@x")]
    c._refresh_bots = lambda: None
    c._status = type("S", (), {"config": lambda s, **k: None})()
    c._tk = type("Tk", (), {"after": lambda s, ms, fn: None, "update": lambda s: None})()

    c._provision_n(1)
    time.sleep(0.2)  # let the background thread run
    assert called["cmd"][0] == "/venv/bin/python3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_provision_n_uses_sys_executable -v`
Expected: FAIL — cmd[0] is `"python3"`, not `sys.executable`.

- [ ] **Step 3: Implement**

Modify `_provision_n` to use `sys.executable` and run on a background thread:

```python
    def _provision_n(self, count: int) -> None:
        """Provision the first `count` unprovisioned accounts, one at a time.

        Runs on a background thread so the UI stays responsive; progress is
        marshalled to the Tk thread via `after`. Sequential only; verifies
        exit code 0 after each; stops on the first failure.
        """
        import sys
        import threading

        pending = self._unprovisioned_accounts()[:count]

        def _set_status(text: str) -> None:
            self._tk.after(0, lambda: self._status.config(text=text))

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
                _set_status(f"{name}: provisioned")
            self._tk.after(0, self._refresh_bots)
            _set_status(f"Provisioned {len(pending)} bot(s)")

        threading.Thread(target=worker, daemon=True).start()
```

Update the dialog's `run()` (it currently calls `self._provision_n(n)` synchronously — with the background thread, this returns immediately, which is now correct):

```python
        def run() -> None:
            try:
                n = count.get()
            except tk.TclError:
                return  # non-numeric input; keep the dialog open
            win.destroy()
            self._provision_n(n)
```

(The `run()` body is unchanged — it already just calls `_provision_n`; the fix is inside `_provision_n`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_provision_n_uses_sys_executable -v`
Expected: PASS.

- [ ] **Step 5: Run the full console suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS (existing `test_provision_n_sequential_and_stops_on_failure` may need its `_tk` stub to include `after` — verify and update if needed).

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "fix: provision uses venv python on a background thread with live feedback"
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

- [ ] **Step 2: Verify provision command works from the console environment**

Run: `source .venv/bin/activate && python3 -c "import sys; print(sys.executable)"` and confirm the venv python runs `python3 -m gt_spector.provision list`.

- [ ] **Step 3: Live provision test (1 bot)**

Launch the console, open Provision → Provision Bots…, select 1, click Provision. Confirm:
- The status bar updates to "Provisioning bot09 (sr02-12@mx1.us)..." immediately.
- The UI stays responsive (can click around) while it works.
- It completes with "bot09: provisioned" and the bot list refreshes.

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from provision feedback verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
