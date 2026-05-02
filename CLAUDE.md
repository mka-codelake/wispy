# wispy -- Lokales Offline-Diktier-Tool

## Was ist wispy?

Minimalistisches Push-to-Talk Diktiertool fuer Windows. Nutzer drueckt Hotkey, spricht, laesst los -- Text erscheint dort, wo der Cursor ist (Notepad, Browser, VS Code, egal wo). Komplett lokal, kein Cloud-Dienst.

## Technischer Stack

- **STT**: `faster-whisper` (CTranslate2) mit Whisper Large V3 Turbo. CUDA optional via Lazy-Loading; CPU-Default lauffaehig auch ohne NVIDIA-Hardware.
- **Audio**: `sounddevice` (PortAudio), 16kHz mono
- **Hotkey**: `keyboard` Library, systemweit
- **Text-Ausgabe**: `pyperclip` + `keyboard` (Clipboard-Paste via Ctrl+V)
- **Feedback**: `winsound` (Beep bei Start/Stop)
- **Config**: `PyYAML` + dataclass

## Architektur

- Threading (kein asyncio) -- Hotkey-Hook, PortAudio-Callback und GPU-Transkription sind blockierend
- Clipboard-Paste statt Tastatur-Simulation -- schnell, Unicode-sicher, ueberall
- Kein GUI (v1) -- Konsolen-Output reicht
- Kein eigener VAD -- Push-to-Talk reicht; faster-whisper hat Silero-VAD
- **Muss nativ unter Windows laufen** (nicht WSL2) -- wegen Mikrofon, Hotkeys, Tastatur-Simulation
- **Update-Mechanismus** (`updater.py`): Beim Start prueft wispy zwei Asset-Streams unabhaengig -- App-Bundle (Tag `vX.Y.Z`) und CUDA-Bundle (Tag `cuda-vX.Y.Z`). Drei Config-Stufen: `update_check: false` (kein Check), `update_check: true, auto_update: false` (Default -- checken + prompten + selbst-Restart), `update_check: true, auto_update: true` (silent). Bei Update wird das passende Asset gezogen, Swap durchgefuehrt, wispy neu gestartet -- alles in einem Lauf, ohne dass der User ein zweites Mal klickt. **Whitelist** beim Swap: `config.yaml`, `models/`, `hotwords.txt`, `cuda/`. Nur im frozen Build aktiv.

### Bundle-Architektur -- Plugin-/Component-Modell

Zwei unabhaengig versionierte Artefakte auf GitHub Releases:

- **App-Bundle** (~400 MB): App-Code + Python-Runtime + non-CUDA libs. Tag-Schema `vX.Y.Z`, Sanity-Check gegen `pyproject.toml` im CI. Asset-Name `wispy-vX.Y.Z.zip`.
- **CUDA-Bundle** (~1.5 GB): nur die CUDA-DLLs aus den `nvidia-*`-pip-Paketen. Tag-Schema `cuda-vX.Y.Z` (Mirror der CUDA-Toolkit-Version, optional Build-Counter `cuda-vX.Y.Z-bN`). Asset-Name `wispy-cuda-vX.Y.Z.zip`.

Lokales Layout:

```
app_dir/
  wispy.exe
  _internal/        # Python + non-CUDA libs (immer)
  cuda/             # optional, lazy nachgeladen
    cublas64_12.dll
    cudnn_*.dll
    cudart64_12.dll
    _version.txt    # vom CI geschrieben
  config.yaml
  models/
```

**Lazy-CUDA-Loading-Flow**: Beim Start prueft wispy, ob eine NVIDIA-GPU vorhanden ist (via `nvidia-smi` / WMI / Registry). Wenn ja UND `cuda/` fehlt -> Konsolen-Prompt "CUDA-Treiber nachladen? [y/n]". Bei `y` wird das CUDA-Bundle nach `cuda/` geladen. Bei `n` oder keiner GPU -> CPU-Modus (`device: "auto"` ist konfiguriert). CTranslate2 findet die DLLs ueber `os.add_dll_directory(app_dir / "cuda")` vor dem `WhisperModel()`-Aufruf. Bei CUDA-Fehler zur Laufzeit -> Fallback CPU mit Konsolen-Hinweis.

## Projektstruktur

Standard-Python src-Layout (PyPA-Empfehlung), Start via `python -m wispy`.

```
src/wispy/
  __init__.py       # Package-Marker, __version__
  __main__.py       # Entry fuer `python -m wispy` (absoluter Import zu wispy.main)
  main.py           # Main-Loop, Orchestrierung, Admin-Elevation
  audio.py          # Mikrofon-Aufnahme (sounddevice)
  transcribe.py     # Whisper-Modell laden + transkribieren
  hotkey.py         # Globaler Hotkey, Hold + Toggle Modus
  output.py         # Text einfuegen via Clipboard-Paste
  feedback.py       # Beep-Sounds (winsound)
  config.py         # Config-Laden (YAML -> dataclass)
  paths.py          # app_dir / Modell-Pfad-Aufloesung (src-aware + frozen-aware)
  model_fetch.py    # First-run HuggingFace-Snapshot-Download
  gpu_detect.py     # NVIDIA-GPU-Detection beim Start (nvidia-smi / WMI / Registry)
  cuda_loader.py    # Lazy-Download des CUDA-Bundles + os.add_dll_directory
  updater.py        # Update-Mechanismus: dual-stream Check, Asset-Auswahl, Self-Restart-Swap

pyproject.toml      # Package-Metadaten + Dependencies (setuptools-Backend)
config.yaml         # Standard-Konfiguration im Repo-Root
build/wispy.spec    # PyInstaller-Spec (Entry: src/wispy/__main__.py)
build/build.ps1     # Portable-Build via uv + PyInstaller
```

