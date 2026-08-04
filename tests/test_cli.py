def test_cli_commands_exist():
    from gt_spector.session import Session
    from viewer.cli import CliSession
    s = Session(":99")
    cli = CliSession.__new__(CliSession)
    cli._session = s
    assert hasattr(cli, "do_move")
    assert hasattr(cli, "do_click")
    assert hasattr(cli, "do_drag")
    assert hasattr(cli, "do_key")
    assert hasattr(cli, "do_type")


def test_cli_navigation_commands_exist():
    from gt_spector.session import Session
    from viewer.cli import CliSession
    s = Session(":99")
    cli = CliSession.__new__(CliSession)
    cli._session = s
    for cmd in ("where", "go", "route", "locate", "label", "screens", "loc"):
        assert hasattr(cli, f"do_{cmd}"), f"missing do_{cmd}"


def test_do_change_account_wires_flow(monkeypatch):
    from viewer import cli as cli_mod

    calls = {}
    class FakeFlow:
        def __init__(self, *a, **k):
            calls["kwargs"] = k
        def change_account(self, email, password):
            calls["account"] = (email, password)
            return "shelter_view"

    monkeypatch.setattr(cli_mod, "LoginFlow", FakeFlow)
    s = object.__new__(cli_mod.CliSession)
    s._session = type("S", (), {"display": ":13"})()
    s._display = 13
    s._gw = object()
    s._locator = object()
    monkeypatch.setattr(s, "_bot_prefix", lambda: "/home/swong/dls/wineprefix_bots/bot04")
    s.do_change_account("sr02-07@mx1.us bamboo-H4")
    assert calls["account"] == ("sr02-07@mx1.us", "bamboo-H4")
    assert "confirm" in calls["kwargs"]


def test_cli_go_parses_verbose_flag(monkeypatch):
    from viewer import cli as cli_mod

    traces: list[object] = []

    class FakeSession:
        def refresh(self) -> None:
            pass

    class FakeGW:
        def identify(self, session: object) -> str:
            return "alliance_menu"

    class FakeNavigator:
        def __init__(
            self,
            gw: FakeGW,
            locator: object,
            session: FakeSession,
            trace: object | None = None,
        ) -> None:
            self.gw = gw
            self.session = session
            self.trace = trace
            traces.append(trace)

        def goto(self, target: str) -> str:
            self.session.refresh()
            return self.gw.identify(self.session) or target

    monkeypatch.setattr(cli_mod, "Navigator", FakeNavigator)

    cli = cli_mod.CliSession.__new__(cli_mod.CliSession)
    cli._session = FakeSession()
    object.__setattr__(cli, "_gw", FakeGW())
    object.__setattr__(cli, "_locator", object())

    cli.do_go("alliance_menu -v")
    assert traces[-1] is not None
    assert callable(traces[-1])

    cli.do_go("alliance_menu")
    assert traces[-1] is None


class FakeFrameSession:
    def __init__(self, mid_r, high_r):
        self.mid_r = mid_r
        self.high_r = high_r
        self.clicks: list[tuple[int, int]] = []
    def get_pixel(self, x, y):
        # GQ_LOW sentinel bright => top rows in view
        if (x, y) == (825, 253):
            return (200, 0, 0)
        if (x, y) == (966, 253):
            return (0, 0, 0)
        if (x, y) == (858, 363):
            return (self.mid_r, 79, 54)
        if (x, y) == (973, 363):
            return (self.high_r, 114, 76)
        return (0, 0, 0)
    def click(self, x, y):
        self.clicks.append((x, y))
        if (x, y) == (858, 363):
            self.mid_r = 77
            self.high_r = 38
        elif (x, y) == (973, 363):
            self.mid_r = 156
            self.high_r = 96
        elif (x, y) == (745, 363):
            self.mid_r = 38
            self.high_r = 38
    def refresh(self):
        pass
    def move_mouse(self, x, y):
        pass
    def scroll(self, direction, amount):
        pass


def test_read_frame_rate_high():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=156, high_r=96)) == "high"


def test_read_frame_rate_mid():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=77, high_r=38)) == "mid"


def test_read_frame_rate_low():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=38, high_r=38)) == "low"


