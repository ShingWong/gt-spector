import json
import os
import re
import shutil
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, cast

import numpy as np

from gt_spector import audio, logs, monitor, overlay, settings
from gt_spector.bot_manager import Bot, BotManager, BotState
from gt_spector.monitor import BotMonitor
from gt_spector.script import ScriptRunner
from gt_spector.scripts.help_bot import HelpBot
from viewer.tooltip import ToolTip


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


class BotConsole:
    def __init__(self) -> None:
        self._manager = BotManager()
        self._manager.load_from_prefixes()
        self._accounts = self._load_accounts()
        self._monitor = BotMonitor(self._manager, _make_vlm())
        self._frames: dict[str, np.ndarray | None] = {}
        self._nav_cache: dict[str, Any] | None = None
        self._vlm_screens: dict[str, str] = {}

        self._tk = tk.Tk()
        self._tk.title("gt-spector — Bot Console")
        self._tk.geometry(self._load_geometry("600x500"))

        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_bot_list()

        self._poll()
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)

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

    def _load_accounts(self) -> dict[str, str]:
        accounts: dict[str, str] = {}
        try:
            for i, line in enumerate(Path("/home/swong/dls/src/ahk/accounts").read_text().splitlines()):
                line = line.strip()
                if ":" in line:
                    email = line.split(":")[0].strip()
                    name = f"bot{i + 1:02d}"
                    accounts[name] = email
        except (FileNotFoundError, OSError):
            pass
        return accounts

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
        sel_menu.add_command(label="Check All", command=self._check_all)
        sel_menu.add_command(label="Uncheck All", command=self._uncheck_all)
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
        prov_menu.add_command(label="Provision Bots", command=self._on_provision)
        menubar.add_cascade(label="Provision", menu=prov_menu)

        script_menu = tk.Menu(menubar, tearoff=0)
        script_menu.add_command(label="Help Bot", command=self._start_help_bot)
        script_menu.add_command(label="Stop Script", command=self._stop_scripts)
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
        ttk.Button(toolbar, text="Help Bot", command=self._start_help_bot).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop Script", command=self._stop_scripts).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Clear Status",
                   command=lambda: self._status.config(text="Ready")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear Logs", command=self._clear_logs).pack(side=tk.LEFT, padx=2)

    def _setup_bot_list(self) -> None:
        frame = ttk.Frame(self._tk)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        ttk.Label(frame, text="Bots", font=("", 11, "bold")).pack(anchor=tk.W)
        canvas = tk.Canvas(frame, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        self._list_frame = ttk.Frame(canvas)
        self._list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._rows: dict[str, dict[str, Any]] = {}
        self._runners: dict[str, ScriptRunner] = {}
        self._build_rows()

    def _build_rows(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._rows.clear()
        header = ttk.Frame(self._list_frame)
        header.pack(fill=tk.X, pady=(0, 2))
        for text, width, anchor in [
            ("", 2, tk.CENTER), ("Bot", 8, tk.W), ("Account", 18, tk.W),
            ("Disp", 5, tk.E), ("Status", 24, tk.W), ("Activity", 16, tk.W),
            ("Loc", 12, tk.W), ("CR", 4, tk.E), ("IV", 4, tk.E),
            ("Snd", 2, tk.W), ("CPU", 6, tk.E), ("Mem", 6, tk.E),
            ("PID", 10, tk.E),
        ]:
            ttk.Label(header, text=text, width=width, anchor=anchor,
                      font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="", width=5).pack(side=tk.RIGHT)
        for bot in self._manager.bots:
            row = ttk.Frame(self._list_frame)
            row.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar()
            ttk.Checkbutton(row, variable=var, width=2).pack(side=tk.LEFT)
            ttk.Label(row, text=bot.name, width=8, anchor=tk.W).pack(side=tk.LEFT)
            acct = self._accounts.get(bot.name, "")
            ttk.Label(row, text=acct, width=18, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=f":{bot.display}", width=5, anchor=tk.E).pack(side=tk.LEFT)
            status_lbl = ttk.Label(row, width=24, anchor=tk.W)
            status_lbl.pack(side=tk.LEFT)
            status_tip = ToolTip(status_lbl, "")
            activity_lbl = ttk.Label(row, width=16, anchor=tk.W)
            activity_lbl.pack(side=tk.LEFT)
            loc_lbl = ttk.Label(row, width=12, anchor=tk.W)
            loc_lbl.pack(side=tk.LEFT)
            cr_lbl = ttk.Label(row, width=4, anchor=tk.E)
            cr_lbl.pack(side=tk.LEFT)
            iv_lbl = ttk.Label(row, width=4, anchor=tk.E)
            iv_lbl.pack(side=tk.LEFT)
            snd_lbl = ttk.Label(row, width=2, anchor=tk.W)
            snd_lbl.pack(side=tk.LEFT)
            cpu_lbl = ttk.Label(row, width=6, anchor=tk.E)
            cpu_lbl.pack(side=tk.LEFT)
            mem_lbl = ttk.Label(row, width=6, anchor=tk.E)
            mem_lbl.pack(side=tk.LEFT)
            pid_lbl = ttk.Label(row, width=10, anchor=tk.E)
            pid_lbl.pack(side=tk.LEFT)

            def view_cmd(n: str = bot.name) -> None:
                self._on_view(n)

            ttk.Button(row, text="View", width=5, command=view_cmd).pack(side=tk.RIGHT, padx=1)
            self._rows[bot.name] = {
                "var": var, "status": status_lbl, "status_tip": status_tip,
                "activity": activity_lbl, "loc": loc_lbl, "cr": cr_lbl,
                "iv": iv_lbl, "snd": snd_lbl, "cpu": cpu_lbl, "mem": mem_lbl,
                "pid": pid_lbl,
            }
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
        """Script + map for the status column. State words live in the glyph."""
        if script:
            return f"{script} @ {loc or '?'}"
        if loc and loc != "?":
            return loc
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

    def _detect_location(self, bot: Bot, frame: Any) -> str | None:
        if frame is None:
            return "?"
        if monitor.frame_is_blank(frame):
            return "blank"
        loc = monitor.detect_screen(frame, self._nav_table())
        if loc is not None:
            return loc
        screens = cast(dict[str, str] | None, getattr(self, "_vlm_screens", None))
        if screens:
            return screens.get(bot.name)
        return None

    @staticmethod
    def _needs_recovery(loc: str | None, expected: str | None) -> bool:
        if loc in (None, "?", "blank"):
            return False
        return expected is not None and loc != expected

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
        for bot in self._manager.bots:
            r = self._rows.get(bot.name)
            if not r:
                continue
            self._manager._refresh_state(bot)
            glyph, _ = self._status_glyph(bot)
            frame = self._read_frame(bot.display)
            self._frames[bot.name] = frame
            r["status_tip"].set_text(self._status_tooltip(bot, frame))
            loc = self._detect_location(bot, frame)
            if loc is None:
                vlm_loc = self._monitor.vlm_tick(frame, bot, time.monotonic())
                if vlm_loc:
                    self._vlm_screens[bot.name] = vlm_loc
                    loc = vlm_loc
            r["loc"].config(text=loc or "?")
            runner = self._runners.get(bot.name)
            script = runner.script.name if runner and runner.script else ""
            status_text = self._status_text(script, loc)
            r["status"].config(text=f"{glyph} {status_text}".rstrip(), foreground=self._status_color(bot))
            if runner and runner.script:
                status = None
                if frame is not None:
                    status = runner.tick(frame)
                r["activity"].config(text=status or "")
            else:
                r["activity"].config(text="")
            r["cr"].config(text=str(bot.crash_count))
            r["iv"].config(text=str(bot.intervention_count))
            muted = audio.is_muted(bot.pid) if bot.pid else None
            r["snd"].config(text="🔇" if muted is True else "🔊" if muted is False else "—")
            if bot.state == BotState.RUNNING:
                running_count += 1
                s = self._manager.get_process_stats(bot)
                if s:
                    r["cpu"].config(text=f"{s['cpu_percent']:.0f}")
                    r["mem"].config(text=f"{s['rss_mb']}M")
                    r["pid"].config(text=str(s['pid']))
                    total_cpu += s['cpu_percent']
                    total_mem += s['rss_mb']
                else:
                    r["cpu"].config(text="")
                    r["mem"].config(text="")
                    r["pid"].config(text=str(bot.pid) if bot.pid else "")
            else:
                r["cpu"].config(text="")
                r["mem"].config(text="")
                r["pid"].config(text=str(bot.pid) if bot.pid else "")
        self._status.config(
            text=f"GPU {gpu['gpu_busy_percent']:.0f}%  "
                 f"VRAM {gpu['vram_used_mb']}/{gpu['vram_total_mb']}M  "
                 f"RAM {ram['mem_used_mb']}/{ram['mem_total_mb']}M  "
                 f"Swap {ram['swap_used_mb']}/{ram['swap_total_mb']}M  "
                 f"| {running_count} bots  "
                 f"CPU {total_cpu:.0f}%  MEM {total_mem}M"
        )

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
        self._apply_sound_policy()
        logs.log_system(f"sound mode = {settings.sound_mode()}")

    def _apply_sound_policy(self) -> None:
        mode = settings.sound_mode()
        for bot in self._manager.bots:
            if mode == "all_off" and bot.pid:
                audio.set_muted(bot.pid, True)
            elif mode == "all_on" and bot.pid:
                audio.set_muted(bot.pid, False)
            # viewer mode: per-bot sound_muted governs; viewers set it directly

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

    def _start_help_bot(self) -> None:
        for bot in self._get_checked():
            if bot.name in self._runners:
                self._runners[bot.name].stop()
            self._status.config(text=f"Navigating {bot.name} to alliance...")
            self._tk.update()
            ok = HelpBot.navigate_to_alliance(bot.display)
            if not ok:
                self._status.config(text=f"Failed to navigate {bot.name}")
                continue
            runner = ScriptRunner(bot.display, None, None, None)
            runner.start(HelpBot())
            self._runners[bot.name] = runner
            self._status.config(text=f"Help bot running on {bot.name}")

    def _stop_scripts(self) -> None:
        for bot in self._get_checked():
            runner = self._runners.pop(bot.name, None)
            if runner:
                runner.stop()
        self._status.config(text="Scripts stopped")

    def _get_checked(self) -> list[Bot]:
        return [b for b in self._manager.bots
                if self._rows.get(b.name, {}).get("var", tk.BooleanVar()).get()]

    def _check_all(self) -> None:
        for r in self._rows.values():
            r["var"].set(True)

    def _uncheck_all(self) -> None:
        for r in self._rows.values():
            r["var"].set(False)

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
        self._status.config(text="Provisioning bots from accounts file...")
        self._tk.update()
        base = "/home/swong/dls/wineprefix_bots"
        for entry in os.listdir(base):
            shutil.rmtree(os.path.join(base, entry), ignore_errors=True)
        self._manager.bots.clear()
        self._build_rows()
        self._tk.update()

        for name, email in self._accounts.items():
            self._status.config(text=f"Building {name} ({email})...")
            self._tk.update()
            account_num = int(name.replace("bot", ""))
            if account_num == 1:
                reg = "/tmp/igg_sr04_full.reg"
            elif account_num == 2:
                reg = "/tmp/igg_sr05_full.reg"
            else:
                reg = None
            r = subprocess.run(
                ["python3", "-m", "gt_spector.provision", "init", name,
                 "--account", email] + (["--reg", reg] if reg and os.path.exists(reg) else []),
                capture_output=True, text=True, timeout=120, check=False)
            self._status.config(text=f"{name}: {r.stdout.strip()[-60:]}")
            self._tk.update()
        self._status.config(text="Provisioning complete")
        self._refresh_bots()

    def _refresh_bots(self) -> None:
        self._manager.load_from_prefixes()
        self._build_rows()
        self._status.config(text=f"Refreshed: {len(self._manager.bots)} bots")

    def _setup_statusbar(self) -> None:
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _monitor_tick(self) -> None:
        for bot in self._manager.bots:
            if bot.state != BotState.RUNNING or not bot.pid:
                continue
            now = time.monotonic()
            self._monitor.note_running(bot, now)
            runner = self._runners.get(bot.name)
            if not self._monitor.check_responsiveness(bot, now):
                self._monitor.mark_crash(bot)
                logs.log_bot(bot.name, "non-responsive, restarting game")
                self._manager.restart_game(bot)
                self._monitor.mark_intervention(bot)
                continue
            if runner and runner.script:
                expected = getattr(runner.script, "expected_screen", None)
                if expected:
                    loc = self._detect_location(bot, self._frames.get(bot.name))
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

    def _poll(self) -> None:
        self._nav_cache = None
        self._update_rows()
        self._monitor_tick()
        self._tk.after(2000, self._poll)

    def _on_close(self) -> None:
        self._save_geometry()
        self._tk.destroy()

    def run(self) -> None:
        self._tk.mainloop()
