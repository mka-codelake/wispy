"""Unit tests for build/extract_release_notes.py.

The extractor lives under build/ rather than src/wispy/ because it is only
ever used by the release CI. We still test it: a silent regression here
would mean the GitHub Release body falls back to whatever default the
softprops action picks, which is exactly what we are trying to avoid.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

from extract_release_notes import extract_section


SAMPLE_CHANGELOG = """\
# Changelog

All notable changes to wispy will be documented in this file.

## [0.4.3] — 2026-05-03

Hotfix für zwei Probleme aus v0.4.1.

### Fixed
- CUDA-Treiber wurden trotz Installation nicht gefunden.
- Modell-Download zeigte keinen Fortschritt.

## [0.4.2] — 2026-05-03

Test-Komfort.

### Added
- `cuda_path` in config.yaml.
- `model_local_source` und `cuda_local_source`.

### Changed
- cuda_loader API erweitert.

## [0.3.0] — 2026-05-02

### Added
- Update mechanism.

### Notes
- Anonymous GitHub API.

[0.4.3]: https://example.com/compare/v0.4.2...v0.4.3
[0.4.2]: https://example.com/compare/v0.4.1...v0.4.2
[0.3.0]: https://example.com/compare/v0.2.0...v0.3.0
"""


class TestExtractSection:
    def test_returns_body_for_existing_version(self):
        body = extract_section(SAMPLE_CHANGELOG, "0.4.3")
        assert body is not None
        assert "Hotfix für zwei Probleme" in body
        assert "### Fixed" in body
        assert "CUDA-Treiber" in body

    def test_excludes_heading_line(self):
        body = extract_section(SAMPLE_CHANGELOG, "0.4.3")
        assert "## [0.4.3]" not in body
        assert "2026-05-03" not in body.splitlines()[0]

    def test_stops_before_next_section_heading(self):
        body = extract_section(SAMPLE_CHANGELOG, "0.4.3")
        # Must not bleed into v0.4.2's content
        assert "Test-Komfort" not in body
        assert "cuda_path" not in body

    def test_middle_section_isolates_content(self):
        body = extract_section(SAMPLE_CHANGELOG, "0.4.2")
        assert body is not None
        assert "Test-Komfort" in body
        assert "cuda_path" in body
        assert "cuda_loader API erweitert" in body
        # Not bleeding into next or previous
        assert "Hotfix" not in body
        assert "Update mechanism" not in body

    def test_last_section_excludes_link_reference_table(self):
        """The `[X.Y.Z]: https://...` table at the bottom is repo-doc only."""
        body = extract_section(SAMPLE_CHANGELOG, "0.3.0")
        assert body is not None
        assert "Update mechanism" in body
        assert "Anonymous GitHub API" in body
        # Link references must not be in the release body
        assert "[0.4.3]: https://" not in body
        assert "[0.3.0]: https://" not in body

    def test_returns_none_for_missing_version(self):
        assert extract_section(SAMPLE_CHANGELOG, "9.9.9") is None

    def test_does_not_match_partial_version(self):
        # "0.4" should not match "0.4.3" (we want exact-version matching)
        assert extract_section(SAMPLE_CHANGELOG, "0.4") is None

    def test_handles_crlf_line_endings(self):
        crlf = SAMPLE_CHANGELOG.replace("\n", "\r\n")
        body = extract_section(crlf, "0.4.3")
        assert body is not None
        assert "Hotfix für zwei Probleme" in body

    def test_body_is_trimmed(self):
        body = extract_section(SAMPLE_CHANGELOG, "0.4.3")
        # Should not start with leading blank, should not end with whitespace
        assert not body.startswith("\n")
        assert not body.endswith("\n\n")
        assert body == body.rstrip()
