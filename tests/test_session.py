def test_session_file_source(tmp_path):
    from gt_spector import Session
    import numpy as np
    from PIL import Image

    img = Image.new("RGB", (100, 50), color=(255, 0, 0))
    path = str(tmp_path / "test.png")
    img.save(path)

    s = Session(":9", source=f"file://{path}")
    assert s.frame.shape == (50, 100, 3)
    assert s.get_pixel(0, 0) == (255, 0, 0)
    area = s.capture_area(0, 0, 50, 25)
    assert area.shape == (25, 50, 3)
