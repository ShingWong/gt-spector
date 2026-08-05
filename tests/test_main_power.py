from gt_spector import __main__ as M


def _fake_manager():
    class _Bot:
        def __init__(self, name):
            self.name = name
            self.state = "Offline"
            self.started = 0
            self.stopped = 0

    class _Manager:
        def __init__(self):
            self.bots = [_Bot("bot01"), _Bot("bot02")]

        def get(self, name):
            return next((b for b in self.bots if b.name == name), None)

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

    return _Manager()


def test_parse_power_args_basic():
    action, target = M._parse_power_args(["start", "bot01"])
    assert (action, target) == ("start", "bot01")


def test_parse_power_args_all_aliases():
    assert M._parse_power_args(["start_all"]) == ("start", "all")
    assert M._parse_power_args(["stop_all"]) == ("stop", "all")
    assert M._parse_power_args(["restart_all"]) == ("restart", "all")


def test_parse_power_args_no_target():
    assert M._parse_power_args(["start"]) is None


def test_parse_power_args_unknown():
    assert M._parse_power_args(["launch", "bot01"]) is None