Interne Imports sind **relative** Imports (`from .audio import Recorder`) -- Ausnahme: `__main__.py` nutzt einen **absoluten** Import (`from wispy.main import main`), damit PyInstaller das Entry-Script als Top-Level laden kann.

## Datenfluss

```
[Hotkey gedrueckt] -> Beep(800Hz) -> Recorder.start()
[Nutzer spricht]   -> PortAudio-Callback fuellt Chunk-Liste
[Hotkey losgelassen] -> Recorder.stop() -> Beep(400Hz) -> audio_queue.put(audio)
Transcription-Worker: audio -> faster-whisper.transcribe() -> output.type_text()
output.type_text: Clipboard sichern -> Text -> Clipboard -> Ctrl+V -> Clipboard restore
```

## Ausfuehrung

```powershell
# Unter Windows (nicht WSL2!):
pip install -e .
python -m wispy
```

Erster Start mit NVIDIA-GPU: optionaler Konsolen-Prompt zum CUDA-Bundle-Download (~1.5 GB nach `<app_dir>/cuda/`). Bei `n` oder keiner GPU laeuft wispy auf CPU.

Erster Start laedt Whisper-Modell herunter (~1.6 GB nach `<repo-root>/models/large-v3-turbo/`), danach gecached.
`keyboard`-Library braucht Admin-Rechte -- `main.py::_elevate_and_exit()` triggert UAC automatisch, re-launcht `python -m wispy <args>` (Source-Run) bzw. `wispy.exe <args>` (Frozen) mit "runas".

## Release

Kanonische App-Version lebt in `pyproject.toml`; `__version__` wird via `importlib.metadata` daraus abgeleitet.

**App-Release** (Tag `vX.Y.Z`): Version in `pyproject.toml` bumpen -> committen -> `git tag vX.Y.Z && git push origin main --tags`. Workflow `.github/workflows/release.yml` baut `wispy-vX.Y.Z.zip` (App-Code, kein CUDA) auf `windows-latest` und published.

**CUDA-Release** (Tag `cuda-vX.Y.Z`): manueller Tag-Push, z.B. `git tag cuda-v12.9.1 && git push origin cuda-v12.9.1`. Workflow `.github/workflows/release-cuda.yml` (siehe Phase 1 der lokalen Implementation) installiert `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` + `nvidia-cuda-runtime-cu12` via uv, packt die DLLs samt `_version.txt` in `wispy-cuda-vX.Y.Z.zip` und published als separater Release.

CUDA-Releases sind selten (gekoppelt an CUDA-Toolkit-Bumps). App-Releases laufen frei davon. Updater im Tool prueft beide Streams unabhaengig.

**Manueller Fallback fuer App**: `build.ps1 -CreateZip` -> `gh release create` (Details in `CONTRIBUTING.md`).

## Umsetzungsstatus

- [x] Projektstruktur (src-Layout, pyproject.toml, .gitignore)
- [x] config.py / config.yaml / audio.py / transcribe.py / hotkey.py / output.py / feedback.py / paths.py / model_fetch.py / main.py -- v1-Stand
- [x] Portable-Build via build/build.ps1 + build/wispy.spec (monolithisch, wird auf Plugin-Modell umgestellt)
- [x] Update-Mechanismus v1 (`updater.py`, monolithisch)
- [ ] **Plugin-Modell -- App-Bundle ohne CUDA** (in Arbeit, Phase 1)
- [ ] **CUDA-Bundle als separates Release-Artefakt** (Phase 1)
- [ ] **`gpu_detect.py` + `cuda_loader.py` -- Lazy-CUDA-Loading** (Phase 2)
- [ ] **Updater dual-stream + selbst-Restart** (Phase 3)
- [ ] **UI/UX-Polishing** (Phase 4 -- Progress-Anzeige, harmonisierte Konsolen-Logs)

## Verifikation

| Test | Erwartung |
|------|-----------|
| F9 halten, "Hallo Welt" sagen, loslassen | Text erscheint im Notepad |
| Toggle: F9, sprechen, F9 | Transkription erscheint |
| < 0.3s druecken und loslassen | "(too short, skipped)" in Konsole |
| Clipboard hatte vorher Inhalt | Nach Diktieren alter Inhalt zurueck |

## Issue-Label-Konventionen

- `do-not-automate` -- Bot-Hands-off, Issue wird bei `@claude`-Triggern nicht aufgegriffen.
- `parked` -- bewusst zurueckgestellt, spaeter re-evaluieren. Wird in der Regel mit `do-not-automate` kombiniert. Begruendung gehoert als Comment ans Issue (Datum + Warum).
  - **Re-Aktivierung**: beide Labels entfernen.
  - **Endgueltige Ablehnung**: Issue schliessen mit Reason `not planned`, Label `wontfix` setzen.
- Workflow-Detail-Regeln fuer Bot-Verhalten: siehe `.github/AGENT_BRIEFING.md`.
