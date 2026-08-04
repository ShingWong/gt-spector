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

`provision.py init` applies this automatically when a new bot is provisioned
(start the game, set the config, stop the game). Run the command manually
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
Account passwords are in /home/swong/dls/src/ahk/accounts
(email:password per line).
