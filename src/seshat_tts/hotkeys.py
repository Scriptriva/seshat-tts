from __future__ import annotations

from collections.abc import Callable

import keyboard


class HotkeyManager:
    def __init__(self) -> None:
        self._handles: dict[str, object] = {}

    def register(self, name: str, hotkey: str, callback: Callable[[], None]) -> None:
        self.unregister(name)
        if not hotkey.strip():
            return
        self._handles[name] = keyboard.add_hotkey(hotkey, callback, suppress=False, trigger_on_release=False)

    def unregister(self, name: str | None = None) -> None:
        if name is not None:
            handle = self._handles.pop(name, None)
            if handle is not None:
                keyboard.remove_hotkey(handle)
            return
        for handle in self._handles.values():
            keyboard.remove_hotkey(handle)
        self._handles.clear()


def listen_for_hotkey() -> str:
    return keyboard.read_hotkey(suppress=False)
