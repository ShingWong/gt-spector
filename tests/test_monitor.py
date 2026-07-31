import numpy as np
import pytest
import requests


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


def test_should_vlm_check_throttled():
    from gt_spector.monitor import BotMonitor
    m = BotMonitor(None)
    bot = type("B", (), {"name": "bot01"})()
    now = 100.0
    assert m.should_vlm_check(bot, now) is True
    assert m.should_vlm_check(bot, now + 2) is False
    assert m.should_vlm_check(bot, now + 11) is True


def test_classify_frame_calls_vlm(monkeypatch):
    from gt_spector import monitor
    calls = {}

    class FakeVLM:
        def analyze_frame(self, frame, prompt=None, max_tokens=200):
            calls["shape"] = frame.shape
            return {"choices": [{"message": {"content": "SCREEN: ALLIANCE"}}]}

    m = monitor.BotMonitor(None, vlm=FakeVLM())
    import numpy as np
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    assert m.classify_frame(frame, 10) == "ALLIANCE"
    # 1/4 scale sent to VLM
    assert calls["shape"] == (216, 288, 3)


def test_classify_frame_returns_none_on_error(monkeypatch):
    from gt_spector import monitor
    m = monitor.BotMonitor(None, vlm=type("V", (), {"analyze_frame": lambda *a, **k: (_ for _ in ()).throw(RuntimeError())})())
    import numpy as np
    assert m.classify_frame(np.zeros((10, 10, 3), dtype=np.uint8), 10) is None


@pytest.mark.parametrize(
    "exc",
    [requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError],
)
def test_classify_frame_returns_none_on_request_errors(exc):
    from gt_spector import monitor
    m = monitor.BotMonitor(None, vlm=type("V", (), {"analyze_frame": lambda *a, **k: (_ for _ in ()).throw(exc())})())
    import numpy as np
    assert m.classify_frame(np.zeros((10, 10, 3), dtype=np.uint8), 10) is None


def test_classify_frame_content_none_returns_none():
    from gt_spector import monitor
    vlm = type("V", (), {"analyze_frame": lambda *a, **k: {"choices": [{"message": {"content": None}}]}})()
    m = monitor.BotMonitor(None, vlm=vlm)
    import numpy as np
    assert m.classify_frame(np.zeros((10, 10, 3), dtype=np.uint8), 10) is None


def test_classify_frame_non_dict_message_returns_none():
    from gt_spector import monitor
    vlm = type("V", (), {"analyze_frame": lambda *a, **k: {"choices": [{"message": "not a dict"}]}})()
    m = monitor.BotMonitor(None, vlm=vlm)
    import numpy as np
    assert m.classify_frame(np.zeros((10, 10, 3), dtype=np.uint8), 10) is None


def test_classify_frame_vlm_none_returns_none():
    from gt_spector import monitor
    m = monitor.BotMonitor(None)
    import numpy as np
    assert m.classify_frame(np.zeros((10, 10, 3), dtype=np.uint8), 10) is None


def test_vlm_tick_throttles_and_classifies():
    from gt_spector import monitor
    calls = []

    class FakeVLM:
        def analyze_frame(self, frame, prompt=None, max_tokens=200):
            calls.append(frame.shape)
            return {"choices": [{"message": {"content": "SCREEN: LOBBY"}}]}

    m = monitor.BotMonitor(None, vlm=FakeVLM())
    bot = type("B", (), {"name": "bot02", "display": 10})()
    import numpy as np
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    assert m.vlm_tick(frame, bot, 100.0) == "LOBBY"
    assert m.vlm_tick(frame, bot, 101.0) is None
    assert m.vlm_tick(frame, bot, 111.0) == "LOBBY"
    assert len(calls) == 2
