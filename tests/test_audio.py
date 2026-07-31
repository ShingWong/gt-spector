import subprocess

import pytest


@pytest.fixture()
def fake_pactl(monkeypatch):
    """Replace subprocess.run so audio.py never touches real pactl."""
    calls = []

    def fake_run(cmd, capture_output=False, text=False, timeout=5, check=False):
        calls.append(cmd)
        out = ""
        if cmd[:2] == ["pactl", "list"]:
            out = (
                "Sink Input #7400\n"
                "\tapplication.process.id = \"33425\"\n"
                "Sink Input #7405\n"
                "\tapplication.process.id = \"33425\"\n"
                "Sink Input #9999\n"
                "\tapplication.process.id = \"12345\"\n"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_get_sink_inputs(fake_pactl):
    from gt_spector import audio
    assert audio.get_sink_inputs(33425) == [7400, 7405]
    assert audio.get_sink_inputs(12345) == [9999]
    assert audio.get_sink_inputs(1) == []


def test_set_muted(fake_pactl):
    from gt_spector import audio
    audio.set_muted(33425, True)
    assert ["pactl", "set-sink-input-mute", "7400", "1"] in fake_pactl
    assert ["pactl", "set-sink-input-mute", "7405", "1"] in fake_pactl
    audio.set_muted(33425, False)
    assert ["pactl", "set-sink-input-mute", "7400", "0"] in fake_pactl


def test_set_muted_no_streams_is_noop(fake_pactl):
    from gt_spector import audio
    audio.set_muted(1, True)  # no matching sink-inputs
    assert fake_pactl == [["pactl", "list", "sink-inputs"]]  # nothing beyond the list call


def test_is_muted(fake_pactl):
    from gt_spector import audio
    # fake output has no Muted: lines -> is_muted returns None
    assert audio.is_muted(33425) is None
