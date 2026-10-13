import os
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

WINE_BIN = "/opt/wine-proton/bin/wine"
BASE_DIR = "/home/swong/dls/wineprefix_bots"


class BotState(Enum):
    OFFLINE = "Offline"
    STARTING = "Starting"
    RUNNING = "Running"
    PAUSED = "Paused"
    ERROR = "Error"


@dataclass
class Bot:
    name: str
    account: str = ""
    state: BotState = BotState.OFFLINE
    pid: int | None = None
    prefix: str = ""
    display: int = 9
    shm_id: int = 9
    script_paused: bool = False
    xvfb_pid: int | None = None
    crash_count: int = 0
    intervention_count: int = 0

    @property
    def game_dir(self) -> str:
        base = os.path.join(
            self.prefix, "drive_c", "Program Files",
            "DoomsdayLastSurvivors"
        )
        # Prefer the newest installed version dir, fall back to 1.59.0.
        try:
            versions = sorted(
                d for d in os.listdir(base)
                if d.startswith("Doomsday_") and os.path.isdir(os.path.join(base, d))
            )
            if versions:
                return os.path.join(base, versions[-1])
        except OSError:
            pass
        return os.path.join(base, "Doomsday_1.59.0")

    @property
    def log_path(self) -> str:
        return os.path.join(
            self.prefix, "drive_c", "users", "steamuser",
            "AppData", "LocalLow", "IGG", "Doomsday Last Survivors",
            "Player.log"
        )

    @property
    def shm_path(self) -> str:
        return f"/dev/shm/gt-spector-{self.shm_id}-frame"


