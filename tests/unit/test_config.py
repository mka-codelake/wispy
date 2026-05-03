"""Unit tests for wispy.config."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from wispy.config import (
    Config,
    _apply_user_overrides_to_template,
    _migrate_config_yaml_if_needed,
    _yaml_scalar,
    default_config_path,
    load_config,
)


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
            "cuda_path",
            "model_local_source",
            "cuda_local_source",
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


class TestYamlScalar:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "null"),
            (True, "true"),
            (False, "false"),
            (16000, "16000"),
            (5, "5"),
        ],
    )
    def test_simple_scalars(self, value, expected):
        assert _yaml_scalar(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("F9", '"F9"'),
            ("auto", '"auto"'),
            ("", '""'),
            ('with "quotes"', '"with \\"quotes\\""'),
            ("path\\with\\backslash", '"path\\\\with\\\\backslash"'),
            # YAML reserved tokens MUST be quoted, otherwise yes/no/null
            # are parsed as bools or null.
            ("yes", '"yes"'),
            ("no", '"no"'),
            ("null", '"null"'),
        ],
    )
    def test_strings_are_always_quoted(self, value, expected):
        assert _yaml_scalar(value) == expected

    def test_quoted_string_round_trips_through_yaml(self):
        # Whatever _yaml_scalar produces must be loadable by yaml.safe_load
        # back into the original Python string. This is the contract that
        # makes the line-replace correct.
        for s in ["F9", 'with "quotes"', 'D:\\path\\to', "ja", "yes", ""]:
            rendered = _yaml_scalar(s)
            parsed = yaml.safe_load(f"key: {rendered}")["key"]
            assert parsed == s, f"Roundtrip broke for {s!r}: rendered={rendered!r}, parsed={parsed!r}"


class TestApplyUserOverrides:
    TEMPLATE = (
        "# header comment\n"
        "model_name: \"large-v3-turbo\"\n"
        "\n"
        "# spacing\n"
        "hotkey: \"F9\"              # e.g. F9, F12, ctrl+space\n"
        "device: \"auto\"\n"
        "sample_rate: 16000\n"
        "audio_device: null\n"
        "auto_update: false\n"
    )

    def test_no_overrides_returns_template_verbatim(self):
        assert _apply_user_overrides_to_template(self.TEMPLATE, {}) == self.TEMPLATE

    def test_simple_string_override(self):
        result = _apply_user_overrides_to_template(self.TEMPLATE, {"hotkey": "F12"})
        assert 'hotkey: "F12"' in result
        # Inline comment must be preserved
        assert "# e.g. F9, F12, ctrl+space" in result
        # Other lines untouched
        assert 'device: "auto"' in result

    def test_int_override(self):
        result = _apply_user_overrides_to_template(self.TEMPLATE, {"sample_rate": 22050})
        assert "sample_rate: 22050" in result
        assert "sample_rate: 16000" not in result

    def test_null_override_renders_as_yaml_null(self):
        # User might explicitly set audio_device to a number then back to null.
        # The renderer must output `null`, not the Python literal.
        result = _apply_user_overrides_to_template(
            self.TEMPLATE, {"audio_device": None}
        )
        assert "audio_device: null" in result

    def test_bool_override(self):
        result = _apply_user_overrides_to_template(
            self.TEMPLATE, {"auto_update": True}
        )
        assert "auto_update: true" in result

    def test_unknown_key_in_overrides_is_ignored(self):
        # If overrides contain a key that is not in the template, the
        # template stays untouched and the key is dropped on the floor.
        result = _apply_user_overrides_to_template(
            self.TEMPLATE, {"unknown_key": "x"}
        )
        assert "unknown_key" not in result

    def test_multiple_overrides_applied(self):
        result = _apply_user_overrides_to_template(
            self.TEMPLATE, {"hotkey": "F12", "device": "cuda", "sample_rate": 48000}
        )
        assert 'hotkey: "F12"' in result
        assert 'device: "cuda"' in result
        assert "sample_rate: 48000" in result


class TestMigrateConfigYaml:
    """End-to-end exercises for _migrate_config_yaml_if_needed."""

    TEMPLATE_TEXT = (
        "# wispy config\n"
        "model_name: \"large-v3-turbo\"\n"
        "model_path: null\n"
        "model_hub_id: \"dropbox-dash/faster-whisper-large-v3-turbo\"\n"
        "device: \"auto\"\n"
        "compute_type: \"default\"\n"
        "language: \"de\"\n"
        "sample_rate: 16000\n"
        "audio_device: null\n"
        "hotkey: \"F9\"\n"
        "record_mode: \"hold\"\n"
        "beam_size: 5\n"
        "initial_prompt: \"\"\n"
        "restore_clipboard: true\n"
        "update_check: true\n"
        "auto_update: false\n"
        "cuda_path: null\n"
        "model_local_source: null\n"
        "cuda_local_source: null\n"
    )

    def _setup(self, tmp_path: Path, mocker, user_yaml_text: str):
        user_yaml = tmp_path / "config.yaml"
        user_yaml.write_text(user_yaml_text, encoding="utf-8")
        template = tmp_path / "config.yaml.default"
        template.write_text(self.TEMPLATE_TEXT, encoding="utf-8")
        mocker.patch(
            "wispy.config.default_config_template_path", return_value=template
        )
        return user_yaml

    def test_complete_yaml_is_no_op(self, tmp_path: Path, mocker):
        # YAML already has every dataclass field — migration must not touch it.
        user_yaml = self._setup(tmp_path, mocker, self.TEMPLATE_TEXT)
        original_text = user_yaml.read_text()
        original_mtime = user_yaml.stat().st_mtime

        _migrate_config_yaml_if_needed(user_yaml)

        assert user_yaml.read_text() == original_text
        assert not (tmp_path / "config.yaml.backup").exists()

    def test_missing_fields_trigger_backfill_with_user_overrides_preserved(
        self, tmp_path: Path, mocker, capsys
    ):
        # Old user yaml — only hotkey and language, both set to non-default.
        # cuda_path / model_local_source / cuda_local_source are missing.
        user_yaml = self._setup(
            tmp_path, mocker, "hotkey: \"F12\"\nlanguage: \"en\"\n"
        )

        _migrate_config_yaml_if_needed(user_yaml)

        # Backup created
        backup = tmp_path / "config.yaml.backup"
        assert backup.exists()
        assert backup.read_text() == "hotkey: \"F12\"\nlanguage: \"en\"\n"

        # Merged file: full set of keys with user values preserved
        merged = yaml.safe_load(user_yaml.read_text())
        assert set(merged.keys()) == {f.name for f in fields(Config)}
        assert merged["hotkey"] == "F12"           # user override preserved
        assert merged["language"] == "en"           # user override preserved
        assert merged["model_name"] == "large-v3-turbo"  # default from template
        assert merged["cuda_path"] is None          # newly added field

        # User-facing message
        out = capsys.readouterr().out
        assert "Added" in out and "new field" in out
        assert "config.yaml.backup" in out

    def test_overwrites_previous_backup(self, tmp_path: Path, mocker):
        # Run migration twice in scenarios that BOTH actually trigger work.
        # The second backup must reflect the state right before the second
        # migration, not the first.
        user_yaml = self._setup(tmp_path, mocker, "hotkey: \"F12\"\n")
        _migrate_config_yaml_if_needed(user_yaml)
        backup_after_first = (tmp_path / "config.yaml.backup").read_text()
        assert backup_after_first == "hotkey: \"F12\"\n"

        # Simulate a state where the user removed several fields again so a
        # second migration has work to do, plus changed hotkey to F11.
        user_yaml.write_text("hotkey: \"F11\"\n", encoding="utf-8")
        _migrate_config_yaml_if_needed(user_yaml)

        backup_after_second = (tmp_path / "config.yaml.backup").read_text()
        # Backup now reflects the F11 state, not F12.
        assert backup_after_second == "hotkey: \"F11\"\n"
        assert backup_after_second != backup_after_first

    def test_idempotent_after_first_migration(self, tmp_path: Path, mocker):
        user_yaml = self._setup(tmp_path, mocker, "hotkey: \"F12\"\n")
        _migrate_config_yaml_if_needed(user_yaml)
        first_text = user_yaml.read_text()

        # Rerun: should be no-op now (all fields present)
        _migrate_config_yaml_if_needed(user_yaml)
        second_text = user_yaml.read_text()

        assert first_text == second_text

    def test_multiline_value_is_skipped_with_warning(
        self, tmp_path: Path, mocker, capsys
    ):
        # Old yaml has a multi-line initial_prompt + missing new fields.
        old = (
            "hotkey: \"F12\"\n"
            "initial_prompt: |\n"
            "  Hello world,\n"
            "  multi-line prompt.\n"
        )
        user_yaml = self._setup(tmp_path, mocker, old)

        _migrate_config_yaml_if_needed(user_yaml)

        merged = yaml.safe_load(user_yaml.read_text())
        # F12 was carried over (single-line override)
        assert merged["hotkey"] == "F12"
        # Multi-line was NOT carried over — falls back to template default
        assert merged["initial_prompt"] == ""
        # Warning printed to stderr
        err = capsys.readouterr().err
        assert "Multi-line" in err
        assert "initial_prompt" in err
        # Backup still has the original multi-line value
        assert "multi-line prompt" in (tmp_path / "config.yaml.backup").read_text()

    def test_no_template_warns_and_leaves_user_file_untouched(
        self, tmp_path: Path, mocker, capsys
    ):
        user_yaml = tmp_path / "config.yaml"
        user_yaml.write_text("hotkey: \"F12\"\n", encoding="utf-8")
        mocker.patch(
            "wispy.config.default_config_template_path", return_value=None
        )

        original = user_yaml.read_text()
        _migrate_config_yaml_if_needed(user_yaml)

        # File unchanged, no backup created
        assert user_yaml.read_text() == original
        assert not (tmp_path / "config.yaml.backup").exists()

        err = capsys.readouterr().err
        assert "no default template was found" in err

    def test_missing_user_file_is_no_op(self, tmp_path: Path, mocker):
        # Pre-template-missing path: migration only runs if the user has
        # a config.yaml in the first place.
        user_yaml = tmp_path / "does-not-exist.yaml"
        mocker.patch(
            "wispy.config.default_config_template_path", return_value=None
        )

        _migrate_config_yaml_if_needed(user_yaml)  # must not raise

        assert not user_yaml.exists()


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
