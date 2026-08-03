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
        if (x, y) == (858, 310):
            return (self.mid_r, 79, 54)
        if (x, y) == (973, 310):
            return (self.high_r, 114, 76)
        return (0, 0, 0)
    def click(self, x, y):
        self.clicks.append((x, y))
        if (x, y) == (858, 310):
            self.mid_r = 109
        elif (x, y) == (973, 310):
            self.high_r = 150
        elif (x, y) == (745, 310):
            self.mid_r = 54
            self.high_r = 52
    def refresh(self):
        pass


def test_read_frame_rate_high():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=165, high_r=150)) == "high"


def test_read_frame_rate_mid():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=109, high_r=52)) == "mid"


def test_read_frame_rate_low():
    from viewer.cli import read_frame_rate
    assert read_frame_rate(FakeFrameSession(mid_r=54, high_r=52)) == "low"


def test_set_frame_rate_cycles(monkeypatch):
    from viewer import cli as cli_mod
    monkeypatch.setattr(cli_mod, "GQ_SETTLE", 0.0)
    # low state: mid dark, high dark
    s = FakeFrameSession(mid_r=54, high_r=52)
    assert cli_mod.set_frame_rate(s, "mid") == "mid"
    assert (858, 310) in s.clicks
    assert cli_mod.set_frame_rate(s, "high") == "high"
    assert (973, 310) in s.clicks


def test_in_game_settings_registry():
    from viewer.cli import IN_GAME_SETTINGS
    assert "graphics-quality" in IN_GAME_SETTINGS
    assert "frame-rate" in IN_GAME_SETTINGS
    fr = IN_GAME_SETTINGS["frame-rate"]
    assert fr["values"] == {"low", "mid", "high"}
    assert callable(fr["read"])
    assert callable(fr["set"])
