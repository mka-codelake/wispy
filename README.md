# wispy

Minimalistisches Push-to-Talk Diktiertool fuer Windows. Hotkey druecken, sprechen, loslassen -- der Text erscheint dort, wo der Cursor ist (Notepad, Browser, VS Code, egal wo). Komplett lokal, keine Cloud, kein Abo.

- **Backend:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2/CUDA), Modell `large-v3-turbo`
- **Sprache:** Deutsch (per Config aenderbar)
- **Footprint:** ~250 LOC, 6 direkte Dependencies, kein GUI

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

# 3. Dependencies installieren
pip install -r requirements.txt

# 4. Erster Start (laedt beim ersten Lauf das Modell ~1.5 GB)
python wispy.py
```

> Beim **ersten** Start laedt `model_fetch.py` das Modell `large-v3-turbo` (~1.6 GB) via `huggingface_hub.snapshot_download` direkt in `<repo-root>\models\large-v3-turbo\`. Kein HuggingFace-Cache im User-Profile -- das Modell liegt neben dem Quellcode und wandert bei einem Verschieben des Ordners mit. Der Zielpfad wird von `paths.py::resolve_model_path` bestimmt; via `model_path` in `config.yaml` laesst sich ein eigener Ordner setzen.

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
python wispy.py --config C:\pfad\zu\meine-config.yaml
```

---

## Bekannte Stolperfallen

| Symptom | Ursache | Loesung |
|---|---|---|
| `Could not load library cudnn_*.dll` / `cublas64_*.dll` | CUDA Toolkit fehlt, ist **Version 13.x** (inkompatibel mit CTranslate2) oder nicht im PATH | CUDA Toolkit **12.x** installieren (empfohlen: 12.9.1), danach Konsole neu starten |
| Hotkey reagiert nicht auf F9 | Konsole nicht als Admin gestartet | wispy in Admin-PowerShell starten |
| `Failed to query device 0` / kein Audio | Kein Mikrofon erkannt oder Berechtigung fehlt | Windows-Datenschutz-Einstellungen pruefen, anderes `audio_device` in Config probieren |
| `(too short, skipped)` bei jedem Druck | Hotkey wird zu kurz gehalten (< 0.3 s) | Laenger halten oder `MIN_DURATION_SEC` in `wispy.py` reduzieren |
| Erste Transkription dauert sehr lange | Modell wird heruntergeladen (~1.5 GB) | Einmaliger Vorgang, danach gecached |
| Transkription falsch oder leer | Falsche Sprache, schlechtes Mikrofon-Signal, zu leise gesprochen | `language` in Config pruefen, naeher ans Mikrofon |

---

## Lizenz / Status

Persoenliches Tool, Work in Progress.
