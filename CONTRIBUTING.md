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
Tag schema: `vX.Y.Z` (with "v" prefix). Current line: `version = "X.Y.Z"` in `[project]`.

### Steps (run on Windows — the build requires PyInstaller + CUDA DLLs)

1. **Bump the version** in `pyproject.toml` (the single source of truth):
   ```toml
   version = "0.3.0"
   ```

2. **Commit** the version bump:
   ```powershell
   git add pyproject.toml
   git commit -m "chore: bump version to 0.3.0"
   ```

3. **Tag** the commit:
   ```powershell
   git tag v0.3.0
   git push origin main --tags
   ```

4. **Build the bundle and create the ZIP**:
   ```powershell
   .\build\build.ps1 -CreateZip
   ```
   This produces `dist\wispy-v0.3.0.zip` (reads the version from `pyproject.toml` automatically).

5. **Create the GitHub Release** and attach the ZIP:
   ```powershell
   gh release create v0.3.0 dist\wispy-v0.3.0.zip `
       --title "wispy v0.3.0" `
       --notes "Brief description of what changed."
   ```

The release is now live on GitHub with the versioned ZIP as an asset.

> **Note:** Steps 4 and 5 require a Windows machine with `uv`, CUDA 12.x, and `gh` installed.
> Automation via GitHub Actions is planned for Phase 2 (separate issue).

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
