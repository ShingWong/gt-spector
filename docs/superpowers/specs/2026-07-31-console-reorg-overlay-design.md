# Console Reorganization + Overlay Display Control — Design

## Overview

Reorganize the gt-spector bot console into a desktop-app-style layout (menu bar on top, icon bar below) with better grouping, and add overlay display control from both the console and each viewer window.

## Goals

- Desktop-app layout: menu bar on top, icon bar below it, content, status bar.
- Move most controls from the flat toolbar into grouped menus.
- Add overlay (marker) control: per-bot toggle, global master toggle, list, clear, add.
- Same overlay controls available in each viewer window.

## Non-goals

- No changes to game navigation logic or bot scripts.
- No changes to marker drawing visuals (colors, shapes, labels) — only visibility toggling.

## Architecture

### 1. Overlay settings (new, in `gt_spector/overlay.py`)

Add a settings store at `~/.config/gt-spector/overlay_settings.json`:

```json
{ "global_enabled": true, "per_display": { "10": true, "11": false } }
```

New functions in `overlay.py`:

- `overlay_enabled(display: int) -> bool` — returns `global_enabled AND per_display[display]`
- `set_overlay_enabled(display: int | None, enabled: bool) -> None`
  - `display=None` sets the global flag
  - `display=int` sets the per-display flag
- `toggle_overlay(display: int | None) -> bool` — flips and returns new state
- `_settings_path() -> Path`, `_load_settings()`, `_save_settings()` internal helpers

`draw_markers()` is updated to return the frame unchanged when `overlay_enabled(display)` is False. The per-marker `visible` flag continues to control individual markers.

### 2. Console layout (`viewer/bot_console.py`)

```
┌────────────────────────────────────────────────────┐
│ File  Selection  Actions  Provision  Scripts  ... │  menu bar
│────────────────────────────────────────────────────│
│ [▶] [■] [↻]  |  [▶▶] [■■] [↻↻]  |  [Help Bot] ...│  icon bar
│────────────────────────────────────────────────────│
│ bot rows (checkboxes + state + stats + View btn)   │
│────────────────────────────────────────────────────│
│ status bar                                         │
└────────────────────────────────────────────────────┘
```

#### Menu bar

| Menu | Items |
|------|-------|
| **File** | Refresh, Quit |
| **Selection** | Check All, Uncheck All |
| **Actions** | Start, Stop, Restart, Start All, Stop All, Restart All |
| **Provision** | Provision Bots |
| **Scripts** | Help Bot, Stop Script |
| **Overlay** | "Show Overlays" (checkbutton, global), Show on Checked, Hide on Checked, Add Marker…, List Markers, Clear Markers on Checked |
| **View** | Open Viewers (checked bots) |

Menu items act on checked bots where applicable (Actions, Scripts, View, Overlay per-bot items). Overlay "Show Overlays" is a global checkbutton reflecting `overlay_settings.global_enabled`.

#### Icon bar

Compact buttons for the most common operations, separated into groups:
- Start ▶, Stop ■, Restart ↻
- Start All ▶▶, Stop All ■■, Restart All ↻↻
- Help Bot, Stop Script

The old flat toolbar (Provision, Check All, Uncheck All, Help Bot, Stop Script buttons) is replaced by the menu bar + icon bar. Provision, Check/Uncheck All move to menus; Help Bot/Stop Script remain on the icon bar for quick access.

#### Overlay dialogs

- **Add Marker…** — `tkinter.simpledialog` asking for x, y, optional label; applied to checked bots via `add_marker(display, x, y, label)`.
- **List Markers** — a read-only Toplevel showing markers for the checked bots (id, x, y, label, color), with a Refresh button.
- **Clear Markers on Checked** — clears all markers for checked bots.

### 3. Viewer additions (`viewer/gui.py`)

Add an **Overlay** menu to each viewer window:
- "Show Markers" (checkbutton, per-display toggle reflecting `overlay_enabled(display)`)
- List Markers
- Clear Markers
- Add Marker at cursor position (uses last recorded frame cursor position; falls back to prompt if unavailable)

The existing `draw_markers()` call in `_poll()` stays unchanged — it reads the settings automatically.

### 4. Data flow

- Console and viewer call the existing `add_marker()` / `clear_markers()` and new `set_overlay_enabled()` / `toggle_overlay()`.
- `draw_markers()` reads settings every frame, so toggles take effect immediately without restart.
- Per-bot toggles in the console call `set_overlay_enabled(bot.display, enabled)` for each checked bot.
- Global toggle calls `set_overlay_enabled(None, enabled)`.

## Error handling

- Missing/corrupt `overlay_settings.json` → treated as all-enabled; writes recreate the file.
- No checked bots → Overlay/Actions/Scripts menu items show a status message "No bots selected" instead of failing.
- List Markers with no markers → show "No markers" in the dialog.

## Testing

- Unit tests for `overlay.py`: `overlay_enabled` truth table, `set_overlay_enabled` persistence, corrupted-file fallback.
- Manual: toggle global overlay in console → all viewers stop/start drawing; per-bot toggle affects only that bot's viewer.
