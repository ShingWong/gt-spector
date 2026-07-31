import numpy as np
import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    from gt_spector import settings, overlay
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path / "bots")
    yield overlay, settings


def test_overlay_enabled_global_off(cfg):
    overlay, settings = cfg
    settings.set_overlay_global(False)
    assert overlay.overlay_enabled(10) is False


def test_overlay_enabled_per_bot_off(cfg):
    overlay, settings = cfg
    settings.set_bot_overlay("bot01", False)
    assert overlay.overlay_enabled(10) is False  # bot01 -> display 10


def test_overlay_enabled_both_on(cfg):
    overlay, settings = cfg
    assert overlay.overlay_enabled(10) is True


def test_set_overlay_enabled_global(cfg):
    overlay, settings = cfg
    overlay.set_overlay_enabled(None, False)
    assert settings.overlay_global_enabled() is False


def test_set_overlay_enabled_per_bot(cfg):
    overlay, settings = cfg
    overlay.set_overlay_enabled(10, False)
    assert settings.bot_overlay_enabled("bot01") is False


def test_toggle_global(cfg):
    overlay, settings = cfg
    assert overlay.toggle_overlay(None) is False
    assert settings.overlay_global_enabled() is False
    assert overlay.toggle_overlay(None) is True


def test_display_to_bot():
    from gt_spector.overlay import display_to_bot
    assert display_to_bot(10) == "bot01"
    assert display_to_bot(9) == "bot00"
    assert display_to_bot(2) is None


def test_draw_markers_skipped_when_disabled(cfg):
    overlay, settings = cfg
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    overlay.add_marker(10, 25, 25, "A")
    settings.set_bot_overlay("bot01", False)
    result = overlay.draw_markers(frame, 10)
    assert np.array_equal(result, frame)


def test_draw_markers_drawn_when_enabled(cfg):
    overlay, settings = cfg
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    overlay.add_marker(10, 25, 25, "A")
    settings.set_bot_overlay("bot01", True)
    result = overlay.draw_markers(frame, 10)
    assert not np.array_equal(result, frame)
