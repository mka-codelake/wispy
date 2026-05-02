"""Unit tests for wispy.updater."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wispy import updater


class TestParseVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("0.1.0", "0.1.0"),
            ("v0.1.0", "0.1.0"),
            ("0.3.0", "0.3.0"),
            ("v1.2.3", "1.2.3"),
            ("v1.0.0-rc1", "1.0.0rc1"),  # PEP 440 normalises rc separator
        ],
    )
    def test_strips_leading_v_and_parses(self, raw: str, expected: str):
        result = updater._parse_version(raw)
        assert result is not None
        assert str(result) == expected

    @pytest.mark.parametrize("garbage", ["", "abc", "v", "v.x.y"])
    def test_returns_none_on_unparseable(self, garbage: str):
        assert updater._parse_version(garbage) is None


class TestRequestHeaders:
    def test_anonymous_when_no_token_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        h = updater._request_headers()
        assert h["Accept"] == "application/vnd.github+json"
        assert h["User-Agent"] == "wispy-updater"
        assert "Authorization" not in h

    def test_includes_bearer_when_token_set(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_FAKE_TOKEN_FOR_TESTING_ONLY")
        h = updater._request_headers()
        assert h["Authorization"] == "Bearer ghp_FAKE_TOKEN_FOR_TESTING_ONLY"

    def test_empty_token_is_treated_as_no_token(self, monkeypatch):
        # os.environ.get("GITHUB_TOKEN") returns "" not None when set to empty.
        # An empty string is falsy in the `if token:` check, so no Authorization header.
        monkeypatch.setenv("GITHUB_TOKEN", "")
        h = updater._request_headers()
        assert "Authorization" not in h


class TestStagingPaths:
    def test_staging_dir_is_under_app_dir(self, fake_app_dir: Path):
        assert updater._staging_dir(fake_app_dir) == fake_app_dir / "update-staging"

    def test_backup_dir_is_under_app_dir(self, fake_app_dir: Path):
        assert updater._backup_dir(fake_app_dir) == fake_app_dir / "update-backup"


class TestFetchReleases:
    def _make_response(self, payload) -> MagicMock:
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_returns_list_payload_on_success(self, mocker):
        payload = [
            {"tag_name": "v0.4.0", "assets": []},
            {"tag_name": "v0.3.0", "assets": []},
        ]
        mocker.patch("urllib.request.urlopen", return_value=self._make_response(payload))
        result = updater._fetch_releases()
        assert result == payload

    def test_returns_none_when_payload_is_not_a_list(self, mocker):
        # GitHub returns an error envelope dict instead of the expected list.
        mocker.patch(
            "urllib.request.urlopen",
            return_value=self._make_response({"message": "rate limited"}),
        )
        assert updater._fetch_releases() is None

    def test_returns_none_on_network_error(self, mocker):
        mocker.patch(
            "urllib.request.urlopen", side_effect=ConnectionError("network down")
        )
        assert updater._fetch_releases() is None

    def test_returns_none_on_timeout(self, mocker):
        mocker.patch("urllib.request.urlopen", side_effect=TimeoutError("slow"))
        assert updater._fetch_releases() is None


class TestFindStagedZip:
    def _write_zip(self, path: Path, payload: bytes = b"hello") -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("dummy.txt", payload)

    def test_returns_none_when_staging_missing(self, fake_app_dir: Path):
        assert updater.find_staged_zip(fake_app_dir) is None

    def test_returns_none_when_no_zip_in_staging(self, fake_app_dir: Path):
        (fake_app_dir / "update-staging").mkdir()
        assert updater.find_staged_zip(fake_app_dir) is None

    def test_returns_valid_zip(self, fake_app_dir: Path):
        staging = fake_app_dir / "update-staging"
        staging.mkdir()
        z = staging / "wispy-v0.4.0.zip"
        self._write_zip(z)
        assert updater.find_staged_zip(fake_app_dir) == z

    def test_discards_corrupt_zip_and_returns_none(self, fake_app_dir: Path):
        staging = fake_app_dir / "update-staging"
        staging.mkdir()
        bad = staging / "wispy-v0.5.0.zip"
        bad.write_bytes(b"not a zip file")

        assert updater.find_staged_zip(fake_app_dir) is None
        # Corrupt files are removed so they do not stick around forever
        assert not bad.exists()

    def test_prefers_newest_valid_zip_when_multiple_exist(self, fake_app_dir: Path):
        import os
        import time

        staging = fake_app_dir / "update-staging"
        staging.mkdir()
        older = staging / "wispy-v0.3.0.zip"
        newer = staging / "wispy-v0.4.0.zip"
        self._write_zip(older)
        self._write_zip(newer)

        # Force a measurable mtime difference
        old_time = time.time() - 10
        os.utime(older, (old_time, old_time))

        assert updater.find_staged_zip(fake_app_dir) == newer


class TestHandlePostUpdateStart:
    def test_no_op_when_backup_dir_absent(self, fake_app_dir: Path, capsys):
        updater.handle_post_update_start(fake_app_dir, "0.4.0")
        captured = capsys.readouterr()
        assert "Updated to" not in captured.out

    def test_announces_and_cleans_up_when_backup_dir_present(
        self, fake_app_dir: Path, capsys
    ):
        backup = fake_app_dir / "update-backup"
        staging = fake_app_dir / "update-staging"
        backup.mkdir()
        staging.mkdir()
        (backup / "stale.txt").write_text("stale")
        (staging / "leftover.zip").write_bytes(b"PK")

        updater.handle_post_update_start(fake_app_dir, "0.4.0")

        captured = capsys.readouterr()
        assert "Updated to v0.4.0" in captured.out
        assert not backup.exists()
        assert not staging.exists()


class TestDownloadStagedUpdateGuards:
    def test_source_run_short_circuits(self, fake_app_dir: Path, monkeypatch, capsys):
        # Default test runs have sys.frozen unset, so source-run path triggers.
        if hasattr(sys, "frozen"):
            monkeypatch.delattr(sys, "frozen", raising=False)

        result = updater.download_staged_update("0.3.0", fake_app_dir)

        assert result is False
        captured = capsys.readouterr()
        assert "only works in the portable build" in captured.out


class TestSwapWhitelist:
    """The _SWAP_WHITELIST is the contract that protects user data during update.

    Drift here is a regression risk — anything that gets removed silently
    erases user files on the next swap.
    """

    def test_protects_known_user_files(self):
        wl = updater._SWAP_WHITELIST
        assert "config.yaml" in wl
        assert "hotwords.txt" in wl
        assert "models" in wl

    def test_protects_internal_swap_directories(self):
        wl = updater._SWAP_WHITELIST
        assert "update-backup" in wl
        assert "update-staging" in wl
