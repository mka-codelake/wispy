# Contributing to wispy

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## How to Contribute

### Reporting Bugs

1. Check existing [issues](https://github.com/mka-codelake/wispy/issues) to avoid duplicates
2. Use the bug report template when creating a new issue
3. Include steps to reproduce, expected behavior, and actual behavior

### Suggesting Features

1. Check existing [issues](https://github.com/mka-codelake/wispy/issues) for similar requests
2. Use the feature request template
3. Describe the use case and expected behavior

### Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Write or update tests as needed
5. Ensure all tests pass
6. Commit with clear, descriptive messages
7. Push to your fork and open a Pull Request

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `refactor:` — Code restructuring without behavior change
- `test:` — Adding or updating tests
- `chore:` — Maintenance tasks

### Code Style

- Follow existing code patterns and conventions
- Keep changes focused and minimal
- Add tests for new functionality

## Release Process

The canonical version lives **exclusively** in `pyproject.toml` (`version = "X.Y.Z"`).
`src/wispy/__init__.py` derives `__version__` from it at runtime via `importlib.metadata`.
Tag schema: `vX.Y.Z` (with "v" prefix).

### Canonical path: tag push → GitHub Actions (recommended)

1. **Bump the version** in `pyproject.toml`:
   ```toml
   version = "0.3.0"
   ```

2. **Add a CHANGELOG entry.** Append a `## [0.3.0] — YYYY-MM-DD`
   block to `CHANGELOG.md` with the user-facing changes (Added /
   Changed / Fixed / Removed sections). The Release workflow extracts
   this block via `build/extract_release_notes.py` and uses it as the
   GitHub Release body — without the block the workflow fails fast.

3. **Commit** the version bump + changelog:
   ```powershell
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore(release): prepare v0.3.0"
   ```

4. **Tag and push** — CI handles the rest:
   ```powershell
   git tag v0.3.0
   git push origin main --tags
   ```

The `.github/workflows/release.yml` workflow automatically checks that
the tag matches `pyproject.toml`, builds the portable bundle on
`windows-latest` via `build/build.ps1 -CreateZip`, extracts the
matching CHANGELOG section as the release body, and publishes
`wispy-v0.3.0.zip` as the GitHub Release asset.

### Manual fallback (when CI is unavailable)

> Requires a Windows machine with `uv`, CUDA 12.x and `gh` installed.

After step 4 above:

5. **Build the bundle and ZIP**:
   ```powershell
   .\build\build.ps1 -CreateZip
   ```
   Produces `dist\wispy-v0.3.0.zip` (version is read from `pyproject.toml`).

6. **Create the GitHub Release** and attach the ZIP:
   ```powershell
   gh release create v0.3.0 dist\wispy-v0.3.0.zip `
       --title "wispy v0.3.0" `
       --notes-file release-notes.md
   ```
   (Generate `release-notes.md` first via
   `python build\extract_release_notes.py --tag v0.3.0 --output release-notes.md`.)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
