import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, cast

import numpy as np

from gt_spector import audio, login_flow, logs, monitor, overlay, settings
from gt_spector.bot_manager import Bot, BotManager, BotState
from gt_spector.monitor import BotMonitor
from gt_spector.script import ScriptRunner
from gt_spector.scripts.help_bot import HelpBot
from gt_spector.scripts.navigate_bot import NavigateBot

ACCOUNTS_FILE = Path("/home/swong/dls/src/ahk/accounts")
PREFIXES_DIR = Path("/home/swong/dls/wineprefix_bots")

MONITOR_INTERVAL = 2.0


class _VlmAdapter:
    """Thin wrapper around gt_spector.vlm (WIP module); degrades to None via _make_vlm."""

    def __init__(self, vlm: Any) -> None:
        self._vlm = vlm

    def analyze_frame(self, frame: Any, prompt: str | None = None,
                      max_tokens: int = 200) -> dict[str, Any]:
        return self._vlm.analyze_frame(frame, prompt=prompt, max_tokens=max_tokens)


def _make_vlm() -> Any:
    try:
        from gt_spector import vlm
    except Exception:  # noqa: BLE001 - WIP module; degrade to None
        return None
    return _VlmAdapter(vlm)


class _FrameSession:
    """Minimal frame-only object for GameWorld.identify (frame + get_pixel).

    Avoids constructing a real Session (which attaches an X input) on every
    poll; the console already has the frame in hand.
    """

    def __init__(self, frame: Any) -> None:
        self._frame = frame

    @property
    def frame(self) -> Any:
        return self._frame

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        return tuple(int(v) for v in self._frame[y, x, :3])


