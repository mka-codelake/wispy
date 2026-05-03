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
    """Loads the Whisper model once, then transcribes audio arrays.

    main.py decides on a concrete device before instantiating us — when
    `<app_dir>/cuda/` is missing, it forces device="cpu" so CTranslate2
    cannot try to load the unavailable NVIDIA DLLs. We still keep two
    layers of CUDA fallback as defence in depth:

    - At construction time, if the chosen device fails to load with a
      CUDA-shaped error, we retry with device="cpu" once.
    - At transcribe time, if the first dictation crashes with a similar
      error (CTranslate2 sometimes only loads CUDA backends lazily), we
      rebuild the model on CPU and retry the call once.
    """

    def __init__(
        self,
        model_path: Path,
        device: str = "auto",
        compute_type: str = "default",
        language: str = "de",
        beam_size: int = 5,
        initial_prompt: str = "",
        hotwords: str = "",
    ):
        self.language = language
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt or None
        self.hotwords = hotwords or None
        self._model_path = model_path
        self._device = device
        self._compute_type = compute_type

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
            if self._looks_like_cuda_failure(e, device):
                self._fallback_to_cpu(reason=e)
                return
            self._explain_load_error(e, device)
            raise
        print("[transcribe] Model ready.")

    def _fallback_to_cpu(self, reason: Exception) -> None:
        """Reload the model on CPU. Used both at init and at runtime fallback."""
        print(f"[transcribe] CUDA load failed: {reason}", file=sys.stderr)
        print("[transcribe] Falling back to CPU — slower but reliable.", file=sys.stderr)
        try:
            self.model = WhisperModel(
                str(self._model_path),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
            )
            self._device = "cpu"
            self._compute_type = "int8"
            print("[transcribe] Model ready on CPU (fallback).")
        except Exception as e2:
            self._explain_load_error(e2, "cpu")
            raise

    @staticmethod
    def _looks_like_cuda_failure(err: Exception, device: str) -> bool:
        if device not in ("cuda", "auto"):
            return False
        msg = str(err).lower()
        return any(h in msg for h in _CUDA_DLL_HINTS)

    @staticmethod
    def _explain_load_error(err: Exception, device: str) -> None:
        """Print a readable hint for common model-loading failures."""
        msg = str(err).lower()
        looks_like_cuda_dll = device in ("cuda", "auto") and any(h in msg for h in _CUDA_DLL_HINTS)

        print("", file=sys.stderr)
        print("[transcribe] ERROR: failed to load Whisper model.", file=sys.stderr)
        print(f"[transcribe] Original error: {err}", file=sys.stderr)
        print("", file=sys.stderr)

        if looks_like_cuda_dll:
            print(
                "[transcribe] This looks like a missing CUDA runtime library\n"
                "             (cuBLAS / cuDNN / cudart).\n"
                "\n"
                "  wispy ships without CUDA libraries — they are downloaded\n"
                "  on demand into <app_dir>/cuda/ on machines with an NVIDIA\n"
                "  GPU. If you skipped that prompt, restart wispy and answer\n"
                "  'y' to download the CUDA runtime, or set device: cpu in\n"
                "  config.yaml to force CPU mode.\n"
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
        try:
            return self._do_transcribe(audio)
        except Exception as e:
            if self._looks_like_cuda_failure(e, self._device):
                # CTranslate2 sometimes only loads the CUDA backend on the
                # first compute call. Rebuild on CPU and retry once.
                self._fallback_to_cpu(reason=e)
                return self._do_transcribe(audio)
            raise

    def _do_transcribe(self, audio: np.ndarray) -> str:
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
