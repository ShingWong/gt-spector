import numpy as np
from PIL import Image


def test_wait_for_color(tmp_path):
    from gt_spector.triggers import Triggers
    from gt_spector.screen import Screen
    img = Image.new("RGB", (100, 100), color=(50, 100, 150))
    p = str(tmp_path / "test.png")
    img.save(p)
    sc = Screen(p)
    class FakeSession:
        frame = sc.frame
        refresh = sc.refresh
        get_pixel = sc.get_pixel
    t = Triggers(FakeSession())
    ok, frame = t.wait_for_color(50, 50, (40, 90, 140), (60, 110, 160), timeout=1)
    assert ok
    ok, frame = t.wait_for_color(50, 50, (0, 0, 0), (10, 10, 10), timeout=0.5)
    assert not ok


def test_wait_for_change(tmp_path):
    from gt_spector.triggers import Triggers
    from PIL import Image
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    p = str(tmp_path / "test2.png")
    img.save(p)
    from gt_spector.screen import Screen
    sc = Screen(p)
    called = [0]
    class FakeSession:
        frame = sc.frame
        def refresh(self):
            called[0] += 1
        get_pixel = sc.get_pixel
    t = Triggers(FakeSession())
    ok, frame = t.wait_for_change(timeout=0.5)
    assert not ok  # No change in static file
