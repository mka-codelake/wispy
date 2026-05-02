"""Config loading: YAML file -> dataclass."""

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

import yaml

from .paths import get_app_dir


@dataclass
class Config:
    model_name: str = "large-v3-turbo"
    model_path: Optional[str] = None
    model_hub_id: str = "dropbox-dash/faster-whisper-large-v3-turbo"
    device: str = "auto"
    compute_type: str = "default"
    language: str = "de"
    sample_rate: int = 16000
    audio_device: Optional[int] = None
    hotkey: str = "F9"
    record_mode: str = "hold"  # "hold" or "toggle"
    beam_size: int = 5
    initial_prompt: str = ""
    restore_clipboard: bool = True
    update_check: bool = True
    auto_update: bool = False


def default_config_path() -> Path:
    """Return the default config.yaml path (next to wispy.exe or in the repo)."""
    return get_app_dir() / "config.yaml"


def load_config(path: Optional[Path] = None) -> Config:
    """Load config from YAML file, falling back to defaults for missing keys."""
    path = path or default_config_path()
    if not path.exists():
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    valid_keys = {field.name for field in fields(Config)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return Config(**filtered)
