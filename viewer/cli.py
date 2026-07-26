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

    def do_move(self, arg):
        """move <x> <y> [speed] — Move mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: move <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.move_mouse(x, y, speed)
        print("ok")

    def do_click(self, arg):
        """click <x> <y> [speed] — Click mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: click <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.click(x, y, speed)
        print("ok")

    def do_drag(self, arg):
        """drag <x1> <y1> <x2> <y2> [speed] — Click-and-drag"""
        args = shlex.split(arg)
        if len(args) < 4:
            print("Usage: drag <x1> <y1> <x2> <y2> [speed]")
            return
        x1, y1, x2, y2 = map(int, args[:4])
        speed = int(args[4]) if len(args) > 4 else 400
        self._session.drag(x1, y1, x2, y2, speed)
        print("ok")

    def do_key(self, arg):
        """key <key> — Send keystroke (e.g. Return, Escape)"""
        key = arg.strip()
        if not key:
            print("Usage: key <key>")
            return
        self._session.key_press(key)
        print("ok")

    def do_type(self, arg):
        """type <text> — Type text"""
        text = arg.strip()
        if not text:
            print("Usage: type <text>")
            return
        self._session.type_text(text)
        print("ok")

    def do_EOF(self, arg):
        print()
        return True

    def do_quit(self, arg):
        return True


def run_cli(session):
    CliSession(session).cmdloop()
