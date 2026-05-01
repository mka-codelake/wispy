# CLAUDE.md — Architecture Notes for AI Assistants

## Vocabulary / Hotwords

`hotwords.txt` (repo root, next to `config.yaml`) is a plain-text vocabulary file: one term per line, `#` for comments.

At startup `src/wispy/main.py` calls `paths.load_vocabulary()`, joins the terms into a space-separated string, and passes it as the `hotwords` parameter to `Transcriber.__init__()`. `Transcriber` forwards it to `faster-whisper`'s `model.transcribe()` on every call. This is a soft bias — it improves recognition of domain-specific terms but does not guarantee exact spelling.

`initial_prompt` (configured via `config.yaml`) remains an independent, complementary mechanism and is still forwarded unchanged.

## Path resolution

`src/wispy/paths.py::get_app_dir()` is the single source of truth for the app root directory — it handles both `python -m wispy` (source run) and the PyInstaller-frozen `wispy.exe`. All runtime files (`config.yaml`, `hotwords.txt`, `models/`) live relative to this directory.
