import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

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

    @property
    def game_dir(self) -> str:
        return os.path.join(
            self.prefix, "drive_c", "Program Files",
            "DoomsdayLastSurvivors", "Doomsday_1.59.0"
        )

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
    def __init__(self):
        self.bots: list[Bot] = []

    def add(self, bot: Bot) -> None:
        self.bots.append(bot)

    def get(self, name: str) -> Bot | None:
        for b in self.bots:
            if b.name == name:
                return b
        return None

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
        if bot.pid and self._pid_alive(bot.pid):
            bot.state = BotState.RUNNING
        elif bot.xvfb_pid and self._pid_alive(bot.xvfb_pid):
            bot.state = BotState.RUNNING
        else:
            bot.state = BotState.OFFLINE
            bot.pid = None

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
            timeout=5,
        )
        wins = r.stdout.strip().split()
        return wins[0] if wins else None

    def start_xvfb(self, bot: Bot) -> None:
        display = bot.display
        subprocess.run(["fuser", "-k", f"/tmp/.X11-unix/X{display}"],
                       capture_output=True, timeout=5)
        subprocess.run(["fuser", "-k", f"/tmp/.X{display}-lock"],
                       capture_output=True, timeout=5)
        for p in (f"/tmp/.X{display}-lock", f"/tmp/.X11-unix/X{display}"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        proc = subprocess.Popen(
            ["Xvfb", f":{display}", "-screen", "0", "1152x864x24",
             "-nolisten", "tcp", "-noreset", "-ac"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
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
        }
        proc = subprocess.Popen(
            [WINE_BIN, "Doomsday.exe",
             "-screen-width", "1152", "-screen-height", "864",
             "-fullscreen", "False", "-la"],
            cwd=bot.game_dir, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
        )
        bot.pid = proc.pid
        time.sleep(3)

    def stop_game(self, bot: Bot) -> None:
        if bot.pid and self._pid_alive(bot.pid):
            os.killpg(os.getpgid(bot.pid), signal.SIGTERM)
            time.sleep(2)
            if self._pid_alive(bot.pid):
                os.killpg(os.getpgid(bot.pid), signal.SIGKILL)
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
        subprocess.Popen(
            ["python3", "-m", "gt_spector", "--session", f":{bot.display}"],
            env={"DISPLAY": ":0"},
        )
