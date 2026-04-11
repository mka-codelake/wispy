wispy -- portable push-to-talk dictation for Windows
=====================================================

Voraussetzungen
---------------
  * Windows 10 oder 11 (x64)
  * NVIDIA-GPU mit aktuellem Grafiktreiber
      Check: In einer PowerShell "nvidia-smi" eingeben. Wenn ein Tableau
      mit deiner GPU erscheint, ist der Treiber da. Sonst den aktuellen
      GeForce- oder Studio-Treiber von
          https://www.nvidia.com/Download/index.aspx
      installieren.
  * Mikrofon-Berechtigung fuer Desktop-Apps
      Einstellungen -> Datenschutz -> Mikrofon -> Desktop-Apps zulassen
  * ca. 4 GB freier Festplattenplatz
  * Beim allerersten Start einmalig Internet
      (~1.6 GB Whisper-Modell-Download)

Installation
------------
  1. ZIP in einen beliebigen Ordner auspacken, z.B.
         C:\Tools\wispy
     Kein Installer noetig. Kein Eintrag in der Registry.
  2. Optional config.yaml oeffnen und Einstellungen anpassen
     (Hotkey, Sprache, ...).
  3. Doppelklick auf wispy.exe
  4. Beim ersten Start:
       - UAC-Prompt bestaetigen (fuer den globalen Hotkey-Hook)
       - wispy laedt einmalig das Whisper-Modell (~1.6 GB) nach
             <wispy-ordner>\models\large-v3-turbo\
       - Danach meldet wispy "Model ready." und ist einsatzbereit.

Bedienung
---------
  * Hotkey HALTEN (Standard: F9) -> Beep 800 Hz -> jetzt sprechen
  * Hotkey LOSLASSEN              -> Beep 400 Hz -> Text erscheint am
                                      aktuellen Cursor (via Clipboard-Paste)
  * Zu kurz gedrueckt (< 0.3 s)   -> wird ignoriert
  * wispy beenden                 -> Strg+C in der Konsole oder Fenster
                                      schliessen

Konfiguration
-------------
Alle Einstellungen liegen in config.yaml direkt neben wispy.exe:

  hotkey          F9, F12, "ctrl+space", ... beliebige Taste
  record_mode     "hold" (halten) oder "toggle" (einmal druecken)
  language        "de", "en", "fr", ...
  model_name      "large-v3-turbo" (Standard)
  model_path      null = Default <wispy>\models\<model_name>
                  oder absoluter Pfad zu einem eigenen Modell-Ordner
  device          "cuda" (v1: nur GPU)
  compute_type    "float16"

Nach Aenderungen an config.yaml wispy neu starten.

Verschieben / Kopieren / USB-Stick
----------------------------------
Der gesamte wispy-Ordner ist portable. Du kannst ihn:
  * an einen anderen Pfad verschieben
  * auf einen USB-Stick kopieren
  * an einem anderen Windows-Rechner mit NVIDIA-GPU auspacken
und wispy laeuft dort sofort weiter. Das bereits heruntergeladene
Modell wandert im Ordner mit, ein erneuter Download findet nicht statt.

Deinstallation
--------------
Den wispy-Ordner einfach loeschen. Fertig. wispy schreibt nichts in
die Registry und legt keine Dateien ausserhalb seines eigenen Ordners
ab.

Bei Problemen
-------------
wispy gibt bei jedem Start aus, welche Pfade es effektiv verwendet:
    [wispy] app_dir    = ...
    [wispy] config     = ...
    [wispy] model_path = ...
Fehler (fehlendes Modell, CUDA-Probleme, ...) werden mit klaren
Hinweisen auf der Konsole gemeldet. Die Konsole bitte offen lassen,
bevor du ein Problem meldest.

GPU / CUDA-Details
------------------
wispy bringt seinen eigenen CUDA-Runtime-Stack im Ordner _internal\
mit (cublas64_12.dll, cudnn_*.dll, cudart64_12.dll). Du brauchst
KEIN systemweit installiertes CUDA Toolkit. Nur der NVIDIA-Treiber
muss vorhanden sein, weil er das Kernel-Modul und nvcuda.dll liefert,
die nicht aus einem Anwendungsordner geladen werden koennen.
