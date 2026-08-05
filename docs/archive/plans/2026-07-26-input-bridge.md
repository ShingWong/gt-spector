# Input Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mouse and keyboard input to the gt-spector Session, CLI, and GUI — allowing agents and humans to send clicks and keystrokes to headless game instances.

**Architecture:** Python subprocess calls to `xdotool` targeting the correct `DISPLAY=:N`. Session.input provides the agent API. CLI exposes commands. GUI forwards canvas clicks to the game at the correct coordinates (accounting for view scale).

**Tech Stack:** Python, xdotool, subprocess

## Global Constraints

- All input goes through `xdotool` subprocess calls targeting the session's `DISPLAY=:N`
- Mouse speed in pixels/sec: `move_mouse(x, y, speed=400)` — waits for the simulated travel time
- Session already has `display` attribute set in `__init__`
- `DISPLAY=:N` xdotool must work on the headless Xvfb displays (Xvfb processes already running)

---

### Task 1: Input Module

**Files:**
- Create: `gt_spector/input.py`
- Modify: `gt_spector/session.py` — wire input methods
- Create: `tests/test_input.py`

**Interfaces:**
- Consumes: `session.display` string (e.g., `:9`)
- Produces: `Session.move_mouse()`, `Session.click()`, `Session.drag()`, `Session.key_press()`, `Session.type_text()`

- [ ] **Step 1: Create input.py**

```python
import math
import subprocess
import time


class Input:
    def __init__(self, display: str):
        self._display = display
        self._env = {"DISPLAY": display}

    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        dx = 0
        dy = 0
        # Get current position for distance calculation
        try:
            out = subprocess.run(
                ["xdotool", "getmouselocation"],
                capture_output=True, text=True, env=self._env, timeout=5
            ).stdout
            parts = out.strip().split()
            cx = int(parts[0].split(":")[1])
            cy = int(parts[1].split(":")[1])
            dx = x - cx
            dy = y - cy
        except Exception:
            pass
        subprocess.run(
            ["xdotool", "mousemove", "--sync", str(x), str(y)],
            env=self._env, timeout=10
        )
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self.move_mouse(x, y, speed)
        subprocess.run(["xdotool", "click", "1"], env=self._env, timeout=5)

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        subprocess.run(
            ["xdotool", "mousemove", "--sync", str(x1), str(y1)],
            env=self._env, timeout=10
        )
        subprocess.run(["xdotool", "mousedown", "1"], env=self._env, timeout=5)
        subprocess.run(
            ["xdotool", "mousemove", "--sync", str(x2), str(y2)],
            env=self._env, timeout=10
        )
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx * dx + dy * dy)
        if distance > 0 and speed > 0:
            time.sleep(distance / speed)
        subprocess.run(["xdotool", "mouseup", "1"], env=self._env, timeout=5)

    def key_press(self, key: str) -> None:
        subprocess.run(["xdotool", "key", key], env=self._env, timeout=5)

    def type_text(self, text: str) -> None:
        subprocess.run(["xdotool", "type", text], env=self._env, timeout=30)
```

- [ ] **Step 2: Wire into Session**

In `gt_spector/session.py`, after `self._screen = ...`, add:
```python
        from .input import Input
        self._input = Input(display)
```

And add input methods:
```python
    def move_mouse(self, x: int, y: int, speed: float = 400) -> None:
        self._input.move_mouse(x, y, speed)

    def click(self, x: int, y: int, speed: float = 400) -> None:
        self._input.click(x, y, speed)

    def drag(self, x1: int, y1: int, x2: int, y2: int, speed: float = 400) -> None:
        self._input.drag(x1, y1, x2, y2, speed)

    def key_press(self, key: str) -> None:
        self._input.key_press(key)

    def type_text(self, text: str) -> None:
        self._input.type_text(text)
```

- [ ] **Step 3: Create test**

```python
def test_input_init():
    from gt_spector.input import Input
    inp = Input(":99")
    assert inp._display == ":99"
    assert inp._env == {"DISPLAY": ":99"}
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add gt_spector/input.py gt_spector/session.py tests/test_input.py
git commit -m "feat: input module with mouse/keyboard via xdotool"
```

---

