# change-account CLI Command — Design

## Problem

Logging a bot into a specific IGG account (e.g. switching bot04 from guest to
sr02-07) requires a delicate multi-step flow through the game's embedded
browser. It took ~12 hours of trial-and-error to get working, and each time it
was done by hand. Agents have no reliable way to change an account without
re-inventing the flow.

## Goal

Add a `change-account` command to the interactive CLI (`CliSession`) that
drives the full login flow automatically. During development, the command
pauses at each step and asks the human to confirm the screen before
proceeding. No VLM — only the deterministic template/fingerprint
identification already in the project.

## Command

```
change-account <email> [password]
```

- `email` (required) — the IGG account email, e.g. `sr02-07@mx1.us`.
- `password` (optional) — if omitted, prompts for it. Default password for
  farm accounts is `bamboo-H4`.

If the bot is already logged into the requested email, the command reports
that and does nothing.

## Flow (verified live on bot06, 2026-08-04; re-verified on bot07, 2026-08-05)

All coordinates below are **game-window-relative**. The window is offset by
**(+3, +29)** on the screen; to click a window-relative `(x, y)`, send a
screen click at `(x+3, y+29)`.

**Field positions are NOT fixed — they are derived from the password-reveal
eye icon** (see below), because the login page render shifts between bots and
renders. The table below is a single render's reference only:

| Step | Action | Window coord (one render) | Identify via |
|------|--------|--------------|--------------|
| 1 | Navigate current screen → `account` | (Navigator) | `account_title_static` |
| 2 | Click CHANGE ACCOUNT button | (573, 660) | `igg_id_static` (state 2) |
| 3 | Click IGG Account icon | (735, 262) | browser spawns, `igg_login_exit_static` |
| 4 | Click email field, `{CtrlA}`, type email | (365, 126) | — |
| 5 | Click password field, `{CtrlA}`, type password | (365, 226) | — |
| 6 | Click eye to reveal password, confirm, click eye to hide | (880, 226) | — |
| 7 | Click LOGIN | (365, 296) | success page `login_ok_currently_static` |
| 8 | Click Continue | (500, 300) | `select_igg_id` (`login_select_igg_id_static`) |
| 9 | Click the IGG ID row | (350, 165) | ID-confirm dialog (also `igg_login_exit_static`) |
| 10 | Click OK | (700, 560) | game loads; identify shelter/events |

**Eye-derived positions (the actual mechanism):** `login()` locates the
password-reveal eye icon (`igg_login_eye2_static`, falling back to
`login_eye_static`) and derives: email 100px above (`EMAIL_Y_ABOVE_EYE=100`),
password aligned with the eye, login 70px below (`LOGIN_Y_BELOW_EYE=70`), all
at x=365. This is what makes login work across varying page renders.

**Typing** must use the one-shot `sendtext.exe` Wine helper (Windows SendInput
with `KEYEVENTF_UNICODE`), because X11/xdotool typing drops `@`/uppercase.

**Verified input sequence (bot06, 2026-08-04):**
- Browser clicks go through **xdotool** (`session.click`), not the Wine helper.
  The embedded browser only registers xdotool clicks on its input fields.
- Field **text** is then sent **text-only** via the one-shot helper — no
  coordinates. A Wine-helper click (or the `sendtextd` daemon's
  `SetForegroundWindow` on every command) steals focus from the field the
  xdotool click just focused, so the text never lands.

```
WINEPREFIX=<bot-prefix> wine .../sendtext.exe "{CtrlA}<text>"
```

- `typing.type_text(prefix, display, text)` wraps the text-only form.
- `typing.type_at(prefix, display, text, x, y)` (click+type) still exists but
  is **not** used for the browser form; the browser ignores its click.
- Expect long delays (multiple seconds) between the click and the text
  appearing — the embedded browser responds slowly to input.
- The persistent `sendtextd` daemon is **not** reliable for the browser form;
  use the one-shot binary.

**Screens that share the `igg_login_exit_static` template** (the browser X):
- `igg_login` (email/password form)
- login success page (distinguish with `login_ok_currently_static`)
- select IGG ID page (distinguish with `login_select_igg_id_static`)
- ID-confirm dialog

## Implementation

### New module: `gt_spector/login_flow.py`

`LoginFlow(session, gw, locator, confirm=print)` with:

- `change_account(email, password) -> str` — runs steps 1-10, returns the
  final screen name (or "error" on failure).
- `_confirm(step_msg) -> bool` — hook; during development the CLI wires it to
  an `input()` prompt. Non-interactive callers can pass `lambda _: True`.
- Uses the existing `Navigator` for steps 1-3 and screen identification
  (templates/fingerprints) for verification at each step.
- Runs `sendtext.exe` via `subprocess` for typing; coordinates are the
  window-relative constants above.

### CLI: `do_change_account(self, arg)`

In `viewer/cli.py` `CliSession`:

- Parses `email [password]`; prompts for password if missing.
- Resolves the bot's Wine prefix for this display (display 9+n ↔ bot0n), so
  it can locate the right `sendtext.exe` invocation and `WINEPREFIX`.
- Wires `LoginFlow`'s `confirm` to an interactive prompt.
- Prints each step and the final result.

### Game world updates

Field coordinates are **eye-derived at runtime**, not fixed locations:
`login()` locates the password-reveal eye icon (polling until it renders —
the browser's X button appears before the eye), then derives email 100px
above, password aligned, login 70px below, all at x=365. The `login_*`
locations in `game_world.yaml` are legacy references, not used for clicking.

Fixed templates still used by the flow:

- `login_ok_currently_static` → success-page check.
- `igg_login` / `select_igg_id` → identifiable via `igg_login_exit_static`
  as the base template.

## Agent-facing documentation

Add to `docs/cli.md` (new section "Changing a bot's account"):

```text
## Change Account

Switch a bot to a specific IGG account via the embedded browser login.

  python -m gt_spector --session :<display> --cli
  > change_account sr02-07@mx1.us

The command walks the full login flow: Settings -> Account -> Change Account
-> IGG Account -> browser login form. It pauses at each step and asks you to
confirm the screen before continuing. Type the password when prompted if not
given as an argument.

Relies on deterministic template identification (no VLM) and the sendtext.exe
Wine helper for reliable typing of '@' and uppercase. Account passwords are
in /home/swong/dls/src/ahk/accounts (email:password per line).
```

## Testing

- Unit tests for `LoginFlow` with a fake session: verify each step's action
  and that it stops on a confirm-rejected step.
- The live bot07 flow (2026-08-05) is the acceptance test: `expired_login
  sr02-09@mx1.us` on bot07 navigates the expired-session dialog → game login
  → IGG browser, types credentials, and loads the game past login.
  Without the eye-polling fix, the same flow fails with
  `error: eye icon not found` (eye renders after the browser X button).

## Non-goals

- No VLM-based screen reading.
- No password storage beyond the existing accounts file.
- No multi-ID selection logic — all farm accounts have exactly one IGG ID.
