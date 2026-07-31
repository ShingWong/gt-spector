"""Persistent screen markers drawn into the viewer frame pipeline.

Stores marker data in a JSON file. The viewer reads and draws them
onto each frame before display. No X11 dependency.

Usage:
  python -m gt_spector.overlay <display> mark <x> <y> [label]
  python -m gt_spector.overlay <display> clear [id]
  python -m gt_spector.overlay <display> list
  python -m gt_spector.overlay <display> toggle
  python -m gt_spector.overlay <display> status
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from gt_spector import settings as _settings

MARKER_DIR = Path.home() / ".config" / "gt-spector"


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


@dataclass
class Marker:
    id: str
    x: int
    y: int
    r: int = 0
    g: int = 255
    b: int = 0
    label: str = ""
    visible: bool = True


def _markers_path(display: int) -> Path:
    return MARKER_DIR / f"markers_d{display}.json"


def load_markers(display: int) -> list[Marker]:
    path = _markers_path(display)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [Marker(**m) for m in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def save_markers(display: int, markers: list[Marker]) -> None:
    path = _markers_path(display)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(m) for m in markers], indent=2))


def add_marker(display: int, x: int, y: int, label: str = "",
               r: int = 0, g: int = 255, b: int = 0) -> Marker:
    markers = load_markers(display)
    mid = label if label else f"m{x}_{y}"
    # Remove existing with same id
    markers = [m for m in markers if m.id != mid]
    m = Marker(id=mid, x=x, y=y, r=r, g=g, b=b, label=label)
    markers.append(m)
    save_markers(display, markers)
    return m


def clear_markers(display: int, mid: str | None = None) -> None:
    markers = load_markers(display)
    if mid is None:
        markers.clear()
    else:
        markers = [m for m in markers if m.id != mid]
    save_markers(display, markers)


def draw_markers(frame: np.ndarray, display: int) -> np.ndarray:
    """Return a copy of frame with markers drawn on it."""
    if not overlay_enabled(display):
        return frame.copy()
    result = frame.copy()
    markers = load_markers(display)
    if not markers:
        return result

    img = Image.fromarray(result)
    draw = ImageDraw.Draw(img)
    h, w = result.shape[:2]

    for m in markers:
        if not m.visible:
            continue
        cx, cy = m.x, m.y
        color = (int(m.r), int(m.g), int(m.b))
        dark = (m.r // 4, m.g // 4, m.b // 4)

        # Dark background under marker area
        lw = len(m.label) * 7 + 4 if m.label else 0
        draw.rectangle(
            [cx - 14, cy - 14, cx + 14 + lw, cy + 14],
            fill=dark, outline=None,
        )

        # Circle outline
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=color, width=2)

        # Crosshair
        draw.line([cx - 12, cy, cx + 12, cy], fill=color, width=2)
        draw.line([cx, cy - 12, cx, cy + 12], fill=color, width=2)

        # Label
        if m.label:
            draw.text((cx + 10, cy - 9), m.label, fill=color)

    return np.asarray(img)


# ── CLI ───────────────────────────────────────────────────────────

def _main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    display = int(sys.argv[1])
    cmd = sys.argv[2]

    if cmd == "mark":
        if len(sys.argv) < 5:
            print("Usage: python -m gt_spector.overlay <display> mark <x> <y> [label]")
            sys.exit(1)
        x = int(sys.argv[3])
        y = int(sys.argv[4])
        label = sys.argv[5] if len(sys.argv) > 5 else ""
        m = add_marker(display, x, y, label)
        print(f"  Marker '{m.id}' at ({x},{y})")

    elif cmd == "clear":
        mid = sys.argv[3] if len(sys.argv) > 3 else None
        clear_markers(display, mid)
        print(f"  Cleared {'all' if mid is None else mid}")

    elif cmd == "list":
        markers = load_markers(display)
        if not markers:
            print("  No markers")
        else:
            for m in markers:
                print(f"  {m.id:12s} @ ({m.x:4d},{m.y:4d})  "
                      f"RGB({m.r},{m.g},{m.b})  label='{m.label}'")

    elif cmd == "toggle":
        state = toggle_overlay(display)
        print(f"  Overlay {'ON' if state else 'OFF'} for display {display}")

    elif cmd == "status":
        print(f"  Display {display} overlay: {'ON' if overlay_enabled(display) else 'OFF'}")

    else:
        print(f"Unknown: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    _main()
