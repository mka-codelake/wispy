"""First-run model download via huggingface_hub.snapshot_download."""

import sys
from pathlib import Path

from .paths import REQUIRED_MODEL_FILES, check_model_complete, missing_model_files


def ensure_model_available(model_hub_id: str, target_dir: Path) -> None:
    """Make sure the Whisper model is present in target_dir.

    If target_dir already contains all required files, this is a no-op.
    Otherwise the model is downloaded from Hugging Face into target_dir.
    Raises RuntimeError with a readable message on failure.
    """
    if check_model_complete(target_dir):
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    if any(target_dir.iterdir()):
        missing = missing_model_files(target_dir)
        print(
            f"[model] Found incomplete model in {target_dir}. "
            f"Missing: {', '.join(missing)}. Will re-download."
        )
    else:
        print(f"[model] Model not found in {target_dir}.")

    print(
        f"[model] Downloading '{model_hub_id}' to {target_dir}.\n"
        f"[model] This happens once at first start (~1.6 GB, takes a few minutes) ..."
    )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as e:
        raise RuntimeError(
            "huggingface_hub is not installed. Reinstall wispy or run:\n"
            "  pip install huggingface_hub"
        ) from e

    try:
        snapshot_download(
            repo_id=model_hub_id,
            local_dir=str(target_dir),
        )
    except Exception as e:
        _explain_download_error(e, model_hub_id, target_dir)
        raise RuntimeError(f"Model download failed: {e}") from e

    if not check_model_complete(target_dir):
        missing = missing_model_files(target_dir)
        raise RuntimeError(
            f"Download finished but the model is still incomplete.\n"
            f"  Path    : {target_dir}\n"
            f"  Missing : {', '.join(missing)}\n"
            f"  Expected: {', '.join(REQUIRED_MODEL_FILES)}\n"
            f"Try deleting the folder and running wispy again, or copy the\n"
            f"files manually from https://huggingface.co/{model_hub_id}/tree/main"
        )

    print(f"[model] Download complete. Model is ready at {target_dir}.")


def _explain_download_error(err: Exception, model_hub_id: str, target_dir: Path) -> None:
    """Print a readable hint for common download failures."""
    msg = str(err).lower()
    print("", file=sys.stderr)
    print(f"[model] ERROR: failed to download model '{model_hub_id}'.", file=sys.stderr)
    print(f"[model] Target : {target_dir}", file=sys.stderr)
    print(f"[model] Cause  : {err}", file=sys.stderr)
    print("", file=sys.stderr)

    if any(k in msg for k in ("401", "404", "repository not found", "repo not found", "gated repo", "authentication")):
        print(
            "[model] The Hugging Face repo could not be found or is not public.\n"
            f"         Repo ID : {model_hub_id}\n"
            "         Check the model_hub_id in config.yaml and make sure the\n"
            "         repo exists at https://huggingface.co/<repo_id>.",
            file=sys.stderr,
        )
    elif any(k in msg for k in ("connection", "timeout", "network", "dns", "name resolution", "unreachable", "getaddrinfo")):
        print(
            "[model] Looks like a network problem. Check your internet connection\n"
            "         and retry. A corporate proxy or firewall may be blocking\n"
            "         huggingface.co.",
            file=sys.stderr,
        )
    elif any(k in msg for k in ("no space", "enospc", "disk full", "write error")):
        print(
            "[model] Disk space problem. Make sure you have at least 2 GB free\n"
            "         and that wispy can write into its own folder.",
            file=sys.stderr,
        )
    else:
        print(
            "[model] Alternatively, download the 5 files manually from\n"
            f"         https://huggingface.co/{model_hub_id}/tree/main\n"
            f"         and place them into: {target_dir}",
            file=sys.stderr,
        )
