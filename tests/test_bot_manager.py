def test_refresh_state_not_running_when_only_xvfb_alive(monkeypatch):
    from gt_spector.bot_manager import Bot, BotManager, BotState

    m = BotManager()
    bot = Bot(name="bot10", xvfb_pid=99999)  # fake alive xvfb

    def fake_find_game_pid(b):
        return None  # no game process

    monkeypatch.setattr(m, "_find_game_pid", fake_find_game_pid)
    monkeypatch.setattr(m, "_pid_alive", lambda pid: True)  # xvfb "alive"

    m._refresh_state(bot)
    # Xvfb alive but no game -> NOT Running (STARTING or OFFLINE)
    assert bot.state != BotState.RUNNING
