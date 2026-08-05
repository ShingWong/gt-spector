# Bot Power CLI — Design

## Problem

Agents need to power bots on and off programmatically. The interactive bot
console has Start/Stop/All buttons wired to `BotManager`, but there is no
CLI entry for scripted/agentic use. Today a power-up requires either the
GUI console or manual wine/Xvfb commands.

## Goal

Add subcommands to `python -m gt_spector` that start/stop individual bots or
all bots, reusing `BotManager` (the same code the console buttons use), and
report each bot's resulting state.

## Commands

```
python -m gt_spector start bot07     # power on bot07
python -m gt_spector start all       # power on every discovered bot
python -m gt_spector stop bot07      # power off bot07
python -m gt_spector stop all        # power off all bots
python -m gt_spector restart bot07   # stop then start bot07
python -m gt_spector restart all     # stop then start all bots
```

`start_all`, `stop_all`, and `restart_all` are accepted as single-token
aliases for `all`.

## Flow

1. `BotManager.load_from_prefixes()` discovers bots from `wineprefix_bots/`
   (same source as the console). An unknown bot name is an error (exit 1).
2. `start <name>`: `manager.start_game(bot)` (starts Xvfb + wine), then a
   short fixed wait, then `manager._refresh_state(bot)` and print the state
   (`RUNNING` / `STARTING` / `OFFLINE`).
3. `stop <name>`: `manager.stop_game(bot)` (kills every Doomsday.exe on the
   bot's display), then print `OFFLINE`.
4. `restart <name>`: `manager.restart_game(bot)` (stop then start), then a
   short fixed wait and report the state (same as `start`).
5. `all`: loop over `manager.bots`, acting on each and reporting it
   individually. Non-zero exit if any bot failed.

## Architecture

- New `run_power_command(manager, action, target) -> int` in
  `gt_spector/power.py` (new module). `action` is `start` | `stop` |
  `restart`, `target` is `all` | a bot name. Returns process exit code.
- `__main__.py` dispatches subcommands before the existing `--cli` /
  `--bot-console` / `--in-game-settings` flags. Unknown bot → error + exit 1.
- Errors from `start_game` / `stop_game` (`RuntimeError`, `OSError`) are
  caught, printed, and yield exit 1.

### Short fixed wait

`start` waits a fixed few seconds after launching (default ~5s), then
reports the bot's state via `_refresh_state`. No long polling.

## Testing

- Unit tests for `run_power_command` with a fake manager: arg parsing,
  unknown-bot error, `all` loop, state reporting.
- No real wine / Xvfb in unit tests.
- Manual verification on bot07 (`python -m gt_spector start bot07` → state,
  `stop bot07` → state).

## Out of Scope

- A `status` subcommand (verify-and-report is built into start/stop).
- Changes to `BotManager` itself.
