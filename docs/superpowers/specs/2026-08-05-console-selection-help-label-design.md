# Console Selection Buttons + Alliance Help Label — Design

## Problem

1. **Select All / Unselect All are hard to reach.** They exist only in the
   Selection menu (`viewer/bot_console.py` `_check_all` / `_uncheck_all`).
   With many bots, operators need one-click select-all/unselect-all.
2. **The Loc column reads "EVENT" for bots in the help loop.** When a bot has
   a HelpBot running, `_detect_location` returns the nav-table name `EVENT`
   (the alliance help area), which is unhelpful — the operator wants to see
   that the bot is actively helping in the alliance.

## Goal

1. Add **Select All** / **Unselect All** toolbar buttons for one-click
   selection, keeping the existing menu items.
2. Show **"Alliance Help"** in the Loc column when a bot's HelpBot is running
   and the bot is on the help area, instead of the raw `EVENT`/`help_dialog`
   name.

## Behavior

### 1. Toolbar buttons

In `_setup_toolbar`, add a new group after the Help buttons:

- `☑ All` → `self._check_all()` (select every bot row)
- `☐ None` → `self._uncheck_all()` (clear selection)

The toolbar group layout becomes:
`Start Stop | StartAll StopAll RestartAll | StartHelp StopHelp | ☑All ☐None | ClearStatus ClearLogs`

The existing Selection menu items remain.

### 2. Alliance Help label

In `_update_rows`, after computing `loc` and `runner`:

```python
loc = self._detect_location(bot, frame)
runner = self._runners.get(bot.name)
if (runner is not None
        and getattr(runner.script, "self_healing", False)
        and loc in ("EVENT", "help_dialog", "ALLIANCE_HELP")):
    loc = "Alliance Help"
```

Conditions:
- `runner.script.self_healing` is True — only HelpBot runners have this
  marker, so the label only appears while a help loop is active.
- `loc` is a help-area name — so a bot on `EVENT` *without* a help bot keeps
  showing `EVENT`.

The tooltip (`_status_tooltip`) uses the raw loc internally and is unchanged.

## Files

- `viewer/bot_console.py` — `_setup_toolbar` (buttons), `_update_rows` (loc label).

## Testing

- A unit test for the Loc-label logic: `_update_rows` (or a small extracted
  helper) maps `EVENT` → `Alliance Help` when a self-healing runner is present
  and loc is a help-area name; keeps `EVENT` when no runner, and keeps other
  screens unchanged.
- Toolbar wiring: verify `_setup_toolbar` references `_check_all`/`_uncheck_all`
  (methods already exist and are tested via the menu).

## Out of scope

- The toolbar is left as a flat button strip (no dropdown regrouping).
- No change to the raw nav-table names for non-help screens.
