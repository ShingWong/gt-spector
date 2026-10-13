import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _fast_navigation(monkeypatch):
    monkeypatch.setattr("gt_spector.navigator.MIN_SETTLE", 0.0)
    monkeypatch.setattr("gt_spector.navigator.MAX_SETTLE_TRIES", 5)
    monkeypatch.setattr("gt_spector.navigator.MAX_ESC", 3)


class FakeGW:
    def __init__(self, screens):
        self.screens = screens
        all_edges = {
            "a": {"b": {"action": "click", "location": "b_btn"}},
            "b": {},
        }
        self.navigation = {
            src: {
                dst: edge
                for dst, edge in edges.items()
                if dst in screens
            }
            for src, edges in all_edges.items()
            if src in screens
        }
        self._locator = None
    def identify(self, session):
        return self.screens.get(session.name)
    def _resolve_hop(self, session, screen, target):
        self.screens[session.name] = target
        return True


class FakeSession:
    def __init__(self, name="a"):
        self.name = name
        self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
        self.esc_count = 0
    def refresh(self):
        return self.frame
    def key_press(self, key):
        if key == "Escape":
            self.esc_count += 1


def _nav(gw, session, trace=None):
    from gt_spector.navigator import Navigator
    return Navigator(gw, None, session, trace=trace)


def test_route_to_finds_bfs_path():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)
    assert n.route_to("b") == ["a", "b"]


def test_route_to_no_path():
    gw = FakeGW({"a": "a"})
    s = FakeSession("a")
    n = _nav(gw, s)
    assert n.route_to("b") is None


def test_route_to_already_at_target():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("b")
    n = _nav(gw, s)
    assert n.route_to("b", screen="b") == ["b"]


def test_settle_waits_until_screen_changes():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)
    # source is "a"; identify returns "a" for the first 3 calls then "b"
    # (which must hold for STABLE_TRIES consecutive polls to be accepted).
    calls = {"n": 0}
    def fake_identify(session):
        calls["n"] += 1
        if calls["n"] < 3:
            return "a"
        return "b"
    gw.identify = fake_identify
    result = n._settle("a")
    assert result == "b"
    assert calls["n"] == 4  # 2 x "a" (reset) + "b" (candidate) + "b" (stable)


def test_settle_ignores_single_flash_of_wrong_screen():
    """A one-frame flash of another screen (e.g. avatar_menu opening briefly
    matching world_map via the shared avatar template) must not be returned;
    the stable screen that follows is."""
    gw = FakeGW({"a": "a", "b": "b", "c": "c"})
    s = FakeSession("a")
    n = _nav(gw, s)
    seq = iter(["b", "c", "c"])
    gw.identify = lambda session: next(seq)
    assert n._settle("a") == "c"


def test_settle_returns_none_after_max_tries():
    gw = FakeGW({"a": "a"})
    s = FakeSession("a")
    n = _nav(gw, s)
    gw.identify = lambda session: "a"  # never changes
    assert n._settle("a") is None


def test_goto_success():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)
    result = n.goto("b")
    assert result == "b"
    assert gw.screens[s.name] == "b"


def test_goto_recomputes_after_different_landing():
    gw = FakeGW({"a": "a", "b": "b", "c": "c"})
    gw.navigation["a"] = {"b": {"action": "click", "location": "b_btn"}}
    gw.navigation["b"] = {"c": {"action": "click", "location": "c_btn"}}
    s = FakeSession("a")
    n = _nav(gw, s)
    # The first hop from a -> b always lands on "c" instead.
    orig_resolve = gw._resolve_hop
    hop_count = {"n": 0}
    def resolve(session, screen, target):
        hop_count["n"] += 1
        if hop_count["n"] == 1:
            session.name = "c"
            return True
        return orig_resolve(session, screen, target)
    gw._resolve_hop = resolve
    result = n.goto("c")
    assert result == "c"
    assert gw.screens[s.name] == "c"


def test_goto_recomputes_after_landing_intermediate():
    gw = FakeGW({"a": "a", "b": "b", "c": "c", "d": "d"})
    gw.navigation["a"] = {"b": {"action": "click", "location": "b_btn"}}
    gw.navigation["b"] = {"c": {"action": "click", "location": "c_btn"}}
    gw.navigation["d"] = {"c": {"action": "click", "location": "c_btn"}}
    s = FakeSession("a")
    n = _nav(gw, s)

    def resolve(session, screen, target):
        session.name = "c" if target == "c" else "d"
        return True
    gw._resolve_hop = resolve

    route_calls = {"n": 0}
    orig_route_to = n.route_to
    def route_to(target, screen=None):
        route_calls["n"] += 1
        return orig_route_to(target, screen)
    n.route_to = route_to

    result = n.goto("c")
    assert result == "c"
    assert gw.screens[s.name] == "c"
    assert route_calls["n"] > 1


def test_goto_returns_stuck_screen_on_hop_failure():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)
    gw._resolve_hop = lambda session, screen, target: False
    assert n.goto("b") == "a"


