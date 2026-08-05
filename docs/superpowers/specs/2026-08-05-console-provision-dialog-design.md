# Console Provision Dialog — Design

## Problem

The console's "Provision Bots" menu entry provisions **every** account in the
accounts file in one loop (`viewer/bot_console.py` `_on_provision`). This is
unreliable for mass provisioning: a single slow/failing bot blocks or fails the
whole batch with no per-bot verification, and there's no way to provision a
subset.

## Goal

Replace the one-shot batch provision with a dialog that:

1. Reads `~/dls/src/ahk/accounts` as the source of truth.
2. Maps accounts to bots **by line order** (first entry → `bot01`, second →
   `bot02`, …) — never by assuming the email is sequential.
3. Lists the accounts that are not yet provisioned (no `drive_c` in the
   prefix).
4. Lets the operator pick how many to provision (1..N, where N = number of
   unprovisioned accounts).
5. Provisions them **one at a time, strictly sequential, no parallel**,
   verifying each succeeded before starting the next, and stopping on the
   first failure.

## Behavior

- New `_unprovisioned_accounts() -> list[tuple[str, str]]`: reads the accounts
  file, maps line order → bot name, filters to accounts whose prefix lacks
  `drive_c`. Pure, testable logic.
- New `_provision_n(count: int) -> None`: provisions the first `count`
  unprovisioned accounts sequentially via `python3 -m gt_spector.provision init
  <name> --account <email>`, verifying exit code 0 after each, stopping on the
  first failure, updating the status bar, then refreshing the bot list.
- New `_on_provision()` opens a `tk.Toplevel` dialog:
  - A label listing the unprovisioned accounts (`bot09 → sr02-12@mx1.us`), or
    "All accounts provisioned" if none.
  - A `ttk.Spinbox` from 1 to N (default 1).
  - A "Provision" button that calls `_provision_n` and closes the dialog.
  - A "Cancel" button.

## Files

- `viewer/bot_console.py` — replace `_on_provision`; add
  `_unprovisioned_accounts`, `_provision_n`, `_provision_dialog`.
- `tests/test_bot_console.py` — tests for `_unprovisioned_accounts` and
  `_provision_n`.

## Testing

- `_unprovisioned_accounts`: fake accounts file (tmp file) + tmp prefix dirs;
  verifies line-order mapping and filtering of provisioned prefixes.
- `_provision_n`: mocked `subprocess.run`; verifies sequential one-at-a-time
  execution, exit-code verification, stop-on-failure, and that it skips
  already-provisioned accounts.
- The GUI dialog itself is not unit-tested (consistent with existing console
  tests, which test logic via `object.__new__(BotConsole)`).

## Out of scope

- Auto-login / auto-helpbot after provisioning (that stays manual per the
  verified lifecycle).
- Progress bars or background threads (provisioning is sequential and modal).
