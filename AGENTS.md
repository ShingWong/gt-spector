# gt-spector — Agent Development Guide

## Project Overview

GPU readback + viewer + bot API for headless DLS game farm. Python library with C/C++ acceleration (numpy, PIL, OpenCV). DXVK readback (C++) writes raw frames to SHM; Python reads via mmap.

**Root project:** `/home/swong/dls/gt-spector/`
**DXVK build:** `/home/swong/dls/dxvk/dxvk-source-2.5.3/`
**DXVK patches/notes:** `/home/swong/dls/src/dxvk-patch/`
**DXVK experiments:** `/home/swong/dls/dxvk-test1/`
**SHM color format:** RGBA (R@byte0, G@byte1, B@byte2, A@byte3) — verified against user-observed display colors. DXVK docs say BGRA but actual bytes are RGBA.

## Available Skills

Loaded via Superpowers plugin. Use the `skill` tool to load:

| Skill | When |
|-------|------|
| `brainstorming` | Before any creative work |
| `writing-plans` | After design approval |
| `subagent-driven-development` | Executing plan tasks |
| `requesting-code-review` | Before merging |
| `verification-before-completion` | Before claiming done |
| `systematic-debugging` | Debugging bugs |
| `test-driven-development` | During implementation |

## Build & Test

```bash
# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# Test
pytest tests/

# Lint
ruff check gt_spector/ tests/
mypy gt_spector/

# Run viewer
python -m gt_spector --session :9

# Run CLI
python -m gt_spector --session :9 --cli
```

## CLI navigation

Drive bots screen-to-screen from the interactive CLI (see `docs/cli.md`):

```bash
python -m gt_spector --session :<display> --cli
```

Core commands: `where`, `go <screen> [-v]`, `route <screen>`,
`locate <template>`, `label <screen>`, `screens`, `loc <screen> <name>`.
`-v` on `go` prints each hop as it moves. Navigation is template-based
(no VLM).

For one-shot initialization of game options (or after Wine-prefix rebuilds):
`python -m gt_spector --session :<display> --in-game-settings "graphics-quality=low"`
(see `docs/cli.md` "In-Game Settings").

To switch a bot's IGG account:
`change_account <email> [password]` in the CLI (see docs/cli.md "Change Account").

## Code Style

- Python: ruff + mypy strict
- C++ (DXVK patches): match existing conventions
- No unnecessary comments
- TDD where practical (red → green → refactor)

## Quality Gates

Before marking done: build passes, tests pass, lint passes, self-review, clean commits.

## DXVK Build (separate)

```bash
cd /home/swong/dls/dxvk/dxvk-source-2.5.3/build-win64 && ninja -j4
cp src/d3d11/d3d11.dll src/dxgi/dxgi.dll src/d3d10/d3d10core.dll \
  /home/swong/dls/wineprefix_dls/drive_c/windows/system32/
```

## DXVK Patch (required to run headless)

The project depends on a patched DXVK (offscreen swapchain). Patch + notes:
`/home/swong/dls/src/dxvk-patch/` — apply per `dxvk-offscreen-README.txt`.
The patched DLLs are copied into prefixes by `gt_spector/provision.py`
(`DXVK_SRC`).

## MCP Servers

- **context7** — library/framework docs (use when asked about API usage)
- **jcodemunch** — code index/search (disabled by default)
