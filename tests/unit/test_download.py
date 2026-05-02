"""Unit tests for wispy.download (chunked download + progress rendering)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wispy import download


# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------

class TestFormatSize:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, "0 B"),
            (512, "512 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024 * 1024, "1.0 MB"),
            (5 * 1024 * 1024 + 512 * 1024, "5.5 MB"),
            (1024 * 1024 * 1024, "1.00 GB"),
            (int(1.94 * 1024 * 1024 * 1024), "1.94 GB"),
        ],
    )
    def test_human_readable(self, value, expected):
        assert download._format_size(value) == expected


class TestFormatSpeed:
    def test_zero_speed(self):
        assert "--" in download._format_speed(0)

    def test_negative_speed_treated_as_unknown(self):
        assert "--" in download._format_speed(-1)

    def test_bytes_per_second(self):
        assert "B/s" in download._format_speed(500)

    def test_kilobytes_per_second(self):
        out = download._format_speed(50 * 1024)
        assert "KB/s" in out

    def test_megabytes_per_second(self):
        out = download._format_speed(5 * 1024 * 1024)
        assert "MB/s" in out


class TestFormatEta:
    def test_zero_seconds_shows_placeholder(self):
        assert "--" in download._format_eta(0)

    def test_inf_shows_placeholder(self):
        assert "--" in download._format_eta(float("inf"))

    def test_seconds_under_a_minute(self):
        out = download._format_eta(45)
        assert "0:45" in out

    def test_minutes_and_seconds(self):
        out = download._format_eta(125)
        assert "2:05" in out

    def test_hours_minutes_seconds(self):
        out = download._format_eta(3 * 3600 + 5 * 60 + 7)
        # 3 h 5 m 7 s → " 3:05:07"
        assert "3:05:07" in out


class TestFormatProgressLine:
    def test_with_known_total(self):
        line = download.format_progress_line(
            downloaded=512 * 1024 * 1024,
            total=1024 * 1024 * 1024,
            elapsed_seconds=10.0,
            label="[update]",
        )
        assert "[update]" in line
        assert "50.0%" in line
        assert "MB" in line  # downloaded
        assert "GB" in line  # total
        assert "ETA" in line

    def test_without_total_shows_unknown_eta(self):
        line = download.format_progress_line(
            downloaded=10 * 1024 * 1024,
            total=None,
            elapsed_seconds=2.0,
        )
        assert "downloaded" in line
        assert "%" not in line
        assert "ETA" in line

    def test_zero_elapsed_does_not_divide_by_zero(self):
        line = download.format_progress_line(
            downloaded=100,
            total=1000,
            elapsed_seconds=0.0,
        )
        assert "10.0%" in line
        # speed must show the placeholder, not a NaN
        assert "--" in line or "B/s" in line


# ---------------------------------------------------------------------------
# _read_content_length
# ---------------------------------------------------------------------------

class TestReadContentLength:
    def _resp_with_header(self, value):
        resp = MagicMock()
        resp.headers = {"Content-Length": value} if value is not None else {}
        return resp

    def test_returns_none_when_header_missing(self):
        assert download._read_content_length(self._resp_with_header(None)) is None

    def test_returns_none_when_header_is_zero(self):
        assert download._read_content_length(self._resp_with_header("0")) is None

    def test_returns_none_when_header_is_garbage(self):
        assert download._read_content_length(self._resp_with_header("not-a-number")) is None

    def test_returns_int_for_valid_header(self):
        assert download._read_content_length(self._resp_with_header("1234567")) == 1234567


# ---------------------------------------------------------------------------
# download_with_progress: end-to-end with fake response
# ---------------------------------------------------------------------------

class _FakeResp:
    """Streams `data` in chunks of `chunk_size` bytes."""

    def __init__(self, data: bytes, headers: dict, chunk_size: int = 64 * 1024):
        self._buf = data
        self.headers = headers
        self._chunk_size = chunk_size

    def read(self, n: int = -1):
        if not self._buf:
            return b""
        n = self._chunk_size if (n is None or n < 0) else min(n, self._chunk_size)
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDownloadWithProgress:
    def test_happy_path_writes_full_payload(self, mocker, tmp_path: Path):
        payload = b"X" * (3 * 1024 * 1024)
        fake_resp = _FakeResp(payload, headers={"Content-Length": str(len(payload))})
        mocker.patch("urllib.request.urlopen", return_value=fake_resp)

        # Synthetic monotonic clock: increments by 0.6 s per call, robust
        # against any number of progress emits the implementation chooses.
        clock_state = [0.0]

        def fake_now() -> float:
            value = clock_state[0]
            clock_state[0] += 0.6
            return value

        target = tmp_path / "out.zip"
        ok = download.download_with_progress(
            url="https://fake/file",
            target=target,
            headers={"X-Test": "1"},
            label="[update]",
            now=fake_now,
        )

        assert ok is True
        assert target.read_bytes() == payload

    def test_returns_false_on_network_error(self, mocker, tmp_path: Path):
        mocker.patch(
            "urllib.request.urlopen", side_effect=ConnectionError("network down")
        )
        target = tmp_path / "out.zip"

        ok = download.download_with_progress(
            url="https://fake/file",
            target=target,
            headers=None,
            label="[update]",
        )

        assert ok is False
        # Partial file must be cleaned up
        assert not target.exists()

    def test_creates_target_parent_directory(self, mocker, tmp_path: Path):
        fake_resp = _FakeResp(b"hi", headers={})
        mocker.patch("urllib.request.urlopen", return_value=fake_resp)

        target = tmp_path / "deep" / "nested" / "file.bin"
        ok = download.download_with_progress(
            url="https://fake/file",
            target=target,
            headers=None,
            now=lambda: 0.0,
        )

        assert ok is True
        assert target.read_bytes() == b"hi"

    def test_handles_missing_content_length(self, mocker, tmp_path: Path):
        # Server omitted Content-Length header — progress line falls back to
        # "X downloaded" without a percentage. Must still complete the download.
        payload = b"YYY" * 1024
        fake_resp = _FakeResp(payload, headers={})
        mocker.patch("urllib.request.urlopen", return_value=fake_resp)

        target = tmp_path / "out.bin"
        ok = download.download_with_progress(
            url="https://fake/file",
            target=target,
            headers=None,
            now=lambda: 0.0,
        )

        assert ok is True
        assert target.read_bytes() == payload
