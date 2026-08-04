"""Automated IGG browser login for a bot (change account).

Verified live on bot04 (2026-08-04). Coordinates are window-relative;
screen clicks add the (+3,+29) window offset. Typing uses the one-shot
sendtext.exe helper. Each step can be confirmed/rejected via the `confirm`
hook; during development the CLI wires it to a prompt.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gt_spector import typing

EMAIL = (365, 156)
PASSWORD = (365, 226)
EYE = (885, 195)
LOGIN_BTN = (462, 258)
CONTINUE = (500, 300)
SELECT_ID = (350, 165)
OK = (700, 560)
WIN_OFFSET = (3, 29)


class LoginFlow:
    def __init__(
        self,
        session: Any,
        gw: Any,
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

    def _window_click(self, x: int, y: int) -> None:
        self._session.click(x + WIN_OFFSET[0], y + WIN_OFFSET[1])

    def _type(self, text: str, x: int, y: int) -> bool:
        return typing.type_at(self._prefix, self._display, f"{{CtrlA}}{text}", x, y)

    def _wait(self, seconds: float = 4.0) -> None:
        time.sleep(seconds)
        self._session.refresh()

    def change_account(self, email: str, password: str) -> str:
        gw = self._gw
        from gt_spector.navigator import Navigator
        nav = Navigator(gw, self._locator, self._session)

        steps = [
            ("navigate", lambda: nav.goto("change_account") is not None),
            ("open igg browser", self._open_igg_browser),
            ("enter email", lambda: self._type(email, *EMAIL)),
            ("enter password", lambda: self._type(password, *PASSWORD)),
            ("reveal password", lambda: self._window_click(*EYE) or True),
            ("submit login", self._submit_login),
            ("select id", self._select_id),
            ("confirm ok", lambda: self._window_click(*OK) or True),
        ]
        for label, fn in steps:
            if not self._confirm(label):
                return "cancelled"
            if not fn():
                return "error"
            self._wait()
        return gw.identify(self._session) or "unknown"

    def _open_igg_browser(self) -> bool:
        # on change_account state 2, IGG icon at (735,262) window-relative
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
