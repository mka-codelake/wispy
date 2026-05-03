"""Update mechanism: dual-stream version check, staged download, next-boot swap.

Two independent release streams are tracked:

- **App stream** (tag `vX.Y.Z`): the wispy executable, Python runtime, and
  non-CUDA libs. Asset name `wispy-vX.Y.Z.zip`.
- **CUDA stream** (tag `cuda-vX.Y.Z[-bN]`): the NVIDIA runtime DLLs that
  wispy lazy-installs into `<app_dir>/cuda/`. Asset name
  `wispy-cuda-vX.Y.Z[-bN].zip`. Only relevant for users who installed the
  CUDA bundle on this machine.

Update flow at startup:

1. Both streams are queried in parallel (best-effort, failures are silent
   and non-fatal — wispy must always continue to start).
2. The user is informed via console: "running latest" or "Update available".
3. If `auto_update: true`, the update is applied without prompting; if
   `auto_update: false` (default), wispy asks `[y/N]`.
4. Apply = download both bundles to `update-staging/`, write a
   PowerShell helper that swaps each into place on next boot, exit so the
   helper can replace `wispy.exe`.
5. The helper restarts wispy automatically; on next normal start
   `handle_post_update_start` cleans up the backup and prints
   "Updated to vX.Y.Z. Welcome back."

Three configuration tiers:

- `update_check: false`                          → no checks, no prompts.
- `update_check: true,  auto_update: false`      → check + prompt (default).
- `update_check: true,  auto_update: true`       → check + apply silently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packaging.version import Version

from .download import download_with_progress

_GITHUB_REPO = "mka-codelake/wispy"
_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases?per_page=50"

_APP_TAG_PREFIX = "v"
_CUDA_TAG_PREFIX = "cuda-v"

# Names the swap must never move or overwrite.
# The cuda/ entry protects the user's installed CUDA bundle from being
# wiped by an app-only update; the cuda update path replaces it explicitly.
_SWAP_WHITELIST = frozenset({
    "config.yaml",
    "hotwords.txt",
    "models",
    "cuda",
    "update-backup",
    "update-staging",
})


# ---------------------------------------------------------------------------
# Auth + version helpers
# ---------------------------------------------------------------------------

def _request_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "wispy-updater"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _parse_version(v: str) -> Optional[Version]:
    """Parse an app version string. Strips leading 'v', returns None on failure."""
    try:
        return Version(v.lstrip("v"))
    except Exception:
        return None


def _parse_cuda_version(s: str) -> Optional[Version]:
    """Parse a CUDA version string. Strips cuda-v prefix and -bN build counter."""
    s = s.strip()
    if s.startswith(_CUDA_TAG_PREFIX):
        s = s[len(_CUDA_TAG_PREFIX):]
    if "-b" in s:
        s = s.split("-b", 1)[0]
    try:
        return Version(s)
    except Exception:
        return None


def _staging_dir(app_dir: Path) -> Path:
    return app_dir / "update-staging"


def _backup_dir(app_dir: Path) -> Path:
    return app_dir / "update-backup"


def _default_cuda_dir(app_dir: Path) -> Path:
    return app_dir / "cuda"


def _local_cuda_version(cuda_dir: Path) -> Optional[Version]:
    marker = cuda_dir / "_version.txt"
    if not marker.is_file():
        return None
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return _parse_cuda_version(raw)


def _is_cuda_installed(cuda_dir: Path) -> bool:
    if not cuda_dir.is_dir():
        return False
    return any(p.suffix.lower() == ".dll" for p in cuda_dir.iterdir())


# ---------------------------------------------------------------------------
# Releases fetch + filtering
# ---------------------------------------------------------------------------

def _fetch_releases() -> Optional[list]:
    """Fetch the recent /releases list. Returns None on any failure."""
    try:
        req = urllib.request.Request(_RELEASES_URL, headers=_request_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[update] Check failed ({type(e).__name__}): {e}")
        return None
    if not isinstance(payload, list):
        return None
    return payload


def _find_latest_app_release(releases: list) -> Optional[dict]:
    candidates = []
    for rel in releases:
        tag = rel.get("tag_name", "")
        if not tag.startswith(_APP_TAG_PREFIX):
            continue
        if tag.startswith(_CUDA_TAG_PREFIX):
            continue  # cuda-v starts with v too, exclude explicitly
        ver = _parse_version(tag)
        if ver is None:
            continue
        candidates.append((ver, rel))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


def _find_latest_cuda_release(releases: list) -> Optional[dict]:
    candidates = []
    for rel in releases:
        tag = rel.get("tag_name", "")
        if not tag.startswith(_CUDA_TAG_PREFIX):
            continue
        ver = _parse_cuda_version(tag)
        if ver is None:
            continue
        candidates.append((ver, rel))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


# ---------------------------------------------------------------------------
# Public API: check_for_updates / UpdateStatus
# ---------------------------------------------------------------------------

@dataclass
class UpdateStatus:
    app_release: Optional[dict] = None  # populated only if newer than current
    cuda_release: Optional[dict] = None  # populated only if newer AND cuda is installed locally

    def has_update(self) -> bool:
        return self.app_release is not None or self.cuda_release is not None


def check_for_updates(
    current_app_version: str,
    app_dir: Path,
    cuda_dir: Optional[Path] = None,
) -> UpdateStatus:
    """Query both release streams and return what (if anything) is newer.

    The cuda stream is only considered when a local cuda/ bundle exists.
    A user without GPU has no reason to download cuda updates.

    `cuda_dir` defaults to <app_dir>/cuda when not given (legacy behaviour).
    Pass an explicit path when the user has configured `cuda_path` to a
    non-default location.
    """
    if cuda_dir is None:
        cuda_dir = _default_cuda_dir(app_dir)

    releases = _fetch_releases()
    if releases is None:
        return UpdateStatus()

    status = UpdateStatus()

    # App stream
    app_rel = _find_latest_app_release(releases)
    if app_rel is not None:
        remote = _parse_version(app_rel["tag_name"])
        local = _parse_version(current_app_version)
        if remote is not None and local is not None and remote > local:
            status.app_release = app_rel

    # CUDA stream — only if user has cuda installed
    if _is_cuda_installed(cuda_dir):
        cuda_rel = _find_latest_cuda_release(releases)
        if cuda_rel is not None:
            remote = _parse_cuda_version(cuda_rel["tag_name"])
            local = _local_cuda_version(cuda_dir)
            if remote is not None and (local is None or remote > local):
                status.cuda_release = cuda_rel

    return status


def report_update_status(current_app_version: str, status: UpdateStatus) -> None:
    """Print a one-line status to the console — equivalent across all three tiers."""
    if not status.has_update():
        print(f"[update] Running latest version (v{current_app_version}).")
        return
    if status.app_release is not None:
        print(
            f"[update] App update available: v{current_app_version} -> "
            f"{status.app_release['tag_name']}"
        )
    if status.cuda_release is not None:
        print(f"[update] CUDA update available: -> {status.cuda_release['tag_name']}")


def prompt_for_update(status: UpdateStatus) -> bool:
    """Return True if the user accepts the update at the [y/N] prompt."""
    if not status.has_update():
        return False
    try:
        answer = input("[update] Apply update now? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes", "j", "ja")


def start_update_check_thread_async(current_version: str) -> None:
    """Run the verbose check in the background. Used for a non-blocking startup banner."""

    def _worker():
        releases = _fetch_releases()
        if releases is None:
            return
        app_rel = _find_latest_app_release(releases)
        if app_rel is None:
            return
        remote = _parse_version(app_rel["tag_name"])
        local = _parse_version(current_version)
        if remote is None or local is None:
            return
        if remote > local:
            print(
                f"[update] (background) App update available: v{local} -> "
                f"{app_rel['tag_name']}"
            )

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Download: stage one or both bundles in update-staging/
# ---------------------------------------------------------------------------

def _pick_zip_asset(release: dict, expected_prefix: str) -> Optional[dict]:
    for a in release.get("assets", []):
        name = a.get("name", "")
        if name.startswith(expected_prefix) and name.endswith(".zip"):
            return a
    return None


def _download_asset(asset: dict, target: Path) -> bool:
    url = asset.get("browser_download_url")
    if not url:
        return False
    return download_with_progress(
        url=url,
        target=target,
        headers=_request_headers(),
        label="[update]",
    )


def stage_updates(status: UpdateStatus, app_dir: Path) -> dict:
    """Download the relevant ZIPs into update-staging/. Returns a dict of staged paths.

    Result keys: 'app' -> Path to wispy-vX.Y.Z.zip (or absent),
                 'cuda' -> Path to wispy-cuda-*.zip (or absent).
    On any download failure the partial files are cleaned up and the key
    is omitted from the returned dict.
    """
    staging = _staging_dir(app_dir)
    staging.mkdir(parents=True, exist_ok=True)

    staged: dict = {}

    if status.app_release is not None:
        asset = _pick_zip_asset(status.app_release, "wispy-v")
        if asset is None:
            print(
                f"[update] App release {status.app_release['tag_name']} has no "
                "wispy-v*.zip asset — skipping."
            )
        else:
            zip_path = staging / asset["name"]
            print(f"[update] Downloading {asset['name']} ...")
            if _download_asset(asset, zip_path):
                staged["app"] = zip_path

    if status.cuda_release is not None:
        asset = _pick_zip_asset(status.cuda_release, "wispy-cuda-v")
        if asset is None:
            print(
                f"[update] CUDA release {status.cuda_release['tag_name']} has no "
                "wispy-cuda-*.zip asset — skipping."
            )
        else:
            zip_path = staging / asset["name"]
            print(f"[update] Downloading {asset['name']} ...")
            if _download_asset(asset, zip_path):
                staged["cuda"] = zip_path

    return staged


# ---------------------------------------------------------------------------
# Power-user CLI path: --update flag
# ---------------------------------------------------------------------------

def download_staged_update(current_version: str, app_dir: Path) -> bool:
    """Power-user / scripted entry point: download whatever is newer, exit normally.

    Equivalent to running the default flow with auto_update=true, but does
    NOT trigger the swap on this run — the swap will fire on the next
    normal start. Returns True iff at least one bundle was staged.

    Only operates in the frozen build, like the v1 updater. Source installs
    should `git pull && pip install -e .`.
    """
    if not getattr(sys, "frozen", False):
        print("[update] --update only works in the portable build (wispy.exe).")
        print("[update] For source installs: git pull && pip install -e .")
        return False

    status = check_for_updates(current_version, app_dir)
    report_update_status(current_version, status)
    if not status.has_update():
        return False

    staged = stage_updates(status, app_dir)
    if not staged:
        print("[update] Staging produced no usable bundle.")
        return False

    print("[update] Update staged. It will be applied on the next normal start.")
    return True


# ---------------------------------------------------------------------------
# Find / validate staged bundles for the next-boot swap
# ---------------------------------------------------------------------------

def find_staged_zip(app_dir: Path) -> Optional[Path]:
    """Return the path to a valid app-bundle ZIP in staging, or None.

    Kept under the v1 name for compatibility with any external callers.
    Only finds the *app* bundle — the cuda bundle is consumed inside
    trigger_swap when present.
    """
    staging = _staging_dir(app_dir)
    if not staging.is_dir():
        return None

    candidates = sorted(
        [p for p in staging.glob("wispy-v*.zip") if not p.name.startswith("wispy-cuda-")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for zip_path in candidates:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                if zf.testzip() is None:
                    return zip_path
        except Exception:
            pass
        print(f"[update] Discarding invalid/corrupt staged ZIP: {zip_path.name}")
        zip_path.unlink(missing_ok=True)

    return None


def _find_staged_cuda_zip(app_dir: Path) -> Optional[Path]:
    staging = _staging_dir(app_dir)
    if not staging.is_dir():
        return None
    candidates = sorted(
        staging.glob("wispy-cuda-v*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for zip_path in candidates:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                if zf.testzip() is None:
                    return zip_path
        except Exception:
            pass
        print(f"[update] Discarding invalid/corrupt staged cuda ZIP: {zip_path.name}")
        zip_path.unlink(missing_ok=True)
    return None


# ---------------------------------------------------------------------------
# Post-swap startup hook
# ---------------------------------------------------------------------------

def handle_post_update_start(app_dir: Path, current_version: str) -> None:
    """Called at normal startup: if backup dir exists, a swap just succeeded."""
    backup = _backup_dir(app_dir)
    if not backup.is_dir():
        return

    ver = current_version.lstrip("v")
    print(f"[update] Updated to v{ver}. Welcome back.")

    for path in (_backup_dir(app_dir), _staging_dir(app_dir)):
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Swap trigger: unpack staged bundles, write PS helper, exit so swap can run
# ---------------------------------------------------------------------------

def trigger_swap(
    app_zip: Optional[Path],
    cuda_zip: Optional[Path],
    app_dir: Path,
    cuda_dir: Optional[Path] = None,
) -> None:
    """Unpack staged bundle(s), write swap PS script, launch it, then exit.

    At least one of `app_zip` / `cuda_zip` must be provided. Source
    installs print a hint and return without exiting.

    `cuda_dir` defaults to <app_dir>/cuda when not given (legacy behaviour).
    Pass an explicit path when the user has configured `cuda_path` to a
    non-default location.
    """
    if not getattr(sys, "frozen", False):
        print("[update] Swap is only supported in the portable build (wispy.exe).")
        return
    if app_zip is None and cuda_zip is None:
        return

    if cuda_dir is None:
        cuda_dir = _default_cuda_dir(app_dir)

    staging = _staging_dir(app_dir)
    print("[update] Applying staged update ...")

    new_app_bundle: Optional[Path] = None
    if app_zip is not None:
        unpack_dir = staging / "unpacked-app"
        if unpack_dir.exists():
            shutil.rmtree(unpack_dir)
        unpack_dir.mkdir(parents=True)
        with zipfile.ZipFile(app_zip) as zf:
            zf.extractall(unpack_dir)
        # build.ps1 packs `dist/wispy/`, so the ZIP top-level is wispy/
        candidate = unpack_dir / "wispy"
        new_app_bundle = candidate if candidate.is_dir() else unpack_dir

    new_cuda_bundle: Optional[Path] = None
    if cuda_zip is not None:
        unpack_dir = staging / "unpacked-cuda"
        if unpack_dir.exists():
            shutil.rmtree(unpack_dir)
        unpack_dir.mkdir(parents=True)
        with zipfile.ZipFile(cuda_zip) as zf:
            zf.extractall(unpack_dir)
        # release-cuda.yml packs the cuda/ directory, so the ZIP top-level is cuda/
        candidate = unpack_dir / "cuda"
        new_cuda_bundle = candidate if candidate.is_dir() else unpack_dir

    ps_path = staging / "_swap.ps1"
    ps_path.write_text(
        _build_swap_script(
            app_dir=app_dir,
            cuda_dir=cuda_dir,
            new_app_bundle=new_app_bundle,
            new_cuda_bundle=new_cuda_bundle,
            backup=_backup_dir(app_dir),
        ),
        encoding="utf-8",
    )

    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(ps_path)],
        creationflags=flags,
    )
    sys.exit(0)


def _build_swap_script(
    app_dir: Path,
    cuda_dir: Path,
    new_app_bundle: Optional[Path],
    new_cuda_bundle: Optional[Path],
    backup: Path,
) -> str:
    """Generate the PowerShell swap helper script as a string."""
    wl = sorted(_SWAP_WHITELIST)
    where_filter = " -and ".join(f"$_.Name -ne '{name}'" for name in wl)

    app_str = str(app_dir)
    cuda_target_str = str(cuda_dir)
    backup_str = str(backup)
    exe_str = str(app_dir / "wispy.exe")

    do_app = new_app_bundle is not None
    do_cuda = new_cuda_bundle is not None
    bundle_str = str(new_app_bundle) if do_app else ""
    cuda_str = str(new_cuda_bundle) if do_cuda else ""

    return f"""\
