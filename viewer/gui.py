import os
import time as _time
import tkinter as tk
from datetime import UTC
from functools import partial
from tkinter import ttk

import numpy as np
from PIL import Image, ImageTk

from gt_spector import audio, overlay, settings
from viewer.tooltip import ToolTip


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
        self._drag_pos: tuple[int, int] | None = None
        self._is_dragging = False
        self._handling_release = False
        self._marker_pick_mode = False
        self._skip_release = False
        self._template_mode = ""
        self._template_poly: list[tuple[int, int]] = []
        self._template_overlay_on = False
        self._last_box: tuple[int, int, int, int] | None = None
        self._last_template_mode = ""
        self._last_redraw = 0.0
        self._last_frame_sample: bytes | None = None
        self._tk.geometry("1152x914")
        self._scale = 1.0
        self._frame_counter = 0
        self._last_shm_counter = -1
        self._fps_start = _time.monotonic()
        self._fps_frames = 0
        self._poll()

    def _setup_menu(self):
        menubar = tk.Menu(self._tk)
        self._tk.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Capture Frame", command=self._capture)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        overlay_menu = tk.Menu(menubar, tearoff=0)
        self._overlay_var = tk.BooleanVar(value=overlay.overlay_enabled(self._display_num()))
        overlay_menu.add_checkbutton(
            label="Show Markers", variable=self._overlay_var,
            command=self._on_overlay_toggle)
        overlay_menu.add_separator()
        overlay_menu.add_command(
            label="Set Marker with Mouse", command=self._on_set_marker_with_mouse)
        overlay_menu.add_command(
            label="Add Marker at Location...", command=self._on_add_marker_at_location)
        overlay_menu.add_command(
            label="Clear Last Marker", command=self._on_clear_last_marker)
        overlay_menu.add_command(
            label="Clear All Markers", command=self._on_clear_all_markers)
        overlay_menu.add_command(label="List Markers", command=self._on_viewer_list_markers)
        menubar.add_cascade(label="Overlay", menu=overlay_menu)

        template_menu = tk.Menu(menubar, tearoff=0)
        self._template_mode_var = tk.StringVar(value="")
        for label, mode in [("Rectangle", "rect"), ("Circle", "circle"), ("Freehand", "freehand")]:
            template_menu.add_radiobutton(
                label=label, variable=self._template_mode_var, value=mode,
                command=partial(self._on_template_mode, mode))
        template_menu.add_separator()
        template_menu.add_command(label="Save Template...", command=self._on_save_template)
        template_menu.add_separator()
        self._template_overlay_var = tk.BooleanVar(value=False)
        template_menu.add_checkbutton(
            label="Show Template Matches", variable=self._template_overlay_var,
            command=self._on_template_overlay_toggle)
        menubar.add_cascade(label="Template", menu=template_menu)

        nav_menu = tk.Menu(menubar, tearoff=0)
        nav_menu.add_command(label="Move Mouse to...", command=self._on_move_mouse_to)
        menubar.add_cascade(label="Navigate", menu=nav_menu)

    def _setup_toolbar(self):
        toolbar = ttk.Frame(self._tk)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        for text, cmd, tip in [
            ("Attach", self._on_attach, "Attach to a session display"),
            ("Detach", self._on_detach, "Detach from the current display"),
            ("Capture", self._capture, "Save the current frame to /tmp"),
            ("Reset Zoom", self._on_reset_zoom, "Reset the window size"),
        ]:
            btn = ttk.Button(toolbar, text=text, command=cmd)
            btn.pack(side=tk.LEFT, padx=2)
            ToolTip(btn, tip)
        ttk.Label(toolbar, text="FPS:").pack(side=tk.LEFT, padx=(10, 2))
        self._fps_var = tk.IntVar(value=self._session.fps)
        self._fps_spin = ttk.Spinbox(
            toolbar, from_=1, to=60, width=4,
            textvariable=self._fps_var,
            command=self._on_fps_change,
        )
        self._fps_spin.pack(side=tk.LEFT, padx=2)
        self._fps_var.trace_add("write", lambda *a: self._on_fps_change())
        ToolTip(self._fps_spin, "Target frame rate (1-60)")
        self._game_pid_env = os.environ.get("GT_SPECTOR_GAME_PID")
        self._sound_btn = ttk.Button(
            toolbar, text=self._sound_label(), command=self._on_sound_toggle)
        self._sound_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self._sound_btn, "Mute / unmute the game's audio")
        quit_btn = ttk.Button(toolbar, text="Quit", command=self._on_close)
        quit_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(quit_btn, "Close this viewer")

    def _display_num(self) -> int:
        return int(self._session.display.lstrip(":"))

    def _game_pid(self) -> int | None:
        from gt_spector.bot_manager import BotManager

        pid = BotManager().find_game_pid_by_display(self._display_num())
        if pid is not None:
            return pid
        if self._game_pid_env:
            try:
                return int(self._game_pid_env)
            except ValueError:
                return None
        return None

    def _on_overlay_toggle(self) -> None:
        overlay.set_overlay_enabled(self._display_num(), self._overlay_var.get())

    def _on_template_mode(self, mode: str) -> None:
        self._template_mode = mode
        self._template_poly = []
        self._status.config(
            text=f"Template mode: {mode} — drag on the frame to define a region")

    def _on_template_overlay_toggle(self) -> None:
        self._template_overlay_on = self._template_overlay_var.get()
        self._status.config(
            text="Template matches ON" if self._template_overlay_on else "Template matches OFF")

    def _on_save_template(self) -> None:
        if self._last_box is None:
            self._status.config(
                text="Pick a Template mode and drag a region on the frame first")
            return
        sx, sy, fx, fy = self._last_box
        self._save_template_from_box(sx, sy, fx, fy, self._last_template_mode)

    def _save_template_from_box(self, sx: int, sy: int, fx: int, fy: int,
                                mode: str | None = None) -> None:
        mode = mode or self._template_mode
        if not mode:
            return
        if mode == "freehand" and self._template_poly:
            x0 = min(px for px, _ in self._template_poly)
            y0 = min(py for _, py in self._template_poly)
            x1 = max(px for px, _ in self._template_poly)
            y1 = max(py for _, py in self._template_poly)
        else:
            x0, y0 = min(sx, fx), min(sy, fy)
            x1, y1 = max(sx, fx), max(sy, fy)
        if x1 - x0 < 1 or y1 - y0 < 1:
            self._status.config(text="Template region too small — drag a larger area")
            return
        import tkinter.simpledialog as sd
        name = sd.askstring("Save Template", "Template name:", parent=self._tk)
        if not name:
            return
        self._last_box = (sx, sy, fx, fy)
        self._last_template_mode = mode
        from gt_spector import templates as T
        frame = self._session.frame
        patch = frame[y0:y1, x0:x1, :3]
        mask: np.ndarray | None = None
        if mode == "circle":
            import cv2
            mask = np.zeros((patch.shape[0], patch.shape[1]), dtype=np.uint8)
            cv2.circle(
                mask, (patch.shape[1] // 2, patch.shape[0] // 2),
                min(patch.shape[1], patch.shape[0]) // 2, 1, thickness=-1)
        elif mode == "freehand" and len(self._template_poly) >= 3:
            import cv2
            mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
            pts = np.array([(px - x0, py - y0) for px, py in self._template_poly],
                           dtype=np.int32)
            cv2.fillPoly(mask, [pts], 1)
        t = T.Template(name=name, shape=mode, x=x0, y=y0,
                       w=x1 - x0, h=y1 - y0, game_version=T.GAME_VERSION,
                       score_threshold=0.75)
        T.save_template(t, patch, mask)
        self._status.config(text=f"Template '{name}' saved")
        self._template_poly = []
        self._template_mode = ""
        self._template_mode_var.set("")

    def _on_set_marker_with_mouse(self) -> None:
        overlay.set_overlay_enabled(self._display_num(), True)
        self._overlay_var.set(True)
        self._marker_pick_mode = True
        self._status.config(text="Left-click on the frame to set a marker")

    def _on_add_marker_at_location(self) -> None:
        import tkinter.simpledialog as sd
        x = sd.askinteger("Add Marker", "x:", parent=self._tk)
        y = sd.askinteger("Add Marker", "y:", parent=self._tk)
        if x is not None and y is not None:
            overlay.add_marker(self._display_num(), x, y, "loc")
            self._status.config(text=f"Marker added at ({x}, {y})")

    def _on_viewer_list_markers(self) -> None:
        win = tk.Toplevel(self._tk)
        win.title("Markers")
        for m in overlay.load_markers(self._display_num()):
            ttk.Label(win, text=f"{m.id} @ ({m.x},{m.y}) label='{m.label}'").pack(anchor=tk.W)

    def _on_clear_last_marker(self) -> None:
        markers = overlay.load_markers(self._display_num())
        if markers:
            last = markers[-1]
            overlay.clear_markers(self._display_num(), last.id)
            self._status.config(text=f"Cleared marker {last.id}")
        else:
            self._status.config(text="No markers to clear")

    def _on_clear_all_markers(self) -> None:
        overlay.clear_markers(self._display_num())
        self._status.config(text="All markers cleared")

    def _on_move_mouse_to(self) -> None:
        import tkinter.simpledialog as sd
        x = sd.askinteger("Move Mouse", "x:", parent=self._tk)
        y = sd.askinteger("Move Mouse", "y:", parent=self._tk)
        if x is not None and y is not None:
            self._session.move_mouse(x, y)
            self._status.config(text=f"Mouse moved to ({x}, {y})")

    def _sound_icon(self) -> str:
        pid = self._game_pid()
        if pid:
            return "🔇" if audio.is_muted(pid) else "🔊"
        return "—"

    def _sound_label(self) -> str:
        return f"{self._sound_icon()} Sound"

    def _on_sound_toggle(self) -> None:
        pid = self._game_pid()
        if not pid:
            self._status.config(text="No game pid for sound control")
            return
        muted = audio.is_muted(pid)
        audio.set_muted(pid, not muted)
        bot_name = overlay.display_to_bot(self._display_num())
        if bot_name:
            settings.set_bot_sound_muted(bot_name, not muted)
        self._sound_btn.config(text=self._sound_label())

    def _setup_canvas(self):
        self._frame = ttk.Frame(self._tk)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._canvas_label = ttk.Label(self._frame, takefocus=True)
        self._frame.columnconfigure(0, weight=1)
        self._frame.rowconfigure(0, weight=1)
        self._canvas_label.grid(sticky="nsew")
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
            shm_changed = self._session.refresh()
            frame = self._session.frame
            h, w = frame.shape[:2]
            now = _time.monotonic()
            # Only redraw when the actual pixel content changed (the game can
            # advance its frame counter on a static screen) AND the throttle
            # allows it. A cheap strided sample detects change without a full
            # compare; the expensive conversion happens only on real changes.
            changed = False
            if shm_changed:
                sample = frame[::32, ::32].tobytes()
                changed = sample != getattr(self, "_last_frame_sample", None)
                if changed:
                    self._last_frame_sample = sample
            dragging_selection = self._template_mode and self._drag_start is not None
            if (changed or dragging_selection) and (now - self._last_redraw) >= 0.066:
                self._last_redraw = now
                frame = overlay.draw_markers(frame, self._display_num())
                frame = self._draw_template_overlay(frame)
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
                self._frame_counter += 1
            # FPS tracking
            self._fps_frames += 1
            actual_fps = self._session.fps
            if self._fps_frames >= max(actual_fps, 5) * 2:
                elapsed = _time.monotonic() - self._fps_start
                fps = self._fps_frames / elapsed if elapsed > 0 else 0
                self._tk.title(f"gt-spector — {self._session.display} — {fps:.0f} FPS")
                self._fps_start = _time.monotonic()
                self._fps_frames = 0
        except Exception as e:  # noqa: BLE001
            self._status.config(text=f"Error: {e}")
        delay = max(50, int(1000 / self._session.fps))
        self._tk.after(delay, self._poll)

    def _draw_template_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Draw live template-match boxes and the in-progress selection preview."""
        preview = self._template_mode and self._drag_start is not None
        if not self._template_overlay_on and not preview:
            return frame
        import cv2
        frame = frame.copy()
        if self._template_overlay_on:
            from gt_spector import templates as T
            from gt_spector.locator import Locator
            loc = getattr(self, "_locator", None)
            if loc is None:
                loc = Locator()
                self._locator = loc
            for t in T.load_templates():
                r = loc.find(frame, t.name)
                if r.found:
                    x0 = r.cx - t.w // 2
                    y0 = r.cy - t.h // 2
                    cv2.rectangle(frame, (x0, y0), (x0 + t.w, y0 + t.h), (255, 0, 255), 1)
        if preview:
            start = self._drag_start
            end = self._drag_pos
            if start is not None and end is not None:
                sx, sy = start
                fx, fy = end
                x0, y0 = min(sx, fx), min(sy, fy)
                x1, y1 = max(sx, fx), max(sy, fy)
                color = (0, 255, 255)
                if self._template_mode == "circle" and x1 - x0 > 0 and y1 - y0 > 0:
                    cv2.ellipse(frame, ((x0 + x1) // 2, (y0 + y1) // 2),
                                ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, color, 1)
                elif self._template_mode == "freehand" and len(self._template_poly) >= 2:
                    pts = np.array(self._template_poly, dtype=np.int32)
                    cv2.polylines(frame, [pts], False, color, 1)
                elif self._template_mode != "freehand":
                    cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1)
        return frame

    def _on_fps_change(self):
        try:
            val = self._fps_var.get()
            if val >= 1:
                self._session.fps = val
        except (ValueError, tk.TclError):
            pass

    def _on_reset_zoom(self):
        self._tk.geometry("1152x914")

    def _on_mouse_move(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        self._last_frame_pos = (fx, fy)
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
        if self._marker_pick_mode:
            self._marker_pick_mode = False
            self._skip_release = True
            overlay.add_marker(self._display_num(), fx, fy, "picked")
            self._status.config(text=f"Marker set at ({fx}, {fy})")
            return
        self._drag_start = (fx, fy)
        self._is_dragging = False
        if self._template_mode:
            self._drag_pos = (fx, fy)
            if self._template_mode == "freehand":
                self._template_poly = [(fx, fy)]
            self._status.config(text=f"Template mode: {self._template_mode} — drag to define region")
            return
        self._session.move_mouse(fx, fy)
        self._session.mouse_down()

    def _on_canvas_drag(self, event):
        if not hasattr(self, "_scale") or self._scale == 0:
            return
        self._is_dragging = True
        fx = int(event.x / self._scale)
        fy = int(event.y / self._scale)
        if self._template_mode:
            self._drag_pos = (fx, fy)
            if self._template_mode == "freehand":
                self._template_poly.append((fx, fy))
            return
        self._session.move_mouse(fx, fy)

    def _on_canvas_release(self, event):
        if self._handling_release or not hasattr(self, "_scale") or self._scale == 0:
            return
        self._handling_release = True
        try:
            if self._skip_release:
                self._skip_release = False
                return
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
            if self._template_mode:
                self._save_template_from_box(sx, sy, fx, fy)
                return
            if was_drag:
                self._session.mouse_up()
                self._status.config(text=f"Drag: ({sx},{sy}) -> ({fx},{fy})")
            else:
                self._session.mouse_up()
                now = _time.monotonic()
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
        except Exception as e:  # noqa: BLE001
            self._status.config(text=f"Attach error: {e}")

    def _on_detach(self):
        self._session.detach()
        self._tk.title("gt-spector — detached")
        self._status.config(text="Detached")

    def _on_close(self):
        pid = self._game_pid()
        if pid:
            try:
                if settings.sound_mode() == "viewer":
                    audio.set_muted(pid, True)
            except (ValueError, OSError):
                pass
        self._running = False
        self._tk.destroy()

    def run(self):
        self._tk.mainloop()


def run_gui(session):
    w = ViewerWindow(session)
    w.run()
