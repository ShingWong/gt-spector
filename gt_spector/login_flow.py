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

    def _window_click(self, x: int, y: int) -> bool:
        self._session.click(x, y)
        return True

    def _type(self, text: str, x: int, y: int) -> bool:
        return typing.type_at(self._prefix, self._display, f"{{CtrlA}}{text}", x, y)

    def _wait(self, seconds: float = 4.0) -> None:
        time.sleep(seconds)
        self._session.refresh()

    def change_account(self, email: str, password: str) -> str:
        gw = self._gw
        from gt_spector.navigator import Navigator
        nav = Navigator(gw, self._locator, self._session)

        steps: list[tuple[str, Callable[[], bool]]] = [
            ("navigate", lambda: nav.goto("change_account") is not None),
            ("open igg browser", self._open_igg_browser),
            ("enter email", lambda: self._type(email, *EMAIL)),
            ("enter password", lambda: self._type(password, *PASSWORD)),
            ("reveal password", lambda: self._window_click(*EYE)),
            ("hide password", lambda: self._window_click(*EYE)),
            ("submit login", self._submit_login),
            ("continue after login", lambda: self._window_click(*CONTINUE)),
            ("select id", self._select_id),
            ("confirm ok", lambda: self._window_click(*OK)),
        ]
        for label, fn in steps:
            if not self._confirm(label):
                return "cancelled"
            if not fn():
                return "error"
            self._wait()
        return gw.identify(self._session) or "unknown"

    def _open_igg_browser(self) -> bool:
        self._window_click(735, 262)
        self._wait(6)
        return True

    def _submit_login(self) -> bool:
        self._window_click(*LOGIN_BTN)
        self._wait(5)
        return True

    def _select_id(self) -> bool:
        self._window_click(*SELECT_ID)
        self._wait(5)
        return True
