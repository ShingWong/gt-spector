import tkinter.simpledialog as sd
from types import SimpleNamespace

import numpy as np
import pytest

from gt_spector import templates as T


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TEMPLATE_ROOT", tmp_path)
    yield T


def test_build_template_from_box(cfg):
    # mirror the rect capture logic: frame[y0:y1, x0:x1]
    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    frame[10:40, 20:60] = 200
    box = (20, 10, 60, 40)
    patch = frame[box[1]:box[3], box[0]:box[2]]
    t = T.Template(name="rect_btn", shape="rect", x=box[0], y=box[1],
                   w=box[2] - box[0], h=box[3] - box[1],
                   game_version=T.GAME_VERSION, score_threshold=0.75)
    T.save_template(t, patch)
    assert np.array_equal(T.get_patch("rect_btn"), patch)
    assert T.get_patch("rect_btn").shape == (30, 40, 3)


def test_circle_mask_nonzero(cfg):
    frame = np.full((40, 40, 3), 200, dtype=np.uint8)
    t = T.Template(name="circle", shape="circle", x=0, y=0, w=40, h=40,
                   game_version=T.GAME_VERSION, score_threshold=0.7)
    # center (20,20) radius 15
    import cv2
    mask = np.zeros((40, 40), dtype=np.uint8)
    cv2.circle(mask, (20, 20), 15, 1, thickness=-1)
    T.save_template(t, frame, mask)
    m = T.get_mask("circle")
    assert m is not None and m[20, 20] == 1 and m[1, 1] == 0


def test_freehand_box_spans_polygon_extent(cfg, monkeypatch):
    from viewer.gui import ViewerWindow

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[30:70, 40:80] = 200
    poly = [(40, 30), (80, 30), (80, 70), (40, 70), (42, 33)]
    win = SimpleNamespace(
        _template_mode="freehand",
        _template_poly=poly,
        _session=SimpleNamespace(frame=frame),
        _status=SimpleNamespace(config=lambda **kw: None),
        _template_mode_var=SimpleNamespace(set=lambda v: None),
        _tk=None,
    )
    monkeypatch.setattr(sd, "askstring", lambda *a, **kw: "freehand_btn")
    ViewerWindow._save_template_from_box(win, 40, 30, 42, 33, "freehand")
    t = next(x for x in T.load_templates() if x.name == "freehand_btn")
    patch = T.get_patch("freehand_btn")
    mask = T.get_mask("freehand_btn")
    assert (t.x, t.y, t.w, t.h) == (40, 30, 40, 40)
    assert patch is not None and patch.shape == (40, 40, 3)
    assert mask is not None and mask.shape == (40, 40)
    assert mask[0, 0] == 1 and mask[39, 39] == 1
