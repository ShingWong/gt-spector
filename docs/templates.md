# Template Workflow

Template matching locates known UI regions in the game frame, with VLM fallback for
non-matches. Templates are authored in the viewer GUI, consumed by `Locator` and
`VlmReader`.

## Store
Templates live under `~/.config/gt-spector/templates/`: `templates.json` is the index
(one `Template` record per entry), `patches/<name>.png` is the RGB patch, and an
optional `patches/<name>_mask.png` holds the masked shape for circle/freehand.
Each record carries `name`, `shape` (rect/circle/freehand), bounding box,
`game_version`, and a per-template `score_threshold`.

## Authoring
In the viewer (`gt-spector --session :9`), Template menu: pick **Rectangle**,
**Circle**, or **Freehand** and drag on the frame (freehand needs a closed polygon,
3+ clicks); **Save Template...** writes the patch (plus a mask for circle/freehand)
and appends to the index; **Show Template Matches** toggles live match overlays.

## Naming
snake_case, matching the game-world KB in `gt_spector/game_world.yaml` (e.g.
`help_btn`, `login_failed_ok`); same-name entries are replaced on save.

## Locator
```python
locator = Locator()
res = locator.find(frame, "help_btn")  # LocateResult(cx, cy, score, found)
if res.found:
    session.click(res.cx, res.cy)
```
A template is found when its match score meets its `score_threshold` (default 0.8).
Below threshold, a VLM fallback — a callable of `(frame, name, score) -> LocateResult
| None` — supplies the result via `locator.set_vlm_fallback(fn)`.

## Reader
`VlmReader(locator)` crops a box around a located center and asks the VLM for the
value: `reader.read(frame, name, center, value_hint="")` returns `{"value", "conf"}`.

## Game Version Tagging
Templates are tagged with the version they were authored against
(`GAME_VERSION = "Doomsday_1.59.0"` in `gt_spector/templates.py`). On a game
update, old templates mis-match or score low: re-author or delete them
(`delete_template`/remove the patch files) rather than keeping stale ones.