class BotManager:
    def __init__(self) -> None:
        self.bots: list[Bot] = []

    def add(self, bot: Bot) -> None:
        self.bots.append(bot)

    def get(self, name: str) -> Bot | None:
        for b in self.bots:
            if b.name == name:
                return b
        return None

    def reload_from_prefixes(self) -> None:
        """Drop all tracked bots and re-scan the prefixes directory.

        Used after provisioning a new prefix (which creates a directory the
        startup scan did not see), so the new bot can be found by name.
        """
        self.bots = []
        self.load_from_prefixes()

    def load_from_prefixes(self) -> None:
        if not os.path.exists(BASE_DIR):
            return
        for entry in sorted(os.listdir(BASE_DIR)):
            prefix = os.path.join(BASE_DIR, entry)
            if not os.path.isdir(prefix) or not os.path.exists(os.path.join(prefix, "drive_c")):
                continue
            bot = Bot(name=entry, prefix=prefix)
            try:
                n = int(entry.replace("bot", ""))
                bot.display = 9 + n
                bot.shm_id = bot.display
            except ValueError:
                bot.display = 9
                bot.shm_id = 9
            self._refresh_state(bot)
            self.bots.append(bot)

    def _refresh_state(self, bot: Bot) -> None:
        if bot.state == BotState.ERROR:
            return
        if bot.pid and self._pid_alive(bot.pid):
            bot.state = BotState.RUNNING
            return
        game_pid = self._find_game_pid(bot)
        if game_pid is not None:
            bot.pid = game_pid
            bot.state = BotState.RUNNING
            return
        if bot.xvfb_pid and self._pid_alive(bot.xvfb_pid):
            # Xvfb alone is not a running game; the game may have crashed
            # or exited after the display started. Report transitional so the
            # console allows a start/stop.
            bot.pid = None
            bot.state = BotState.STARTING
            return
        bot.state = BotState.OFFLINE
        bot.pid = None

    def _find_game_pid(self, bot: Bot) -> int | None:
        prefix = bot.prefix.encode()
        for pid_str in os.listdir("/proc/"):
            if not pid_str.isdigit():
                continue
            try:
                with open(f"/proc/{pid_str}/cmdline", "rb") as f:
                    cmdline = f.read()
                if b"Doomsday.exe" not in cmdline or b"start.exe" in cmdline:
                    continue
                with open(f"/proc/{pid_str}/environ", "rb") as f:
                    env = f.read()
                if b"WINEPREFIX=" + prefix + b"\x00" in env:
                    return int(pid_str)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        return None

    def find_game_pid_by_display(self, display: int) -> int | None:
        disp = f":{display}".encode()
        for pid_str in os.listdir("/proc/"):
            if not pid_str.isdigit():
                continue
            try:
                with open(f"/proc/{pid_str}/cmdline", "rb") as f:
                    cmdline = f.read()
                if b"Doomsday.exe" not in cmdline or b"start.exe" in cmdline:
                    continue
                with open(f"/proc/{pid_str}/environ", "rb") as f:
                    env = f.read()
                if b"DISPLAY=" + disp + b"\x00" in env:
                    return int(pid_str)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        return None

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _find_window(self, display: int) -> str | None:
        r = subprocess.run(
            ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
            capture_output=True, text=True, env={"DISPLAY": f":{display}"},
            timeout=5, check=False,
        )
        wins = r.stdout.strip().split()
        return wins[0] if wins else None

    def start_xvfb(self, bot: Bot) -> None:
        display = bot.display
        subprocess.run(["fuser", "-k", f"/tmp/.X11-unix/X{display}"],
                       capture_output=True, timeout=5, check=False)
        subprocess.run(["fuser", "-k", f"/tmp/.X{display}-lock"],
                       capture_output=True, timeout=5, check=False)
        for p in (f"/tmp/.X{display}-lock", f"/tmp/.X11-unix/X{display}"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        proc = subprocess.Popen(
            ["Xvfb", f":{display}", "-screen", "0", "1152x864x24",
             "-nolisten", "tcp", "-noreset", "-ac"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        bot.xvfb_pid = proc.pid
        time.sleep(2)
        # Verify it's running
        try:
            subprocess.run(["xdpyinfo", "-display", f":{display}"],
                           capture_output=True, timeout=3, check=True)
        except subprocess.CalledProcessError:
            raise RuntimeError(f"Xvfb :{display} failed to start")

    def start_game(self, bot: Bot) -> None:
        if bot.state == BotState.RUNNING:
            return
        self.start_xvfb(bot)
        bot.state = BotState.STARTING

        os.makedirs(os.path.dirname(bot.log_path), exist_ok=True)
        shm_path = f"/dev/shm/gt-spector-{bot.shm_id}-frame"
        if os.path.exists(shm_path):
            os.remove(shm_path)

        env = {**os.environ,
               "DISPLAY": f":{bot.display}",
               "WINEPREFIX": bot.prefix,
               "GT_SPECTOR_ENABLE_READBACK": "1",
               "GT_SPECTOR_SHM_ID": str(bot.shm_id),
               # Required for the patched DXVK offscreen swapchain (see
               # README "Required env vars" + src/dxvk-patch). Missing these
               # leaves the GPU idle / falls back to software rendering.
               "DXVK_OFFSCREEN": "1",
               "DXVK_ASYNC": "1",
               "DXVK_WSI_DRIVER": "None",
               "MESA_GLSL_CACHE_DISABLE": "true",
               "vblank_mode": "0",
               # Per-bot DXVK state cache (shader pipeline cache). Stored
               # outside the (reflinked) game dir so it's writable and
               # isolated per bot; the mesa GPL cache shares compiled
               # pipelines across all bots.
               "DXVK_STATE_CACHE_PATH": os.path.join(bot.prefix, "dxvk-cache"),
        }
        proc = subprocess.Popen(
            [WINE_BIN, "Doomsday.exe",
             "-screen-width", "1152", "-screen-height", "864",
             "-fullscreen", "False", "-la"],
            cwd=bot.game_dir, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        bot.pid = proc.pid
        time.sleep(3)

    def _find_game_pids_by_display(self, display: int) -> list[int]:
        """All Doomsday.exe pids on a display (excludes start.exe wrappers)."""
        disp = f":{display}".encode()
        pids: list[int] = []
        for pid_str in os.listdir("/proc/"):
            if not pid_str.isdigit():
                continue
            try:
                with open(f"/proc/{pid_str}/cmdline", "rb") as f:
                    cmdline = f.read()
                if b"Doomsday.exe" not in cmdline or b"start.exe" in cmdline:
                    continue
                with open(f"/proc/{pid_str}/environ", "rb") as f:
                    env = f.read()
                if b"DISPLAY=" + disp + b"\x00" in env:
                    pids.append(int(pid_str))
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        return pids

    def stop_game(self, bot: Bot) -> None:
        """Kill every Doomsday.exe on the bot's display, then its Xvfb.

        The tracked `bot.pid` is a start.exe wrapper whose process group may
        not cover the real Doomsday.exe (it reparents to init). Killing only
        that group can leave a stale game running on the same display, which
        then competes for focus/rendering. So we kill all matching pids, then
        the Xvfb so a stale display can't look like a running game.
        """
        if bot.pid and self._pid_alive(bot.pid):
            os.killpg(os.getpgid(bot.pid), signal.SIGTERM)
            time.sleep(1)
        for pid in self._find_game_pids_by_display(bot.display):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        time.sleep(2)
        for pid in self._find_game_pids_by_display(bot.display):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        if bot.pid and self._pid_alive(bot.pid):
            os.killpg(os.getpgid(bot.pid), signal.SIGKILL)
        # Clean up the display so a stale Xvfb can't look like a running game.
        if bot.xvfb_pid and self._pid_alive(bot.xvfb_pid):
            try:
                os.killpg(os.getpgid(bot.xvfb_pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            bot.xvfb_pid = None
        bot.pid = None
        bot.state = BotState.OFFLINE

    def restart_game(self, bot: Bot) -> None:
        self.stop_game(bot)
        time.sleep(2)
        self.start_game(bot)

    def stop_all(self) -> None:
        for bot in self.bots:
            if bot.state != BotState.OFFLINE:
                self.stop_game(bot)
    def attach_viewer(self, bot: Bot) -> None:
        env = {"DISPLAY": ":0"}
        if bot.pid:
            env["GT_SPECTOR_GAME_PID"] = str(bot.pid)
        subprocess.Popen(
            ["/home/swong/dls/src/gt-spector/.venv/bin/python3", "-m", "gt_spector", "--session", f":{bot.display}"],
            env=env,
            cwd="/home/swong/dls/src/gt-spector",
        )

    # ── Stats ──────────────────────────────────────────────────────────
    _CARD = "/sys/class/drm/card1"

    def get_process_stats(self, bot: Bot) -> dict[str, Any] | None:
        pid = self._cached_game_pid(bot)
        if pid is None:
            return None
        return self._ps_stats([pid]).get(pid)

    def get_process_stats_many(self, bots: list[Bot]) -> dict[str, dict[str, Any]]:
        """Stats for many bots in one `ps` call (the console poll loop)."""
        pids = [p for p in (self._cached_game_pid(b) for b in bots) if p is not None]
        return self._ps_stats(pids)

    def _pid_stats_for(self, bot: Bot, stats_map: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        pid = self._cached_game_pid(bot)
        if pid is None:
            return None
        return stats_map.get(str(pid))

    def _ps_stats(self, pids: list[int]) -> dict[int, dict[str, Any]]:
        if not pids:
            return {}
        try:
            r = subprocess.run(
                ["ps", "-p", ",".join(str(p) for p in pids),
                 "-o", "pid=,%cpu=,%mem=,rss=", "--no-headers"],
                capture_output=True, text=True, timeout=5, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return {}
        out: dict[int, dict[str, Any]] = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
                out[pid] = {
                    "pid": pid,
                    "cpu_percent": float(parts[1]),
                    "mem_percent": float(parts[2]),
                    "rss_mb": int(parts[3]) // 1024,
                }
            except ValueError:
                continue
        return out

    def _cached_game_pid(self, bot: Bot) -> int | None:
        """Return the bot's Doomsday pid, scanning /proc only when needed.

        _find_game_pid scans every /proc entry (cmdline + environ per pid),
        which is ~120ms per call and dominates the console poll loop. Cache
        per prefix; revalidate cheaply via _pid_alive before rescanning.
        """
        cache = getattr(self, "_pid_cache", None)
        if cache is None:
            cache = {}
            object.__setattr__(self, "_pid_cache", cache)
        cached = cache.get(bot.prefix)
        if cached is not None and self._pid_alive(cached):
            return cached
        pid = self._find_game_pid(bot)
        if pid is not None:
            cache[bot.prefix] = pid
        return pid

    def get_gpu_stats(self) -> dict[str, Any]:
        card = self._CARD
        gpu_busy = 0.0
        vram_total = 0
        vram_used = 0
        try:
            with open(f"{card}/device/gpu_busy_percent") as f:
                gpu_busy = float(f.read().strip())
        except (FileNotFoundError, OSError, ValueError):
            pass
        try:
            with open(f"{card}/device/mem_info_vram_total") as f:
                vram_total = int(f.read().strip())
        except (FileNotFoundError, OSError, ValueError):
            pass
        try:
            with open(f"{card}/device/mem_info_vram_used") as f:
                vram_used = int(f.read().strip())
        except (FileNotFoundError, OSError, ValueError):
            pass
        return {"gpu_busy_percent": gpu_busy,
                "vram_total_mb": vram_total // 1048576,
                "vram_used_mb": vram_used // 1048576}

    def get_system_ram(self) -> dict[str, Any]:
        import re
        try:
            with open("/proc/meminfo") as f:
                data = f.read()
            m_total = re.search(r"MemTotal:\s+(\d+)", data)
            m_avail = re.search(r"MemAvailable:\s+(\d+)", data)
            total = int(m_total.group(1)) // 1024 if m_total else 0
            available = int(m_avail.group(1)) // 1024 if m_avail else 0
            st = re.search(r"SwapTotal:\s+(\d+)", data)
            sf = re.search(r"SwapFree:\s+(\d+)", data)
            swap_total = int(st.group(1)) // 1024 if st else 0
            swap_free = int(sf.group(1)) // 1024 if sf else 0
            return {"mem_total_mb": total, "mem_used_mb": total - available,
                    "swap_total_mb": swap_total, "swap_used_mb": swap_total - swap_free}
        except (FileNotFoundError, AttributeError, OSError, ValueError):
            return {"mem_total_mb": 0, "mem_used_mb": 0,
                    "swap_total_mb": 0, "swap_used_mb": 0}
