def test_standard_settings_constant():
    from gt_spector.provision import _STANDARD_SETTINGS
    assert _STANDARD_SETTINGS == (
        "graphics-quality=low,frame-rate=low,sound-effects=off,background-music=off"
    )


def test_apply_standard_settings_calls_flow(monkeypatch):
    import gt_spector.provision as p

    started = []
    stopped = []
    waited = []
    applied = []

    class FakeBot:
        display = 14

    class FakeManager:
        def start_game(self, bot):
            started.append(bot.display)
        def stop_game(self, bot):
            stopped.append(bot.display)

    monkeypatch.setattr(p, "_Bot", lambda *a, **k: FakeBot())
    monkeypatch.setattr(p, "_Manager", FakeManager)
    monkeypatch.setattr(p, "_wait_for_game", lambda bot: waited.append(bot.display))
    monkeypatch.setattr(p, "_run_settings_apply", lambda d: applied.append(d))

    p._apply_standard_settings("bot05", "/p")
    assert started == [14]
    assert stopped == [14]
    assert waited == [14]
    assert applied == [14]


def test_apply_standard_settings_stops_game_on_failure(monkeypatch):
    import gt_spector.provision as p

    stopped = []

    class FakeBot:
        display = 14

    class FakeManager:
        def start_game(self, bot):
            pass
        def stop_game(self, bot):
            stopped.append(bot.display)

    def boom(display):
        raise RuntimeError("settings apply failed")

    monkeypatch.setattr(p, "_Bot", lambda *a, **k: FakeBot())
    monkeypatch.setattr(p, "_Manager", FakeManager)
    monkeypatch.setattr(p, "_wait_for_game", lambda bot: None)
    monkeypatch.setattr(p, "_run_settings_apply", boom)

    import pytest
    with pytest.raises(RuntimeError):
        p._apply_standard_settings("bot05", "/p")
    assert stopped == [14]
