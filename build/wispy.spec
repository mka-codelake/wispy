# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for wispy -- Windows portable One-Folder bundle (CPU-only).

Build (from the repo root, inside the build venv):
    pyinstaller build/wispy.spec --clean --noconfirm

Entry point is src/wispy/__main__.py. The src/ directory is added to
pathex so PyInstaller resolves the `wispy` package correctly.

Output:
    dist/wispy/wispy.exe      entry point, asInvoker (wispy self-elevates)
    dist/wispy/_internal/     Python runtime and non-CUDA libs

CUDA DLLs are deliberately NOT bundled here. They live in a separate
release artifact (`wispy-cuda-vX.Y.Z.zip`) and are loaded lazily into
`<app_dir>/cuda/` on demand. See CLAUDE.md > Bundle-Architektur.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# build/wispy.spec -> repo root is one level up from SPECPATH.
ROOT = Path(SPECPATH).resolve().parent


# Pull in everything from ctranslate2 and faster_whisper: binaries, data
# files, and hidden imports. collect_all handles the tricky bits of each
# package (the Silero VAD asset lives inside faster_whisper). Note:
# CTranslate2 itself is shipped without CUDA libs — those come via the
# separate CUDA bundle.
ct2_datas, ct2_binaries, ct2_hidden = collect_all("ctranslate2")
fw_datas, fw_binaries, fw_hidden = collect_all("faster_whisper")

a = Analysis(
    [str(ROOT / "src" / "wispy" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=ct2_binaries + fw_binaries,
    datas=ct2_datas + fw_datas,
    hiddenimports=[
        "wispy",
        "wispy.main",
        "wispy.audio",
        "wispy.config",
        "wispy.feedback",
        "wispy.hotkey",
        "wispy.model_fetch",
        "wispy.output",
        "wispy.paths",
        "wispy.transcribe",
        "wispy.updater",
        "ctranslate2",
        "sounddevice",
        "keyboard",
        "pyperclip",
        "huggingface_hub",
        "yaml",
        "packaging",
        "packaging.version",
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
