from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from PIL import ImageEnhance, ImageTk

from .capture import capture_absolute_region
from .config import Rect


class RegionPicker(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        bounds: Rect,
        on_selected: Callable[[Rect], None],
    ) -> None:
        super().__init__(parent)
        self._bounds = bounds
        self._on_selected = on_selected
        self._start_x = 0
        self._start_y = 0
        self._rect_id: int | None = None
        self._label_id: int | None = None

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{bounds.width}x{bounds.height}{bounds.left:+d}{bounds.top:+d}")
        self.configure(cursor="crosshair")

        screenshot = capture_absolute_region(bounds.left, bounds.top, bounds.width, bounds.height)
        dimmed = ImageEnhance.Brightness(screenshot).enhance(0.55)
        self._image = ImageTk.PhotoImage(dimmed)

        self.canvas = tk.Canvas(self, bg="#050608", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, image=self._image, anchor=tk.NW)
        self.canvas.create_text(
            18,
            18,
            text="Drag to select. Esc cancels.",
            fill="#f4f7fb",
            anchor=tk.NW,
            font=("Segoe UI", 12, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda _event: self.destroy())

        self.focus_force()
        self.grab_set()

    def _on_press(self, event: tk.Event) -> None:
        self._start_x = int(event.x)
        self._start_y = int(event.y)
        self._rect_id = self.canvas.create_rectangle(
            self._start_x,
            self._start_y,
            self._start_x,
            self._start_y,
            outline="#ff365f",
            width=3,
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self._rect_id is not None:
            x1, x2 = sorted((self._start_x, int(event.x)))
            y1, y2 = sorted((self._start_y, int(event.y)))
            self.canvas.coords(self._rect_id, x1, y1, x2, y2)
            label = f"{x2 - x1} x {y2 - y1}"
            if self._label_id is None:
                self._label_id = self.canvas.create_text(
                    x1 + 8,
                    max(12, y1 - 18),
                    text=label,
                    fill="#f4f7fb",
                    anchor=tk.W,
                    font=("Segoe UI", 10, "bold"),
                )
            else:
                self.canvas.coords(self._label_id, x1 + 8, max(12, y1 - 18))
                self.canvas.itemconfigure(self._label_id, text=label)

    def _on_release(self, event: tk.Event) -> None:
        x1, x2 = sorted((self._start_x, int(event.x)))
        y1, y2 = sorted((self._start_y, int(event.y)))
        self.grab_release()
        self.destroy()
        if x2 - x1 < 4 or y2 - y1 < 4:
            return
        self._on_selected(
            Rect(
                left=self._bounds.left + x1,
                top=self._bounds.top + y1,
                width=x2 - x1,
                height=y2 - y1,
            )
        )
