"""powerup-login: scripted in-game login for Doomsday: Last Survivors.

Drives a bot through Settings -> Account -> Change Account -> IGG Account
to open the embedded browser login page, then types the target account
credentials and confirms login.

Locations are recorded interactively (VLM scene analysis + human click
guidance) and stored as named (x, y) constants below. Each step's scene is
identified by a distinctive pixel fingerprint so the script can verify it
is on the right screen before clicking.

Usage:
  python -m gt_spector.scripts.powerup_login <bot_name> --account <email> [--password <pw>]
"""

from __future__ import annotations

import argparse
import time

# ── Recorded locations (filled in as we map each step) ──────────────────
# Each is (x, y). Scenes keyed by a stable fingerprint pixel.
LOC = {
    # Step: main map (after restart). Avatar top-left.
    "main_map": None,
    "avatar": None,
    # Step: profile panel. Settings gear button.
    "profile_settings": None,
    # Step: settings menu. Account entry.
    "settings_account": None,
    # Step: account page. Change Account button.
    "account_change": None,
    # Step: account-type dialog. IGG Account option.
    "dialog_igg": None,
    # Step: browser login page. Email / password fields.
    "login_email": None,
    "login_password": None,
    "login_submit": None,
    # Step: login confirmation. Continue button.
    "confirm_continue": None,
    # Step: id selection. The existing IGG ID row.
    "id_select": None,
}

# Scene fingerprints: (x, y) -> (r_min, r_max, g_min, g_max, b_min, b_max)
SCENE_FP = {}


def click(session, key: str) -> None:
    """Click a recorded location by name; raise if not yet recorded."""
    pos = LOC.get(key)
    if pos is None:
        raise ValueError(f"Location '{key}' not recorded yet")
    session.click(pos[0], pos[1])


def wait_frames(session, seconds: float = 3.0) -> None:
    time.sleep(seconds)
    session.refresh()


def on_scene(session, key: str) -> bool:
    """True if the frame's fingerprint for `key` matches (or not set)."""
    fp = SCENE_FP.get(key)
    if fp is None:
        return True  # not fingerprinted yet
    x, y = LOC[key]
    r, g, b = session.get_pixel(x, y)
    return fp[0] <= r <= fp[1] and fp[2] <= g <= fp[3] and fp[4] <= b <= fp[5]


def main():
    parser = argparse.ArgumentParser(description="powerup-login: scripted in-game login")
    parser.add_argument("bot", help="bot name (e.g. bot02)")
    parser.add_argument("--account", help="email to log in")
    parser.add_argument("--password", help="password")
    parser.add_argument("--display", default=None, help="X display (default: auto from bot)")
    args = parser.parse_args()

    from gt_spector.bot_manager import BotManager
    from gt_spector.session import Session

    m = BotManager()
    m.load_from_prefixes()
    bot = m.get(args.bot)
    if not bot:
        print(f"Bot {args.bot} not found")
        return
    display = args.display or f":{bot.display}"
    session = Session(display, source=f"shm://{bot.display}")

    # Restart the game for a clean state.
    print(f"Restarting {args.bot}...")
    m.restart_game(bot)
    wait_frames(session, 75)
    print("Game restarted. Waiting for main map...")
    # STEP: main map -> avatar. Record LOC['avatar'] after human confirms.
    # This is a WIP skeleton; locations are filled in during mapping.


if __name__ == "__main__":
    main()
