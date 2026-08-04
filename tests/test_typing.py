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


def test_click_at_uses_empty_text(monkeypatch):
    from gt_spector import typing as T

    calls = []
    def fake_run(cmd, env=None, **kw):
        calls.append(cmd)
        return FakeResult()
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert T.click_at("/p", ":13", 700, 560) is True
    assert calls[0][-3] == ""  # empty text arg


def test_type_at_reports_failure(monkeypatch):
    from gt_spector import typing as T

    class FailResult:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FailResult())
    assert T.type_at("/p", ":13", "x", 1, 2) is False
