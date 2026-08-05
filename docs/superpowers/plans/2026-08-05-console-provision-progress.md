# Console Provision Progress Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the console's provisioning a dedicated progress display so progress isn't overwritten by the 2s poll's GPU/RAM stats footer.

**Architecture:** Replace `_set_status` (which writes to the shared `self._status` footer label, colliding with the poll's stats line) with a dedicated provisioning progress label. The worker thread updates ONLY that label via `_tk.after`; the footer stats keep showing GPU/CPU/RAM. The label appears during provisioning and is cleared/hidden on completion.

**Tech Stack:** Python, tkinter/ttk (`ttk.Label`), `viewer/bot_console.py`.

## Global Constraints

- Provisioning progress is shown in a DEDICATED label (e.g. `self._provision_status`), NOT `self._status` (the footer that the 2s poll writes GPU/RAM stats to).
- The progress label is created once (in `_setup_statusbar` or `_setup_bot_list`) and shown/hidden (`.pack`/`.pack_forget`) around provisioning.
- The worker thread updates the progress label ONLY via `self._tk.after(0, ...)` (thread-safe).
- The footer `self._status` continues to show GPU/VRAM/RAM/Swap/bots/CPU/MEM from `_update_rows` — unchanged.
- On provisioning completion (success or failure/stop), the progress label is cleared and hidden.
- Existing `_provision_n` tests updated to use the new progress label.

---
### Task 1: Dedicated provision progress label

**Files:**
- Modify: `viewer/bot_console.py` (`_setup_statusbar` or `_setup_bot_list`, `_provision_n`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `self._tk`, `self._status` (unchanged footer), `_unprovisioned_accounts`, `subprocess.run`, `sys.executable`.
- Produces: `self._provision_status` (a `ttk.Label`); `_provision_n` shows/hides it and updates its text via `_tk.after`. `_refresh_bots` behavior unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_provision_n_updates_dedicated_label_not_footer(monkeypatch):
    import sys

    from viewer import bot_console as bc

    c = make_console()
    label_updates = []
    footer_updates = []

    c._provision_status = type("L", (), {
        "config": lambda s, text=None: label_updates.append(text),
        "pack": lambda *a, **k: None,
        "pack_forget": lambda *a, **k: None,
    })()
    c._status = type("S", (), {"config": lambda s, text=None: footer_updates.append(text)})()
    c._tk = type("Tk", (), {"after": lambda s, ms, fn: fn()})()

    def fake_run(cmd, **kw):
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(bc.subprocess, "run", fake_run)
    c._unprovisioned_accounts = lambda: [("bot10", "sr02-13@mx1.us")]
    c._login_password = lambda email: "pw"
    c._manager = type("M", (), {
        "get": lambda self, n: type("B", (), {"name": "bot10", "display": 19, "prefix": "/p"})(),
        "start_game": lambda self, b: None,
    })()
    c._boot_and_login = lambda bot, email, password: "shelter_view"
    c._refresh_bots = lambda: None

    c._provision_n(1)
    time.sleep(0.1)
    assert any("Provisioning bot10" in t for t in label_updates), label_updates
    assert "Provisioning bot10" not in "".join(footer_updates), footer_updates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_provision_n_updates_dedicated_label_not_footer -v`
Expected: FAIL — `_provision_status` doesn't exist, or `_provision_n` still writes to `self._status`.

- [ ] **Step 3: Implement**

Create the progress label in `_setup_statusbar` (after the footer `self._status`):

```python
    def _setup_statusbar(self) -> None:
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)
        self._provision_status = ttk.Label(
            self._tk, text="", anchor=tk.W, foreground="#cc0000",
            font=("", 10, "bold"))
        # hidden by default; _provision_n shows it during provisioning
```

Add helper methods:

```python
    def _show_provision_progress(self) -> None:
        try:
            self._provision_status.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)
        except Exception:  # noqa: BLE001 - already visible
            pass

    def _set_provision_progress(self, text: str) -> None:
        self._tk.after(0, lambda: self._provision_status.config(text=text))

    def _hide_provision_progress(self) -> None:
        self._tk.after(0, lambda: self._provision_status.pack_forget())
```

Rewrite `_provision_n`'s `_set_status` to use the dedicated label:

```python
        def _set_status(text: str) -> None:
            self._set_provision_progress(text)

        def worker() -> None:
            self._tk.after(0, self._show_provision_progress)
            try:
                for name, email in pending:
                    _set_status(f"Provisioning {name} ({email})...")
                    ...  # unchanged provision/start/login logic
                self._tk.after(0, self._refresh_bots)
                _set_status(f"Provisioned {len(pending)} bot(s)")
            finally:
                self._hide_provision_progress()
```

Wrap the loop in try/finally so the progress label is always hidden on completion or failure. The `self._status` footer is left untouched by `_provision_n`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_provision_n_updates_dedicated_label_not_footer -v`
Expected: PASS.

- [ ] **Step 5: Update pre-existing `_provision_n` tests**

The existing tests (e.g. `test_provision_n_sequential_and_stops_on_failure`, `test_provision_n_reports_start_login_exception`) stub `_status`/`_tk` and assert status text. Update them so:
- `_provision_status` stub is provided (a `config`/`pack`/`pack_forget` fake that records text).
- Assertions that checked `self._status.config(text=...)` now check the dedicated label's recorded text.
- The `_tk.after` stub must execute the callback synchronously (or the tests use `_sync_threads` as before).

Preserve each test's original intent (sequential, stop-on-failure, slice, exception reporting).

- [ ] **Step 6: Run the full console suite + lint**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS.

Run: `ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: dedicated provisioning progress label (not overwritten by stats footer)"
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

Launch the console, start provisioning a bot. Capture the console window and confirm the DEDICATED progress label shows "Provisioning bot<N>..." while the footer still shows "GPU ... | N bots ..." (not overwritten).

- [ ] **Step 3: Confirm the label hides on completion**

After provisioning finishes, the progress label disappears and the footer stats remain.

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from provision progress verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
