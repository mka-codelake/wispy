<img src="./etc/logo.svg" width="400" align="right" alt="wispy"/>

# wispy

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)

> [!NOTE]
> **wispy** is in Beta. Configuration format and command-line options may change between minor versions.

Minimalist push-to-talk dictation tool for Windows. Press a hotkey, speak, release -- the text appears wherever your cursor is (Notepad, browser, VS Code, anywhere). Fully local, no cloud, no subscription.

- **Backend:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2/CUDA), model `large-v3-turbo`
- **Language:** German (configurable via config)
- **Footprint:** ~250 LOC, 6 direct dependencies, no GUI

## Overview

wispy solves a specific problem: speech input without cloud dependency, without privacy concerns, and without latency from network round-trips. If you dictate a lot and have an NVIDIA GPU, wispy provides an offline solution that transcribes faster and more accurately than most online services -- and not a single syllable ever leaves your local machine.

wispy is designed as a personal productivity tool. There is no GUI, no tray app, no cloud integration. It runs as a console process in the background and waits for a hotkey.

**Who is it for?** Windows users with an NVIDIA GPU who want to dictate offline and without subscription costs -- in any application that accepts keyboard input.

## Features

- **Push-to-Talk or Toggle** -- Start and stop recording via hotkey, freely configurable (`hold` or `toggle` mode)
- **Fully offline** -- Transcription runs entirely locally via `faster-whisper` (CTranslate2/CUDA), no network access after the initial model download
- **Works everywhere** -- Text output via clipboard paste (Ctrl+V simulation), compatible with any Windows application including umlauts and special characters
- **Clipboard protection** -- Previous clipboard content is automatically restored after pasting
- **Multilingual** -- Language configurable via ISO code in `config.yaml` (`de`, `en`, `fr`, ...)
- **Audio feedback** -- Beep tones signal recording start (800 Hz) and end (400 Hz) without screen distraction
- **Portable build** -- PyInstaller bundle (`build/build.ps1`) produces a self-contained `dist/wispy/` directory including CUDA DLLs; no Python required on the target machine
- **Flexible model path** -- Model is stored by default next to the source code in `models/`; freely configurable via `model_path` in `config.yaml`

---

## Requirements

