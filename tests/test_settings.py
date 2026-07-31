import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    from gt_spector import settings
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path / "bots")
    return settings


def test_defaults_when_missing(cfg):
    assert cfg.get_global() == {}
    assert cfg.bot_overlay_enabled("bot01") is True
    assert cfg.sound_mode() == "viewer"
    assert cfg.bot_sound_muted("bot01") is False
    assert cfg.log_max_bytes() == 512 * 1024


def test_global_roundtrip(cfg):
    cfg.set_global(overlay_global_enabled=False, sound_mode="all_off")
    assert cfg.overlay_global_enabled() is False
    assert cfg.sound_mode() == "all_off"


def test_bot_roundtrip(cfg):
    cfg.set_bot("bot01", overlay_enabled=False, sound_muted=True)
    assert cfg.bot_overlay_enabled("bot01") is False
    assert cfg.bot_sound_muted("bot01") is True
    # bot02 untouched
    assert cfg.bot_overlay_enabled("bot02") is True


def test_bot_files_are_isolated(cfg):
    cfg.set_bot("bot01", overlay_enabled=False)
    cfg.set_bot("bot02", overlay_enabled=True)
    assert (cfg.BOTS_DIR / "bot01.json").exists()
    assert (cfg.BOTS_DIR / "bot02.json").exists()


def test_log_size_roundtrip(cfg):
    cfg.set_log_max_bytes(1024 * 1024)
    assert cfg.log_max_bytes() == 1024 * 1024


def test_corrupt_global_file_falls_back(cfg, monkeypatch):
    cfg.GLOBAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.GLOBAL_PATH.write_text("{ not json")
    assert cfg.overlay_global_enabled() is True
    assert cfg.sound_mode() == "viewer"
