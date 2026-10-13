# eg2-screen-lib — screen-state library and autonomous tutorial

**Run:** 2026-10-12 17:25 → 2026-10-13 06:38. **Host:** 10.0.0.19. **sha:** `9bd5907`.
Working log: `STATUS.md`. Design notes: `docs/eg2-screen-lib.md`.

## Question

Can a game bot identify on-screen state **without a human in the loop**? The
prior workflow was hand-authored `wait_for_color(x, y, r-range, g-range)` —
deterministic and free, but it breaks on resolution/theme change and does not
scale across a farm: every screen needs coordinates and ranges written by a
person.

## Doctrine: a cost-ordered cascade

| layer | handles | cost | mechanism |
|---|---|---|---|
| 1 | fixed-location banners | CPU, free | template patch match |
| 2 | unknown overlays | one EG2 call | contour localise → crop → name |
| 3 | genuinely new screens | ~6.6 s | Qwen names it, goes to the bank |

Each layer handles what the layer below cannot see. **EG2 is layer 2 only** —
it never fires for the cases layer 1 resolves, which is why this use case
looks unlike the text benchmark.

## Measurements

### Layer 1 — template patch has a huge margin and costs nothing

10% patch of the hero-upgrade banner rect `(677,349,475,135) → (840,395,150,45)`:

| frame | score |
|---|---|
| banner frames | **1.000** |
| skip-dialog frames | 0.49 |
| sky | 0.21 |
| all others | **≤0.492** |

Threshold **0.75**. CPU only, no GPU. The margin between 1.000 and 0.492 is
wide enough that layer 1 can be trusted to reject cheaply.

### Layer 2 — text→image retrieval works end to end

**red-query vs red-image cosine 0.780** under `llama-eg2.service` (0.749–0.78
when the server was run manually). Vectors identical between manual and
systemd, so the unit is not degrading the model.

This is the only capability in the whole EG2 exercise that had no prior
equivalent: BGE-M3 cannot embed an image at all, so on this axis it is not a
competitor.

### Layer 3 — LLM describe at 6.6 s

Acceptable for genuinely-new screens, which are rare by construction.

### Autonomy — the actual result

- **Autonomous tutorial completion achieved**: `tut2_25` iter 0 proposed
  `TAP 960 430` with a stated reason, iter 1 returned `DONE`. Zero
  interventions.
- The prior attempt **stopped after 4 blind-tap misses** — the human-in-the-loop
  failure mode this replaces.
- The `identify=None` case is where the value concentrates: a `+` tap hit
  SKIP's hitbox and produced a `Skip Tutorial? Cancel/Skip` dialog the bot
  could not name. Without layer 2 that is a step-in; it was captured as
  `tutorial_skip_dialog.png` instead.

## Screen-graph corrections observed empirically

The graph in the DB did not survive contact with the instances:

- `afk_popup → world_map` is **stale** — Confirm (741,676) landed on
  `shelter_view` twice.
- **Two new edges**, neither in the DB: `shelter_view --esc--> exit_dialog`
  and `exit_dialog --esc--> shelter_view`.
- `start_norah` had **zero** out-edges; measured `tap (1050,100) → afk_popup`.
- walker 2-cycled `shelter ↔ exit_dialog` 12× — no loop detection; fixed by
  stopping on a repeated edge.
- `afk_popup` turned out to be a **bucket**, not a screen: EG2 clustering of
  84 frames gave 5 clusters (Norah core, AFK-resources, shelter, exit-dialog,
  banner-variant).

Audit: **5 unmatchable screens** (bag/mission/messages/hero/region_overview),
**9 no-out-edge screens**. That middle gap is what layer 2 exists to fill, and
its size is the bound on what EG2 contributes here.

## Verdict

**EG2 stays for this workload; BGE stays for text.** They do not compete — the
text gate (`experiments/e9-embed-knn/`, MRR 0.985 vs 0.968) ruled BGE the
better *text* embedder under pre-registration, and nothing here weakens that.
What this run establishes is a different axis: **reduction in human
interventions**, which no text benchmark was structurally able to measure.

The honest bound on the value is the layer-2 workload: 5 unmatchable + 9
no-out-edge screens. Layer 1 handles the rest at zero cost and layer 3 handles
novelty. If that middle count grows across a larger farm, EG2's contribution
grows with it; if it stays in single digits, layer 2 is a convenience rather
than a load-bearing component.

## Hygiene

Frame corpora under `frames/`, `auto_frames/`, `walk_frames/`, `tut_frames/`
are **gitignored** per TEST_HYGIENE R4 — regenerable captures, not evidence.
The numbers in this file are the evidence, and they are the part that has to
survive.

Two harness findings worth keeping, as with the e9 run:

1. `afk_popup` was a bucket masquerading as a screen; clustering it changed
   the graph topology rather than just naming it.
2. `$VAR` inside `EXTRA_OPTIONS` is **not** expanded from a systemd
   `EnvironmentFile`. `llama-eg2` received the literal `$MMPROJ_FILE` and
   loaded no projector. `/etc/llama-vision.config` carried the same latent
   bug on its activation path (`cp` onto `/etc/llama.config`) — **fixed
   2026-10-13**, path inlined, backup at
   `/etc/llama-vision.config.bak-*`.
