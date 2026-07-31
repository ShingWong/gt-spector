import pytest


@pytest.fixture()
def logs(tmp_path, monkeypatch):
    from gt_spector import logs, settings
    monkeypatch.setattr(logs, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path.parent)
    monkeypatch.setattr(settings, "GLOBAL_PATH", tmp_path.parent / "settings.json")
    monkeypatch.setattr(settings, "BOTS_DIR", tmp_path.parent / "bots")
    return logs, settings


def test_log_system_writes_file(logs):
    logs_module, _ = logs
    logs_module.log_system("hello")
    content = (logs_module.LOGS_DIR / "system.log").read_text()
    assert "hello" in content


def test_log_bot_writes_per_bot_file(logs):
    logs_module, _ = logs
    logs_module.log_bot("bot01", "crash")
    content = (logs_module.LOGS_DIR / "bot01.log").read_text()
    assert "crash" in content


def test_rotation_keeps_two_copies(logs, monkeypatch):
    logs_module, settings = logs
    monkeypatch.setattr(settings, "log_max_bytes", lambda: 100)
    # Write enough to exceed 100 bytes twice
    for _ in range(5):
        logs_module.log_bot("bot01", "x" * 60)
    files = sorted(p.name for p in logs_module.LOGS_DIR.iterdir())
    assert "bot01.log" in files
    assert "bot01.log.1" in files


def test_clear_all_logs(logs):
    logs_module, _ = logs
    logs_module.log_system("s")
    logs_module.log_bot("bot01", "b")
    logs_module.clear_all_logs()
    assert (logs_module.LOGS_DIR / "system.log").exists() is False
    assert (logs_module.LOGS_DIR / "bot01.log").exists() is False
