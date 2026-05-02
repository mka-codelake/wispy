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
