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
    add_cuda_to_dll_search_path_at,
    fetch_latest_cuda_release,
    install_cuda_bundle,
    install_cuda_from_local,
    is_cuda_installed_at,
)
from .feedback import beep_start, beep_stop  # noqa: E402
from .gpu_detect import detect_nvidia_gpu  # noqa: E402
from .hotkey import HotkeyListener  # noqa: E402
from .model_fetch import ensure_model_available  # noqa: E402
from .output import type_text  # noqa: E402
from .paths import get_app_dir, load_vocabulary, resolve_cuda_path, resolve_model_path  # noqa: E402
from .updater import (  # noqa: E402
    check_for_updates,
    download_staged_update,
    handle_post_update_start,
    prompt_for_update,
    report_update_status,
    stage_updates,
    trigger_swap,
)

MIN_DURATION_SEC = 0.3


def _ensure_cuda_or_fallback(cfg: Config, app_dir: Path, cuda_dir: Path) -> bool:
    """Decide whether the run should use CUDA, installing the bundle if needed.

    Returns True if `cuda_dir` is populated and ready to be added to the
    DLL search path. Returns False in every other case (user declined,
    no GPU, install failed, device forced to CPU).

    Behaviour:

    - cfg.device == "cpu"         → never CUDA, return False without prompts.
    - cuda_dir already populated  → CUDA is ready, return True.
    - cuda_local_source set       → install silently from the local artefact
                                     (test/offline path, no prompt).
    - GPU detection result:
        * "yes"      → tell the user, ask, download from GitHub on accept.
        * "no"       → no prompt; return False.
        * "unknown"  → ambiguous. Prompt with a clear notice.

    The function does NOT exit/restart the process. After a successful
    install, control returns to main() so the rest of startup can proceed
    in the same process.
    """
    if cfg.device == "cpu":
        return False
    if is_cuda_installed_at(cuda_dir):
        return True

    # Test-bootstrap path: install silently from a local file/directory.
    if cfg.cuda_local_source:
        local = Path(cfg.cuda_local_source)
        if not local.is_absolute():
            local = (app_dir / local).resolve()
        if install_cuda_from_local(local, cuda_dir):
            print("[gpu] CUDA runtime ready (from local source).")
            return True
        print("[gpu] cuda_local_source failed — falling through to network/CPU.")

    gpu_status = detect_nvidia_gpu()
    if gpu_status == "no":
        return False

    if gpu_status == "yes":
        print("[gpu] NVIDIA GPU detected.")
    else:  # "unknown"
        print("[gpu] Could not detect a NVIDIA GPU automatically (nvidia-smi missing or unresponsive).")
        print("[gpu] If you have a NVIDIA card, you can still install the CUDA runtime.")
    print("[gpu] CUDA runtime is not installed yet (~1.3 GB download).")

    try:
        answer = input("[gpu] Download CUDA runtime now? [y/N]: ").strip().lower()
    except EOFError:
        answer = ""

    if answer not in ("y", "yes", "j", "ja"):
        print("[gpu] Skipping CUDA install. wispy will run on CPU.")
        return False

    release = fetch_latest_cuda_release()
    if release is None:
        print("[gpu] No CUDA release found on GitHub — running on CPU.")
        return False

    if not install_cuda_bundle(release, app_dir, cuda_dir=cuda_dir):
        print("[gpu] CUDA install failed — running on CPU.")
        return False

    print("[gpu] CUDA runtime ready.")
    return True


def _resolve_effective_device(cfg: Config, cuda_available: bool) -> tuple[str, str]:
    """Pick (device, compute_type) for the Transcriber given the cuda/ state.

    The Transcriber must never be initialised with a GPU device when the
    CUDA bundle is not present, otherwise CTranslate2 will crash on the
    first transcribe() call with a missing-DLL error. This helper enforces
    that invariant.
    """
    if cfg.device == "cpu":
        return "cpu", cfg.compute_type
    if cuda_available:
        return cfg.device, cfg.compute_type
    if cfg.device == "cuda":
        print("[wispy] device=cuda configured but CUDA runtime is missing — falling back to CPU.")
    return "cpu", cfg.compute_type


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
    cuda_dir = resolve_cuda_path(cfg.cuda_path)

    # --- Update flow: post-swap cleanup, then dual-stream check + apply -----
    handle_post_update_start(app_dir, __version__)

    if cfg.update_check:
        status = check_for_updates(__version__, app_dir, cuda_dir=cuda_dir)
        report_update_status(__version__, status)
        if status.has_update():
            # Three tiers collapse here:
            #   auto_update=true  -> always proceed
            #   --update flag     -> force proceed for this run (power-user / scripts)
            #   else              -> ask the user
            proceed = cfg.auto_update or args.update or prompt_for_update(status)
            if proceed:
                staged = stage_updates(status, app_dir)
                if staged:
                    trigger_swap(
                        app_zip=staged.get("app"),
                        cuda_zip=staged.get("cuda"),
                        app_dir=app_dir,
                        cuda_dir=cuda_dir,
                    )
                    # trigger_swap exits in frozen build. Source runs return
                    # here and just continue with the older binaries.
            else:
                print("[update] Skipped. wispy will continue on the current version.")
    elif args.update:
        print("[update] --update was set, but update_check is disabled in config.")

    model_path = resolve_model_path(cfg.model_name, cfg.model_path)

    vocabulary = load_vocabulary()
    hotwords_str = " ".join(vocabulary)

    print(f"[wispy] version     = {__version__}")
    print(f"[wispy] app_dir     = {app_dir}")
    print(f"[wispy] config      = {config_path} "
          f"({'found' if config_path.exists() else 'defaults'})")
    print(f"[wispy] model_path  = {model_path}")
    print(f"[wispy] vocabulary  = {len(vocabulary)} term(s) loaded")

    # --- Lazy CUDA install on first start with a NVIDIA GPU ----------------
    cuda_available = _ensure_cuda_or_fallback(cfg, app_dir, cuda_dir)
    if cuda_available:
        # Register cuda_dir on the DLL search path so CTranslate2 finds the
        # NVIDIA libraries on first WhisperModel(...) call.
        add_cuda_to_dll_search_path_at(cuda_dir)

    # Pick effective device. If cuda/ is missing we MUST force CPU here,
    # otherwise CTranslate2 happily initialises and then crashes on the
    # first transcribe() call with a missing-DLL error.
    effective_device, effective_compute_type = _resolve_effective_device(cfg, cuda_available)

    print(f"[wispy] hotkey={cfg.hotkey}, mode={cfg.record_mode}, "
          f"model={cfg.model_name}, device={effective_device}, lang={cfg.language}")

    # --- Ensure model is present (first-run download or local copy) ----------
    # Note: hf_hub's tqdm progress is left enabled so the user sees what is
    # going on during the multi-minute initial download. The trade-off is a
    # final "Download complete:" line that may land just below wispy's
    # "[wispy] Ready!" banner — that's accepted as preferable to a silent
    # five-minute wait.
    model_local_source: Path | None = None
    if cfg.model_local_source:
        model_local_source = Path(cfg.model_local_source)
        if not model_local_source.is_absolute():
            model_local_source = (app_dir / model_local_source).resolve()
    try:
        ensure_model_available(cfg.model_hub_id, model_path, local_source=model_local_source)
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
        device=effective_device,
        compute_type=effective_compute_type,
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
