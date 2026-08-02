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

import yaml

logger = logging.getLogger(__name__)

DEFAULT_YAML = Path(__file__).parent / "game_world.yaml"


def _pixel_in_range(rgb: tuple[int, int, int], fp: list[int]) -> bool:
    x, y, r0, r1, g0, g1, b0, b1 = fp
    r, g, b = rgb
    return r0 <= r <= r1 and g0 <= g <= g1 and b0 <= b <= b1


class GameWorld:
    def __init__(self, path: Path = DEFAULT_YAML) -> None:
        self.path = path
        with open(path) as f:
            self.data = yaml.safe_load(f)
        self.locations = self.data.get("locations", {})
        self.screens = self.data.get("screens", {})
        self.zones = self.data.get("zones", {})
        self.map_levels = self.data.get("map_levels", {})
        self.navigation = self.data.get("navigation", {})
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
    def identify(self, session) -> str | None:
        """Return the screen name whose fingerprint fully matches, else None."""
        for name, spec in self.screens.items():
            fp = spec.get("fingerprint")
            if not fp:
                continue
            if self._matches(session, fp):
                return name
        return None

    def _matches(self, session, fingerprint: list[list[int]]) -> bool:
        try:
            for entry in fingerprint:
                if not _pixel_in_range(session.get_pixel(entry[0], entry[1]), entry):
                    return False
            return True
        except Exception:
            return False

    def map_level(self, session) -> str | None:
        """Return 'world_map' or 'world_map_regional' via minimap discriminator."""
        for name, spec in self.map_levels.items():
            fp = spec.get("fingerprint")
            if fp and self._matches(session, fp):
                return name
        return None

    # ── Actions ─────────────────────────────────────────────────────────────
    def click(self, session, screen: str, name: str) -> bool:
        pos = self.loc(screen, name)
        if pos is None:
            logger.warning("No location %s on screen %s", name, screen)
            return False
        session.click(*pos)
        return True

    def navigate(self, session, target: str, screen: str | None = None) -> bool:
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
        node = found
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()

        current = screen
        for nxt in path[1:]:
            action = edges[current][nxt]
            if action.get("action") == "click":
                self.click(session, current, action["location"])
            elif action.get("action") == "zoom_out":
                session.scroll(5, 4)
            elif action.get("action") == "zoom_in":
                session.scroll(-5, 4)
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
    def explore(self, session) -> None:
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
