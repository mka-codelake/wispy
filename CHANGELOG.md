# Changelog

All notable changes to wispy will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.3.0]: https://github.com/mka-codelake/wispy/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mka-codelake/wispy/releases/tag/v0.2.0
