from gt_spector.login_flow import IN_GAME_TEMPLATES, LoginFlow, LoginStateMachine


def test_in_game_templates_exist_in_store():
    """Every in-game detection template must be a registered template."""
    from gt_spector import templates as _t

    available = {t.name for t in _t.load_templates()}
    assert set(IN_GAME_TEMPLATES) <= available


class FakeGW:
    def __init__(self):
        self.screens = {}
        self.navigation = {
            "settings": {"change_account": {"action": "click"}},
            "shelter_view": {"change_account": {"action": "locate", "name": "x"}},
        }
        self._locator = None
        self._screen = "settings"
    def identify(self, session):
        return self._screen
    def set_locator(self, loc):
        pass
    def _resolve_hop(self, session, screen, target):
        self._screen = target
        return True
    def loc(self, screen, name):
        return (575, 654) if name == "glory_league_go" else None


class FakeSession:
    def __init__(self):
        self.clicks = []
        self.display = ":13"
        self.attaches = []
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
    def attach(self, display, source=""):
        self.attaches.append((display, source))


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


def test_state_machine_reattaches_after_expired_ok(monkeypatch):
    """Dismissing the expired dialog restarts the browser (SHM detach); the
    state machine must reattach the session before reading the next screen."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
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
    # The OK click must be followed by a reattach to the same display.
    assert s.attaches == [(":13", "shm://13")]


def test_state_machine_use_another_account_before_login(monkeypatch):
    """A remembered session shows the 'currently logged in' page; the flow
    must click Use-another-account before reaching the login form."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    seq = ["login_current_static", "igg_login_exit_static"]
    idx = {"i": 0}
    def detect():
        st = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return st
    sm._detect_state = detect

    class UseAnotherLoc(FakeLoc):
        def find(self, frame, name):
            r = super().find(frame, name)
            if name == "login_use_another_static":
                return type("R", (), {"found": r.found, "cx": 518, "cy": 369})()
            return r

    sm._locator = UseAnotherLoc(found=("login_current_static", "login_use_another_static"))
    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    # The Use-another-account button (518,369) must be clicked before login.
    assert (518, 369) in s.clicks


def test_state_machine_polls_game_login_igg_button(monkeypatch):
    """The IGG account button on game_login renders late; _locate_poll must
    retry until it appears instead of erroring on the first frame."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    # Button missing on the first locate, present on the second.
    calls = {"n": 0}
    def flaky(self, frame, name):
        if name == "game_login_igg_account":
            calls["n"] += 1
            if calls["n"] == 1:
                return type("R", (), {"found": False, "cx": 0, "cy": 0})()
            return type("R", (), {"found": True, "cx": 635, "cy": 585})()
        found = name in ("igg_login_eye2_static", "login_eye_static")
        return type("R", (), {"found": found, "cx": 880, "cy": 226})()
    sm._locator = type("FL", (), {"find": flaky})()
    r = sm._locate_poll("game_login_igg_account", timeout=0.5)
    assert r is not None and r.cx == 635
    assert calls["n"] >= 2


def test_state_machine_clicks_glory_league_go(monkeypatch):
    """After OK+reattach the game may land on the Glory League splash; the
    flow must click GO (575,654) to reach the browser current-account page."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    seq = ["glory_league_event", "login_current_static", "igg_login_exit_static"]
    idx = {"i": 0}
    def detect():
        st = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return st
    sm._detect_state = detect
    sm._locator = FakeLoc(found=("login_current_static", "login_use_another_static"))
    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    # GO button (575,654) must be clicked to leave the splash.
    assert (575, 654) in s.clicks


def test_state_machine_reaches_in_game(monkeypatch):
    from gt_spector import login_flow as L
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(found=("region_static",)), "/p", ":13")
    result = sm.run("a@b.c", "pw")
    assert result == "settings"


def test_state_machine_force_account_relogs_from_in_game(monkeypatch):
    """With force_account, reaching in_game (an auto-logged-in session, possibly
    the master account) must NOT be accepted — the flow re-logs-in the intended
    account via the browser."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()

    # FakeGW.identify returns "in_game" (via region_static) then "change_account"
    # after nav.goto; navigate through to the browser login form.
    class RelogGW(FakeGW):
        def __init__(self):
            super().__init__()
            self._screen = "shelter_view"
        def identify(self, session):
            return self._screen
        def _resolve_hop(self, session, screen, target):
            self._screen = target
            return True

    gw = RelogGW()
    sm = LoginStateMachine(s, gw, FakeLoc(found=("region_static",)), "/p", ":13",
                           confirm=lambda m: True)
    sm.run("a@b.c", "pw", force_account=True)
    # The flow must NOT accept the auto-logged-in session; it re-logs-in via
    # the browser, so the IGG account button must be clicked.
    assert (735, 262) in s.clicks


def test_state_machine_esc_and_login_after_another_login_disconnect(monkeypatch):
    """Another-device-logged-in popup -> ESC, then the login flow continues."""
    import gt_spector.typing as T
    from gt_spector import login_flow as L
    monkeypatch.setattr(T, "type_text", lambda *a, **k: True)
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)

    s = FakeSession()
    gw = FakeGW()
    sm = LoginStateMachine(s, gw, FakeLoc(), "/p", ":13", confirm=lambda m: True)
    seq = ["another_login_disconnect_detect_static", "game_login_last_login_static",
           "igg_login_exit_static"]
    idx = {"i": 0}
    def detect():
        st = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return st
    sm._detect_state = detect
    sm._locator = FakeLoc(found=("another_login_disconnect_detect_static",
                                 "game_login_igg_account"))
    result = sm.run("a@b.c", "pw")
    assert result == "settings"
    # The popup must be dismissed with ESC before proceeding.
    assert ("Escape",) in s.clicks


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
