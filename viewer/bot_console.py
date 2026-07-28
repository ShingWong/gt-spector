import tkinter as tk
from tkinter import ttk

from gt_spector.bot_manager import BotManager, BotState


class BotConsole:
    def __init__(self):
        self._manager = BotManager()
        self._manager.load_from_prefixes()
        self._accounts = self._load_accounts()

        self._tk = tk.Tk()
        self._tk.title("gt-spector — Bot Console")
        self._tk.geometry("600x500")

        self._setup_menu()
        self._setup_toolbar()
        self._setup_bot_list()
        self._setup_statusbar()

        self._poll()
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_accounts(self) -> dict[str, str]:
        accounts = {}
        try:
            with open("/home/swong/dls/ahk/accounts") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if ":" in line:
                        email = line.split(":")[0].strip()
                        name = f"bot{i+1:02d}"
                        accounts[name] = email
        except FileNotFoundError:
            pass
        return accounts

    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Refresh", command=self._refresh_bots)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        for text, cmd in [
            ("Start", lambda: self._action("start")),
            ("Stop", lambda: self._action("stop")),
            ("Restart", lambda: self._action("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        for text, cmd in [
            ("Start All", lambda: self._action_all("start")),
            ("Stop All", lambda: self._action_all("stop")),
            ("Restart All", lambda: self._action_all("restart")),
        ]:
            ttk.Button(toolbar, text=text, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Check All", command=self._check_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Uncheck All", command=self._uncheck_all).pack(side=tk.LEFT, padx=2)

    def _setup_bot_list(self):
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
        self._rows: dict[str, dict] = {}
        self._build_rows()

    def _build_rows(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._rows.clear()
        for bot in self._manager.bots:
            row = ttk.Frame(self._list_frame)
            row.pack(fill=tk.X, pady=2)
            var = tk.BooleanVar()
            ttk.Checkbutton(row, variable=var, width=2).pack(side=tk.LEFT)
            ttk.Label(row, width=2).pack(side=tk.LEFT)  # icon placeholder
            ttk.Label(row, text=bot.name, width=8).pack(side=tk.LEFT)
            acct = self._accounts.get(bot.name, "")
            ttk.Label(row, text=acct, width=20).pack(side=tk.LEFT)
            ttk.Label(row, text=f":{bot.display}", width=6).pack(side=tk.LEFT)
            state_lbl = ttk.Label(row, width=10)
            state_lbl.pack(side=tk.LEFT)
            pid_lbl = ttk.Label(row, width=12)
            pid_lbl.pack(side=tk.LEFT)
            ttk.Button(row, text="View", width=6,
                       command=lambda n=bot.name: self._on_view(n)).pack(side=tk.RIGHT, padx=2)
            self._rows[bot.name] = {"var": var, "state": state_lbl, "pid": pid_lbl}
        self._update_rows()

    def _update_rows(self):
        for bot in self._manager.bots:
            r = self._rows.get(bot.name)
            if not r:
                continue
            self._manager._refresh_state(bot)
            r["state"].config(text=bot.state.value)
            r["pid"].config(text=f"PID {bot.pid}" if bot.pid else "")

    def _get_checked(self):
        return [b for b in self._manager.bots
                if self._rows.get(b.name, {}).get("var", tk.BooleanVar()).get()]

    def _check_all(self):
        for r in self._rows.values():
            r["var"].set(True)

    def _uncheck_all(self):
        for r in self._rows.values():
            r["var"].set(False)

    def _on_view(self, name: str):
        bot = self._manager.get(name)
        if bot:
            self._manager.attach_viewer(bot)
            self._status.config(text=f"Viewer opened for {name}")

    def _action(self, action: str):
        for bot in self._get_checked():
            try:
                getattr(self._manager, f"{action}_game")(bot)
            except Exception as e:
                self._status.config(text=f"Error on {bot.name}: {e}")
        self._update_rows()

    def _action_all(self, action: str):
        for bot in self._manager.bots:
            try:
                getattr(self._manager, f"{action}_game")(bot)
            except Exception as e:
                self._status.config(text=f"Error on {bot.name}: {e}")
        self._update_rows()

    def _refresh_bots(self):
        self._manager.load_from_prefixes()
        self._build_rows()
        self._status.config(text=f"Refreshed: {len(self._manager.bots)} bots")

    def _setup_statusbar(self):
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_close(self):
        self._manager.stop_all()
        self._tk.destroy()

    def _poll(self):
        self._update_rows()
        self._tk.after(2000, self._poll)

    def run(self):
        self._tk.mainloop()