class BotConsole:
    def __init__(self) -> None:
        self._manager = BotManager()
        self._manager.load_from_prefixes()
        self._accounts = self._load_accounts()
        self._monitor = BotMonitor(self._manager, _make_vlm())
        self._frames: dict[str, np.ndarray | None] = {}
        self._nav_cache: dict[str, Any] | None = None
        self._vlm_screens: dict[str, str] = {}
        self._sound_applied: dict[str, int] = {}
        self._vlm_stop = False
        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator
        self._gw = GameWorld()
        self._locator = Locator()
        self._gw.set_locator(self._locator)

        self._tk = tk.Tk()
        self._tk.title("gt-spector — Bot Console")
        self._tk.geometry(self._load_geometry("600x500"))

        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_bot_list()

        self._start_monitor_worker()
        self._poll()
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)
        if settings.vlm_enabled():
            self._start_vlm_worker()

    def _geometry_path(self) -> Path:
        return Path.home() / ".config" / "gt-spector" / "console_geometry.json"

    def _load_geometry(self, default: str) -> str:
        try:
            data = json.loads(self._geometry_path().read_text())
            w = max(400, min(2000, int(data.get("w", 600))))
            h = max(300, min(1500, int(data.get("h", 500))))
            x = int(data.get("x", -1))
            y = int(data.get("y", -1))
            if x < 0 or y < 0:
                return f"{w}x{h}"
            return f"{w}x{h}+{x}+{y}"
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return default

    def _save_geometry(self) -> None:
        m = re.match(r"(\d+)x(\d+)[+]?(-?\d+)?[+]?(-?\d+)?", self._tk.geometry())
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            x = int(m.group(3)) if m.group(3) else -1
            y = int(m.group(4)) if m.group(4) else -1
            w = max(400, min(2000, w))
            h = max(300, min(1500, h))
            path = self._geometry_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"w": w, "h": h, "x": x, "y": y}))
            os.replace(tmp, path)

    def _parse_accounts(self) -> list[tuple[str, str]]:
        """Read ACCOUNTS_FILE, mapping line order -> (bot name, email).

        Source of truth is the accounts file; bot name is line order (first
        entry -> bot01, second -> bot02, ...), never the email itself.
        Malformed lines yield no entry but still consume a line slot.
        """
        out: list[tuple[str, str]] = []
        try:
            lines = ACCOUNTS_FILE.read_text().splitlines()
        except (FileNotFoundError, OSError):
            return out
        for i, line in enumerate(lines):
            line = line.strip()
            if ":" not in line:
                continue
            email = line.split(":")[0].strip()
            out.append((f"bot{i + 1:02d}", email))
        return out

    def _load_accounts(self) -> dict[str, str]:
        return dict(self._parse_accounts())

    def _unprovisioned_accounts(self) -> list[tuple[str, str]]:
        """Accounts (line order -> bot name) whose prefix is not provisioned.

        Returns [(bot_name, email), ...] for accounts lacking a prefix with
        drive_c. Accounts are mapped by line order (first -> bot01), never by
        assuming the email is sequential.
        """
        return [
            (name, email)
            for name, email in self._parse_accounts()
            if not (PREFIXES_DIR / name / "drive_c").exists()
        ]

    def _login_password(self, email: str) -> str:
        """Password for an account email from the accounts file."""
        try:
            for line in ACCOUNTS_FILE.read_text().splitlines():
                if line.startswith(email + ":"):
                    return line.split(":", 1)[1].strip()
        except (FileNotFoundError, OSError):
            pass
        return ""

    def _boot_and_login(self, bot, email: str, password: str) -> str:
        """Wait for boot, then log the bot in. Returns final screen."""
        session, gw, locator = self._provision_session(bot)

        import time as _t
        boot_deadline = _t.monotonic() + 120
        screen = None
        while _t.monotonic() < boot_deadline:
            _t.sleep(3)
            try:
                session.refresh()
                screen = gw.identify(session)
            except Exception:  # noqa: BLE001 - boot in progress
                screen = None
            if screen in ("startup_expired", "game_login", "igg_login",
                          "another_login_disconnect") or screen is not None:
                break
        if screen is None:
            return "error: no login screen after boot"
        return login_flow.expired_login(
            email, password, session, gw, locator,
            bot.prefix, f":{bot.display}",
            force_account=True,
        )

    def _provision_session(self, bot: Any) -> tuple[Any, Any, Any]:
        """Create the game-world objects bound to a bot's display."""
        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator
        from gt_spector.session import Session

        gw = GameWorld()
        locator = Locator()
        gw.set_locator(locator)
        session = Session(f":{bot.display}", source=f"shm://{bot.display}")
        return session, gw, locator

    def _apply_default_settings(self, bot: Any, gw: Any, locator: Any,
                                session: Any) -> str | None:
        """Navigate to system_settings and apply the default in-game options.

        Returns None on success, or a failure description. Called once after a
        fresh provision+login so each bot gets the same low graphics / silent
        audio profile the rest of the farm runs with.
        """
        from gt_spector.navigator import Navigator
        from viewer import cli as cli_mod

        nav = Navigator(gw, locator, session)
        return cli_mod.apply_in_game_settings(
            session, cli_mod.DEFAULT_IN_GAME_SETTINGS, gw, nav,
        )

    def _provision_n(self, count: int) -> None:
        """Provision the first `count` unprovisioned accounts, one at a time.

        Runs on a background thread so the UI stays responsive; progress is
        marshalled to the Tk thread via `after`. Sequential only; verifies
        exit code 0 after each; stops on the first failure.
        """
        import threading

        pending = self._unprovisioned_accounts()[:count]

        def _set_status(text: str) -> None:
            self._set_provision_progress(text)

        def worker() -> None:
            self._tk.after(0, self._show_provision_progress)
            try:
                for name, email in pending:
                    _set_status(f"Provisioning {name} ({email})...")
                    try:
                        r = subprocess.run(
                            [sys.executable, "-m", "gt_spector.provision", "init",
                             name, "--account", email],
                            capture_output=True, text=True, timeout=600, check=False)
                    except (OSError, subprocess.TimeoutExpired) as e:
                        _set_status(f"{name}: FAILED ({e})")
                        return
                    if r.returncode != 0:
                        tail = (r.stderr or r.stdout or "").strip()[-60:]
                        _set_status(f"{name}: FAILED ({tail})")
                        return
                    _set_status(f"{name}: provisioned, starting...")
                    # The prefix directory only exists now; the startup scan
                    # does not know it, so re-scan before looking it up.
                    self._manager.reload_from_prefixes()
                    # Show the new bot in the list immediately.
                    self._tk.after(0, self._refresh_bots)
                    bot = self._manager.get(name)
                    if bot is None:
                        _set_status(f"{name}: FAILED (no bot)")
                        return
                    try:
                        self._manager.start_game(bot)
                        password = self._login_password(email)
                        result = self._boot_and_login(bot, email, password)
                    except Exception as e:  # noqa: BLE001 - report, don't die silently
                        _set_status(f"{name}: FAILED ({e})")
                        return
                    if result not in ("in_game", "shelter_view", "world_map",
                                      "start_norah", "glory_league_event", None):
                        _set_status(f"{name}: login failed ({result})")
                        return
                    _set_status(f"{name}: logged in, applying settings...")
                    try:
                        session, gw, locator = self._provision_session(bot)
                        settings_fail = self._apply_default_settings(
                            bot, gw, locator, session)
                    except Exception as e:  # noqa: BLE001 - report, don't die silently
                        _set_status(f"{name}: settings FAILED ({e})")
                        return
                    if settings_fail:
                        _set_status(f"{name}: settings failed ({settings_fail})")
                        return
                self._tk.after(0, self._refresh_bots)
                _set_status(f"Provisioned {len(pending)} bot(s)")
            finally:
                self._hide_provision_progress()

        threading.Thread(target=worker, daemon=True).start()

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Refresh", command=self._refresh_bots)
        file_menu.add_command(label="Settings…", command=self._on_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        sel_menu = tk.Menu(menubar, tearoff=0)
        sel_menu.add_command(label="Select All", command=self._check_all)
        sel_menu.add_command(label="Clear Selection", command=self._uncheck_all)
        menubar.add_cascade(label="Selection", menu=sel_menu)

        act_menu = tk.Menu(menubar, tearoff=0)
        act_menu.add_command(label="Start", command=lambda: self._action("start"))
        act_menu.add_command(label="Stop", command=lambda: self._action("stop"))
        act_menu.add_command(label="Restart", command=lambda: self._action("restart"))
        act_menu.add_separator()
        act_menu.add_command(label="Start All", command=lambda: self._action_all("start"))
        act_menu.add_command(label="Stop All", command=lambda: self._action_all("stop"))
        act_menu.add_command(label="Restart All", command=lambda: self._action_all("restart"))
        menubar.add_cascade(label="Actions", menu=act_menu)

        prov_menu = tk.Menu(menubar, tearoff=0)
        prov_menu.add_command(label="Provision Bots…", command=self._on_provision)
        menubar.add_cascade(label="Provision", menu=prov_menu)

        script_menu = tk.Menu(menubar, tearoff=0)
        script_menu.add_command(label="Start Help Bot", command=self._start_help_bot)
        script_menu.add_command(label="Stop Help Bot", command=self._stop_help_bots)
        script_menu.add_separator()
        script_menu.add_command(label="Navigate to Help Dialog", command=self._navigate_to_help_dialog)
        menubar.add_cascade(label="Scripts", menu=script_menu)

        overlay_menu = tk.Menu(menubar, tearoff=0)
        self._overlay_global_var = tk.BooleanVar(value=settings.overlay_global_enabled())
        overlay_menu.add_checkbutton(
            label="Show Overlays", variable=self._overlay_global_var,
            command=self._on_overlay_global_toggle)
        overlay_menu.add_command(label="Show on Checked", command=lambda: self._overlay_checked(True))
        overlay_menu.add_command(label="Hide on Checked", command=lambda: self._overlay_checked(False))
        overlay_menu.add_separator()
        overlay_menu.add_command(label="Add Marker…", command=self._on_add_marker)
        overlay_menu.add_command(label="List Markers", command=self._on_list_markers)
        overlay_menu.add_command(label="Clear Markers on Checked", command=self._on_clear_markers)
        menubar.add_cascade(label="Overlay", menu=overlay_menu)

        sound_menu = tk.Menu(menubar, tearoff=0)
        self._sound_mode_var = tk.StringVar(value=settings.sound_mode())
        for label, mode in [("All Off", "all_off"), ("Viewer Control", "viewer"), ("All On", "all_on")]:
            sound_menu.add_radiobutton(
                label=label, value=mode, variable=self._sound_mode_var,
                command=self._on_sound_mode)
        menubar.add_cascade(label="Sound", menu=sound_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Open Viewers", command=self._open_viewers)
        menubar.add_cascade(label="View", menu=view_menu)

        logs_menu = tk.Menu(menubar, tearoff=0)
        logs_menu.add_command(label="Clear Logs", command=self._clear_logs)
        menubar.add_cascade(label="Logs", menu=logs_menu)

    def _setup_toolbar(self) -> None:
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        for text, cmd in [
            ("▶ Start", lambda: self._action("start")),
            ("■ Stop", lambda: self._action("stop")),
            ("↻ Restart", lambda: self._action("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        for text, cmd in [
            ("▶▶ Start All", lambda: self._action_all("start")),
            ("■■ Stop All", lambda: self._action_all("stop")),
            ("↻↻ Restart All", lambda: self._action_all("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Start Help", command=self._start_help_bot).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop Help", command=self._stop_help_bots).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="☑ All", command=self._check_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="☐ None", command=self._uncheck_all).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Clear Status",
                   command=lambda: self._status.config(text="Ready")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear Logs", command=self._clear_logs).pack(side=tk.LEFT, padx=2)

    def _setup_bot_list(self) -> None:
        frame = ttk.Frame(self._tk)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        ttk.Label(frame, text="Bots", font=("", 11, "bold")).pack(anchor=tk.W)
        self._columns = [
            ("sel", "✓", 30, tk.CENTER),
            ("bot", "Bot", 90, tk.W),
            ("account", "Account", 170, tk.W),
            ("disp", "Disp", 50, tk.E),
            ("status", "Status", 200, tk.W),
            ("activity", "Activity", 140, tk.W),
            ("help", "Help", 60, tk.E),
            ("loc", "Loc", 100, tk.W),
            ("cr", "CR", 40, tk.E),
            ("iv", "IV", 40, tk.E),
            ("snd", "Snd", 40, tk.W),
            ("cpu", "CPU", 50, tk.E),
            ("mem", "Mem", 60, tk.E),
            ("pid", "PID", 90, tk.E),
            ("view", "View", 50, tk.CENTER),
        ]
        self._tree = ttk.Treeview(
            frame, columns=[c[0] for c in self._columns],
            show="headings", selectmode="extended",
        )
        for key, text, width, anchor in self._columns:
            self._tree.heading(key, text=text, anchor=anchor)
            self._tree.column(key, width=width, minwidth=30, anchor=anchor)
        for color in ("green", "gold", "blue", "red", "black"):
            self._tree.tag_configure(color, foreground=color)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<Button-1>", self._on_tree_click)
        self._tree.bind("<Double-1>", self._on_tree_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Motion>", self._on_tree_motion)
        self._tree.bind("<Leave>", self._on_tree_leave)
        self._tooltips: dict[str, str] = {}
        self._tree_tip: tk.Toplevel | None = None
        self._tree_tip_label: ttk.Label | None = None
        self._runners: dict[str, ScriptRunner] = {}
        self._restart_runner_pending: set[str] = set()
        self._pending_restart_script: dict[str, Any] = {}
        self._build_rows()

    def _build_rows(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._tooltips = {}
        for bot in self._manager.bots:
            self._tree.insert("", tk.END, iid=bot.name,
                              values=("☐", bot.name, "", "", "", "", "", "", "", "", "", "", "", "", "[View]"))
        self._update_rows()

    def _status_glyph(self, bot: Bot) -> tuple[str, str]:
        if bot.state == BotState.RUNNING:
            return "●", "Running"
        if bot.state == BotState.STARTING:
            return "◐", "Starting"
        if bot.state == BotState.ERROR:
            return "▲", "Alert"
        if bot.state == BotState.OFFLINE:
            return "✕", "Offline"
        return "●", bot.state.value

    def _status_color(self, bot: Bot) -> str:
        if bot.state == BotState.RUNNING:
            return "green"
        if bot.state == BotState.STARTING:
            return "gold"
        if bot.state == BotState.ERROR:
            return "blue"
        if bot.state == BotState.OFFLINE:
            return "red"
        return "black"

    @staticmethod
    def _status_text(script: str, loc: str | None) -> str:
        """Script + map for the status column. Map alone lives in the Loc column."""
        if script:
            return f"{script} @ {loc or '?'}"
        return ""

    def _status_tooltip(self, bot: Bot, frame: np.ndarray | None = None) -> str:
        runner = self._runners.get(bot.name)
        script = runner.script.name if runner and runner.script else ""
        if frame is None:
            frame = self._read_frame(bot.display)
        loc = self._detect_location(bot, frame)
        base = f"{bot.state.value} — {script} in {loc or '?'}" if script else f"{bot.state.value} — in {loc or '?'}"
        if getattr(bot, "intervention_count", 0) > 0:
            base += f", {bot.intervention_count} interventions"
        return base

    def _detect_location(self, bot: Bot, frame: Any,
                         gw: Any = None, locator: Any = None) -> str | None:
        if frame is None:
            return "?"
        if monitor.frame_is_blank(frame):
            return "blank"
        loc = monitor.detect_screen(frame, self._nav_table())
        if loc is not None:
            return loc
        gw = gw or self._gw
        locator = locator or self._locator
        try:
            identified = gw.identify(_FrameSession(frame))
            if identified:
                return identified
        except Exception:  # noqa: BLE001, S110
            pass
        screens = cast(dict[str, str] | None, getattr(self, "_vlm_screens", None))
        if screens:
            return screens.get(bot.name)
        return None

    @staticmethod
    def _needs_recovery(loc: str | None, expected: str | None) -> bool:
        if loc in (None, "?", "blank"):
            return False
        return expected is not None and loc != expected

    @staticmethod
    def _loc_label(loc: str | None, runner: Any | None) -> str | None:
        """Friendly Loc label: 'Alliance Help' when this bot's help loop is
        active on the help area; otherwise the raw location name."""
        if (runner is not None
                and getattr(runner.script, "self_healing", False)
                and loc in ("EVENT", "help_dialog", "ALLIANCE_HELP")):
            return "Alliance Help"
        return loc

    def _nav_table(self) -> dict[str, Any]:
        cache = cast(dict[str, Any] | None, getattr(self, "_nav_cache", None))
        if cache is not None:
            return cache
        p = Path("~/.config/gt-spector/nav_table.json").expanduser()
        try:
            cache = cast(dict[str, Any], json.loads(p.read_text()))
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {"states": {}}
        self._nav_cache = cache
        return cache

    def _update_rows(self) -> None:
        gpu = self._manager.get_gpu_stats()
        ram = self._manager.get_system_ram()
        total_cpu = 0.0
        total_mem = 0
        running_count = 0
        self._frames = {}
        running = [b for b in self._manager.bots
                   if b.state == BotState.RUNNING and self._tree.exists(b.name)]
        stats_map = self._manager.get_process_stats_many(running)
        for bot in self._manager.bots:
            if not self._tree.exists(bot.name):
                continue
            self._manager._refresh_state(bot)
            glyph, _ = self._status_glyph(bot)
            frame = self._read_frame(bot.display)
            self._frames[bot.name] = frame
            self._tooltips[bot.name] = self._status_tooltip(bot, frame)
            loc = self._detect_location(bot, frame)
            runner = self._runners.get(bot.name)
            loc = self._loc_label(loc, runner)
            script = runner.script.name if runner and runner.script else ""
            status_text = self._status_text(script, loc)
            activity = ""
            if runner and runner.script:
                status = None
                if frame is not None:
                    status = runner.tick(frame)
                activity = status or ""
            muted = audio.is_muted(bot.pid) if bot.pid else None
            cpu, mem, pid = "", "", ""
            s = self._manager._pid_stats_for(bot, stats_map)
            if s:
                running_count += 1
                cpu = f"{s['cpu_percent']:.0f}"
                mem = f"{s['rss_mb']}M"
                pid = str(s['pid'])
                total_cpu += s['cpu_percent']
                total_mem += s['rss_mb']
            else:
                pid = str(bot.pid) if bot.pid else ""
            sel = "☑" if bot.name in set(self._tree.selection()) else "☐"
            help_count = ""
            if runner is not None:
                help_count = str(getattr(runner, "help_clicks", ""))
            self._tree.item(bot.name, tags=(self._status_color(bot),), values=(
                sel,
                bot.name,
                self._accounts.get(bot.name, ""),
                f":{bot.display}",
                f"{glyph} {status_text}".rstrip(),
                activity,
                help_count,
                loc or "?",
                str(bot.crash_count),
                str(bot.intervention_count),
                "🔇" if muted is True else "🔊" if muted is False else "—",
                cpu,
                mem,
                pid,
                "[View]",
            ))
        self._status.config(
            text=f"GPU {gpu['gpu_busy_percent']:.0f}%  "
                 f"VRAM {gpu['vram_used_mb']}/{gpu['vram_total_mb']}M  "
                 f"RAM {ram['mem_used_mb']}/{ram['mem_total_mb']}M  "
                 f"Swap {ram['swap_used_mb']}/{ram['swap_total_mb']}M  "
                 f"| {running_count} bots  "
                 f"CPU {total_cpu:.0f}%  MEM {total_mem}M"
        )

    def _on_tree_click(self, event: Any) -> str | None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            return None
        col = self._tree.identify_column(event.x)
        key = self._columns[int(col[1:]) - 1][0] if col.startswith("#") else None
        if key == "sel":
            self._toggle_selected(iid)
            return "break"
        if key == "view":
            self._on_view(iid)
            return "break"
        return None

    def _toggle_selected(self, iid: str) -> None:
        selected = set(self._tree.selection())
        if iid in selected:
            selected.discard(iid)
        else:
            selected.add(iid)
        self._tree.selection_set(*selected)

    def _on_tree_select(self, _event: Any = None) -> None:
        self._update_selection_only()

    def _update_selection_only(self) -> None:
        """Re-render only the ☑/☐ selection column after a selection change.

        The full _update_rows (stats, location detection, tooltips) is
        expensive and already runs on the 2s poll; a selection only changes
        the checkbox glyph, so update that alone for instant feedback.
        """
        selected = set(self._tree.selection())
        for bot in self._manager.bots:
            if not self._tree.exists(bot.name):
                continue
            try:
                values = list(self._tree.item(bot.name, "values") or ())
            except Exception:  # noqa: BLE001, S112 - a missing row must not abort
                continue
            if not values:
                continue
            values[0] = "☑" if bot.name in selected else "☐"
            self._tree.item(bot.name, values=tuple(values))

    def _on_tree_double_click(self, event: Any) -> None:
        iid = self._tree.identify_row(event.y)
        if iid:
            self._on_view(iid)

    def _on_tree_motion(self, event: Any) -> None:
        iid = self._tree.identify_row(event.y)
        col = self._tree.identify_column(event.x)
        key = self._columns[int(col[1:]) - 1][0] if col.startswith("#") else None
        if key == "view":
            self._tree.configure(cursor="hand2")
        else:
            self._tree.configure(cursor="")
        text = self._tooltips.get(iid, "")
        if not text:
            self._hide_tree_tip()
            return
        x = self._tree.winfo_rootx() + event.x + 16
        y = self._tree.winfo_rooty() + event.y + 16
        if self._tree_tip is None:
            self._tree_tip = tk.Toplevel(self._tree)
            self._tree_tip.wm_overrideredirect(True)
            self._tree_tip_label = ttk.Label(
                self._tree_tip, background="#ffffe0", relief=tk.SOLID, borderwidth=1)
            self._tree_tip_label.pack()
        self._tree_tip_label.config(text=text)
        self._tree_tip.wm_geometry(f"+{x}+{y}")

    def _on_tree_leave(self, _event: Any = None) -> None:
        self._hide_tree_tip()

    def _hide_tree_tip(self) -> None:
        if self._tree_tip is not None:
            self._tree_tip.destroy()
            self._tree_tip = None

    def _parse_shm_frame(self, buf: Any) -> np.ndarray | None:
        import struct

        if len(buf) < 16:
            return None
        try:
            _c, w, h = struct.unpack("<QII", buf[:16])
            return np.frombuffer(buf, dtype=np.uint8, offset=16).copy().reshape(h, w, 4)
        except (struct.error, ValueError):
            return None

    def _read_frame(self, display: int) -> np.ndarray | None:
        import mmap

        try:
            with open(f"/dev/shm/gt-spector-{display}-frame", "r+b") as f:
                mm = mmap.mmap(f.fileno(), 0)
                try:
                    return self._parse_shm_frame(mm)
                finally:
                    mm.close()
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _on_overlay_global_toggle(self) -> None:
        overlay.set_overlay_enabled(None, self._overlay_global_var.get())
        logs.log_system(f"overlay global = {self._overlay_global_var.get()}")

    def _overlay_checked(self, enabled: bool) -> None:
        for bot in self._get_checked():
            overlay.set_overlay_enabled(bot.display, enabled)
            logs.log_system(f"overlay {bot.name} = {enabled}")

    def _on_add_marker(self) -> None:
        import tkinter.simpledialog as sd

        x = sd.askinteger("Add Marker", "x:", parent=self._tk)
        if x is None:
            return
        y = sd.askinteger("Add Marker", "y:", parent=self._tk)
        if y is None:
            return
        label = sd.askstring("Add Marker", "label (optional):", parent=self._tk) or ""
        for bot in self._get_checked():
            overlay.add_marker(bot.display, x, y, label)
        self._status.config(text=f"Markers added to {len(self._get_checked())} bots")

    def _on_list_markers(self) -> None:
        win = tk.Toplevel(self._tk)
        win.title("Markers")
        for bot in self._get_checked():
            ttk.Label(win, text=f"=== {bot.name} ===", font=("", 10, "bold")).pack(anchor=tk.W)
            markers = overlay.load_markers(bot.display)
            if not markers:
                ttk.Label(win, text="  No markers").pack(anchor=tk.W)
            for m in markers:
                ttk.Label(win, text=f"  {m.id} @ ({m.x},{m.y}) label='{m.label}'").pack(anchor=tk.W)

    def _on_clear_markers(self) -> None:
        for bot in self._get_checked():
            overlay.clear_markers(bot.display)
        self._status.config(text="Markers cleared")

    def _on_sound_mode(self) -> None:
        settings.set_sound_mode(self._sound_mode_var.get())
        self._sound_applied.clear()
        self._apply_sound_policy()
        logs.log_system(f"sound mode = {settings.sound_mode()}")

    def _apply_sound_for_bot(self, bot: Bot) -> None:
        if not bot.pid:
            return
        mode = settings.sound_mode()
        if mode == "all_off":
            audio.set_muted(bot.pid, True)
        elif mode == "all_on":
            audio.set_muted(bot.pid, False)
        elif settings.bot_sound_muted(bot.name):
            audio.set_muted(bot.pid, True)
        self._sound_applied[bot.name] = bot.pid

    def _apply_sound_policy(self) -> None:
        for bot in self._manager.bots:
            self._apply_sound_for_bot(bot)

    def _open_viewers(self) -> None:
        for bot in self._get_checked():
            self._manager.attach_viewer(bot)
        self._status.config(text="Viewers opened")

    def _clear_logs(self) -> None:
        logs.clear_all_logs()
        self._status.config(text="Logs cleared")

    def _on_settings(self) -> None:
        import tkinter.simpledialog as sd

        cur = settings.log_max_bytes() // 1024
        val = sd.askinteger("Settings", "Log rotation size (KB):", parent=self._tk,
                            initialvalue=cur, minvalue=1)
        if val:
            settings.set_log_max_bytes(val * 1024)
            logs.log_system(f"log_max_bytes = {val * 1024}")
        ival = sd.askfloat("Settings", "VLM status interval (s):", parent=self._tk,
                           initialvalue=settings.vlm_interval(), minvalue=1)
        if ival:
            settings.set_vlm_interval(ival)
            logs.log_system(f"vlm_interval = {ival}")
        dval = sd.askinteger("Settings", "VLM downscale factor (1=full res):", parent=self._tk,
                             initialvalue=settings.vlm_downscale(), minvalue=1)
        if dval:
            settings.set_vlm_downscale(dval)
            logs.log_system(f"vlm_downscale = {dval}")

    def _start_help_bot(self) -> None:
        for bot in self._get_checked():
            old = self._runners.pop(bot.name, None)
            if old:
                old.stop()
            self._status.config(text=f"Starting help bot on {bot.name}...")
            self._tk.update()
            bot_help = HelpBot()
            bot_help.start(bot.display)
            self._runners[bot.name] = bot_help
            self._status.config(text=f"Help bot running on {bot.name}")

    def _stop_help_bots(self) -> None:
        for bot in self._get_checked():
            runner = self._runners.pop(bot.name, None)
            if runner:
                runner.stop()
        self._status.config(text="Help bots stopped")

    def _navigate_to_help_dialog(self) -> None:
        for bot in self._get_checked():
            old = self._runners.pop(bot.name, None)
            if old:
                old.stop()
            self._status.config(text=f"Navigating {bot.name} to help dialog...")
            self._tk.update()
            nav = NavigateBot()
            nav.start(bot.display)
            self._runners[bot.name] = nav
            self._status.config(text=f"{bot.name}: {nav.status}")

    def _stop_scripts(self) -> None:
        for bot in self._get_checked():
            runner = self._runners.pop(bot.name, None)
            if runner:
                runner.stop()
        self._status.config(text="Scripts stopped")

    def _get_checked(self) -> list[Bot]:
        selected = set(self._tree.selection())
        return [b for b in self._manager.bots if b.name in selected]

    def _check_all(self) -> None:
        self._tree.selection_set(self._tree.get_children())

    def _uncheck_all(self) -> None:
        self._tree.selection_remove(self._tree.get_children())

    def _on_view(self, name: str) -> None:
        bot = self._manager.get(name)
        if bot:
            self._manager.attach_viewer(bot)
            self._status.config(text=f"Viewer opened for {name}")

    def _action(self, action: str) -> None:
        for bot in self._get_checked():
            try:
                getattr(self._manager, f"{action}_game")(bot)
            except (OSError, RuntimeError) as e:
                self._status.config(text=f"Error on {bot.name}: {e}")
        self._update_rows()

    def _action_all(self, action: str) -> None:
        for bot in self._manager.bots:
            try:
                getattr(self._manager, f"{action}_game")(bot)
            except (OSError, RuntimeError) as e:
                self._status.config(text=f"Error on {bot.name}: {e}")
        self._update_rows()

    def _on_provision(self) -> None:
        self._provision_dialog()

    def _provision_dialog(self) -> None:
        """Dialog: list unprovisioned accounts, pick 1..N, provision sequentially."""
        pending = self._unprovisioned_accounts()
        win = tk.Toplevel(self._tk)
        win.title("Provision Bots")
        if not pending:
            ttk.Label(win, text="All accounts provisioned").pack(padx=12, pady=12)
            ttk.Button(win, text="Close", command=win.destroy).pack(pady=4)
            return

        ttk.Label(win, text="Unprovisioned accounts:", font=("", 10, "bold")).pack(
            anchor=tk.W, padx=12, pady=(12, 4))
        for name, email in pending:
            ttk.Label(win, text=f"  {name} -> {email}", anchor=tk.W).pack(
                anchor=tk.W, padx=16)
        count = tk.IntVar(value=1)
        ttk.Label(win, text="How many to provision?").pack(anchor=tk.W, padx=12, pady=(10, 2))
        ttk.Spinbox(win, from_=1, to=len(pending), textvariable=count, width=6).pack(
            anchor=tk.W, padx=16)

        def run() -> None:
            try:
                n = count.get()
            except tk.TclError:
                return  # non-numeric input; keep the dialog open
            win.destroy()
            self._provision_n(n)

        ttk.Button(win, text="Provision", command=run).pack(side=tk.LEFT, padx=12, pady=12)
        ttk.Button(win, text="Cancel", command=win.destroy).pack(
            side=tk.LEFT, padx=4, pady=12)

    def _refresh_bots(self) -> None:
        # reload (clear + rescan), not load (append): a manual refresh must
        # reflect removed/provisioned prefixes without duplicating bots.
        self._manager.reload_from_prefixes()
        self._build_rows()
        self._status.config(text=f"Refreshed: {len(self._manager.bots)} bots")

    def _setup_statusbar(self) -> None:
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)
        self._provision_status = ttk.Label(
            self._tk, text="", anchor=tk.W, foreground="#cc0000",
            font=("", 10, "bold"))
        # hidden by default; _provision_n shows it during provisioning

    def _show_provision_progress(self) -> None:
        try:
            self._provision_status.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)
        except Exception:  # noqa: BLE001, S110 - already visible
            pass

    def _set_provision_progress(self, text: str) -> None:
        self._tk.after(0, lambda: self._provision_status.config(text=text))

    def _hide_provision_progress(self) -> None:
        self._tk.after(0, lambda: self._provision_status.pack_forget())

    def _start_monitor_worker(self) -> None:
        """Background daemon thread running the monitor tick.

        check_responsiveness sleeps ~0.4s per running bot (sampling SHM
        counters), which would freeze the Tk UI if run on the main thread.
        Run it on a daemon thread so the UI poll only does the quick row
        update. Stops when the console closes (via _vlm_stop).
        """
        import threading

        from gt_spector.game_world import GameWorld
        from gt_spector.locator import Locator

        def worker() -> None:
            # Own GameWorld/Locator: the UI thread shares self._gw/_locator
            # (whose mutable _gray_cache would race if accessed concurrently).
            gw = GameWorld()
            locator = Locator()
            gw.set_locator(locator)
            while not self._vlm_stop:
                time.sleep(MONITOR_INTERVAL)
                try:
                    self._monitor_tick(gw, locator)
                except Exception as e:  # noqa: BLE001 - never kill the worker
                    logs.log_system(f"monitor worker error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _start_vlm_worker(self) -> None:
        """Background thread: classify running bots on the settable interval."""
        import threading

        self._vlm_stop = False

        def worker() -> None:
            while not self._vlm_stop:
                time.sleep(settings.vlm_interval())
                try:
                    self._vlm_worker_tick()
                except Exception as e:  # noqa: BLE001 - never kill the worker
                    logs.log_system(f"vlm worker error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _vlm_worker_tick(self) -> None:
        """One VLM classification pass, called from the background thread."""
        gpu = self._manager.get_gpu_stats()
        if not monitor.gpu_slot_free(gpu):
            return
        for bot in self._manager.bots:
            if bot.state != BotState.RUNNING or not bot.pid:
                continue
            frame = self._frames.get(bot.name)
            if frame is None:
                continue
            vlm_loc = self._monitor.classify_frame(frame, bot.display)
            if vlm_loc:
                self._vlm_screens[bot.name] = vlm_loc
                logs.log_bot(bot.name, f"VLM screen = {vlm_loc}")

    def _monitor_tick(self, gw: Any = None, locator: Any = None) -> None:
        for bot in self._manager.bots:
            try:
                self._monitor_one(bot, gw, locator)
            except Exception:  # noqa: BLE001 - one bot must not kill the poll
                logs.log_bot(bot.name, "monitor error, continuing")

    def _monitor_one(self, bot: Bot, gw: Any = None, locator: Any = None) -> None:
        if bot.state != BotState.RUNNING or not bot.pid:
            return
        now = time.monotonic()
        self._monitor.note_running(bot, now)
        if self._sound_applied.get(bot.name) != bot.pid:
            self._apply_sound_for_bot(bot)
        runner = self._runners.get(bot.name)
        if not self._monitor.check_responsiveness(bot, now):
            self._monitor.mark_crash(bot)
            logs.log_bot(bot.name, "non-responsive, restarting game")
            self._stop_stale_runner(bot)
            self._manager.restart_game(bot)
            self._monitor.mark_intervention(bot)
            return
        if bot.name in self._restart_runner_pending:
            self._restart_pending_runner(bot)
        if runner and runner.script:
            # Self-healing scripts (HelpBot) re-navigate on their own thread;
            # console recovery would crash (run_script) or fight the thread.
            if getattr(runner.script, "self_healing", False):
                return
            expected = getattr(runner.script, "expected_screen", None)
            if expected:
                if gw is None:
                    from gt_spector.game_world import GameWorld
                    from gt_spector.locator import Locator
                    gw = GameWorld()
                    locator = Locator()
                    gw.set_locator(locator)
                loc = self._detect_location(
                    bot, self._frames.get(bot.name), gw=gw, locator=locator)
                if self._needs_recovery(loc, expected):
                    if self._monitor.recoveries_left(bot):
                        logs.log_bot(bot.name, f"wrong screen {loc}, recovering")
                        self._monitor.recover(
                            bot, lambda b, s: self._runners[b.name].run_script(s), runner.script)
                    else:
                        logs.log_bot(bot.name, "recovery exhausted, marking ERROR")
                        self._monitor.mark_error(bot, runner)
                        bot.state = BotState.ERROR
                else:
                    self._monitor.recovery_succeeded(bot)

    def _stop_stale_runner(self, bot: Bot) -> None:
        """Stop a runner whose game is being restarted; restart it once up.

        HelpBot threads poll the old session/SHM and die or go stale when the
        game restarts. Record the pending restart; the next responsive pass
        (new PID) brings it back via run_script.
        """
        runner = self._runners.get(bot.name)
        if runner is None:
            return
        if runner.script is not None:
            self._pending_restart_script[bot.name] = runner.script
        self._restart_runner_pending.add(bot.name)
        try:
            runner.stop()
        except Exception:  # noqa: BLE001 - never let cleanup kill the poll
            logs.log_bot(bot.name, "runner stop during game restart failed")

    def _restart_pending_runner(self, bot: Bot) -> None:
        """Restart a runner marked for restart once the game is responsive."""
        runner = self._runners.get(bot.name)
        if runner is None:
            self._restart_runner_pending.discard(bot.name)
            self._pending_restart_script.pop(bot.name, None)
            return
        script = self._pending_restart_script.pop(bot.name, None)
        if script is None or not hasattr(runner, "run_script"):
            self._restart_runner_pending.discard(bot.name)
            return
        try:
            runner.run_script(script)
            self._restart_runner_pending.discard(bot.name)
        except Exception:  # noqa: BLE001 - one bot must not kill the poll
            logs.log_bot(bot.name, "runner restart failed, continuing")

    def _poll(self) -> None:
        self._nav_cache = None
        self._update_rows()
        self._tk.after(2000, self._poll)

    def _on_close(self) -> None:
        self._vlm_stop = True
        self._save_geometry()
        self._tk.destroy()

    def run(self) -> None:
        self._tk.mainloop()
