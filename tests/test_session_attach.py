def test_session_attach(tmp_path):
    from gt_spector import Session
    from PIL import Image
    img = Image.new("RGB", (50, 50), color=(0, 255, 0))
    p1 = str(tmp_path / "green.png")
    img.save(p1)
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    p2 = str(tmp_path / "red.png")
    img.save(p2)

    s = Session(":9", source=f"file://{p1}")
    assert s.get_pixel(0, 0) == (0, 255, 0)
    s.attach(":0", source=f"file://{p2}")
    assert s.get_pixel(0, 0) == (255, 0, 0)
    s.detach()
