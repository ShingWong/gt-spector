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