# wispy update swap script (auto-generated -- do not edit)
$ErrorActionPreference = 'Continue'
$AppDir       = '{app_str}'
$CudaTarget   = '{cuda_target_str}'
$BackupDir    = '{backup_str}'
$WispyExe     = '{exe_str}'
$DoAppSwap    = ${str(do_app).lower()}
$DoCudaSwap   = ${str(do_cuda).lower()}
$NewBundleDir = '{bundle_str}'
$NewCudaDir   = '{cuda_str}'

Write-Host '[update] Waiting for wispy.exe to exit ...'
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {{
    if (-not (Get-Process -Name 'wispy' -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 250
}}

if ($DoAppSwap) {{
    Write-Host '[update] Moving current app files to backup ...'
    if (Test-Path $BackupDir) {{ Remove-Item -Recurse -Force $BackupDir }}
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    Get-ChildItem $AppDir | Where-Object {{ {where_filter} }} | ForEach-Object {{
        try {{
            Move-Item $_.FullName (Join-Path $BackupDir $_.Name) -Force
        }} catch {{
            Write-Host "  Warning: could not move $($_.Name)"
        }}
    }}

    Write-Host '[update] Installing new app version ...'
    Get-ChildItem $NewBundleDir | Where-Object {{ {where_filter} }} | ForEach-Object {{
        $dest = Join-Path $AppDir $_.Name
        try {{
            if ($_.PSIsContainer) {{
                Copy-Item $_.FullName $dest -Recurse -Force
            }} else {{
                Copy-Item $_.FullName $dest -Force
            }}
        }} catch {{
            Write-Host "  Warning: could not copy $($_.Name)"
        }}
    }}
}} else {{
    # Even without an app swap we still create the backup dir as the
    # signal handle_post_update_start uses to detect a fresh swap.
    if (-not (Test-Path $BackupDir)) {{
        New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    }}
}}

if ($DoCudaSwap) {{
    Write-Host '[update] Replacing cuda runtime at' $CudaTarget '...'
    if (Test-Path $CudaTarget) {{ Remove-Item -Recurse -Force $CudaTarget }}
    $CudaParent = Split-Path -Parent $CudaTarget
    if (-not (Test-Path $CudaParent)) {{ New-Item -ItemType Directory -Force -Path $CudaParent | Out-Null }}
    Copy-Item $NewCudaDir $CudaTarget -Recurse -Force
}}

Write-Host '[update] Starting new wispy ...'
Start-Process $WispyExe
Write-Host '[update] Swap complete.'
"""