| | |
|---|---|
| **Operating System** | Windows 10/11 **native** -- not WSL2 (due to microphone, hotkey, and keyboard simulation requirements) |
| **Python** | 3.10, 3.11, or 3.12 |
| **GPU** | NVIDIA GPU with ~3 GB free VRAM (for `large-v3-turbo` + `float16`) |
| **CUDA Toolkit** | **Version 12.x -- NOT 13.x.** `faster-whisper` uses `CTranslate2`, which currently only supports CUDA 12 (with cuDNN 9 -> CUDA >= 12.3). Recommended: **CUDA 12.9.1** (latest 12.x series, June 2025) or 12.6/12.8. Install manually -- it includes `cudart`, `cuBLAS`, and `cuDNN`, which `faster-whisper` needs at runtime. **Direct download (Windows x86_64):** [cuda_12.9.1_576.57_windows.exe](https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_576.57_windows.exe) (~3.56 GB) or the archive page [developer.nvidia.com/cuda-12-9-1-download-archive](https://developer.nvidia.com/cuda-12-9-1-download-archive). A selection of all 12.x versions can be found in the [CUDA Toolkit Archive](https://developer.nvidia.com/cuda-toolkit-archive). |
| **Admin rights** | Recommended at startup -- the `keyboard` library hooks into the global keyboard hook and requires this on most Windows systems |
| **Microphone** | Check privacy settings: *Settings -> Privacy -> Microphone -> Allow desktop apps* |
| **Disk space** | ~4 GB (model ~1.5 GB + venv + dependencies) |

---

## Setup

```powershell
# 1. Clone the repo
cd C:\path\to\wispy

# 2. Create and activate a venv
python -m venv .venv
.\.venv\Scripts\activate

# 3. Install wispy as an editable package (pulls all dependencies from pyproject.toml)
pip install -e .

# 4. First run (downloads the model ~1.6 GB on first launch)
python -m wispy
```

> On the **first** launch, `src/wispy/model_fetch.py` downloads the `large-v3-turbo` model (~1.6 GB) via `huggingface_hub.snapshot_download` directly into `<repo-root>\models\large-v3-turbo\`. No HuggingFace cache in your user profile -- the model sits next to the source code and moves with it if you relocate the folder. The target path is determined by `src/wispy/paths.py::resolve_model_path`; you can set a custom directory via `model_path` in `config.yaml`.

---

## Portable Build (optional)

If you don't want a Python installation on the target machine, you can build wispy as a portable one-folder bundle. The script `build/build.ps1` invokes PyInstaller with `build/wispy.spec` and produces `dist/wispy/` with `wispy.exe` plus an `_internal/` directory.

```powershell
# In the repo root, in a PowerShell:
.\build\build.ps1
```

The resulting `dist/wispy/` folder is self-contained:

- **No CUDA Toolkit** required on the target machine -- the bundle includes `cudart64_12.dll`, `cublas64_12.dll`, and `cudnn_*.dll` in `_internal/`. Only a current NVIDIA driver is needed (for `nvcuda.dll` and the kernel module, which must come from the system).
- **No installer.** Copy the folder, run `wispy.exe`, done.
- **Portable.** The folder can be moved to a USB drive or another machine; the already downloaded model travels along in `models/`.

End-user documentation for the bundle is located in `build/README.txt` and is copied by PyInstaller to `dist/wispy/README.txt`.

---

## Controls

**Default mode: Hold (Push-to-Talk)**

| Action | Key press |
|---|---|
| Start recording | **Hold F9** -> Beep 800 Hz |
| Stop recording + transcribe | Release F9 -> Beep 400 Hz -> Text is inserted at cursor |
| Recording discarded | Released in < 0.3 s -> `(too short, skipped)` in console |
| Quit wispy | **Ctrl+C** in the console window |

**Toggle mode** (set in `config.yaml`: `record_mode: toggle`)

| Action | Key press |
|---|---|
| Start recording | Press F9 once |
| Stop recording + transcribe | Press F9 again |

Text is inserted via clipboard + simulated Ctrl+V -- works in any application, including umlauts and special characters. The previous clipboard content is restored after insertion (can be disabled via `restore_clipboard: false`).

---

## Configuration

All settings are in `config.yaml`. The most important ones:

```yaml
hotkey: "F9"              # Any key -- "F9", "F12", "ctrl+space", ...
record_mode: "hold"       # "hold" or "toggle"
language: "de"            # ISO code -- "de", "en", "fr", ...
model_name: "large-v3-turbo"   # Also: "small", "medium", "large-v3"
device: "cuda"            # "cuda" or "cpu"
compute_type: "float16"   # "float16" (GPU) / "int8" (CPU)
audio_device: null        # null = default microphone, otherwise index
restore_clipboard: true   # Restore old clipboard content after insertion
```

Load a custom config:

```powershell
python -m wispy --config C:\path\to\my-config.yaml
```

---

## Vocabulary (Hotwords)

Whisper sometimes mis-transcribes technical terms, file names, or proper names (e.g. `wispy` → `Whispy`, `.gitignore` → `Gitignore`). The vocabulary file lets you bias the model towards recognising specific terms correctly.

**Location:** `hotwords.txt` next to `config.yaml` (same folder as `wispy.exe` or the repo root when running from source).

**Format:** plain text, one term per line. Lines starting with `#` and blank lines are ignored.

```text
# wispy vocabulary
wispy
.gitignore
pyproject.toml
MyCompanyName
```

**How it works:** Terms are passed to `faster-whisper`'s `hotwords` parameter on every transcription call. This is a soft bias — it makes the model *prefer* these spellings but does not guarantee them. For hard replacements, a post-processing step is planned separately.

**Hot-reload:** Not supported. Restart wispy after editing `hotwords.txt`.

**Startup feedback:** wispy prints the number of loaded terms at startup:
```
[wispy] vocabulary  = 3 term(s) loaded
```

---

## Project Structure

```
wispy/
├── src/wispy/
│   ├── __init__.py       # Package marker, __version__
│   ├── __main__.py       # Entry point for `python -m wispy`
│   ├── main.py           # Main loop, orchestration, UAC elevation
│   ├── audio.py          # Microphone recording (sounddevice/PortAudio)
│   ├── transcribe.py     # Whisper model loading and transcription
│   ├── hotkey.py         # Global hotkey listener (hold + toggle)
│   ├── output.py         # Text output via clipboard paste
│   ├── feedback.py       # Beep sounds (winsound)
│   ├── config.py         # Config dataclass + YAML loader
│   ├── paths.py          # Model path resolution (src-aware + frozen)
│   └── model_fetch.py    # First-run download via HuggingFace Hub
├── build/
│   ├── build.ps1         # Portable build script (uv + PyInstaller)
│   ├── wispy.spec        # PyInstaller spec
│   └── README.txt        # End-user documentation for the bundle
├── etc/
│   └── logo.svg          # Project logo
├── config.yaml           # Default configuration
├── hotwords.txt          # Vocabulary list for transcription biasing (hotwords)
└── pyproject.toml        # Package metadata and dependencies
```

Internal imports use relative imports (`from .audio import Recorder`). Exception: `__main__.py` uses an absolute import so that PyInstaller can correctly load the entry script as top-level.

---

## Auto-Update

wispy checks for updates in the background on every start and notifies you if a newer release is available. It never downloads anything without your explicit consent.

### How the update flow works

1. **Version check (automatic):** At every start, wispy queries the GitHub release API in a background thread. Dictation is immediately ready — the check does not block startup. If a newer version is available, a message appears in the console:
   ```
   [update] Update available: v0.2.0 -> v0.3.0
   [update] To download, start wispy again with --update
   ```

2. **Download (explicit, with `--update`):** When you want to fetch the new version, start wispy once with `--update`:
   ```powershell
   wispy.exe --update
   ```
   The release ZIP is downloaded to `update-staging/` next to `wispy.exe`. Dictation works normally for the rest of that session.

3. **Apply on next normal start (automatic):** On the next regular start (without `--update`), wispy detects the staged ZIP, unpacks it, and launches a PowerShell helper script that performs the swap while wispy is not running. The new version then starts automatically.

### Protected files — never touched during an update

The following files and folders are always excluded from the swap:

| Path | What it contains |
|---|---|
| `config.yaml` | Your configuration |
| `models/` | Downloaded Whisper model (~1.6 GB) |
| `hotwords.txt` | Your vocabulary list |

### Disable update check

Set `update_check: false` in `config.yaml`:

```yaml
update_check: false
```

When disabled, wispy performs no background check at startup, no staging, no swap, and `--update` has no effect (displays a message instead).

### Authentication (optional)

If the repository is private or you hit GitHub's anonymous rate limit, set the `GITHUB_TOKEN` environment variable. wispy uses it automatically as a Bearer token for all API and download requests.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first for guidelines on branching, commit conventions, and the pull request process.

---

## Troubleshooting

| Symptom | Cause | Solution |
|---|---|---|
| `Could not load library cudnn_*.dll` / `cublas64_*.dll` | CUDA Toolkit missing, is **version 13.x** (incompatible with CTranslate2), or not in PATH | Install CUDA Toolkit **12.x** (recommended: 12.9.1), then restart the console |
| Hotkey does not respond to F9 | Console not started as admin | Start wispy in an admin PowerShell |
| `Failed to query device 0` / no audio | No microphone detected or permission missing | Check Windows privacy settings, try a different `audio_device` in config |
| `(too short, skipped)` on every press | Hotkey held too briefly (< 0.3 s) | Hold longer or reduce `MIN_DURATION_SEC` in `src/wispy/main.py` |
| First transcription takes very long | Model is being downloaded (~1.5 GB) | One-time process, cached afterwards |
| Transcription wrong or empty | Wrong language, poor microphone signal, speaking too quietly | Check `language` in config, move closer to the microphone |

---

## License

Copyright 2026 Michael Kagel

wispy is free software and licensed under the **GNU General Public License v3.0 or (at your option) any later version**. See [LICENSE](LICENSE) for the full license text.

wispy is distributed in the hope that it will be useful, but **WITHOUT ANY WARRANTY**; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Contributions are also licensed under GPL v3 -- details in [CONTRIBUTING.md](CONTRIBUTING.md).
