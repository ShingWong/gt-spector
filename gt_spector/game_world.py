"""Game world knowledge + scene identification for Doomsday: Last Survivors.

Loads `game_world.yaml` and provides:
  - identify(session) -> screen name or None (deterministic pixel fingerprints)
  - loc(screen, name) -> (x, y) or None
  - click(session, screen, name)
  - navigate(session, target) via the screen graph
  - explore(session): interactive helper to register unknown screens
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

DEFAULT_YAML = Path(__file__).parent / "game_world.yaml"


def _pixel_in_range(rgb: tuple[int, int, int], fp: list[int]) -> bool:
    _, _, r0, r1, g0, g1, b0, b1 = fp
    r, g, b = rgb
    return r0 <= r <= r1 and g0 <= g <= g1 and b0 <= b <= b1


class GameWorld:
    def __init__(self, path: Path = DEFAULT_YAML) -> None:
        self.path = path
        with open(path) as f:
            self.data: dict[str, Any] = yaml.safe_load(f)
        self.locations: dict[str, Any] = self.data.get("locations", {})
        self.screens: dict[str, Any] = self.data.get("screens", {})
        self.zones: dict[str, Any] = self.data.get("zones", {})
        self.map_levels: dict[str, Any] = self.data.get("map_levels", {})
        self.navigation: dict[str, Any] = self.data.get("navigation", {})
        self._locator: Any = None
        # Index locations by screen for fast lookup.
        self._loc_index: dict[str, dict[str, tuple[int, int]]] = {}
        for name, info in self.locations.items():
            for scr in info.get("screens", []):
                self._loc_index.setdefault(scr, {})[name] = (info["x"], info["y"])

    # ── Lookup ──────────────────────────────────────────────────────────────
    def screen_names(self) -> list[str]:
        return list(self.screens)

    def location_names(self, screen: str) -> list[str]:
        return list(self._loc_index.get(screen, {}))

    def loc(self, screen: str, name: str) -> tuple[int, int] | None:
        return self._loc_index.get(screen, {}).get(name)

    def zones_for(self, screen: str) -> list[str]:
        return list(self.zones)

    # ── Identification ──────────────────────────────────────────────────────
    def identify(self, session: Any) -> str | None:
        """Return the screen name whose fingerprint/templates match, else None.

        A screen matches when ALL its template locators find (score >= their
        threshold), OR all its pixel-fingerprint probes match. Template-based
        detection is preferred (robust to brightness/overlay changes); pixel
        probes are the fallback.
        """
        if self._locator is None:
            self._ensure_locator()
        for name, spec in self.screens.items():
            if spec.get("templates"):
                if self._locator is not None and self._templates_match(session, spec["templates"]):
                    return name
                continue
            fp = spec.get("fingerprint")
            if not fp:
                continue
            if self._matches(session, fp):
                return name
        return None

    def _ensure_locator(self) -> None:
        from gt_spector.locator import Locator

        self._locator = Locator()

    def _templates_match(self, session: Any, templates: list[str]) -> bool:
        for tname in templates:
            r = self._locator.find(session.frame, tname)
            if not r.found:
                return False
        return True

    def _matches(self, session: Any, fingerprint: list[list[int]]) -> bool:
        try:
            for entry in fingerprint:
                if not _pixel_in_range(session.get_pixel(entry[0], entry[1]), entry):
                    return False
            return True
        except Exception:  # noqa: BLE001
            return False

    def map_level(self, session: Any) -> str | None:
        """Return 'world_map' or 'world_map_regional' via minimap discriminator."""
        for name, spec in self.map_levels.items():
            fp = spec.get("fingerprint")
            if fp and self._matches(session, fp):
                return name
        return None

    # ── Actions ─────────────────────────────────────────────────────────────
    def click(self, session: Any, screen: str, name: str) -> bool:
        pos = self.loc(screen, name)
        if pos is None:
            logger.warning("No location %s on screen %s", name, screen)
            return False
        session.click(*pos)
        return True

    def set_locator(self, locator: Any) -> None:
        self._locator = locator

    def _resolve_hop(self, session: Any, screen: str, target: str) -> bool:
        action = self.navigation.get(screen, {}).get(target)
        if action is None:
            return False
        if action.get("action") == "click":
            self.click(session, screen, action["location"])
            return True
        if action.get("action") == "locate":
            if self._locator is None:
                return False
            res = self._locator.find(session.frame, action["name"])
            if not res.found:
                return False
            session.click(res.cx, res.cy)
            return True
        if action.get("action") == "esc":
            session.key_press("Escape")
            return True
        if action.get("action") == "zoom_out":
            session.scroll(5, 4)
            return True
        if action.get("action") == "zoom_in":
            session.scroll(-5, 4)
            return True
        return False

    def navigate(self, session: Any, target: str, screen: str | None = None) -> bool:
        """Walk the navigation graph from current `screen` to `target`.

        Returns True if target screen reached (via identify()), else False.
        BFS over the graph to keep paths short; performs the recorded action
        (click a location, or zoom) at each hop, re-identifying after each.
        """
        if screen is None:
            screen = self.identify(session)
            if screen is None:
                logger.warning("Cannot navigate: current screen unknown")
                return False
        if screen == target:
            return True

        from collections import deque

        edges = self.navigation
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
            logger.warning("No path from %s to %s", screen, target)
            return False

        # Reconstruct path and execute each hop.
        path = []
        node: str | None = found
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()

        current = screen
        for nxt in path[1:]:
            if not self._resolve_hop(session, current, nxt):
                logger.warning("Hop %s -> %s failed; aborting navigation", current, nxt)
                return False
            import time

            time.sleep(2.5)
            session.refresh()
            if self.identify(session) == nxt:
                current = nxt
            else:
                logger.warning("Hop %s -> %s did not land; re-identifying", current, nxt)
                current = self.identify(session) or current
        return self.identify(session) == target

    # ── Interactive exploration ─────────────────────────────────────────────
    def explore(self, session: Any) -> None:
        """Ask the user to identify the current unknown screen and its clicks."""
        name = input("What screen is this? (snake_case) > ").strip()
        while True:
            desc = input("Short description > ").strip()
            if desc:
                break
        self.screens[name] = {"description": desc, "fingerprint": []}
        print(f"Screen '{name}' registered with no fingerprint yet.")
        while True:
            loc_input = input("Click point 'name x y' (or blank to finish) > ").strip()
            if not loc_input:
                break
            parts = loc_input.split()
            if len(parts) != 3:
                print("Expected: name x y")
                continue
            ln, x, y = parts
            self.locations[ln] = {"x": int(x), "y": int(y), "screens": [name]}
            self._loc_index.setdefault(name, {})[ln] = (int(x), int(y))
        self.save()
        print("Saved. You may add a fingerprint later via fingerprint_capture.")

    def save(self) -> None:
        self.data["locations"] = self.locations
        self.data["screens"] = self.screens
        with open(self.path, "w") as f:
            yaml.safe_dump(self.data, f, sort_keys=False)
