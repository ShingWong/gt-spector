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

### 1. Settings layout (hybrid: global + per-bot)

```
~/.config/gt-spector/
  settings.json        ← global (console-only writes): overlay global_enabled, sound mode
  bots/bot01.json      ← per-bot (console + that bot's viewer): overlay enabled, sound state
  bots/bot02.json
```

- **Global** `settings.json`:
  ```json
  { "overlay_global_enabled": true, "sound_mode": "viewer" }
  ```
- **Per-bot** `bots/<bot_name>.json`:
  ```json
  { "overlay_enabled": true, "sound_muted": false }
  ```
- **Atomic writes everywhere** (write temp file + rename). This prevents torn reads/writes. The console (single process) is the only writer of `settings.json`; a bot's viewer is the only writer of that bot's per-bot file. A rare console↔viewer race on the same per-bot file can still lose one read-modify-write update, but this is acceptable given toggles are infrequent and the file is rewritten on every change.
- Per-bot files are keyed by bot name, not display, so they survive display renumbering.
- `overlay.py` maps display → bot name (via the same `9 + n` rule used by `BotManager.load_from_prefixes`; a display not matching a known bot falls back to the global flag).

New functions in `overlay.py`:

- `overlay_enabled(display: int) -> bool` — returns `global_enabled AND per-bot enabled` (per-bot default true when unknown)
- `set_overlay_enabled(display: int | None, enabled: bool) -> None`
  - `display=None` sets the global flag in `settings.json`
  - `display=int` sets that bot's flag in its per-bot file
- `toggle_overlay(display: int | None) -> bool` — flips and returns new state
- `_settings_path()` / `_bots_dir()` / `_load_global()` / `_save_global()` / `_load_bot(name)` / `_save_bot(name, data)` internal helpers

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
| **File** | Refresh, Settings…, Quit |
| **Selection** | Check All, Uncheck All |
| **Actions** | Start, Stop, Restart, Start All, Stop All, Restart All |
| **Provision** | Provision Bots |
| **Scripts** | Help Bot, Stop Script |
| **Overlay** | "Show Overlays" (checkbutton, global), Show on Checked, Hide on Checked, Add Marker…, List Markers, Clear Markers on Checked |
| **Sound** | All Off (radio), Viewer Control (radio), All On (radio) |
| **View** | Open Viewers (checked bots) |
| **Logs** | Clear Logs |

**Settings…** dialog: log rotation size (KB). Writes `log_max_bytes` to global settings.

Menu items act on checked bots where applicable (Actions, Scripts, View, Overlay per-bot items). Overlay "Show Overlays" is a global checkbutton reflecting `overlay_settings.global_enabled`.

#### Icon bar

Compact buttons for the most common operations, separated into groups:
- Start ▶, Stop ■, Restart ↻
- Start All ▶▶, Stop All ■■, Restart All ↻↻
- Help Bot, Stop Script
- Clear Status, Clear Logs

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

Stored in the global `settings.json` under `sound_mode` (`"all_off" | "viewer" | "all_on"`). Per-bot sound state lives in the per-bot file under `sound_muted` (used to restore state across console restarts in `viewer` mode).

Functions in a small `sound_settings` helper (or inside `bot_manager.py`):
- `get_sound_mode() -> str` — reads global `settings.json`
- `set_sound_mode(mode: str) -> None` — writes global `settings.json` (atomic)
- `apply_sound_policy(bots: list[Bot]) -> None` — mutes all when `all_off`, unmutes all when `all_on`; in `viewer` mode, applies per-bot based on per-bot `sound_muted` / viewer-open state.

### 7. Console sound integration

