import numpy as np
import pytest


@pytest.fixture()
def nav_table():
    return {
        "states": {
            "ALLIANCE": {
                "fingerprints": [{"x": 930, "y": 550, "r": (150, 255), "g": (0, 100), "b": (0, 100)}],
            },
            "LOBBY": {
                "fingerprints": [{"x": 50, "y": 764, "r": (0, 100), "g": (0, 100), "b": (100, 255)}],
            },
        }
    }


def make_frame(rgb_at):
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    for (x, y), rgb in rgb_at.items():
        frame[y, x] = rgb
    return frame


def test_detect_screen_match(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (200, 50, 50)})  # matches ALLIANCE red badge
    assert detect_screen(frame, nav_table) == "ALLIANCE"


def test_detect_screen_no_match(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (0, 0, 0)})
    assert detect_screen(frame, nav_table) is None


def test_detect_screen_multiple(nav_table):
    from gt_spector.monitor import detect_screen
    frame = make_frame({(930, 550): (200, 50, 50), (50, 764): (0, 0, 200)})
    # ALLIANCE checked first, matches
    assert detect_screen(frame, nav_table) == "ALLIANCE"


def test_frame_is_blank():
    from gt_spector.monitor import frame_is_blank
    assert frame_is_blank(np.zeros((100, 100, 3), dtype=np.uint8)) is True
    assert frame_is_blank(np.full((100, 100, 3), 255, dtype=np.uint8)) is True
    noisy = np.zeros((100, 100, 3), dtype=np.uint8)
    noisy[50, 50] = (128, 128, 128)
    assert frame_is_blank(noisy) is False


def test_mark_crash_and_intervention(tmp_path, monkeypatch):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    m.mark_crash(bot)
    assert bot.crash_count == 1
    m.mark_intervention(bot)
    assert bot.intervention_count == 1
