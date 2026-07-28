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
        self._is_dragging = False
        self._handling_release = False
        self._tk.geometry("1152x720")
        self._scale = 1.0
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
        ttk.Button(toolbar, text="Reset Zoom", command=self._on_reset_zoom).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Quit", command=self._on_close).pack(side=tk.LEFT, padx=2)

    def _setup_canvas(self):
        self._frame = ttk.Frame(self._tk)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._canvas_label = ttk.Label(self._frame, takefocus=True)
        self._frame.columnconfigure(0, weight=1)
        self._frame.rowconfigure(0, weight=1)
        self._canvas_label.grid()
        self._canvas_label.bind("<Motion>", self._on_mouse_move)
        self._canvas_label.bind("<ButtonPress-1>", self._on_canvas_click)
        self._canvas_label.bind("<B1-Motion>", self._on_canvas_drag)
        self._canvas_label.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._tk.bind("<ButtonRelease-1>", lambda e: self._on_canvas_release(e) if self._drag_start else None)
        self._canvas_label.bind("<ButtonPress-3>", self._on_canvas_right_click)
        self._canvas_label.bind("<B3-Motion>", self._on_canvas_right_drag)
        self._canvas_label.bind("<ButtonRelease-3>", self._on_canvas_right_release)
        self._tk.bind("<ButtonRelease-3>", lambda e: self._on_canvas_right_release(e) if self._drag_start else None)
        self._canvas_label.bind("<ButtonPress-2>", lambda e: self._session._input.middle_click(int(e.x/self._scale), int(e.y/self._scale)))
        self._canvas_label.bind("<MouseWheel>", self._on_scroll)
        self._canvas_label.bind("<Button-4>", lambda e: self._on_scroll_at(e, 1))
        self._canvas_label.bind("<Button-5>", lambda e: self._on_scroll_at(e, -1))
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
            self._tk.update_idletasks()
            fw = max(self._frame.winfo_width(), 50)
            fh = max(self._frame.winfo_height(), 50)
            scale = min(fw / w, fh / h)
            nw, nh = max(int(w * scale), 50), max(int(h * scale), 50)
            img = Image.fromarray(frame).resize((nw, nh), Image.Resampling.NEAREST)
            self._tk_photo = ImageTk.PhotoImage(img)
            self._canvas_label.config(image=self._tk_photo)
            self._img_w, self._img_h = nw, nh
            self._scale = scale
        except Exception as e:  # noqa: BLE001
            self._status.config(text=f"Error: {e}")
        delay = max(50, int(1000 / self._session.fps))
        self._tk.after(delay, self._poll)

    def _on_reset_zoom(self):
        self._tk.geometry("1152x720")

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
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._drag_start = (fx, fy)
        self._is_dragging = False
        self._session.move_mouse(fx, fy)
        self._session.mouse_down()

    def _on_canvas_drag(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        self._is_dragging = True
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._session.move_mouse(fx, fy)

    def _on_canvas_release(self, event):
        if self._handling_release or not hasattr(self, "_scale") or self._scale == 0:
            return
        self._handling_release = True
        try:
            if event.widget is not self._canvas_label:
                cx = event.x_root - self._canvas_label.winfo_rootx()
                cy = event.y_root - self._canvas_label.winfo_rooty()
            else:
                cx, cy = event.x, event.y
            fx = int(cx / self._scale)
            fy = int(cy / self._scale)
            sx, sy = self._drag_start or (fx, fy)
            was_drag = self._is_dragging
            self._is_dragging = False
            self._drag_start = None
            if was_drag:
                self._session.mouse_up()
                self._status.config(text=f"Drag: ({sx},{sy}) -> ({fx},{fy})")
            else:
                import time
                self._session.mouse_up()
                now = time.monotonic()
                if now - self._last_click_time < 0.5:
                    self._session._input.double_click(fx, fy)
                    self._status.config(text=f"Double-click: ({fx}, {fy})")
                    self._last_click_time = 0.0
                else:
                    self._last_click_time = now
                    self._status.config(text=f"Click: ({fx}, {fy})")
        finally:
            self._handling_release = False

    def _on_canvas_right_click(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._drag_start = (fx, fy)
        self._is_dragging = False

    def _on_canvas_right_drag(self, event):
        if not hasattr(self, '_scale') or self._scale == 0:
            return
        self._is_dragging = True
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._session.move_mouse(fx, fy)

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
        was_drag = self._is_dragging
        self._is_dragging = False
        self._drag_start = None
        dx = abs(fx - sx)
        dy = abs(fy - sy)
        if was_drag or dx >= 5 or dy >= 5:
            self._session._input.drag_right(sx, sy, fx, fy)
            self._status.config(text=f"Right-drag: ({sx},{sy}) -> ({fx},{fy})")
        else:
            self._session._input.click_right(fx, fy)
            self._status.config(text=f"Right-click: ({fx}, {fy})")

    def _on_scroll(self, event):
        direction = 1 if event.delta > 0 else -1
        clicks = max(1, abs(event.delta) // 120)
        fx = int(event.x / self._scale) if hasattr(self, "_scale") and self._scale else 0
        fy = int(event.y / self._scale) if hasattr(self, "_scale") and self._scale else 0
        self._session.move_mouse(fx, fy)
        self._session._input.scroll(direction, clicks)
        self._status.config(text=f"Scroll: {'up' if direction > 0 else 'down'}")

    def _on_scroll_at(self, event, direction: int):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._session.move_mouse(fx, fy)
        self._session._input.scroll(direction, 2)

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
