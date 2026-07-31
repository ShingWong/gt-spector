# Console Reorg + Overlay + Sound + Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the bot console into a menu-bar + icon-bar layout, add overlay (marker) display control, sound control, per-bot status/location columns, monitoring with crash/restart recovery, and rotated system/per-bot logging.

**Architecture:** Four small new modules (`settings.py`, `audio.py`, `logs.py`, `monitor.py`) plus edits to `overlay.py`, `viewer/bot_console.py`, `viewer/gui.py`, and `bot_manager.py`. Settings persist in a hybrid layout: one global `settings.json` + one file per bot under `bots/`. The console poll loop (2s) drives status, monitoring, and recovery.

**Tech Stack:** Python 3.11+, Tkinter/ttk, numpy, JSON, subprocess (`pactl`, `xdotool`), pytest.

## Global Constraints

- Settings layout: global `~/.config/gt-spector/settings.json` + per-bot `~/.config/gt-spector/bots/<bot_name>.json`.
- Atomic writes everywhere: write temp file, then `os.replace`.
- Per-bot files keyed by bot name (NOT display).
- Sound mode values: `"all_off" | "viewer" | "all_on"`.
- Sound sink-inputs found via `application.process.id == game_pid`.
- Log rotation default 500 KB, keep 2 copies (`.log`, `.log.1`); size settable in console (stored as `log_max_bytes`).
- Status glyphs: ● green (Running), ◐ yellow (Starting), ✕ red (Offline/Error), ▲ blue (Alert/recovering/unrecoverable). Tooltip shows status words on mouse-over.
- CR = crash count (game restarts this session), IV = intervention count (recoveries this session). Both in-memory only.
- Screen fingerprints live in `nav_table.json` under `states.<NAME>.fingerprints`.
- VLM screen checks: 1/4 scale frames, round-robin, only when VLM slot free — never block bot actions.
- Recovery: ESC-to-shelter, then re-run the interrupted script.
- Code style: ruff + mypy strict, line-length 100. No unnecessary comments.
- Tests live in `tests/` (pytest). TDD: write failing test, verify fail, implement, verify pass, commit.

---

### Task 1: Settings store (`gt_spector/settings.py`)

**Files:**
- Create: `gt_spector/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CONFIG_DIR: Path`, `GLOBAL_PATH: Path`, `BOTS_DIR: Path`
  - `load_json(path, default) -> dict`
  - `save_json(path, data)` (atomic)
  - `get_global() -> dict`, `set_global(**kwargs)`
  - `get_bot(name) -> dict`, `set_bot(name, **kwargs)`
  - `overlay_global_enabled() -> bool`, `set_overlay_global(enabled: bool)`
  - `bot_overlay_enabled(name) -> bool`, `set_bot_overlay(name, enabled: bool)`
  - `sound_mode() -> str`, `set_sound_mode(mode: str)`
  - `bot_sound_muted(name) -> bool`, `set_bot_sound_muted(name, muted: bool)`
  - `log_max_bytes() -> int`, `set_log_max_bytes(n: int)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings.py`:

```python
import json
import os

import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    from gt_spector import settings
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path / "bots")
    return settings


def test_defaults_when_missing(cfg):
    assert cfg.get_global() == {}
    assert cfg.bot_overlay_enabled("bot01") is True
    assert cfg.sound_mode() == "viewer"
    assert cfg.bot_sound_muted("bot01") is False
    assert cfg.log_max_bytes() == 512 * 1024


def test_global_roundtrip(cfg):
    cfg.set_global(overlay_global_enabled=False, sound_mode="all_off")
    assert cfg.overlay_global_enabled() is False
    assert cfg.sound_mode() == "all_off"


def test_bot_roundtrip(cfg):
    cfg.set_bot("bot01", overlay_enabled=False, sound_muted=True)
    assert cfg.bot_overlay_enabled("bot01") is False
    assert cfg.bot_sound_muted("bot01") is True
    # bot02 untouched
    assert cfg.bot_overlay_enabled("bot02") is True


def test_bot_files_are_isolated(cfg):
    cfg.set_bot("bot01", overlay_enabled=False)
    cfg.set_bot("bot02", overlay_enabled=True)
    assert (cfg.BOTS_DIR / "bot01.json").exists()
    assert (cfg.BOTS_DIR / "bot02.json").exists()


def test_log_size_roundtrip(cfg):
    cfg.set_log_max_bytes(1024 * 1024)
    assert cfg.log_max_bytes() == 1024 * 1024


def test_corrupt_global_file_falls_back(cfg, monkeypatch):
    cfg.GLOBAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.GLOBAL_PATH.write_text("{ not json")
    assert cfg.overlay_global_enabled() is True
    assert cfg.sound_mode() == "viewer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gt_spector.settings'`

- [ ] **Step 3: Write minimal implementation**

Create `gt_spector/settings.py`:

```python
"""Persistent settings for gt-spector: global + per-bot JSON files.

Layout:
  ~/.config/gt-spector/settings.json        global settings
  ~/.config/gt-spector/bots/<name>.json     per-bot settings

All writes are atomic (write temp file, then os.replace).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "gt-spector"
GLOBAL_PATH = CONFIG_DIR / "settings.json"
BOTS_DIR = CONFIG_DIR / "bots"

DEFAULT_LOG_MAX_BYTES = 512 * 1024
DEFAULT_SOUND_MODE = "viewer"


def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def get_global() -> dict:
    return load_json(GLOBAL_PATH, {})


def set_global(**kwargs) -> None:
    data = get_global()
    data.update(kwargs)
    save_json(GLOBAL_PATH, data)


def get_bot(name: str) -> dict:
    return load_json(BOTS_DIR / f"{name}.json", {})


def set_bot(name: str, **kwargs) -> None:
    data = get_bot(name)
    data.update(kwargs)
    save_json(BOTS_DIR / f"{name}.json", data)


def overlay_global_enabled() -> bool:
    return bool(get_global().get("overlay_global_enabled", True))


def set_overlay_global(enabled: bool) -> None:
    set_global(overlay_global_enabled=enabled)


def bot_overlay_enabled(name: str) -> bool:
    return bool(get_bot(name).get("overlay_enabled", True))


def set_bot_overlay(name: str, enabled: bool) -> None:
    set_bot(name, overlay_enabled=enabled)


def sound_mode() -> str:
    return get_global().get("sound_mode", DEFAULT_SOUND_MODE)


def set_sound_mode(mode: str) -> None:
    set_global(sound_mode=mode)


def bot_sound_muted(name: str) -> bool:
    return bool(get_bot(name).get("sound_muted", False))


def set_bot_sound_muted(name: str, muted: bool) -> None:
    set_bot(name, sound_muted=muted)


def log_max_bytes() -> int:
    try:
        return int(get_global().get("log_max_bytes", DEFAULT_LOG_MAX_BYTES))
    except (TypeError, ValueError):
        return DEFAULT_LOG_MAX_BYTES


def set_log_max_bytes(n: int) -> None:
    set_global(log_max_bytes=max(1024, int(n)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_settings.py gt_spector/settings.py
git commit -m "feat: add persistent settings store (global + per-bot)"
```

