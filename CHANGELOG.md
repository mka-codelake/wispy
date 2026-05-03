# Changelog

All notable changes to wispy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.5] — 2026-05-03

### Changed
- **Documentation language standardised on English.** All repo
  artefacts that are visible to contributors, end users or in GitHub
  Releases are now in English: this changelog (every prior block has
  been re-written), `CLAUDE.md`, the in-bundle `build/README.txt`,
  test fixture data, and the `AGENT_BRIEFING.md` style rule. Code,
  console output and config comments were already English.

## [0.4.4] — 2026-05-03

Polish for `config.yaml` plus automatic migration for older user-side
copies of the file.

### Changed
- **`config.yaml` reordered and consistently commented.** Path-typed
  fields now sit next to their functional block (`model_path` under
  Model, `cuda_path` under CUDA), the test bootstrap fields
  (`model_local_source`, `cuda_local_source`) live in their own
  "Local sources (advanced / for testing)" section. Every path field
  has a 3-4 line explanation block plus a commented example value —
  the same depth as the original `model_path` block. Section headers
  are visually separated by `# ===` rules.

### Added
- **Automatic migration of the user-side `config.yaml`** at startup.
  When wispy ships fields the user's existing `config.yaml` does not
  contain yet, a migration runs:
  - **Backup** the existing file to `config.yaml.backup` (overwrites
    on subsequent migrations — most recent state wins).
  - **Default template** (a copy of the active `config.yaml` shipped
    inside the bundle) is used as the new base.
  - **Customised values** from the old file are line-replaced into the
    new template — dataclass-default vs. user value is compared, every
    deviation is preserved.
  - **Comments** in the old `config.yaml` are not preserved (the backup
    keeps them). Section comments come from the new template.
  - **Multi-line values** (e.g. block-scalar `initial_prompt`) are not
    auto-migrated — the template default is used and a console hint
    asks the user to re-apply manually from the backup.
  - **Write errors or missing template** are non-fatal: wispy keeps
    starting, the console shows a warning, the user file is left
    untouched. Dataclass defaults still cover the missing fields at
    runtime.

### Internal
- `paths.default_config_template_path()` resolves the template path
  (frozen: `_internal/config.yaml.default`, source: `<repo>/config.yaml`).
- `build.ps1` snapshots `config.yaml` -> `config.yaml.default` just
  before PyInstaller runs, `wispy.spec` includes that file via `datas`.
  The snapshot file is gitignored.
- `config.load_config(path, migrate=True)` — the new `migrate`
  keyword defaults to True; tests can pass `migrate=False` for
  side-effect-free isolation.

## [0.4.3] — 2026-05-03

Hotfix for two issues that survived in v0.4.1 / v0.4.2.

### Fixed
- **CUDA libraries not found despite a successful install.** In v0.2.0
  / v0.3.0 the NVIDIA DLLs lived in `<app_dir>/_internal/`, a directory
  Windows automatically searches when loading DLLs from a frozen
  PyInstaller bundle. Plugin-model from v0.4.0 onwards puts them in
  `<cuda_dir>` (default `<app_dir>/cuda/`), which is *not* on the
  default search path. `os.add_dll_directory()` alone is not enough —
  CTranslate2 loads cuBLAS / cuDNN / cudart as transitive dependencies
  via the standard resolver, which honours `PATH`. wispy now prepends
  `cuda_dir` to `os.environ["PATH"]` at startup so every DLL lookup
  (including transitive ones) sees the directory. Symptom was
  `[transcribe] CUDA load failed: Library cublas64_12.dll is not found
  or cannot be loaded` on the first hotkey press, followed by the CPU
  fallback. With the fix wispy uses the GPU on NVIDIA machines as
  intended.
- **Model download showed no progress.** v0.4.1 set
  `HF_HUB_DISABLE_PROGRESS_BARS=1` to drop a cosmetic `Download
  complete:` line that landed below `[wispy] Ready!`. The trade-off
  was too harsh — users sat in front of five minutes of silent output.
  wispy now lets huggingface_hub display its tqdm bar again. The
  cosmetic trailing line after `Ready!` is accepted as the smaller
  problem.

