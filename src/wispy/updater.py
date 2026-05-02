"""Update mechanism: background version check, staged download, and next-boot swap."""

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from packaging.version import Version

_GITHUB_REPO = "mka-codelake/wispy"
_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"

# Names the swap must never move or overwrite
_SWAP_WHITELIST = frozenset({
    "config.yaml",
    "hotwords.txt",
    "models",
    "update-backup",
    "update-staging",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _request_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "wispy-updater"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _fetch_release_data() -> Optional[dict]:
    """Fetch the latest release JSON from GitHub API. Returns None on any error."""
    try:
        req = urllib.request.Request(_API_URL, headers=_request_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[update] Check failed ({type(e).__name__}): {e}")
        return None


def _parse_version(v: str) -> Optional[Version]:
    try:
        return Version(v.lstrip("v"))
    except Exception:
        return None


def _staging_dir(app_dir: Path) -> Path:
    return app_dir / "update-staging"


def _backup_dir(app_dir: Path) -> Path:
    return app_dir / "update-backup"


# ---------------------------------------------------------------------------
# Phase 1 — version check
# ---------------------------------------------------------------------------

def _run_check_verbose(current_version: str) -> None:
    """Query GitHub for the latest release and print the result to the console."""
    print("[update] Checking for updates ...")
    data = _fetch_release_data()
    if data is None:
        return  # error already printed

    tag = data.get("tag_name", "").strip()
    if not tag:
        print("[update] Remote version unavailable.")
        return

    remote_ver = _parse_version(tag)
    local_ver = _parse_version(current_version)

    if remote_ver is None or local_ver is None:
        print("[update] Could not parse version strings.")
        return

    if remote_ver <= local_ver:
        print(f"[update] No update available (current: v{local_ver})")
    else:
        print(f"[update] Update available: v{local_ver} -> {tag}")
        print("[update] To download, start wispy again with --update")


def start_update_check_thread(current_version: str) -> None:
    """Start a background thread that checks for updates without blocking startup."""
    threading.Thread(
        target=_run_check_verbose,
        args=(current_version,),
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Phase 2 — staged download (explicit --update trigger only)
# ---------------------------------------------------------------------------

def download_staged_update(current_version: str, app_dir: Path) -> bool:
    """Check for update and download the release ZIP to the staging folder.

    Returns True on success. Only works in the portable (frozen) build.
    Source installs should use ``git pull`` / ``pip install -e .`` instead.
    """
    if not getattr(sys, "frozen", False):
        print("[update] --update only works in the portable build (wispy.exe).")
        print("[update] For source installs: git pull && pip install -e .")
        return False

    print("[update] Checking for updates ...")
    data = _fetch_release_data()
    if data is None:
        return False

    tag = data.get("tag_name", "").strip()
    if not tag:
        print("[update] Remote version unavailable.")
        return False

    remote_ver = _parse_version(tag)
    local_ver = _parse_version(current_version)

    if remote_ver is None or local_ver is None:
        print("[update] Could not parse version strings.")
        return False

    if remote_ver <= local_ver:
        print(f"[update] No update available (current: v{local_ver})")
        return False

    expected_name = f"wispy-v{remote_ver}.zip"
    assets = data.get("assets", [])
    asset = next((a for a in assets if a["name"] == expected_name), None)
    if not asset:
        print(f"[update] Asset '{expected_name}' not found in latest release.")
        return False

    staging = _staging_dir(app_dir)
    staging.mkdir(parents=True, exist_ok=True)

    lock = staging / ".lock"
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        print("[update] Another download is already in progress.")
        return False

    zip_path = staging / expected_name
    try:
        if zip_path.exists():
            zip_path.unlink()

        size = asset.get("size", 0)
        size_str = f" ({size / 1024 / 1024:.1f} MB)" if size else ""
        print(f"[update] Downloading {expected_name}{size_str} ...")

        req = urllib.request.Request(
            asset["browser_download_url"],
            headers=_request_headers(),
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(zip_path, "wb") as out:
                shutil.copyfileobj(resp, out)

        print("[update] Download complete. Will apply on next normal start.")
        return True

    except Exception as e:
        print(f"[update] Download failed: {e}")
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    finally:
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Phase 3 — next-boot swap
# ---------------------------------------------------------------------------

def find_staged_zip(app_dir: Path) -> Optional[Path]:
    """Return the path to a valid staged ZIP, or None if none exists.

    Incomplete or corrupt ZIPs are discarded automatically.
    """
    staging = _staging_dir(app_dir)
    if not staging.is_dir():
        return None

    candidates = sorted(
        staging.glob("wispy-v*.zip"),
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


def handle_post_update_start(app_dir: Path, current_version: str) -> None:
    """Called at normal startup: if backup dir exists, a swap just succeeded.

    Prints the success message and removes backup and staging directories.
    """
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


def trigger_swap(zip_path: Path, app_dir: Path) -> None:
    """Unpack staged ZIP, write PowerShell swap script, launch it, then exit.

    This function never returns for frozen builds: it calls sys.exit(0) to
    release the wispy.exe file lock so the swap script can replace it.
    For source installs it prints a message and returns without exiting.
    """
    if not getattr(sys, "frozen", False):
        print("[update] Swap is only supported in the portable build (wispy.exe).")
        return

    staging = _staging_dir(app_dir)
    unpack_dir = staging / "unpacked"

    print("[update] Applying staged update ...")

    if unpack_dir.exists():
        shutil.rmtree(unpack_dir)
    unpack_dir.mkdir(parents=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(unpack_dir)

    # build.ps1 uses: Compress-Archive -Path dist/wispy
    # So the ZIP contains a top-level wispy/ subfolder.
    new_bundle = unpack_dir / "wispy"
    if not new_bundle.is_dir():
        new_bundle = unpack_dir  # fallback: flat ZIP structure

    ps_path = staging / "_swap.ps1"
    ps_path.write_text(
        _build_swap_script(app_dir, new_bundle, _backup_dir(app_dir)),
        encoding="utf-8",
    )

    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(ps_path)],
        creationflags=flags,
    )
    sys.exit(0)


def _build_swap_script(app_dir: Path, new_bundle: Path, backup: Path) -> str:
    """Generate the PowerShell swap helper script as a string."""
    wl = sorted(_SWAP_WHITELIST)
    # PowerShell Where-Object filter that excludes all whitelist names
    where_filter = " -and ".join(f"$_.Name -ne '{name}'" for name in wl)

    app_str = str(app_dir)
    bundle_str = str(new_bundle)
    backup_str = str(backup)
    exe_str = str(app_dir / "wispy.exe")

    return f"""\
# wispy update swap script (auto-generated -- do not edit)
$ErrorActionPreference = 'Continue'
$AppDir       = '{app_str}'
$NewBundleDir = '{bundle_str}'
$BackupDir    = '{backup_str}'
$WispyExe     = '{exe_str}'

Write-Host '[update] Waiting for wispy.exe to exit ...'
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {{
    if (-not (Get-Process -Name 'wispy' -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 250
}}

Write-Host '[update] Moving current files to backup ...'
if (Test-Path $BackupDir) {{ Remove-Item -Recurse -Force $BackupDir }}
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Get-ChildItem $AppDir | Where-Object {{ {where_filter} }} | ForEach-Object {{
    try {{
        Move-Item $_.FullName (Join-Path $BackupDir $_.Name) -Force
    }} catch {{
        Write-Host "  Warning: could not move $($_.Name)"
    }}
}}

Write-Host '[update] Installing new version ...'
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

Write-Host '[update] Starting new wispy ...'
Start-Process $WispyExe
Write-Host '[update] Swap complete.'
"""
