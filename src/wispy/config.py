"""Config loading: YAML file -> dataclass.

Includes a small migration helper so that user-side ``config.yaml`` files
get backfilled with new fields when they are added to the dataclass in a
new wispy version. See ``_migrate_config_yaml_if_needed``.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from .paths import default_config_template_path, get_app_dir


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
    # Storage choice: where to keep the CUDA runtime DLLs once installed.
    # null = <app_dir>/cuda/. Useful when several wispy installs share one
    # CUDA bundle on disk.
    cuda_path: Optional[str] = None
    # Test bootstrap: when set, wispy uses these local artefacts instead of
    # downloading from HuggingFace / GitHub Releases. Speeds up iteration
    # and enables offline testing. null = normal network download.
    model_local_source: Optional[str] = None     # path to a complete model dir
    cuda_local_source: Optional[str] = None      # path to a wispy-cuda-*.zip OR an extracted dir


def default_config_path() -> Path:
    """Return the default config.yaml path (next to wispy.exe or in the repo)."""
    return get_app_dir() / "config.yaml"


def load_config(path: Optional[Path] = None, *, migrate: bool = True) -> Config:
    """Load config from YAML file, falling back to defaults for missing keys.

    When ``migrate`` is True (the default), user-side config.yaml files that
    are missing fields known to the current ``Config`` dataclass get
    automatically backfilled from the bundled template — see
    ``_migrate_config_yaml_if_needed``. Tests pass ``migrate=False`` to
    keep load_config side-effect-free.
    """
    path = path or default_config_path()

    if migrate:
        try:
            _migrate_config_yaml_if_needed(path)
        except Exception as e:
            # Migration must never block startup. A failed migration leaves
            # the user's config untouched and the dataclass defaults will
            # cover the missing fields.
            print(f"[config] Migration skipped due to error: {e}", file=sys.stderr)

    if not path.exists():
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    valid_keys = {field.name for field in fields(Config)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return Config(**filtered)


# ---------------------------------------------------------------------------
# Migration: backfill new dataclass fields into an older user config.yaml
# ---------------------------------------------------------------------------

def _migrate_config_yaml_if_needed(user_path: Path) -> None:
    """If user_path is missing dataclass fields, merge them in from the template.

    Strategy (preserves the user's customised values, may lose user comments):

    1. Read the user's config.yaml. If every dataclass field is already
       present: do nothing.
    2. If fields are missing, locate the bundled default template via
       ``default_config_template_path()``. If no template can be found,
       print a warning and bail — the dataclass defaults will still cover
       missing fields at runtime, the user just won't see the new keys
       in their file.
    3. Backup the user's config to ``config.yaml.backup`` (overwrites any
       previous backup — most recent migration wins).
    4. Walk every field. For each field whose user value differs from the
       current dataclass default, replace the corresponding line in the
       template via regex. Multi-line user values are flagged and skipped
       (the template's default stays, with a console hint that manual
       migration is required).
    5. Write the merged result back to user_path.
    """
    if not user_path.is_file():
        return  # First-run: there is no config.yaml yet to migrate.

    with open(user_path, "r", encoding="utf-8") as f:
        user_data = yaml.safe_load(f) or {}
    if not isinstance(user_data, dict):
        return  # Empty or malformed YAML — nothing to migrate from.

    dataclass_fields = {f.name: f.default for f in fields(Config)}
    missing = [k for k in dataclass_fields if k not in user_data]
    if not missing:
        return  # Already up to date.

    template_path = default_config_template_path()
    if template_path is None:
        print(
            f"[config] config.yaml is missing {len(missing)} new field(s) "
            f"({', '.join(missing)}) but no default template was found. "
            "Please add the fields manually or reinstall wispy.",
            file=sys.stderr,
        )
        return

    # Detect multi-line user values that we cannot safely line-replace.
    multiline_overrides = [
        k
        for k, v in user_data.items()
        if k in dataclass_fields
        and v != dataclass_fields[k]
        and isinstance(v, str)
        and "\n" in v
    ]

    backup_path = user_path.with_name(user_path.name + ".backup")
    shutil.copy2(user_path, backup_path)

    template_text = template_path.read_text(encoding="utf-8")
    overrides = {
        k: v
        for k, v in user_data.items()
        if k in dataclass_fields
        and v != dataclass_fields[k]
        and k not in multiline_overrides
    }
    merged_text = _apply_user_overrides_to_template(template_text, overrides)
    user_path.write_text(merged_text, encoding="utf-8")

    print(
        f"[config] Added {len(missing)} new field(s) to config.yaml: "
        f"{', '.join(missing)}"
    )
    print(f"[config] Backup of your previous config saved as {backup_path.name}.")
    if multiline_overrides:
        print(
            f"[config] Multi-line value(s) detected for {', '.join(multiline_overrides)} "
            "— these were reset to the template default. Please re-apply them "
            f"manually from {backup_path.name}.",
            file=sys.stderr,
        )
    print("[config] Comments from your previous config.yaml were not preserved.")


def _apply_user_overrides_to_template(template: str, overrides: Dict[str, Any]) -> str:
    """Replace each ``key: <default>`` line in template with the user's value.

    The trailing inline comment, indentation and surrounding whitespace are
    preserved. Only the value token between the colon and the comment / EOL
    is rewritten.

    Each override matches at most one line (the first occurrence) — config.yaml
    sections are flat, so a single match per key is correct.
    """
    if not overrides:
        return template

    remaining = dict(overrides)
    out_lines = []
    for line in template.splitlines(keepends=True):
        if remaining:
            replaced_line, key = _try_replace_value(line, remaining)
            if key is not None:
                line = replaced_line
                remaining.pop(key, None)
        out_lines.append(line)
    return "".join(out_lines)


_VALUE_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<sep>:[ \t]+)"
    r"(?P<value>[^\r\n#]*?)"
    r"(?P<trail>[ \t]*(?:#[^\r\n]*)?\r?\n?)$"
)


def _try_replace_value(line: str, overrides: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """If `line` declares a key that is in `overrides`, rewrite the value.

    Returns ``(possibly_modified_line, key_used)``. ``key_used`` is None when
    no replacement happened.
    """
    match = _VALUE_LINE_RE.match(line)
    if not match:
        return line, None
    key = match.group("key")
    if key not in overrides:
        return line, None
    new_value = _yaml_scalar(overrides[key])
    rebuilt = (
        f"{match.group('indent')}{key}{match.group('sep')}{new_value}{match.group('trail')}"
    )
    return rebuilt, key


def _yaml_scalar(value: Any) -> str:
    """Render a Python value as a YAML scalar for inline replacement."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Always quote strings — defends against YAML reserved tokens
        # (``yes``, ``no``, ``null``, ``on``, ``off``) and against values
        # that would change meaning when unquoted.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    # Fallback — yaml.safe_dump produces a single-line scalar for most
    # primitive types we care about.
    return yaml.safe_dump(value, default_flow_style=True).strip().rstrip("...").strip()
