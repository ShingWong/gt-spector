import argparse


def main():
    parser = argparse.ArgumentParser(description="gt-spector: game testing inspector")
    parser.add_argument("--session", default=":9", help="DISPLAY target")
    parser.add_argument("--source", default="file:///tmp/test-frame.png", help="Frame source")
    parser.add_argument("--cli", action="store_true", help="CLI mode instead of GUI")
    args = parser.parse_args()

    from .session import Session

    session = Session(args.session, source=args.source)

    if args.cli:
        from viewer.cli import run_cli

        run_cli(session)
    else:
        from viewer.gui import run_gui

        run_gui(session)


if __name__ == "__main__":
    main()
