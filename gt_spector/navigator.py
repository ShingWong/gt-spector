from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

MIN_SETTLE = 0.15
MAX_SETTLE_TRIES = 15
MAX_ESC = 3


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
        """Wait for the screen to change away from `source_screen`.

        Poll identify() at least every MIN_SETTLE seconds, up to
        MAX_SETTLE_TRIES times. Returns the new screen, or None if it never
        changed.
        """
        for _ in range(MAX_SETTLE_TRIES):
            time.sleep(MIN_SETTLE)
            self._session.refresh()
            current: str | None = self._gw.identify(self._session)
            if current is not None and current != source_screen:
                return current
        return None

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

        for _ in range(MAX_ESC + 1):
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
