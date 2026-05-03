# Changelog

All notable changes to wispy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.3] — 2026-05-03

Hotfix für zwei in v0.4.1/v0.4.2 noch enthaltene Probleme.

### Fixed
- **CUDA-Treiber wurden trotz Installation nicht gefunden.** In v0.2.0
  / v0.3.0 lagen die NVIDIA-DLLs in `<app_dir>/_internal/`, einem
  Verzeichnis, das Windows beim DLL-Loading frozen-PyInstaller-Bundles
  automatisch durchsucht. Mit dem Plugin-Modell ab v0.4.0 liegen sie in
  `<cuda_dir>` (Default `<app_dir>/cuda/`), was nicht im Default-
  Search-Path ist. `os.add_dll_directory()` allein hat nicht gereicht,
  weil CTranslate2 cuBLAS / cuDNN / cudart als transitive Dependencies
  über den Standard-Resolver lädt — der respektiert nur `PATH`. wispy
  prependiert `cuda_dir` jetzt zur Laufzeit an `os.environ["PATH"]`,
  damit alle DLL-Lookups (auch transitive) das Verzeichnis sehen.
  Symptom war: `[transcribe] CUDA load failed: Library cublas64_12.dll
  is not found or cannot be loaded` beim ersten Hotkey-Druck, danach
  CPU-Fallback. Mit dem Fix nutzt wispy auf NVIDIA-Maschinen wie
  vorgesehen die GPU.
- **Modell-Download zeigte keinen Fortschritt.** v0.4.1 hatte
  `HF_HUB_DISABLE_PROGRESS_BARS=1` gesetzt, um eine kosmetische
  `Download complete:`-Zeile loszuwerden, die nach `[wispy] Ready!` auf
  der Konsole landete. Das war zu hart — der User saß fünf Minuten vor
  schwarzem Output. wispy lässt huggingface_hub jetzt wieder seine
  tqdm-Bar zeigen. Die kosmetische Final-Zeile nach `Ready!` ist als
  akzeptabler Trade-off eingeplant.

## [0.4.2] — 2026-05-03

Test-Komfort: lokale Bezugsquellen für CUDA-Bundle und Whisper-Modell.

### Added
- **`cuda_path`** in `config.yaml` — Storage-Choice für die CUDA-Runtime,
  analog zu `model_path`. Default `null` zeigt auf `<wispy>/cuda/`.
  Mehrere wispy-Instanzen können sich denselben CUDA-Bundle-Pfad teilen,
  oder du legst CUDA bewusst außerhalb des wispy-Ordners ab. Der Updater,
  der Lazy-Installer und das Swap-Skript respektieren den konfigurierten
  Pfad gleichermaßen.
- **`model_local_source`** — Pfad zu einem vollständigen lokalen Modell-
  Verzeichnis. Wenn gesetzt, kopiert wispy beim ersten Start die Dateien
  von dort statt sie von Hugging Face zu ziehen. Spart bei Test-Iterationen
  den 1.6-GB-Download.
- **`cuda_local_source`** — Pfad zu einer `wispy-cuda-*.zip`-Datei oder
  einem bereits entpackten CUDA-Verzeichnis. Wenn gesetzt, installiert
  wispy ohne Netzwerk-Zugriff aus dieser Quelle (kein Prompt). Nützlich
  zum Testen von Pre-Release-CUDA-Bundles oder offline.

### Changed
- `cuda_loader` API erweitert: `*_at`-Varianten der Helper akzeptieren
  einen expliziten `cuda_dir`-Pfad (`is_cuda_installed_at`,
  `find_local_cuda_version_at`, `add_cuda_to_dll_search_path_at`,
  `install_cuda_bundle(..., cuda_dir=...)`). Die alten Funktionen mit
  `app_dir`-Parameter bleiben als Wrapper erhalten.
- `updater.check_for_updates` und `updater.trigger_swap` akzeptieren
  einen optionalen `cuda_dir`-Parameter, damit der konfigurierte Pfad
  über den ganzen Update-Pfad hinweg konsistent verwendet wird. Das
  PowerShell-Swap-Skript schreibt das CUDA-Update an den expliziten
  Zielpfad, nicht hartcodiert nach `<app_dir>/cuda`.

