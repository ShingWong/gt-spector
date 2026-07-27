import tkinter as tk
from datetime import UTC
from tkinter import ttk

from PIL import Image, ImageTk


class ViewerWindow:
    def __init__(self, session):
        self._session = session
        self._tk = tk.Tk()
        self._tk.title(f"gt-spector — {session.display}")
        self._setup_menu()
        self._setup_toolbar()
        self._setup_canvas()
        self._setup_statusbar()
        self._running = True
        self._tk.protocol("WM_DELETE_WINDOW", self._on_close)
        self._last_click_time = 0.0
        self._drag_start = None
        self._poll()

    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Capture Frame", command=self._capture)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(toolbar, text="Attach", command=self._on_attach).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Detach", command=self._on_detach).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Capture", command=self._capture).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Quit", command=self._on_close).pack(side=tk.LEFT, padx=2)

    def _setup_canvas(self):
        self._frame = ttk.Frame(self._tk)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._canvas_label = ttk.Label(self._frame, takefocus=True)
        self._canvas_label.pack()
        self._canvas_label.bind("<Motion>", self._on_mouse_move)
        self._canvas_label.bind("<ButtonPress-1>", self._on_canvas_click)
        self._canvas_label.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._tk.bind("<ButtonRelease-1>", lambda e: self._on_canvas_release(e) if self._drag_start else None)
        self._canvas_label.bind("<Button-3>", self._on_canvas_right_click)
        self._canvas_label.bind("<ButtonRelease-3>", self._on_canvas_right_release)
        self._tk.bind("<ButtonRelease-3>", lambda e: self._on_canvas_right_release(e) if self._drag_start else None)
        self._canvas_label.bind("<Key>", self._on_key)

    def _setup_statusbar(self):
        self._status = ttk.Label(
            self._tk, text="Ready", relief=tk.SUNKEN, anchor=tk.W
        )
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

    def _poll(self):
        if not self._running:
            return
        try:
            self._session.refresh()
            frame = self._session.frame
            h, w = frame.shape[:2]
            max_size = 800
            scale = min(max_size / w, max_size / h, 1.0)
            nw, nh = int(w * scale), int(h * scale)
            img = Image.fromarray(frame).resize((nw, nh), Image.Resampling.NEAREST)
            self._tk_photo = ImageTk.PhotoImage(img)
            self._canvas_label.config(image=self._tk_photo)
            self._img_w, self._img_h = nw, nh
            self._scale = scale
        except Exception as e:  # noqa: BLE001
            self._status.config(text=f"Error: {e}")
        delay = max(50, int(1000 / self._session.fps))
        self._tk.after(delay, self._poll)

    def _on_mouse_move(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        try:
            r, g, b = self._session.get_pixel(fx, fy)
            self._status.config(text=f"Pixel: ({fx}, {fy}) -> RGB({r}, {g}, {b})")
        except (IndexError, ValueError):
            pass

    def _on_canvas_click(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        self._canvas_label.focus_set()
        # Store start position — if released without motion, it's a click
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._drag_start = (fx, fy)

    def _on_canvas_release(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        if event.widget is not self._canvas_label:
            cx = event.x_root - self._canvas_label.winfo_rootx()
            cy = event.y_root - self._canvas_label.winfo_rooty()
        else:
            cx, cy = event.x, event.y
        fx = int(cx / self._scale)
        fy = int(cy / self._scale)
        fy = int(event.y / self._scale)
        sx, sy = getattr(self, "_drag_start", (fx, fy))
        self._drag_start = None
        if sx == fx and sy == fy:
            import time
            now = time.monotonic()
            if now - self._last_click_time < 0.5:
                self._session.click(fx, fy, speed=800)
                self._session.click(fx, fy, speed=800)
                self._status.config(text=f"Double-click: ({fx}, {fy})")
                self._last_click_time = 0.0
            else:
                self._session.click(fx, fy)
                self._status.config(text=f"Click: ({fx}, {fy})")
                self._last_click_time = now
        else:
            self._session.drag(sx, sy, fx, fy)
            self._status.config(text=f"Drag: ({sx},{sy}) -> ({fx},{fy})")

    def _on_canvas_right_click(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._drag_start = (fx, fy)

    def _on_canvas_right_release(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        if event.widget is not self._canvas_label:
            cx = event.x_root - self._canvas_label.winfo_rootx()
            cy = event.y_root - self._canvas_label.winfo_rooty()
        else:
            cx, cy = event.x, event.y
        fx = int(cx / self._scale)
        fy = int(cy / self._scale)
        sx, sy = getattr(self, "_drag_start", (fx, fy))
        self._drag_start = None
        dx = abs(fx - sx)
        dy = abs(fy - sy)
        if dx == 0 and dy == 0:
            return
        self._session.move_mouse(fx, fy)
        self._status.config(text=f"Move: ({sx},{sy}) -> ({fx},{fy})")

    def _on_key(self, event):
        if event.char and event.char.isprintable():
            self._session.type_text(event.char)
        elif event.keysym == "Return":
            self._session.key_press("Return")
        elif event.keysym == "Tab":
            self._session.key_press("Tab")
        elif event.keysym == "Escape":
            self._session.key_press("Escape")
        elif event.keysym == "BackSpace":
            self._session.key_press("BackSpace")
        elif event.keysym == "Delete":
            self._session.key_press("Delete")
        elif event.keysym in ("Up", "Down", "Left", "Right"):
            self._session.key_press(event.keysym)
        self._status.config(text=f"Key: {event.keysym}")

    def _capture(self):
        from datetime import datetime

        path = (
            f"/tmp/gt-spector-capture-{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.png"
        )
        img = Image.fromarray(self._session.frame)
        img.save(path)
        self._status.config(text=f"Captured: {path}")

    def _on_attach(self):
        import tkinter.simpledialog
        display = tkinter.simpledialog.askstring(
            "Attach Session", "Display (e.g. :9):", parent=self._tk)
        if not display:
            return
        source = f"shm://{display.lstrip(':')}"
        try:
            self._session.attach(display, source)
            self._tk.title(f"gt-spector — {display}")
            self._status.config(text=f"Attached: {display}")
        except Exception as e:
            self._status.config(text=f"Attach error: {e}")

    def _on_detach(self):
        self._session.detach()
        self._tk.title("gt-spector — detached")
        self._status.config(text="Detached")

    def _on_close(self):
        self._running = False
        self._tk.destroy()

    def run(self):
        self._tk.mainloop()


def run_gui(session):
    w = ViewerWindow(session)
    w.run()
