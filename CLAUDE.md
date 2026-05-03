# wispy -- Local offline dictation tool

## What is wispy?

A minimal push-to-talk dictation tool for Windows. The user holds a hotkey,
speaks, releases -- the transcribed text appears wherever the cursor is
(Notepad, browser, VS Code, anywhere). Fully local, no cloud service.

## Repo language

All repo content -- code, comments, commit messages, release notes, this
file -- is **English**. wispy is not localised; the German `language: de`
default in `config.yaml` only configures Whisper's transcription target,
not the project itself. Avoid German strings anywhere in the repository,
including in tests and docs.

## Tech stack

- **STT**: `faster-whisper` (CTranslate2) with Whisper Large V3 Turbo. CUDA optional via lazy loading; the CPU default works without NVIDIA hardware.
- **Audio**: `sounddevice` (PortAudio), 16 kHz mono
- **Hotkey**: `keyboard` library, system-wide
- **Text output**: `pyperclip` + `keyboard` (clipboard paste via Ctrl+V)
- **Feedback**: `winsound` (beep on start/stop)
- **Config**: `PyYAML` + dataclass

## Architecture

- Threading (no asyncio) -- the hotkey hook, the PortAudio callback and the GPU transcription are all blocking.
- Clipboard paste rather than keyboard simulation -- fast, Unicode-safe, works everywhere.
- No GUI in v1 -- console output is enough.
- No own VAD -- push-to-talk is sufficient; faster-whisper carries Silero-VAD.
- **Must run natively on Windows** (not WSL2) -- microphone, hotkeys, keyboard simulation all need Windows native APIs.
- **Update mechanism** (`updater.py`): at startup wispy queries two asset streams independently -- the app bundle (tag `vX.Y.Z`) and the CUDA bundle (tag `cuda-vX.Y.Z`). Three configuration tiers: `update_check: false` (no check), `update_check: true, auto_update: false` (default -- check, prompt, self-restart on accept), `update_check: true, auto_update: true` (silent). On update the matching asset is fetched, the swap is performed, and wispy restarts itself -- all in one run, no second click required. **Whitelist** for the swap: `config.yaml`, `models/`, `hotwords.txt`, `cuda/`. Active only in the frozen build.

### Bundle architecture -- plugin/component model

Two independently versioned artefacts on GitHub Releases:

- **App bundle** (~400 MB): app code + Python runtime + non-CUDA libs. Tag schema `vX.Y.Z`, sanity-checked against `pyproject.toml` in CI. Asset name `wispy-vX.Y.Z.zip`.
- **CUDA bundle** (~1.5 GB): only the CUDA DLLs from the `nvidia-*` pip packages. Tag schema `cuda-vX.Y.Z` (mirrors the CUDA toolkit version, optional build counter `cuda-vX.Y.Z-bN`). Asset name `wispy-cuda-vX.Y.Z.zip`.

Local layout:

```
app_dir/
  wispy.exe
  _internal/        # Python + non-CUDA libs (always)
  cuda/             # optional, lazy-loaded
    cublas64_12.dll
    cudnn_*.dll
    cudart64_12.dll
    _version.txt    # written by CI
  config.yaml
  models/
```

**Lazy CUDA loading flow**: at startup wispy probes whether a NVIDIA GPU is present (via `nvidia-smi` / WMI / Registry). If yes AND `cuda/` is missing -> console prompt "Download CUDA runtime now? [y/n]". On `y` the CUDA bundle is fetched into `cuda/`. On `n` or no GPU -> CPU mode (`device: "auto"` is configured). CTranslate2 finds the DLLs via `os.add_dll_directory(app_dir / "cuda")` plus a `PATH` prepend before the `WhisperModel()` call. On a CUDA error at runtime -> CPU fallback with a console hint.

## Project layout

Standard Python src layout (PyPA recommendation), launch via `python -m wispy`.

```
src/wispy/
  __init__.py       # package marker, __version__
  __main__.py       # entry for `python -m wispy` (absolute import to wispy.main)
  main.py           # main loop, orchestration, admin elevation
  audio.py          # microphone capture (sounddevice)
  transcribe.py     # load + run the Whisper model
  hotkey.py         # global hotkey, hold + toggle modes
  output.py         # text injection via clipboard paste
  feedback.py       # beep sounds (winsound)
  config.py         # config loader (YAML -> dataclass)
  paths.py          # app_dir / model path resolution (src-aware + frozen-aware)
  model_fetch.py    # first-run HuggingFace snapshot download
  gpu_detect.py     # NVIDIA GPU detection at startup (nvidia-smi / WMI / Registry)
  cuda_loader.py    # lazy download of the CUDA bundle + DLL search-path setup
  updater.py        # update mechanism: dual-stream check, asset selection, self-restart swap
  download.py       # chunked HTTP download with carriage-return progress
build/
  build.ps1         # portable build via uv + PyInstaller
  wispy.spec        # PyInstaller spec (entry: src/wispy/__main__.py)
  extract_release_notes.py     # CHANGELOG -> GitHub Release body extractor
  cuda-release-notes.md.template

pyproject.toml      # package metadata + dependencies (setuptools backend)
config.yaml         # default configuration in the repo root
CHANGELOG.md        # canonical release notes (drives the GitHub Release body)
```

