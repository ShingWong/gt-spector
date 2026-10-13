# EG2 screen autodiscovery + tutorial guard (2026-10-11 → 13)

Joint work with the positronic EG2 experiments (branch `eg2-screen-lib` in
positronic-engram; servers `:8091` EG2, `:8080` Qwen-27B+mmproj). Proposal
code lands as untracked `_PROPOSAL` files; nothing tracked touched.

## Screen graph: observed, not guessed

- `start_norah` had zero out-edges. Measured 2x: tap-empty-space (1050,100)
  → `afk_popup`. Proposed in `new_screens.yaml` (experiment branch).
- `afk_popup` → `world_map` edge looks STALE: Confirm (741,676) landed on
  `shelter_view` twice.
- New ESC edges (DB knew neither): `shelter_view` ↔ `exit_dialog` both ways.
- `afk_popup` → `world_map` is suspect until the bucket is split (below).

## afk_popup is a bucket, retire it

The name lumped every unidentified AFK popup. EG2 clustering of 84 frames →
5 clusters: Norah core, AFK-resources, shelter, exit-dialog, + banner-variant
(alliance toast splits Norah frames; cluster ≠ screen without template check).
First real entry proposed: `afk_resource_collect` (Qwen-named, 24 stable-pixel
fingerprint probes, observed advance). Overlay: `new_screens.yaml` (experiment branch).

## Completeness audit (game_world.yaml)

- 5 UNMATCHABLE screens (no templates AND no fingerprint — identify() can
  never return them): bag_menu, mission_menu, messages, hero_menu,
  region_overview. Core menus, not corners.
- 9 screens with no out-edges (BFS dies arriving).
- Descriptions complete. Rot is matchers + edges.

## Tutorial guard doctrine (measured)

- Full-frame EG2 cosine REJECTED as detector: shelter scored tutorial 0.139
  over a true 0.127. Text-query detection also fails (overlap).
- Fixed banners → 10% template patch: positives 1.000, rest ≤0.492 (hero
  upgrade banner). ms on CPU.
- Unknown overlays → contour localize + EG2-names-the-crop (skip~skip 0.997,
  skip~exit 0.71).
- New screens → Qwen names, bank grows per incident.
- Follower: crop-zoom grounding only (full-frame fractions hit SKIP twice);
  Qwen needs 1500+ token budget (600+ reasoning tokens or empty replies).
- Two paths: requirement-met → follow with per-tap verify; BLOCKED (5
  distinct taps, no change; measured: EXP 0/100 hero tutorial) → SKIP out
  once, verified banner-gone on bot16, resume navigation.
- Layering: vectors build definitions, templates serve them, vectors watch
  them decay (re-embed per known screen, flag drift for re-templating).

## Proposal files (untracked, gt_spector/)

- `tutorial_guard_PROPOSAL.py` — v3 three-layer guard module.
- `banner_hero_upgrade_PROPOSAL.png` — 10% patch asset.
- `tutorial_bank_PROPOSAL.json` — L3 seed vectors (5 tut + 10 normal).
- `scripts/tutorial_follow_PROPOSAL.py` — two-path follower (crop grounding).
- `tutorial_nav_PROPOSAL.py` — goto() wrapper + 3 merge points.

## Servers (10.0.0.19)

- `:8091` EG2 Q8+mmproj via `llama-eg2.service` (systemd, verified identical
  vectors). Binds 127.0.0.1. Request shape + pinned LLAMA_MEDIA_MARKER in unit.
- `:8080` Qwen3.8-27B+mmproj, ~6.6s/describe (87+ reasoning tokens per reply —
  budget accordingly). No VL serve anywhere else on the net (checked .249, .20, .100).