## [0.4.2] — 2026-05-03

Test ergonomics: local sources for the CUDA bundle and the Whisper
model.

### Added
- **`cuda_path`** in `config.yaml` — storage choice for the CUDA
  runtime, analogous to `model_path`. Default `null` means
  `<wispy>/cuda/`. Useful when several wispy installs share one CUDA
  bundle, or when CUDA should live outside the wispy folder. The
  updater, the lazy installer and the swap helper all respect the
  configured path.
- **`model_local_source`** — path to a complete local model directory.
  When set, wispy copies the files from there at first start instead
  of pulling from Hugging Face. Saves the 1.6 GB download during test
  iterations.
- **`cuda_local_source`** — path to a `wispy-cuda-*.zip` file or to an
  already extracted CUDA directory. When set, wispy installs from
  that source without network access (no prompt). Useful for testing
  pre-release CUDA bundles or working offline.

### Changed
- `cuda_loader` API extended: `*_at` variants of the helpers accept an
  explicit `cuda_dir` (`is_cuda_installed_at`,
  `find_local_cuda_version_at`, `add_cuda_to_dll_search_path_at`,
  `install_cuda_bundle(..., cuda_dir=...)`). The legacy `app_dir`-based
  functions stay as wrappers.
- `updater.check_for_updates` and `updater.trigger_swap` accept an
  optional `cuda_dir` so the configured path is used consistently
  across the whole update flow. The PowerShell swap script writes the
  CUDA update to that explicit target rather than hard-coded
  `<app_dir>/cuda`.

## [0.4.1] — 2026-05-03

Hotfix for the UX and stability issues found in v0.4.0 during the
first hands-on test.

### Fixed
- **`cublas64_12.dll not found` on first dictation.** v0.4.0 could end
  up initialising the Transcriber with `device="auto"` even when no
  CUDA bundle was present — the crash then only surfaced on the first
  hotkey press. The startup path now always checks whether
  `<app_dir>/cuda/` exists and contains DLLs; if not, the Transcriber
  is forced to `device="cpu"`.
- **GPU detection more robust** — new tri-state probe
  (`yes` / `no` / `unknown`). When `nvidia-smi` is missing on PATH or
  times out, wispy now still asks instead of silently defaulting to
  CPU. The previous behaviour could leave a real NVIDIA card
  undetected and skip the CUDA prompt.
- **Additional runtime fallback in `transcribe.py`** — even when
  CTranslate2 only loads its CUDA libraries lazily on the first
  inference and fails there, wispy now rebuilds the model on CPU
  internally and completes the transcription. No more hard crash
  during a hotkey press.

### Changed
- **No self-restart after the CUDA download.** After a successful CUDA
  install wispy keeps running in the same process — the model
  download and the rest of startup happen seamlessly without a
  second program launch.
- **Console cleaned up after `Ready!`.** The `Download complete: …`
  line from `huggingface_hub` no longer trails past
  `[wispy] Ready!`. wispy sets `HF_HUB_DISABLE_PROGRESS_BARS=1` and
  emits its own concise status messages for the model download.

## [0.4.0] — 2026-05-03

### Changed
- **Plugin-/component-bundle architecture** — the application and the
  CUDA runtime are now shipped as two independently versioned release
  artefacts: the app bundle (`wispy-vX.Y.Z.zip`, ~400 MB) and the
  CUDA bundle (`wispy-cuda-vX.Y.Z.zip`, ~1.5 GB). Previously the app
  bundle contained the CUDA DLLs directly and was ~2 GB.
- **Default mode is CPU** — `device: "auto"` is the new default. On
  systems without a NVIDIA card wispy runs straight on CPU. On systems
  with a NVIDIA card wispy asks once at first start whether to fetch
  the CUDA bundle.

### Added
- **Lazy CUDA loading** — at first start with a detected NVIDIA GPU
  wispy offers (in the console) to download the matching CUDA bundle
  from GitHub Releases. On confirmation the bundle is extracted into
  `<app_dir>/cuda/`; on decline wispy continues on CPU.
- **Dual-stream updater** — the update check queries the app stream
  (`vX.Y.Z`) and the CUDA stream (`cuda-vX.Y.Z`) independently. An
  app-only update leaves the local CUDA bundle untouched and vice
  versa.
