"""Shared pytest fixtures for the wispy test suite."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest


# Ensure src/ is on sys.path so `import wispy` works without installing the
# package. Editable install would do the same, but this avoids the dev-deps
# install step being a hard prerequisite.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture
def repo_root() -> Path:
    """Absolute path to the repository root, useful for fixtures that read tracked files."""
    return _REPO_ROOT


@pytest.fixture
def fake_app_dir(tmp_path: Path) -> Iterator[Path]:
    """A throwaway directory mimicking the runtime app_dir layout."""
    (tmp_path / "_internal").mkdir()
    (tmp_path / "models").mkdir()
    yield tmp_path
