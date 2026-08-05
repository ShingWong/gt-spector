import argparse
import sys
from collections.abc import Callable
from typing import Any, cast


def apply_in_game_settings(session: Any, settings_str: str, gw: Any, navigator: Any) -> int:
    from viewer import cli as cli_mod

    if (
        gw.identify(session) != "system_settings"
        and navigator.goto("system_settings") != "system_settings"
    ):
        print("error: could not reach system_settings", file=sys.stderr)
        return 1
    pairs: dict[str, str] = {}
    for part in settings_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            print(f"error: expected key=value, got '{part}'", file=sys.stderr)
            return 1
        k, v = part.split("=", 1)
        pairs[k.strip()] = v.strip()
    unknown = [k for k in pairs if k not in cli_mod.IN_GAME_SETTINGS]
    if unknown:
        valid = ", ".join(sorted(cli_mod.IN_GAME_SETTINGS))
        print(f"error: unknown setting(s) {unknown}; valid: {valid}", file=sys.stderr)
        return 1
    for k, v in pairs.items():
        entry = cli_mod.IN_GAME_SETTINGS[k]
        values = cast(set[str], entry["values"])
        if v not in values:
            valid = ", ".join(sorted(values))
            print(f"error: {k}: invalid value '{v}'; valid: {valid}", file=sys.stderr)
            return 1
        setter = cast(Callable[[Any, str], str], entry["set"])
        result = setter(session, v)
        if result != v:
            print(f"{k}: failed to set {v} (result {result})", file=sys.stderr)
            return 1
        print(f"{k}={result}")
    return 0


POWER_ACTIONS = {"start", "stop", "restart", "start_all", "stop_all", "restart_all"}


def _parse_power_args(argv: list[str]) -> tuple[str, str] | None:
    """Return (action, target) for power subcommands, else None."""
    if not argv:
        return None
    token = argv[0]
    if token in ("start_all", "stop_all", "restart_all"):
        return (token[:-4], "all")
    if token in ("start", "stop", "restart"):
        if len(argv) < 2:
            return None
        return (token, argv[1])
    return None


def main() -> None:
    from .session import Session

    if "--list-sessions" in sys.argv:
        sessions = Session.list_sessions()
        if not sessions:
            print("No active sessions found")
        else:
            print(f"{'ID':<6} {'Frames':<10} {'Size':<12}")
            print("-" * 30)
            for s in sessions:
                print(f"{s['id']:<6} {s['frame']:<10} {s['width']}x{s['height']:<6}")
        sys.exit(0)

    power = _parse_power_args(sys.argv[1:])
    if power is not None:
        from gt_spector.bot_manager import BotManager
        from gt_spector.power import run_power_command

        manager = BotManager()
        manager.load_from_prefixes()
        action, target = power
        sys.exit(run_power_command(manager, action, target))

    parser = argparse.ArgumentParser(description="gt-spector: game testing inspector")
    parser.add_argument("--session", default=":9", help="DISPLAY target")
    parser.add_argument("--source", default=None, help="Frame source (default: shm://<session>)")
    parser.add_argument("--cli", action="store_true", help="CLI mode instead of GUI")
    parser.add_argument("--bot-console", action="store_true", help="Bot management console")
    parser.add_argument("--in-game-settings", default=None, help='one-shot init: "k=v,k2=v2"')
    args = parser.parse_args()

    if args.bot_console:
        from viewer.bot_console import BotConsole

        BotConsole().run()
        return

    from .session import Session

    source = args.source or f"shm://{args.session.lstrip(':')}"
    session = Session(args.session, source=source)

    if args.in_game_settings:
        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator
        from gt_spector.navigator import Navigator

        gw = GameWorld()
        locator = Locator()
        gw.set_locator(locator)
        navigator = Navigator(gw, locator, session)
        sys.exit(apply_in_game_settings(session, args.in_game_settings, gw, navigator))

    if args.cli:
        from viewer.cli import run_cli

        run_cli(session)
    else:
        from viewer.gui import run_gui

        run_gui(session)


if __name__ == "__main__":
    main()
