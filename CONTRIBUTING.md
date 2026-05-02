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

### Kanonischer Weg: Tag-Push → GitHub Actions (empfohlen)

1. **Version bumpen** in `pyproject.toml`:
   ```toml
   version = "0.3.0"
   ```

2. **Commit** des Version-Bumps:
   ```powershell
   git add pyproject.toml
   git commit -m "chore: bump version to 0.3.0"
   ```

3. **Tag setzen und pushen** — CI übernimmt den Rest:
   ```powershell
   git tag v0.3.0
   git push origin main --tags
   ```

Der Workflow `.github/workflows/release.yml` prüft automatisch, dass Tag und `pyproject.toml`-Version übereinstimmen, baut das portable Bundle auf `windows-latest` via `build/build.ps1 -CreateZip` und veröffentlicht `wispy-v0.3.0.zip` als GitHub-Release-Asset mit automatisch generierten Release Notes.

### Manueller Fallback (falls CI nicht verfügbar)

> Erfordert eine Windows-Maschine mit `uv`, CUDA 12.x und `gh` installiert.

Nach Schritt 3 oben:

4. **Bundle bauen und ZIP erstellen**:
   ```powershell
   .\build\build.ps1 -CreateZip
   ```
   Erzeugt `dist\wispy-v0.3.0.zip` (Version wird automatisch aus `pyproject.toml` gelesen).

5. **GitHub Release erstellen** und ZIP anhängen:
   ```powershell
   gh release create v0.3.0 dist\wispy-v0.3.0.zip `
       --title "wispy v0.3.0" `
       --notes "Brief description of what changed."
   ```

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
