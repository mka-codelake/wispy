"""Detect whether a NVIDIA GPU is available on the host.

Uses nvidia-smi via subprocess. nvidia-smi ships with the NVIDIA driver,
so its presence + a clean exit are a reliable proxy for "this machine has
a usable NVIDIA GPU and a working driver".

The detection is **tri-state** because a missing nvidia-smi on PATH does
NOT mean "no GPU". Some driver installations land it in a non-default
directory (`C:\\Program Files\\NVIDIA Corporation\\NVSMI`), and corporate
images can strip system tools. Returning "unknown" lets the caller fall
back to asking the user instead of silently defaulting to CPU and then
crashing when CTranslate2 tries to use a card that is actually present.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Literal

GpuStatus = Literal["yes", "no", "unknown"]

_TIMEOUT_SECONDS = 5


def detect_nvidia_gpu() -> GpuStatus:
    """Tri-state probe.

    - "yes":     nvidia-smi exists, ran cleanly, listed >=1 GPU.
    - "no":      nvidia-smi exists and ran but reported no GPU, or exited
                 non-zero (which on most systems means "no usable GPU").
    - "unknown": nvidia-smi missing on PATH, timed out, or raised an
                 OSError. We cannot tell whether a GPU is present.
    """
    if shutil.which("nvidia-smi") is None:
        return "unknown"

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"

    if result.returncode != 0:
        return "no"

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return "yes" if lines else "no"


def has_nvidia_gpu() -> bool:
    """Strict yes/no convenience wrapper. Treats "unknown" as "no".

    Kept for callers that only care about the confident-yes case. Most
    code in wispy now consults `detect_nvidia_gpu()` directly so it can
    fall back to asking the user when detection is ambiguous.
    """
    return detect_nvidia_gpu() == "yes"
