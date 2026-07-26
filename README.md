# gt-spector — Game Testing Inspector

**Peek into headless GPU-accelerated game instances. CLI for agents, GUI for humans.**

Inspects headless game farms running on DXVK offscreen swapchains. Provides per-instance frame capture, pixel-level queries, mouse/keyboard input, and color-based event triggers — all through a simple Python API that agents can script. Desktop GUI for human debugging with frame display, pixel readout, and session management.

## Quick Start

```python
from gt_spector import Session

s = Session(":9", source="file:///tmp/frame.png")
px = s.get_pixel(100, 200)         # (R, G, B)
area = s.capture_area(0, 0, 200, 100)  # numpy array
s.click(300, 400)                  # move + click
s.wait_for_color(100, 200, (120,130), (140,150), timeout=600)
```

CLI mode: `gt-spector --session :9 --cli`
GUI: `gt-spector --session :9`

## Architecture

```
Game Instance (DXVK offscreen) → SHM → Session → numpy → agent API / GUI
              xdotool ← Session.input ← agent / GUI
```

## Repository

```bash
git clone https://github.com/<owner>/gt-spector
cd gt-spector
```

## Project Structure

```
gt-spector/
  README.md
  AGENTS.md
  gt_spector/          ← Python library
    __init__.py
    session.py          per-instance handle
    screen.py           capture_area, get_pixel
    input.py            move_mouse, click, drag
    triggers.py          wait_for_color, wait_for_match
  viewer/              ← Desktop app
    __main__.py
    cli.py
    gui.py
  docs/
    superpowers/specs/ ← design docs
```

## Status

- [ ] dls_bot_lib — agent API (file-backed first)
- [ ] viewer GUI — frame display, pixel readout, session management
- [ ] viewer CLI — stdin command processor
- [ ] DXVK readback — queue-ordered copy → SHM
- [ ] Integration — SHM backend for Session
