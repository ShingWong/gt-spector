import tkinter as tk
from tkinter import ttk

from gt_spector.bot_manager import Bot, BotManager, BotState


class BotConsole:
    def __init__(self):
        self._manager = BotManager()
        self._manager.load_from_prefixes()

        self._tk = tk.Tk()
        self._tk.title("gt-spector — Bot Console")
        self._tk.geometry("1100x700")

        self._setup_menu()
        self._setup_toolbar()
        self._setup_panels()
        self._setup_statusbar()

        self._selected: set[str] = set()
        self._poll()
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Provision New Bot", command=self._on_provision)
        file_menu.add_separator()
        file_menu.add_command(label="Refresh", command=self._refresh)
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="Start Selected", command=lambda: self._action("start")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop Selected", command=lambda: self._action("stop")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Restart Selected", command=lambda: self._action("restart")).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Select All", command=self._on_select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Deselect All", command=self._on_deselect_all).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Start All", command=lambda: self._action_all("start")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop All", command=lambda: self._action_all("stop")).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Restart All", command=lambda: self._action_all("restart")).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(toolbar, text="Run Script", command=self._on_run_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Pause Script", command=self._on_pause_script).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Resume Script", command=self._on_resume_script).pack(side=tk.LEFT, padx=2)

    def _setup_panels(self):
        paned = ttk.PanedWindow(self._tk, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, width=400)
        paned.add(left, weight=1)

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        # Bot list
        ttk.Label(left, text="Bots", font=("", 11, "bold")).pack(anchor=tk.W, padx=4, pady=2)
        self._tree = ttk.Treeview(
            left, columns=("state", "display", "pid"),
            show="tree headings", selectmode="extended", height=20,
        )
        self._tree.heading("#0", text="Name")
        self._tree.heading("state", text="State")
        self._tree.heading("display", text="Display")
        self._tree.heading("pid", text="PID")
        self._tree.column("#0", width=120)
        self._tree.column("state", width=100)
        self._tree.column("display", width=60)
        self._tree.column("pid", width=80)
        self._tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)

        scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Attach view area
        ttk.Label(right, text="Attached Bot View", font=("", 11, "bold")).pack(anchor=tk.W, padx=4, pady=2)
        self._attach_frame = ttk.Frame(right)
        self._attach_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self._attach_label = ttk.Label(self._attach_frame, text="Select a bot to view")
        self._attach_label.pack(expand=True)

    def _setup_statusbar(self):
        self._status = ttk.Label(self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _refresh(self):
        self._manager.load_from_prefixes()
        self._rebuild_tree()
        self._status.config(text=f"Refreshed: {len(self._manager.bots)} bots")

    def _rebuild_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for bot in self._manager.bots:
            self._tree.insert(
                "", tk.END, iid=bot.name,
                text=bot.name,
                values=(bot.state.value, f":{bot.display}", bot.pid or ""),
            )

    def _on_select_all(self):
        self._tree.selection_set(self._tree.get_children())
        self._selected = set(self._tree.selection())
        self._status.config(text=f"Selected all {len(self._selected)} bots")

    def _on_deselect_all(self):
        self._tree.selection_remove(self._tree.selection())
        self._selected.clear()
        self._status.config(text="No bots selected")

    def _on_tree_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            if item in self._selected:
                self._tree.selection_remove(item)
                self._selected.discard(item)
            else:
                self._tree.selection_add(item)
                self._selected.add(item)
            self._on_select(event)

    def _on_select(self, event):
        self._selected = set(self._tree.selection())
        count = len(self._selected)
        if count == 0:
            self._status.config(text="Ready")
            self._attach_label.config(text="No bot selected")
        elif count == 1:
            name = list(self._selected)[0]
            bot = self._manager.get(name)
            self._status.config(text=f"Selected: {name} ({bot.state.value})")
            # Launch viewer for this bot
            if bot:
                self._manager.attach_viewer(bot)
                self._attach_label.config(text=f"Viewer opened for {name} on :{bot.display}")
        else:
            self._status.config(text=f"Selected: {count} bots")

    def _action(self, action: str):
        for name in self._selected:
            bot = self._manager.get(name)
            if not bot:
                continue
            if action == "start":
                self._manager.start_game(bot)
            elif action == "stop":
                self._manager.stop_game(bot)
            elif action == "restart":
                self._manager.restart_game(bot)
        self._rebuild_tree()

    def _action_all(self, action: str):
        for bot in self._manager.bots:
            if action == "start":
                self._manager.start_game(bot)
            elif action == "stop":
                self._manager.stop_game(bot)
            elif action == "restart":
                self._manager.restart_game(bot)
        self._rebuild_tree()

    def _on_run_script(self):
        self._status.config(text="Run Script — coming soon")

    def _on_pause_script(self):
        for name in self._selected:
            bot = self._manager.get(name)
            if bot:
                bot.script_paused = True
        self._status.config(text="Script paused on selected bots")

    def _on_resume_script(self):
        for name in self._selected:
            bot = self._manager.get(name)
            if bot:
                bot.script_paused = False
        self._status.config(text="Script resumed on selected bots")

    def _on_provision(self):
        self._status.config(text="Provision dialog — coming soon")

    def _on_close(self):
        self._manager.stop_all()
        self._tk.destroy()

    def _poll(self):
        for bot in self._manager.bots:
            self._manager._refresh_state(bot)
        self._rebuild_tree()
        self._tk.after(2000, self._poll)

    def run(self):
        self._rebuild_tree()
        self._tk.mainloop()
