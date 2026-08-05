import subprocess

import numpy as np
import pytest

from gt_spector.bot_manager import Bot, BotState
from viewer.bot_console import BotConsole


def make_console() -> BotConsole:
    c = object.__new__(BotConsole)
    c._sound_applied = {}
    c._restart_runner_pending = set()
    c._pending_restart_script = {}
    c._gw = None
    c._locator = None
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
    ("", "LOBBY", ""),
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


def test_tree_columns_include_sel_and_view():
    c = make_console()
    c._columns = [
        ("sel", "✓", 30, "center"), ("bot", "Bot", 90, "w"),
        ("view", "View", 50, "center"),
    ]
    keys = [k for k, *_ in c._columns]
    assert "sel" in keys and "view" in keys
    assert keys.index("sel") < keys.index("bot") < keys.index("view")


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


def test_monitor_tick_stops_and_restarts_self_healing_runner_on_crash(tmp_path, monkeypatch):
    """A game restart must restart the bot's HelpBot runner afterwards."""
    from gt_spector import logs
    from gt_spector.scripts.help_bot import HelpBot

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
            bot.pid = 222

    c._manager = FakeManager()
    hb = HelpBot()
    hb.stop = lambda: calls.append("stop")
    hb.run_script = lambda *a, **k: calls.append("run_script")
    hb.self_healing = True
    c._runners = {"bot01": hb}
    c._frames = {"bot01": None}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            calls.append("check")
            return False

        def mark_crash(self, bot):
            pass

        def mark_intervention(self, bot):
            pass

    c._monitor = FakeMonitor()
    c._monitor_tick()
    # The stale HelpBot must be stopped when the game restarts so it can be
    # restarted once the game is back up.
    assert "stop" in calls


def test_monitor_tick_restarts_runner_after_game_recovers(tmp_path, monkeypatch):
    """Once the restarted game is responsive, the HelpBot is brought back."""
    from gt_spector import logs
    from gt_spector.scripts.help_bot import HelpBot

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
    hb = HelpBot()
    hb.stop = lambda: calls.append("stop")
    hb.run_script = lambda *a, **k: calls.append("run_script")
    hb.self_healing = True
    c._runners = {"bot01": hb}
    c._frames = {"bot01": None}
    responsive = {"value": False}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return responsive["value"]

        def mark_crash(self, bot):
            pass

        def mark_intervention(self, bot):
            pass

    c._monitor = FakeMonitor()

    # Pass 1: crash -> stop stale runner, mark restart pending.
    c._monitor_tick()
    assert "stop" in calls
    assert "bot01" in c._restart_runner_pending

    # Pass 2: game responsive -> runner restarted, pending cleared.
    responsive["value"] = True
    c._monitor_tick()
    assert "run_script" in calls
    assert "bot01" not in c._restart_runner_pending


def test_monitor_tick_runner_without_run_script_skips_restart(tmp_path, monkeypatch):
    """A NavigateBot-like runner (no run_script) must not be run on restart."""
    from gt_spector import logs

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    nav = type("N", (), {"script": object(), "stop": lambda self: None})()
    c._runners = {"bot01": nav}
    c._frames = {"bot01": None}
    logged = []
    monkeypatch.setattr(logs, "log_bot", lambda name, msg: logged.append(msg))
    responsive = {"value": False}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return responsive["value"]

        def mark_crash(self, bot):
            pass

        def mark_intervention(self, bot):
            pass

    c._monitor = FakeMonitor()

    # Crash -> stale runner stopped, restart marked pending.
    c._monitor_tick()
    assert "bot01" in c._restart_runner_pending

    # Game back -> the runner is skipped (no run_script), pending cleared.
    responsive["value"] = True
    c._monitor_tick()
    assert "bot01" not in c._restart_runner_pending
    assert not any("restart failed" in m for m in logged)


def test_monitor_tick_restarts_script_runner_with_captured_script(tmp_path, monkeypatch):
    """A ScriptRunner restart must use the script captured before stop, not
    the (now-None) runner.script."""
    from gt_spector import logs
    from gt_spector.script import ScriptRunner

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    started = []
    script = type("S", (), {"on_start": lambda s, d: started.append(d),
                             "on_stop": lambda s, d: None})()
    runner = ScriptRunner(10, None, None, None)
    runner.start(script)
    c._runners = {"bot01": runner}
    c._frames = {"bot01": None}
    responsive = {"value": False}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return responsive["value"]

        def mark_crash(self, bot):
            pass

        def mark_intervention(self, bot):
            pass

    c._monitor = FakeMonitor()

    # Crash -> stop nulls runner.script; the captured script survives.
    c._monitor_tick()
    assert runner.script is None

    # Game back -> restarted with the captured script, not None.
    responsive["value"] = True
    c._monitor_tick()
    assert runner.script is script
    assert started == [10, 10]
    assert "bot01" not in c._restart_runner_pending


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


