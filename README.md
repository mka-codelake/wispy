<img src="./etc/logo.svg" width="400" align="right" alt="wispy"/>

# wispy

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

> [!NOTE]
> **wispy** ist in Beta. Konfigurationsformat und Kommandozeilenoptionen koennen sich zwischen Minor-Versionen aendern.

Minimalistisches Push-to-Talk Diktiertool fuer Windows. Hotkey druecken, sprechen, loslassen -- der Text erscheint dort, wo der Cursor ist (Notepad, Browser, VS Code, egal wo). Komplett lokal, keine Cloud, kein Abo.

- **Backend:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2/CUDA), Modell `large-v3-turbo`
- **Sprache:** Deutsch (per Config aenderbar)
- **Footprint:** ~250 LOC, 6 direkte Dependencies, kein GUI

## Ueberblick

wispy loest ein konkretes Problem: Spracheingabe ohne Cloud-Abhaengigkeit, ohne Datenschutzbedenken und ohne Latenzen durch Netzwerkrundtrips. Wer viel diktiert und eine NVIDIA-GPU hat, bekommt mit wispy eine Offline-Loesung, die schneller und praeziser transkribiert als die meisten Online-Dienste -- und die keine einzige Silbe das lokale Netzwerk verlaesst.

wispy ist als persoenliches Produktivitaetstool konzipiert. Es gibt keine GUI, keine Tray-App, keine Cloud-Anbindung. Es laeuft als Konsolen-Prozess im Hintergrund und wartet auf einen Hotkey.

**Fuer wen?** Windows-Nutzer mit NVIDIA-GPU, die offline und ohne Abo-Kosten diktieren wollen -- in jeder Anwendung, die Tastatureingaben akzeptiert.

## Features

- **Push-to-Talk oder Toggle** -- Aufnahme per Hotkey starten und beenden, frei konfigurierbar (`hold` oder `toggle`-Modus)
- **Voellig offline** -- Transkription laeuft vollstaendig lokal via `faster-whisper` (CTranslate2/CUDA), kein Netzwerkzugriff nach dem ersten Modell-Download
- **Funktioniert ueberall** -- Textausgabe per Clipboard-Paste (Ctrl+V-Simulation), kompatibel mit jeder Windows-Anwendung inkl. Umlauten und Sonderzeichen
- **Clipboard-Schutz** -- Vorheriger Clipboard-Inhalt wird nach dem Einfuegen automatisch wiederhergestellt
- **Mehrsprachig** -- Sprache per ISO-Code in `config.yaml` einstellbar (`de`, `en`, `fr`, ...)
- **Akustisches Feedback** -- Beep-Toene signalisieren Aufnahmestart (800 Hz) und -ende (400 Hz) ohne Bildschirmablenkung
- **Portabler Build** -- PyInstaller-Bundle (`build/build.ps1`) erzeugt ein selbsttragendes `dist/wispy/`-Verzeichnis inkl. CUDA-DLLs; kein Python auf dem Zielrechner noetig
- **Flexibler Modell-Pfad** -- Modell liegt per Default neben dem Quellcode in `models/`; ueber `model_path` in `config.yaml` frei konfigurierbar

---

## Voraussetzungen

