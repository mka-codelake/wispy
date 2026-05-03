"""Unit tests for wispy.gpu_detect."""

from __future__ import annotations

import subprocess

import pytest

from wispy import gpu_detect


def _stub_completed_process(returncode: int, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


class TestHasNvidiaGpu:
    def test_false_when_nvidia_smi_not_on_path(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value=None)
        assert gpu_detect.has_nvidia_gpu() is False

    def test_false_on_timeout(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5),
        )
        assert gpu_detect.has_nvidia_gpu() is False

    def test_false_on_oserror(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            side_effect=OSError("permission denied"),
        )
        assert gpu_detect.has_nvidia_gpu() is False

    def test_false_on_non_zero_exit(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=1, stdout=""),
        )
        assert gpu_detect.has_nvidia_gpu() is False

    def test_false_on_empty_output(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=0, stdout=""),
        )
        assert gpu_detect.has_nvidia_gpu() is False

    def test_false_on_whitespace_only_output(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=0, stdout="   \n\n  "),
        )
        assert gpu_detect.has_nvidia_gpu() is False

    def test_true_on_single_gpu(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(
                returncode=0, stdout="NVIDIA GeForce RTX 4070\n"
            ),
        )
        assert gpu_detect.has_nvidia_gpu() is True

    def test_true_on_multi_gpu(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(
                returncode=0, stdout="NVIDIA RTX 4070\nNVIDIA RTX 3060\n"
            ),
        )
        assert gpu_detect.has_nvidia_gpu() is True


class TestDetectNvidiaGpuTriState:
    """Tri-state detect_nvidia_gpu() differentiates "no" from "unknown".

    The distinction matters because "unknown" (nvidia-smi missing on PATH,
    timeout) leaves the door open for a user with a NVIDIA card whose
    detection happens to fail. The caller can then ask the user instead
    of silently defaulting to CPU.
    """

    def test_unknown_when_nvidia_smi_not_on_path(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value=None)
        assert gpu_detect.detect_nvidia_gpu() == "unknown"

    def test_unknown_on_timeout(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5),
        )
        assert gpu_detect.detect_nvidia_gpu() == "unknown"

    def test_unknown_on_oserror(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            side_effect=OSError("permission denied"),
        )
        assert gpu_detect.detect_nvidia_gpu() == "unknown"

    def test_no_on_non_zero_exit(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=1, stdout=""),
        )
        # nvidia-smi was reachable but failed -> there is no usable GPU
        assert gpu_detect.detect_nvidia_gpu() == "no"

    def test_no_on_empty_output(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=0, stdout=""),
        )
        assert gpu_detect.detect_nvidia_gpu() == "no"

    def test_yes_on_at_least_one_gpu(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(
                returncode=0, stdout="NVIDIA GeForce RTX 4070\n"
            ),
        )
        assert gpu_detect.detect_nvidia_gpu() == "yes"

    def test_has_nvidia_gpu_treats_unknown_as_false(self, mocker):
        # Strict wrapper: "unknown" must be False so legacy callers do not
        # silently start treating ambiguous detection as a GPU presence.
        mocker.patch("wispy.gpu_detect.shutil.which", return_value=None)
        assert gpu_detect.has_nvidia_gpu() is False

    def test_has_nvidia_gpu_true_only_on_yes(self, mocker):
        mocker.patch("wispy.gpu_detect.shutil.which", return_value="/usr/bin/nvidia-smi")
        mocker.patch(
            "wispy.gpu_detect.subprocess.run",
            return_value=_stub_completed_process(returncode=0, stdout="RTX 4070\n"),
        )
        assert gpu_detect.has_nvidia_gpu() is True
