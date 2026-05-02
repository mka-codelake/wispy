"""Unit tests for wispy.model_fetch."""

from __future__ import annotations

from pathlib import Path

import pytest

from wispy.model_fetch import ensure_model_available
from wispy.paths import REQUIRED_MODEL_FILES


def _populate_complete_model(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_MODEL_FILES:
        (target / name).write_bytes(b"stub")


class TestEnsureModelAvailable:
    def test_no_op_when_model_already_complete(self, mocker, tmp_path: Path):
        target = tmp_path / "model"
        _populate_complete_model(target)

        snap = mocker.patch("huggingface_hub.snapshot_download")
        ensure_model_available("any/repo", target)

        snap.assert_not_called()

    def test_downloads_when_directory_missing(self, mocker, tmp_path: Path):
        target = tmp_path / "model"

        def fake_snapshot(repo_id, local_dir):
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            for name in REQUIRED_MODEL_FILES:
                (Path(local_dir) / name).write_bytes(b"downloaded")

        snap = mocker.patch(
            "huggingface_hub.snapshot_download", side_effect=fake_snapshot
        )

        ensure_model_available("hub/repo", target)

        snap.assert_called_once_with(repo_id="hub/repo", local_dir=str(target))
        assert all((target / name).is_file() for name in REQUIRED_MODEL_FILES)

    def test_downloads_when_directory_present_but_incomplete(
        self, mocker, tmp_path: Path
    ):
        target = tmp_path / "model"
        target.mkdir()
        # Only one of the required files is present -> incomplete
        (target / REQUIRED_MODEL_FILES[0]).write_bytes(b"partial")

        def fake_snapshot(repo_id, local_dir):
            for name in REQUIRED_MODEL_FILES:
                (Path(local_dir) / name).write_bytes(b"downloaded")

        snap = mocker.patch(
            "huggingface_hub.snapshot_download", side_effect=fake_snapshot
        )

        ensure_model_available("hub/repo", target)

        snap.assert_called_once()

    def test_raises_runtime_error_when_download_fails(self, mocker, tmp_path: Path):
        target = tmp_path / "model"

        mocker.patch(
            "huggingface_hub.snapshot_download",
            side_effect=ConnectionError("network down"),
        )

        with pytest.raises(RuntimeError, match="Model download failed"):
            ensure_model_available("hub/repo", target)

    def test_raises_runtime_error_when_download_returns_incomplete(
        self, mocker, tmp_path: Path
    ):
        target = tmp_path / "model"

        def half_download(repo_id, local_dir):
            # Only writes one file, leaving the model incomplete
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            (Path(local_dir) / REQUIRED_MODEL_FILES[0]).write_bytes(b"only one")

        mocker.patch(
            "huggingface_hub.snapshot_download", side_effect=half_download
        )

        with pytest.raises(RuntimeError, match="Download finished but the model is still incomplete"):
            ensure_model_available("hub/repo", target)

    def test_propagates_huggingface_hub_import_error_as_runtime_error(
        self, mocker, tmp_path: Path
    ):
        target = tmp_path / "model"

        # Force the lazy `from huggingface_hub import snapshot_download` to fail.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "huggingface_hub":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        mocker.patch.object(builtins, "__import__", side_effect=fake_import)

        with pytest.raises(RuntimeError, match="huggingface_hub is not installed"):
            ensure_model_available("hub/repo", target)
