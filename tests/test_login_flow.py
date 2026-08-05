from gt_spector.login_flow import LoginFlow, LoginStateMachine, login


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


def test_login_uses_eye_derived_positions(monkeypatch):
    import gt_spector.typing as T
    calls = []
    def fake_type(prefix, display, text, x, y):
        calls.append((text, x, y))
        return True
    monkeypatch.setattr(T, "type_at", fake_type)
    import gt_spector.login_flow as L
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    result = login("a@b.c", "pw", s, gw, FakeLoc(eye=(880, 226)), "/p", ":13",
                   confirm=lambda m: True)
    assert result == "settings"
    # email 100 above eye, password aligned, login 70 below
    assert ("{CtrlA}a@b.c", 365, 126) in calls
    assert ("{CtrlA}pw", 365, 226) in calls


def test_state_machine_reaches_browser_login(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    seen = []
    def confirm(msg):
        seen.append(msg)
        return True
    sm._confirm = confirm
    # Simulate walking: expired -> game_login -> browser login (terminal for SM)
    seq = ["start_expire_ok_static", "game_login_last_login_static",
           "igg_login_exit_static"]
    idx = {"i": 0}
    def detect():
        st = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return st
    sm._detect_state = detect
    # All nav templates locatable so the actions click the right spots
    sm._locator = FakeLoc(found=(
        "start_expire_ok_static", "game_login_igg_account",
    ))
    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    assert "start_expire_ok_static" in seen
    assert "igg_login_exit_static" in seen


def test_state_machine_reaches_in_game(monkeypatch):
    import gt_spector.login_flow as L
    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(found=("region_static",)), "/p", ":13")
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    result = sm.run("a@b.c", "pw")
    assert result == "settings"


def test_change_account_wires(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    s = FakeSession()
    gw = FakeGW()
    flow = LoginFlow(s, gw, FakeLoc(found=("igg_login_exit_static",)), "/p", ":13")
    result = flow.change_account("a@b.c", "pw")
    # FakeGW lands on change_account and stays there; login() returns identify
    assert result == "change_account"
    assert (735, 262) in s.clicks  # opened the browser


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
