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
    from gt_spector import monitor, settings
    monkeypatch.setattr(settings, "vlm_downscale", lambda: 2)
    calls = {}

    class FakeVLM:
        def analyze_frame(self, frame, prompt=None, max_tokens=200):
            calls["shape"] = frame.shape
            return {"choices": [{"message": {"content": "SCREEN: ALLIANCE"}}]}

    m = monitor.BotMonitor(None, vlm=FakeVLM())
    import numpy as np
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    assert m.classify_frame(frame, 10) == "ALLIANCE"
    # 1/2 scale sent to VLM (higher res than the old 1/4)
    assert calls["shape"] == (432, 576, 3)


def test_classify_frame_uses_settable_downscale(monkeypatch):
    from gt_spector import monitor, settings
    monkeypatch.setattr(settings, "vlm_downscale", lambda: 4)
    calls = {}

    class FakeVLM:
        def analyze_frame(self, frame, prompt=None, max_tokens=200):
            calls["shape"] = frame.shape
            return {"choices": [{"message": {"content": "SCREEN: LOBBY"}}]}

    m = monitor.BotMonitor(None, vlm=FakeVLM())
    import numpy as np
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    assert m.classify_frame(frame, 10) == "LOBBY"
    assert calls["shape"] == (216, 288, 3)


def test_gpu_slot_free():
    from gt_spector import monitor
    assert monitor.gpu_slot_free({"gpu_busy_percent": 10.0}) is True
    assert monitor.gpu_slot_free({"gpu_busy_percent": 95.0}) is False
    assert monitor.gpu_slot_free({}) is True


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


def test_check_responsiveness_within_grace_missing_counter(monkeypatch):
    from gt_spector import monitor
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    m = monitor.BotMonitor(None)
    bot = type("B", (), {"name": "bot01", "pid": 111, "shm_path": "/nonexistent/missing-shm"})()
    m.note_running(bot, 100.0)
    assert m.check_responsiveness(bot, 150.0) is True


def test_check_responsiveness_within_grace_stalled_counter(monkeypatch, tmp_path):
    import struct

    from gt_spector import monitor
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    shm = tmp_path / "frame"
    shm.write_bytes(struct.pack("<Q", 42))
    m = monitor.BotMonitor(None)
    bot = type("B", (), {"name": "bot01", "pid": 111, "shm_path": str(shm)})()
    m.note_running(bot, 100.0)
    assert m.check_responsiveness(bot, 150.0) is True


def test_check_responsiveness_stalled_counter_after_grace(monkeypatch, tmp_path):
    import struct

    from gt_spector import monitor
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    shm = tmp_path / "frame"
    shm.write_bytes(struct.pack("<Q", 42))
    m = monitor.BotMonitor(None)
    bot = type("B", (), {"name": "bot01", "pid": 111, "shm_path": str(shm)})()
    m.note_running(bot, 100.0)
    assert m.check_responsiveness(bot, 161.0) is False


def test_check_responsiveness_advancing_counter_after_grace(monkeypatch):
    from gt_spector import monitor
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    m = monitor.BotMonitor(None)
    values = iter([42, 43])
    m._read_counter = lambda path: next(values)
    bot = type("B", (), {"name": "bot01", "pid": 111, "shm_path": "/dev/shm/x"})()
    m.note_running(bot, 100.0)
    assert m.check_responsiveness(bot, 161.0) is True


def test_note_running_new_pid_resets_grace(monkeypatch):
    from gt_spector import monitor
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    m = monitor.BotMonitor(None)
    bot = type("B", (), {"name": "bot01", "pid": 111, "shm_path": "/nonexistent/missing-shm"})()
    m.note_running(bot, 0.0)
    bot.pid = 222
    m.note_running(bot, 100.0)
    assert m.check_responsiveness(bot, 159.0) is True


def _stub_xdotool(monkeypatch) -> None:
    """Force recover()'s xdotool lookup to fail fast (no ESC chain)."""
    from gt_spector import monitor

    def fake_run(*args, **kwargs):
        raise OSError("xdotool unavailable")

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)


def test_recover_increments_attempts_up_to_limit(monkeypatch, tmp_path):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    _stub_xdotool(monkeypatch)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    assert m.recoveries_left(bot) is True
    for _ in range(monitor.MAX_RECOVERY_ATTEMPTS):
        m.recover(bot, lambda b, s: None, None)
    assert m.recoveries_left(bot) is False


def test_recovery_succeeded_resets_attempts(monkeypatch, tmp_path):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    _stub_xdotool(monkeypatch)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    for _ in range(monitor.MAX_RECOVERY_ATTEMPTS):
        m.recover(bot, lambda b, s: None, None)
    assert m.recoveries_left(bot) is False
    m.recovery_succeeded(bot)
    assert m.recoveries_left(bot) is True


def test_note_running_new_pid_resets_recovery_attempts(monkeypatch, tmp_path):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    _stub_xdotool(monkeypatch)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    for _ in range(monitor.MAX_RECOVERY_ATTEMPTS):
        m.recover(bot, lambda b, s: None, None)
    assert m.recoveries_left(bot) is False
    bot.pid = 999
    m.note_running(bot, 0.0)
    assert m.recoveries_left(bot) is True


def test_mark_error_logs_and_stops_runner(monkeypatch, tmp_path):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    stopped: list[str] = []
    runner = type("R", (), {"stop": lambda self: stopped.append("stopped")})()
    m = monitor.BotMonitor(None)
    m.mark_error(bot, runner)
    assert stopped == ["stopped"]
    assert "ERROR" in (tmp_path / "bot01.log").read_text()


def test_mark_error_runner_without_stop_noop(monkeypatch, tmp_path):
    from gt_spector import logs, monitor
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    from gt_spector.bot_manager import Bot
    bot = Bot(name="bot01", display=10)
    m = monitor.BotMonitor(None)
    m.mark_error(bot, object())
    assert "ERROR" in (tmp_path / "bot01.log").read_text()


def test_refresh_state_preserves_error_state(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager, BotState
    bot = Bot(name="bot01")
    bot.state = BotState.ERROR
    bot.pid = 424242
    m = BotManager()
    monkeypatch.setattr(m, "_pid_alive", lambda pid: True)
    m._refresh_state(bot)
    assert bot.state == BotState.ERROR
