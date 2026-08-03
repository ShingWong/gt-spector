import json

import numpy as np
import pytest

from gt_spector.templates import (
    GAME_VERSION,
    Template,
    delete_template,
    get_mask,
    get_patch,
    load_templates,
    save_template,
    template_dir,
)


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    from gt_spector import templates
    monkeypatch.setattr(templates, "TEMPLATE_ROOT", tmp_path)
    yield templates


def test_save_load_roundtrip(cfg):
    patch = np.zeros((40, 40, 3), dtype=np.uint8)
    patch[:, :, 0] = 255
    t = Template(name="test_btn", shape="rect", x=100, y=50, w=40, h=40,
                 game_version=GAME_VERSION, score_threshold=0.8)
    saved = save_template(t, patch)
    assert (template_dir() / "patches" / "test_btn.png").exists()
    assert saved.name == "test_btn"
    loaded = load_templates()
    assert len(loaded) == 1 and loaded[0].name == "test_btn"
    assert np.array_equal(get_patch("test_btn"), patch)
    assert get_mask("test_btn") is None


def test_mask_roundtrip(cfg):
    patch = np.ones((10, 10, 3), dtype=np.uint8) * 200
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[:, 0:5] = 1
    t = Template(name="circ", shape="circle", x=5, y=5, w=10, h=10,
                 game_version=GAME_VERSION, score_threshold=0.7)
    save_template(t, patch, mask)
    assert np.array_equal(get_mask("circ"), mask)


def test_delete(cfg):
    patch = np.zeros((8, 8, 3), dtype=np.uint8)
    t = Template(name="gone", shape="rect", x=0, y=0, w=8, h=8,
                 game_version=GAME_VERSION, score_threshold=0.8)
    save_template(t, patch)
    delete_template("gone")
    assert load_templates() == []
    assert not (template_dir() / "patches" / "gone.png").exists()


def test_version_tag_is_current(cfg):
    assert GAME_VERSION == "Doomsday_1.59.0"


def test_corrupt_index_not_wiped(cfg):
    idx = template_dir() / "templates.json"
    idx.write_text("{ this is not json")
    patch = np.zeros((8, 8, 3), dtype=np.uint8)
    t = Template(name="new_btn", shape="rect", x=0, y=0, w=8, h=8,
                 game_version=GAME_VERSION, score_threshold=0.8)
    with pytest.raises(json.JSONDecodeError):
        save_template(t, patch)
    assert idx.read_text() == "{ this is not json"
    with pytest.raises(json.JSONDecodeError):
        delete_template("new_btn")
    assert idx.read_text() == "{ this is not json"
