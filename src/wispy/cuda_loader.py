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

After extraction the local layout becomes `<cuda_dir>/...` where
`cuda_dir` is configurable (defaults to `<app_dir>/cuda/`).
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

from .download import download_with_progress

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
    if "-b" in s:
        s = s.split("-b", 1)[0]
    try:
        return Version(s)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Local cuda state — cuda_dir is the configurable directory
# ---------------------------------------------------------------------------

def find_local_cuda_version_at(cuda_dir: Path) -> Optional[Version]:
    """Read <cuda_dir>/_version.txt and parse it. Returns None if absent or unreadable."""
    marker = cuda_dir / "_version.txt"
    if not marker.is_file():
        return None
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return _parse_cuda_version(raw)


def is_cuda_installed_at(cuda_dir: Path) -> bool:
    """Return True if cuda_dir exists and has at least one DLL."""
    if not cuda_dir.is_dir():
        return False
    return any(p.suffix.lower() == ".dll" for p in cuda_dir.iterdir())


# Legacy app_dir-based helpers (used by older tests / external callers).
# New code should prefer the *_at variants with an explicit cuda_dir.

def find_local_cuda_version(app_dir: Path) -> Optional[Version]:
    return find_local_cuda_version_at(app_dir / "cuda")


def is_cuda_installed(app_dir: Path) -> bool:
    return is_cuda_installed_at(app_dir / "cuda")


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
# ZIP validation + extraction (shared between download and bootstrap paths)
# ---------------------------------------------------------------------------

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
    return all(name.startswith("cuda/") for name in names)


def _extract_cuda_zip_to(zip_path: Path, cuda_dir: Path) -> bool:
    """Extract `zip_path` such that the resulting tree is `cuda_dir/...`.

    The ZIP itself contains a top-level `cuda/` directory (see release-cuda.yml).
    After extraction the layout becomes `cuda_dir/cublas64_12.dll`, etc.
    Existing contents of cuda_dir are removed first.
    """
    if cuda_dir.exists():
        shutil.rmtree(cuda_dir, ignore_errors=True)
    cuda_dir.parent.mkdir(parents=True, exist_ok=True)

    # Extract into a temp staging dir, then rename `cuda/` to cuda_dir.
    with tempfile.TemporaryDirectory(dir=str(cuda_dir.parent)) as staging:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(staging)
        except (zipfile.BadZipFile, OSError) as e:
            print(f"[cuda] Extract failed: {e}")
            return False
        extracted = Path(staging) / "cuda"
        if not extracted.is_dir():
            print(f"[cuda] Extracted ZIP did not contain a top-level cuda/ dir.")
            return False
        shutil.move(str(extracted), str(cuda_dir))
    return cuda_dir.is_dir()


def _copy_cuda_dir_to(source_dir: Path, cuda_dir: Path) -> bool:
    """Copy a pre-extracted cuda directory tree into cuda_dir.

    `source_dir` should look like the extracted contents of a wispy-cuda-*.zip,
    i.e. directly contain cublas64_12.dll, _version.txt, etc.
    """
    if not source_dir.is_dir():
        return False
    has_dll = any(p.suffix.lower() == ".dll" for p in source_dir.iterdir())
    if not has_dll:
        print(f"[cuda] Source directory has no DLLs: {source_dir}")
        return False
    if cuda_dir.exists():
        shutil.rmtree(cuda_dir, ignore_errors=True)
    cuda_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, cuda_dir)
    return cuda_dir.is_dir()


# ---------------------------------------------------------------------------
# Bootstrap: install from a local path (test / offline mode)
# ---------------------------------------------------------------------------

def install_cuda_from_local(local_source: Path, cuda_dir: Path) -> bool:
    """Install the CUDA bundle from a local file or directory, no network.

    `local_source` may be either:
      - a wispy-cuda-*.zip file (validated + extracted), or
      - a directory whose contents are copied verbatim into cuda_dir.

    Returns True on success.
    """
    if not local_source.exists():
        print(f"[cuda] Local source does not exist: {local_source}")
        return False

    if local_source.is_file():
        print(f"[cuda] Installing CUDA from local ZIP {local_source} ...")
        if not _validate_zip(local_source):
            print(f"[cuda] Local ZIP failed validation: {local_source}")
            return False
        if not _extract_cuda_zip_to(local_source, cuda_dir):
            return False
        print(f"[cuda] Installed CUDA bundle into {cuda_dir}.")
        return True

    if local_source.is_dir():
        print(f"[cuda] Installing CUDA from local directory {local_source} ...")
        if not _copy_cuda_dir_to(local_source, cuda_dir):
            return False
        print(f"[cuda] Installed CUDA bundle into {cuda_dir}.")
        return True

    print(f"[cuda] Local source is neither a file nor a directory: {local_source}")
    return False


# ---------------------------------------------------------------------------
# Network: download GitHub release asset to cuda_dir
# ---------------------------------------------------------------------------

def install_cuda_bundle(release: dict, app_dir_or_cuda_dir: Path, *, cuda_dir: Optional[Path] = None) -> bool:
    """Download and extract the cuda asset from a GitHub release object.

    Two call shapes are supported for backwards compatibility:
      - install_cuda_bundle(release, app_dir)        # legacy; uses app_dir/cuda
      - install_cuda_bundle(release, app_dir, cuda_dir=...)  # explicit target

    Returns True on success. Cleans up partial downloads on failure.
    """
    target = cuda_dir if cuda_dir is not None else (app_dir_or_cuda_dir / "cuda")

    assets = release.get("assets", [])
    asset = next(
        (
            a
            for a in assets
            if a.get("name", "").startswith("wispy-cuda-v") and a["name"].endswith(".zip")
        ),
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

    download_dir = target.parent / "cuda-staging"
    download_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(download_dir), delete=False, suffix=".zip.partial"
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    ok = download_with_progress(
        url=url,
        target=tmp_path,
        headers=_request_headers(),
        label="[cuda]",
    )
    if not ok:
        tmp_path.unlink(missing_ok=True)
        return False

    try:
        if not _validate_zip(tmp_path):
            print("[cuda] Downloaded ZIP failed validation.")
            return False
        if not _extract_cuda_zip_to(tmp_path, target):
            return False
    finally:
        tmp_path.unlink(missing_ok=True)
        try:
            if download_dir.is_dir() and not any(download_dir.iterdir()):
                download_dir.rmdir()
        except OSError:
            pass

    print(f"[cuda] Installed CUDA bundle into {target}.")
    return True


# ---------------------------------------------------------------------------
# Runtime DLL search path
# ---------------------------------------------------------------------------

def add_cuda_to_dll_search_path_at(cuda_dir: Path) -> bool:
    """Make `cuda_dir` visible to CTranslate2's DLL loader.

    Uses os.add_dll_directory (Python 3.8+, Windows). On non-Windows or when
    the call is unavailable this is a no-op. Returns True if the directory
    was registered.
    """
    if not cuda_dir.is_dir():
        return False
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return False
    try:
        add_dll_directory(str(cuda_dir))
        return True
    except OSError:
        return False


def add_cuda_to_dll_search_path(app_dir: Path) -> bool:
    """Legacy wrapper: registers `<app_dir>/cuda/` on the DLL search path."""
    return add_cuda_to_dll_search_path_at(app_dir / "cuda")
