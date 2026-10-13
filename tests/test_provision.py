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


def test_clear_master_session_removes_session_keys(tmp_path):
    import gt_spector.provision as p

    reg = tmp_path / "user.reg"
    reg.write_text(
        '"gpc.sdk.last_login.userid_h1"=hex:32,31\n'
        '"gpc.sdk.account.gpcid_h2"=hex:33,34\n'
        '"PreLoginUserId_h3"=hex:35,36\n'
        '"2086834008|LoginState_h4"=dword:00000001\n'
        '"gpc.sdk.agreement.last.signing.timestamp.v2._x_h5"=hex:31\n'
        '"kept_other_setting_h6"=dword:00000002\n'
    )
    p._clear_master_session(str(reg))
    content = reg.read_text()
    # Session keys removed; tutorial/agreement + unrelated keys kept.
    assert "last_login.userid" not in content
    assert "account.gpcid" not in content
    assert "PreLoginUserId" not in content
    assert "LoginState_h4" in content
    assert "agreement.last.signing" in content
    assert "kept_other_setting_h6" in content


def test_clear_master_session_missing_file(tmp_path):
    import gt_spector.provision as p

    p._clear_master_session(str(tmp_path / "nope.reg"))  # no error


def test_clear_master_cookies_removes_sso(tmp_path):
    import gt_spector.provision as p

    appdata = tmp_path / "appdata"
    appdata.mkdir()
    (appdata / "Cookies").write_bytes(b"account_sso_token...")
    (appdata / "Cookies-journal").write_bytes(b"j")
    (appdata / "Local Storage" / "leveldb").mkdir(parents=True)
    (appdata / "Local Storage" / "leveldb" / "000003.log").write_bytes(b"sr02-14")
    (appdata / "Session Storage").mkdir()
    (appdata / "udid_cache").write_bytes(b"f1466fec")
    (appdata / "guestid_cache").write_bytes(b"f1466fec")
    (appdata / "unrelated").write_bytes(b"keep")
    p._clear_master_cookies(str(appdata))
    assert not (appdata / "Cookies").exists()
    assert not (appdata / "Cookies-journal").exists()
    assert not (appdata / "Local Storage").exists()
    assert not (appdata / "Session Storage").exists()
    assert not (appdata / "udid_cache").exists()
    assert not (appdata / "guestid_cache").exists()
    assert (appdata / "unrelated").exists()


def test_clear_master_cookies_missing(tmp_path):
    import gt_spector.provision as p

    p._clear_master_cookies(str(tmp_path / "nope"))  # no error


def test_copy_master_appdata_missing_source_warns(monkeypatch, tmp_path):
    import gt_spector.provision as p
    monkeypatch.setattr(p, "MASTER_APPDATA", str(tmp_path / "missing"))
    dest = tmp_path / "dest"
    (dest / "drive_c" / "users" / "steamuser").mkdir(parents=True)
    p._copy_master_appdata(str(dest))
