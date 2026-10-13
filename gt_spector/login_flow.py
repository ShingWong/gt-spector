"""IGG login: state-machine navigation + verified browser login.

The path to the IGG browser login (expired-session dialog -> game login
page -> browser) is driven by a locator-based state machine that adapts to
whatever screen is present (the page layout shifts between renders). Once on
the browser login form, the proven login() routine takes over and completes
the login (eye-derived field positions, sendtext.exe typing, continue/select-
ID/confirm). login() is the exact code verified on bot05 — not rewritten.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gt_spector import typing
from gt_spector.game_world import GameWorld

EMAIL_X = 365
EYE_TEMPLATES = ("igg_login_eye2_static", "login_eye_static")
EMAIL_Y_ABOVE_EYE = 100
LOGIN_Y_BELOW_EYE = 70
_EYE_POLL_INTERVAL = 0.5
_EYE_POLL_TIMEOUT = 20.0
FIELD_FOCUS_WAIT = 1.0
POST_TYPE_WAIT = 0.5
PAGE_SETTLE_WAIT = 1.5
CONTINUE = (500, 300)
SELECT_ID = (350, 165)
OK = (700, 560)

# Reliable in-game template (login succeeded). region_overview/avatar match
# spuriously on the login page, so they are excluded. In-game detection
# relies on region_static (shelter_view's region icon).
IN_GAME_TEMPLATES = ("region_static",)


def _window_click(session: Any, x: int, y: int) -> bool:
    session.click(x, y)
    return True


def _type(session: Any, prefix: str, display: str, text: str, x: int, y: int) -> bool:
    # Click the field via xdotool (the browser registers xdotool clicks), then
    # send text via the wine helper (text-only, no click — the click already
    # focused the field, and the helper re-clicking would steal focus). The
    # embedded browser responds slowly to input, so wait long enough after the
    # click for the field to accept typing before sending text.
    if text:
        session.click(x, y)
        time.sleep(FIELD_FOCUS_WAIT)
        ok = typing.type_text(prefix, display, f"{{CtrlA}}{text}")
        time.sleep(POST_TYPE_WAIT)
        return ok
    session.click(x, y)
    return True


def _wait(session: Any, seconds: float = 4.0) -> None:
    time.sleep(seconds)
    session.refresh()


def _find_eye(locator: Any, session: Any) -> tuple[int, int] | None:
    """Locate the password-reveal eye icon (position varies by page render).

    The browser's X button renders before the form's eye icon, so a one-shot
    check misses it. Poll (condition-based wait) until the eye renders or the
    timeout elapses.
    """
    if locator is None:
        from gt_spector.locator import Locator
        locator = Locator()
    deadline = time.monotonic() + _EYE_POLL_TIMEOUT
    while True:
        session.refresh()
        for name in EYE_TEMPLATES:
            r = locator.find(session.frame, name)
            if r.found:
                return (r.cx, r.cy)
        if time.monotonic() >= deadline:
            return None
        time.sleep(_EYE_POLL_INTERVAL)


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
    # The browser is still settling when the eye first renders; wait for it
    # to finish laying out before the first field interaction, or the email
    # click can land before the field is interactive.
    time.sleep(PAGE_SETTLE_WAIT)
    session.refresh()
    email_pos = (EMAIL_X, ey - EMAIL_Y_ABOVE_EYE)
    pass_pos = (EMAIL_X, ey)
    login_pos = (EMAIL_X, ey + LOGIN_Y_BELOW_EYE)

    steps: list[tuple[str, Callable[[], bool]]] = [
        ("enter email", lambda: _type(session, prefix, display, email, *email_pos)),
        ("enter password", lambda: _type(session, prefix, display, password, *pass_pos)),
        ("reveal password", lambda: _type(session, prefix, display, "", *eye)),
        ("hide password", lambda: _type(session, prefix, display, "", *eye)),
        ("submit login", lambda: _type(session, prefix, display, "", *login_pos)),
        ("continue after login", lambda: _type(session, prefix, display, "", *CONTINUE)),
        ("select id", lambda: _type(session, prefix, display, "", *SELECT_ID)),
        ("confirm ok", lambda: _type(session, prefix, display, "", *OK)),
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


class LoginStateMachine:
    """Drive navigation to the IGG browser, then hand off to login().

    States are detected by locating templates. The browser login form
    (igg_login) delegates to the verified login() routine. Unknown states
    fall back to the Navigator's ESC recovery.
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

    def _reattach(self) -> None:
        """Reconnect the SHM readback after the game restarts its browser.

        Clicking OK on the expired-login dialog reinitializes the embedded
        browser, which tears down and recreates the DXVK offscreen swapchain.
        The old ShmScreen keeps a stale mmap/counter, so refresh() returns the
        dead pre-restart frame forever. Re-attaching (fresh ShmScreen + Input)
        re-opens the shm file and sees the real next screen (game_login).
        """
        time.sleep(3)
        self._session.attach(
            self._display,
            source=f"shm://{self._display.lstrip(':')}",
        )

    def _locate_poll(self, name: str, timeout: float = _EYE_POLL_TIMEOUT) -> Any | None:
        """Locate `name`, polling until it renders or the timeout elapses.

        Pages render asynchronously (the IGG account button, the browser form),
        so a one-shot locate misses elements that are still loading. Mirrors
        _find_eye's condition-based wait.
        """
        deadline = time.monotonic() + timeout
        while True:
            r = self._locate(name)
            if r is not None:
                return r
            if time.monotonic() >= deadline:
                return None
            time.sleep(_EYE_POLL_INTERVAL)

    def _detect_state(self) -> str:
        if self._in_game():
            return "in_game"
        # glory_league_event is fingerprint-only (no templates), so it must be
        # detected via identify() before the template checks below.
        if self._gw.identify(self._session) == "glory_league_event":
            return "glory_league_event"
        for name in ("login_current_static", "igg_login_exit_static",
                     "game_login_last_login_static",
                     "start_expire_ok_static", "start_expire_more_static",
                     "another_login_disconnect_detect_static"):
            if self._locate(name):
                return name
        return "unknown"

    def run(self, email: str, password: str, force_account: bool = False) -> str:
        for _ in range(20):
            state = self._detect_state()
            if state == "in_game":
                if not force_account:
                    return self._gw.identify(self._session) or "in_game"
                # force_account: the auto-logged-in session is not trusted
                # (it may be the master account). Re-login the intended
                # account through the browser.
                from gt_spector.navigator import Navigator
                nav = Navigator(self._gw, self._locator, self._session)
                if nav.goto("change_account") != "change_account":
                    return "error"
                _wait(self._session)
                self._session.click(735, 262)  # IGG account button
                _wait(self._session, 6)
                return login(
                    email, password,
                    self._session, self._gw, self._locator,
                    self._prefix, self._display,
                    confirm=self._confirm,
                )
            if not self._confirm(state):
                return "cancelled"

            if state in ("start_expire_ok_static", "start_expire_more_static"):
                r = self._locate(state)
                if r is None:
                    return "error"
                self._session.click(r.cx, r.cy)
                # Dismissing the expired dialog restarts the embedded browser,
                # which detaches the DXVK SHM readback. Reconnect before the
                # next detect, or we read the dead pre-restart frame and the
                # flow never sees the real game_login page.
                self._reattach()
            elif state == "another_login_disconnect_detect_static":
                # Another device is logged in with this ID. ESC dismisses the
                # popup to the game login page; the loop re-detects and runs
                # the login module.
                self._session.key_press("Escape")
            elif state == "glory_league_event":
                # Glory League splash after login; click GO to continue to the
                # browser login page (current-account prompt). The GO button is
                # a fixed yaml location (no locator template), so use gw.loc().
                pos = self._gw.loc("glory_league_event", "glory_league_go")
                if pos is None:
                    return "error"
                self._session.click(*pos)
            elif state == "login_current_static":
                # A previous session is remembered ("currently logged in");
                # click Use-another-account to reach the real login form.
                r = self._locate_poll("login_use_another_static")
                if r is None:
                    return "error"
                self._session.click(r.cx, r.cy)
            elif state == "game_login_last_login_static":
                # The IGG account button renders after the last-login text;
                # poll until it appears, then click to open the browser.
                r = self._locate_poll("game_login_igg_account")
                if r is None:
                    return "error"
                self._session.click(r.cx, r.cy)
            elif state == "igg_login_exit_static":
                # Browser login form reached: use the verified login().
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
    force_account: bool = False,
) -> str:
    """Complete login from the expired-session / unlinked-account entry.

    When `force_account` is set (provisioning), an auto-logged-in session is
    not trusted — the intended account is always logged in via the browser.
    """
    return LoginStateMachine(
        session, gw, locator, prefix, display, confirm=confirm,
    ).run(email, password, force_account=force_account)


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
