import numpy as np
import pytest

from gt_spector.bot_manager import Bot, BotState
from viewer.bot_console import BotConsole


def make_console() -> BotConsole:
    c = object.__new__(BotConsole)
    c._sound_applied = {}
    return c


def make_bot(state: BotState = BotState.RUNNING, name: str = "bot01") -> Bot:
    bot = Bot(name=name)
    bot.state = state
    return bot


@pytest.mark.parametrize(
    "state,expected",
    [
        (BotState.RUNNING, ("●", "Running")),
        (BotState.STARTING, ("◐", "Starting")),
        (BotState.OFFLINE, ("✕", "Offline")),
        (BotState.ERROR, ("▲", "Alert")),
        (BotState.PAUSED, ("●", "Paused")),
    ],
)
def test_status_glyph(state, expected):
    assert make_console()._status_glyph(make_bot(state)) == expected


@pytest.mark.parametrize("script,loc,expected", [
    ("help_bot", "LOBBY", "help_bot @ LOBBY"),
    ("help_bot", None, "help_bot @ ?"),
    ("", "LOBBY", "LOBBY"),
    ("", None, ""),
    ("", "?", ""),
])
def test_status_text(script, loc, expected):
    assert BotConsole._status_text(script, loc) == expected


@pytest.mark.parametrize(
    "state,expected",
    [
        (BotState.RUNNING, "green"),
        (BotState.STARTING, "gold"),
        (BotState.OFFLINE, "red"),
        (BotState.ERROR, "blue"),
        (BotState.PAUSED, "black"),
    ],
)
def test_status_color(state, expected):
    assert make_console()._status_color(make_bot(state)) == expected


def test_status_tooltip_no_script():
    c = make_console()
    c._runners = {}
    c._read_frame = lambda d: None
    assert c._status_tooltip(make_bot()) == "Running — in ?"


def test_status_tooltip_with_script():
    from gt_spector.scripts.help_bot import HelpBot

    c = make_console()
    c._runners = {"bot01": type("R", (), {"script": HelpBot()})()}
    c._read_frame = lambda d: None
    assert c._status_tooltip(make_bot()) == "Running — help-bot in ?"


def test_status_tooltip_with_interventions():
    from gt_spector.scripts.help_bot import HelpBot

    c = make_console()
    c._runners = {"bot01": type("R", (), {"script": HelpBot()})()}
    c._read_frame = lambda d: None
    bot = make_bot()
    bot.intervention_count = 3
    assert c._status_tooltip(bot) == "Running — help-bot in ?, 3 interventions"


def test_detect_location_no_frame():
    assert make_console()._detect_location(make_bot(), None) == "?"


def test_detect_location_blank():
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    assert make_console()._detect_location(make_bot(), frame) == "blank"


def test_detect_location_match():
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    frame[545:555, 925:935] = (200, 50, 50)
    c = make_console()
    c._nav_table = lambda: {
        "states": {
            "ALLIANCE": {
                "fingerprints": [
                    {"x": 930, "y": 550, "r": (150, 255), "g": (0, 100), "b": (0, 100)}
                ]
            }
        }
    }
    assert c._detect_location(make_bot(), frame) == "ALLIANCE"


def test_detect_location_falls_back_to_vlm_cache():
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    frame[545:555, 925:935] = (200, 50, 50)
    c = make_console()
    c._nav_table = lambda: {"states": {}}
    c._vlm_screens = {"bot01": "ALLIANCE"}
    assert c._detect_location(make_bot(), frame) == "ALLIANCE"


def test_make_vlm_none_when_module_unavailable(monkeypatch):
    import sys

    from viewer.bot_console import _make_vlm

    monkeypatch.setitem(sys.modules, "gt_spector.vlm", None)
    assert _make_vlm() is None


def test_make_vlm_adapter_wraps_module(monkeypatch):
    import sys
    from types import SimpleNamespace

    from viewer.bot_console import _make_vlm

    calls = []
    fake = SimpleNamespace(
        analyze_frame=lambda frame, prompt=None, max_tokens=500:
        calls.append((frame, prompt, max_tokens)) or {})
    monkeypatch.setitem(sys.modules, "gt_spector.vlm", fake)
    vlm = _make_vlm()
    assert vlm is not None
    vlm.analyze_frame("f", prompt="P", max_tokens=200)
    assert calls == [("f", "P", 200)]


