# Console Reorganization + Overlay Display Control + Sound Control — Design

## Overview

Reorganize the gt-spector bot console into a desktop-app-style layout (menu bar on top, icon bar below) with better grouping, and add overlay display control and sound control from both the console and each viewer window.

## Goals

- Desktop-app layout: menu bar on top, icon bar below it, content, status bar.
- Move most controls from the flat toolbar into grouped menus.
- Add overlay (marker) control: per-bot toggle, global master toggle, list, clear, add.
- Same overlay controls available in each viewer window.
- Add sound control: 3 console modes (All Off, Viewer Control, All On), per-bot sound status in bot stats, mute on viewer close, viewer sound toggle.

## Non-goals

- No changes to game navigation logic or bot scripts.
- No changes to marker drawing visuals (colors, shapes, labels) — only visibility toggling.
- No per-bot volume leveling — only mute/unmute.

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
| **Sound** | All Off (radio), Viewer Control (radio), All On (radio) |
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

## Sound Control

### Audio architecture

Each bot's game process emits audio streams via PipeWire (pipewire-pulse). Sink-inputs carry `application.process.id` = game PID. Mute/unmute via `pactl set-sink-input-mute <id> 1|0`.

### 5. New module `gt_spector/audio.py`

- `get_sink_inputs(game_pid: int) -> list[int]` — query `pactl list sink-inputs`, return sink-input ids whose `application.process.id` matches.
- `set_muted(game_pid: int, muted: bool) -> None` — `pactl set-sink-input-mute` for each matching sink-input. No-op if none found.
- `is_muted(game_pid: int) -> bool | None` — True if all found sink-inputs are muted, False if any unmuted, None if none found.
- All functions tolerate `pactl` missing or failing (return empty/None).

### 6. Sound mode (global setting)

Stored at `~/.config/gt-spector/sound_settings.json`:
```json
{ "mode": "all_off" | "viewer" | "all_on" }
```

Functions in a small `sound_settings` helper (or inside `bot_manager.py`):
- `get_sound_mode() -> str`
- `set_sound_mode(mode: str) -> None`
- `apply_sound_policy(bots: list[Bot]) -> None` — mutes all when `all_off`, unmutes all when `all_on`; in `viewer` mode, applies per-bot based on viewer-open state.

### 7. Console sound integration

- **Sound menu**: radio buttons All Off / Viewer Control / All On. Selecting a mode calls `set_sound_mode` + `apply_sound_policy`.
- **Bot stats sound column**: a `snd` column showing 🔊 (unmuted) / 🔇 (muted) / — (no stream), refreshed in `_update_rows()` via `audio.is_muted(bot.pid)`.
- **Viewer open**: `attach_viewer` passes `GT_SPECTOR_GAME_PID=<bot.pid>` env var to the viewer subprocess. In `viewer` mode, opening a viewer unmutes that bot.
- **Viewer close**: the viewer mutes its bot on close when mode is `viewer`. (See §8.)

### 8. Viewer sound integration

- **Sound toggle button** in the viewer toolbar: shows 🔊/🔇; clicking calls `audio.set_muted(game_pid, state)` using the `GT_SPECTOR_GAME_PID` env var.
- **On window close**: read `sound_settings.json`; if mode == `viewer`, call `audio.set_muted(game_pid, True)` before destroying.
- Viewer resolves game_pid from `GT_SPECTOR_GAME_PID`; if unset, skips sound control.

## Persistence

All settings persist across restarts of the console, viewers, and game instances:

- `~/.config/gt-spector/overlay_settings.json` — `global_enabled` + per-display flags.
- `~/.config/gt-spector/sound_settings.json` — sound `mode`.
- Settings are loaded once at console/viewer startup and written on every change (atomic write: write to temp file, then rename).
- Per-display overlay settings persist per display number, so they survive bot restarts and console restarts.
- Settings files are re-read by viewers when they start, so a viewer launched later reflects the current console state.
- Corrupt/missing files fall back to defaults (overlay enabled, sound `all_off`) and are rewritten on next change.

## Error handling

- Missing/corrupt `overlay_settings.json` → treated as all-enabled; writes recreate the file.
- No checked bots → Overlay/Actions/Scripts menu items show a status message "No bots selected" instead of failing.
- List Markers with no markers → show "No markers" in the dialog.
- `pactl` unavailable or no sink-inputs for a bot → sound status shows "—", mute/unmute calls are no-ops.
- Missing/corrupt `sound_settings.json` → default mode `all_off`.

## Testing

- Unit tests for `overlay.py`: `overlay_enabled` truth table, `set_overlay_enabled` persistence, corrupted-file fallback.
- Unit tests for `audio.py` (with pactl stubbed): `get_sink_inputs` parsing, `set_muted` subprocess args, `is_muted` result mapping.
- Manual: toggle global overlay in console → all viewers stop/start drawing; per-bot toggle affects only that bot's viewer.
- Manual sound: switch modes All Off/Viewer Control/All On → verify mute state via `pactl list short sink-inputs`; open and close a viewer in viewer mode → sound toggles off on close.