## [0.4.1] — 2026-05-03

Hotfix für die in v0.4.0 gefundenen UX- und Stabilitätsprobleme nach dem
ersten Praxistest.

### Fixed
- **`cublas64_12.dll not found` beim ersten Diktat behoben.** v0.4.0
  konnte unter bestimmten Bedingungen den Transcriber mit `device="auto"`
  initialisieren, obwohl gar kein CUDA-Bundle vorhanden war — der Crash
  trat dann erst beim ersten Hotkey-Druck auf. Beim Start wird jetzt
  zwingend geprüft, ob `<app_dir>/cuda/` existiert und Inhalt hat;
  wenn nicht, wird der Transcriber direkt auf `device="cpu"` initialisiert.
- **GPU-Erkennung robuster** — neue dreiwertige Detection
  (`yes` / `no` / `unknown`). Wenn `nvidia-smi` nicht im PATH liegt oder
  ein Timeout auftritt, fragt wispy jetzt trotzdem nach, statt stumm
  auf CPU zu schalten. Vorher konnte eine echte NVIDIA-Karte unentdeckt
  bleiben und der CUDA-Prompt entfiel.
- **Zusätzlicher Runtime-Fallback in `transcribe.py`** — selbst wenn
  CTranslate2 die CUDA-Libraries erst beim Inference lädt und dort
  scheitert, baut wispy das Modell intern auf CPU neu und erledigt das
  Diktat. Kein harter Crash mehr während eines Hotkey-Drucks.

### Changed
- **Kein Self-Restart mehr nach CUDA-Download.** Nach erfolgreicher
  Installation des CUDA-Bundles läuft wispy direkt im selben Prozess
  weiter — der Modell-Download und alles weitere passieren nahtlos
  ohne erneuten Programmstart.
- **Konsole nach `Ready!` aufgeräumt.** Die `Download complete: …`-
  Zeile von `huggingface_hub` taucht jetzt nicht mehr nach dem
  `[wispy] Ready!`-Banner auf. wispy setzt
  `HF_HUB_DISABLE_PROGRESS_BARS=1` und gibt eigene, klare
  Status-Meldungen für den Modell-Download.

## [0.4.0] — 2026-05-03

### Changed
- **Plugin-/Component-Bundle-Architektur** — die Anwendung und die
  CUDA-Runtime werden jetzt als zwei unabhängig versionierte
  Release-Artefakte ausgeliefert: das App-Bundle (`wispy-vX.Y.Z.zip`,
  ~400 MB) und das CUDA-Bundle (`wispy-cuda-vX.Y.Z.zip`, ~1.5 GB). Vorher
  enthielt das App-Bundle die CUDA-DLLs direkt und war ~2 GB groß.
- **Default-Modus auf CPU** — `device: "auto"` ist neuer Default. Auf
  Systemen ohne NVIDIA-Karte läuft wispy direkt auf CPU. Auf Systemen
  mit NVIDIA-Karte fragt wispy beim ersten Start einmalig, ob das
  CUDA-Bundle nachgeladen werden soll.

### Added
- **Lazy-CUDA-Loading** — beim ersten Start mit erkannter NVIDIA-GPU
  bietet wispy in der Konsole an, das passende CUDA-Bundle aus den
  GitHub Releases zu laden. Bei Bestätigung wird das Bundle nach
  `<app_dir>/cuda/` extrahiert; bei Ablehnung läuft wispy auf CPU
  weiter.
- **Dual-Stream Updater** — der Update-Check prüft den App-Stream
  (`vX.Y.Z`) und den CUDA-Stream (`cuda-vX.Y.Z`) unabhängig. Eine
  reine App-Aktualisierung lässt das lokale CUDA-Bundle unangetastet
  und umgekehrt.
