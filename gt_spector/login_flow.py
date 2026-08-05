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

EMAIL = (365, 156)
PASSWORD = (365, 226)
EYE = (885, 195)
LOGIN_BTN = (462, 258)
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
    """
    confirm = confirm or (lambda _msg: True)

    steps: list[tuple[str, Callable[[], bool]]] = [
        ("enter email", lambda: _type(prefix, display, email, *EMAIL)),
        ("enter password", lambda: _type(prefix, display, password, *PASSWORD)),
        ("reveal password", lambda: _window_click(session, *EYE)),
        ("hide password", lambda: _window_click(session, *EYE)),
        ("submit login", lambda: _submit_login(session)),
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


def _submit_login(session: Any) -> bool:
    session.click(*LOGIN_BTN)
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
    """Click OK on the startup_expired dialog (or skip if already past it)."""
    from gt_spector.locator import Locator
    loc = locator or Locator()
    r = loc.find(session.frame, "start_expire_ok_static")
    if not r.found:
        return True
    session.click(r.cx, r.cy)
    return True


def _open_game_login(session: Any, locator: Any) -> bool:
    """Click the dynamic IGG account button on the game login page."""
    r = locator.find(session.frame, "game_login_igg_account")
    if not r.found:
        return False
    session.click(r.cx, r.cy)
    return True


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
