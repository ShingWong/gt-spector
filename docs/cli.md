# CLI Navigation

Interactive driver for moving bots screen-to-screen, built on template matching
(`Locator`) plus the `Navigator` graph. No VLM is involved in navigation:
screens and hops are identified by templates alone.

## Launch

```bash
python -m gt_spector --session :<display> --cli
```

The `<display>` is the X display for the headless game (e.g. `:9`).

## Command Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `where` | Report the current screen | `where` |
| `go <screen> [-v]` | Navigate to a screen, hopping through the graph | `go alliance_menu` |
| `route <screen>` | Show the BFS path to a screen without moving | `route alliance_menu` |
| `locate <template>` | Find a template's current position on the frame | `locate alliance_title_static` |
| `label <screen>` | Draw that screen's fixed templates on the overlay | `label alliance_menu` |
| `screens` | List all known screens | `screens` |
| `loc <screen> <name>` | Show a location's coords | `loc alliance_menu back_static` |

Raw commands also remain available: `pixel`, `click`, `key`, `type`, `move`,
`drag`.

## Verbose Movement

`-v` applies only to movement. It makes `go` print each hop as it executes:

```
> go alliance_menu -v
  hop select_igg_id -> world_map
  landed: world_map
  hop world_map -> alliance_menu
  landed: alliance_menu
arrived at alliance_menu
```

Static commands (`where`, `route`, `locate`, `label`, `screens`, `loc`) have no
`-v`.

## Worked Session

```
> where
select_igg_id

> go alliance_menu -v
  hop select_igg_id -> world_map
  landed: world_map
  hop world_map -> alliance_menu
  landed: alliance_menu
arrived at alliance_menu

> where
alliance_menu
```

## In-Game Settings (initialization)

Set game options in one shot during initialization (or after a Wine-prefix
rebuild). This auto-navigates to the system settings menu, applies each
setting, and exits:

```
python -m gt_spector --session :<display> --in-game-settings "graphics-quality=low"
```

Multiple settings are comma-separated:

```
python -m gt_spector --session :<display> --in-game-settings \
  "graphics-quality=low,frame-rate=low,sound-effects=on,background-music=off"
```

Valid keys and values:
- `graphics-quality=low|high`
- `frame-rate=low|mid|high`
- `sound-effects=on|off`
- `background-music=on|off`

Settings are applied via deterministic pixel-color detection (no VLM). New
settings are added to the `IN_GAME_SETTINGS` registry in `viewer/cli.py`.
Unknown keys or invalid values exit with an error listing the valid options.

## Standard Bot Configuration

Every bot is initialized with the following in-game settings:

| Setting          | Value |
|------------------|-------|
| graphics-quality | low   |
| frame-rate       | low   |
| sound-effects    | off   |
| background-music | off   |

Apply to a bot (e.g. bot02 on :11):

```
python -m gt_spector --session :11 --in-game-settings \
  "graphics-quality=low,frame-rate=low,sound-effects=off,background-music=off"
```

The master provisioning snapshot (`game-base/IGG-appdata-master/`) already
carries the standard in-game config (it was captured from a bot set to these
values), so newly provisioned bots start at low/off. Run the command manually
after a Wine-prefix rebuild or if a bot's settings drifted.

## Change Account

Switch a bot to a specific IGG account via the embedded browser login.

  python -m gt_spector --session :<display> --cli
  > change_account sr02-07@mx1.us

The command walks the full login flow: Settings -> Account -> Change Account
-> IGG Account -> browser login form. It pauses at each step and asks you to
confirm the screen before continuing. Type the password when prompted, or
pass it as the second argument.

Relies on deterministic template identification (no VLM) and the
sendtext.exe Wine helper for reliable typing of '@' and uppercase.

Input sequence (verified live): clicks on the browser form go through xdotool
(`session.click` — the embedded browser only registers xdotool clicks), then
the field text is sent text-only via `sendtext.exe` (`typing.type_text`, no
coords — a click from the Wine helper would steal focus from the field that
the xdotool click just focused). Long delays are expected between click and
text because the browser responds slowly to input.

Field positions are **eye-derived at runtime**: the password-reveal eye icon
is located (polled until it renders — the browser's X button appears before
the eye), then email is 100px above, password aligned, login 70px below, all
at x=365. This adapts to page-render shifts between bots.

Navigation and the help loop automatically dismiss popups and screen-saver
screens via `exit_popups` (see AGENTS.md "Popup & screen-saver handling").

Account passwords are in /home/swong/dls/src/ahk/accounts
(email:password per line).

## Expired Login

Complete a login after a bot's session expired (e.g. a fresh provision or an
expired session) — same browser login flow as Change Account, but starting
from the expired-session dialog.

  python -m gt_spector --session :<display> --cli
  > expired_login sr02-09@mx1.us

Pauses for `y/N` confirmation at each step; pass the password as the second
argument to skip the prompt.

## Bot Power

Start, stop, or restart bots (individual or all) from the command line for
agentic/scripted use. Reuses the same BotManager the console's Start/Stop
buttons use.

  python -m gt_spector start bot07
  python -m gt_spector start all
  python -m gt_spector stop bot07
  python -m gt_spector stop all
  python -m gt_spector restart bot07
  python -m gt_spector restart all

`start_all`, `stop_all`, and `restart_all` are aliases for the `all` forms.

`start`/`restart` wait a few seconds after launching, then report the bot's
state (Running/Starting/Offline). `stop` reports Offline once killed.
Unknown bot names or launch failures exit non-zero.
