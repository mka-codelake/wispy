"""Path helpers: PyInstaller-aware app directory and model location resolution."""

import sys
from pathlib import Path
from typing import Optional


REQUIRED_MODEL_FILES = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
)


def get_app_dir() -> Path:
    """Return the directory that holds config.yaml, models/, logs/.

    - PyInstaller bundle: folder of wispy.exe (sys.executable).
    - Running from source: repo root (three levels up from src/wispy/paths.py).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resolve_model_path(model_name: str, model_path: Optional[str] = None) -> Path:
    """Resolve the effective model directory.

    - If model_path is set, use it (absolute or relative to app_dir).
    - Otherwise fall back to <app_dir>/models/<model_name>.
    """
    if model_path:
        p = Path(model_path)
        if not p.is_absolute():
            p = get_app_dir() / p
        return p.resolve()
    return (get_app_dir() / "models" / model_name).resolve()


def resolve_cuda_path(cuda_path: Optional[str] = None) -> Path:
    """Resolve the effective CUDA runtime directory.

    Mirrors `resolve_model_path`. The CUDA DLLs (cublas64_12.dll, cudnn_*,
    cudart64_12.dll) live here, plus a `_version.txt` marker.

    - If cuda_path is set, use it (absolute or relative to app_dir).
    - Otherwise fall back to <app_dir>/cuda.
    """
    if cuda_path:
        p = Path(cuda_path)
        if not p.is_absolute():
            p = get_app_dir() / p
        return p.resolve()
    return (get_app_dir() / "cuda").resolve()


def check_model_complete(model_dir: Path) -> bool:
    """Return True if model_dir exists and contains every required file."""
    if not model_dir.is_dir():
        return False
    return all((model_dir / name).is_file() for name in REQUIRED_MODEL_FILES)


def missing_model_files(model_dir: Path) -> list:
    """Return the names of required files that are missing from model_dir."""
    if not model_dir.is_dir():
        return list(REQUIRED_MODEL_FILES)
    return [name for name in REQUIRED_MODEL_FILES if not (model_dir / name).is_file()]


def default_config_template_path() -> Optional[Path]:
    """Return the location of the config.yaml template shipped with wispy.

    The template is the source-of-truth default `config.yaml` and is used
    by the runtime migration step (see ``config._migrate_config_yaml_if_needed``)
    to backfill new fields into a user-side config.yaml after an update.

    Resolution:
    - **Frozen build** (PyInstaller): ``<exe_dir>/_internal/config.yaml.default``,
      written by build.ps1 right before PyInstaller runs and pulled into the
      bundle via wispy.spec's datas.
    - **Source run**: ``<repo_root>/config.yaml`` itself — the same file the
      build snapshots, just under its primary name.

    Returns the absolute path if it exists, ``None`` otherwise.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller One-Folder: _internal/ sits next to the .exe.
        internal = Path(sys.executable).resolve().parent / "_internal"
        for candidate in ("config.yaml.default", "config.yaml"):
            template = internal / candidate
            if template.is_file():
                return template
        return None

    # Source run: use the repository's own config.yaml as the template.
    template = Path(__file__).resolve().parents[2] / "config.yaml"
    return template if template.is_file() else None


def get_vocabulary_path() -> Path:
    """Return the path to hotwords.txt next to config.yaml (app_dir)."""
    return get_app_dir() / "hotwords.txt"


def load_vocabulary() -> list[str]:
    """Load vocabulary terms from hotwords.txt.

    Returns a list of non-empty, non-comment lines. Returns [] if the file
    does not exist.
    """
    path = get_vocabulary_path()
    if not path.is_file():
        return []
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            term = line.strip()
            if term and not term.startswith("#"):
                terms.append(term)
    return terms
