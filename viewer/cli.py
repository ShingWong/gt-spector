import cmd
import shlex
from datetime import UTC, datetime

from PIL import Image


class CliSession(cmd.Cmd):
    intro = "gt-spector CLI. Type help or ? to list commands."
    prompt = "> "

    def __init__(self, session):
        super().__init__()
        self._session = session

    def do_pixel(self, arg):
        """pixel <x> <y> — Get pixel color"""
        args = shlex.split(arg)
        if len(args) != 2:
            print("Usage: pixel <x> <y>")
            return
        x, y = int(args[0]), int(args[1])
        r, g, b = self._session.get_pixel(x, y)
        print(f"({r}, {g}, {b})")

    def do_capture(self, arg):
        """capture [path] — Capture frame to PNG"""
        path = (
            arg
            or f"/tmp/gt-spector-capture-{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.png"
        )
        img = Image.fromarray(self._session.frame)
        img.save(path)
        print(f"captured {path}")

    def do_EOF(self, arg):
        print()
        return True

    def do_quit(self, arg):
        return True


def run_cli(session):
    CliSession(session).cmdloop()
