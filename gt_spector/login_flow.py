"""Automated IGG browser login for a bot (change account).

Verified live on bot04 (2026-08-04). All coordinates are client/frame
relative throughout the codebase, and the headless bots run under Xvfb with
no window manager, so client coords coincide with screen coords. Typing uses
the one-shot sendtext.exe helper, whose SetCursorPos is also screen-absolute.
Each step can be confirmed/rejected via the `confirm` hook; during development
the CLI wires it to a prompt.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gt_spector import typing
from gt_spector.game_world import GameWorld

EMAIL_X = 365
PASSWORD_X = 365
LOGIN_X = 365
EYE_TEMPLATES = ("igg_login_eye2_static", "login_eye_static")
EYE_X_OFFSET = 0
EMAIL_Y_ABOVE_EYE = 100
LOGIN_Y_BELOW_EYE = 70
CONTINUE = (500, 300)
SELECT_ID = (350, 165)
OK = (700, 560)


def _window_click(session: Any, x: int, y: int) -> bool:
    session.click(x, y)
    return True


def _type(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    return typing.type_at(prefix, display, f"{{CtrlA}}{text}", x, y)


def _wait(session: Any, seconds: float = 4.0) -> None:
    time.sleep(seconds)
    session.refresh()


def _find_eye(locator: Any, session: Any) -> tuple[int, int] | None:
    """Locate the password-reveal eye icon (position varies by page render).

    Both eye versions have been seen across page renders, so try each.
    """
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
    """Complete the IGG browser login from the current screen.

    Starts from wherever the browser login page is (e.g. igg_login after an
    expired session, or after change_account opens the browser) and drives
    through email, password, submit, continue, select ID, and confirm. Returns
    the final screen name, or "cancelled" / "error".

    The login page's title/background shifts between renders, so the field
    positions move. They are derived from the password-reveal eye icon, which
    is locatable: email is 100px above the eye, password aligned with it, and
    the login button 70px below it (all at x=365, inside the wide fields).
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
        ("submit login", lambda: _submit_login(session, login_pos)),
        ("continue after login", lambda: _window_click(session, *CONTINUE)),
        ("select id", lambda: _select_id(session)),
        ("confirm ok", lambda: _window_click(session, *OK)),
    ]
    for label, fn in steps:
        if not confirm(label):
            return "cancelled"
        if not fn():
            return "error"
        _wait(session)
    return gw.identify(session) or "unknown"


def _submit_login(session: Any, login_pos: tuple[int, int]) -> bool:
    session.click(*login_pos)
    _wait(session, 5)
    return True


def _select_id(session: Any) -> bool:
    session.click(*SELECT_ID)
    _wait(session, 5)
    return True


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
    """Complete login from the expired-session / unlinked-account entry.

    The game shows the expired-session dialog whenever an account is unlinked
    or its session expires. Drive it to the browser login page (OK on the
    dialog, then the game login page's IGG account button), then complete the
    IGG browser login. Returns the final screen name, or "cancelled"/"error".
    """
    confirm = confirm or (lambda _msg: True)

    nav_steps: list[tuple[str, Callable[[], bool]]] = [
        ("dismiss expired session", lambda: _ok_expired(session, locator)),
        ("open igg browser", lambda: _open_game_login(session, locator)),
    ]
    for label, fn in nav_steps:
        if not confirm(label):
            return "cancelled"
        if not fn():
            return "error"
        _wait(session)
        if confirm(f"after {label}, screen={gw.identify(session)}"):
            pass

    return login(
        email, password,
        session, gw, locator,
        prefix, display,
        confirm=confirm,
    )


def _ok_expired(session: Any, locator: Any = None) -> bool:
    """Dismiss the startup_expired dialog (click OK, or More if that shows).

    The expired-session dialog shows either an OK button or a More button
    depending on state; both lead toward the game login page.
    """
    loc = locator or _new_locator()
    for name in ("start_expire_ok_static", "start_expire_more_static"):
        r = loc.find(session.frame, name)
        if r.found:
            session.click(r.cx, r.cy)
            return True
    return True


def _open_game_login(session: Any, locator: Any) -> bool:
    """Click the dynamic IGG account button on the game login page."""
    r = locator.find(session.frame, "game_login_igg_account")
    if not r.found:
        return False
    session.click(r.cx, r.cy)
    return True


def _new_locator():
    from gt_spector.locator import Locator
    return Locator()


class LoginFlow:
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
        gw = self._gw
        from gt_spector.navigator import Navigator
        nav = Navigator(gw, self._locator, self._session)

        navigate_steps: list[tuple[str, Callable[[], bool]]] = [
            ("navigate", lambda: nav.goto("change_account") is not None),
            ("open igg browser", self._open_igg_browser),
        ]
        for label, fn in navigate_steps:
            if not self._confirm(label):
                return "cancelled"
            if not fn():
                return "error"
            self._wait()

        return login(
            email, password,
            self._session, gw, self._locator,
            self._prefix, self._display,
            confirm=self._confirm,
        )

    def _open_igg_browser(self) -> bool:
        self._window_click(735, 262)
        self._wait(6)
        return True

    def _window_click(self, x: int, y: int) -> bool:
        self._session.click(x, y)
        return True

    def _wait(self, seconds: float = 4.0) -> None:
        _wait(self._session, seconds)
