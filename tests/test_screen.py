import numpy as np
from PIL import Image


def test_get_pixel(tmp_path):
    from gt_spector.screen import Screen
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    p = str(tmp_path / "pixel.png")
    img.save(p)
    sc = Screen(p)
    pixel = sc.get_pixel(25, 25)
    assert pixel == (10, 20, 30)


def test_capture_area(tmp_path):
    from gt_spector.screen import Screen
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    p = str(tmp_path / "area.png")
    img.save(p)
    sc = Screen(p)
    area = sc.capture_area(10, 10, 30, 30)
    assert area.shape == (20, 20, 3)
    assert tuple(area[0, 0]) == (255, 0, 0)
