# gt-spector Initial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the initial gt-spector library and viewer that reads a frame from a file and displays it in a desktop window with pixel readout.

**Architecture:** Python package `gt_spector` exposes `Session` class that reads frames from a file source. `viewer` package provides a tkinter GUI. CLI entry point via `python -m gt_spector`.

**Tech Stack:** Python 3.13, numpy, Pillow, tkinter (stdlib)

## Global Constraints

- All heavy ops must be in C/C++ bindings (numpy/PIL — no pure-Python pixel loops)
- Library has no GUI dependencies; viewer depends on stdlib tkinter only
- Session source abstraction must support file:// and later shm://
- Commits after each task with clean messages

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `gt_spector/__init__.py`
- Create: `viewer/__init__.py`
- Create: `tests/test_session.py`

**Interfaces:**
- Consumes: nothing
- Produces: installable package structure, test infrastructure

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "gt-spector"
version = "0.1.0"
description = "Game testing inspector"
requires-python = ">=3.11"
dependencies = [
    "numpy",
    "Pillow",
]
optional-dependencies = { dev = ["pytest", "ruff", "mypy"] }

[project.scripts]
gt-spector = "gt_spector.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
```

- [ ] **Step 2: Create package __init__.py**

```python
from .session import Session

__all__ = ["Session"]
```

- [ ] **Step 3: Create viewer __init__.py** (empty)

- [ ] **Step 4: Create test placeholder**

```python
def test_import():
    from gt_spector import Session
    assert Session is not None
```

- [ ] **Step 5: Verify import works**

Run: `python -c "from gt_spector import Session; print('ok')"`
Expected: prints "ok"

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml gt_spector/ viewer/ tests/
git commit -m "chore: initial project scaffold"
```

---

### Task 2: Session with File Source

**Files:**
- Create: `gt_spector/session.py`
- Create: `gt_spector/screen.py`
- Create: `gt_spector/source.py`
- Modify: `tests/test_session.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Session(display, source)` — `session.frame` → numpy ndarray (H, W, 3) in RGB

- [ ] **Step 1: Create source.py**

```python
import enum
import re
from dataclasses import dataclass

class SourceKind(enum.Enum):
    FILE = "file"
    SHM = "shm"

@dataclass
class SourceSpec:
    kind: SourceKind
    path: str

def parse_source(s: str) -> SourceSpec:
    m = re.match(r"(file|shm)://(.+)", s)
    if not m:
        raise ValueError(f"Invalid source: {s}")
    return SourceSpec(SourceKind(m.group(1)), m.group(2))
```

- [ ] **Step 2: Create screen.py** (pixel queries on numpy arrays)

```python
import numpy as np
from PIL import Image

class Screen:
    def __init__(self, source_path: str):
        self._source_path = source_path
        self._frame: np.ndarray | None = None

    def refresh(self) -> np.ndarray:
        img = Image.open(self._source_path)
        self._frame = np.asarray(img.convert("RGB"))
        return self._frame

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            return self.refresh()
        return self._frame

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return tuple(map(int, self.frame[y, x]))

    def capture_area(self, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        return self.frame[y1:y2, x1:x2].copy()
```

- [ ] **Step 3: Create session.py**

```python
from .source import parse_source, SourceKind
from .screen import Screen

class Session:
    def __init__(self, display: str, source: str = "file:///tmp/test-frame.png", fps: int = 5):
        self.display = display
        self.fps = fps
        spec = parse_source(source)
        if spec.kind == SourceKind.FILE:
            self._screen = Screen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind} not implemented")

    @property
    def frame(self):
        return self._screen.frame

    def refresh(self):
        return self._screen.refresh()

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return self._screen.get_pixel(x, y)

    def capture_area(self, x1: int, y1: int, x2: int, y2: int):
        return self._screen.capture_area(x1, y1, x2, y2)
```

- [ ] **Step 4: Write and run test**

