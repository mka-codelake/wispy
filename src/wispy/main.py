"""wispy -- Minimal local push-to-talk dictation tool.

Usage:
    python -m wispy [--config path/to/config.yaml] [--update]
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

    Branches on sys.frozen: the bundled wispy.exe re-runs itself with its
    own args, while the source run re-launches 'python -m wispy <args>'.
    """
    user_args = " ".join(f'"{a}"' for a in sys.argv[1:])
    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = user_args
    else:
        exe = sys.executable  # python.exe
        params = f"-m wispy {user_args}".strip()
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1
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
from . import __version__  # noqa: E402
from .audio import Recorder  # noqa: E402
from .config import Config, default_config_path, load_config  # noqa: E402
from .cuda_loader import (  # noqa: E402
    add_cuda_to_dll_search_path,
    fetch_latest_cuda_release,
    install_cuda_bundle,
    is_cuda_installed,
)
from .feedback import beep_start, beep_stop  # noqa: E402
from .gpu_detect import has_nvidia_gpu  # noqa: E402
from .hotkey import HotkeyListener  # noqa: E402
from .model_fetch import ensure_model_available  # noqa: E402
from .output import type_text  # noqa: E402
from .paths import get_app_dir, load_vocabulary, resolve_model_path  # noqa: E402
from .updater import (  # noqa: E402
    download_staged_update,
    find_staged_zip,
    handle_post_update_start,
    start_update_check_thread,
    trigger_swap,
)

MIN_DURATION_SEC = 0.3


def _restart_wispy() -> None:
    """Re-launch wispy with the same argv, then exit the current process.

    Used after a successful lazy CUDA download so the freshly installed
    DLLs are picked up cleanly by a fresh CTranslate2 import.
    """
    import subprocess

    if getattr(sys, "frozen", False):
        argv = [sys.executable] + sys.argv[1:]
    else:
        argv = [sys.executable, "-m", "wispy"] + sys.argv[1:]
    print("[wispy] Restarting ...")
    subprocess.Popen(argv)
    sys.exit(0)


def _maybe_offer_cuda_install(cfg: Config, app_dir: Path) -> None:
    """Offer to download the CUDA runtime bundle on first start with a NVIDIA GPU.

    No-op when device is forced to "cpu", when no NVIDIA GPU is detected,
    or when the cuda/ directory is already populated.
    """
    if cfg.device == "cpu":
        return
    if not has_nvidia_gpu():
        return
    if is_cuda_installed(app_dir):
        return

    print("[gpu] NVIDIA GPU detected.")
    print("[gpu] CUDA runtime is not installed yet (~1.5 GB download).")
    try:
        answer = input("[gpu] Download CUDA runtime now? [y/N]: ").strip().lower()
    except EOFError:
        # No interactive stdin (e.g. piped, scripted) — default to "no" so we
        # do not freeze the start.
        answer = ""

    if answer not in ("y", "yes", "j", "ja"):
        print("[gpu] Skipping CUDA install. wispy will run on CPU.")
        return

    release = fetch_latest_cuda_release()
    if release is None:
        print("[gpu] No CUDA release found on GitHub — running on CPU.")
        return

    if install_cuda_bundle(release, app_dir):
        _restart_wispy()
    else:
        print("[gpu] CUDA install failed — running on CPU.")


def main():
    parser = argparse.ArgumentParser(description="wispy -- local push-to-talk dictation")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Download the latest wispy release to the staging folder, then run normally",
    )
    args = parser.parse_args()

    config_path = args.config or default_config_path()
    app_dir = get_app_dir()
    cfg: Config = load_config(config_path)

    # --- Phase 1: post-swap cleanup (backup dir present = swap just succeeded) ---
    handle_post_update_start(app_dir, __version__)

    # --- Phase 2: apply staged update on normal start (swap + exit) ----------
    if not args.update and cfg.update_check:
        staged = find_staged_zip(app_dir)
        if staged:
            trigger_swap(staged, app_dir)
            # trigger_swap exits for frozen builds; returns here only in source runs

    # --- Phase 3: explicit --update flag → download then continue -----------
    if args.update:
        if cfg.update_check:
            download_staged_update(__version__, app_dir)
        else:
            print("[update] Update check is disabled (update_check: false in config).")

    model_path = resolve_model_path(cfg.model_name, cfg.model_path)

    vocabulary = load_vocabulary()
    hotwords_str = " ".join(vocabulary)

    print(f"[wispy] version     = {__version__}")
    print(f"[wispy] app_dir     = {app_dir}")
    print(f"[wispy] config      = {config_path} "
          f"({'found' if config_path.exists() else 'defaults'})")
    print(f"[wispy] model_path  = {model_path}")
    print(f"[wispy] vocabulary  = {len(vocabulary)} term(s) loaded")
    print(f"[wispy] hotkey={cfg.hotkey}, mode={cfg.record_mode}, "
          f"model={cfg.model_name}, device={cfg.device}, lang={cfg.language}")

    # --- Lazy CUDA install on first start with a NVIDIA GPU ----------------
    _maybe_offer_cuda_install(cfg, app_dir)

    # Make CTranslate2 see <app_dir>/cuda/ when looking for the NVIDIA DLLs.
    # No-op on CPU systems and on Linux/macOS dev runs.
    add_cuda_to_dll_search_path(app_dir)

    # --- Background update check (skipped when --update was used this run) ---
    if cfg.update_check and not args.update:
        start_update_check_thread(__version__)

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
    from .transcribe import Transcriber  # noqa: E402

    transcriber = Transcriber(
        model_path=model_path,
        device=cfg.device,
        compute_type=cfg.compute_type,
        language=cfg.language,
        beam_size=cfg.beam_size,
        initial_prompt=cfg.initial_prompt,
        hotwords=hotwords_str,
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
