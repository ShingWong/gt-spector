import pytest

from gt_spector import bot_manager
from viewer import gui as gui_mod
from viewer.gui import ViewerWindow


def make_window(**attrs) -> ViewerWindow:
    w = object.__new__(ViewerWindow)
    for k, v in attrs.items():
        setattr(w, k, v)
    return w


@pytest.fixture()
def no_live_pid(monkeypatch):
    monkeypatch.setattr(bot_manager.BotManager, "find_game_pid_by_display",
                        lambda self, display: None)


def make_session(display: str = ":10") -> object:
    return type("Session", (), {"display": display})()


def make_status() -> object:
    return type("Status", (), {"config": lambda self, **kw: None})()


def test_display_num():
    w = make_window(_session=make_session())
    assert w._display_num() == 10


def test_sound_icon_no_pid(no_live_pid):
    w = make_window(_session=make_session(), _game_pid_env=None)
    assert w._sound_icon() == "—"


@pytest.mark.parametrize("muted,expected", [(True, "🔇"), (False, "🔊"), (None, "🔊")])
def test_sound_icon(no_live_pid, monkeypatch, muted, expected):
    w = make_window(_session=make_session(), _game_pid_env="123")
    monkeypatch.setattr(gui_mod.audio, "is_muted", lambda pid: muted)
    assert w._sound_icon() == expected


def test_game_pid_resolves_live(monkeypatch):
    monkeypatch.setattr(bot_manager.BotManager, "find_game_pid_by_display",
                        lambda self, display: 999)
    w = make_window(_session=make_session(), _game_pid_env="123")
    assert w._game_pid() == 999


def test_game_pid_falls_back_to_env(no_live_pid):
    w = make_window(_session=make_session(), _game_pid_env="123")
    assert w._game_pid() == 123


def test_game_pid_none_when_no_live_or_env(no_live_pid):
    w = make_window(_session=make_session(), _game_pid_env=None)
    assert w._game_pid() is None


def test_sound_toggle_flips(no_live_pid, monkeypatch):
    state = {"muted": False}
    button_calls: list[dict] = []
    w = make_window(
        _session=make_session(),
        _game_pid_env="123",
        _status=make_status(),
        _sound_btn=type("Btn", (), {"config": lambda self, **kw: button_calls.append(kw)})(),
    )
    monkeypatch.setattr(gui_mod.audio, "is_muted", lambda pid: state["muted"])
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: state.update(muted=muted))
    w._on_sound_toggle()
    assert state["muted"] is True
    assert button_calls == [{"text": "🔇 Sound"}]
    w._on_sound_toggle()
    assert state["muted"] is False
    assert button_calls == [{"text": "🔇 Sound"}, {"text": "🔊 Sound"}]


def test_sound_toggle_no_pid(no_live_pid):
    status_calls: list[dict] = []
    w = make_window(_session=make_session(), _game_pid_env=None)
    w._status = type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})()
    w._sound_btn = type("Btn", (), {"config": lambda self, **kw: None})()
    w._on_sound_toggle()
    assert status_calls == [{"text": "No game pid for sound control"}]


def test_on_close_mutes_in_viewer_mode(no_live_pid, monkeypatch):
    destroyed: list[int] = []
    muted_calls: list[tuple] = []
    w = make_window(_session=make_session(), _game_pid_env="123", _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "viewer")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: muted_calls.append((pid, muted)))
    w._on_close()
    assert muted_calls == [(123, True)]
    assert destroyed == [1]
    assert w._running is False


def test_on_close_no_mute_other_mode(no_live_pid, monkeypatch):
    destroyed: list[int] = []
    w = make_window(_session=make_session(), _game_pid_env="123", _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "never")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: pytest.fail("no set"))
    w._on_close()
    assert destroyed == [1]
    assert w._running is False


def test_on_close_no_pid(no_live_pid, monkeypatch):
    destroyed: list[int] = []
    w = make_window(_session=make_session(), _game_pid_env=None, _tk=make_tk(destroyed))
    monkeypatch.setattr(gui_mod.settings, "sound_mode", lambda: "viewer")
    monkeypatch.setattr(gui_mod.audio, "set_muted", lambda pid, muted: pytest.fail("no set"))
    w._on_close()
    assert destroyed == [1]
    assert w._running is False


def test_on_close_bad_pid_still_closes(no_live_pid, monkeypatch):
    destroyed: list[int] = []
    w = make_window(_session=make_session(), _game_pid_env="not-a-pid", _tk=make_tk(destroyed))
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


