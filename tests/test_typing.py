import os
import subprocess


class FakeResult:
    returncode = 0


def test_type_at_invokes_sendtext(monkeypatch):
    from gt_spector import typing as T

    calls = []
    def fake_run(cmd, env=None, **kw):
        calls.append((cmd, env))
        return FakeResult()
    monkeypatch.setattr(subprocess, "run", fake_run)

    ok = T.type_at("/home/swong/dls/wineprefix_bots/bot04", ":13",
                   "{CtrlA}sr02-07@mx1.us", 365, 156)
    assert ok is True
    assert len(calls) == 1
    cmd, env = calls[0]
    assert cmd[0] == "/opt/wine-proton/bin/wine"
    assert cmd[1].endswith("sendtext.exe")
    assert "{CtrlA}sr02-07@mx1.us" in cmd
    assert "365" in cmd and "156" in cmd
    assert env["WINEPREFIX"] == "/home/swong/dls/wineprefix_bots/bot04"
    assert env["DISPLAY"] == ":13"
    assert env["HOME"] == os.environ["HOME"]


def test_type_at_reports_failure(monkeypatch):
    from gt_spector import typing as T

    class FailResult:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FailResult())
    assert T.type_at("/p", ":13", "x", 1, 2) is False


def test_type_at_returns_false_on_exceptions(monkeypatch):
    from gt_spector import typing as T

    def boom(cmd, env=None, **kw):
        raise subprocess.TimeoutExpired(cmd, timeout=30)
    monkeypatch.setattr(subprocess, "run", boom)
    assert T.type_at("/p", ":13", "x", 1, 2) is False

    def boom2(cmd, env=None, **kw):
        raise OSError("no display")
    monkeypatch.setattr(subprocess, "run", boom2)
    assert T.type_at("/p", ":13", "x", 1, 2) is False
