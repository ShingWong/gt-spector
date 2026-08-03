from gt_spector.scripts.help_bot import TRIGGER_X, TRIGGER_Y, HelpBot


def test_help_bot_uses_navigator_for_alliance(monkeypatch):
    calls = {}

    class FakeSession:
        def refresh(self):
            calls["refresh"] = True

        def get_pixel(self, x, y):
            return (200, 0, 0)

        def click(self, x, y):
            calls["click"] = (x, y)

    class FakeGW:
        def identify(self, session):
            return "avatar_menu"

    class FakeNavigator:
        def __init__(self, gw, locator, session):
            calls["ctor"] = True

        def goto(self, target):
            calls["goto"] = target
            return target

    monkeypatch.setattr("gt_spector.scripts.help_bot.Navigator", FakeNavigator)
    monkeypatch.setattr("gt_spector.scripts.help_bot.time.sleep", lambda s: None)
    b = HelpBot()
    b._gw = FakeGW()
    b._locator = object()
    b._session = FakeSession()
    b._navigate_to_help_dialog()
    assert calls["goto"] == "alliance_menu"
    assert calls["click"] == (TRIGGER_X, TRIGGER_Y)
