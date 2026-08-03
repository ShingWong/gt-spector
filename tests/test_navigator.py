import numpy as np


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
    n.MIN_SETTLE = 0.0  # don't actually sleep in tests
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
    n.MIN_SETTLE = 0.0
    gw.identify = lambda session: "a"  # never changes
    assert n._settle("a") is None
