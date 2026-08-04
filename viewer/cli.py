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

SOUND_OFF = (906, 532)
SOUND_ON = (955, 532)
MUSIC_OFF = (906, 638)
MUSIC_ON = (955, 638)

SETTINGS_SCROLL_POINT = (600, 400)
SETTINGS_MAX_SCROLLS = 30
SETTINGS_SCROLL_SETTLE = 0.8


def ensure_settings_row(session: Any, position: str) -> bool:
    """Scroll the system settings list to the hard stop for the target group.

    position "top" targets the graphics-quality/frame-rate rows, "bottom"
    the sound-effects/background-music rows. The list has no scrollbar and a
    hard stop at each end, so we scroll until the frame stops changing.
    """
    if position == "top":
        sentinels = (GQ_LOW, GQ_HIGH)
        direction = 1
    elif position == "bottom":
        sentinels = (SOUND_OFF, SOUND_ON)
        direction = -1
    else:
        raise ValueError(f"unknown settings row position: {position}")
    import time
    session.move_mouse(*SETTINGS_SCROLL_POINT)
    if any(session.get_pixel(x, y)[0] > 80 for x, y in sentinels):
        return True
    prev = None
    stable = 0
    for _ in range(SETTINGS_MAX_SCROLLS):
        session.scroll(direction, 3)
        time.sleep(SETTINGS_SCROLL_SETTLE)
        session.refresh()
        cur = session.frame
        if prev is not None:
            diff = (cur.astype(int) - prev.astype(int)).__abs__().sum()
            if diff < 500000:
                stable += 1
                if stable >= 2:
                    break
                prev = cur
                continue
        prev = cur
    return any(session.get_pixel(x, y)[0] > 80 for x, y in sentinels)


def read_graphics_quality(session: Any) -> str:
    r, _, _ = session.get_pixel(*GQ_HIGH)
    return "high" if r >= GQ_HIGH_BRIGHT_R else "low"


def set_graphics_quality(session: Any, target: str) -> str:
    if not ensure_settings_row(session, "top"):
        return "unreachable"
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
    if not ensure_settings_row(session, "top"):
        return "unreachable"
    current = read_frame_rate(session)
    if current == target:
        return current
    click = {"low": FR_LOW, "mid": FR_MID, "high": FR_HIGH}[target]
    session.click(*click)
    import time
    time.sleep(GQ_SETTLE)
    session.refresh()
    return read_frame_rate(session)


def read_sound_effects(session: Any) -> str:
    r, _, _ = session.get_pixel(*SOUND_ON)
    return "on" if r >= 80 else "off"


def set_sound_effects(session: Any, target: str) -> str:
    if not ensure_settings_row(session, "bottom"):
        return "unreachable"
    current = read_sound_effects(session)
    if current == target:
        return current
    click = SOUND_OFF if target == "off" else SOUND_ON
    session.click(*click)
    import time
    time.sleep(GQ_SETTLE)
    session.refresh()
    return read_sound_effects(session)


def read_background_music(session: Any) -> str:
    r, _, _ = session.get_pixel(*MUSIC_ON)
    return "on" if r >= 80 else "off"


def set_background_music(session: Any, target: str) -> str:
    if not ensure_settings_row(session, "bottom"):
        return "unreachable"
    current = read_background_music(session)
    if current == target:
        return current
    click = MUSIC_OFF if target == "off" else MUSIC_ON
    session.click(*click)
    import time
    time.sleep(GQ_SETTLE)
    session.refresh()
    return read_background_music(session)


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
    "sound-effects": {
        "values": {"on", "off"},
        "read": read_sound_effects,
        "set": set_sound_effects,
    },
    "background-music": {
        "values": {"on", "off"},
        "read": read_background_music,
        "set": set_background_music,
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
