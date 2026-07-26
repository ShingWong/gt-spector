def test_cli_commands_exist():
    from viewer.cli import CliSession
    from gt_spector.session import Session
    s = Session(":99")
    cli = CliSession.__new__(CliSession)
    cli._session = s
    assert hasattr(cli, "do_move")
    assert hasattr(cli, "do_click")
    assert hasattr(cli, "do_drag")
    assert hasattr(cli, "do_key")
    assert hasattr(cli, "do_type")
