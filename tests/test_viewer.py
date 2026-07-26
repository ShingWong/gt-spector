def test_viewer_cli_import():
    from viewer.cli import run_cli
    assert callable(run_cli)
