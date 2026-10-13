from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

MIN_SETTLE = 0.15
MAX_SETTLE_TRIES = 15
MAX_ESC = 3
# Consecutive identical identifications required for _settle to accept a
# landing screen. Screen transitions animate; identify() can briefly match
# a wrong screen (e.g. avatar_menu opening flashes a frame that matches
# world_map via the avatar template). Requiring stability avoids treating a
# mid-animation frame as the landing screen, which otherwise recomputes the
# route from a ghost screen and loops (e.g. shelter_view <-> world_map).
STABLE_TRIES = 2


class Navigator:
    def __init__(self, gw: Any, locator: Any, session: Any,
                 trace: Callable[[str], None] | None = None) -> None:
        self._gw = gw
        self._locator = locator
        self._session = session
        self._trace = trace or (lambda msg: None)

    def _report(self, msg: str) -> None:
        self._trace(msg)

    def route_to(self, target: str, screen: str | None = None) -> list[str] | None:
        """BFS path from `screen` (default: identify) to `target`. No movement."""
        if screen is None:
            screen = self._gw.identify(self._session)
            if screen is None:
                return None
        if screen == target:
            return [screen]
        edges = self._gw.navigation
        prev: dict[str, str | None] = {screen: None}
        queue = deque([screen])
        found: str | None = None
        while queue:
            cur = queue.popleft()
            if cur == target:
                found = cur
                break
            for nxt in edges.get(cur, {}):
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        if found is None:
            return None
        path = []
        node: str | None = found
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        return path

    def _settle(self, source_screen: str) -> str | None:
        """Wait for the screen to change away from `source_screen` and hold.

        Poll identify() at least every MIN_SETTLE seconds, up to
        MAX_SETTLE_TRIES times. The first poll that returns a screen other
        than `source_screen` is remembered; it is only accepted once the same
        screen has been observed for STABLE_TRIES consecutive polls (so a
        single mid-animation frame that flashes a wrong screen, e.g.
        avatar_menu -> world_map via the shared avatar template, is not
        treated as the landing screen). Returns the stable screen, or None if
        it never settled.
        """
        candidate: str | None = None
        candidate_count = 0
        for _ in range(MAX_SETTLE_TRIES):
            time.sleep(MIN_SETTLE)
            self._session.refresh()
            current: str | None = self._gw.identify(self._session)
            if current is None or current == source_screen:
                candidate = None
                candidate_count = 0
                continue
            if current == candidate:
                candidate_count += 1
                if candidate_count >= STABLE_TRIES:
                    return current
            else:
                candidate = current
                candidate_count = 1
        return candidate if candidate_count >= STABLE_TRIES else None

    def _recover_esc(self) -> str | None:
        """ESC up to MAX_ESC times, re-identifying after each."""
        for _ in range(MAX_ESC):
            self._session.key_press("Escape")
            time.sleep(MIN_SETTLE)
            self._session.refresh()
            current: str | None = self._gw.identify(self._session)
            if current is not None:
                return current
        return None

    def goto(self, target: str) -> str | None:
        """Navigate to `target`. Returns target on success, else the stuck
        screen or None if no path exists."""
        current: str | None = self._gw.identify(self._session)
        if current == target:
            return target
        if current is None:
            current = self._recover_esc()
            if current is None:
                return None
        if current == "unknown_screen_with_back_button":
            from gt_spector.popups import exit_popups

            if exit_popups(self._session, self._locator, current):
                time.sleep(0.5)
                self._session.refresh()
                current = self._gw.identify(self._session)
                if current == target:
                    return target

        for _ in range(MAX_ESC + 1):
            if self._is_esc_advance(current):
                pressed = self._do_esc_advance(current)
                self._report(f"esc-advance: {current} -> {pressed}")
                current = pressed
                if current is None:
                    return None
                if current == target:
                    return target
                continue  # recompute route from the landing screen
            path = self.route_to(target, screen=current)
            if path is None:
                return None
            if len(path) == 1:  # already there
                return target

            for nxt in path[1:]:
                prev = current
                self._report(f"hop {prev} -> {nxt}")
                ok = self._gw._resolve_hop(self._session, current, nxt)
                if not ok:
                    return current
                landed = self._settle(current)
                self._report(f"landed: {landed}")
                if landed == nxt:
                    current = nxt
                elif landed is not None and landed != current:
                    # Different known screen: recompute route from here.
                    current = landed
                    self._report(f"recompute route from {current}")
                    break
                else:
                    # Screen didn't change or is unknown: ESC + recompute.
                    recovered = self._recover_esc()
                    if recovered is None:
                        return current
                    self._report(f"ESC recovery: -> {recovered}")
                    current = recovered
                    break
            if self._gw.identify(self._session) == target:
                return target
        return current

    def _is_esc_advance(self, screen: str | None) -> bool:
        """True if `screen` is an ESC-advance screen (unknown next screen).

        Screens marked `advance: esc` in the game world (e.g. startup Norah
        story) progress via a single ESC to a screen that isn't known until
        it appears. The caller re-identifies and recomputes the route from
        wherever it lands.
        """
        if screen is None:
            return False
        spec = self._gw.screens.get(screen, {})
        if isinstance(spec, dict):
            return spec.get("advance") == "esc"
        return False

    def _do_esc_advance(self, source: str) -> str | None:
        """Press ESC on an advance screen and return the resulting screen.

        Polls identify() until the screen changes away from the advance
        screen (the transition can take a moment and may land on any known
        screen). Returns the new screen, or None if it never changes.
        """
        self._session.key_press("Escape")
        for _ in range(MAX_SETTLE_TRIES):
            time.sleep(MIN_SETTLE)
            self._session.refresh()
            current: str | None = self._gw.identify(self._session)
            if current is not None and current != source:
                return current
        return self._gw.identify(self._session)
