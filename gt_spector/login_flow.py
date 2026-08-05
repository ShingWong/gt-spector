"""IGG login: state-machine navigation + working browser login.

The path to the browser login (expired-session dialog -> game login page ->
IGG browser) is modeled as a locator-driven state machine that adapts to
whatever screen is present. Once on the IGG browser login form, the proven
login() routine (eye-derived field positions, sendtext.exe typing) takes
over and completes the login through the ID-select/confirm screens.

Credential entry is NOT rewritten: it is the same code verified on bot05.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gt_spector import typing
from gt_spector.game_world import GameWorld

EMAIL_X = 365
EMAIL_Y_ABOVE_EYE = 100
LOGIN_Y_BELOW_EYE = 70

EYE_TEMPLATES = ("igg_login_eye2_static", "login_eye_static")

# Reliable in-game templates (login succeeded). region_overview/avatar match
# spuriously on the login page, so they are excluded.
IN_GAME_TEMPLATES = ("region_static", "shelter")


def _wait(session: Any, seconds: float = 4.0) -> None:
    time.sleep(seconds)
    session.refresh()


def _type(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    return typing.type_at(prefix, display, f"{{CtrlA}}{text}", x, y)


def _window_click(session: Any, x: int, y: int) -> bool:
    session.click(x, y)
    return True


def _find_eye(locator: Any, session: Any) -> tuple[int, int] | None:
    """Locate the password-reveal eye icon (position varies by page render)."""
    if locator is None:
        from gt_spector.locator import Locator
        locator = Locator()
    for name in EYE_TEMPLATES:
        r = locator.find(session.frame, name)
        if r.found:
            return (r.cx, r.cy)
    return None


def login(
    email: str,
    password: str,
    session: Any,
    gw: GameWorld,
    locator: Any,
    prefix: str,
    display: str,
    confirm: Callable[[str], bool] | None = None,
) -> str:
    """Complete the IGG browser login from the current screen (verified).

    Starts from wherever the browser login page is and drives through email,
    password, submit, continue, select ID, and confirm. Returns the final
    screen name, or "cancelled" / "error". Field positions are derived from
    the password-reveal eye icon (email 100px above, password aligned, login
    70px below, all at x=365 inside the wide fields).
    """
    confirm = confirm or (lambda _msg: True)
    eye = _find_eye(locator, session)
    if eye is None:
        return "error: eye icon not found"
    _, ey = eye
    email_pos = (EMAIL_X, ey - EMAIL_Y_ABOVE_EYE)
    pass_pos = (EMAIL_X, ey)
    login_pos = (EMAIL_X, ey + LOGIN_Y_BELOW_EYE)

    steps: list[tuple[str, Callable[[], bool]]] = [
        ("enter email", lambda: _type(prefix, display, email, *email_pos)),
        ("enter password", lambda: _type(prefix, display, password, *pass_pos)),
        ("reveal password", lambda: _window_click(session, *eye)),
        ("hide password", lambda: _window_click(session, *eye)),
        ("submit login", lambda: _window_click(session, *login_pos)),
        ("continue after login", lambda: _window_click(session, 500, 300)),
        ("select id", lambda: _window_click(session, 350, 165)),
        ("confirm ok", lambda: _window_click(session, 700, 560)),
    ]
    for label, fn in steps:
        if not confirm(label):
            return "cancelled"
        if not fn():
            return "error"
        _wait(session)
    return gw.identify(session) or "unknown"


class LoginStateMachine:
    """Drive navigation to the IGG browser, then call login().

    States are detected by locating templates. On the browser login form
    (igg_login), the working login() completes the flow. Unknown states fall
    back to the Navigator's ESC recovery.
    """

    def __init__(
        self,
        session: Any,
        gw: GameWorld,
        locator: Any,
        prefix: str,
        display: str,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._session = session
        self._gw = gw
        self._locator = locator
        self._prefix = prefix
        self._display = display
        self._confirm = confirm or (lambda _msg: True)

    def _locate(self, name: str):
        r = self._locator.find(self._session.frame, name)
        return r if r.found else None

    def _in_game(self) -> bool:
        return any(self._locate(t) is not None for t in IN_GAME_TEMPLATES)

    def _detect_state(self) -> str:
        if self._in_game():
            return "in_game"
        for name in ("igg_login_exit_static", "game_login_last_login_static",
                     "start_expire_ok_static", "start_expire_more_static"):
            if self._locate(name):
                return name
        return "unknown"

    def run(self, email: str, password: str) -> str:
        for _ in range(20):
            state = self._detect_state()
            if state == "in_game":
                return self._gw.identify(self._session) or "in_game"
            if not self._confirm(state):
                return "cancelled"

            if state in ("start_expire_ok_static", "start_expire_more_static"):
                r = self._locate(state)
                if r is None:
                    return "error"
                self._session.click(r.cx, r.cy)
            elif state == "game_login_last_login_static":
                r = self._locate("game_login_igg_account")
                if r is None:
                    return "error"
                self._session.click(r.cx, r.cy)
            elif state == "igg_login_exit_static":
                # Browser login form reached: use the proven login() routine.
                return login(
                    email, password,
                    self._session, self._gw, self._locator,
                    self._prefix, self._display,
                    confirm=self._confirm,
                )
            else:  # unknown: last-resort ESC recovery
                from gt_spector.navigator import Navigator
                nav = Navigator(self._gw, self._locator, self._session)
                nav._recover_esc()
            _wait(self._session)
        return "timeout"


def expired_login(
    email: str,
    password: str,
    session: Any,
    gw: GameWorld,
    locator: Any,
    prefix: str,
    display: str,
    confirm: Callable[[str], bool] | None = None,
) -> str:
    """Complete login from the expired-session / unlinked-account entry."""
    return LoginStateMachine(
        session, gw, locator, prefix, display, confirm=confirm,
    ).run(email, password)


class LoginFlow:
    """Back-compat wrapper: change_account navigates to the browser then logs in."""

    def __init__(
        self,
        session: Any,
        gw: GameWorld,
        locator: Any,
        prefix: str,
        display: str,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._session = session
        self._gw = gw
        self._locator = locator
        self._prefix = prefix
        self._display = display
        self._confirm = confirm or (lambda _msg: True)

    def change_account(self, email: str, password: str) -> str:
        from gt_spector.navigator import Navigator
        nav = Navigator(self._gw, self._locator, self._session)
        if not self._confirm("navigate"):
            return "cancelled"
        if nav.goto("change_account") != "change_account":
            return "error"
        if not self._confirm("open igg browser"):
            return "cancelled"
        self._session.click(735, 262)
        _wait(self._session, 6)
        return login(
            email, password,
            self._session, self._gw, self._locator,
            self._prefix, self._display,
            confirm=self._confirm,
        )
