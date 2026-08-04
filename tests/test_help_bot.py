from gt_spector.scripts.help_bot import HelpBot
from gt_spector.scripts.help_nav import TRIGGER_X, TRIGGER_Y, navigate_to_help_dialog


def test_help_bot_on_start_wires_session(monkeypatch):
    class FakeGW:
        def set_locator(self, locator):
            pass

    class FakeSession:
        def __init__(self, display, source):
            self.display = display
            self.source = source

    monkeypatch.setattr("gt_spector.game_world.GameWorld", FakeGW)
    monkeypatch.setattr("gt_spector.session.Session", FakeSession)

    b = HelpBot()
    b.on_start(7)

    assert b._session is not None
    assert b._session.source == "shm://7"
    assert b._status == "starting"


def test_navigate_to_help_dialog_uses_navigator(monkeypatch):
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

    monkeypatch.setattr("gt_spector.scripts.help_nav.Navigator", FakeNavigator)
    monkeypatch.setattr("gt_spector.scripts.help_nav.time.sleep", lambda s: None)
    gw = FakeGW()
    locator = object()
    session = FakeSession()
    navigate_to_help_dialog(gw, locator, session)
    assert calls["goto"] == "alliance_menu"
    assert calls["click"] == (TRIGGER_X, TRIGGER_Y)


def test_navigate_to_help_dialog_already_there(monkeypatch):
    class FakeSession:
        def refresh(self):
            pass

        def get_pixel(self, x, y):
            return (0, 0, 0)

        def click(self, x, y):
            pass

    class FakeGW:
        def identify(self, session):
            return "help_dialog"

    monkeypatch.setattr("gt_spector.scripts.help_nav.Navigator", lambda *a, **k: None)
    status = navigate_to_help_dialog(FakeGW(), object(), FakeSession())
    assert status == "help_dialog"


def test_navigate_to_help_dialog_unknown_screen(monkeypatch):
    class FakeSession:
        def refresh(self):
            pass

        def get_pixel(self, x, y):
            return (0, 0, 0)

        def click(self, x, y):
            pass

    class FakeGW:
        def identify(self, session):
            return None

    monkeypatch.setattr("gt_spector.scripts.help_nav.Navigator", lambda *a, **k: None)
    status = navigate_to_help_dialog(FakeGW(), object(), FakeSession())
    assert status == "unknown_screen"
