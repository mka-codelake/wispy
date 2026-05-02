"""Lazy download + extraction of the CUDA runtime bundle.

The CUDA bundle (`wispy-cuda-vX.Y.Z.zip`) is published as its own GitHub
Release on a `cuda-vX.Y.Z` tag. wispy fetches it on demand at first run
on a machine with an NVIDIA GPU (after asking the user). It is also used
during update by the dual-stream updater to pull a newer CUDA bundle.

Asset layout inside the ZIP:

    cuda/
      cublas64_12.dll
      cublasLt64_12.dll
      cudnn_*.dll
      cudart64_12.dll
      _version.txt

After extraction the local layout becomes `<app_dir>/cuda/...`.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from packaging.version import Version

_GITHUB_REPO = "mka-codelake/wispy"
_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases?per_page=50"
_TAG_PREFIX = "cuda-v"


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _request_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "wispy-cuda-loader"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _parse_cuda_version(s: str) -> Optional[Version]:
    """Parse a CUDA version string. Strips the cuda-v prefix and any -bN suffix."""
    s = s.strip()
    if s.startswith(_TAG_PREFIX):
        s = s[len(_TAG_PREFIX):]
    # Drop any -bN build counter — versioning compares the underlying CUDA
    # toolkit version, the build counter is only there to allow re-rolls.
    if "-b" in s:
        s = s.split("-b", 1)[0]
    try:
        return Version(s)
    except Exception:
        return None


def _cuda_dir(app_dir: Path) -> Path:
    return app_dir / "cuda"


def find_local_cuda_version(app_dir: Path) -> Optional[Version]:
    """Read <app_dir>/cuda/_version.txt and parse it. Returns None if absent or unreadable."""
    marker = _cuda_dir(app_dir) / "_version.txt"
    if not marker.is_file():
        return None
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return _parse_cuda_version(raw)


def is_cuda_installed(app_dir: Path) -> bool:
    """Return True if the cuda/ directory exists and has at least one DLL."""
    cuda = _cuda_dir(app_dir)
    if not cuda.is_dir():
        return False
    return any(p.suffix.lower() == ".dll" for p in cuda.iterdir())


# ---------------------------------------------------------------------------
# Latest cuda release lookup
# ---------------------------------------------------------------------------

def fetch_latest_cuda_release() -> Optional[dict]:
    """Return the GitHub Release object for the highest cuda-v* tag, or None.

    Hits /releases?per_page=50, filters for cuda-v* tag names, picks the
    one with the highest version. Returns None on any error or when no
    cuda release exists yet.
    """
    try:
        req = urllib.request.Request(_RELEASES_URL, headers=_request_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[cuda] Release lookup failed ({type(e).__name__}): {e}")
        return None

    if not isinstance(payload, list):
        return None

    candidates = []
    for release in payload:
        tag = release.get("tag_name", "")
        if not tag.startswith(_TAG_PREFIX):
            continue
        ver = _parse_cuda_version(tag)
        if ver is None:
            continue
        candidates.append((ver, release))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------

def _download_to_tempfile(url: str, target_dir: Path) -> Optional[Path]:
    """Download `url` to a fresh tempfile inside target_dir. Returns the path or None."""
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(target_dir), delete=False, suffix=".zip.partial"
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        req = urllib.request.Request(url, headers=_request_headers())
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return tmp_path
    except Exception as e:
        print(f"[cuda] Download failed: {e}")
        tmp_path.unlink(missing_ok=True)
        return None


def _validate_zip(zip_path: Path) -> bool:
    """Return True iff the file is a readable ZIP whose top-level dir is `cuda/`."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                return False
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False
    if not names:
        return False
    # Every member must live under cuda/ — otherwise we would dump files all
    # over app_dir on extract.
    return all(name.startswith("cuda/") for name in names)


def _extract_cuda_zip(zip_path: Path, app_dir: Path) -> bool:
    """Extract `zip_path` into app_dir, replacing any existing cuda/ contents."""
    target = _cuda_dir(app_dir)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(app_dir)
    except (zipfile.BadZipFile, OSError) as e:
        print(f"[cuda] Extract failed: {e}")
        return False
    return target.is_dir()


def install_cuda_bundle(release: dict, app_dir: Path) -> bool:
    """Download and extract the cuda asset from a GitHub release object.

    Returns True on success. Cleans up partial downloads on failure.
    """
    assets = release.get("assets", [])
    asset = next(
        (a for a in assets if a.get("name", "").startswith("wispy-cuda-v") and a["name"].endswith(".zip")),
        None,
    )
    if asset is None:
        print(f"[cuda] Release {release.get('tag_name')} has no wispy-cuda-*.zip asset.")
        return False

    url = asset.get("browser_download_url")
    if not url:
        print("[cuda] Release asset has no download URL.")
        return False

    size_bytes = asset.get("size", 0)
    size_str = f" ({size_bytes / 1024 / 1024:.0f} MB)" if size_bytes else ""
    print(f"[cuda] Downloading {asset['name']}{size_str} ...")

    download_dir = app_dir / "cuda-staging"
    tmp_path = _download_to_tempfile(url, download_dir)
    if tmp_path is None:
        return False

    try:
        if not _validate_zip(tmp_path):
            print(f"[cuda] Downloaded ZIP failed validation.")
            return False
        if not _extract_cuda_zip(tmp_path, app_dir):
            return False
    finally:
        tmp_path.unlink(missing_ok=True)
        # Clean up the staging dir if it ended up empty
        try:
            if download_dir.is_dir() and not any(download_dir.iterdir()):
                download_dir.rmdir()
        except OSError:
            pass

    print(f"[cuda] Installed CUDA bundle into {_cuda_dir(app_dir)}.")
    return True


# ---------------------------------------------------------------------------
# Runtime DLL search path
# ---------------------------------------------------------------------------

def add_cuda_to_dll_search_path(app_dir: Path) -> bool:
    """Make the cuda/ directory visible to CTranslate2's DLL loader.

    Uses os.add_dll_directory (Python 3.8+, Windows). On non-Windows or when
    the call is unavailable this is a no-op. Returns True if the directory
    was registered.
    """
    cuda = _cuda_dir(app_dir)
    if not cuda.is_dir():
        return False
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        # Non-Windows: CTranslate2 will look at LD_LIBRARY_PATH instead, but
        # wispy itself is Windows-only at runtime, so this branch is mostly
        # for development / unit tests on Linux.
        return False
    try:
        add_dll_directory(str(cuda))
        return True
    except OSError:
        return False
