"""Bot health monitoring: screen detection, responsiveness, recovery."""

from __future__ import annotations

import struct
import subprocess
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import requests

from gt_spector import logs, settings


def _in_range(val: int, rng: tuple[int, int]) -> bool:
    return rng[0] <= val <= rng[1]


def detect_screen(frame: np.ndarray, nav_table: dict[str, Any]) -> str | None:
    """Return the first state whose fingerprints all match the frame, else None."""
    states: dict[str, Any] = nav_table.get("states", {})
    for name, data in states.items():
        fps = data.get("fingerprints", [])
        if not fps:
            continue
        ok = True
        for fp in fps:
            try:
                x, y = int(fp["x"]), int(fp["y"])
                if not (0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]):
                    ok = False
                    break
                r, g, b = int(frame[y, x, 0]), int(frame[y, x, 1]), int(frame[y, x, 2])
                if not (_in_range(r, fp["r"]) and _in_range(g, fp["g"]) and _in_range(b, fp["b"])):
                    ok = False
                    break
            except (KeyError, TypeError, IndexError, ValueError):
                ok = False
                break
        if ok:
            return name
    return None


def frame_is_blank(frame: np.ndarray) -> bool:
    """True if the frame is uniform (all-near-black or all-white)."""
    if frame.size == 0:
        return True
    std = float(np.std(frame))
    return std < 0.5


VLM_INTERVAL = 10.0

STARTUP_GRACE = 60.0

MAX_RECOVERY_ATTEMPTS = 3

GPU_BUSY_MAX = 85.0


def _downscale(frame: np.ndarray, factor: int | None = None) -> np.ndarray:
    if factor is None:
        factor = settings.vlm_downscale()
    return frame[::factor, ::factor, :3]


def gpu_slot_free(gpu_stats: dict[str, Any]) -> bool:
    """True when the GPU has headroom for a VLM inference."""
    busy = gpu_stats.get("gpu_busy_percent", 0.0)
    try:
        return float(busy) < GPU_BUSY_MAX
    except (TypeError, ValueError):
        return True


def _parse_screen(content: str) -> str | None:
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("SCREEN:"):
            name = line.split(":", 1)[1].strip().upper()
            return name or None
    return None


class BotMonitor:
    def __init__(self, manager: Any, vlm: Any = None):
        self._manager = manager
        self._vlm = vlm
        self._last_shm_counter: dict[str, int] = {}
        self._last_vlm_check: dict[str, float] = {}
        self._started_at: dict[str, float] = {}
        self._seen_pid: dict[str, int | None] = {}
        self._recovery_attempts: dict[str, int] = {}

    def _read_counter(self, shm_path: str) -> int | None:
        try:
            with open(shm_path, "rb") as f:
                return int(struct.unpack("<Q", f.read(8))[0])
        except (FileNotFoundError, OSError, struct.error):
            return None

    def note_running(self, bot: Any, now: float) -> None:
        """Track when a bot's game process appeared; resets on pid change."""
        pid = bot.pid
        if pid != self._seen_pid.get(bot.name):
            self._started_at[bot.name] = now
            self._recovery_attempts.pop(bot.name, None)
        self._seen_pid[bot.name] = pid

    def check_responsiveness(self, bot: Any, now: float) -> bool:
        if now - self._started_at.get(bot.name, now) < STARTUP_GRACE:
            return True
        c0 = self._read_counter(bot.shm_path)
        if c0 is None:
            return False
        time.sleep(0.4)
        c1 = self._read_counter(bot.shm_path)
        if c1 is None:
            return False
        return c1 != c0

    def mark_crash(self, bot: Any) -> None:
        bot.crash_count += 1
        logs.log_bot(bot.name, f"CRASH restart (count={bot.crash_count})")

    def mark_intervention(self, bot: Any) -> None:
        bot.intervention_count += 1
        logs.log_bot(bot.name, f"INTERVENTION recovery (count={bot.intervention_count})")

    def recover(self, bot: Any, run_script: Callable[[Any, Any], Any], script: Any) -> bool:
        """ESC-to-shelter, then re-run the script. Returns True on success."""
        self.mark_intervention(bot)
        self._recovery_attempts[bot.name] = self._recovery_attempts.get(bot.name, 0) + 1
        env = {"DISPLAY": f":{bot.display}"}
        wid = self._manager._find_window(bot.display) if self._manager else None
        if wid is None:
            try:
                r = subprocess.run(
                    ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
                    capture_output=True, text=True, env=env, timeout=5, check=False,
                )
                wid = r.stdout.strip().split()[0] if r.stdout.strip() else None
            except (OSError, subprocess.SubprocessError):
                wid = None
        if wid:
            for _ in range(8):
                subprocess.run(["xdotool", "key", "--window", wid, "Escape"],
                               capture_output=True, env=env, timeout=5, check=False)
                time.sleep(2)
        run_script(bot, script)
        return True

    def recoveries_left(self, bot: Any) -> bool:
        return self._recovery_attempts.get(bot.name, 0) < MAX_RECOVERY_ATTEMPTS

    def recovery_succeeded(self, bot: Any) -> None:
        self._recovery_attempts.pop(bot.name, None)

    def mark_error(self, bot: Any, runner: Any) -> None:
        """Log the fatal state and stop the script; caller sets bot.state."""
        logs.log_bot(bot.name, "ERROR: recovery failed, script stopped")
        stop = getattr(runner, "stop", None)
        if callable(stop):
            stop()

    def should_vlm_check(self, bot: Any, now: float) -> bool:
        last = self._last_vlm_check.get(bot.name, -1e9)
        if (now - last) >= settings.vlm_interval():
            self._last_vlm_check[bot.name] = now
            return True
        return False

    def classify_frame(self, frame: np.ndarray, display: int) -> str | None:
        if self._vlm is None:
            return None
        try:
            small = _downscale(np.asarray(frame))
            result = self._vlm.analyze_frame(small, prompt=(
                "Identify this Doomsday: Last Survivors screen in ONE phrase. "
                "Format: SCREEN: <name>"), max_tokens=200)
            content = result["choices"][0]["message"]["content"]
            return _parse_screen(content)
        except (KeyError, IndexError, TypeError, AttributeError, RuntimeError, OSError, ValueError,
                requests.exceptions.RequestException):
            return None

    def vlm_tick(self, frame: np.ndarray, bot: Any, now: float) -> str | None:
        if not self.should_vlm_check(bot, now):
            return None
        return self.classify_frame(frame, bot.display)
