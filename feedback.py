"""Audio feedback via winsound (Windows only)."""

import threading


def _beep(frequency: int, duration_ms: int):
    """Play a beep in a background thread so it doesn't block."""
    try:
        import winsound
        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass  # Silently ignore on non-Windows or if audio fails


def beep_start():
    """Short high-pitched beep to signal recording start."""
    threading.Thread(target=_beep, args=(800, 150), daemon=True).start()


def beep_stop():
    """Short low-pitched beep to signal recording stop."""
    threading.Thread(target=_beep, args=(400, 150), daemon=True).start()
