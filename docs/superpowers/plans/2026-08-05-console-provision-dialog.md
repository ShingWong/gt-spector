# Console Provision Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the console's batch-provision with a dialog that lists unprovisioned accounts and provisions a user-selected count, one at a time, verified sequentially.

**Architecture:** Add `_unprovisioned_accounts() -> list[tuple[str, str]]` (pure logic: read accounts file, map line-order → bot name, filter to prefixes without `drive_c`), `_provision_n(count) -> None` (sequential subprocess provision with per-bot exit-code verification and stop-on-failure), and `_provision_dialog()` (a `tk.Toplevel` with an account list, a 1..N Spinbox, Provision and Cancel buttons). `_on_provision` opens the dialog instead of batch-looping.

**Tech Stack:** Python, tkinter/ttk (already used by the console), `gt_spector/provision.py` CLI, `BotManager`.

## Global Constraints

- Accounts source of truth: `/home/swong/dls/src/ahk/accounts` (line `email:password` per line).
- Bot name = line order: first entry → `bot01`, second → `bot02`, … (`bot{i+1:02d}`). Never assume email is sequential.
- "Provisioned" = prefix directory exists with `drive_c` (`wineprefix_bots/<name>/drive_c`).
- Provision command: `python3 -m gt_spector.provision init <name> --account <email>`.
- Provisioning is strictly sequential (one at a time, no parallel), verifying exit code 0 after each, stopping on the first failure.
- The GUI dialog is not unit-tested; the pure logic (`_unprovisioned_accounts`, `_provision_n`) is.
- Tests use fake accounts files (tmp files) and fake prefix dirs; no real wine/provisioning in tests.

---
### Task 1: _unprovisioned_accounts

**Files:**
- Modify: `viewer/bot_console.py` (add `_unprovisioned_accounts`; refactor `_load_accounts` to share the accounts-file read)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `Path("/home/swong/dls/src/ahk/accounts")`, `Path("/home/swong/dls/wineprefix_bots")` (the provision BASE_DIR).
- Produces: `_unprovisioned_accounts() -> list[tuple[str, str]]` — ordered list of `(bot_name, email)` for accounts without a provisioned prefix. `_provision_n` (Task 2) and `_provision_dialog` (Task 3) consume it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_unprovisioned_accounts_line_order(tmp_path, monkeypatch):
    from pathlib import Path as _Path

    from viewer import bot_console as bc

    accounts = tmp_path / "accounts"
    accounts.write_text(
        "sr02-04@mx1.us:bamboo-H4\n"
        "sr02-05@mx1.us:bamboo-H4\n"
        "sr02-20@mx1.us:bamboo-H4\n"
    )
    prefixes = tmp_path / "prefixes"
    (prefixes / "bot01" / "drive_c").mkdir(parents=True)  # bot01 provisioned

    monkeypatch.setattr(bc, "ACCOUNTS_FILE", accounts)
    monkeypatch.setattr(bc, "PREFIXES_DIR", prefixes)

    c = make_console()
    got = c._unprovisioned_accounts()
    # bot01 (sr02-04) is provisioned; bot02 (sr02-05) and bot03 (sr02-20) are not
    assert got == [("bot02", "sr02-05@mx1.us"), ("bot03", "sr02-20@mx1.us")]