---

### Task 2: Overlay display control (`gt_spector/overlay.py`)

**Files:**
- Modify: `gt_spector/overlay.py`
- Test: `tests/test_overlay.py` (new)

**Interfaces:**
- Consumes: `gt_spector.settings` functions from Task 1.
- Produces:
  - `overlay_enabled(display: int) -> bool` — global AND per-bot (bot name resolved via `display_to_bot(display)`).
  - `set_overlay_enabled(display: int | None, enabled: bool) -> None`
  - `toggle_overlay(display: int | None) -> bool`
  - `display_to_bot(display: int) -> str | None` — `9 + n` rule matching `BotManager.load_from_prefixes`.
  - CLI gains `toggle` and `status` subcommands.
  - `draw_markers(frame, display)` returns frame unchanged when overlay disabled.

- [ ] **Step 1: Write the failing test**

Create `tests/test_overlay.py`:

```python
import numpy as np
import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    from gt_spector import settings, overlay
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path / "bots")
    yield overlay, settings


def test_overlay_enabled_global_off(cfg):
    overlay, settings = cfg
    settings.set_overlay_global(False)
    assert overlay.overlay_enabled(10) is False


def test_overlay_enabled_per_bot_off(cfg):
    overlay, settings = cfg
    settings.set_bot_overlay("bot01", False)
    assert overlay.overlay_enabled(10) is False  # bot01 -> display 10


def test_overlay_enabled_both_on(cfg):
    overlay, settings = cfg
    assert overlay.overlay_enabled(10) is True


def test_set_overlay_enabled_global(cfg):
    overlay, settings = cfg
    overlay.set_overlay_enabled(None, False)
    assert settings.overlay_global_enabled() is False


def test_set_overlay_enabled_per_bot(cfg):
    overlay, settings = cfg
    overlay.set_overlay_enabled(10, False)
    assert settings.bot_overlay_enabled("bot01") is False


def test_toggle_global(cfg):
    overlay, settings = cfg
    assert overlay.toggle_overlay(None) is False
    assert settings.overlay_global_enabled() is False
    assert overlay.toggle_overlay(None) is True


def test_display_to_bot():
    from gt_spector.overlay import display_to_bot
    assert display_to_bot(10) == "bot01"
    assert display_to_bot(9) == "bot00"
    assert display_to_bot(2) is None


def test_draw_markers_skipped_when_disabled(cfg):
    overlay, settings = cfg
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    overlay.add_marker(10, 25, 25, "A")
    settings.set_bot_overlay("bot01", False)
    result = overlay.draw_markers(frame, 10)
    assert np.array_equal(result, frame)


def test_draw_markers_drawn_when_enabled(cfg):
    overlay, settings = cfg
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    overlay.add_marker(10, 25, 25, "A")
    settings.set_bot_overlay("bot01", True)
    result = overlay.draw_markers(frame, 10)
    assert not np.array_equal(result, frame)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_overlay.py -v`
Expected: FAIL (`overlay_enabled`/`set_overlay_enabled`/`toggle_overlay`/`display_to_bot` not defined)

- [ ] **Step 3: Write minimal implementation**

Edit `gt_spector/overlay.py`:

Add at the top, after existing imports:

```python
from gt_spector import settings as _settings
```

Add module-level helpers before the `Marker` dataclass:

```python
def display_to_bot(display: int) -> str | None:
    """Map a display number to a bot name via the 9 + n rule used by BotManager."""
    n = display - 9
    return f"bot{n:02d}" if n >= 0 else None


def overlay_enabled(display: int) -> bool:
    if not _settings.overlay_global_enabled():
        return False
    name = display_to_bot(display)
    if name is None:
        return True
    return _settings.bot_overlay_enabled(name)


def set_overlay_enabled(display: int | None, enabled: bool) -> None:
    if display is None:
        _settings.set_overlay_global(enabled)
    else:
        name = display_to_bot(display)
        if name is not None:
            _settings.set_bot_overlay(name, enabled)


def toggle_overlay(display: int | None) -> bool:
    if display is None:
        enabled = not _settings.overlay_global_enabled()
        _settings.set_overlay_global(enabled)
    else:
        name = display_to_bot(display)
        if name is None:
            return True
        enabled = not _settings.bot_overlay_enabled(name)
        _settings.set_bot_overlay(name, enabled)
    return enabled
```

Change `draw_markers` to gate on `overlay_enabled(display)`:

```python
def draw_markers(frame: np.ndarray, display: int) -> np.ndarray:
    if not overlay_enabled(display):
        return frame.copy()
    result = frame.copy()
    ...
```

Extend the CLI in `_main()`:

```python
    elif cmd == "toggle":
        display_arg = sys.argv[3] if len(sys.argv) > 3 else None
        d = int(display_arg) if display_arg is not None else None
        state = toggle_overlay(d)
        print(f"  Overlay {'ON' if state else 'OFF'} for {'global' if d is None else f'display {d}'}")

    elif cmd == "status":
        d = int(sys.argv[3]) if len(sys.argv) > 3 else None
        if d is None:
            print(f"  Global overlay: {'ON' if _settings.overlay_global_enabled() else 'OFF'}")
        else:
            print(f"  Display {d} overlay: {'ON' if overlay_enabled(d) else 'OFF'}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_overlay.py -v`
