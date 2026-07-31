import numpy as np
import pytest

from gt_spector.bot_manager import Bot, BotState
from viewer.bot_console import BotConsole


def make_console() -> BotConsole:
    return object.__new__(BotConsole)


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
        (BotState.ERROR, ("✕", "Error")),
        (BotState.PAUSED, ("●", "Paused")),
    ],
)
def test_status_glyph(state, expected):
    assert make_console()._status_glyph(make_bot(state)) == expected


@pytest.mark.parametrize(
    "state,expected",
    [
        (BotState.RUNNING, "green"),
        (BotState.STARTING, "gold"),
        (BotState.OFFLINE, "red"),
        (BotState.ERROR, "red"),
        (BotState.PAUSED, "black"),
    ],
)
def test_status_color(state, expected):
    assert make_console()._status_color(make_bot(state)) == expected


def test_status_tooltip_no_script():
    c = make_console()
    c._runners = {}
    c._read_frame = lambda d: None
    assert c._status_tooltip(make_bot()) == "Running — no script, in ?"


def test_status_tooltip_with_script():
    from gt_spector.scripts.help_bot import HelpBot

    c = make_console()
    c._runners = {"bot01": type("R", (), {"script": HelpBot()})()}
    c._read_frame = lambda d: None
    assert c._status_tooltip(make_bot()) == "Running — help-bot, in ?"


def test_status_tooltip_with_interventions():
    from gt_spector.scripts.help_bot import HelpBot

    c = make_console()
    c._runners = {"bot01": type("R", (), {"script": HelpBot()})()}
    c._read_frame = lambda d: None
    bot = make_bot()
    bot.intervention_count = 3
    assert c._status_tooltip(bot) == "Running — help-bot, in ?, 3 interventions"


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