```python
def test_session_file_source(tmp_path):
    from gt_spector import Session
    import numpy as np
    from PIL import Image

    # Create a small test image
    img = Image.new("RGB", (100, 50), color=(255, 0, 0))
    path = str(tmp_path / "test.png")
    img.save(path)

    s = Session(":9", source=f"file://{path}")
    assert s.frame.shape == (50, 100, 3)
    assert s.get_pixel(0, 0) == (255, 0, 0)
    area = s.capture_area(0, 0, 50, 25)
    assert area.shape == (25, 50, 3)
```

Run: `pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gt_spector/source.py gt_spector/screen.py gt_spector/session.py tests/test_session.py
git commit -m "feat: Session with file source, pixel queries"
```

---

### Task 3: Test Pattern Generator

**Files:**
- Create: `gt_spector/test_pattern.py`
- Create: `tests/test_test_pattern.py`

**Interfaces:**
- Consumes: nothing
- Produces: `generate_test_pattern(path, width=1152, height=864)` — creates a recognizable test PNG

- [ ] **Step 1: Create test_pattern.py**

```python
import numpy as np
from PIL import Image

def generate_test_pattern(
    path: str,
    width: int = 1152,
    height: int = 864,
) -> str:
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 30    # dark red background
    arr[50:100, 50:200] = [255, 0, 0]    # red rectangle
    arr[200:250, 50:200] = [0, 255, 0]   # green rectangle
    arr[350:400, 50:200] = [0, 0, 255]   # blue rectangle
    arr[500:550, 50:200] = [255, 255, 0] # yellow rectangle

    arr[50:100, 400:800, :] = [200, 200, 200] # gray bar for text-like area

    Image.fromarray(arr).save(path)
    return path
```

- [ ] **Step 2: Write and run test**

```python
def test_generate_test_pattern(tmp_path):
    from gt_spector.test_pattern import generate_test_pattern
    from PIL import Image

    p = generate_test_pattern(str(tmp_path / "pattern.png"), width=100, height=50)
    img = Image.open(p)
    assert img.size == (100, 50)
```

Run: `pytest tests/test_test_pattern.py -v`
Expected: PASS

- [ ] **Step 3: Generate the test frame**

```bash
python -c "from gt_spector.test_pattern import generate_test_pattern; generate_test_pattern('/tmp/test-frame.png')"
```

Verify: `ls -la /tmp/test-frame.png`

- [ ] **Step 4: Commit**

```bash
git add gt_spector/test_pattern.py tests/test_test_pattern.py
git commit -m "feat: test pattern generator"
```

---

### Task 4: Viewer GUI

**Files:**
- Create: `viewer/gui.py`
- Create: `viewer/cli.py`
- Modify: `gt_spector/__init__.py`

**Interfaces:**
- Consumes: `Session(display, source)` from Task 2
- Produces: `run_gui(session)` — opens tkinter window, shows frame with pixel readout

- [ ] **Step 1: Create gui.py**

```python
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import numpy as np

class ViewerWindow:
    def __init__(self, session):
        self._session = session
        self._tk = tk.Tk()
        self._tk.title(f"gt-spector — {session.display}")
        self._setup_menu()
        self._setup_toolbar()
        self._setup_canvas()
        self._setup_statusbar()
        self._running = True
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Capture Frame", command=self._capture)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="Capture", command=self._capture).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Quit", command=self._on_close).pack(side=tk.LEFT, padx=2)

    def _setup_canvas(self):
        self._frame = ttk.Frame(self._tk)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._canvas_label = ttk.Label(self._frame)
        self._canvas_label.pack()
        self._canvas_label.bind("<Motion>", self._on_mouse_move)

    def _setup_statusbar(self):
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _poll(self):
        if not self._running:
            return
        try:
            self._session.refresh()
            frame = self._session.frame
            h, w = frame.shape[:2]
            max_size = 800
            scale = min(max_size / w, max_size / h, 1.0)
            nw, nh = int(w * scale), int(h * scale)
            img = Image.fromarray(frame).resize((nw, nh), Image.NEAREST)
            self._tk_photo = ImageTk.PhotoImage(img)
            self._canvas_label.config(image=self._tk_photo)
            self._img_w, self._img_h = nw, nh
            self._scale = scale
        except Exception as e:
            self._status.config(text=f"Error: {e}")
        delay = max(50, int(1000 / self._session.fps))
        self._tk.after(delay, self._poll)

    def _on_mouse_move(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        try:
            r, g, b = self._session.get_pixel(fx, fy)
            self._status.config(text=f"Pixel: ({fx}, {fy}) → RGB({r}, {g}, {b})")
        except Exception:
            pass

    def _capture(self):
        from datetime import datetime
        path = f"/tmp/gt-spector-capture-{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        img = Image.fromarray(self._session.frame)
        img.save(path)
        self._status.config(text=f"Captured: {path}")

    def _on_close(self):
        self._running = False
        self._tk.destroy()

    def run(self):
        self._tk.mainloop()


def run_gui(session):
    w = ViewerWindow(session)
    w.run()
```

