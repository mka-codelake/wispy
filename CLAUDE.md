# wispy -- Lokales Offline-Diktier-Tool

## Was ist wispy?

Minimalistisches Push-to-Talk Diktiertool fuer Windows. Nutzer drueckt Hotkey, spricht, laesst los -- Text erscheint dort, wo der Cursor ist (Notepad, Browser, VS Code, egal wo). Komplett lokal, kein Cloud-Dienst.

## Technischer Stack

- **STT**: `faster-whisper` (CTranslate2/CUDA) mit Whisper Large V3 Turbo
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

Erster Start laedt Whisper-Modell herunter (~1.6 GB nach `<repo-root>/models/large-v3-turbo/`), danach gecached.
`keyboard`-Library braucht Admin-Rechte -- `main.py::_elevate_and_exit()` triggert UAC automatisch, re-launcht `python -m wispy <args>` (Source-Run) bzw. `wispy.exe <args>` (Frozen) mit "runas".

## Release

Kanonische Version lebt in `pyproject.toml`; `__version__` wird via `importlib.metadata` daraus abgeleitet. Release-Ablauf siehe `CONTRIBUTING.md` (Bump → Tag → `build.ps1 -CreateZip` → `gh release create`).

## Umsetzungsstatus

- [x] Projektstruktur (src-Layout, pyproject.toml, .gitignore)
- [x] config.py -- Config-Dataclass + YAML-Loader
- [x] config.yaml -- Standardwerte
- [x] audio.py -- Recorder-Klasse
- [x] transcribe.py -- Transcriber-Klasse
- [x] hotkey.py -- HotkeyListener
- [x] output.py -- Clipboard-Paste
- [x] feedback.py -- Beep-Sounds
- [x] paths.py + model_fetch.py -- app-dir + First-run-Download
- [x] main.py -- Main-Loop, alles zusammengesteckt
- [x] Portable-Build via build/build.ps1 + build/wispy.spec

## Verifikation

| Test | Erwartung |
|------|-----------|
| F9 halten, "Hallo Welt" sagen, loslassen | Text erscheint im Notepad |
| Toggle: F9, sprechen, F9 | Transkription erscheint |
| < 0.3s druecken und loslassen | "(too short, skipped)" in Konsole |
| Clipboard hatte vorher Inhalt | Nach Diktieren alter Inhalt zurueck |
