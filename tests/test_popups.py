from gt_spector.popups import (
    BACK_BUTTON_SCREENS,
    SCREENSAVER_SCREENS,
    exit_popups,
)


class _FakeLocate:
    def __init__(self, found=True):
        self.found = found
        self.cx = 22
        self.cy = 21


class _FakeLocator:
    def find(self, frame, name):
        return _FakeLocate()


class _FakeSession:
    def __init__(self):
        self.keys = []
        self.clicks = []
        self.refreshed = 0
        self.frame = None

    def key_press(self, key):
        self.keys.append(key)

    def click(self, x, y):
        self.clicks.append((x, y))

    def refresh(self):
        self.refreshed += 1


def test_registries_cover_known_popups():
    assert "resouce_reaping" in SCREENSAVER_SCREENS
    assert "another_login_disconnect" in SCREENSAVER_SCREENS
    assert "road_to_conquest_menu" in BACK_BUTTON_SCREENS
    assert "unknown_screen_with_back_button" in BACK_BUTTON_SCREENS


def test_exit_popups_esc_for_screensaver():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "resouce_reaping") is True
    assert "Escape" in s.keys


def test_exit_popups_esc_for_another_login():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "another_login_disconnect") is True
    assert "Escape" in s.keys


def test_exit_popups_back_button_for_road_to_conquest():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "road_to_conquest_menu") is True
    assert s.clicks == [(22, 21)]


def test_exit_popups_back_button_for_unknown_with_back():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "unknown_screen_with_back_button") is True
    assert s.clicks == [(22, 21)]


def test_exit_popups_no_action_for_unknown_screen():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), "shelter_view") is False
    assert s.keys == [] and s.clicks == []


def test_exit_popups_none_screen_no_action():
    s = _FakeSession()
    assert exit_popups(s, _FakeLocator(), None) is False


def test_exit_popups_no_action_when_back_button_missing():
    class _NoBack(_FakeLocator):
        def find(self, frame, name):
            return _FakeLocate(found=False)

    s = _FakeSession()
    assert exit_popups(s, _NoBack(), "road_to_conquest_menu") is False
    assert s.clicks == []
