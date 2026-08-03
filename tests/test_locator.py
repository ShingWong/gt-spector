import numpy as np
import pytest

from gt_spector.locator import LocateResult


def _noise_frame(seed=0):
    return np.random.default_rng(seed).integers(0, 255, (864, 1152, 3), dtype=np.uint8)


def _stamp(frame, px, py, size, value=200):
    block = frame[py:py + size, px:px + size]
    block[:] = value
    block[:, :, 0] = np.linspace(0, 255, size, dtype=np.uint8)[:, None]
    return frame


def _frame_with_patch(px=50, py=100, size=24, value=200):
    return _stamp(_noise_frame(), px, py, size, value)


def _register(locator, name, px, py, size, shape="rect", threshold=0.6):
    patch = _frame_with_patch(px, py, size)[py:py + size, px:px + size]
    from gt_spector import templates as T
    t = T.Template(name=name, shape=shape, x=px, y=py, w=size, h=size,
                   game_version=T.GAME_VERSION, score_threshold=threshold)
    T.save_template(t, patch)
    return t


@pytest.fixture()
def loc(tmp_path, monkeypatch):
    from gt_spector import locator, templates
    monkeypatch.setattr(templates, "TEMPLATE_ROOT", tmp_path)
    yield locator.Locator(), templates


def test_find_exact_center(loc):
    locator, _ = loc
    _register(locator, "t", 50, 100, 24)
    frame = _frame_with_patch()
    r = locator.find(frame, "t")
    assert r.found
    # center of 24x24 patch placed at (50,100) is (62, 112)
    assert r.cx == 62 and r.cy == 112
    assert r.score > 0.99


def test_find_not_present(loc):
    locator, _ = loc
    _register(locator, "t", 50, 100, 24)
    frame = _noise_frame()
    r = locator.find(frame, "t")
    assert not r.found


def test_find_all(loc):
    locator, _ = loc
    _register(locator, "a", 50, 100, 24)
    _register(locator, "b", 400, 300, 16)
    frame = _stamp(_frame_with_patch(50, 100, 24), 400, 300, 16)
    res = locator.find_all(frame, ["a", "b"])
    assert res["a"].found and res["b"].found
    assert res["a"].cx == 62 and res["b"].cx == 408


def test_vlm_fallback_called_on_low_score(loc):
    locator, _ = loc
    _register(locator, "t", 50, 100, 24, threshold=0.999)
    called = []

    def fb(frame, name, score):
        called.append((name, score))
        return LocateResult(cx=10, cy=20, score=score, found=True)

    locator.set_vlm_fallback(fb)
    frame = _frame_with_patch()
    frame[100:124, 50:74] ^= 60
    r = locator.find(frame, "t")
    assert r.found and r.cx == 10
    assert called and called[0][0] == "t"
