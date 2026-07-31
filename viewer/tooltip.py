"""Shared hover tooltip for Tk widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


class ToolTip:
    """Simple hover tooltip for a widget."""

    def __init__(self, widget: Any, text: str = "") -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def set_text(self, text: str) -> None:
        self._text = text

    def _show(self, _event: Any = None) -> None:
        if not self._text:
            return
        x = self._widget.winfo_rootx() + 16
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = ttk.Label(self._tip, text=self._text, background="#ffffe0",
                        relief=tk.SOLID, borderwidth=1)
        lbl.pack()

    def _hide(self, _event: Any = None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