Expected: PASS

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/ -v`
Expected: existing tests still pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add tests/test_overlay.py gt_spector/overlay.py
git commit -m "feat: overlay display control with global + per-bot toggles"
```

---

### Task 3: Audio control module (`gt_spector/audio.py`)

**Files:**
- Create: `gt_spector/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: nothing (raw subprocess to `pactl`).
- Produces:
  - `get_sink_inputs(game_pid: int) -> list[int]`
  - `set_muted(game_pid: int, muted: bool) -> None`
  - `is_muted(game_pid: int) -> bool | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio.py`:

```python
import subprocess

import pytest


@pytest.fixture()
def fake_pactl(monkeypatch):
    """Replace subprocess.run so audio.py never touches real pactl."""
    calls = []

    def fake_run(cmd, capture_output=False, text=False, timeout=5, check=False):
        calls.append(cmd)
        out = ""
        if cmd[:2] == ["pactl", "list"]:
            out = (
                "Sink Input #7400\n"
                "\tapplication.process.id = \"33425\"\n"
                "Sink Input #7405\n"
                "\tapplication.process.id = \"33425\"\n"
                "Sink Input #9999\n"
                "\tapplication.process.id = \"12345\"\n"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_get_sink_inputs(fake_pactl):
    from gt_spector import audio
    assert audio.get_sink_inputs(33425) == [7400, 7405]
    assert audio.get_sink_inputs(12345) == [9999]
    assert audio.get_sink_inputs(1) == []


def test_set_muted(fake_pactl):
    from gt_spector import audio
    audio.set_muted(33425, True)
    assert ["pactl", "set-sink-input-mute", "7400", "1"] in fake_pactl
    assert ["pactl", "set-sink-input-mute", "7405", "1"] in fake_pactl
    audio.set_muted(33425, False)
    assert ["pactl", "set-sink-input-mute", "7400", "0"] in fake_pactl


def test_set_muted_no_streams_is_noop(fake_pactl):
    from gt_spector import audio
    audio.set_muted(1, True)  # no matching sink-inputs
    assert fake_pactl == []  # nothing extra beyond the list call


def test_is_muted(fake_pactl):
    from gt_spector import audio
    # fake output has no Muted: lines -> is_muted returns None
    assert audio.is_muted(33425) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gt_spector.audio'`

- [ ] **Step 3: Write minimal implementation**

Create `gt_spector/audio.py`:

```python
"""Control game audio via PipeWire pactl.

Each game process emits sink-inputs carrying application.process.id = game_pid.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional


def _pactl_list() -> str:
    try:
        r = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ""


def get_sink_inputs(game_pid: int) -> list[int]:
    out = _pactl_list()
    result: list[int] = []
    current: Optional[int] = None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line.strip())
        if m:
            current = int(m.group(1))
            continue
        if current is None:
            continue
        pm = re.search(r'application\.process\.id\s*=\s*"(\d+)"', line)
        if pm and int(pm.group(1)) == game_pid:
            result.append(current)
    return result


def set_muted(game_pid: int, muted: bool) -> None:
    for sid in get_sink_inputs(game_pid):
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(sid), "1" if muted else "0"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass


def is_muted(game_pid: int) -> Optional[bool]:
    out = _pactl_list()
    ids = set(get_sink_inputs(game_pid))
    if not ids:
        return None
    states: list[bool] = []
    current: Optional[int] = None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line.strip())
        if m:
            current = int(m.group(1))
            continue
        if current not in ids:
            continue
        mm = re.search(r"Mute:\s*(\w+)", line)
        if mm:
            states.append(mm.group(1) == "yes")
    if not states:
        return None
    return all(states)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_audio.py gt_spector/audio.py
git commit -m "feat: audio control via pactl sink-input mute"
```

---

### Task 4: Logging subsystem (`gt_spector/logs.py`)

**Files:**
- Create: `gt_spector/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: `gt_spector.settings.log_max_bytes` from Task 1.
- Produces:
  - `LOGS_DIR: Path`
  - `log_system(msg: str)` — appends timestamped line to `logs/system.log`, rotates.
  - `log_bot(name: str, msg: str)` — appends to `logs/<name>.log`, rotates.
  - `clear_all_logs()` — truncates system + all bot logs and removes `.1` copies.
  - `_rotate(path: Path)` — if file > max bytes, rename to `.1` (replace existing) and start fresh.

- [ ] **Step 1: Write the failing test**

Create `tests/test_logs.py`:

```python
import pytest


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    from gt_spector import logs, settings
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path.parent)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path.parent / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path.parent / "bots")
    return logs, settings


def test_log_system_writes_file(logs):
    logs_module, _ = logs
    logs_module.log_system("hello")
    content = (logs_module.LOGS_DIR / "system.log").read_text()
    assert "hello" in content


def test_log_bot_writes_per_bot_file(logs):
    logs_module, _ = logs
    logs_module.log_bot("bot01", "crash")
    content = (logs_module.LOGS_DIR / "bot01.log").read_text()
    assert "crash" in content


def test_rotation_keeps_two_copies(logs, monkeypatch):
    logs_module, settings = logs
    monkeypatch.setattr(settings, "log_max_bytes", lambda: 100)
    # Write enough to exceed 100 bytes twice
    for _ in range(5):
        logs_module.log_bot("bot01", "x" * 60)
    files = sorted(p.name for p in logs_module.LOGS_DIR.iterdir())
    assert "bot01.log" in files
    assert "bot01.log.1" in files


def test_clear_all_logs(logs):
    logs_module, _ = logs
    logs_module.log_system("s")
    logs_module.log_bot("bot01", "b")
    logs_module.clear_all_logs()
    assert (logs_module.LOGS_DIR / "system.log").exists() is False
    assert (logs_module.LOGS_DIR / "bot01.log").exists() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gt_spector.logs'`

- [ ] **Step 3: Write minimal implementation**

Create `gt_spector/logs.py`:

```python
"""Rotating logs: one system log + one log per bot.

Rotation: when a file exceeds settings.log_max_bytes(), the current file is
renamed to <name>.log.1 (replacing any existing .1), and a new file starts.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from gt_spector import settings

LOGS_DIR = settings.CONFIG_DIR / "logs"


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rotate(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > settings.log_max_bytes():
            backup = path.with_suffix(path.suffix + ".1")
            if backup.exists():
                backup.unlink()
            os.replace(path, backup)
    except (OSError, ValueError):
        pass


def _append(path: Path, msg: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with open(path, "a") as f:
            f.write(f"[{_stamp()}] {msg}\n")
    except OSError:
        print(f"log error: {path}: {msg}", file=__import__("sys").stderr)


def log_system(msg: str) -> None:
    _append(LOGS_DIR / "system.log", msg)


def log_bot(name: str, msg: str) -> None:
    _append(LOGS_DIR / f"{name}.log", msg)


def clear_all_logs() -> None:
    for p in LOGS_DIR.glob("*.log*"):
        try:
            p.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_logs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_logs.py gt_spector/logs.py
git commit -m "feat: rotating system + per-bot logs"
```

---

### Task 5: Monitor, fingerprints & recovery (`gt_spector/monitor.py`)

**Files:**
- Create: `gt_spector/monitor.py`
- Modify: `/home/swong/.config/gt-spector/nav_table.json` (add `fingerprints`)
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `Bot` (from `bot_manager`), `settings`, `logs`.
- Produces:
  - `detect_screen(frame: np.ndarray, nav_table: dict) -> str | None` — pure function; returns state name matching a fingerprint, else None.
  - `frame_is_blank(frame: np.ndarray) -> bool`
  - `class BotMonitor` with:
    - `__init__(self, manager, vlm=None)`
    - `check_responsiveness(bot) -> bool` (uses `Bot.shm_path`, reads frame counter twice with a small delay; False if stalled)
    - `mark_crash(bot)` → increments `bot.crash_count`, logs, returns None
    - `mark_intervention(bot)` → increments `bot.intervention_count`, logs
    - `recover(bot, script)` → ESC-to-shelter chain + re-run script; increments intervention; returns True/False
  - `Bot.crash_count: int = 0`, `Bot.intervention_count: int = 0` fields added to the dataclass.
  - `run_script()` helper on `ScriptRunner` to re-run a stopped script: add `run_script(script, display)` (see Task 6 note).

- [ ] **Step 1: Write the failing test**

Create `tests/test_monitor.py`:

```python
import numpy as np
import pytest


@pytest.fixture()
def nav_table():
    return {
        "states": {
            "ALLIANCE": {
                "fingerprints": [{"x": 930, "y": 550, "r": (150, 255), "g": (0, 100), "b": (0, 100)}],
            },
            "LOBBY": {
                "fingerprints": [{"x": 50, "y": 764, "r": (0, 100), "g": (0, 100), "b": (100, 255)}],
            },
        }
    }


def make_frame(rgb_at):
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    for (x, y), rgb in rgb_at.items():
        frame[y, x] = rgb
    return frame


def test_detect_screen_match(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (200, 50, 50)})  # matches ALLIANCE red badge
    assert detect_screen(frame, nav_table) == "ALLIANCE"


def test_detect_screen_no_match(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (0, 0, 0)})
    assert detect_screen(frame, nav_table) is None


def test_detect_screen_multiple(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (200, 50, 50), (50, 764): (0, 0, 200)})
    # ALLIANCE checked first, matches
    assert detect_screen(frame, nav_table) == "ALLIANCE"


def test_frame_is_blank():
    from gt_spector.monitor import frame_is_blank
    assert frame_is_blank(np.zeros((100, 100, 3), dtype=np.uint8)) is True
    assert frame_is_blank(np.full((100, 100, 3), 255, dtype=np.uint8)) is True
    noisy = np.zeros((100, 100, 3), dtype=np.uint8)
    noisy[50, 50] = (128, 128, 128)
    assert frame_is_blank(noisy) is False


def test_mark_crash_and_intervention(tmp_path, monkeypatch):
    from gt_spector import monitor, logs
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    m.mark_crash(bot)
    assert bot.crash_count == 1
    m.mark_intervention(bot)
    assert bot.intervention_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gt_spector.monitor'`

- [ ] **Step 3: Write minimal implementation**

Edit `gt_spector/bot_manager.py` — add fields to `Bot`:

```python
@dataclass
class Bot:
    name: str
    account: str = ""
    state: BotState = BotState.OFFLINE
    pid: int | None = None
    prefix: str = ""
    display: int = 9
    shm_id: int = 9
    script_paused: bool = False
    xvfb_pid: int | None = None
    crash_count: int = 0
    intervention_count: int = 0
```

Create `gt_spector/monitor.py`:

```python
"""Bot health monitoring: screen detection, responsiveness, recovery."""

from __future__ import annotations

import struct
import subprocess
import time
from typing import Callable, Optional

import numpy as np

from gt_spector import logs


def _in_range(val: int, rng: tuple) -> bool:
    return rng[0] <= val <= rng[1]


def detect_screen(frame: np.ndarray, nav_table: dict) -> Optional[str]:
    """Return the first state whose fingerprints all match the frame, else None."""
    states = nav_table.get("states", {})
    for name, data in states.items():
        fps = data.get("fingerprints", [])
        if not fps:
            continue
        ok = True
        for fp in fps:
            try:
                x, y = int(fp["x"]), int(fp["y"])
                if not (0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]):
                    ok = False
                    break
                r, g, b = int(frame[y, x, 0]), int(frame[y, x, 1]), int(frame[y, x, 2])
                if not (_in_range(r, fp["r"]) and _in_range(g, fp["g"]) and _in_range(b, fp["b"])):
                    ok = False
                    break
            except (KeyError, TypeError, IndexError, ValueError):
                ok = False
                break
        if ok:
            return name
    return None


def frame_is_blank(frame: np.ndarray) -> bool:
    """True if the frame is uniform (all-near-black or all-white)."""
    if frame.size == 0:
        return True
    std = float(np.std(frame))
    return std < 5.0


class BotMonitor:
    def __init__(self, manager, vlm=None):
        self._manager = manager
        self._vlm = vlm
        self._last_shm_counter: dict[str, int] = {}
        self._last_vlm_check: dict[str, float] = {}

    def _read_counter(self, shm_path: str) -> Optional[int]:
        try:
            with open(shm_path, "rb") as f:
                return struct.unpack("<Q", f.read(8))[0]
        except (FileNotFoundError, OSError, struct.error):
            return None

    def check_responsiveness(self, bot) -> bool:
        c0 = self._read_counter(bot.shm_path)
        if c0 is None:
            return False
        time.sleep(0.4)
        c1 = self._read_counter(bot.shm_path)
        if c1 is None:
            return False
        return c1 != c0

    def mark_crash(self, bot) -> None:
        bot.crash_count += 1
        logs.log_bot(bot.name, f"CRASH restart (count={bot.crash_count})")

    def mark_intervention(self, bot) -> None:
        bot.intervention_count += 1
        logs.log_bot(bot.name, f"INTERVENTION recovery (count={bot.intervention_count})")

    def recover(self, bot, run_script: Callable, script) -> bool:
        """ESC-to-shelter, then re-run the script. Returns True on success."""
        self.mark_intervention(bot)
        env = {"DISPLAY": f":{bot.display}"}
        wid = self._manager._find_window(bot.display) if self._manager else None
        if wid is None:
            try:
                r = subprocess.run(
                    ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
                    capture_output=True, text=True, env=env, timeout=5,
                )
                wid = r.stdout.strip().split()[0] if r.stdout.strip() else None
            except (OSError, subprocess.SubprocessError):
                wid = None
        if wid:
            for _ in range(8):
                subprocess.run(["xdotool", "key", "--window", wid, "Escape"],
                               capture_output=True, env=env, timeout=5)
                time.sleep(2)
        run_script(bot, script)
        return True
```

