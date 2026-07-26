# Task 1 — Type Hint Regression Fix

## Changes Made

**File:** `gt_spector/session.py`

1. Added `from __future__ import annotations` at top of file for Python 3.9+ `|` syntax support
2. Fixed `_screen` type hint: `Screen | ShmScreen` → `Screen | ShmScreen | None`
3. Fixed `_input` type hint: `Input` → `Input | None`
4. Added `_check_attached()` helper that raises `RuntimeError("Session detached")` if `_screen is None or _input is None`
5. Added `_check_attached()` guard to all methods that use `_screen` or `_input`: `frame`, `refresh`, `get_pixel`, `capture_area`, `move_mouse`, `click`, `drag`, `key_press`, `type_text`

`detach()` and `attach()` intentionally left without guards since they manage the attached/detached state.

## Verification

- `python3 -m pytest tests/ -v` — 9/9 passed
- Commit `2357026` on `feat/session-mgmt`
