from gt_spector.scripts.help_loop import HELP_COLOR, HelpLoop


class FakeSession:
    def __init__(self, pixel):
        self.pixel = pixel
        self.clicks = 0

    def get_pixel(self, x, y):
        return self.pixel

    def click(self, x, y):
        self.clicks += 1


def _gold():
    return (HELP_COLOR >> 16) & 0xFF, (HELP_COLOR >> 8) & 0xFF, HELP_COLOR & 0xFF


def test_help_loop_clicks_on_gold_pixel():
    s = FakeSession(_gold())
    assert HelpLoop().run(s) == "clicked"
    assert s.clicks == 1


def test_help_loop_idle_on_gray_pixel():
    s = FakeSession((120, 120, 120))
    assert HelpLoop().run(s) == "idle"
    assert s.clicks == 0
