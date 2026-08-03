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
| `locate <template>` | Find a template's current position on the frame | `locate help_btn` |
| `label <screen>` | Draw that screen's fixed templates on the overlay | `label alliance_menu` |
| `screens` | List all known screens | `screens` |
| `loc <screen> <name>` | Show a location's coords | `loc alliance_menu recruit_btn` |

Raw commands also remain available: `pixel`, `click`, `key`, `type`, `move`,
`drag`.

## Verbose Movement

`-v` applies only to movement. It makes `go` print each hop as it executes:

```
> go alliance_menu -v
  hop world -> alliance
  landed: alliance
  hop alliance -> alliance_menu
  landed: alliance_menu
arrived at alliance_menu
```

Static commands (`where`, `route`, `locate`, `label`, `screens`, `loc`) have no
`-v`.

## Worked Session

```
> where
world

> go alliance_menu -v
  hop world -> alliance
  landed: alliance
  hop alliance -> alliance_menu
  landed: alliance_menu
arrived at alliance_menu

> where
alliance_menu
```
