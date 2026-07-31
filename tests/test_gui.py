import pytest

from viewer import gui as gui_mod
from viewer.gui import ViewerWindow


def make_window(**attrs) -> ViewerWindow:
    w = object.__new__(ViewerWindow)
    for k, v in attrs.items():
        setattr(w, k, v)
    return w


def make_session(display: str = ":10") -> object:
    return type("Session", (), {"display": display})()


def make_status() -> object:
    return type("Status", (), {"config": lambda self, **kw: None})()


def test_display_num():
    w = make_window(_session=make_session())
    assert w._display_num() == 10


def test_sound_icon_no_pid():
    w = make_window(_game_pid=None)
    assert w._sound_icon() == "—"


@pytest.mark.parametrize("muted,expected", [(True, "🔇"), (False, "🔊"), (None, "🔊")])
def test_sound_icon(monkeypatch, muted, expected):
    w = make_window(_game_pid="123")
    monkeypatch.setattr(gui_mod.audio, "is_muted", lambda pid: muted)
    assert w._sound_icon() == expected


def test_sound_toggle_flips(monkeypatch):
    state = {"muted": False}
    button_calls: list[dict] = []
    w = make_window(
        _game_pid="123",
        _status=make_status(),
        _sound_btn=type("Btn", (), {"config": lambda self, **kw: button_calls.append(kw)})(),
    )
    monkeypatch.setattr(gui_mod.audio, "is_muted", lambda pid: state["muted"])
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: state.update(muted=muted))
    w._on_sound_toggle()
    assert state["muted"] is True
    assert button_calls == [{"text": "🔇"}]
    w._on_sound_toggle()
    assert state["muted"] is False
    assert button_calls == [{"text": "🔇"}, {"text": "🔊"}]


def test_sound_toggle_no_pid():
    status_calls: list[dict] = []
    w = make_window(_game_pid=None)
    w._status = type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})()
    w._sound_btn = type("Btn", (), {"config": lambda self, **kw: None})()
    w._on_sound_toggle()
    assert status_calls == [{"text": "No game pid for sound control"}]


def test_on_close_mutes_in_viewer_mode(monkeypatch):
    destroyed: list[int] = []
    muted_calls: list[tuple] = []
    w = make_window(_game_pid="123", _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "viewer")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: muted_calls.append((pid, muted)))
    w._on_close()
    assert muted_calls == [(123, True)]
    assert destroyed == [1]
    assert w._running is False


def test_on_close_no_mute_other_mode(monkeypatch):
    destroyed: list[int] = []
    w = make_window(_game_pid="123", _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "never")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: pytest.fail("no set"))
    w._on_close()
    assert destroyed == [1]
    assert w._running is False


def test_on_close_no_pid(monkeypatch):
    destroyed: list[int] = []
    w = make_window(_game_pid=None, _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "viewer")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: pytest.fail("no set"))
    w._on_close()
    assert destroyed == [1]
    assert w._running is False


def test_on_close_bad_pid_still_closes(monkeypatch):
    destroyed: list[int] = []
    w = make_window(_game_pid="not-a-pid", _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "viewer")
    w._on_close()
    assert destroyed == [1]
    assert w._running is False


def test_mouse_move_tracks_position():
    w = make_window(
        _scale=2.0,
        _session=type("Session", (), {"get_pixel": lambda self, x, y: (1, 2, 3)})(),
        _status=make_status(),
    )
    w._on_mouse_move(type("Event", (), {"x": 10, "y": 20})())
    assert w._last_frame_pos == (5, 10)


def test_mouse_move_no_scale():
    w = make_window(_session=make_session(), _status=make_status())
    w._on_mouse_move(type("Event", (), {"x": 10, "y": 20})())
    assert not hasattr(w, "_last_frame_pos")


def test_on_overlay_toggle(monkeypatch):
    calls: list[tuple] = []
    w = make_window(_session=make_session())
    w._overlay_var = type("Var", (), {"get": lambda self: True})()
    monkeypatch.setattr(gui_mod.overlay, "set_overlay_enabled", lambda d, e: calls.append((d, e)))
    w._on_overlay_toggle()
    assert calls == [(10, True)]


def test_on_add_marker_at_cursor_uses_last_pos(monkeypatch):
    calls: list[tuple] = []
    w = make_window(_session=make_session(), _last_frame_pos=(42, 43))
    monkeypatch.setattr(
        gui_mod.overlay, "add_marker",
        lambda d, x, y, label="": calls.append((d, x, y, label)),
    )
    w._on_add_marker_at_cursor()
    assert calls == [(10, 42, 43, "cursor")]


def test_on_viewer_list_markers(monkeypatch):
    titles: list[str] = []
    texts: list[str] = []

    class FakeWin:
        def __init__(self, master):
            titles.append("win")

        def title(self, t):
            titles.append(t)

    class FakeLabel:
        def __init__(self, master, text):
            texts.append(text)

        def pack(self, **kw):
            pass

    w = make_window(_session=make_session(), _tk=make_tk([]))
    markers = [type("M", (), {"id": "m1", "x": 1, "y": 2, "label": "a"})()]
    monkeypatch.setattr(gui_mod.overlay, "load_markers", lambda d: markers)
    monkeypatch.setattr(gui_mod.tk, "Toplevel", FakeWin)
    monkeypatch.setattr(gui_mod.ttk, "Label", FakeLabel)
    w._on_viewer_list_markers()
    assert titles == ["win", "Markers"]
    assert texts == ["m1 @ (1,2) label='a'"]


def make_tk(destroyed: list) -> object:
    return type("Tk", (), {"destroy": lambda self: destroyed.append(1)})()