- **Sound menu**: radio buttons All Off / Viewer Control / All On. Selecting a mode calls `set_sound_mode` + `apply_sound_policy`.
- **Bot stats sound column**: a `snd` column showing 🔊 (unmuted) / 🔇 (muted) / — (no stream), refreshed in `_update_rows()` via `audio.is_muted(bot.pid)`.
- **Viewer open**: `attach_viewer` passes `GT_SPECTOR_GAME_PID=<bot.pid>` env var to the viewer subprocess. In `viewer` mode, opening a viewer unmutes that bot.
- **Viewer close**: the viewer mutes its bot on close when mode is `viewer`. (See §8.)

### 8. Viewer sound integration

- **Sound toggle button** in the viewer toolbar: shows 🔊/🔇; clicking calls `audio.set_muted(game_pid, state)` using the `GT_SPECTOR_GAME_PID` env var.
- **On window close**: read global `settings.json`; if `sound_mode == "viewer"`, call `audio.set_muted(game_pid, True)` before destroying.
- Viewer resolves game_pid from `GT_SPECTOR_GAME_PID`; if unset, skips sound control.

## Monitoring, Health Check & Recovery

### 9. Enhanced bot status columns

New bot row layout:

```
☑ bot01 :10  acct@mail  [● RUNNING]  [help-bot:badge_info]  [ALLIANCE]  CR:2  IV:1  45% 1.2G 123 [View]
☐ bot02 :11  acct@mail  [✕ OFFLINE]  [—]                    [—]         CR:0  IV:0  —    —    —   [View]
```

| Column | Content |
|--------|---------|
| **Status** | Color/shape-coded indicator + state text: ● green circle (Running), ◐ yellow half-circle (Starting), ✕ red X (Offline/Error), ▲ blue triangle (Alert: recovering / unable to recover). Mouse-over shows a tooltip with the full status wording. |
| **Activity** | What the bot is doing: script name + tick status (e.g., `help-bot:badge_info`), or blank |
| **Location** | Current screen (ALLIANCE, LOBBY, EXIT, …), `?` if unknown, `blank` for blank/crash frames |
| **CR** | Crash count (game restarts this session, in-memory) |
| **IV** | Intervention count (recoveries this session, in-memory) |
| snd | 🔊 / 🔇 / — |

#### Status indicator glyphs

- ● green — `RUNNING`
- ◐ yellow — `STARTING`
- ✕ red — `OFFLINE` / `ERROR`
- ▲ blue — `ALERT` (recovering via ESC-to-shelter, or unable to recover after retries)
- Tooltip (mouse-over) shows a short status sentence, e.g. "Running — help-bot, in ALLIANCE", "Alert: recovering — re-running help-bot", "Offline".

The blue ▲ overrides the base state when the bot is in a recovery/alert condition; the underlying state still shows in the tooltip.

### 10. Screen monitor (`gt_spector/monitor.py`)

- **Responsiveness check** (every 2s poll): SHM frame counter must advance. Stalled counter → non-responsive → treat as crash: restart game, increment CR, log to bot log.
- **VLM screen ID** (background, throttled): round-robin over running bots, one per ~10s, **only when VLM slot is free** (shared VLM client busy flag; never blocks bot actions).
  - Sends a **1/4 scale frame (288×216)** for fast (~1s) classification.
  - Detects: screen identity, **blank screen**, **crash dialog**, wrong location.
- **Screen fingerprint** (fast, no VLM): derived from `nav_table.json` states (`fingerprints` map added per state). Evaluated each poll (~1ms) to set the Location column; VLM refines/corrects when a fingerprint is ambiguous or absent.

### 11. Recovery

- A running script declares its **expected screen** (e.g., HelpBot → `ALLIANCE`).
- If fingerprint/VLM location ≠ expected:
  1. **Intervention** (increment IV, log event)
  2. ESC-to-shelter (ESC chain to settlement)
  3. Re-run the script that was running (e.g., HelpBot navigates to alliance and resumes)
- If the game is non-responsive or shows a crash dialog → full game restart (increment CR, log event).
- Recovery actions run on the console poll loop so they don't require extra threads.
- While recovering (or when recovery failed after retries), the bot's status shows the blue ▲ ALERT glyph with a tooltip describing the condition.

