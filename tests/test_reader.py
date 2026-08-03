import numpy as np
import pytest

from gt_spector import templates as T


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TEMPLATE_ROOT", tmp_path)
    yield T


def _patch_digit(value: int):
    patch = np.full((30, 30, 3), 200, dtype=np.uint8)
    # encode value as the corner color so a fake VLM can "read" it
    patch[0, 0] = [value, 0, 0]
    return patch


def _register(cfg, name, patch, shape="rect", threshold=0.6, reader="vlm"):
    t = T.Template(name=name, shape=shape, x=0, y=0, w=patch.shape[1],
                   h=patch.shape[0], game_version=T.GAME_VERSION,
                   score_threshold=threshold, reader=reader)
    T.save_template(t, patch)
    return t


def test_analyze_crop_runs(monkeypatch):
    from gt_spector import vlm

    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    calls = {}

    def fake_analyze(frame, prompt=None, max_tokens=500, temperature=0):
        calls["shape"] = frame.shape
        return {"choices": [{"message": {"content": "42"}}]}

    monkeypatch.setattr(vlm, "analyze_frame", fake_analyze)
    text = vlm.analyze_crop(frame, (100, 100, 200, 200), "read the number")
    assert text == "42"
    assert calls["shape"][0] >= (200 - 100) * 3  # upscaled height


def test_vlm_reader_reads_value(cfg, monkeypatch):
    from gt_spector import vlm
    from gt_spector.reader import VlmReader
    # place a 30x30 patch at (100,200) with value 7 encoded in corner
    frame = np.zeros((864, 1152, 3), dtype=np.uint8)
    frame[200:230, 100:130] = 200
    frame[200, 100] = [7, 0, 0]
    patch = _patch_digit(7)
    _register(cfg, "digit", patch)
    # The reader calls locator.find internally; register a fake locator
    class FakeLoc:
        def find(self, frame, name):
            from gt_spector.locator import LocateResult
            return LocateResult(115, 215, 0.99, True)
    def fake_analyze(frame, prompt=None, max_tokens=500, temperature=0):
        return {"choices": [{"message": {"content": "7"}}]}
    monkeypatch.setattr(vlm, "analyze_frame", fake_analyze)
    r = VlmReader(FakeLoc()).read(frame, "digit", (115, 215))
    assert r["value"] == "7"
    assert r["conf"] != ""