- **Three update tiers** in `config.yaml`:
  - `update_check: false` — no check, no prompt.
  - `update_check: true, auto_update: false` — check and prompt
    (new default).
  - `update_check: true, auto_update: true` — silent update plus
    restart.
- **Self-restart after update** — after a successful swap wispy
  restarts itself in the new version; no manual launch needed.
- **Download progress** — for both app and CUDA downloads wispy
  shows continuous progress, throughput and ETA in the console.
- **Robust CPU fallback in `transcribe.py`** — if CUDA fails during
  the model load phase, wispy automatically falls back to CPU
  (`int8`) and prints a clear notice.

### Fixed
- An app update no longer overwrites the local CUDA bundle —
  `cuda/` is now explicitly on the swap whitelist (alongside
  `config.yaml`, `models/` and `hotwords.txt`).

### Removed
- **CUDA DLLs are no longer part of the app bundle.** From v0.4.0
  onwards they live in the separate CUDA bundle. Anyone coming from
  v0.3.0 on a NVIDIA machine is asked once at first start whether to
  fetch the CUDA bundle.

### Migration

Coming from **v0.3.0**:

- The update flows through the built-in updater (the console reads
  "App update available: v0.3.0 -> v0.4.0").
- At first start after the update wispy asks about the CUDA bundle
  (only on machines with a NVIDIA card). `[y]` fetches it, `[n]` /
  Enter skips and wispy runs on CPU.
- Personal `config.yaml` is preserved. An old `device: "cuda"` value
  produces an explicit CUDA attempt after the update; if the
  libraries are not (yet) present, wispy falls back to CPU
  automatically.

## [0.3.0] — 2026-05-02

### Added
- **Client-side update mechanism** with non-blocking version check, explicit
  staged download via `--update`, and next-boot swap. Configuration files
  (`config.yaml`), Whisper models, and the user's vocabulary file are
  protected by a hard whitelist and are never overwritten by an update.
  Update check is opt-out via `update_check: false` in `config.yaml`. The
  mechanism operates only on the portable Windows bundle (`wispy.exe`);
  source installs see a hint to use `git pull` instead. (#5)
- **Vocabulary / hotwords mechanism** that biases Whisper's decoder toward
  domain-specific terms (technical jargon, names, abbreviations). Loaded
  from `hotwords.txt` next to the binary, one term per line. (#1)

### Notes
- The version check uses anonymous GitHub API access; no token is needed.
  The optional `GITHUB_TOKEN` environment variable is still honored for
  higher rate limits but never required.

## [0.2.0] — 2026-04-13

First public release. Before this point the repository was internal.

### Added
- **Push-to-talk dictation** on Windows with a global hotkey
  (default `F9`, configurable). Hold mode (press-and-hold) and
  toggle mode (press to start, press again to stop).
- **Local Whisper transcription** via `faster-whisper` + CTranslate2
  with `large-v3-turbo`. CUDA DLLs were bundled directly into the
  PyInstaller bundle (`_internal/`) at this point.
- **First-run Whisper model download** at startup (~1.6 GB into
  `<wispy>/models/`, cached afterwards).
- **Clipboard-paste output** instead of keyboard simulation — Unicode
  safe, fast, the previous clipboard contents are optionally restored.
- **Auto elevation** via UAC: the `keyboard` hook needs admin rights,
  wispy requests them itself.
- **PyInstaller one-folder build** via `build/build.ps1` with `uv` as
  the Python manager. Output is a portable `dist/wispy/` directory
  with `wispy.exe` + `_internal/`.
- **YAML-based configuration** (`config.yaml` next to `wispy.exe`):
  model, hotkey, language, audio device, beam size, initial prompt,
  clipboard restore.
- **German** as the default language (`language: de`).

[0.4.5]: https://github.com/mka-codelake/wispy/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/mka-codelake/wispy/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/mka-codelake/wispy/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/mka-codelake/wispy/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/mka-codelake/wispy/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/mka-codelake/wispy/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mka-codelake/wispy/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mka-codelake/wispy/releases/tag/v0.2.0