- **Drei Konfigurationsstufen für Updates** in `config.yaml`:
  - `update_check: false` — kein Check, kein Prompt.
  - `update_check: true, auto_update: false` — checken und nachfragen
    (neuer Default).
  - `update_check: true, auto_update: true` — silent updaten und neu
    starten.
- **Selbst-Neustart nach Update** — nach einem erfolgreichen Swap
  startet wispy automatisch in der neuen Version, ohne dass die
  Anwendung erneut von Hand gestartet werden muss.
- **Download-Fortschrittsanzeige** — bei App- und CUDA-Downloads zeigt
  wispy fortlaufend Fortschritt, Geschwindigkeit und ETA in der
  Konsole.
- **Robuster CPU-Fallback in `transcribe.py`** — falls CUDA während der
  Modell-Ladephase fehlschlägt, fällt wispy automatisch auf CPU
  (`int8`) zurück und gibt einen klaren Hinweis aus.

### Fixed
- Ein App-Update überschreibt das lokale CUDA-Bundle nicht mehr —
  `cuda/` ist jetzt explizit in der Swap-Whitelist (zusätzlich zu
  `config.yaml`, `models/` und `hotwords.txt`).

### Removed
- **CUDA-DLLs aus dem App-Bundle**. Sie sind ab v0.4.0 nur noch im
  separaten CUDA-Bundle enthalten. Wer von v0.3.0 kommt und auf einer
  NVIDIA-Maschine läuft, wird beim ersten Start mit v0.4.0 einmalig
  gefragt, ob das CUDA-Bundle nachgeladen werden soll.

### Migration

Wer von **v0.3.0** kommt:

- Update läuft normal über den eingebauten Updater (Konsole zeigt
  "App update available: v0.3.0 -> v0.4.0").
- Beim ersten Start nach dem Update fragt wispy nach dem CUDA-Bundle
  (nur auf Maschinen mit NVIDIA-Karte). `[y]` lädt es nach,
  `[n]`/Enter überspringt — wispy läuft dann auf CPU.
- Persönliche `config.yaml` bleibt erhalten. Der frühere Wert
  `device: "cuda"` führt nach dem Update zu einem expliziten
  CUDA-Versuch; falls die Bibliotheken nicht (mehr) vorhanden sind,
  fällt wispy automatisch auf CPU zurück.

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

Erstes öffentliches Release. Vor diesem Punkt war das Repo intern.

### Added
- **Push-to-Talk-Diktat** unter Windows mit globalem Hotkey
  (Default `F9`, konfigurierbar). Hold-Modus (drücken & halten)
  und Toggle-Modus (drücken zum Starten/Stoppen).
- **Lokale Whisper-Transkription** über
  `faster-whisper` + CTranslate2 mit `large-v3-turbo`. CUDA-DLLs
  damals direkt im PyInstaller-Bundle (`_internal/`) gepackt.
- **Whisper-Modell-Erstdownload** beim ersten Start
  (~1.6 GB nach `<wispy>/models/`, danach Offline).
- **Clipboard-Paste-Output** statt Tastatur-Simulation —
  Unicode-sicher und schnell, ursprünglicher Clipboard-Inhalt
  wird optional wiederhergestellt.
- **Auto-Elevation** via UAC: das `keyboard`-Hook braucht
  Admin-Rechte, wispy fordert sie selbst an.
- **PyInstaller-One-Folder-Build** über `build/build.ps1` mit
  `uv` als Python-Manager. Output ist ein portables
  `dist/wispy/`-Verzeichnis mit `wispy.exe` + `_internal/`.
- **YAML-basierte Konfiguration** (`config.yaml` neben
  `wispy.exe`): Modell, Hotkey, Sprache, Audio-Device,
  Beam-Size, Initial-Prompt, Clipboard-Restore.
- **Deutsch** als Default-Sprache (`language: de`).

[0.4.3]: https://github.com/mka-codelake/wispy/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/mka-codelake/wispy/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/mka-codelake/wispy/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/mka-codelake/wispy/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mka-codelake/wispy/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mka-codelake/wispy/releases/tag/v0.2.0
