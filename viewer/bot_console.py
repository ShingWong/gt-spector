import tkinter as tk
from tkinter import ttk

from gt_spector.bot_manager import Bot, BotManager, BotState


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
        file_menu.add_command(label="Refresh", command=self._refresh)
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

    def _setup_bot_list(self):
        frame = ttk.Frame(self._tk)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        ttk.Label(frame, text="Bots", font=("", 11, "bold")).pack(anchor=tk.W)

        self._checkboxes: dict[str, tk.BooleanVar] = {}
        self._list_frame = ttk.Frame(frame)
        self._list_frame.pack(fill=tk.BOTH, expand=True)

        self._rebuild_list()

    def _setup_statusbar(self):
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _rebuild_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._checkboxes.clear()

        for bot in self._manager.bots:
            row = ttk.Frame(self._list_frame)
            row.pack(fill=tk.X, pady=1)

            var = tk.BooleanVar()
            self._checkboxes[bot.name] = var
            cb = ttk.Checkbutton(row, variable=var, width=2)
            cb.pack(side=tk.LEFT)

            state_label = {"Offline": "⚫", "Running": "🟢", "Starting": "🟡", "Paused": "🟠", "Error": "🔴"}.get(
                bot.state.value, "⚪"
            )
            ttk.Label(row, text=state_label, width=2).pack(side=tk.LEFT)
            ttk.Label(row, text=f"{bot.name}", width=8).pack(side=tk.LEFT)
            ttk.Label(row, text=f":{bot.display}", width=6).pack(side=tk.LEFT)
            ttk.Label(row, text=bot.state.value, width=10).pack(side=tk.LEFT)

            btn = ttk.Button(row, text="View", width=6,
                             command=lambda n=bot.name: self._on_view(n))
            btn.pack(side=tk.RIGHT, padx=2)

            if bot.pid:
                ttk.Label(row, text=f"PID {bot.pid}", width=10).pack(side=tk.RIGHT)

    def _get_checked(self) -> list[Bot]:
        return [b for b in self._manager.bots if self._checkboxes.get(b.name, tk.BooleanVar()).get()]

    def _on_view(self, name: str):
        bot = self._manager.get(name)
        if bot:
            self._manager.attach_viewer(bot)
            self._status.config(text=f"Viewer opened for {name}")

    def _action(self, action: str):
        for bot in self._get_checked():
            if action == "start":
                self._manager.start_game(bot)
            elif action == "stop":
                self._manager.stop_game(bot)
            elif action == "restart":
                self._manager.restart_game(bot)
        self._rebuild_list()

    def _action_all(self, action: str):
        for bot in self._manager.bots:
            if action == "start":
                self._manager.start_game(bot)
            elif action == "stop":
                self._manager.stop_game(bot)
            elif action == "restart":
                self._manager.restart_game(bot)
        self._rebuild_list()

    def _refresh(self):
        self._manager.load_from_prefixes()
        self._rebuild_list()
        self._status.config(text=f"Refreshed: {len(self._manager.bots)} bots")

    def _on_close(self):
        self._manager.stop_all()
        self._tk.destroy()

    def _poll(self):
        for bot in self._manager.bots:
            self._manager._refresh_state(bot)
        self._rebuild_list()
        self._tk.after(2000, self._poll)

    def run(self):
        self._rebuild_list()
        self._tk.mainloop()
