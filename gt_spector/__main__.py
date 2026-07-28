import argparse
import sys


def main():
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

    parser = argparse.ArgumentParser(description="gt-spector: game testing inspector")
    parser.add_argument("--session", default=":9", help="DISPLAY target")
    parser.add_argument("--source", default=None, help="Frame source (default: shm://<session>)")
    parser.add_argument("--cli", action="store_true", help="CLI mode instead of GUI")
    parser.add_argument("--bot-console", action="store_true", help="Bot management console")
    args = parser.parse_args()

    if args.bot_console:
        from viewer.bot_console import BotConsole

        BotConsole().run()
        return

    from .session import Session

    source = args.source or f"shm://{args.session.lstrip(':')}"
    session = Session(args.session, source=source)

    if args.cli:
        from viewer.cli import run_cli

        run_cli(session)
    else:
        from viewer.gui import run_gui

        run_gui(session)


if __name__ == "__main__":
    main()
