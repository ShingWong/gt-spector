import cmd
import io
import shlex
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from gt_spector.game_world import GameWorld
from gt_spector.locator import Locator
from gt_spector.navigator import Navigator

GQ_LOW = (825, 253)
GQ_HIGH = (966, 253)
GQ_HIGH_BRIGHT_R = 80
GQ_SETTLE = 2.0

FR_LOW = (745, 310)
FR_MID = (858, 310)
FR_HIGH = (973, 310)


def read_graphics_quality(session: Any) -> str:
    r, _, _ = session.get_pixel(*GQ_HIGH)
    return "high" if r >= GQ_HIGH_BRIGHT_R else "low"


def set_graphics_quality(session: Any, target: str) -> str:
    current = read_graphics_quality(session)
    if current == target:
        return current
    click = GQ_LOW if target == "low" else GQ_HIGH
    session.click(*click)
    import time
    time.sleep(GQ_SETTLE)
    session.refresh()
    return read_graphics_quality(session)


def read_frame_rate(session: Any) -> str:
    mid_r, _, _ = session.get_pixel(*FR_MID)
    high_r, _, _ = session.get_pixel(*FR_HIGH)
    if high_r >= 120:
        return "high"
    if mid_r >= 90:
        return "mid"
    return "low"


def set_frame_rate(session: Any, target: str) -> str:
    current = read_frame_rate(session)
    if current == target:
        return current
    click = {"low": FR_LOW, "mid": FR_MID, "high": FR_HIGH}[target]
    session.click(*click)
    import time
    time.sleep(GQ_SETTLE)
    session.refresh()
    return read_frame_rate(session)


IN_GAME_SETTINGS = {
    "graphics-quality": {
        "values": {"low", "high"},
        "read": read_graphics_quality,
        "set": set_graphics_quality,
    },
    "frame-rate": {
        "values": {"low", "mid", "high"},
        "read": read_frame_rate,
        "set": set_frame_rate,
    },
}


class CliSession(cmd.Cmd):
    intro = "gt-spector CLI. Type help or ? to list commands."
    prompt = "> "

    def __init__(self, session: Any) -> None:
        super().__init__()
        self._session = session
        self._display = int(self._session.display.lstrip(":")) if self._session.display else 9
        self._gw = GameWorld()
        self._locator = Locator()
        self._gw.set_locator(self._locator)
        self._navigator = Navigator(self._gw, self._locator, self._session)

    def do_pixel(self, arg: str) -> None:
        """pixel <x> <y> — Get pixel color"""
        args = shlex.split(arg)
        if len(args) != 2:
            print("Usage: pixel <x> <y>")
            return
        x, y = int(args[0]), int(args[1])
        r, g, b = self._session.get_pixel(x, y)
        print(f"({r}, {g}, {b})")

    def do_capture(self, arg: str) -> None:
        """capture [path] — Capture frame to PNG"""
        path = (
            arg
            or f"/tmp/gt-spector-capture-{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.png"
        )
        img = Image.fromarray(self._session.frame)
        img.save(path)
        print(f"captured {path}")

    def do_move(self, arg: str) -> None:
        """move <x> <y> [speed] — Move mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: move <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.move_mouse(x, y, speed)
        print("ok")

    def do_click(self, arg: str) -> None:
        """click <x> <y> [speed] — Click mouse"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("Usage: click <x> <y> [speed]")
            return
        x, y = int(args[0]), int(args[1])
        speed = int(args[2]) if len(args) > 2 else 400
        self._session.click(x, y, speed)
        print("ok")

    def do_drag(self, arg: str) -> None:
        """drag <x1> <y1> <x2> <y2> [speed] — Click-and-drag"""
        args = shlex.split(arg)
        if len(args) < 4:
            print("Usage: drag <x1> <y1> <x2> <y2> [speed]")
            return
        x1, y1, x2, y2 = map(int, args[:4])
        speed = int(args[4]) if len(args) > 4 else 400
        self._session.drag(x1, y1, x2, y2, speed)
        print("ok")

    def do_key(self, arg: str) -> None:
        """key <key> — Send keystroke (e.g. Return, Escape)"""
        key = arg.strip()
        if not key:
            print("Usage: key <key>")
            return
        self._session.key_press(key)
        print("ok")

    def do_type(self, arg: str) -> None:
        """type <text> — Type text"""
        text = arg.strip()
        if not text:
            print("Usage: type <text>")
            return
        self._session.type_text(text)
        print("ok")

    def _display_num(self) -> int:
        return self._display

    def do_where(self, arg: str) -> None:
        """where — identify the current screen"""
        self._session.refresh()
        screen = self._gw.identify(self._session)
        print(screen if screen else "unknown")

    def do_go(self, arg: str) -> None:
        """go <screen> [-v] — navigate to a screen; -v shows each hop"""
        args = shlex.split(arg)
        verbose = "-v" in args
        args = [a for a in args if a != "-v"]
        if not args:
            print("Usage: go <screen> [-v]")
            return
        target = args[0]
        trace = (lambda m: print(f"  {m}")) if verbose else None
        nav = Navigator(self._gw, self._locator, self._session, trace=trace)
        result = nav.goto(target)
        if result == target:
            print(f"arrived at {target}")
        else:
            print(f"navigation failed (stuck at {result or 'unknown'})")

    def do_route(self, arg: str) -> None:
        """route <screen> — print the BFS path without moving"""
        target = arg.strip()
        if not target:
            print("Usage: route <screen>")
            return
        path = self._navigator.route_to(target)
        print(" -> ".join(path) if path else "no path")

    def do_locate(self, arg: str) -> None:
        """locate <template> — find a template's current position"""
        name = arg.strip()
        if not name:
            print("Usage: locate <template>")
            return
        self._session.refresh()
        r = self._locator.find(self._session.frame, name)
        print(f"{name}: found={r.found} score={r.score:.3f} center=({r.cx},{r.cy})" if r.found
              else f"{name}: not found")

    def do_label(self, arg: str) -> None:
        """label <screen> — draw the screen's fixed templates on the overlay"""
        screen = arg.strip()
        if not screen:
            print("Usage: label <screen>")
            return
        import contextlib

        from gt_spector.scripts import label_fixed
        with contextlib.redirect_stdout(io.StringIO()):
            label_fixed.main_args(self._display_num(), screen)
        print(f"labeled fixed templates for {screen}")

    def do_screens(self, arg: str) -> None:
        """screens — list all known screens"""
        for name, spec in self._gw.screens.items():
            tmpl = spec.get("templates") or []
            print(f"  {name:24s} templates={tmpl}")

    def do_loc(self, arg: str) -> None:
        """loc <screen> <name> — show a location's coordinates"""
        parts = shlex.split(arg)
        if len(parts) != 2:
            print("Usage: loc <screen> <name>")
            return
        screen, name = parts
        pos = self._gw.loc(screen, name)
        print(f"{screen}.{name} = {pos}" if pos else f"{screen}.{name}: not found")

    def do_EOF(self, arg: str) -> bool:
        print()
        return True

    def do_quit(self, arg: str) -> bool:
        return True


def run_cli(session: Any) -> None:
    CliSession(session).cmdloop()
