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
