wispy -- portable push-to-talk dictation for Windows
=====================================================

Requirements
------------
  * Windows 10 or 11 (x64)
  * NVIDIA GPU is optional; without one wispy runs on CPU.
      Check: open PowerShell and run "nvidia-smi". If it lists your GPU,
      the driver is in place. If you have a NVIDIA card without a driver,
      install a current GeForce or Studio driver from
          https://www.nvidia.com/Download/index.aspx
      first. wispy itself fetches the matching CUDA runtime DLLs on demand
      at first start (no system-wide CUDA toolkit needed).
  * Microphone permission for desktop apps
      Settings -> Privacy -> Microphone -> Allow desktop apps
  * ~4 GB free disk space
  * Internet connection at first start
      (one-time ~1.6 GB Whisper model download, plus optional ~1.5 GB
       CUDA bundle on NVIDIA machines)

Installation
------------
  1. Extract the ZIP into any folder, e.g.
         C:\Tools\wispy
     No installer needed. Nothing is written to the registry.
  2. Optionally open config.yaml and adjust settings
     (hotkey, language, ...).
  3. Double-click wispy.exe
  4. At the first start:
       - Confirm the UAC prompt (needed for the global hotkey hook).
       - On a NVIDIA machine wispy asks once whether to download the
         CUDA runtime (~1.5 GB into <wispy-folder>\cuda\).
         Decline -> wispy runs on CPU.
       - wispy then fetches the Whisper model (~1.6 GB into
         <wispy-folder>\models\large-v3-turbo\).
       - After "Model ready." wispy is ready to dictate.

Usage
-----
  * HOLD the hotkey (default: F9) -> beep 800 Hz -> speak now
  * RELEASE the hotkey            -> beep 400 Hz -> text appears at
                                       the current cursor via clipboard
                                       paste
  * Press < 0.3 s                 -> ignored
  * Quit wispy                    -> Ctrl+C in the console, or close
                                       the window

Configuration
-------------
All settings live in config.yaml right next to wispy.exe:

  hotkey          F9, F12, "ctrl+space", ... any key combo
  record_mode     "hold" (push-to-talk) or "toggle" (press to start,
                  press again to stop)
  language        "de", "en", "fr", ... ISO 639-1 code
  model_name      "large-v3-turbo" (default)
  model_path      null = use the default <wispy>\models\<model_name>
                  or an absolute path to a custom model folder
  cuda_path       null = use the default <wispy>\cuda
                  or an absolute path to a shared CUDA folder
  device          "auto" (default), "cuda" or "cpu"
  compute_type    "default" (best precision per device), "float16",
                  "int8_float16", "int8"
  update_check    true / false  (look for new versions on startup)
  auto_update     false (default, ask before applying) / true (silent)

After changes to config.yaml, restart wispy.

Move / copy / USB stick
-----------------------
The whole wispy folder is portable. You can:
  * move it to another path,
  * copy it to a USB stick,
  * extract it on another Windows machine.
wispy continues to run there. The already downloaded model and CUDA
bundle move with the folder; no re-download happens.

Uninstallation
--------------
Delete the wispy folder. Done. wispy writes nothing to the registry
and never creates files outside its own folder.

Updates
-------
wispy checks for updates on startup against this repository's GitHub
Releases. Three configuration tiers control the behaviour:

  update_check: false                       no check, no prompt
  update_check: true, auto_update: false    check + ask "[y/N]"  (default)
  update_check: true, auto_update: true     check + apply silently + restart

Updates run as next-boot swaps:
  1. wispy downloads the new app bundle (and the CUDA bundle if a newer
     one is available).
  2. wispy exits, a small PowerShell helper swaps the files,
     wispy restarts itself in the new version.
  3. Your config.yaml, models/, hotwords.txt and cuda/ are protected by
     a hard whitelist and are never overwritten.

If problems occur
-----------------
wispy prints the effective paths it uses on every startup:
    [wispy] app_dir    = ...
    [wispy] config     = ...
    [wispy] model_path = ...
Errors (missing model, CUDA problems, ...) are reported with clear
hints on the console. Please leave the console open before reporting
an issue.

GPU / CUDA details
------------------
wispy ships without CUDA libraries by default. On a NVIDIA machine the
matching cuBLAS / cuDNN / cudart DLLs are downloaded on demand at first
start into <wispy-folder>\cuda\. You do NOT need a system-wide CUDA
toolkit. Only the NVIDIA driver itself must be present, because it
provides the kernel module and nvcuda.dll, which cannot be loaded from
an application folder.
