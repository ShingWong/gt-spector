def test_login_field_locations_present():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    for name, coords in {
        "login_enter_email_static": (365, 156),
        "login_enter_password": (365, 226),
        "login_eye_static": (885, 195),
        "login_login_static": (462, 258),
    }.items():
        loc = gw.locations.get(name)
        assert loc is not None, f"missing {name}"
        assert (loc["x"], loc["y"]) == coords, f"{name} at {coords}"


class _FakeLocate:
    def __init__(self, found: bool):
        self.found = found
        self.cx = 0
        self.cy = 0
        self.score = 1.0


class _FakeLocator:
    def __init__(self, present: set[str]):
        self._present = present

    def find(self, frame, name):
        return _FakeLocate(name in self._present)


def test_login_screen_states_identify_uniquely():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    session = type("S", (), {"frame": None})()
    cases = {
        "igg_login": {"igg_login_exit_static", "login_enter_email_static"},
        "igg_login_success": {"igg_login_exit_static", "login_ok_currently_static"},
        "select_igg_id": {"igg_login_exit_static", "login_select_igg_id_static"},
        "igg_id_confirm": {"login_confirm_igg_id_static"},
    }
    for expected, present in cases.items():
        gw.set_locator(_FakeLocator(present))
        assert gw.identify(session) == expected


def test_login_screen_templates_exist_in_store():
    from gt_spector import templates as _t
    names = {
        "igg_login_exit_static",
        "login_enter_email_static",
        "login_ok_currently_static",
        "login_select_igg_id_static",
        "login_confirm_igg_id_static",
    }
    available = {t.name for t in _t.load_templates()}
    assert names <= available


def test_hero_details_screen_config():
    from gt_spector.game_world import GameWorld
    gw = GameWorld()
    spec = gw.screens["hero_details"]
    assert spec["templates"] == ["hero_details_detect_static"]
    assert spec.get("advance") == "esc"
    # ESC from hero_details returns to shelter (not world map).
    assert gw.navigation["hero_details"]["shelter"] == {"action": "esc"}


def test_hero_details_template_in_store():
    from gt_spector import templates as _t
    available = {t.name for t in _t.load_templates()}
    assert "hero_details_detect_static" in available
    t = next(x for x in _t.load_templates() if x.name == "hero_details_detect_static")
    assert t.fixed is True


def test_identify_self_initializes_locator(monkeypatch):
    from gt_spector import locator as locator_mod
    from gt_spector.game_world import GameWorld

    created = []
    class FakeLocator:
        def __init__(self):
            created.append(self)
        def find(self, frame, name):
            return _FakeLocate(False)
    monkeypatch.setattr(locator_mod, "Locator", FakeLocator)

    gw = GameWorld()
    assert gw._locator is None
    session = type("S", (), {"frame": object()})()
    gw.identify(session)
    # identify lazily created a locator instead of skipping template screens
    assert len(created) == 1
