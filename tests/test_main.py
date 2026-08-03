def test_apply_in_game_settings_navigates_and_sets(monkeypatch):
    from gt_spector.__main__ import apply_in_game_settings
    from viewer import cli as cli_mod

    applied = {}
    calls = {"goto": []}

    class FakeSession:
        def __init__(self):
            self.display = ":10"

        def refresh(self):
            pass

    class FakeGW:
        def set_locator(self, loc):
            pass

        def identify(self, session):
            return "main_menu"

        def loc(self, screen, name):
            return (1, 1)

    class FakeNav:
        def goto(self, target):
            calls["goto"].append(target)
            return target

    def fake_set(session, target):
        applied["graphics-quality"] = target
        return target

    monkeypatch.setattr(
        cli_mod,
        "IN_GAME_SETTINGS",
        {
            "graphics-quality": {
                "values": {"low", "high"},
                "read": lambda s: "low",
                "set": fake_set,
            }
        },
    )

    result = apply_in_game_settings(FakeSession(), "graphics-quality=low", FakeGW(), FakeNav())
    assert result == 0
    assert calls["goto"] == ["system_settings"]
    assert applied.get("graphics-quality") == "low"


def test_apply_in_game_settings_unknown_key():
    from gt_spector.__main__ import apply_in_game_settings

    class FakeNav:
        def goto(self, target):
            return target

    class FakeGW:
        def identify(self, session):
            return "system_settings"

    result = apply_in_game_settings(None, "bogus=1", FakeGW(), FakeNav())
    assert result != 0  # non-zero exit on unknown key
