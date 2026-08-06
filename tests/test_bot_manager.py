def test_refresh_state_not_running_when_only_xvfb_alive(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager, BotState

    m = BotManager()
    bot = Bot(name="bot10", xvfb_pid=99999, pid=12345)  # stale pid + alive xvfb

    def fake_find_game_pid(b):
        return None  # no game process

    monkeypatch.setattr(m, "_find_game_pid", fake_find_game_pid)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: pid == 99999)  # only xvfb alive

    m._refresh_state(bot)
    assert bot.state == BotState.STARTING
    assert bot.pid is None  # stale pid cleared


def test_stop_game_kills_xvfb(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager

    m = BotManager()
    bot = Bot(name="bot10", xvfb_pid=12345, display=19)
    killed = []

    def fake_find_game_pids_by_display(display):
        return []

    def fake_pid_alive(pid):
        return True

    def fake_killpg(pgid, sig):
        killed.append(pgid)

    monkeypatch.setattr(m, "_find_game_pids_by_display", fake_find_game_pids_by_display)
    monkeypatch.setattr(m, "_pid_alive", fake_pid_alive)
    monkeypatch.setattr("gt_spector.bot_manager.os.killpg", fake_killpg)
    monkeypatch.setattr("gt_spector.bot_manager.os.getpgid", lambda pid: pid)

    m.stop_game(bot)
    # the xvfb_pid must have been killed
    assert 12345 in killed
