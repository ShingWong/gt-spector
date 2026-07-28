import tkinter as tk
from tkinter import ttk

from gt_spector.bot_manager import BotManager, BotState


class BotConsole:
    def __init__(self):
        self._manager = BotManager()
        self._manager.load_from_prefixes()

        self._tk = tk.Tk()
        self._tk.title("gt-spector — Bot Console")
        self._tk.geometry("500x500")

        self._setup_menu()
        self._setup_toolbar()
        self._setup_bot_list()
        self._setup_statusbar()

        self._poll()
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)

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

        ttk.Button(toolbar, text="Start", command=lambda: self._action("start")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop", command=lambda: self._action("stop")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Restart", command=lambda: self._action("restart")).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Start All", command=lambda: self._action_all("start")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop All", command=lambda: self._action_all("stop")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Restart All", command=lambda: self._action_all("restart")).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Check All", command=self._check_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Uncheck All", command=self._uncheck_all).pack(side=tk.LEFT, padx=2)

    def _setup_bot_list(self):
        frame = ttk.Frame(self._tk)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        ttk.Label(frame, text="Bots", font=("", 11, "bold")).pack(anchor=tk.W)

        # Scrollable area
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
            cb = ttk.Checkbutton(row, variable=var, width=2)
            cb.pack(side=tk.LEFT)

            icon = ttk.Label(row, width=2)
            icon.pack(side=tk.LEFT)

            name_lbl = ttk.Label(row, text=bot.name, width=8)
            name_lbl.pack(side=tk.LEFT)

            disp_lbl = ttk.Label(row, text=f":{bot.display}", width=6)
            disp_lbl.pack(side=tk.LEFT)

            state_lbl = ttk.Label(row, width=10)
            state_lbl.pack(side=tk.LEFT)

            pid_lbl = ttk.Label(row, width=12)
            pid_lbl.pack(side=tk.LEFT)

            view_btn = ttk.Button(row, text="View", width=6,
                                  command=lambda n=bot.name: self._on_view(n))
            view_btn.pack(side=tk.RIGHT, padx=2)

            self._rows[bot.name] = {
                "var": var, "icon": icon, "name": name_lbl,
                "disp": disp_lbl, "state": state_lbl, "pid": pid_lbl,
            }

        self._update_rows()

    def _update_rows(self):
        icons = {s.value: s.value[0] for s in BotState}
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
            getattr(self._manager, f"{action}_game")(bot)
        self._update_rows()

    def _action_all(self, action: str):
        for bot in self._manager.bots:
            getattr(self._manager, f"{action}_game")(bot)
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