def test_monitor_tick_recover_when_attempts_left(tmp_path, monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    script = type("S", (), {"expected_screen": "ALLIANCE"})()
    runner = type("R", (), {"script": script})()
    runner.run_script = lambda s: None
    c._runners = {"bot01": runner}
    c._frames = {"bot01": None}
    calls = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

        def recoveries_left(self, bot):
            return True

        def recover(self, bot, run_script, script):
            calls["recover"] = (run_script, script)

        def recovery_succeeded(self, bot):
            calls["succeeded"] = True

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame: "LOBBY"
    c._monitor_tick()
    run_closure, recovered_script = calls["recover"]
    assert recovered_script is script
    run_closure(bot, script)
    assert "succeeded" not in calls
    assert bot.state == BotState.RUNNING


def test_monitor_tick_marks_error_when_recovery_exhausted(tmp_path, monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    script = type("S", (), {"expected_screen": "ALLIANCE"})()
    runner = type("R", (), {"script": script})()
    c._runners = {"bot01": runner}
    c._frames = {"bot01": None}
    calls = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

        def recoveries_left(self, bot):
            return False

        def mark_error(self, bot, runner):
            calls["marked"] = (bot, runner)

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame: "LOBBY"
    c._monitor_tick()
    assert calls["marked"] == (bot, runner)
    assert bot.state == BotState.ERROR


def test_monitor_tick_recovery_succeeded_on_expected_screen(tmp_path, monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    script = type("S", (), {"expected_screen": "ALLIANCE"})()
    runner = type("R", (), {"script": script})()
    c._runners = {"bot01": runner}
    c._frames = {"bot01": None}
    calls = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

        def recoveries_left(self, bot):
            return True

        def recovery_succeeded(self, bot):
            calls["succeeded"] = True

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame: "ALLIANCE"
    c._monitor_tick()
    assert calls["succeeded"] is True
    assert bot.state == BotState.RUNNING


def test_monitor_tick_reapplies_sound_on_pid_change(tmp_path, monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    c._runners = {}
    c._frames = {}
    applied = []
    c._apply_sound_for_bot = lambda bot: (applied.append(bot.pid),
                                          c._sound_applied.__setitem__(bot.name, bot.pid))

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

    c._monitor = FakeMonitor()
    c._monitor_tick()
    assert applied == [111]
    assert c._sound_applied == {"bot01": 111}
    c._monitor_tick()
    assert applied == [111]
    bot.pid = 222
    c._monitor_tick()
    assert applied == [111, 222]


def test_monitor_tick_crash_restarts_game(tmp_path, monkeypatch):
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    calls = []

    class FakeManager:
        def __init__(self):
            self.bots = [bot]

        def restart_game(self, bot):
            calls.append("restart")

    c._manager = FakeManager()
    c._runners = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            calls.append("note")

        def check_responsiveness(self, bot, now):
            return False

        def mark_crash(self, bot):
            calls.append("crash")

        def mark_intervention(self, bot):
            calls.append("intervention")

    c._monitor = FakeMonitor()
    c._monitor_tick()
    assert calls.count("note") == 1
    assert calls.count("crash") == 1
    assert calls.count("restart") == 1
    assert calls.count("intervention") == 1


def test_save_geometry_atomic(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    c = make_console()
    c._tk = type("Tk", (), {"geometry": lambda self: "640x480+10+20"})()
    c._save_geometry()
    p = tmp_path / ".config" / "gt-spector" / "console_geometry.json"
    assert json.loads(p.read_text()) == {"w": 640, "h": 480, "x": 10, "y": 20}
    assert not p.with_name("console_geometry.json.tmp").exists()


def test_on_close_saves_geometry(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    c = make_console()
    calls = []
    c._tk = type("Tk", (), {"geometry": lambda self: "600x500+5+5",
                            "destroy": lambda self: calls.append("destroy")})()
    c._manager = type("M", (), {"stop_all": lambda self: calls.append("stop_all")})()
    c._on_close()
    assert calls == ["destroy"]
    assert (tmp_path / ".config" / "gt-spector" / "console_geometry.json").exists()


def test_on_close_does_not_stop_games(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    c = make_console()
    calls = []
    c._tk = type("Tk", (), {"geometry": lambda self: "600x500+5+5",
                            "destroy": lambda self: calls.append("destroy")})()
    c._manager = type("M", (), {"stop_all": lambda self: calls.append("stop_all")})()
    c._on_close()
    assert "stop_all" not in calls


@pytest.mark.parametrize(
    "loc,expected,should",
    [
        (None, "ALLIANCE", False),
        ("?", "ALLIANCE", False),
        ("blank", "ALLIANCE", False),
        ("ALLIANCE", "ALLIANCE", False),
        ("LOBBY", "ALLIANCE", True),
    ],
)
def test_needs_recovery(loc, expected, should):
    assert make_console()._needs_recovery(loc, expected) is should


def test_parse_shm_frame_empty():
    assert make_console()._parse_shm_frame(b"") is None


def test_parse_shm_frame_short():
    assert make_console()._parse_shm_frame(b"\x01\x00" * 4) is None


def test_parse_shm_frame_ok():
    import struct

    h, w = 2, 3
    data = struct.pack("<QII", 1, w, h) + b"\x0a\x0b\x0c\xff" * (h * w)
    frame = make_console()._parse_shm_frame(data)
    assert frame is not None and frame.shape == (h, w, 4)
    assert tuple(frame[0, 0]) == (10, 11, 12, 255)


def test_nav_table_missing(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "expanduser", lambda self: tmp_path / "missing.json")
    assert make_console()._nav_table() == {"states": {}}


def test_nav_table_parse(tmp_path, monkeypatch):
    from pathlib import Path

    p = tmp_path / "nav.json"
    p.write_text('{"states": {"LOBBY": {"fingerprints": []}}}')
    monkeypatch.setattr(Path, "expanduser", lambda self: p)
    assert make_console()._nav_table() == {"states": {"LOBBY": {"fingerprints": []}}}


def test_run_script_alias():
    from gt_spector.script import ScriptRunner
    from gt_spector.scripts.help_bot import HelpBot

    runner = ScriptRunner(10, None, None, None)
    started: list[str] = []
    runner.start = lambda s: started.append(s.name)
    runner.run_script(HelpBot())
    assert started == ["help-bot"]


def test_help_bot_expected_screen():
    from gt_spector.scripts.help_bot import HelpBot

    assert HelpBot.expected_screen == "ALLIANCE"
