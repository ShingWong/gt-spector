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


def _nav(gw, session):
    from gt_spector.navigator import Navigator
    return Navigator(gw, None, session)


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
    # source is "a"; identify will return "a" for the first 3 calls then "b"
    calls = {"n": 0}
    def fake_identify(session):
        calls["n"] += 1
        if calls["n"] < 3:
            return "a"
        return "b"
    gw.identify = fake_identify
    result = n._settle("a")
    assert result == "b"
    assert calls["n"] == 3


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