| | |
|---|---|
| **Betriebssystem** | Windows 10/11 **nativ** -- nicht WSL2 (wegen Mikrofon, Hotkey, Tastatur-Simulation) |
| **Python** | 3.10, 3.11 oder 3.12 |
| **GPU** | NVIDIA-GPU mit ~3 GB freiem VRAM (fuer `large-v3-turbo` + `float16`) |
| **CUDA Toolkit** | **Version 12.x -- NICHT 13.x.** `faster-whisper` nutzt `CTranslate2`, und das unterstuetzt aktuell ausschliesslich CUDA 12 (mit cuDNN 9 -> CUDA >= 12.3). Empfohlen: **CUDA 12.9.1** (letzte 12er-Reihe, Juni 2025) oder 12.6/12.8. Manuell installieren -- enthaelt `cudart`, `cuBLAS` und `cuDNN`, die `faster-whisper` zur Laufzeit braucht. **Direkt-Download (Windows x86_64):** [cuda_12.9.1_576.57_windows.exe](https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_576.57_windows.exe) (~3.56 GB) bzw. die Archiv-Seite [developer.nvidia.com/cuda-12-9-1-download-archive](https://developer.nvidia.com/cuda-12-9-1-download-archive). Eine Auswahl aller 12.x-Versionen findest du im [CUDA Toolkit Archive](https://developer.nvidia.com/cuda-toolkit-archive). |
| **Admin-Rechte** | Beim Start empfohlen -- die `keyboard`-Library haengt sich global in den Tastatur-Hook ein und braucht das auf den meisten Windows-Systemen |
| **Mikrofon** | Datenschutz-Einstellungen pruefen: *Einstellungen -> Datenschutz -> Mikrofon -> Desktop-Apps zulassen* |
| **Speicherplatz** | ~4 GB (Modell ~1.5 GB + venv + Dependencies) |

---

## Setup

```powershell
# 1. Repo holen
cd C:\pfad\zu\wispy

# 2. venv anlegen und aktivieren
python -m venv .venv
.\.venv\Scripts\activate

# 3. wispy als editable Package installieren (zieht alle Dependencies aus pyproject.toml)
pip install -e .

# 4. Erster Start (laedt beim ersten Lauf das Modell ~1.6 GB)
python -m wispy
```

> Beim **ersten** Start laedt `src/wispy/model_fetch.py` das Modell `large-v3-turbo` (~1.6 GB) via `huggingface_hub.snapshot_download` direkt in `<repo-root>\models\large-v3-turbo\`. Kein HuggingFace-Cache im User-Profile -- das Modell liegt neben dem Quellcode und wandert bei einem Verschieben des Ordners mit. Der Zielpfad wird von `src/wispy/paths.py::resolve_model_path` bestimmt; via `model_path` in `config.yaml` laesst sich ein eigener Ordner setzen.

---

## Portable Build (optional)

Wer kein Python-Setup auf dem Zielrechner will, kann wispy als portablen One-Folder-Bundle bauen. Das Skript `build/build.ps1` ruft PyInstaller mit `build/wispy.spec` auf und produziert `dist/wispy/` mit `wispy.exe` plus einem `_internal/`-Ordner.

```powershell
# Im Repo-Root, in einer PowerShell:
.\build\build.ps1
```

Der fertige `dist/wispy/`-Ordner ist selbst-tragend:

- **Kein CUDA Toolkit** auf dem Zielrechner noetig -- der Bundle bringt `cudart64_12.dll`, `cublas64_12.dll` und `cudnn_*.dll` in `_internal/` mit. Nur ein aktueller NVIDIA-Treiber wird gebraucht (fuer `nvcuda.dll` und das Kernel-Modul, die systemweit kommen muessen).
- **Kein Installer.** Ordner kopieren, `wispy.exe` starten, fertig.
- **Portable.** Ordner laesst sich auf USB-Stick / anderen Rechner verschieben; das bereits heruntergeladene Modell wandert in `models/` mit.

Die End-Nutzer-Doku fuer den Bundle liegt in `build/README.txt` und wird von PyInstaller nach `dist/wispy/README.txt` kopiert.

---

## Steuerung

**Standard-Modus: Hold (Push-to-Talk)**

| Aktion | Tastendruck |
|---|---|
| Aufnahme starten | **F9 gedrueckt halten** -> Beep 800 Hz |
| Aufnahme beenden + transkribieren | F9 loslassen -> Beep 400 Hz -> Text wird am Cursor eingefuegt |
| Aufnahme verworfen | < 0.3 s losgelassen -> `(too short, skipped)` in Konsole |
| wispy beenden | **Ctrl+C** im Konsolen-Fenster |

**Toggle-Modus** (in `config.yaml` setzen: `record_mode: toggle`)

| Aktion | Tastendruck |
|---|---|
| Aufnahme starten | F9 einmal druecken |
| Aufnahme beenden + transkribieren | F9 erneut druecken |

Text wird via Clipboard + simuliertes Ctrl+V eingefuegt -- funktioniert in jeder Anwendung, auch mit Umlauten und Sonderzeichen. Der vorherige Clipboard-Inhalt wird nach dem Einfuegen wiederhergestellt (deaktivierbar via `restore_clipboard: false`).

---

## Konfiguration

Alle Einstellungen liegen in `config.yaml`. Die wichtigsten:

```yaml
hotkey: "F9"              # Beliebige Taste -- "F9", "F12", "ctrl+space", ...
record_mode: "hold"       # "hold" oder "toggle"
language: "de"            # ISO-Code -- "de", "en", "fr", ...
model_name: "large-v3-turbo"   # Auch: "small", "medium", "large-v3"
device: "cuda"            # "cuda" oder "cpu"
compute_type: "float16"   # "float16" (GPU) / "int8" (CPU)
audio_device: null        # null = Standard-Mikrofon, sonst Index
restore_clipboard: true   # Alten Clipboard-Inhalt nach dem Einfuegen zuruecksetzen
```

Eine eigene Config laden:

```powershell
python -m wispy --config C:\pfad\zu\meine-config.yaml
```

---

## Projektstruktur

```
wispy/
├── src/wispy/
│   ├── __init__.py       # Package-Marker, __version__
│   ├── __main__.py       # Einstiegspunkt fuer `python -m wispy`
│   ├── main.py           # Haupt-Loop, Orchestrierung, UAC-Elevation
│   ├── audio.py          # Mikrofon-Aufnahme (sounddevice/PortAudio)
│   ├── transcribe.py     # Whisper-Modell laden und transkribieren
│   ├── hotkey.py         # Globaler Hotkey-Listener (hold + toggle)
│   ├── output.py         # Textausgabe via Clipboard-Paste
│   ├── feedback.py       # Beep-Sounds (winsound)
│   ├── config.py         # Config-Dataclass + YAML-Loader
│   ├── paths.py          # Modell-Pfad-Aufloesung (src-aware + frozen)
│   └── model_fetch.py    # Erster-Start-Download via HuggingFace Hub
├── build/
│   ├── build.ps1         # Portable-Build-Skript (uv + PyInstaller)
│   ├── wispy.spec        # PyInstaller-Spec
│   └── README.txt        # End-Nutzer-Doku fuer den Bundle
├── etc/
│   └── logo.svg          # Projekt-Logo
├── config.yaml           # Standard-Konfiguration
└── pyproject.toml        # Package-Metadaten und Dependencies
```

Interne Imports sind relative Imports (`from .audio import Recorder`). Ausnahme: `__main__.py` nutzt einen absoluten Import, damit PyInstaller das Entry-Script korrekt als Top-Level laden kann.

---

## Mitwirken

Beitraege sind willkommen. Bitte lies zuerst [CONTRIBUTING.md](CONTRIBUTING.md) fuer Hinweise zu Branching, Commit-Konventionen und dem Pull-Request-Prozess.

---

## Bekannte Stolperfallen

| Symptom | Ursache | Loesung |
|---|---|---|
| `Could not load library cudnn_*.dll` / `cublas64_*.dll` | CUDA Toolkit fehlt, ist **Version 13.x** (inkompatibel mit CTranslate2) oder nicht im PATH | CUDA Toolkit **12.x** installieren (empfohlen: 12.9.1), danach Konsole neu starten |
| Hotkey reagiert nicht auf F9 | Konsole nicht als Admin gestartet | wispy in Admin-PowerShell starten |
| `Failed to query device 0` / kein Audio | Kein Mikrofon erkannt oder Berechtigung fehlt | Windows-Datenschutz-Einstellungen pruefen, anderes `audio_device` in Config probieren |
| `(too short, skipped)` bei jedem Druck | Hotkey wird zu kurz gehalten (< 0.3 s) | Laenger halten oder `MIN_DURATION_SEC` in `src/wispy/main.py` reduzieren |
| Erste Transkription dauert sehr lange | Modell wird heruntergeladen (~1.5 GB) | Einmaliger Vorgang, danach gecached |
| Transkription falsch oder leer | Falsche Sprache, schlechtes Mikrofon-Signal, zu leise gesprochen | `language` in Config pruefen, naeher ans Mikrofon |

---

## Lizenz

Copyright 2026 Michael Kagel

wispy ist freie Software und steht unter der **GNU General Public License v3.0 oder (nach deiner Wahl) einer spaeteren Version**. Siehe [LICENSE](LICENSE) fuer den vollstaendigen Lizenztext.

wispy wird in der Hoffnung verteilt, dass es nuetzlich ist, aber **ohne jegliche Gewaehrleistung**; auch ohne die implizite Gewaehrleistung der MARKTGAENGIGKEIT oder EIGNUNG FUER EINEN BESTIMMTEN ZWECK.

Beitraege stehen ebenfalls unter der GPL v3 -- Details in [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Persoenliches Tool, Work in Progress.