- [ ] **Step 4: Add fingerprints to nav_table**

Edit `/home/swong/.config/gt-spector/nav_table.json` — add a `fingerprints` array to each state with distinctive check pixels (x, y, and a color range that identifies that screen). For example:

```json
"ALLIANCE": {
  "buttons": [ ...existing... ],
  "fingerprints": [
    { "x": 50, "y": 200, "r": [0, 255], "g": [0, 255], "b": [0, 255] }
  ]
}
```

Use pixels/colors that are characteristic of each screen (e.g., the alliance sidebar area, exit-dialog beige background, region-view minimap). These are calibration values; the exact pixels come from the exploration logs (`~/.config/gt-spector/exploration/`).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_monitor.py -v`
Expected: PASS

- [ ] **Step 6: Run existing tests**

Run: `pytest tests/ -v`
Expected: all pass (no regressions)

- [ ] **Step 7: Commit**

```bash
git add tests/test_monitor.py gt_spector/monitor.py gt_spector/bot_manager.py
git commit -m "feat: screen monitor with responsiveness check and recovery"
```

---

### Task 6: Console reorganization + status columns (`viewer/bot_console.py`)

**Files:**
- Modify: `viewer/bot_console.py`
- Modify: `gt_spector/script.py` (add `run_script`)
- Manual test (Tkinter UI).

**Interfaces:**
- Consumes: Tasks 1-5 (`settings`, `overlay`, `audio`, `logs`, `monitor`), existing `BotManager`, `ScriptRunner`, `HelpBot`.
- Produces: reorganized console layout with menu bar + icon bar, status columns, overlay/sound/logs menus, CR/IV counters.

- [ ] **Step 1: Add `run_script` to `ScriptRunner`**

In `gt_spector/script.py` add:

```python
    def run_script(self, script: BotScript) -> None:
        self.start(script)