def test_on_set_marker_with_mouse_enables_overlay(monkeypatch):
    set_calls: list[tuple] = []
    var_calls: list[bool] = []
    w = make_window(_session=make_session(), _status=make_status())
    w._marker_pick_mode = False
    w._overlay_var = type("Var", (), {"set": lambda self, v: var_calls.append(v)})()
    monkeypatch.setattr(
        gui_mod.overlay, "set_overlay_enabled", lambda d, e: set_calls.append((d, e)))
    w._on_set_marker_with_mouse()
    assert set_calls == [(10, True)]
    assert var_calls == [True]
    assert w._marker_pick_mode is True


def test_canvas_click_pick_mode_places_marker(monkeypatch):
    add_calls: list[tuple] = []
    status_calls: list[dict] = []
    w = make_window(
        _session=make_session(),
        _scale=2.0,
        _marker_pick_mode=True,
        _canvas_label=type("Lbl", (), {"focus_set": lambda self: None})(),
        _status=type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})(),
    )
    monkeypatch.setattr(
        gui_mod.overlay, "add_marker",
        lambda d, x, y, label="": add_calls.append((d, x, y, label)),
    )
    w._on_canvas_click(type("Event", (), {"x": 20, "y": 40})())
    assert add_calls == [(10, 10, 20, "picked")]
    assert w._marker_pick_mode is False
    assert w._skip_release is True
    assert status_calls == [{"text": "Marker set at (10, 20)"}]


def test_canvas_click_pick_mode_does_not_click_game():
    sent: list[str] = []
    session = type("Session", (), {
        "display": ":10",
        "move_mouse": lambda self, x, y: sent.append("move"),
        "mouse_down": lambda self: sent.append("down"),
        "mouse_up": lambda self: sent.append("up"),
    })()
    w = make_window(
        _session=session,
        _scale=1.0,
        _marker_pick_mode=True,
        _canvas_label=type("Lbl", (), {"focus_set": lambda self: None})(),
        _status=make_status(),
    )
    w._on_canvas_click(type("Event", (), {"x": 5, "y": 6})())
    assert sent == []


def test_canvas_click_pick_mode_release_skips(monkeypatch):
    w = make_window(
        _session=make_session(),
        _scale=1.0,
        _marker_pick_mode=False,
        _skip_release=True,
        _handling_release=False,
        _drag_start=None,
        _is_dragging=False,
        _canvas_label=type("Lbl", (), {})(),
        _status=make_status(),
        _last_click_time=0.0,
    )
    w._on_canvas_release(type("Event", (), {"widget": w._canvas_label, "x": 1, "y": 2})())
    assert w._skip_release is False


def test_on_clear_last_marker(monkeypatch):
    calls: list[tuple] = []
    w = make_window(_session=make_session(), _status=make_status())
    markers = [type("M", (), {"id": "m1"})(), type("M", (), {"id": "m2"})()]
    monkeypatch.setattr(gui_mod.overlay, "load_markers", lambda d: markers)
    monkeypatch.setattr(
        gui_mod.overlay, "clear_markers", lambda d, mid=None: calls.append((d, mid)))
    w._on_clear_last_marker()
    assert calls == [(10, "m2")]


def test_on_clear_last_marker_none(monkeypatch):
    status_calls: list[dict] = []
    w = make_window(_session=make_session())
    w._status = type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})()
    monkeypatch.setattr(gui_mod.overlay, "load_markers", lambda d: [])
    w._on_clear_last_marker()
    assert status_calls == [{"text": "No markers to clear"}]


def test_on_clear_all_markers(monkeypatch):
    calls: list[tuple] = []
    w = make_window(_session=make_session(), _status=make_status())
    monkeypatch.setattr(
        gui_mod.overlay, "clear_markers", lambda d, mid=None: calls.append((d, mid)))
    w._on_clear_all_markers()
    assert calls == [(10, None)]


def test_on_add_marker_at_location(monkeypatch):
    import tkinter.simpledialog as sd
    add_calls: list[tuple] = []
    status_calls: list[dict] = []
    w = make_window(_session=make_session(), _tk=make_tk([]))
    w._status = type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})()
    monkeypatch.setattr(sd, "askinteger", lambda *a, **kw: 7)
    monkeypatch.setattr(
        gui_mod.overlay, "add_marker",
        lambda d, x, y, label="": add_calls.append((d, x, y, label)),
    )
    w._on_add_marker_at_location()
    assert add_calls == [(10, 7, 7, "loc")]


def test_on_move_mouse_to(monkeypatch):
    import tkinter.simpledialog as sd
    moved: list[tuple] = []
    status_calls: list[dict] = []
    w = make_window(
        _session=type("Session", (), {"move_mouse": lambda self, x, y: moved.append((x, y))})(),
        _tk=make_tk([]),
    )
    w._status = type("Status", (), {"config": lambda self, **kw: status_calls.append(kw)})()
    monkeypatch.setattr(sd, "askinteger", lambda *a, **kw: 12)
    w._on_move_mouse_to()
    assert moved == [(12, 12)]
    assert status_calls == [{"text": "Mouse moved to (12, 12)"}]


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
