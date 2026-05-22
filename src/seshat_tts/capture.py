from __future__ import annotations

import ctypes
from dataclasses import dataclass

import mss
from PIL import Image
import win32gui
import win32ui

from .config import Rect


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    index: int
    left: int
    top: int
    width: int
    height: int

    @property
    def label(self) -> str:
        return f"{self.index}: {self.width}x{self.height} at {self.left},{self.top}"


def list_monitors() -> list[MonitorInfo]:
    with mss.mss() as sct:
        return [
            MonitorInfo(
                index=index,
                left=int(monitor["left"]),
                top=int(monitor["top"]),
                width=int(monitor["width"]),
                height=int(monitor["height"]),
            )
            for index, monitor in enumerate(sct.monitors)
            if index != 0
        ]


def capture_absolute_region(left: int, top: int, width: int, height: int) -> Image.Image:
    with mss.mss() as sct:
        grab = {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }
        shot = sct.grab(grab)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def capture_monitor_region(monitor_index: int, rect: Rect) -> Image.Image:
    with mss.mss() as sct:
        if monitor_index <= 0 or monitor_index >= len(sct.monitors):
            raise ValueError(f"Monitor {monitor_index} is not available.")
        monitor = sct.monitors[monitor_index]
        return capture_absolute_region(
            int(monitor["left"]) + rect.left,
            int(monitor["top"]) + rect.top,
            rect.width,
            rect.height,
        )


def capture_window_region(hwnd: int, rect: Rect) -> Image.Image:
    image = capture_window(hwnd)
    if rect.left < 0 or rect.top < 0 or rect.width <= 0 or rect.height <= 0:
        raise ValueError("Capture region must be inside the selected window.")
    if rect.left + rect.width > image.width or rect.top + rect.height > image.height:
        raise ValueError("Capture region is outside the selected window. Select the region again in window mode.")
    return image.crop((rect.left, rect.top, rect.left + rect.width, rect.top + rect.height))


def capture_window(hwnd: int) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("Selected window has no capturable size.")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)

    try:
        result = _print_window(hwnd, memory_dc.GetSafeHdc(), 2)
        if result != 1:
            result = _print_window(hwnd, memory_dc.GetSafeHdc(), 0)
        if result != 1:
            raise RuntimeError("PrintWindow failed for the selected window.")

        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        return Image.frombuffer(
            "RGB",
            (info["bmWidth"], info["bmHeight"]),
            bits,
            "raw",
            "BGRX",
            0,
            1,
        ).copy()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)


def _print_window(hwnd: int, hdc: int, flags: int) -> int:
    return int(ctypes.windll.user32.PrintWindow(hwnd, hdc, flags))
