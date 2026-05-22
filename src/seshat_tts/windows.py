from __future__ import annotations

from dataclasses import dataclass

import win32gui


@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def label(self) -> str:
        return f"{self.title} [{self.width}x{self.height} at {self.left},{self.top}]"


def _is_candidate(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd):
        return False
    title = win32gui.GetWindowText(hwnd).strip()
    if not title:
        return False
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return (right - left) > 50 and (bottom - top) > 50


def list_visible_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []

    def callback(hwnd: int, _extra: object) -> None:
        if _is_candidate(hwnd):
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            windows.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=win32gui.GetWindowText(hwnd).strip(),
                    left=left,
                    top=top,
                    right=right,
                    bottom=bottom,
                )
            )

    win32gui.EnumWindows(callback, None)
    windows.sort(key=lambda item: item.title.casefold())
    return windows


def find_window_by_title(title: str) -> WindowInfo | None:
    title = title.strip()
    if not title:
        return None
    for window in list_visible_windows():
        if window.title == title:
            return window
    needle = title.casefold()
    return next((window for window in list_visible_windows() if needle in window.title.casefold()), None)