## Logging

### 12. Logging subsystem (`gt_spector/logs.py`)

```
~/.config/gt-spector/logs/
  system.log        ← console-level events (provision, refresh, mode changes, errors)
  system.log.1      ← rotated copy
  bot01.log         ← per-bot events (start, stop, crash, recovery, screen changes)
  bot01.log.1
  bot02.log
```

- **Rotation**: default **500 KB** per file, keep **2 copies** (`.log`, `.log.1`). Rotation size settable in the console (stored in global `settings.json` as `log_max_bytes`).
- Rotation is safe-guarded (truncate-then-write after renaming, best-effort — logs are non-critical).

### 13. Console logging integration

- **System log** — console events: startup, refresh, provisioning, sound/overlay mode changes, errors.
- **Bot log** — per-bot events: game start/stop, crash restart, screen recovery, screen changes.
- **Clear Status** button — clears the console status bar.
- **Clear Logs** button — truncates system + all bot logs (rotated copies also removed).
- **Log Size** setting — spinbox/dialog in the File menu (Settings…) to set rotation size; writes `log_max_bytes` to global settings.

## Persistence

All settings persist across restarts of the console, viewers, and game instances:

- Global `~/.config/gt-spector/settings.json` — `overlay_global_enabled`, `sound_mode`.
- Per-bot `~/.config/gt-spector/bots/<bot_name>.json` — `overlay_enabled`, `sound_muted`.
- Settings are loaded once at console/viewer startup and written on every change (atomic write: write to temp file, then rename).
- Per-bot settings persist per bot name, so they survive bot restarts and console restarts.
- Settings files are re-read by viewers when they start, so a viewer launched later reflects the current console state.
- Corrupt/missing files fall back to defaults (overlay enabled, sound mode `viewer` toggled per `sound_muted`) and are rewritten on next change.

## Error handling

- Missing/corrupt global `settings.json` or per-bot `bots/*.json` → treated as all-enabled / unmuted; writes recreate the file.
- No checked bots → Overlay/Actions/Scripts menu items show a status message "No bots selected" instead of failing.
- List Markers with no markers → show "No markers" in the dialog.
- `pactl` unavailable or no sink-inputs for a bot → sound status shows "—", mute/unmute calls are no-ops.
- Missing/corrupt `sound_mode` in global settings → default mode `viewer`.
- VLM unavailable (server down) → monitor skips VLM checks, falls back to pixel fingerprints only; no crash loop.
- Log file write failures (permissions/disk) → logged to stderr, never raises in the UI.
- Recovery failing repeatedly for a bot → stop the script, mark bot state `ERROR` (shown as blue ▲ ALERT), log; do not loop forever.
- Tooltip helper: a small `ToolTip` widget (Tkinter) attached to the status cell, populated each poll from the current status text; hides on leave.

## Testing

- Unit tests for `overlay.py`: `overlay_enabled` truth table, `set_overlay_enabled` persistence, corrupted-file fallback.
- Unit tests for `audio.py` (with pactl stubbed): `get_sink_inputs` parsing, `set_muted` subprocess args, `is_muted` result mapping.
- Unit tests for `logs.py`: rotation at size threshold, 2-copy retention, truncate failure tolerance.
- Unit tests for `monitor.py` (with frame/VLM stubbed): responsiveness detection, fingerprint matching, recovery trigger, CR/IV counters.
- Manual: toggle global overlay in console → all viewers stop/start drawing; per-bot toggle affects only that bot's viewer.
- Manual sound: switch modes All Off/Viewer Control/All On → verify mute state via `pactl list short sink-inputs`; open and close a viewer in viewer mode → sound toggles off on close.
- Manual monitoring: stop a game's SHM updates → CR increments and game restarts; move a bot off the alliance screen while HelpBot runs → IV increments and recovery returns it to alliance.