```

(Reuses existing `start`; kept as an explicit alias so the monitor can re-run a script by name.)

- [ ] **Step 2: Rewrite `_setup_menu`**

Replace the File-only menubar with the full menu structure:

```python
    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Refresh", command=self._refresh_bots)
        file_menu.add_command(label="Settings…", command=self._on_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        sel_menu = tk.Menu(menubar, tearoff=0)
        sel_menu.add_command(label="Check All", command=self._check_all)
        sel_menu.add_command(label="Uncheck All", command=self._uncheck_all)
        menubar.add_cascade(label="Selection", menu=sel_menu)

        act_menu = tk.Menu(menubar, tearoff=0)
        act_menu.add_command(label="Start", command=lambda: self._action("start"))
        act_menu.add_command(label="Stop", command=lambda: self._action("stop"))
        act_menu.add_command(label="Restart", command=lambda: self._action("restart"))
        act_menu.add_separator()
        act_menu.add_command(label="Start All", command=lambda: self._action_all("start"))
        act_menu.add_command(label="Stop All", command=lambda: self._action_all("stop"))
        act_menu.add_command(label="Restart All", command=lambda: self._action_all("restart"))
        menubar.add_cascade(label="Actions", menu=act_menu)

        prov_menu = tk.Menu(menubar, tearoff=0)
        prov_menu.add_command(label="Provision Bots", command=self._on_provision)
        menubar.add_cascade(label="Provision", menu=prov_menu)

        script_menu = tk.Menu(menubar, tearoff=0)
        script_menu.add_command(label="Help Bot", command=self._start_help_bot)
        script_menu.add_command(label="Stop Script", command=self._stop_scripts)
        menubar.add_cascade(label="Scripts", menu=script_menu)

        overlay_menu = tk.Menu(menubar, tearoff=0)
        self._overlay_global_var = tk.BooleanVar(value=settings.overlay_global_enabled())
        overlay_menu.add_checkbutton(
            label="Show Overlays", variable=self._overlay_global_var,
            command=self._on_overlay_global_toggle)
        overlay_menu.add_command(label="Show on Checked", command=lambda: self._overlay_checked(True))
        overlay_menu.add_command(label="Hide on Checked", command=lambda: self._overlay_checked(False))
        overlay_menu.add_separator()
        overlay_menu.add_command(label="Add Marker…", command=self._on_add_marker)
        overlay_menu.add_command(label="List Markers", command=self._on_list_markers)
        overlay_menu.add_command(label="Clear Markers on Checked", command=self._on_clear_markers)
        menubar.add_cascade(label="Overlay", menu=overlay_menu)

        sound_menu = tk.Menu(menubar, tearoff=0)
        self._sound_mode_var = tk.StringVar(value=settings.sound_mode())
        for label, mode in [("All Off", "all_off"), ("Viewer Control", "viewer"), ("All On", "all_on")]:
            sound_menu.add_radiobutton(
                label=label, value=mode, variable=self._sound_mode_var,
                command=self._on_sound_mode)
        menubar.add_cascade(label="Sound", menu=sound_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Open Viewers", command=self._open_viewers)
        menubar.add_cascade(label="View", menu=view_menu)

        logs_menu = tk.Menu(menubar, tearoff=0)
        logs_menu.add_command(label="Clear Logs", command=self._clear_logs)
        menubar.add_cascade(label="Logs", menu=logs_menu)
```

- [ ] **Step 3: Rewrite `_setup_toolbar` as icon bar**

```python
    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        for text, cmd in [
            ("▶ Start", lambda: self._action("start")),
            ("■ Stop", lambda: self._action("stop")),
            ("↻ Restart", lambda: self._action("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        for text, cmd in [
            ("▶▶ Start All", lambda: self._action_all("start")),
            ("■■ Stop All", lambda: self._action_all("stop")),
            ("↻↻ Restart All", lambda: self._action_all("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Help Bot", command=self._start_help_bot).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop Script", command=self._stop_scripts).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Clear Status", command=lambda: self._status.config(text="Ready")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear Logs", command=self._clear_logs).pack(side=tk.LEFT, padx=2)
```

- [ ] **Step 4: Extend bot rows with new columns**

Modify `_build_rows` row construction to add: status (glyph+text), activity (script+status), location (screen), CR, IV. Keep existing columns (snd, cpu, mem, pid, View). Example:

```python
    def _build_rows(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._rows.clear()
        for bot in self._manager.bots:
            row = ttk.Frame(self._list_frame)
            row.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar()
            ttk.Checkbutton(row, variable=var, width=2).pack(side=tk.LEFT)
            ttk.Label(row, text=bot.name, width=8).pack(side=tk.LEFT)
            acct = self._accounts.get(bot.name, "")
            ttk.Label(row, text=acct, width=18, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=f":{bot.display}", width=5).pack(side=tk.LEFT)
            status_lbl = ttk.Label(row, width=9)
            status_lbl.pack(side=tk.LEFT)
            status_tip = ToolTip(status_lbl, "")
            activity_lbl = ttk.Label(row, width=16, anchor=tk.W)
            activity_lbl.pack(side=tk.LEFT)
            loc_lbl = ttk.Label(row, width=12)
            loc_lbl.pack(side=tk.LEFT)
            cr_lbl = ttk.Label(row, width=4, anchor=tk.E)
            cr_lbl.pack(side=tk.LEFT)
            iv_lbl = ttk.Label(row, width=4, anchor=tk.E)
            iv_lbl.pack(side=tk.LEFT)
            snd_lbl = ttk.Label(row, width=2)
            snd_lbl.pack(side=tk.LEFT)
            cpu_lbl = ttk.Label(row, width=6, anchor=tk.E)
            cpu_lbl.pack(side=tk.LEFT)
            mem_lbl = ttk.Label(row, width=6, anchor=tk.E)
            mem_lbl.pack(side=tk.LEFT)
            pid_lbl = ttk.Label(row, width=10)
            pid_lbl.pack(side=tk.LEFT)
            ttk.Button(row, text="View", width=5,
                       command=lambda n=bot.name: self._on_view(n)).pack(side=tk.RIGHT, padx=1)
            self._rows[bot.name] = {
                "var": var, "status": status_lbl, "status_tip": status_tip,
                "activity": activity_lbl, "loc": loc_lbl, "cr": cr_lbl,
                "iv": iv_lbl, "snd": snd_lbl, "cpu": cpu_lbl, "mem": mem_lbl,
                "pid": pid_lbl,
            }
        self._update_rows()
```

Add a `ToolTip` class (small Tkinter tooltip helper) at module level:

```python
class ToolTip:
    """Simple hover tooltip for a widget."""
    def __init__(self, widget, text=""):
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def set_text(self, text: str):
        self._text = text

    def _show(self, _event=None):
        if not self._text:
            return
        x = self._widget.winfo_rootx() + 16
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = ttk.Label(self._tip, text=self._text, background="#ffffe0",
                        relief=tk.SOLID, borderwidth=1)
        lbl.pack()

    def _hide(self, _event=None):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
```

- [ ] **Step 5: Update `_update_rows`**

Populate the new columns each poll:

```python
    def _update_rows(self):
        gpu = self._manager.get_gpu_stats()
        ram = self._manager.get_system_ram()
        total_cpu = 0.0
        total_mem = 0
        running_count = 0
        for bot in self._manager.bots:
            r = self._rows.get(bot.name)
            if not r:
                continue
            self._manager._refresh_state(bot)
            # Status glyph + text + tooltip
            glyph, state_text = self._status_glyph(bot)
            r["status"].config(text=f"{glyph} {state_text}", foreground=self._status_color(bot))
            r["status_tip"].set_text(self._status_tooltip(bot))
            # Location + activity
            frame = self._read_frame(bot.display)
            loc = self._detect_location(bot, frame)
            r["loc"].config(text=loc or "?")
            runner = self._runners.get(bot.name)
            if runner and runner.script:
                status = None
                if frame is not None:
                    status = runner.tick(frame)
                r["activity"].config(text=f"{runner.script.name}:{status or 'running'}")
            else:
                r["activity"].config(text="")
            # CR / IV
            r["cr"].config(text=str(bot.crash_count))
            r["iv"].config(text=str(bot.intervention_count))
            # Sound + cpu + mem + pid
            muted = audio.is_muted(bot.pid) if bot.pid else None
            r["snd"].config(text="🔇" if muted is True else "🔊" if muted is False else "—")
            if bot.state == BotState.RUNNING:
                running_count += 1
                s = self._manager.get_process_stats(bot)
                if s:
                    r["cpu"].config(text=f"{s['cpu_percent']:.0f}")
                    r["mem"].config(text=f"{s['rss_mb']}M")
                    r["pid"].config(text=str(s['pid']))
                    total_cpu += s['cpu_percent']
                    total_mem += s['rss_mb']
                else:
                    r["cpu"].config(text="")
                    r["mem"].config(text="")
                    r["pid"].config(text=str(bot.pid) if bot.pid else "")
            else:
                r["cpu"].config(text="")
                r["mem"].config(text="")
                r["pid"].config(text=str(bot.pid) if bot.pid else "")
        self._status.config(...)  # existing summary
```

Add helper methods:

```python
    def _status_glyph(self, bot) -> tuple[str, str]:
        if bot.state == BotState.RUNNING:
            return "●", "Running"
        if bot.state == BotState.STARTING:
            return "◐", "Starting"
        if bot.state in (BotState.OFFLINE, BotState.ERROR):
            return "✕", bot.state.value
        return "●", bot.state.value

    def _status_color(self, bot) -> str:
        if bot.state == BotState.RUNNING:
            return "green"
        if bot.state == BotState.STARTING:
            return "gold"
        if bot.state in (BotState.OFFLINE, BotState.ERROR):
            return "red"
        return "black"

    def _status_tooltip(self, bot) -> str:
        runner = self._runners.get(bot.name)
        script = runner.script.name if runner and runner.script else ""
        loc = self._detect_location(bot, self._read_frame(bot.display))
        base = f"{bot.state.value} — {script or 'no script'}, in {loc or '?'}"
        if getattr(bot, "intervention_count", 0) > 0:
            base += f", {bot.intervention_count} interventions"
        return base

    def _detect_location(self, bot, frame):
        if frame is None:
            return "?"
        if monitor.frame_is_blank(frame):
            return "blank"
        return monitor.detect_screen(frame, self._nav_table())
```

Add `_nav_table()` to load nav_table.json:

```python
    def _nav_table(self) -> dict:
        import os
        p = os.path.expanduser("~/.config/gt-spector/nav_table.json")
        try:
            import json
            return json.loads(open(p).read())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"states": {}}
```

- [ ] **Step 6: Add overlay/sound/settings handlers**

```python
    def _on_overlay_global_toggle(self):
        overlay.set_overlay_enabled(None, self._overlay_global_var.get())
        logs.log_system(f"overlay global = {self._overlay_global_var.get()}")

    def _overlay_checked(self, enabled: bool):
        for bot in self._get_checked():
            overlay.set_overlay_enabled(bot.display, enabled)
            logs.log_system(f"overlay {bot.name} = {enabled}")

    def _on_add_marker(self):
        import tkinter.simpledialog as sd
        x = sd.askinteger("Add Marker", "x:", parent=self._tk)
        if x is None:
            return
        y = sd.askinteger("Add Marker", "y:", parent=self._tk)
        if y is None:
            return
        label = sd.askstring("Add Marker", "label (optional):", parent=self._tk) or ""
        for bot in self._get_checked():
            overlay.add_marker(bot.display, x, y, label)
        self._status.config(text=f"Markers added to {len(self._get_checked())} bots")

    def _on_list_markers(self):
        win = tk.Toplevel(self._tk)
        win.title("Markers")
        for bot in self._get_checked():
            ttk.Label(win, text=f"=== {bot.name} ===", font=("", 10, "bold")).pack(anchor=tk.W)
            markers = overlay.load_markers(bot.display)
            if not markers:
                ttk.Label(win, text="  No markers").pack(anchor=tk.W)
            for m in markers:
                ttk.Label(win, text=f"  {m.id} @ ({m.x},{m.y}) label='{m.label}'").pack(anchor=tk.W)

    def _on_clear_markers(self):
        for bot in self._get_checked():
            overlay.clear_markers(bot.display)
        self._status.config(text="Markers cleared")

    def _on_sound_mode(self):
        settings.set_sound_mode(self._sound_mode_var.get())
        self._apply_sound_policy()
        logs.log_system(f"sound mode = {settings.sound_mode()}")

    def _apply_sound_policy(self):
        mode = settings.sound_mode()
        for bot in self._manager.bots:
            if mode == "all_off":
                audio.set_muted(bot.pid, True)
            elif mode == "all_on":
                audio.set_muted(bot.pid, False)
            # viewer mode: per-bot sound_muted governs; viewers set it directly

    def _open_viewers(self):
        for bot in self._get_checked():
            self._manager.attach_viewer(bot)
        self._status.config(text="Viewers opened")

    def _clear_logs(self):
        logs.clear_all_logs()
        self._status.config(text="Logs cleared")

    def _on_settings(self):
        import tkinter.simpledialog as sd
        cur = settings.log_max_bytes() // 1024
        val = sd.askinteger("Settings", f"Log rotation size (KB):", parent=self._tk,
                            initialvalue=cur, minvalue=1)
        if val:
            settings.set_log_max_bytes(val * 1024)
            logs.log_system(f"log_max_bytes = {val * 1024}")
```

- [ ] **Step 7: Wire monitoring into the poll loop**

Add a `self._monitor = BotMonitor(self._manager)` in `__init__` and extend `_poll`:

```python
    def _poll(self):
        self._update_rows()
        self._monitor_tick()
        self._tk.after(2000, self._poll)

    def _monitor_tick(self):
        for bot in self._manager.bots:
            if bot.state != BotState.RUNNING or not bot.pid:
                continue
            runner = self._runners.get(bot.name)
            if not self._monitor.check_responsiveness(bot):
                self._monitor.mark_crash(bot)
                logs.log_bot(bot.name, "non-responsive, restarting game")
                self._manager.restart_game(bot)
                self._monitor.mark_intervention(bot)
                continue
            if runner and runner.script:
                expected = getattr(runner.script, "expected_screen", None)
                frame = self._read_frame(bot.display)
                if expected:
                    loc = self._detect_location(bot, frame)
                    if loc not in (None, expected):
                        logs.log_bot(bot.name, f"wrong screen {loc}, recovering")
                        self._monitor.recover(bot, lambda b, s: self._runners[b.name].run_script(s), runner.script)
```

Add `expected_screen = "ALLIANCE"` attribute to `HelpBot` in `gt_spector/scripts/help_bot.py`:

```python
class HelpBot:
    name = "help-bot"
    expected_screen = "ALLIANCE"
```

- [ ] **Step 8: Update `attach_viewer` to pass game PID**

In `gt_spector/bot_manager.py`, change `attach_viewer`:

```python
    def attach_viewer(self, bot: Bot) -> None:
        env = {"DISPLAY": ":0"}
        if bot.pid:
            env["GT_SPECTOR_GAME_PID"] = str(bot.pid)
        subprocess.Popen(
            ["/home/swong/dls/src/gt-spector/.venv/bin/python3", "-m", "gt_spector", "--session", f":{bot.display}"],
            env=env,
            cwd="/home/swong/dls/src/gt-spector",
        )
```

- [ ] **Step 9: Manual verification (Tkinter UI)**

Run the console on display :0:
```bash
DISPLAY=:0 python3 -m gt_spector --bot-console
```
Verify:
- Menu bar shows File, Selection, Actions, Provision, Scripts, Overlay, Sound, View, Logs.
- Icon bar shows grouped Start/Stop/Restart buttons + Help Bot/Stop Script + Clear Status/Clear Logs.
- Bot rows show glyph status, activity, location, CR/IV, sound.
- Hover over status shows tooltip.
- Overlay menu toggles global/per-bot; markers appear/disappear in a viewer.
- Sound menu switches modes; sound status column updates.
- Settings dialog changes log size; Clear Logs truncates log files.

- [ ] **Step 10: Commit**

```bash
git add viewer/bot_console.py gt_spector/script.py gt_spector/bot_manager.py gt_spector/scripts/help_bot.py
git commit -m "feat: console menu/icon-bar reorg, status columns, overlay/sound/logs controls"
```

---

### Task 7: Viewer overlay menu + sound toggle (`viewer/gui.py`)

**Files:**
- Modify: `viewer/gui.py`
- Manual test (Tkinter UI).

**Interfaces:**
- Consumes: Tasks 1-3 (`settings`, `overlay`, `audio`).
- Produces: viewer Overlay menu (toggle/list/clear/add), sound toggle button, mute-on-close in viewer mode.

- [ ] **Step 1: Add Overlay menu and Sound toggle to viewer**

Extend `_setup_menu` and `_setup_toolbar` in `ViewerWindow`:

```python
    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Capture Frame", command=self._capture)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        overlay_menu = tk.Menu(menubar, tearoff=0)
        self._display_num = int(self._session.display.lstrip(":"))
        self._overlay_var = tk.BooleanVar(value=overlay.overlay_enabled(self._display_num))
        overlay_menu.add_checkbutton(
            label="Show Markers", variable=self._overlay_var,
            command=self._on_overlay_toggle)
        overlay_menu.add_command(label="List Markers", command=self._on_viewer_list_markers)
        overlay_menu.add_command(label="Clear Markers", command=lambda: overlay.clear_markers(self._display_num))
        overlay_menu.add_command(label="Add Marker at Cursor", command=self._on_add_marker_at_cursor)
        menubar.add_cascade(label="Overlay", menu=overlay_menu)
```

In `_setup_toolbar` add a sound button:

```python
        self._game_pid = os.environ.get("GT_SPECTOR_GAME_PID")
        self._sound_btn = ttk.Button(toolbar, text=self._sound_icon(), command=self._on_sound_toggle)
        self._sound_btn.pack(side=tk.LEFT, padx=2)
```

Add handlers:

```python
    def _display_num(self) -> int:
        return int(self._session.display.lstrip(":"))

    def _on_overlay_toggle(self):
        overlay.set_overlay_enabled(self._display_num(), self._overlay_var.get())

    def _on_viewer_list_markers(self):
        win = tk.Toplevel(self._tk)
        win.title("Markers")
        for m in overlay.load_markers(self._display_num()):
            ttk.Label(win, text=f"{m.id} @ ({m.x},{m.y}) label='{m.label}'").pack(anchor=tk.W)

    def _on_add_marker_at_cursor(self):
        # reuse last known frame position if available, else prompt
        pos = getattr(self, "_last_frame_pos", None)
        if pos:
            overlay.add_marker(self._display_num(), pos[0], pos[1], "cursor")
        else:
            import tkinter.simpledialog as sd
            x = sd.askinteger("Add Marker", "x:", parent=self._tk)
            y = sd.askinteger("Add Marker", "y:", parent=self._tk)
            if x is not None and y is not None:
                overlay.add_marker(self._display_num(), x, y)

    def _sound_icon(self) -> str:
        if self._game_pid:
            return "🔇" if audio.is_muted(int(self._game_pid)) else "🔊"
        return "—"

    def _on_sound_toggle(self):
        if not self._game_pid:
            self._status.config(text="No game pid for sound control")
            return
        muted = audio.is_muted(int(self._game_pid))
        audio.set_muted(int(self._game_pid), not muted)
        self._sound_btn.config(text=self._sound_icon())
```

Track last frame cursor position in `_on_mouse_move`:

```python
    def _on_mouse_move(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._last_frame_pos = (fx, fy)
        ...
```

- [ ] **Step 2: Mute on close in viewer mode**

Change `_on_close`:

```python
    def _on_close(self):
        if self._game_pid:
            try:
                if settings.sound_mode() == "viewer":
                    audio.set_muted(int(self._game_pid), True)
            except (ValueError, OSError):
                pass
        self._running = False
        self._tk.destroy()
```

Add imports at top of `viewer/gui.py`:

```python
import os
from gt_spector import audio, overlay, settings
```

- [ ] **Step 3: Manual verification**

Run a viewer with the game PID set:
```bash
DISPLAY=:0 GT_SPECTOR_GAME_PID=33425 python3 -m gt_spector --session :10
```
Verify:
- Overlay menu toggles markers on/off.
- Sound button toggles mute; sound column in console reflects it.
- Closing the viewer with sound mode = viewer mutes the bot (`pactl list short sink-inputs` shows Mute: yes).

- [ ] **Step 4: Run existing tests + lint**

Run: `pytest tests/ -v`
Run: `ruff check gt_spector/ viewer/`
Run: `mypy gt_spector/`
Expected: all pass / clean

- [ ] **Step 5: Commit**

```bash
git add viewer/gui.py
git commit -m "feat: viewer overlay menu, sound toggle, mute on close"
```

---

## Self-Review Notes

- Spec coverage: overlay control (T1/T2/T6/T7), sound control (T3/T6/T7), menu reorg + icon bar (T6), status columns incl. glyphs/tooltip (T6), CR/IV (T5/T6), monitoring/recovery (T5/T6), logging (T4/T6), settings persistence (T1/T2/T6).
- Deferred/not-covered: VLM round-robin screen checks (Task 5 implements `detect_screen` via fingerprints; the throttled VLM 1/4-scale path is noted but not fully implemented — flagged as a follow-up), `apply_sound_policy` viewer-mode per-bot wiring (partial in T6).
