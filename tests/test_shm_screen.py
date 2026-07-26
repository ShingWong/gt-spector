def test_shm_screen(tmp_path):
    from gt_spector.screen import ShmScreen
    import numpy as np
    import struct

    shm_path = str(tmp_path / "gt-spector-test-frame")
    w, h = 100, 50
    header = struct.pack("<QII", 1, w, h)
    pixels = b'\x00\x00\xff\xff' * (w * h)
    with open(shm_path, "wb") as f:
        f.write(header + pixels)

    sc = ShmScreen.__new__(ShmScreen)
    sc._path = shm_path
    sc._frame = None
    sc._last_counter = 0

    frame = sc.refresh()
    assert frame.shape == (h, w, 3)
    assert tuple(frame[0, 0]) == (255, 0, 0)