Internal imports are **relative** (`from .audio import Recorder`) -- exception: `__main__.py` uses an **absolute** import (`from wispy.main import main`) so PyInstaller can load the entry script as a top-level module.

## Data flow

```
[Hotkey pressed]    -> Beep(800 Hz) -> Recorder.start()
[User speaks]       -> PortAudio callback fills the chunk list
[Hotkey released]   -> Recorder.stop() -> Beep(400 Hz) -> audio_queue.put(audio)
Transcription worker: audio -> faster-whisper.transcribe() -> output.type_text()
output.type_text:    save clipboard -> set text -> Ctrl+V -> restore clipboard
```

## Running

```powershell
# On Windows (not WSL2!):
pip install -e .
python -m wispy
```

First start with a NVIDIA GPU: optional console prompt to download the CUDA bundle (~1.5 GB into `<app_dir>/cuda/`). On `n` or without a NVIDIA GPU, wispy runs on CPU.

First start fetches the Whisper model (~1.6 GB into `<repo-root>/models/large-v3-turbo/`, cached afterwards).
The `keyboard` library needs admin rights -- `main.py::_elevate_and_exit()` triggers UAC automatically and relaunches `python -m wispy <args>` (source run) or `wispy.exe <args>` (frozen) with "runas".

## Releases

The canonical app version lives in `pyproject.toml`; `__version__` is derived from it via `importlib.metadata`.

**App release** (tag `vX.Y.Z`): bump the version in `pyproject.toml` -> commit -> `git tag vX.Y.Z && git push origin main --tags`. The `.github/workflows/release.yml` workflow builds `wispy-vX.Y.Z.zip` (app code, no CUDA) on `windows-latest` and publishes the release. The release body is extracted from `CHANGELOG.md` -- so the matching `## [X.Y.Z]` block must exist before the tag is pushed, otherwise the workflow fails.

**CUDA release** (tag `cuda-vX.Y.Z`): manual tag push, e.g. `git tag cuda-v12.9.1 && git push origin cuda-v12.9.1`. The `.github/workflows/release-cuda.yml` workflow installs `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` + `nvidia-cuda-runtime-cu12` via uv, packs the DLLs together with a `_version.txt` into `wispy-cuda-vX.Y.Z.zip` and publishes a separate release whose body is rendered from `build/cuda-release-notes.md.template`.

CUDA releases are rare (gated by CUDA toolkit bumps). App releases evolve independently. The in-tool updater queries both streams.

**Manual fallback for the app build**: `build.ps1 -CreateZip` -> `gh release create` (details in `CONTRIBUTING.md`).

## Implementation status

- [x] Project layout (src layout, pyproject.toml, .gitignore)
- [x] config.py / config.yaml / audio.py / transcribe.py / hotkey.py / output.py / feedback.py / paths.py / model_fetch.py / main.py -- v1 baseline
- [x] Portable build via build/build.ps1 + build/wispy.spec (now plugin-model; CUDA DLLs out of the app bundle)
- [x] Update mechanism v1 + dual-stream rewrite (`updater.py`)
- [x] Plugin model -- app bundle without CUDA
- [x] CUDA bundle as a separate release artefact
- [x] `gpu_detect.py` + `cuda_loader.py` -- lazy CUDA loading
- [x] Updater dual-stream + self-restart
- [x] UI/UX polish (progress display, harmonised console logs)
- [x] config.yaml auto-migration on startup when fields are added in newer versions

## Verification

| Test | Expectation |
|------|-------------|
| Hold F9, say "Hello world", release | text appears in Notepad |
| Toggle: F9, speak, F9 | transcription appears |
| Press and release within 0.3 s | "(too short, skipped)" in console |
| Clipboard had content before | original clipboard restored after dictation |

## Issue-label conventions

- `do-not-automate` -- hands off for the bot, the issue is not picked up by `@claude` triggers.
- `parked` -- intentionally deferred for later re-evaluation. Usually combined with `do-not-automate`. The reason belongs in a comment on the issue (date + why).
  - **Re-activation**: remove both labels.
  - **Final rejection**: close the issue with reason `not planned` and add the `wontfix` label.
- Workflow-level rules for bot behaviour: see `.github/AGENT_BRIEFING.md`.
