"""Unit tests for wispy.cuda_loader."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from packaging.version import Version

from wispy import cuda_loader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_urllib_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_cuda_zip(path: Path, version: str = "12.9.1") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("cuda/cublas64_12.dll", b"stub")
        zf.writestr("cuda/cudnn_engine.dll", b"stub")
        zf.writestr("cuda/_version.txt", version)


# ---------------------------------------------------------------------------
# _parse_cuda_version
# ---------------------------------------------------------------------------

class TestParseCudaVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("12.9.1", "12.9.1"),
            ("cuda-v12.9.1", "12.9.1"),
            ("cuda-v12.9.1-b2", "12.9.1"),
            ("12.9.1-b3", "12.9.1"),
            ("  cuda-v11.8.0  ", "11.8.0"),
        ],
    )
    def test_strips_prefix_and_build_counter(self, raw, expected):
        result = cuda_loader._parse_cuda_version(raw)
        assert result is not None
        assert str(result) == expected

    @pytest.mark.parametrize("garbage", ["", "cuda-vXY", "abc", "cuda-v"])
    def test_returns_none_on_unparseable(self, garbage):
        assert cuda_loader._parse_cuda_version(garbage) is None


# ---------------------------------------------------------------------------
# Local cuda state
# ---------------------------------------------------------------------------

class TestFindLocalCudaVersion:
    def test_returns_none_when_cuda_dir_missing(self, fake_app_dir):
        assert cuda_loader.find_local_cuda_version(fake_app_dir) is None

    def test_returns_none_when_marker_file_missing(self, fake_app_dir):
        (fake_app_dir / "cuda").mkdir()
        assert cuda_loader.find_local_cuda_version(fake_app_dir) is None

    def test_parses_version_from_marker(self, fake_app_dir):
        cuda = fake_app_dir / "cuda"
        cuda.mkdir()
        (cuda / "_version.txt").write_text("12.9.1\n", encoding="utf-8")
        assert cuda_loader.find_local_cuda_version(fake_app_dir) == Version("12.9.1")

    def test_handles_cuda_v_prefixed_marker(self, fake_app_dir):
        cuda = fake_app_dir / "cuda"
        cuda.mkdir()
        (cuda / "_version.txt").write_text("cuda-v12.9.1", encoding="utf-8")
        assert cuda_loader.find_local_cuda_version(fake_app_dir) == Version("12.9.1")


class TestIsCudaInstalled:
    def test_false_when_cuda_dir_missing(self, fake_app_dir):
        assert cuda_loader.is_cuda_installed(fake_app_dir) is False

    def test_false_when_cuda_dir_empty(self, fake_app_dir):
        (fake_app_dir / "cuda").mkdir()
        assert cuda_loader.is_cuda_installed(fake_app_dir) is False

    def test_false_when_only_non_dll_files_present(self, fake_app_dir):
        cuda = fake_app_dir / "cuda"
        cuda.mkdir()
        (cuda / "_version.txt").write_text("12.9.1")
        assert cuda_loader.is_cuda_installed(fake_app_dir) is False

    def test_true_when_at_least_one_dll_present(self, fake_app_dir):
        cuda = fake_app_dir / "cuda"
        cuda.mkdir()
        (cuda / "cublas64_12.dll").write_bytes(b"stub")
        assert cuda_loader.is_cuda_installed(fake_app_dir) is True


# ---------------------------------------------------------------------------
# fetch_latest_cuda_release
# ---------------------------------------------------------------------------

class TestFetchLatestCudaRelease:
    def test_returns_none_on_network_error(self, mocker):
        mocker.patch(
            "urllib.request.urlopen", side_effect=ConnectionError("no network")
        )
        assert cuda_loader.fetch_latest_cuda_release() is None

    def test_returns_none_when_no_cuda_releases(self, mocker):
        # Releases exist, but none with cuda-v prefix
        payload = [
            {"tag_name": "v0.4.0"},
            {"tag_name": "v0.3.0"},
        ]
        mocker.patch(
            "urllib.request.urlopen", return_value=_make_urllib_response(payload)
        )
        assert cuda_loader.fetch_latest_cuda_release() is None

    def test_picks_highest_cuda_version(self, mocker):
        payload = [
            {"tag_name": "v0.4.0"},
            {"tag_name": "cuda-v11.8.0", "assets": []},
            {"tag_name": "cuda-v12.9.1", "assets": [{"name": "wispy-cuda-v12.9.1.zip"}]},
            {"tag_name": "cuda-v12.6.0", "assets": []},
            {"tag_name": "v0.3.0"},
        ]
        mocker.patch(
            "urllib.request.urlopen", return_value=_make_urllib_response(payload)
        )
        result = cuda_loader.fetch_latest_cuda_release()
        assert result is not None
        assert result["tag_name"] == "cuda-v12.9.1"

    def test_skips_unparseable_cuda_tags(self, mocker):
        payload = [
            {"tag_name": "cuda-vbroken"},
            {"tag_name": "cuda-v12.9.1", "assets": []},
        ]
        mocker.patch(
            "urllib.request.urlopen", return_value=_make_urllib_response(payload)
        )
        result = cuda_loader.fetch_latest_cuda_release()
        assert result is not None
        assert result["tag_name"] == "cuda-v12.9.1"

    def test_returns_none_on_unexpected_payload_shape(self, mocker):
        # API returned a dict, not a list (e.g. error envelope)
        mocker.patch(
            "urllib.request.urlopen",
            return_value=_make_urllib_response({"message": "bad credentials"}),
        )
        assert cuda_loader.fetch_latest_cuda_release() is None


# ---------------------------------------------------------------------------
# _validate_zip / _extract_cuda_zip
# ---------------------------------------------------------------------------

class TestValidateZip:
    def test_rejects_non_zip(self, fake_app_dir):
        bad = fake_app_dir / "bad.zip"
        bad.write_bytes(b"not a zip")
        assert cuda_loader._validate_zip(bad) is False

    def test_rejects_empty_zip(self, fake_app_dir):
        empty = fake_app_dir / "empty.zip"
        with zipfile.ZipFile(empty, "w") as zf:
            pass
        assert cuda_loader._validate_zip(empty) is False

    def test_rejects_zip_with_files_outside_cuda_subdir(self, fake_app_dir):
        bad = fake_app_dir / "wrong-layout.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("cuda/cublas64_12.dll", b"ok")
            zf.writestr("rogue.txt", b"NOT under cuda/ - reject")
        assert cuda_loader._validate_zip(bad) is False

    def test_accepts_well_formed_cuda_zip(self, fake_app_dir):
        good = fake_app_dir / "good.zip"
        _make_cuda_zip(good)
        assert cuda_loader._validate_zip(good) is True


class TestExtractCudaZip:
    def test_replaces_existing_cuda_dir(self, fake_app_dir):
        # Pre-existing junk in cuda/ — must be wiped before extract
        old = fake_app_dir / "cuda"
        old.mkdir()
        (old / "stale.txt").write_text("stale")

        zip_path = fake_app_dir / "good.zip"
        _make_cuda_zip(zip_path)

        result = cuda_loader._extract_cuda_zip(zip_path, fake_app_dir)

        assert result is True
        assert (fake_app_dir / "cuda" / "cublas64_12.dll").is_file()
        assert not (fake_app_dir / "cuda" / "stale.txt").exists()


# ---------------------------------------------------------------------------
# install_cuda_bundle
# ---------------------------------------------------------------------------

class TestInstallCudaBundle:
    def test_returns_false_when_release_has_no_zip_asset(self, fake_app_dir):
        release = {"tag_name": "cuda-v12.9.1", "assets": []}
        assert cuda_loader.install_cuda_bundle(release, fake_app_dir) is False

    def test_full_path_succeeds(self, mocker, fake_app_dir, tmp_path):
        # Pre-build a valid cuda zip that we can pretend is the downloaded asset.
        source_zip = tmp_path / "wispy-cuda-v12.9.1.zip"
        _make_cuda_zip(source_zip)

        release = {
            "tag_name": "cuda-v12.9.1",
            "assets": [
                {
                    "name": "wispy-cuda-v12.9.1.zip",
                    "browser_download_url": "https://fake/wispy-cuda-v12.9.1.zip",
                    "size": source_zip.stat().st_size,
                }
            ],
        }

        # Replace the network call: instead of opening a URL, copy the local
        # file's bytes into the response stream.
        class FakeResp:
            def __init__(self, data: bytes):
                self._data = data
            def read(self, n=-1):
                if not self._data:
                    return b""
                if n == -1:
                    out, self._data = self._data, b""
                    return out
                out, self._data = self._data[:n], self._data[n:]
                return out
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=None):
            return FakeResp(source_zip.read_bytes())

        mocker.patch("urllib.request.urlopen", side_effect=fake_urlopen)

        result = cuda_loader.install_cuda_bundle(release, fake_app_dir)

        assert result is True
        assert (fake_app_dir / "cuda" / "cublas64_12.dll").is_file()
        assert (fake_app_dir / "cuda" / "_version.txt").read_text(encoding="utf-8").strip() == "12.9.1"
        # Staging dir was cleaned up
        assert not (fake_app_dir / "cuda-staging").exists()

    def test_returns_false_when_download_fails(self, mocker, fake_app_dir):
        release = {
            "tag_name": "cuda-v12.9.1",
            "assets": [
                {
                    "name": "wispy-cuda-v12.9.1.zip",
                    "browser_download_url": "https://fake/wispy-cuda-v12.9.1.zip",
                    "size": 0,
                }
            ],
        }
        mocker.patch("urllib.request.urlopen", side_effect=ConnectionError("no net"))

        result = cuda_loader.install_cuda_bundle(release, fake_app_dir)

        assert result is False
        # No partial cuda/ directory should remain
        assert not (fake_app_dir / "cuda").exists()
