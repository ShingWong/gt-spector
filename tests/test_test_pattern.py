def test_generate_test_pattern(tmp_path):
    from gt_spector.test_pattern import generate_test_pattern
    from PIL import Image

    p = generate_test_pattern(str(tmp_path / "pattern.png"), width=100, height=50)
    img = Image.open(p)
    assert img.size == (100, 50)
