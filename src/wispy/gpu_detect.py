"""Detect whether a NVIDIA GPU is available on the host.

Uses nvidia-smi via subprocess. nvidia-smi ships with the NVIDIA driver,
so its presence + a clean exit are a reliable proxy for "this machine has
a usable NVIDIA GPU and a working driver". A machine with an unsupported
or broken driver tends to fail nvidia-smi too, which is the correct
behaviour for our use case (we should not try to use CUDA there).
"""

from __future__ import annotations

import shutil
import subprocess


_TIMEOUT_SECONDS = 5


def has_nvidia_gpu() -> bool:
    """Return True if nvidia-smi exists, runs successfully and reports >=1 GPU.

    Any failure mode (missing executable, non-zero exit, timeout, empty
    output) is treated as "no GPU available". The function never raises.
    """
    if shutil.which("nvidia-smi") is None:
        return False

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False

    if result.returncode != 0:
        return False

    # At least one non-empty line means at least one GPU was reported.
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return len(lines) >= 1
