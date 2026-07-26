# Session Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session attach/detach to the Session class, CLI, and GUI. Add `wait_for_color`, `wait_for_change` triggers. Add `--list-sessions` CLI to show active SHM instances.

**Architecture:** Session gains `attach(display, source)` to swap targets at runtime. Triggers use a blocking poll loop with timeout, reading the frame and checking pixel/area conditions. `--list-sessions` scans `/dev/shm/` for active SHM files.

**Tech Stack:** Python, numpy, xdotool

## Global Constraints

- Attach swaps both the frame source (screen) and input target (xdotool DISPLAY)
- Triggers block until condition met or timeout, return `(bool, frame)`
- `--list-sessions` scans `/dev/shm/gt-spector-*-frame` and reads headers

---

### Task 1: Session Attach/Detach

**Files:**
- Modify: `gt_spector/session.py` — add `attach()` and `detach()` methods
- Create: `tests/test_session_attach.py`

**Interfaces:**
- Consumes: `Session` with `display`, `_screen`, `_input`
- Produces: `Session.attach(display, source)` and `Session.detach()`

- [ ] **Step 1: Add attach/detach to session.py**

```python
    def attach(self, display: str, source: str = "") -> None:
        from .source import parse_source, SourceKind
        self.display = display
        spec = parse_source(source)
        if spec.kind == SourceKind.FILE:
            from .screen import Screen
            self._screen = Screen(spec.path)
        elif spec.kind == SourceKind.SHM:
            from .screen import ShmScreen
            self._screen = ShmScreen(spec.path)
        else:
            raise NotImplementedError(f"Source kind {spec.kind}")
        from .input import Input
        self._input = Input(display)

    def detach(self) -> None:
        from .screen import Screen
        self._screen = Screen("/dev/null")
        self._input = Input(":0")
```

- [ ] **Step 2: Write test**

```python
def test_session_attach(tmp_path):
    from gt_spector import Session
    from PIL import Image
    img = Image.new("RGB", (50, 50), color=(0, 255, 0))
    p1 = str(tmp_path / "green.png")
    img.save(p1)
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    p2 = str(tmp_path / "red.png")
    img.save(p2)

    s = Session(":9", source=f"file://{p1}")
    assert s.get_pixel(0, 0) == (0, 255, 0)
    s.attach(":0", source=f"file://{p2}")
    assert s.get_pixel(0, 0) == (255, 0, 0)
    s.detach()
```

- [ ] **Step 3: Run tests and commit**

---

### Task 2: GUI Attach/Detach Dialog

**Files:**
- Modify: `viewer/gui.py` — wire toolbar buttons, add attach dialog

**Interfaces:**
- Consumes: `Session.attach(display, source)` from Task 1
- Produces: working Attach/Detach buttons in the viewer toolbar

- [ ] **Step 1: Add attach dialog and wire buttons**

```python
    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="Attach", command=self._on_attach).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Detach", command=self._on_detach).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Capture", command=self._capture).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Quit", command=self._on_close).pack(side=tk.LEFT, padx=2)

    def _on_attach(self):
        import tkinter.simpledialog
        display = tkinter.simpledialog.askstring(
            "Attach Session", "Display (e.g. :9):", parent=self._tk)
        if not display:
            return
        source = f"shm://{display.lstrip(':')}"
        try:
            self._session.attach(display, source)
            self._tk.title(f"gt-spector — {display}")
            self._status.config(text=f"Attached: {display}")
        except Exception as e:
            self._status.config(text=f"Attach error: {e}")

    def _on_detach(self):
        self._session.detach()
        self._tk.title("gt-spector — detached")
        self._status.config(text="Detached")
```

- [ ] **Step 2: Verify GUI builds**

```bash
python3 -c "from viewer.gui import ViewerWindow, run_gui; print('ok')"
```

- [ ] **Step 3: Test and commit**

---

### Task 3: Triggers — wait_for_color, wait_for_change

**Files:**
- Create: `gt_spector/triggers.py`
- Modify: `gt_spector/session.py` — wire trigger methods
- Create: `tests/test_triggers.py`

**Interfaces:**
- Consumes: `Session.frame`, `Session.get_pixel()`
- Produces: `Session.wait_for_color(x, y, lo, hi, timeout=600)` and `Session.wait_for_change(region=None, timeout=600)`

- [ ] **Step 1: Create triggers.py**

