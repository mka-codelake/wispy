"""Architecture tests for the GitHub Actions workflow YAMLs.

A broken workflow YAML breaks CI silently — GitHub will skip the run with
a vague error and the failure can go unnoticed for a while. Catching it in
the test suite is cheap insurance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _yaml_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml"))


@pytest.mark.architecture
class TestWorkflowsAreValidYaml:
    @pytest.mark.parametrize(
        "workflow_path",
        _yaml_files(),
        ids=lambda p: p.name,
    )
    def test_workflow_parses(self, workflow_path: Path):
        with open(workflow_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"{workflow_path.name} did not parse to a mapping"

    @pytest.mark.parametrize(
        "workflow_path",
        _yaml_files(),
        ids=lambda p: p.name,
    )
    def test_workflow_has_name_and_jobs(self, workflow_path: Path):
        with open(workflow_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "name" in data, f"{workflow_path.name} has no top-level name"
        assert "jobs" in data, f"{workflow_path.name} has no top-level jobs"
        assert isinstance(data["jobs"], dict)
        assert len(data["jobs"]) >= 1, f"{workflow_path.name} declares no jobs"

    @pytest.mark.parametrize(
        "workflow_path",
        _yaml_files(),
        ids=lambda p: p.name,
    )
    def test_workflow_has_trigger(self, workflow_path: Path):
        # PyYAML parses YAML key `on:` as Python boolean True. We accept either
        # form because both end up in GitHub's internal representation as the
        # `on` keyword.
        with open(workflow_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        has_trigger = "on" in data or True in data
        assert has_trigger, f"{workflow_path.name} has no trigger (on: ...)"
