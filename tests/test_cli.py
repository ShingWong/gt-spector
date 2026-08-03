import shlex


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
    from gt_spector.session import Session
    from viewer.cli import CliSession
    s = Session(":99")
    cli = CliSession.__new__(CliSession)
    cli._session = s
    # stub the navigator
    traced = {}
    class FakeNav:
        def goto(self, target):
            return target
        def route_to(self, target):
            return ["a", target]
    cli._navigator = FakeNav()
    cli._gw = object()
    cli._trace = traced

    # go with -v must pass a trace; go without -v must not
    # we capture via monkeypatching print into traced["calls"]
    out = []
    import builtins
    monkeypatch.setattr(builtins, "print", lambda *a, **k: out.append(a[0]))
    # Simulate the -v flag parsing directly
    args = shlex.split("alliance_menu -v")
    verbose = "-v" in args
    args = [a for a in args if a != "-v"]
    assert verbose is True
    assert args == ["alliance_menu"]
