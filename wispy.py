"""wispy -- Minimal local push-to-talk dictation tool.

Usage:
    python wispy.py [--config path/to/config.yaml]
"""

import argparse
import ctypes
import os
import queue
import sys
import threading
from pathlib import Path


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _elevate_and_exit() -> None:
    """Relaunch wispy with admin rights via ShellExecute('runas', ...).

    The `keyboard` library needs admin rights for its global hook on most
    Windows systems. We relaunch ourselves with runas so the UAC prompt
    appears exactly once per start. When already elevated this is skipped.
    """
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
    except Exception as e:
        print(f"[wispy] Auto-elevation failed: {e}")
        print("[wispy] Please start wispy as Administrator manually.")
        sys.exit(1)
    sys.exit(0)


if sys.platform == "win32" and not _is_admin():
    _elevate_and_exit()


# Imports that touch native libraries happen only after elevation, so the
# elevated process is the one that actually loads them.
from audio import Recorder  # noqa: E402
from config import Config, default_config_path, load_config  # noqa: E402
from feedback import beep_start, beep_stop  # noqa: E402
from hotkey import HotkeyListener  # noqa: E402
from model_fetch import ensure_model_available  # noqa: E402
from output import type_text  # noqa: E402
from paths import get_app_dir, resolve_model_path  # noqa: E402

MIN_DURATION_SEC = 0.3


def main():
    parser = argparse.ArgumentParser(description="wispy -- local push-to-talk dictation")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config_path = args.config or default_config_path()
    app_dir = get_app_dir()
    cfg: Config = load_config(config_path)
    model_path = resolve_model_path(cfg.model_name, cfg.model_path)

    print(f"[wispy] app_dir     = {app_dir}")
    print(f"[wispy] config      = {config_path} "
          f"({'found' if config_path.exists() else 'defaults'})")
    print(f"[wispy] model_path  = {model_path}")
    print(f"[wispy] hotkey={cfg.hotkey}, mode={cfg.record_mode}, "
          f"model={cfg.model_name}, device={cfg.device}, lang={cfg.language}")

    # --- Ensure model is present (first-run download if needed) ----------
    try:
        ensure_model_available(cfg.model_hub_id, model_path)
    except RuntimeError as e:
        print(f"[wispy] {e}")
        sys.exit(2)

    # Model is on disk -- no more network traffic from now on.
    os.environ["HF_HUB_OFFLINE"] = "1"

    # Import Transcriber only AFTER HF_HUB_OFFLINE is set, so faster_whisper
    # sees it on its first import.
    from transcribe import Transcriber  # noqa: E402

    transcriber = Transcriber(
        model_path=model_path,
        device=cfg.device,
        compute_type=cfg.compute_type,
        language=cfg.language,
        beam_size=cfg.beam_size,
        initial_prompt=cfg.initial_prompt,
    )

    recorder = Recorder(sample_rate=cfg.sample_rate, device=cfg.audio_device)
    audio_queue: queue.Queue = queue.Queue()

    def on_start():
        beep_start()
        recorder.start()
        print("[wispy] Recording ...")

    def on_stop():
        audio = recorder.stop()
        beep_stop()
        duration = len(audio) / cfg.sample_rate if len(audio) > 0 else 0
        if duration < MIN_DURATION_SEC:
            print(f"[wispy] (too short: {duration:.2f}s, skipped)")
            return
        print(f"[wispy] Captured {duration:.1f}s audio, transcribing ...")
        audio_queue.put(audio)

    def transcription_worker():
        while True:
            audio = audio_queue.get()
            if audio is None:
                break
            try:
                text = transcriber.transcribe(audio)
                if text:
                    print(f"[wispy] >> {text}")
                    type_text(text, restore_clipboard=cfg.restore_clipboard)
                else:
                    print("[wispy] (no speech detected)")
            except Exception as e:
                print(f"[wispy] Transcription error: {e}")

    worker = threading.Thread(target=transcription_worker, daemon=True)
    worker.start()

    listener = HotkeyListener(
        hotkey=cfg.hotkey,
        mode=cfg.record_mode,
        on_start=on_start,
        on_stop=on_stop,
    )
    listener.start()

    print(f"\n[wispy] Ready! Press {cfg.hotkey} to dictate. Ctrl+C to quit.\n")

    try:
        import keyboard as kb
        kb.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[wispy] Shutting down ...")
        listener.stop()
        audio_queue.put(None)
        worker.join(timeout=5)
        print("[wispy] Bye!")


if __name__ == "__main__":
    main()
