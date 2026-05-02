"""Unit tests for wispy.config."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from wispy.config import Config, default_config_path, load_config


class TestConfigDefaults:
    def test_dataclass_has_expected_field_set(self):
        names = {f.name for f in fields(Config)}
        expected = {
            "model_name",
            "model_path",
            "model_hub_id",
            "device",
            "compute_type",
            "language",
            "sample_rate",
            "audio_device",
            "hotkey",
            "record_mode",
            "beam_size",
            "initial_prompt",
            "restore_clipboard",
            "update_check",
            "auto_update",
        }
        assert names == expected

    def test_default_instance_carries_documented_defaults(self):
        cfg = Config()
        assert cfg.model_name == "large-v3-turbo"
        assert cfg.model_hub_id == "dropbox-dash/faster-whisper-large-v3-turbo"
        assert cfg.language == "de"
        assert cfg.sample_rate == 16000
        assert cfg.hotkey == "F9"
        assert cfg.record_mode == "hold"
        assert cfg.beam_size == 5
        assert cfg.restore_clipboard is True
        assert cfg.update_check is True
        assert cfg.auto_update is False
        assert cfg.model_path is None
        assert cfg.audio_device is None
        assert cfg.initial_prompt == ""


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, tmp_path: Path):
        result = load_config(tmp_path / "does-not-exist.yaml")
        assert isinstance(result, Config)
        assert result == Config()

    def test_overrides_only_specified_keys(self, tmp_path: Path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("hotkey: F12\nlanguage: en\n", encoding="utf-8")

        cfg = load_config(cfg_path)

        assert cfg.hotkey == "F12"
        assert cfg.language == "en"
        # Untouched keys keep defaults
        assert cfg.model_name == "large-v3-turbo"
        assert cfg.update_check is True

    def test_unknown_keys_are_silently_dropped(self, tmp_path: Path):
        """Forward-compat: unknown keys must not crash old wispy versions."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "hotkey: F10\nfuture_feature_xyz: something\n", encoding="utf-8"
        )

        cfg = load_config(cfg_path)

        assert cfg.hotkey == "F10"
        # No AttributeError, no crash
        assert not hasattr(cfg, "future_feature_xyz")

    def test_empty_yaml_is_valid(self, tmp_path: Path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("", encoding="utf-8")

        cfg = load_config(cfg_path)

        assert cfg == Config()

    def test_yaml_with_only_comments_is_valid(self, tmp_path: Path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("# only comments\n# nothing else\n", encoding="utf-8")

        cfg = load_config(cfg_path)

        assert cfg == Config()

    def test_default_config_path_lives_under_app_dir(self, mocker, tmp_path: Path):
        mocker.patch("wispy.config.get_app_dir", return_value=tmp_path)
        assert default_config_path() == tmp_path / "config.yaml"


class TestRepoConfigYamlMatchesDefaults:
    """The shipped config.yaml must agree with the dataclass defaults.

    Drift between the two confuses users: changing a default in code without
    updating config.yaml means the documented default differs from the actual
    runtime default depending on whether the user has a config.yaml or not.
    """

    def test_repo_config_yaml_does_not_drift_from_dataclass(self, repo_root: Path):
        cfg_path = repo_root / "config.yaml"
        if not cfg_path.exists():
            pytest.skip("No top-level config.yaml in repo")

        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        defaults = Config()
        for key, yaml_value in data.items():
            if not hasattr(defaults, key):
                # Keys that exist in YAML but not in Config are caught
                # separately by load_config (silently dropped); we want a
                # louder signal here.
                pytest.fail(f"config.yaml has key {key!r} that Config dataclass lacks")
            default_value = getattr(defaults, key)
            assert yaml_value == default_value, (
                f"config.yaml[{key!r}] = {yaml_value!r} but Config default is "
                f"{default_value!r}. The two are out of sync."
            )