```python
import time
import numpy as np

class Triggers:
    def __init__(self, session):
        self._session = session

    def wait_for_color(
        self, x: int, y: int,
        lo: tuple[int, int, int],
        hi: tuple[int, int, int],
        timeout: float = 600,
    ) -> tuple[bool, np.ndarray]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._session.refresh()
            px = self._session.get_pixel(x, y)
            if all(lo[i] <= px[i] <= hi[i] for i in range(3)):
                return True, self._session.frame
            time.sleep(0.1)
        return False, self._session.frame

    def wait_for_change(
        self, region: tuple[int, int, int, int] | None = None,
        timeout: float = 600,
    ) -> tuple[bool, np.ndarray]:
        deadline = time.monotonic() + timeout
        baseline = self._session.frame.copy()
        while time.monotonic() < deadline:
            self._session.refresh()
            curr = self._session.frame
            if region:
                x1, y1, x2, y2 = region
                if not np.array_equal(curr[y1:y2, x1:x2], baseline[y1:y2, x1:x2]):
                    return True, curr
            else:
                if not np.array_equal(curr, baseline):
                    return True, curr
            time.sleep(0.1)
        return False, self._session.frame
```

- [ ] **Step 2: Wire into Session**

```python
    @property
    def triggers(self):
        from .triggers import Triggers
        return Triggers(self)
```

Usage: `session.triggers.wait_for_color(100, 200, (120,130), (140,150), timeout=600)`

- [ ] **Step 3: Write tests**

```python
import numpy as np
from PIL import Image

def test_wait_for_color(tmp_path):
    from gt_spector.triggers import Triggers
    from gt_spector.screen import Screen
    img = Image.new("RGB", (100, 100), color=(50, 100, 150))
    p = str(tmp_path / "test.png")
    img.save(p)
    sc = Screen(p)
    class FakeSession:
        frame = sc.frame
        refresh = sc.refresh
        get_pixel = sc.get_pixel
    t = Triggers(FakeSession())
    ok, frame = t.wait_for_color(50, 50, (40, 90, 140), (60, 110, 160), timeout=1)
    assert ok
    ok, frame = t.wait_for_color(50, 50, (0, 0, 0), (10, 10, 10), timeout=0.5)
    assert not ok

def test_wait_for_change(tmp_path):
    from gt_spector.triggers import Triggers
    from PIL import Image
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    p = str(tmp_path / "test2.png")
    img.save(p)
    from gt_spector.screen import Screen
    sc = Screen(p)
    called = [0]
    class FakeSession:
        frame = sc.frame
        def refresh(self):
            called[0] += 1
        get_pixel = sc.get_pixel
    t = Triggers(FakeSession())
    ok, frame = t.wait_for_change(timeout=0.5)
    assert not ok  # No change in static file
```

- [ ] **Step 4: Run tests and commit**

---

### Task 4: CLI --list-sessions

**Files:**
- Modify: `gt_spector/session.py` — add `list_sessions()` static method
- Modify: `gt_spector/__main__.py` — add `--list-sessions` flag

- [ ] **Step 1: Add list_sessions to session.py**

```python
    @staticmethod
    def list_sessions() -> list[dict]:
        import glob, struct
        sessions = []
        for path in glob.glob("/dev/shm/gt-spector-*-frame"):
            try:
                with open(path, "rb") as f:
                    data = f.read(16)
                    if len(data) >= 16:
                        counter, w, h = struct.unpack("<QII", data)
                        shm_id = path.split("-")[-1].replace("-frame", "")
                        sessions.append({
                            "id": shm_id,
                            "path": path,
                            "frame": counter,
                            "width": w,
                            "height": h,
                        })
            except Exception:
                pass
        return sessions
```

- [ ] **Step 2: Wire into CLI**

In `gt_spector/__main__.py`, before parsing args:

```python
    if "--list-sessions" in sys.argv:
        sessions = Session.list_sessions()
        if not sessions:
            print("No active sessions found")
        else:
            print(f"{'ID':<6} {'Frames':<10} {'Size':<12}")
            print("-" * 30)
            for s in sessions:
                print(f"{s['id']:<6} {s['frame']:<10} {s['width']}x{s['height']:<6}")
        sys.exit(0)
```

Usage: `python3 -m gt_spector --list-sessions`

- [ ] **Step 3: Test and commit**

---

### Task 5: End-to-End — Attach and trigger test

- [ ] **Step 1: Verify all tests pass**

```bash
cd /home/swong/dls/gt-spector && python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Commit remaining changes and finalize**

```bash
git add -A && git commit -m "docs: session management e2e verification"
```
