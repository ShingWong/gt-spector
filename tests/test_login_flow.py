from gt_spector.login_flow import LoginFlow, LoginStateMachine


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
    def key_press(self, key):
        self.clicks.append((key,))


class FakeLoc:
    """Finds configured templates; always finds the eye icon."""
    def __init__(self, found=(), eye=(880, 226)):
        self._found = set(found)
        self._eye = eye
    def find(self, frame, name):
        found = name in self._found or name in ("igg_login_eye2_static", "login_eye_static")
        return type("R", (), {"found": found, "cx": self._eye[0], "cy": self._eye[1]})()


def test_find_eye_polls_until_icon_renders(monkeypatch):
    """The browser's eye icon renders a moment after the form's X button;
    _find_eye must poll (condition-based wait), not check once."""
    from gt_spector import login_flow as L

    calls = {"n": 0}
    class DelayedEyeLocator:
        def find(self, frame, name):
            calls["n"] += 1
            if name != "igg_login_eye2_static":
                return type("R", (), {"found": False})()
            if calls["n"] < 3:  # not rendered yet
                return type("R", (), {"found": False})()
            return type("R", (), {"found": True, "cx": 880, "cy": 196})()

    class RefreshingSession:
        def __init__(self):
            import numpy as np
            self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
        def refresh(self):
            pass

    monkeypatch.setattr(L, "_EYE_POLL_INTERVAL", 0)
    monkeypatch.setattr(L, "_EYE_POLL_TIMEOUT", 5)
    pos = L._find_eye(DelayedEyeLocator(), RefreshingSession())
    assert pos == (880, 196)
    assert calls["n"] >= 3  # polled more than once


def test_find_eye_returns_none_after_timeout(monkeypatch):
    from gt_spector import login_flow as L

    class NeverLocator:
        def find(self, frame, name):
            return type("R", (), {"found": False})()

    class RefreshingSession:
        def __init__(self):
            import numpy as np
            self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
        def refresh(self):
            pass

    monkeypatch.setattr(L, "_EYE_POLL_INTERVAL", 0)
    monkeypatch.setattr(L, "_EYE_POLL_TIMEOUT", 2)
    assert L._find_eye(NeverLocator(), RefreshingSession()) is None


def test_login_uses_eye_derived_positions(monkeypatch):
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    calls = []
    def fake_type(prefix, display, text):
        calls.append((prefix, text))
        return True
    monkeypatch.setattr(T, "type_text", fake_type)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    result = L.login("a@b.c", "pw", s, gw, FakeLoc(eye=(880, 226)), "/p", ":13",
                     confirm=lambda m: True)
    assert result == "settings"
    # email 100 above eye, password aligned — both typed text-only
    assert ("/p", "{CtrlA}a@b.c") in calls
    assert ("/p", "{CtrlA}pw") in calls


def test_state_machine_reaches_browser_login(monkeypatch):
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    seen = []
    def confirm(msg):
        seen.append(msg)
        return True
    sm._confirm = confirm
    # Simulate walking: expired -> game_login -> browser login
    seq = ["start_expire_ok_static", "game_login_last_login_static",
           "igg_login_exit_static"]
    idx = {"i": 0}
    def detect():
        st = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return st
    sm._detect_state = detect
    sm._locator = FakeLoc(found=("start_expire_ok_static", "game_login_igg_account"))
    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    assert "start_expire_ok_static" in seen
    assert "igg_login_exit_static" in seen


def test_state_machine_reaches_in_game(monkeypatch):
    from gt_spector import login_flow as L
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(found=("region_static",)), "/p", ":13")
    result = sm.run("a@b.c", "pw")
    assert result == "settings"


def test_change_account_full_sequence(monkeypatch):
    import gt_spector.typing as T
    from gt_spector import login_flow as L

    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return True
    flow = LoginFlow(s, gw, FakeLoc(eye=(880, 226)), "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    result = flow.change_account("a@b.c", "pw")
    assert result == "change_account"
    assert seen[:2] == ["navigate", "open igg browser"]
    assert (735, 262) in s.clicks


def test_change_account_stops_on_rejected_confirm(monkeypatch):
    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return msg == "navigate"
    flow = LoginFlow(s, gw, FakeLoc(), "/p", ":13", confirm=confirm)
    result = flow.change_account("a@b.c", "pw")
    assert result == "cancelled"
    assert seen == ["navigate", "open igg browser"]
