def test_copy_master_appdata_copies_bundles(monkeypatch, tmp_path):
    import gt_spector.provision as p

    master = tmp_path / "master"
    appdata = master / "Doomsday_ Last Survivors"
    (appdata / "ab").mkdir(parents=True)
    (appdata / "ab" / "bundle1").write_bytes(b"x")
    (appdata / "VITAL0").write_bytes(b"v")
    (master / "user.reg").write_bytes(b"reg")
    monkeypatch.setattr(p, "MASTER_APPDATA", str(master))

    dest = tmp_path / "dest"
    (dest / "drive_c" / "users" / "steamuser").mkdir(parents=True)
    p._copy_master_appdata(str(dest))

    target = dest / "drive_c" / "users" / "steamuser" / "AppData" / "LocalLow" / "IGG" / "Doomsday_ Last Survivors"
    assert (target / "ab" / "bundle1").exists()
    assert (target / "VITAL0").exists()
    assert (dest / "user.reg").read_bytes() == b"reg"


def test_copy_master_appdata_missing_source_warns(monkeypatch, tmp_path):
    import gt_spector.provision as p
    monkeypatch.setattr(p, "MASTER_APPDATA", str(tmp_path / "missing"))
    dest = tmp_path / "dest"
    (dest / "drive_c" / "users" / "steamuser").mkdir(parents=True)
    p._copy_master_appdata(str(dest))