- [ ] **Step 2: Create cli.py**

```python
import cmd
import sys
import shlex

class CliSession(cmd.Cmd):
    intro = "gt-spector CLI. Type help or ? to list commands."
    prompt = "> "

    def __init__(self, session):
        super().__init__()
        self._session = session

    def do_pixel(self, arg):
        """pixel <x> <y> — Get pixel color"""
        args = shlex.split(arg)
        if len(args) != 2:
            print("Usage: pixel <x> <y>")
            return
        x, y = int(args[0]), int(args[1])
        r, g, b = self._session.get_pixel(x, y)
        print(f"({r}, {g}, {b})")

    def do_capture(self, arg):
        """capture [path] — Capture frame to PNG"""
        from datetime import datetime
        path = arg or f"/tmp/gt-spector-capture-{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        from PIL import Image
        img = Image.fromarray(self._session.frame)
        img.save(path)
        print(f"captured {path}")

    def do_EOF(self, arg):
        print()
        return True

    def do_quit(self, arg):
        return True


def run_cli(session):
    CliSession(session).cmdloop()
```

- [ ] **Step 3: Create __main__.py** (CLI entry point)

```python
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="gt-spector: game testing inspector")
    parser.add_argument("--session", default=":9", help="DISPLAY target")
    parser.add_argument("--source", default="file:///tmp/test-frame.png", help="Frame source")
    parser.add_argument("--cli", action="store_true", help="CLI mode instead of GUI")
    args = parser.parse_args()

    from .session import Session
    session = Session(args.session, source=args.source)

    if args.cli:
        from viewer.cli import run_cli
        run_cli(session)
    else:
        from viewer.gui import run_gui
        run_gui(session)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify GUI launches**

```bash
python -m gt_spector --session :9 --source file:///tmp/test-frame.png &
sleep 2
kill %1 2>/dev/null
```

Expected: window opens briefly showing test pattern, then closes.

- [ ] **Step 5: Verify CLI mode**

```bash
echo -e "pixel 60 75\nquit" | python -m gt_spector --session :9 --cli
```

Expected: `(255, 0, 0)` printed (top-left red rectangle)

- [ ] **Step 6: Commit**

```bash
git add viewer/ gt_spector/__main__.py
git commit -m "feat: viewer GUI and CLI with frame display and pixel readout"
```

---

### Task 5: Lock down with tests

**Files:**
- Create: `tests/test_screen.py`
- Create: `tests/test_viewer.py`

- [ ] **Step 1: Test screen operations**

```python
import numpy as np
from PIL import Image

def test_get_pixel(tmp_path):
    from gt_spector.screen import Screen
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    p = str(tmp_path / "pixel.png")
    img.save(p)
    sc = Screen(p)
    pixel = sc.get_pixel(25, 25)
    assert pixel == (10, 20, 30)

def test_capture_area(tmp_path):
    from gt_spector.screen import Screen
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    p = str(tmp_path / "area.png")
    img.save(p)
    sc = Screen(p)
    area = sc.capture_area(10, 10, 30, 30)
    assert area.shape == (20, 20, 3)
    assert tuple(area[0, 0]) == (255, 0, 0)
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_screen.py
git commit -m "test: screen operation tests"
```
