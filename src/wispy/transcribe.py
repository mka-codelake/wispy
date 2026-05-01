"""Whisper transcription via faster-whisper / CTranslate2."""

import sys
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from .paths import REQUIRED_MODEL_FILES, check_model_complete, missing_model_files

# Substrings (lowercase) that identify CUDA/DLL loading problems in the
# exception message. When any of these appear, we print a helpful hint
# instead of letting the raw ctypes/CTranslate2 error reach the user.
_CUDA_DLL_HINTS = (
    "cublas",
    "cudnn",
    "cudart",
    "cuda",
    "dll",
    "shared object",
    "library",
    "cannot load",
    "could not load",
    "unable to open",
)


class Transcriber:
    """Loads the Whisper model once, then transcribes audio arrays."""

    def __init__(
        self,
        model_path: Path,
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "de",
        beam_size: int = 5,
        initial_prompt: str = "",
        hotwords: str = "",
    ):
        self.language = language
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt or None
        self.hotwords = hotwords or None

        if not check_model_complete(model_path):
            missing = missing_model_files(model_path)
            raise FileNotFoundError(
                f"Whisper model directory is missing files.\n"
                f"  Path    : {model_path}\n"
                f"  Missing : {', '.join(missing)}\n"
                f"  Expected: {', '.join(REQUIRED_MODEL_FILES)}"
            )

        print(f"[transcribe] Loading model from {model_path} on {device} ({compute_type}) ...")
        try:
            self.model = WhisperModel(
                str(model_path),
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )
        except Exception as e:
            self._explain_load_error(e, device)
            raise
        print("[transcribe] Model ready.")

    @staticmethod
    def _explain_load_error(err: Exception, device: str) -> None:
        """Print a readable hint for common model-loading failures."""
        msg = str(err).lower()
        looks_like_cuda_dll = device == "cuda" and any(h in msg for h in _CUDA_DLL_HINTS)

        print("", file=sys.stderr)
        print("[transcribe] ERROR: failed to load Whisper model.", file=sys.stderr)
        print(f"[transcribe] Original error: {err}", file=sys.stderr)
        print("", file=sys.stderr)

        if looks_like_cuda_dll:
            print(
                "[transcribe] This looks like a missing CUDA runtime library\n"
                "             (cuBLAS / cuDNN / cudart).\n"
                "\n"
                "  In a portable wispy bundle these DLLs should live in\n"
                "  _internal\\ next to wispy.exe. If they are missing, the\n"
                "  bundle was built without the nvidia-* pip packages.\n"
                "\n"
                "  When running from source, install them via:\n"
                "    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12\n"
                "\n"
                "  NVIDIA driver itself must also be installed system-wide\n"
                "  (check: `nvidia-smi` in a terminal).\n",
                file=sys.stderr,
            )
        else:
            print(
                "[transcribe] Check the model path and that it contains all\n"
                f"             required files: {', '.join(REQUIRED_MODEL_FILES)}\n",
                file=sys.stderr,
            )

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a float32 mono audio array and return the text."""
        segments, _info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            hotwords=self.hotwords,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()
