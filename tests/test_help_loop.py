import numpy as np
import pytest

from gt_spector import templates as T
from gt_spector.scripts import help_loop


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TEMPLATE_ROOT", tmp_path)
    yield T


def test_help_loop_uses_locator(cfg):
    patch = np.zeros((20, 20, 3), dtype=np.uint8); patch[:, :] = 120
    t = T.Template(name="help_btn", shape="rect", x=527, y=682, w=20, h=20,
                   game_version=T.GAME_VERSION, score_threshold=0.6)
    T.save_template(t, patch)

    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    frame[672:692, 517:537] = 120

    from gt_spector.locator import Locator
    locator = Locator()
    help_loop._locator = locator
    help_loop.HELP_TEMPLATE = "help_btn"

    class FakeSession:
        def __init__(self):
            self.clicks = 0
        @property
        def frame(self):
            return frame
        def click(self, x, y):
            self.clicks += 1

    s = FakeSession()
    # run returns True when it clicks
    assert help_loop.run(s, None) is True
    assert s.clicks == 1
