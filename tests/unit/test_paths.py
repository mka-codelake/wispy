"""Unit tests for wispy.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from wispy.paths import (
    REQUIRED_MODEL_FILES,
    check_model_complete,
    get_app_dir,
    get_vocabulary_path,
    load_vocabulary,
    missing_model_files,
    resolve_cuda_path,
    resolve_model_path,
)


class TestGetAppDir:
    def test_in_source_mode_returns_repo_root(self, repo_root: Path):
        # In dev/test runs sys.frozen is unset; get_app_dir must point at the repo root.
        result = get_app_dir()
        assert result == repo_root

    def test_in_frozen_mode_uses_executable_directory(self, mocker, tmp_path: Path):
        fake_exe = tmp_path / "wispy.exe"
        fake_exe.touch()

        mocker.patch("wispy.paths.sys.frozen", True, create=True)
        mocker.patch("wispy.paths.sys.executable", str(fake_exe))

        result = get_app_dir()
        assert result == tmp_path


class TestResolveModelPath:
    def test_falls_back_to_app_dir_models_subdir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        result = resolve_model_path("large-v3-turbo")
        assert result == (tmp_path / "models" / "large-v3-turbo").resolve()

    def test_absolute_explicit_path_wins(self, tmp_path: Path):
        explicit = tmp_path / "alt-models" / "tiny"
        result = resolve_model_path("ignored", model_path=str(explicit))
        assert result == explicit.resolve()

    def test_relative_explicit_path_anchors_to_app_dir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        result = resolve_model_path("ignored", model_path="custom/place")
        assert result == (tmp_path / "custom" / "place").resolve()


class TestResolveCudaPath:
    def test_falls_back_to_app_dir_cuda_subdir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        result = resolve_cuda_path()
        assert result == (tmp_path / "cuda").resolve()

    def test_absolute_explicit_path_wins(self, tmp_path: Path):
        explicit = tmp_path / "shared-cuda"
        result = resolve_cuda_path(str(explicit))
        assert result == explicit.resolve()

    def test_relative_explicit_path_anchors_to_app_dir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        result = resolve_cuda_path("alt/cuda")
        assert result == (tmp_path / "alt" / "cuda").resolve()


class TestModelCompleteness:
    def test_missing_directory_is_incomplete(self, tmp_path: Path):
        missing_dir = tmp_path / "absent"
        assert check_model_complete(missing_dir) is False
        assert missing_model_files(missing_dir) == list(REQUIRED_MODEL_FILES)

    def test_directory_without_files_is_incomplete(self, tmp_path: Path):
        empty = tmp_path / "empty-model"
        empty.mkdir()
        assert check_model_complete(empty) is False
        assert missing_model_files(empty) == list(REQUIRED_MODEL_FILES)

    def test_full_directory_is_complete(self, tmp_path: Path):
        target = tmp_path / "model"
        target.mkdir()
        for name in REQUIRED_MODEL_FILES:
            (target / name).write_bytes(b"stub")
        assert check_model_complete(target) is True
        assert missing_model_files(target) == []

    def test_partial_directory_reports_only_missing(self, tmp_path: Path):
        target = tmp_path / "model"
        target.mkdir()
        present = REQUIRED_MODEL_FILES[:2]
        for name in present:
            (target / name).write_bytes(b"stub")
        missing = missing_model_files(target)
        assert set(missing) == set(REQUIRED_MODEL_FILES) - set(present)


class TestVocabulary:
    def test_path_lives_in_app_dir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        assert get_vocabulary_path() == tmp_path / "hotwords.txt"

    def test_load_returns_empty_when_file_missing(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        assert load_vocabulary() == []

    def test_load_skips_blank_and_comment_lines(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        (tmp_path / "hotwords.txt").write_text(
            "# header comment\n"
            "Kubernetes\n"
            "\n"
            "  # indented comment treated as comment\n"
            "PyTorch\n"
            "   # leading whitespace is stripped\n",
            encoding="utf-8",
        )
        assert load_vocabulary() == ["Kubernetes", "PyTorch"]

    def test_load_strips_whitespace_around_terms(self, mocker, tmp_path: Path):
        mocker.patch("wispy.paths.get_app_dir", return_value=tmp_path)
        (tmp_path / "hotwords.txt").write_text(
            "  trailing spaces ignored  \n\tTabIndent\n",
            encoding="utf-8",
        )
        assert load_vocabulary() == ["trailing spaces ignored", "TabIndent"]