### Task 2: CLI Input Commands

**Files:**
- Modify: `viewer/cli.py` — add move, click, drag, key, type commands

**Interfaces:**
- Consumes: `Session.input` methods from Task 1
- Produces: CLI `> move 300 400 400`, `> click 300 400`, etc.

- [ ] **Step 1: Add CLI commands to cli.py**

```python
    def do_move(self, arg):
        """move <x> <y> [speed] — Move mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: move <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.move_mouse(x, y, speed)
        print("ok")

    def do_click(self, arg):
        """click <x> <y> [speed] — Click mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: click <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.click(x, y, speed)
        print("ok")

    def do_drag(self, arg):
        """drag <x1> <y1> <x2> <y2> [speed] — Click-and-drag"""
        args = shlex.split(arg)
        if len(args) < 4:
            print("Usage: drag <x1> <y1> <x2> <y2> [speed]")
            return
        x1, y1, x2, y2 = map(int, args[:4])
        speed = int(args[4]) if len(args) > 4 else 400
        self._session.drag(x1, y1, x2, y2, speed)
        print("ok")

    def do_key(self, arg):
        """key <key> — Send keystroke (e.g. Return, Escape)"""
        key = arg.strip()
        if not key:
            print("Usage: key <key>")
            return
        self._session.key_press(key)
        print("ok")

    def do_type(self, arg):
        """type <text> — Type text"""
        text = arg.strip()
        if not text:
            print("Usage: type <text>")
            return
        self._session.type_text(text)
        print("ok")
```

- [ ] **Step 2: Test CLI commands parse**

Create `tests/test_cli.py`:
```python
def test_cli_commands_exist():
    from viewer.cli import CliSession
    from gt_spector.session import Session
    s = Session(":99")
    cli = CliSession.__new__(CliSession)
    cli._session = s
    assert hasattr(cli, "do_move")
    assert hasattr(cli, "do_click")
    assert hasattr(cli, "do_drag")
    assert hasattr(cli, "do_key")
    assert hasattr(cli, "do_type")
```

- [ ] **Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add viewer/cli.py tests/test_cli.py
git commit -m "feat: CLI input commands — move, click, drag, key, type"
```

---

### Task 3: GUI Click Forwarding

**Files:**
- Modify: `viewer/gui.py` — forward clicks on the canvas to the game

**Interfaces:**
- Consumes: `Session.click()` from Task 1, `Session.move_mouse()` from Task 1
- Produces: clicking on the viewer canvas forwards the click to the correct game coordinates

- [ ] **Step 1: Add click handler to ViewerWindow**

In `_setup_canvas()`, after the `<Motion>` bind, add:
```python
        self._canvas_label.bind("<Button-1>", self._on_canvas_click)
```

Add the handler:
```python
    def _on_canvas_click(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._session.click(fx, fy)
        self._status.config(text=f"Click: ({fx}, {fy})")
```

And add right-click for move-only:
```python
        self._canvas_label.bind("<Button-3>", self._on_canvas_right_click)
```

```python
    def _on_canvas_right_click(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._session.move_mouse(fx, fy)
        self._status.config(text=f"Move: ({fx}, {fy})")
```

- [ ] **Step 2: Verify GUI builds**

```bash
python3 -c "from viewer.gui import ViewerWindow, run_gui; print('GUI module ok')"
```

- [ ] **Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add viewer/gui.py
git commit -m "feat: GUI click forwarding — left click, right move"
```

---

### Task 4: End-to-End Verification

**Files:** None — runs existing code.

- [ ] **Step 1: Verify CLI input**

```bash
echo -e "move 200 200\nclick 300 400 400\nkey Return\ntype hello\nquit" | \
  DISPLAY=:9 python3 -m gt_spector --session :9 --source shm://9 --cli
```

Expected: commands execute without error.

- [ ] **Step 2: Verify GUI input**
Launch viewer, click on the canvas, verify the click reaches the game.

```bash
DISPLAY=:0 python3 -m gt_spector --source shm://9 --session :9
```

- [ ] **Step 3: Commit**

```bash
cd /home/swong/dls/gt-spector && git add -A && git commit -m "docs: input bridge e2e verification"
```
