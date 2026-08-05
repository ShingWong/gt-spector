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
        import numpy as np
        self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
    def refresh(self):
        pass
    def get_pixel(self, x, y):
        return (255, 255, 255)
    def click(self, x, y):
        self.clicks.append((x, y))


class FakeLoc:
    """Finds the eye icon; used by login() position derivation."""
    def __init__(self, eye=(880, 226), found_names=()):
        self._eye = eye
        self._found_names = set(found_names)
    def find(self, frame, name):
        found = name in self._found_names or name == "igg_login_eye2_static"
        return type("R", (), {"found": found, "cx": self._eye[0], "cy": self._eye[1]})()


def test_expired_login_flow(monkeypatch):
    import gt_spector.typing as T
    from gt_spector import login_flow as L

    s = FakeSession()
    gw = FakeGW()
    seen = []
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)

    found = {"start_expire_ok_static": True, "game_login_igg_account": True}

    class FakeLoc:
        def find(self, frame, name):
            ok = found.get(name, False) or name == "igg_login_eye2_static"
            return type("R", (), {"found": ok, "cx": 100, "cy": 200})()

    def confirm(msg):
        seen.append(msg)
        return True

    result = L.expired_login("a@b.c", "pw", s, gw, FakeLoc(), "/p", ":13", confirm=confirm)
    assert result == gw.identify(s)
    assert (100, 200) in s.clicks  # OK + IGG button located clicks


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
    flow = LoginFlow(s, gw, FakeLoc(eye=(880, 226)), "/p", ":13", confirm=confirm)
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
        (735, 262), (880, 226), (880, 226), (365, 296),
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