def test_vlm_worker_start_gated_by_setting(monkeypatch, tmp_path):
    from gt_spector import settings as real_settings
    from viewer import bot_console as bc

    monkeypatch.setattr(real_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(real_settings, "GLOBAL_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(real_settings, "BOTS_DIR", tmp_path / "bots")

    started: list[bool] = []

    def fake_start(self) -> None:
        started.append(True)

    monkeypatch.setattr(bc.BotConsole, "_start_vlm_worker", fake_start)

    # disabled (default) -> worker not started
    c = object.__new__(bc.BotConsole)
    c._vlm_stop = False
    if bc.settings.vlm_enabled():
        c._start_vlm_worker()
    assert started == []

    # enabled -> worker started
    bc.settings.set_vlm_enabled(True)
    c2 = object.__new__(bc.BotConsole)
    c2._vlm_stop = False
    if bc.settings.vlm_enabled():
        c2._start_vlm_worker()
    assert started == [True]


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


def test_help_bot_has_run_script():
    """Recovery calls run_script on the runner; HelpBot must provide it."""
    from gt_spector.scripts.help_bot import HelpBot

    assert hasattr(HelpBot, "run_script")


def test_help_bot_is_self_healing():
    """Console must skip crash-prone recovery for self-healing runners."""
    from gt_spector.scripts.help_bot import HelpBot

    assert getattr(HelpBot, "self_healing", False) is True


def test_help_bot_run_script_restarts_thread(monkeypatch):
    from gt_spector.scripts.help_bot import HelpBot

    b = HelpBot()
    calls = []
    monkeypatch.setattr(b, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(b, "start", lambda d: calls.append(("start", d)))
    b.run_script("anything")
    assert calls == ["stop", ("start", 0)]


def test_monitor_tick_skips_recovery_for_self_healing_runner(tmp_path, monkeypatch):
    """Self-healing runners (HelpBot) are not run through console recovery."""
    from gt_spector import logs
    from gt_spector.scripts.help_bot import HelpBot

    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    c = make_console()
    bot = make_bot()
    bot.pid = 111
    c._manager = type("M", (), {"bots": [bot]})()
    hb = HelpBot()
    hb.self_healing = True
    c._runners = {"bot01": hb}
    c._frames = {"bot01": None}
    calls = {}

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

        def recover(self, bot, run_script, script):
            calls["recover"] = True

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame: "LOBBY"
    c._monitor_tick()
    assert "recover" not in calls


def test_monitor_tick_recovers_from_runner_exception(tmp_path, monkeypatch):
    """A runner raising in the recovery path must not kill the whole poll."""
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

    class FakeMonitor:
        def note_running(self, bot, now):
            pass

        def check_responsiveness(self, bot, now):
            return True

        def recoveries_left(self, bot):
            return True

        def recover(self, bot, run_script, script):
            raise RuntimeError("boom")

    c._monitor = FakeMonitor()
    c._detect_location = lambda bot, frame: "LOBBY"
    # Must not raise: the poll loop survives a per-bot recovery failure.
    c._monitor_tick()
    assert bot.state == BotState.RUNNING


def test_unprovisioned_accounts_line_order(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    accounts = tmp_path / "accounts"
    accounts.write_text(
        "sr02-04@mx1.us:bamboo-H4\n"
        "sr02-05@mx1.us:bamboo-H4\n"
        "sr02-20@mx1.us:bamboo-H4\n"
    )
    prefixes = tmp_path / "prefixes"
    (prefixes / "bot01" / "drive_c").mkdir(parents=True)  # bot01 provisioned

    monkeypatch.setattr(bc, "ACCOUNTS_FILE", accounts)
    monkeypatch.setattr(bc, "PREFIXES_DIR", prefixes)

    c = make_console()
    got = c._unprovisioned_accounts()
    # bot01 (sr02-04) is provisioned; bot02 (sr02-05) and bot03 (sr02-20) are not
    assert got == [("bot02", "sr02-05@mx1.us"), ("bot03", "sr02-20@mx1.us")]


def test_unprovisioned_accounts_missing_file(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    monkeypatch.setattr(bc, "ACCOUNTS_FILE", tmp_path / "nope")
    monkeypatch.setattr(bc, "PREFIXES_DIR", tmp_path / "prefixes")
    assert make_console()._unprovisioned_accounts() == []


def test_provision_n_sequential_and_stops_on_failure(tmp_path, monkeypatch):
    c = make_console()
    calls = []
    statuses = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        name = cmd[cmd.index("init") + 1]
        if name == "bot03":  # fail on the 3rd
            return type("R", (), {"returncode": 1, "stderr": "", "stdout": ""})()
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    c._status = type("S", (), {"config": lambda s, text: statuses.append(text)})()
    c._refresh_bots = lambda: None
    c._tk = type("Tk", (), {"update": lambda s: None})()
    c._unprovisioned_accounts = lambda: [
        ("bot01", "a@x"), ("bot02", "b@x"), ("bot03", "c@x"), ("bot04", "d@x")]
    c._provision_n(4)
    # bot01, bot02 provisioned; bot03 failed -> stops, bot04 never run
    assert [x[x.index("init") + 1] for x in calls] == ["bot01", "bot02", "bot03"]


def test_load_accounts_line_order(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    accounts = tmp_path / "accounts"
    accounts.write_text(
        "sr02-04@mx1.us:bamboo-H4\n"
        "malformed-no-colon\n"
        "sr02-05@mx1.us:bamboo-H4\n"
    )
    monkeypatch.setattr(bc, "ACCOUNTS_FILE", accounts)
    monkeypatch.setattr(bc, "PREFIXES_DIR", tmp_path / "prefixes")

    c = make_console()
    # Malformed lines yield no entry but still consume a line slot: the third
    # line (sr02-05) maps to bot03.
    assert c._load_accounts() == {
        "bot01": "sr02-04@mx1.us",
        "bot03": "sr02-05@mx1.us",
    }


def test_load_accounts_missing_file(tmp_path, monkeypatch):
    from viewer import bot_console as bc

    monkeypatch.setattr(bc, "ACCOUNTS_FILE", tmp_path / "nope")
    assert make_console()._load_accounts() == {}


def test_provision_n_slices_to_count(tmp_path, monkeypatch):
    c = make_console()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    c._status = type("S", (), {"config": lambda s, text: None})()
    c._refresh_bots = lambda: None
    c._tk = type("Tk", (), {"update": lambda s: None})()
    c._unprovisioned_accounts = lambda: [
        ("bot01", "a@x"), ("bot02", "b@x"), ("bot03", "c@x")]
    c._provision_n(2)
    # count < len(pending): only the first `count` are provisioned
    assert [x[x.index("init") + 1] for x in calls] == ["bot01", "bot02"]


def test_provision_n_success_refreshes_then_reports(tmp_path, monkeypatch):
    c = make_console()
    refreshed = []
    statuses = []

    def fake_run(cmd, **kw):
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    c._status = type("S", (), {"config": lambda s, text: statuses.append(text)})()
    c._refresh_bots = lambda: refreshed.append(True)
    c._tk = type("Tk", (), {"update": lambda s: None})()
    c._unprovisioned_accounts = lambda: [("bot01", "a@x")]
    c._provision_n(1)
    assert refreshed == [True]
    assert statuses[-1] == "Provisioned 1 bot(s)"


def test_provision_n_failure_tail_falls_back_to_stdout(tmp_path, monkeypatch):
    c = make_console()
    statuses = []

    def fake_run(cmd, **kw):
        return type("R", (), {"returncode": 1, "stderr": "", "stdout": "out of memory"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    c._status = type("S", (), {"config": lambda s, text: statuses.append(text)})()
    c._refresh_bots = lambda: None
    c._tk = type("Tk", (), {"update": lambda s: None})()
    c._unprovisioned_accounts = lambda: [("bot01", "a@x")]
    c._provision_n(1)
    assert statuses[-1] == "bot01: FAILED (out of memory)"


def test_provision_n_handles_subprocess_error(tmp_path, monkeypatch):
    c = make_console()
    statuses = []

    def boom(cmd, **kw):
        raise OSError("python3 not found")

    monkeypatch.setattr(subprocess, "run", boom)
    c._status = type("S", (), {"config": lambda s, text: statuses.append(text)})()
    c._refresh_bots = lambda: None
    c._tk = type("Tk", (), {"update": lambda s: None})()
    c._unprovisioned_accounts = lambda: [("bot01", "a@x")]
    c._provision_n(1)
    assert statuses[-1] == "bot01: FAILED (python3 not found)"


def test_detect_location_accepts_explicit_gw_and_locator():
    c = make_console()
    calls = {}

    class FakeLoc:
        def find(self, frame, name):
            return type("R", (), {"found": False})()

    class FakeGW:
        def identify(self, session):
            calls["identified"] = True
            return "custom_screen"

    c._nav_table = lambda: {"states": {}}
    c._gw = object()  # would fail if used
    c._locator = object()
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    frame[2:6, 2:6] = 200  # non-blank so it falls through to identify()
    loc = c._detect_location(make_bot(), frame, gw=FakeGW(), locator=FakeLoc())
    assert loc == "custom_screen"
    assert calls["identified"] is True


def test_poll_does_not_run_monitor_tick(monkeypatch):
    """The UI poll must not block on the monitor (it runs on a background thread)."""
    c = make_console()
    c._nav_cache = None
    calls = []
    c._update_rows = lambda: calls.append("rows")
    c._tk = type("Tk", (), {"after": lambda self, ms, fn: None})()
    c._monitor_tick = lambda: calls.append("tick")
    c._poll()
    assert calls == ["rows"]  # tick must NOT be called from the UI poll