def test_goto_returns_stuck_screen_on_esc_exhaustion():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)

    def resolve(session, screen, target):
        session.name = None
        return True
    gw._resolve_hop = resolve
    gw.identify = lambda session: gw.screens.get(session.name)

    result = n.goto("b")
    assert result is not None
    assert result == "a"


def test_goto_esc_on_unknown_then_succeed():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    n = _nav(gw, s)
    # On first hop, land on unknown (identify returns None). ESC -> b.
    resolve_called = {"n": 0}
    orig_resolve = gw._resolve_hop
    def resolve(session, screen, target):
        resolve_called["n"] += 1
        if resolve_called["n"] == 1:
            session.name = None  # unknown
            return True
        return orig_resolve(session, screen, target)
    gw._resolve_hop = resolve
    # After ESC, identify should return "b" (recovery); before ESC it is unknown.
    orig_identify = gw.identify
    def identify(session):
        if session.name is None:
            if session.esc_count == 0:
                return None
            return "b"
        return orig_identify(session)
    gw.identify = identify
    result = n.goto("b")
    assert result == "b"
    assert s.esc_count >= 1


def test_goto_no_path():
    gw = FakeGW({"a": "a"})
    s = FakeSession("a")
    n = _nav(gw, s)
    assert n.goto("b") is None


def test_goto_already_at_target():
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("b")
    n = _nav(gw, s)
    assert n.goto("b") == "b"
    assert s.esc_count == 0


def test_goto_esc_advance_to_unknown_then_recompute():
    import numpy as np

    from gt_spector.navigator import Navigator

    # start_norah: advance:esc lands on event screen (unknown to route),
    # which has a route onward to shelter_view.
    landing = {"event": "event"}

    class EAGW:
        def __init__(self):
            self.screens = {
                "start_norah": {"advance": "esc"},
                "event": {"advance": ""},
                "shelter_view": {"advance": ""},
            }
            self.navigation = {
                "event": {"shelter_view": {"action": "click", "location": "x"}},
            }
            self._locator = None

        def identify(self, session):
            # identify returns the screen NAME (the key), matching GameWorld
            if session.name in self.screens:
                return session.name
            return None

        def _resolve_hop(self, session, screen, target):
            session.name = target
            return True

    class EASession:
        def __init__(self):
            self.name = "start_norah"
            self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
            self.esc_count = 0

        def refresh(self):
            return self.frame

        def key_press(self, key):
            if key == "Escape":
                self.esc_count += 1
                # ESC from start_norah lands on the unknown event screen
                self.name = landing["event"]

    gw = EAGW()
    s = EASession()
    n = Navigator(gw, None, s)
    result = n.goto("shelter_view")
    assert result == "shelter_view"
    assert s.esc_count == 1


def test_goto_exits_unknown_back_button_screen_via_popups(monkeypatch):
    """goto from unknown_screen_with_back_button must exit via exit_popups
    (back-button click) and re-identify, not return None without recovery."""
    from gt_spector import navigator as navmod
    from gt_spector.navigator import Navigator
    monkeypatch.setattr(navmod.time, "sleep", lambda *a, **k: None)

    class PBGW:
        def __init__(self):
            self.screens = {"a": "a", "b": "b"}
            self.navigation = {"a": {"b": {"action": "click", "location": "b_btn"}}}
            self._locator = None

        def identify(self, session):
            return session.name

        def _resolve_hop(self, session, screen, target):
            session.name = target
            return True

    class PBSession:
        def __init__(self):
            self.name = "unknown_screen_with_back_button"
            self.frame = np.zeros((50, 50, 3), dtype=np.uint8)
            self.clicks = []
            self.back_clicked = False

        def refresh(self):
            # After the back-button exit, the popup clears to the shelter view.
            if self.name == "unknown_screen_with_back_button" and self.back_clicked:
                self.name = "a"

        def click(self, x, y):
            self.clicks.append((x, y))
            self.back_clicked = True

        def key_press(self, key):
            pass

    class FakeLoc:
        def find(self, frame, name):
            return type("R", (), {"found": True, "cx": 10, "cy": 20})()

    gw = PBGW()
    s = PBSession()
    n = Navigator(gw, FakeLoc(), s)
    result = n.goto("b")
    assert result == "b"
    assert (10, 20) in s.clicks


def test_goto_trace_reports_hops(monkeypatch):
    # reuse FakeGW/FakeSession/_nav from the existing file
    from gt_spector import navigator as navmod
    monkeypatch.setattr(navmod, "MIN_SETTLE", 0.0)
    monkeypatch.setattr(navmod, "MAX_SETTLE_TRIES", 2)
    monkeypatch.setattr(navmod, "MAX_ESC", 1)
    gw = FakeGW({"a": "a", "b": "b"})
    s = FakeSession("a")
    msgs = []
    n = _nav(gw, s, trace=msgs.append)
    n.goto("b")
    assert msgs, "expected at least one trace message"
    assert any("hop" in m.lower() for m in msgs)
