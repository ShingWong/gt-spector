import numpy as np
import pytest

from gt_spector import templates as T


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TEMPLATE_ROOT", tmp_path)
    yield T


def test_resolve_hop_locate(cfg):
    from gt_spector.game_world import GameWorld
    from gt_spector.locator import LocateResult
    # register a template for the chat icon
    patch = np.zeros((20, 20, 3), dtype=np.uint8); patch[:, :] = 90
    t = T.Template(name="chat_icon", shape="rect", x=150, y=790, w=20, h=20,
                   game_version=T.GAME_VERSION, score_threshold=0.6)
    T.save_template(t, patch)

    class FakeLocator:
        def find(self, frame, name):
            return LocateResult(150, 800, 0.99, True)

    gw = GameWorld()
    gw.set_locator(FakeLocator())

    class FakeSession:
        def __init__(self):
            self.clicks = []
            self.frame = np.zeros((864, 1152, 3), dtype=np.uint8)
        def click(self, x, y):
            self.clicks.append((x, y))
        def refresh(self):
            pass

    # _resolve_hop is the unit boundary for the new "locate" action; the full
    # navigate() re-identifies each hop via fingerprints (tested live instead).
    gw.navigation["world_map"]["chat"] = {"action": "locate", "name": "chat_icon"}
    s = FakeSession()
    ok = gw._resolve_hop(s, "world_map", "chat")
    assert ok
    assert (150, 800) in s.clicks


def test_resolve_hop_missing_template(cfg):
    from gt_spector.game_world import GameWorld
    from gt_spector.locator import LocateResult

    class FakeLocator:
        def find(self, frame, name):
            return LocateResult(0, 0, 0.1, False)

    gw = GameWorld()
    gw.set_locator(FakeLocator())

    class FakeSession:
        def __init__(self):
            self.clicks = []
            self.frame = np.zeros((864, 1152, 3), dtype=np.uint8)
        def click(self, x, y):
            self.clicks.append((x, y))
        def refresh(self):
            pass

    gw.navigation["world_map"]["chat"] = {"action": "locate", "name": "missing_icon"}
    s = FakeSession()
    assert gw._resolve_hop(s, "world_map", "chat") is False
    assert s.clicks == []


def test_navigate_stops_on_failed_hop(cfg, monkeypatch):
    from gt_spector.game_world import GameWorld
    from gt_spector.locator import LocateResult

    class FakeLocator:
        def find(self, frame, name):
            return LocateResult(0, 0, 0.1, False)

    gw = GameWorld()
    gw.set_locator(FakeLocator())
    gw.navigation = {
        "A": {"B": {"action": "locate", "name": "missing_icon"}},
        "B": {"C": {"action": "click", "location": "c_btn"}},
    }
    gw.locations["c_btn"] = {"x": 10, "y": 20, "screens": ["B"]}
    gw._loc_index["B"] = {"c_btn": (10, 20)}
    monkeypatch.setattr(gw, "identify", lambda session: "B")
    monkeypatch.setattr("time.sleep", lambda *a: None)

    class FakeSession:
        def __init__(self):
            self.clicks = []
            self.frame = np.zeros((864, 1152, 3), dtype=np.uint8)
        def click(self, x, y):
            self.clicks.append((x, y))
        def refresh(self):
            pass

    s = FakeSession()
    assert gw.navigate(s, "C", screen="A") is False
    assert s.clicks == []