def test_set_frame_rate_cycles(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    # low state: mid dark, high dark
    s = FakeFrameSession(mid_r=54, high_r=52)
    assert cli_mod.set_frame_rate(s, "mid") == "mid"
    assert (858, 363) in s.clicks
    assert cli_mod.set_frame_rate(s, "high") == "high"
    assert (973, 363) in s.clicks


def test_in_game_settings_registry():
    from viewer.cli import IN_GAME_SETTINGS
    assert "graphics-quality" in IN_GAME_SETTINGS
    assert "frame-rate" in IN_GAME_SETTINGS
    assert "sound-effects" in IN_GAME_SETTINGS
    assert "background-music" in IN_GAME_SETTINGS
    for key in ("graphics-quality", "frame-rate", "sound-effects", "background-music"):
        entry = IN_GAME_SETTINGS[key]
        assert entry["values"]
        assert callable(entry["read"])
        assert callable(entry["set"])


class FakeToggleSession:
    def __init__(self, on_r: int, visible: bool = True):
        self.on_r = on_r
        self.visible = visible
        self.clicks: list[tuple[int, int]] = []
        self.scroll_calls: list[tuple[int, int]] = []
    def get_pixel(self, x, y):
        # the ON indicators are the read discriminators; OFF indicators are
        # always lit when the row is in view (used by the scroll sentinel)
        if not self.visible:
            return (0, 0, 0)
        if (x, y) in ((906, 532), (906, 638)):
            return (200, 84, 58)
        if (x, y) in ((955, 532), (955, 638)):
            return (self.on_r, 84, 58)
        return (0, 0, 0)
    def click(self, x, y):
        self.clicks.append((x, y))
        # invert: clicking toggles between on-bright and on-dim
        self.on_r = 121 if self.on_r < 80 else 57
    def refresh(self):
        pass
    def move_mouse(self, x, y):
        pass
    def scroll(self, direction, amount):
        self.scroll_calls.append((direction, amount))
        self.visible = True


def test_read_sound_effects_off():
    from viewer.cli import read_sound_effects
    assert read_sound_effects(FakeToggleSession(on_r=57)) == "off"


def test_read_sound_effects_on():
    from viewer.cli import read_sound_effects
    assert read_sound_effects(FakeToggleSession(on_r=121)) == "on"


def test_read_background_music_off():
    from viewer.cli import read_background_music
    assert read_background_music(FakeToggleSession(on_r=25)) == "off"


def test_read_background_music_on():
    from viewer.cli import read_background_music
    assert read_background_music(FakeToggleSession(on_r=115)) == "on"


def test_set_sound_effects(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    s = FakeToggleSession(on_r=121)  # currently on
    assert cli_mod.set_sound_effects(s, "off") == "off"
    assert (906, 532) in s.clicks


def test_set_background_music(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    s = FakeToggleSession(on_r=25)  # currently off
    assert cli_mod.set_background_music(s, "on") == "on"
    assert (955, 638) in s.clicks


class FakeScrollableSession:
    """Simulates a scrollable system settings list with a hard stop.

    pos 0 = top (graphics/frame rows in view), pos 1 = bottom (sound/music).
    Scrolling moves toward the stop; once there, further scrolls are no-ops
    so consecutive refresh frames are identical.
    """

    def __init__(self, pos: int = 0):
        self.pos = pos
        self.scroll_calls: list[tuple[int, int]] = []
        self.mouse_moves: list[tuple[int, int]] = []
        import numpy as np
        self._np = np

    def move_mouse(self, x: int, y: int) -> None:
        self.mouse_moves.append((x, y))

    def _frame(self):
        a = self._np.zeros((100, 100, 3), dtype=self._np.uint8)
        return a

    @property
    def frame(self):
        return self._frame()

    def refresh(self):
        # frame encodes the scroll stop reached
        return True

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        if (x, y) in ((825, 253), (966, 253)):
            return (120 if self.pos == 0 else 20, 10, 10)
        if (x, y) in ((906, 532), (955, 532)):
            return (120 if self.pos == 1 else 20, 10, 10)
        return (0, 0, 0)

    def scroll(self, direction: int, amount: int) -> None:
        self.scroll_calls.append((direction, amount))
        if direction > 0 and self.pos > 0:
            self.pos -= 1
        elif direction < 0 and self.pos < 1:
            self.pos += 1


def test_ensure_settings_row_scrolls_to_top(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "SETTINGS_SCROLL_SETTLE", 0.0)
    s = FakeScrollableSession(pos=1)  # currently at bottom
    assert cli_mod.ensure_settings_row(s, "top")
    assert s.pos == 0
    assert s.scroll_calls and s.scroll_calls[0][0] > 0
    assert (600, 400) in s.mouse_moves


def test_ensure_settings_row_scrolls_to_bottom(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "SETTINGS_SCROLL_SETTLE", 0.0)
    s = FakeScrollableSession(pos=0)  # currently at top
    assert cli_mod.ensure_settings_row(s, "bottom")
    assert s.pos == 1
    assert s.scroll_calls and s.scroll_calls[0][0] < 0


def test_ensure_settings_row_already_in_place(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "SETTINGS_SCROLL_SETTLE", 0.0)
    s = FakeScrollableSession(pos=0)
    assert cli_mod.ensure_settings_row(s, "top")
    assert s.scroll_calls == []


def test_set_sound_effects_ensures_bottom(monkeypatch):
    from viewer import cli as cli_mod

    calls: list[str] = []
    monkeypatch.setattr(cli_mod, "ensure_settings_row", lambda s, pos: calls.append(pos) or True)
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    s = FakeToggleSession(on_r=121)  # already off
    assert cli_mod.set_sound_effects(s, "off") == "off"
    assert calls == ["bottom"]


def test_set_graphics_quality_ensures_top(monkeypatch):
    from viewer import cli as cli_mod

    calls: list[str] = []
    monkeypatch.setattr(cli_mod, "ensure_settings_row", lambda s, pos: calls.append(pos) or True)
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    s = FakeFrameSession(mid_r=54, high_r=52)  # already low
    assert cli_mod.set_graphics_quality(s, "low") == "low"
    assert calls == ["top"]
