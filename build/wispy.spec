# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for wispy -- Windows portable One-Folder bundle.

Build (from the repo root, inside the build venv):
    pyinstaller build/wispy.spec --clean --noconfirm

Output:
    dist/wispy/wispy.exe      entry point, asInvoker (wispy self-elevates)
    dist/wispy/_internal/     Python runtime, libs, and CUDA DLLs
"""

import site
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# build/wispy.spec -> repo root is one level up from SPECPATH.
ROOT = Path(SPECPATH).resolve().parent


def _find_nvidia_dlls():
    """Collect every .dll shipped by nvidia-* pip packages.

    nvidia-cublas-cu12, nvidia-cudnn-cu12 and nvidia-cuda-runtime-cu12 each
    install their DLLs under `<site-packages>/nvidia/<libname>/bin/*.dll`.
    PyInstaller's automatic hooks are inconsistent about picking these up,
    so we enumerate them ourselves and drop every DLL at the top of the
    bundle so CTranslate2 finds them via the default Windows DLL search
    order.
    """
    seen = set()
    results = []

    search_roots = [Path(p) for p in site.getsitepackages()]
    search_roots.append(Path(site.getusersitepackages()))

    for sp in search_roots:
        nvidia_root = sp / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for dll in nvidia_root.rglob("*.dll"):
            key = dll.name.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append((str(dll), "."))
    return results


# Pull in everything from ctranslate2 and faster_whisper: binaries, data
# files, and hidden imports. collect_all handles the tricky bits of each
# package (the Silero VAD asset lives inside faster_whisper).
ct2_datas, ct2_binaries, ct2_hidden = collect_all("ctranslate2")
fw_datas, fw_binaries, fw_hidden = collect_all("faster_whisper")

nvidia_binaries = _find_nvidia_dlls()

a = Analysis(
    [str(ROOT / "wispy.py")],
    pathex=[str(ROOT)],
    binaries=ct2_binaries + fw_binaries + nvidia_binaries,
    datas=ct2_datas + fw_datas,
    hiddenimports=[
        "ctranslate2",
        "sounddevice",
        "keyboard",
        "pyperclip",
        "huggingface_hub",
        "yaml",
    ] + ct2_hidden + fw_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wispy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # asInvoker: wispy itself handles elevation via ShellExecute("runas").
    uac_admin=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="wispy",
)
