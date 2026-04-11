"""Insert text at cursor position via clipboard paste."""

import time

import keyboard
import pyperclip


def type_text(text: str, restore_clipboard: bool = True):
    """Put text into the clipboard, simulate Ctrl+V, optionally restore old clipboard."""
    if not text:
        return

    old_clipboard = None
    if restore_clipboard:
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = None

    pyperclip.copy(text)
    # Small delay to ensure clipboard is ready
    time.sleep(0.05)
    keyboard.send("ctrl+v")

    if restore_clipboard and old_clipboard is not None:
        # Wait for the paste to complete before restoring
        time.sleep(0.3)
        pyperclip.copy(old_clipboard)
