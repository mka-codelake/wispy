"""Chunked HTTP download helpers with carriage-return progress reporting.

Used by both wispy.updater and wispy.cuda_loader so the progress line
format is consistent across `[update]` and `[cuda]` downloads.
"""

from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

_CHUNK_BYTES = 1024 * 1024          # 1 MiB per chunk
_PROGRESS_INTERVAL_SEC = 0.5        # at most twice per second


# ---------------------------------------------------------------------------
# Pure formatting helpers (easy to unit test)
# ---------------------------------------------------------------------------

def _format_size(num_bytes: int) -> str:
    """Format `num_bytes` as a human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return "    -- /s"
    if bytes_per_second < 1024:
        return f"{bytes_per_second:>4.0f}  B/s"
    if bytes_per_second < 1024 * 1024:
        return f"{bytes_per_second / 1024:>4.1f} KB/s"
    return f"{bytes_per_second / (1024 * 1024):>4.1f} MB/s"


def _format_eta(seconds: float) -> str:
    if seconds <= 0 or seconds == float("inf"):
        return "  --:--"
    seconds = int(seconds)
    if seconds < 60:
        return f"   0:{seconds:02d}"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes:>4}:{sec:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:>2}:{minutes:02d}:{sec:02d}"


def format_progress_line(
    downloaded: int,
    total: Optional[int],
    elapsed_seconds: float,
    label: str = "[download]",
) -> str:
    """Return a one-line progress string suitable for carriage-return rendering.

    `total` may be None when Content-Length was not reported by the server;
    in that case percentage and ETA are replaced with placeholders.
    """
    speed = downloaded / elapsed_seconds if elapsed_seconds > 0 else 0.0

    if total and total > 0:
        pct = (downloaded / total) * 100
        remaining = total - downloaded
        eta = remaining / speed if speed > 0 else float("inf")
        return (
            f"{label} {_format_size(downloaded)} / {_format_size(total)} "
            f"({pct:5.1f}%)  {_format_speed(speed)}  ETA {_format_eta(eta)}"
        )

    return (
        f"{label} {_format_size(downloaded)} downloaded  "
        f"{_format_speed(speed)}  ETA   --:--"
    )


# ---------------------------------------------------------------------------
# Stream download with progress
# ---------------------------------------------------------------------------

def _emit(line: str) -> None:
    """Write a progress line over the previous one using carriage return."""
    # \r returns to column 0; trailing spaces clear leftover characters from
    # a previous longer line.
    sys.stdout.write("\r" + line + "    ")
    sys.stdout.flush()


def download_with_progress(
    url: str,
    target: Path,
    headers: Optional[dict] = None,
    label: str = "[download]",
    timeout: int = 600,
    now: Callable[[], float] = time.monotonic,
) -> bool:
    """Stream `url` into `target` with a carriage-return progress line.

    Returns True on success and False on any failure. On failure the
    partial target file is removed. `now` is injectable for tests.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(target, "wb") as out:
            total = _read_content_length(resp)
            start = now()
            downloaded = 0
            last_emit = 0.0

            while True:
                chunk = resp.read(_CHUNK_BYTES)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)

                tnow = now()
                if tnow - last_emit >= _PROGRESS_INTERVAL_SEC:
                    _emit(format_progress_line(downloaded, total, tnow - start, label))
                    last_emit = tnow

            # Final progress line (so the user sees 100 %), then a newline.
            _emit(format_progress_line(downloaded, total, now() - start, label))
            sys.stdout.write("\n")
            sys.stdout.flush()
        return True
    except Exception as e:
        # Move the cursor to a fresh line so the error is not glued to the
        # progress line that ended without a newline.
        sys.stdout.write("\n")
        sys.stdout.flush()
        print(f"{label} Download failed: {e}")
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _read_content_length(resp) -> Optional[int]:
    raw = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
    if not raw:
        return None
    try:
        value = int(raw)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None
