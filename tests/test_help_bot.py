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


def test_navigate_to_help_dialog_clicks_trigger_when_not_red(monkeypatch):
    """The help dialog opens regardless of the trigger color (no request)."""
    calls = {}

    class FakeSession:
        def refresh(self):
            calls["refresh"] = True

        def get_pixel(self, x, y):
            return (47, 44, 44)  # dark, not red

        def click(self, x, y):
            calls["click"] = (x, y)

    class FakeGW:
        def identify(self, session):
            return "alliance_menu"

    monkeypatch.setattr("gt_spector.scripts.help_nav.Navigator", lambda *a, **k: None)
    monkeypatch.setattr("gt_spector.scripts.help_nav.time.sleep", lambda s: None)
    navigate_to_help_dialog(FakeGW(), object(), FakeSession())
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


class _TickSession:
    def __init__(self, screen="help_dialog", pixel=(71, 72, 71), keys=()):
        self.screen = screen
        self.pixel = pixel
        self.keys = list(keys)
        self.clicks = []
        self.refreshes = 0
        self.frame = None

    def refresh(self):
        self.refreshes += 1

    def get_pixel(self, x, y):
        return self.pixel

    def click(self, x, y):
        self.clicks.append((x, y))

    def key_press(self, key):
        self.keys.append(key)


class _TickGW:
    def __init__(self, screen="help_dialog"):
        self.screen = screen

    def identify(self, session):
        return session.screen

    def set_locator(self, locator):
        pass


def test_help_bot_tick_dismisses_stuck_popup(monkeypatch):
    """Neither-gold-nor-dim pixel -> re-navigate to the dialog."""
    b = HelpBot()
    b._session = _TickSession(pixel=(78, 57, 17))
    b._gw = _TickGW()
    b._loop = type("L", (), {"run": lambda self, s: "stuck", "help_clicks": 0})()
    recovered = []
    monkeypatch.setattr(b, "_navigate_to_help_dialog",
                        lambda: recovered.append(True) or setattr(b, "_status", "recovered"))
    b._tick()
    assert recovered == [True]
    assert b._status == "recovered"


def test_help_bot_tick_dismisses_reaping_screen(monkeypatch):
    """resource-reaping screen-saver popup detected -> exit_popups + re-navigate."""
    b = HelpBot()
    b._session = _TickSession(screen="resouce_reaping", pixel=(71, 72, 71))
    b._gw = _TickGW()
    b._loop = type("L", (), {"run": lambda self, s: "idle", "help_clicks": 0})()
    exited = []
    monkeypatch.setattr(b, "_exit_popups", lambda screen: exited.append(True) or True)
    monkeypatch.setattr(b, "_navigate_to_help_dialog",
                        lambda: setattr(b, "_status", "re-navigated"))
    b._tick()
    assert exited == [True]


def test_help_bot_tick_clicks_gold_and_updates_status(monkeypatch):
    b = HelpBot()
    b._session = _TickSession(pixel=(223, 170, 67))
    b._gw = _TickGW()
    b._locator = type("L", (), {
        "find": lambda self, frame, name: type("R", (), {"found": False, "score": 0.0})()})()
    loop = type("L", (), {"help_clicks": 3, "run": lambda self, s: "clicked"})()
    b._loop = loop
    b._tick()
    assert b._status == "clicked_3"


def test_help_bot_tick_exits_popup_and_navigates(monkeypatch):
    from gt_spector.scripts.help_bot import HelpBot

    b = HelpBot()
    b._session = _TickSession(screen="road_to_conquest_menu", pixel=(71, 72, 71))
    b._gw = _TickGW()
    b._loop = type("L", (), {"run": lambda self, s: "idle", "help_clicks": 0})()
    exited = []

    def fake_exit_popups(screen):
        exited.append(True)
        b._navigate_to_help_dialog()
        return True

    monkeypatch.setattr(b, "_exit_popups", fake_exit_popups)
    monkeypatch.setattr(b, "_navigate_to_help_dialog",
                        lambda: setattr(b, "_status", "re-navigated"))
    b._tick()
    assert exited == [True]
    assert b._status == "re-navigated"


def test_navigate_to_help_dialog_exits_popup(monkeypatch):
    calls = {}

    class FakeSession:
        def refresh(self):
            calls["refresh"] = True

        def get_pixel(self, x, y):
            return (47, 44, 44)

        def click(self, x, y):
            calls["click"] = (x, y)

    class FakeGW:
        def identify(self, session):
            return "road_to_conquest_menu"

    class FakeNavigator:
        def __init__(self, gw, locator, session):
            calls["ctor"] = True

        def goto(self, target):
            return target

    monkeypatch.setattr("gt_spector.scripts.help_nav.Navigator", FakeNavigator)
    monkeypatch.setattr(
        "gt_spector.scripts.help_nav.exit_popups",
        lambda session, locator, screen: calls.setdefault("exit", []).append(screen) or True,
    )
    monkeypatch.setattr("gt_spector.scripts.help_nav.time.sleep", lambda s: None)
    navigate_to_help_dialog(FakeGW(), object(), FakeSession())
    assert calls["exit"] == ["road_to_conquest_menu"]
