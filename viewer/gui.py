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
        ttk.Button(toolbar, text="Capture", command=self._capture).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="Quit", command=self._on_close).pack(
            side=tk.LEFT, padx=2
        )

    def _setup_canvas(self):
        self._frame = ttk.Frame(self._tk)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._canvas_label = ttk.Label(self._frame)
        self._canvas_label.pack()
        self._canvas_label.bind("<Motion>", self._on_mouse_move)

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
            img = Image.fromarray(frame).resize((nw, nh), Image.NEAREST)
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

    def _capture(self):
        from datetime import datetime

        path = (
            f"/tmp/gt-spector-capture-{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.png"
        )
        img = Image.fromarray(self._session.frame)
        img.save(path)
        self._status.config(text=f"Captured: {path}")

    def _on_close(self):
        self._running = False
        self._tk.destroy()

    def run(self):
        self._tk.mainloop()


def run_gui(session):
    w = ViewerWindow(session)
    w.run()
