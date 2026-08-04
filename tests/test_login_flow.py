from gt_spector.login_flow import LoginFlow


class FakeGW:
    def __init__(self):
        self.screens = {}
        self.navigation = {"settings": {"change_account": {"action": "click"}}}
        self._locator = None
        self._screen = "settings"
    def identify(self, session):
        return self._screen
    def set_locator(self, loc):
        pass
    def _resolve_hop(self, session, screen, target):
        self._screen = target
        return True


class FakeSession:
    def __init__(self):
        self.clicks = []
        self.display = ":13"
    def refresh(self):
        pass
    def get_pixel(self, x, y):
        return (255, 255, 255)
    def click(self, x, y):
        self.clicks.append((x, y))


def test_window_click_uses_client_coords():
    s = FakeSession()
    gw = FakeGW()
    flow = LoginFlow(s, gw, None, "/p", ":13", confirm=lambda m: True)
    flow._window_click(100, 200)
    assert s.clicks == [(100, 200)]


def test_change_account_full_sequence(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T

    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return True
    flow = LoginFlow(s, gw, None, "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    result = flow.change_account("a@b.c", "pw")
    assert result == "change_account"
    assert seen == [
        "navigate", "open igg browser", "enter email", "enter password",
        "reveal password", "hide password", "submit login",
        "continue after login", "select id", "confirm ok",
    ]
    assert s.clicks == [
        (735, 262), (885, 195), (885, 195), (462, 258),
        (500, 300), (350, 165), (700, 560),
    ]


def test_change_account_stops_on_rejected_confirm(monkeypatch):
    import gt_spector.typing as T
    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return msg == "navigate"  # only first step accepted
    flow = LoginFlow(s, gw, None, "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    result = flow.change_account("a@b.c", "pw")
    assert result == "cancelled"
    assert seen == ["navigate", "open igg browser"]
