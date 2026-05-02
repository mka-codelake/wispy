"""Global hotkey listener using the keyboard library.

Supports two modes:
  - hold:   Record while the hotkey is held down.
  - toggle: First press starts recording, second press stops.
"""

import threading
from typing import Callable

import keyboard


class HotkeyListener:
    """Listens for a global hotkey and calls on_start / on_stop callbacks."""

    def __init__(
        self,
        hotkey: str = "F9",
        mode: str = "hold",
        on_start: Callable | None = None,
        on_stop: Callable | None = None,
    ):
        self.hotkey = hotkey
        self.mode = mode
        self._on_start = on_start or (lambda: None)
        self._on_stop = on_stop or (lambda: None)
        self._recording = False
        self._lock = threading.Lock()

    def _handle_hold_down(self, event):
        with self._lock:
            if not self._recording:
                self._recording = True
                self._on_start()

    def _handle_hold_up(self, event):
        with self._lock:
            if self._recording:
                self._recording = False
                self._on_stop()

    def _handle_toggle(self, event):
        with self._lock:
            if not self._recording:
                self._recording = True
                self._on_start()
            else:
                self._recording = False
                self._on_stop()

    def start(self):
        """Register the hotkey hooks. Blocks until keyboard.wait() or external stop."""
        if self.mode == "hold":
            keyboard.on_press_key(self.hotkey, self._handle_hold_down, suppress=False)
            keyboard.on_release_key(self.hotkey, self._handle_hold_up, suppress=False)
        else:
            keyboard.on_press_key(self.hotkey, self._handle_toggle, suppress=False)

    def stop(self):
        """Unhook all keyboard listeners."""
        keyboard.unhook_all()
