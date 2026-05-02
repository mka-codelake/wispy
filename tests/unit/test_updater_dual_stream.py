"""Unit tests for the dual-stream update API in wispy.updater (Phase 3)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wispy import updater


def _make_response(payload) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _install_local_cuda(app_dir: Path, version: str = "12.6.0") -> None:
    cuda = app_dir / "cuda"
    cuda.mkdir(parents=True, exist_ok=True)
    (cuda / "cublas64_12.dll").write_bytes(b"stub")
    (cuda / "_version.txt").write_text(version, encoding="utf-8")


# ---------------------------------------------------------------------------
# Stream filtering
# ---------------------------------------------------------------------------

class TestStreamFiltering:
    RELEASES = [
        {"tag_name": "v0.5.0", "assets": []},
        {"tag_name": "v0.4.0", "assets": []},
        {"tag_name": "cuda-v12.9.1", "assets": []},
        {"tag_name": "cuda-v12.6.0", "assets": []},
        {"tag_name": "v0.3.0", "assets": []},
        {"tag_name": "garbage", "assets": []},
    ]

    def test_app_filter_picks_highest_v_tag_excluding_cuda(self):
        result = updater._find_latest_app_release(self.RELEASES)
        assert result is not None
        assert result["tag_name"] == "v0.5.0"

    def test_cuda_filter_picks_highest_cuda_v_tag(self):
        result = updater._find_latest_cuda_release(self.RELEASES)
        assert result is not None
        assert result["tag_name"] == "cuda-v12.9.1"

    def test_app_filter_returns_none_when_only_cuda_releases(self):
        only_cuda = [{"tag_name": "cuda-v12.9.1", "assets": []}]
        assert updater._find_latest_app_release(only_cuda) is None

    def test_cuda_filter_returns_none_when_only_app_releases(self):
        only_app = [{"tag_name": "v0.4.0", "assets": []}]
        assert updater._find_latest_cuda_release(only_app) is None


# ---------------------------------------------------------------------------
# check_for_updates: end-to-end with mocked /releases response
# ---------------------------------------------------------------------------

class TestCheckForUpdates:
    def test_no_update_when_running_latest_and_no_local_cuda(self, mocker, fake_app_dir):
        payload = [
            {"tag_name": "v0.4.0", "assets": []},
            {"tag_name": "cuda-v12.9.1", "assets": []},
        ]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.has_update() is False
        assert status.app_release is None
        assert status.cuda_release is None

    def test_app_update_detected_when_remote_higher(self, mocker, fake_app_dir):
        payload = [{"tag_name": "v0.5.0", "assets": []}]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.app_release is not None
        assert status.app_release["tag_name"] == "v0.5.0"
        assert status.cuda_release is None

    def test_app_update_not_detected_when_remote_lower(self, mocker, fake_app_dir):
        payload = [{"tag_name": "v0.3.0", "assets": []}]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.app_release is None

    def test_cuda_stream_ignored_when_no_local_cuda(self, mocker, fake_app_dir):
        # Even with an obvious cuda release, no cuda/ locally means we stay quiet.
        payload = [{"tag_name": "cuda-v12.9.1", "assets": []}]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.cuda_release is None

    def test_cuda_update_detected_when_local_cuda_outdated(self, mocker, fake_app_dir):
        _install_local_cuda(fake_app_dir, "12.6.0")
        payload = [{"tag_name": "cuda-v12.9.1", "assets": []}]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.cuda_release is not None
        assert status.cuda_release["tag_name"] == "cuda-v12.9.1"

    def test_cuda_update_not_detected_when_local_is_current(self, mocker, fake_app_dir):
        _install_local_cuda(fake_app_dir, "12.9.1")
        payload = [{"tag_name": "cuda-v12.9.1", "assets": []}]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.cuda_release is None

    def test_both_streams_can_update_independently(self, mocker, fake_app_dir):
        _install_local_cuda(fake_app_dir, "12.6.0")
        payload = [
            {"tag_name": "v0.5.0", "assets": []},
            {"tag_name": "cuda-v12.9.1", "assets": []},
        ]
        mocker.patch("urllib.request.urlopen", return_value=_make_response(payload))

        status = updater.check_for_updates("0.4.0", fake_app_dir)

        assert status.app_release is not None
        assert status.cuda_release is not None

    def test_returns_empty_status_on_network_error(self, mocker, fake_app_dir):
        mocker.patch("urllib.request.urlopen", side_effect=ConnectionError("no net"))
        status = updater.check_for_updates("0.4.0", fake_app_dir)
        assert status.has_update() is False


# ---------------------------------------------------------------------------
# Console reporting + interactive prompt
# ---------------------------------------------------------------------------

class TestReportUpdateStatus:
    def test_prints_running_latest_when_no_update(self, capsys):
        status = updater.UpdateStatus()
        updater.report_update_status("0.4.0", status)
        out = capsys.readouterr().out
        assert "Running latest version" in out
        assert "v0.4.0" in out

    def test_prints_app_line_when_app_update_present(self, capsys):
        status = updater.UpdateStatus(app_release={"tag_name": "v0.5.0"})
        updater.report_update_status("0.4.0", status)
        out = capsys.readouterr().out
        assert "App update available" in out
        assert "v0.5.0" in out

    def test_prints_cuda_line_when_cuda_update_present(self, capsys):
        status = updater.UpdateStatus(cuda_release={"tag_name": "cuda-v12.9.1"})
        updater.report_update_status("0.4.0", status)
        out = capsys.readouterr().out
        assert "CUDA update available" in out
        assert "cuda-v12.9.1" in out


class TestPromptForUpdate:
    def test_returns_false_when_no_update_available(self, mocker):
        mocker.patch("builtins.input", side_effect=AssertionError("must not be called"))
        assert updater.prompt_for_update(updater.UpdateStatus()) is False

    @pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES", "j", "ja"])
    def test_returns_true_for_yes_variants(self, mocker, answer):
        mocker.patch("builtins.input", return_value=answer)
        assert updater.prompt_for_update(updater.UpdateStatus(app_release={"tag_name": "v0.5.0"})) is True

    @pytest.mark.parametrize("answer", ["", "n", "no", "nope", "  ", "anything-else"])
    def test_returns_false_for_no_variants(self, mocker, answer):
        mocker.patch("builtins.input", return_value=answer)
        assert updater.prompt_for_update(updater.UpdateStatus(app_release={"tag_name": "v0.5.0"})) is False

    def test_returns_false_on_eof(self, mocker):
        mocker.patch("builtins.input", side_effect=EOFError())
        assert updater.prompt_for_update(updater.UpdateStatus(app_release={"tag_name": "v0.5.0"})) is False


# ---------------------------------------------------------------------------
# stage_updates: download both streams as available
# ---------------------------------------------------------------------------

class TestStageUpdates:
    def test_no_status_no_downloads(self, mocker, fake_app_dir):
        urlopen = mocker.patch("urllib.request.urlopen")
        result = updater.stage_updates(updater.UpdateStatus(), fake_app_dir)
        assert result == {}
        urlopen.assert_not_called()

    def test_skips_release_without_zip_asset(self, mocker, fake_app_dir, capsys):
        urlopen = mocker.patch("urllib.request.urlopen")

        status = updater.UpdateStatus(
            app_release={"tag_name": "v0.5.0", "assets": []},
        )
        result = updater.stage_updates(status, fake_app_dir)

        assert result == {}
        urlopen.assert_not_called()
        out = capsys.readouterr().out
        assert "no wispy-v*.zip asset" in out

    def test_downloads_app_only_when_only_app_release(self, mocker, fake_app_dir, tmp_path):
        # Real file we'll stream as the "downloaded" content
        source = tmp_path / "wispy-v0.5.0.zip"
        with zipfile.ZipFile(source, "w") as zf:
            zf.writestr("wispy/wispy.exe", b"stub")

        class FakeResp:
            def __init__(self, data: bytes):
                self._data = data
            def read(self, n=-1):
                if n == -1:
                    out, self._data = self._data, b""
                    return out
                out, self._data = self._data[:n], self._data[n:]
                return out
            def __enter__(self): return self
            def __exit__(self, *a): return False

        mocker.patch(
            "urllib.request.urlopen",
            return_value=FakeResp(source.read_bytes()),
        )

        status = updater.UpdateStatus(
            app_release={
                "tag_name": "v0.5.0",
                "assets": [
                    {
                        "name": "wispy-v0.5.0.zip",
                        "browser_download_url": "https://fake/wispy-v0.5.0.zip",
                    }
                ],
            },
        )
        result = updater.stage_updates(status, fake_app_dir)

        assert "app" in result
        assert "cuda" not in result
        assert result["app"].is_file()
        assert result["app"].name == "wispy-v0.5.0.zip"
