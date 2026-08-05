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
    """Returns found results for configured templates; eye found always."""
    def __init__(self, found=(), eye=(880, 226)):
        self._found = set(found)
        self._eye = eye
    def find(self, frame, name):
        found = name in self._found or name in ("igg_login_eye2_static", "login_eye_static")
        return type("R", (), {"found": found, "cx": self._eye[0], "cy": self._eye[1]})()


def test_state_machine_reaches_in_game(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    loc = FakeLoc(found=("igg_login_exit_static",))
    sm = LoginStateMachine(s, gw, loc, "/p", ":13", confirm=lambda m: True)
    calls = {"n": 0}
    def detect():
        calls["n"] += 1
        return "igg_login_exit_static" if calls["n"] == 1 else "in_game"
    monkeypatch.setattr(sm, "_detect_state", detect)
    monkeypatch.setattr(sm, "_in_game", lambda: calls["n"] > 1)

    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    assert (880, 226) in s.clicks  # eye reveal/hide


def test_expired_login_flow(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T

    s = FakeSession()
    gw = FakeGW()
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)

    states = ["start_expire_ok_static", "game_login_last_login_static",
              "igg_login_exit_static", "in_game"]
    loc = FakeLoc(found=tuple(states) + ("game_login_igg_account",))
    sm = LoginStateMachine(s, gw, loc, "/p", ":13", confirm=lambda m: True)
    idx = {"i": 0}
    def detect():
        st = states[min(idx["i"], len(states) - 1)]
        idx["i"] += 1
        return st
    monkeypatch.setattr(sm, "_detect_state", detect)
    monkeypatch.setattr(sm, "_in_game", lambda: idx["i"] > 3)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    result = sm.run("a@b.c", "pw")
    assert result == "settings"


def test_change_account_full_sequence(monkeypatch):
    import gt_spector.login_flow as L
    import gt_spector.typing as T

    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return True
    flow = LoginFlow(s, gw, FakeLoc(found=("igg_login_exit_static",)), "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(flow._gw, "identify", lambda session: "settings")

    result = flow.change_account("a@b.c", "pw")
    assert result in ("settings", "error")


def test_change_account_stops_on_rejected_confirm(monkeypatch):
    import gt_spector.typing as T
    s = FakeSession()
    gw = FakeGW()
    seen = []
    def confirm(msg):
        seen.append(msg)
        return msg == "navigate"
    flow = LoginFlow(s, gw, FakeLoc(), "/p", ":13", confirm=confirm)
    monkeypatch.setattr(T, "type_at", lambda *a, **k: True)
    result = flow.change_account("a@b.c", "pw")
    assert result == "cancelled"
