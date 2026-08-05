"""IGG browser login as a locator-driven state machine.

The login path (expired-session dialog -> game login page -> IGG browser
login -> success -> select ID -> confirm -> in game) is modeled as a set of
states, each detected by locating templates. At every step the machine
locates templates to determine the current state and acts accordingly,
branching to whatever login state is actually present (the page title and
field positions shift between renders, so fixed coordinates are unreliable).

Credential entry derives field positions from the password-reveal eye icon
(both eye versions are seen across renders). Typing uses the one-shot
sendtext.exe helper. The terminal state is any in-game screen.
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

# In-game templates that mean "login succeeded".
IN_GAME_TEMPLATES = ("region_static", "region_overview", "avatar", "shelter")


def _wait(session: Any, seconds: float = 4.0) -> None:
    time.sleep(seconds)
    session.refresh()


def _type(prefix: str, display: str, text: str, x: int, y: int) -> bool:
    return typing.type_at(prefix, display, f"{{CtrlA}}{text}", x, y)


def _find(locator: Any, session: Any, name: str):
    r = locator.find(session.frame, name)
    return r if r.found else None


class LoginStateMachine:
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

    # ── State detection ────────────────────────────────────────────────
    def _locate(self, name: str):
        return _find(self._locator, self._session, name)

    def _in_game(self) -> bool:
        return any(self._locate(t) is not None for t in IN_GAME_TEMPLATES)

    def _detect_state(self) -> str:
        """Return the current state name by locating templates.

        Priority: in-game (terminal) first, then login states, so a screen
        that matches multiple templates resolves to the most advanced state.
        """
        if self._in_game():
            return "in_game"
        for name in ("login_confirm_igg_id_static", "login_ok_currently_static",
                     "login_select_igg_id_static", "igg_login_exit_static",
                     "game_login_last_login_static",
                     "start_expire_ok_static", "start_expire_more_static"):
            if self._locate(name):
                return name
        return "unknown"

    # ── Actions ────────────────────────────────────────────────────────
    def _dismiss_expired(self) -> bool:
        for name in ("start_expire_ok_static", "start_expire_more_static"):
            r = self._locate(name)
            if r:
                self._session.click(r.cx, r.cy)
                return True
        return False

    def _open_browser(self) -> bool:
        r = self._locate("game_login_igg_account")
        if r:
            self._session.click(r.cx, r.cy)
            return True
        return False

    def _fill_and_submit(self, email: str, password: str) -> bool:
        eye = None
        for t in EYE_TEMPLATES:
            r = self._locate(t)
            if r:
                eye = (r.cx, r.cy)
                break
        if eye is None:
            return False
        _, ey = eye
        email_pos = (EMAIL_X, ey - EMAIL_Y_ABOVE_EYE)
        pass_pos = (EMAIL_X, ey)
        login_pos = (EMAIL_X, ey + LOGIN_Y_BELOW_EYE)
        if not _type(self._prefix, self._display, email, *email_pos):
            return False
        if not _type(self._prefix, self._display, password, *pass_pos):
            return False
        self._session.click(*eye)
        _wait(self._session, 1)
        self._session.click(*eye)
        self._session.click(*login_pos)
        return True

    def _click_continue(self) -> bool:
        self._session.click(500, 300)
        return True

    def _click_select_id(self) -> bool:
        self._session.click(350, 165)
        return True

    def _click_confirm_ok(self) -> bool:
        self._session.click(700, 560)
        return True

    # ── Main loop ──────────────────────────────────────────────────────
    def run(self, email: str, password: str) -> str:
        for _ in range(20):
            state = self._detect_state()
            if state == "in_game":
                return self._gw.identify(self._session) or "in_game"
            if not self._confirm(state):
                return "cancelled"

            if state == "start_expire_ok_static" or state == "start_expire_more_static":
                if not self._dismiss_expired():
                    return "error"
            elif state == "game_login_last_login_static":
                if not self._open_browser():
                    return "error"
            elif state == "igg_login_exit_static":
                if not self._fill_and_submit(email, password):
                    return "error"
            elif state == "login_ok_currently_static":
                self._click_continue()
            elif state == "login_select_igg_id_static":
                self._click_select_id()
            elif state == "login_confirm_igg_id_static":
                self._click_confirm_ok()
            elif state == "unknown":
                # Last resort: location-identifier recovery via Navigator.
                from gt_spector.navigator import Navigator
                nav = Navigator(self._gw, self._locator, self._session)
                nav._recover_esc()
            _wait(self._session)
        return "timeout"


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

    Runs the state machine until an in-game screen is reached. Returns the
    final screen name, or "cancelled"/"error"/"timeout".
    """
    return LoginStateMachine(
        session, gw, locator, prefix, display, confirm=confirm,
    ).run(email, password)


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
    return login(email, password, session, gw, locator, prefix, display, confirm=confirm)


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
