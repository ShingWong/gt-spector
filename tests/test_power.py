import gt_spector.power as P
from gt_spector.power import run_power_command


class _Bot:
    def __init__(self, name, state):
        self.name = name
        self.state = state
        self.started = 0
        self.stopped = 0


class _FakeManager:
    def __init__(self, bots):
        self.bots = bots

    def get(self, name):
        for b in self.bots:
            if b.name == name:
                return b
        return None

    def start_game(self, bot):
        bot.started += 1
        bot.state = "Running"

    def stop_game(self, bot):
        bot.stopped += 1
        bot.state = "Offline"

    def restart_game(self, bot):
        bot.stopped += 1
        bot.started += 1
        bot.state = "Running"

    def _refresh_state(self, bot):
        return bot.state


def test_start_unknown_bot_returns_1(capsys):
    m = _FakeManager([])
    assert run_power_command(m, "start", "bot99") == 1
    assert "bot99" in capsys.readouterr().err


def test_start_single_bot(capsys, monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    b = _Bot("bot07", "Offline")
    m = _FakeManager([b])
    assert run_power_command(m, "start", "bot07") == 0
    assert b.started == 1
    assert "Running" in capsys.readouterr().out


def test_stop_single_bot(capsys, monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    b = _Bot("bot07", "Running")
    m = _FakeManager([b])
    assert run_power_command(m, "stop", "bot07") == 0
    assert b.stopped == 1
    assert "Offline" in capsys.readouterr().out


def test_restart_single_bot(monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    b = _Bot("bot07", "Offline")
    m = _FakeManager([b])
    assert run_power_command(m, "restart", "bot07") == 0
    assert b.stopped == 1 and b.started == 1


def test_all_target_acts_on_every_bot(capsys, monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    b1 = _Bot("bot01", "Offline")
    b2 = _Bot("bot02", "Offline")
    m = _FakeManager([b1, b2])
    assert run_power_command(m, "start", "all") == 0
    assert b1.started == 1 and b2.started == 1


def test_all_target_one_failure_returns_1(capsys, monkeypatch):
    monkeypatch.setattr(P, "START_WAIT", 0)
    b1 = _Bot("bot01", "Offline")
    m = _FakeManager([b1])

    def boom(bot):
        raise RuntimeError("xvfb failed")
    m.start_game = boom

    assert run_power_command(m, "start", "all") == 1
    assert "bot01" in capsys.readouterr().err


def test_start_all_zero_bots_returns_1(capsys):
    m = _FakeManager([])
    assert run_power_command(m, "start", "all") == 1


def test_invalid_action_returns_2():
    m = _FakeManager([])
    assert run_power_command(m, "fly", "all") == 2
