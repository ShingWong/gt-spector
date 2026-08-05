# gt-spector — Design Document

**Date:** 2026-07-26
**Status:** Approved design, pre-implementation

## Overview

gt-spector is a game testing inspector for headless GPU-accelerated game instances running with DXVK offscreen swapchains. It provides per-instance frame capture, pixel-level queries, mouse/keyboard input, and color-based event triggers through a Python library that agents can script, plus a desktop GUI for human debugging.

## Architecture

```
Game Instance (DXVK offscreen) → SHM → Python Session → numpy → agent API / GUI
              xdotool ← Session.input ← agent / GUI
```

The stack:
- **DXVK (C++)** — writes raw BGRA frames to SHM in `presentImage` via queue-ordered copy submit
- **Python Session** — reads frames via `mmap`, exposes numpy arrays; sends input via `xdotool` subprocess
- **all heavy ops** — numpy, PIL, OpenCV (all C/C++ bindings under the hood, no pure-Python pixel loops)

## Components

### 1. gt_spector Library (`gt_spector/`)

The core library. No GUI dependencies — pure Python + numpy + PIL.

**`Session`** — single entry point for agents and GUI:

```python
class Session:
    # Attach to a headless instance
    session = Session(
        display=":9",               # DISPLAY target for xdotool
        source="shm://gt-spector-9", # "file:///tmp/frame.png" for dev
        fps=5,                       # frame polling rate
    )

    # Screen queries (numpy-backed, fast)
    px = session.get_pixel(x, y)              # → (R, G, B)
    area = session.capture_area(x1, y1, x2, y2)  # → ndarray[H, W, 3]
    frame = session.frame                     # → latest ndarray[H, W, 3]

    # Input (xdotool subprocess, async)
    session.move_mouse(x, y, speed=400)       # pixels/sec, blocks until arrival
    session.click(x, y, speed=400)            # move then click
    session.drag(x1, y1, x2, y2, speed=400)   # press, drag, release
    session.key_press(key)                     # e.g. "Return", "Escape"
    session.type_text("hello")                 # keyboard input

    # Triggers (blocking, timeout in seconds)
    session.wait_for_color(x, y, lo, hi, timeout=600)
    session.wait_for_match(template, region=None, timeout=600)
    session.wait_for_change(region=None, timeout=600)
```

All triggers return `(bool, frame)` — success flag + frame that triggered it.

**Source abstraction:** `Session` takes a `source` parameter. First milestone uses `"file:///path/to/frame.png"` (reads a static file in a loop). Later, `"shm://gt-spector-N"` maps the DXVK shared memory region. The `.frame` property hides this behind a uniform interface.

**Files:**
- `gt_sporer/__init__.py` — Session, public API exports
- `gt_spector/session.py` — Session class, source abstraction
- `gt_spector/screen.py` — capture_area, get_pixel (numpy views)
- `gt_spector/input.py` — move_mouse, click, drag, key_press, type_text (xdotool subprocess)
- `gt_spector/triggers.py` — wait_for_color, wait_for_match, wait_for_change (event loop + timeout)

### 2. Viewer (`viewer/`)

Desktop tkinter app for human debugging. Single-window per session.

**GUI layout:**
- Menu bar: File, Session, Capture, Help
- Toolbar: Attach, Detach, Capture buttons
- Frame display: tkinter Canvas with PIL.ImageTk, scaled to fit
- Status bar: pixel color at cursor, cursor coordinates

**CLI mode (`--cli`):** stdin/stdout command processor. All commands produce machine-parseable output. Pipe-friendly for agent integration.

**Entry point:** `python -m gt_spector --session :9 [--cli]`

### 3. DXVK Readback (future milestone)

In `dxvk_presenter.cpp`, inside `presentImage` when `m_offscreen` is true:
- Submit a `vkCmdCopyImageToBuffer` command buffer to the graphics queue (no wait semaphores — queue ordering guarantees execution after the game's render)
- Signal a fence on copy completion
- On next presentImage call, wait for the fence, map staging buffer, memcpy to SHM
- One staging buffer per swapchain image, one SHM region per instance

## Key Constraints

- `vkQueueSubmit` with any wait semaphore crashes on RADV 25.0.7 + libvulkan 1.4.309
- Workaround: queue-ordered submits (same queue, no wait semaphores)
- DXVK offscreen swapchain already proven stable

## Milestones

1. **Library + Viewer (file-backed):** Session API with file source, CLI, GUI with frame display, pixel readout. No DXVK readback needed yet — test with a static PNG.
2. **DXVK Readback:** Queue-ordered copy → staging buffer → SHM. Replace file source with SHM source in Session.
3. **Integration:** End-to-end — game renders → SHM → viewer shows live frames → agent sends input.
4. **Polish:** triggers, template matching, multi-session, performance tuning.

## Quality Gates

- Build passes (C++ DXVK, Python package)
- Tests pass (pytest)
- Lint passes (ruff, mypy)
- Self-review before claiming done
- Clean commits (no debug code, no commented-out code)