def test_unprovisioned_accounts_missing_file(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    monkeypatch.setattr(bc, "ACCOUNTS_FILE", tmp_path / "nope")
    monkeypatch.setattr(bc, "PREFIXES_DIR", tmp_path / "prefixes")
    assert make_console()._unprovisioned_accounts() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_unprovisioned_accounts_line_order tests/test_bot_console.py::test_unprovisioned_accounts_missing_file -v`
Expected: FAIL — `AttributeError: 'BotConsole' object has no attribute '_unprovisioned_accounts'`

- [ ] **Step 3: Implement**

At module top of `viewer/bot_console.py`, add constants (near the existing imports):

```python
ACCOUNTS_FILE = Path("/home/swong/dls/src/ahk/accounts")
PREFIXES_DIR = Path("/home/swong/dls/wineprefix_bots")
```

Refactor `_load_accounts` to use `ACCOUNTS_FILE`, and add:

```python
def _unprovisioned_accounts(self) -> list[tuple[str, str]]:
    """Accounts (line order -> bot name) whose prefix is not provisioned.

    Returns [(bot_name, email), ...] for accounts lacking a prefix with
    drive_c. Accounts are mapped by line order (first -> bot01), never by
    assuming the email is sequential.
    """
    out: list[tuple[str, str]] = []
    try:
        lines = ACCOUNTS_FILE.read_text().splitlines()
    except (FileNotFoundError, OSError):
        return out
    for i, line in enumerate(lines):
        line = line.strip()
        if ":" not in line:
            continue
        email = line.split(":")[0].strip()
        name = f"bot{i + 1:02d}"
        if (PREFIXES_DIR / name / "drive_c").exists():
            continue
        out.append((name, email))
    return out
```

Update `_load_accounts` to read from `ACCOUNTS_FILE` (same `read_text().splitlines()` logic) so the source-of-truth path is centralized.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_unprovisioned_accounts_line_order tests/test_bot_console.py::test_unprovisioned_accounts_missing_file -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: console _unprovisioned_accounts (line-order mapping)"
```

---
### Task 2: _provision_n (sequential, verified)

**Files:**
- Modify: `viewer/bot_console.py` (add `_provision_n`)
- Test: `tests/test_bot_console.py`

**Interfaces:**
- Consumes: `_unprovisioned_accounts()` (Task 1), `subprocess.run`, `self._status`, `self._refresh_bots()`.
- Produces: `_provision_n(count: int) -> None` — provisions the first `count` unprovisioned accounts sequentially, verifying exit code 0 after each, stopping on first failure. `_provision_dialog` (Task 3) calls it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bot_console.py`:

```python
def test_provision_n_sequential_and_stops_on_failure(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    c = make_console()
    calls = []
    statuses = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        name = cmd[cmd.index("init") + 1]
        if name == "bot03":  # fail on the 3rd
            return type("R", (), {"returncode": 1})()
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    c._status = type("S", (), {"config": lambda s, t: statuses.append(t)})()
    c._refresh_bots = lambda: None
    c._unprovisioned_accounts = lambda: [
        ("bot01", "a@x"), ("bot02", "b@x"), ("bot03", "c@x"), ("bot04", "d@x")]
    c._provision_n(4)
    # bot01, bot02 provisioned; bot03 failed -> stops, bot04 never run
    assert [x[x.index("init") + 1] for x in calls] == ["bot01", "bot02", "bot03"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_console.py::test_provision_n_sequential_and_stops_on_failure -v`
Expected: FAIL — `AttributeError: 'BotConsole' object has no attribute '_provision_n'`

- [ ] **Step 3: Implement**

Add to `viewer/bot_console.py`:

```python
def _provision_n(self, count: int) -> None:
    """Provision the first `count` unprovisioned accounts, one at a time.

    Sequential only (no parallel); verifies exit code 0 after each and stops
    on the first failure. Refreshes the bot list when done.
    """
    pending = self._unprovisioned_accounts()[:count]
    for name, email in pending:
        self._status.config(text=f"Provisioning {name} ({email})...")
        self._tk.update()
        r = subprocess.run(
            ["python3", "-m", "gt_spector.provision", "init", name,
             "--account", email],
            capture_output=True, text=True, timeout=600, check=False)
        if r.returncode != 0:
            tail = (r.stderr or "").strip()[-60:]
            self._status.config(text=f"{name}: FAILED ({tail})")
            return
        self._status.config(text=f"{name}: provisioned")
    self._status.config(text=f"Provisioned {len(pending)} bot(s)")
    self._refresh_bots()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bot_console.py::test_provision_n_sequential_and_stops_on_failure -v`
Expected: PASS. (Note: the test stubs `self._tk.update` implicitly — verify the console object has a `_tk`; if not, guard `_tk.update` behind a hasattr or the test sets `c._tk = type("Tk", (), {"update": lambda s: None})()`.)

- [ ] **Step 5: Lint and commit**

Run: `source .venv/bin/activate && ruff check viewer/bot_console.py tests/test_bot_console.py`
Expected: no errors.

```bash
git add viewer/bot_console.py tests/test_bot_console.py
git commit -m "feat: console _provision_n sequential verified provisioning"
```

---
### Task 3: _provision_dialog and wire the menu

**Files:**
- Modify: `viewer/bot_console.py` (add `_provision_dialog`; change `_on_provision` to open it; update the menu entry label)
- Test: none (GUI dialog is not unit-tested, consistent with existing console tests)

**Interfaces:**
- Consumes: `_unprovisioned_accounts()` (Task 1), `_provision_n(count)` (Task 2), `self._tk`.
- Produces: `_provision_dialog() -> None` — opens the dialog. `_on_provision` calls it; the "Provision Bots" menu entry invokes `_on_provision`.

- [ ] **Step 1: Replace _on_provision with a dialog**

In `viewer/bot_console.py`, replace the body of `_on_provision`:

```python
def _on_provision(self) -> None:
    self._provision_dialog()

def _provision_dialog(self) -> None:
    """Dialog: list unprovisioned accounts, pick 1..N, provision sequentially."""
    pending = self._unprovisioned_accounts()
    win = tk.Toplevel(self._tk)
    win.title("Provision Bots")
    if not pending:
        ttk.Label(win, text="All accounts provisioned").pack(padx=12, pady=12)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=4)
        return

    ttk.Label(win, text="Unprovisioned accounts:", font=("", 10, "bold")).pack(
        anchor=tk.W, padx=12, pady=(12, 4))
    for name, email in pending:
        ttk.Label(win, text=f"  {name} -> {email}", anchor=tk.W).pack(
            anchor=tk.W, padx=16)
    count = tk.IntVar(value=1)
    ttk.Label(win, text="How many to provision?").pack(anchor=tk.W, padx=12, pady=(10, 2))
    ttk.Spinbox(win, from_=1, to=len(pending), textvariable=count, width=6).pack(
        anchor=tk.W, padx=16)

    def run() -> None:
        win.destroy()
        self._provision_n(count.get())

    ttk.Button(win, text="Provision", command=run).pack(side=tk.LEFT, padx=12, pady=12)
    ttk.Button(win, text="Cancel", command=win.destroy).pack(
        side=tk.LEFT, padx=4, pady=12)
```

Update the menu entry label (line ~159) from `"Provision Bots"` to `"Provision Bots…"` so it signals a dialog.

- [ ] **Step 2: Verify the console imports and the menu wiring**

Run: `source .venv/bin/activate && python3 -c "import viewer.bot_console"` then `python3 -c "from viewer.bot_console import BotConsole; print('methods:', [m for m in ('_unprovisioned_accounts','_provision_n','_provision_dialog') if hasattr(BotConsole, m)])"`
Expected: `methods: ['_unprovisioned_accounts', '_provision_n', '_provision_dialog']`

- [ ] **Step 3: Run the full console test suite**

Run: `pytest tests/test_bot_console.py -q`
Expected: PASS.

- [ ] **Step 4: Lint and commit**

Run: `source .venv/bin/activate && ruff check viewer/bot_console.py`
Expected: no errors.

```bash
git add viewer/bot_console.py
git commit -m "feat: console provision dialog (list unprovisioned, pick 1..N)"
```

---
### Task 4: Live verification of the dialog logic

**Files:**
- none (verification only)

**Interfaces:**
- Consumes: the feature from Tasks 1-3.

- [ ] **Step 1: Run full unit test suite**

Run: `source .venv/bin/activate && pytest tests/test_bot_console.py -q`
Expected: PASS.

- [ ] **Step 2: Verify _unprovisioned_accounts against the real accounts file**

Run:

```python
from viewer.bot_console import BotConsole
c = object.__new__(BotConsole)
for name, email in c._unprovisioned_accounts():
    print(name, email)
```

Expected: prints the accounts whose prefixes don't exist (e.g. `bot09 sr02-12@mx1.us` … `bot17 sr02-20@mx1.us`), and none of bot01..bot08.

- [ ] **Step 3: Manual dialog smoke test**

Launch the console with a display and open Provision → Provision Bots…; confirm the dialog lists the unprovisioned accounts, the Spinbox ranges 1..N, and Provision runs sequentially. (This step may be done by the human; the logic is covered by unit tests.)

- [ ] **Step 4: Commit any verification-driven fixes**

```bash
git add -u
git commit -m "fix: adjustments from provision dialog verification"
```

(Only run this step if verification surfaced a real fix. Otherwise skip.)
