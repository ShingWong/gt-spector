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
