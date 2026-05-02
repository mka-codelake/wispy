"""Architecture tests for the plugin-/component-bundle architecture.

These tests are static: they parse the spec/build files rather than running
PyInstaller, because the actual build runs on Windows and pulls multi-GB
dependencies. The contract under test is:

- The app bundle (wispy.spec, build.ps1) must NOT collect or install any
  CUDA / NVIDIA runtime libraries. Those live in the separate cuda bundle.
- The release-cuda.yml workflow exists and its tag pattern matches the
  documented cuda-v* schema; the app release.yml workflow stays on v*.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_FILE = REPO_ROOT / "build" / "wispy.spec"
BUILD_PS1 = REPO_ROOT / "build" / "build.ps1"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


@pytest.mark.architecture
class TestAppBundleHasNoCuda:
    def test_spec_does_not_collect_nvidia_dlls(self):
        spec = SPEC_FILE.read_text(encoding="utf-8")

        # The previous architecture defined a `_find_nvidia_dlls` helper and
        # added its result to `binaries`. Plugin-model removes that entirely.
        assert "_find_nvidia_dlls" not in spec, (
            "wispy.spec still references _find_nvidia_dlls — CUDA collection "
            "must be removed for the plugin-model app bundle."
        )
        assert "nvidia_binaries" not in spec, (
            "wispy.spec still references nvidia_binaries — must be removed."
        )
        # No `nvidia` enumeration of any form
        assert not re.search(r"\bnvidia\b", spec, re.IGNORECASE), (
            "wispy.spec mentions 'nvidia' somewhere — review and remove."
        )

    def test_build_ps1_does_not_install_nvidia_packages(self):
        ps1 = BUILD_PS1.read_text(encoding="utf-8")
        for pkg in ("nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-runtime-cu12"):
            assert pkg not in ps1, (
                f"build.ps1 still installs {pkg} — must be removed (plugin model "
                f"keeps CUDA libs out of the app bundle)."
            )

    def test_build_ps1_has_no_gpu_switch(self):
        """The PR #23 attempt introduced a -Gpu switch. Plugin model drops it."""
        ps1 = BUILD_PS1.read_text(encoding="utf-8")
        assert "-Gpu" not in ps1 and "[switch]$Gpu" not in ps1, (
            "build.ps1 still references a -Gpu switch — plugin model has only "
            "one app build variant (CPU-only); GPU comes from cuda bundle."
        )


@pytest.mark.architecture
class TestReleaseWorkflows:
    def _load(self, name: str) -> dict:
        with open(WORKFLOWS / name, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _on_section(self, wf: dict) -> dict:
        # PyYAML can parse the YAML key `on:` as Python boolean True.
        if "on" in wf:
            return wf["on"]
        if True in wf:
            return wf[True]
        raise AssertionError("Workflow has no `on:` section")

    def test_release_cuda_workflow_exists(self):
        assert (WORKFLOWS / "release-cuda.yml").exists(), (
            "release-cuda.yml is missing — the cuda-v* tag stream cannot publish."
        )

    def test_release_cuda_triggers_on_cuda_v_tags(self):
        wf = self._load("release-cuda.yml")
        on = self._on_section(wf)
        assert "push" in on, "release-cuda.yml has no push trigger"
        tags = on["push"].get("tags", [])
        # Any pattern in the list must start with 'cuda-v'
        assert tags, "release-cuda.yml has no tag patterns under push"
        for pattern in tags:
            assert pattern.startswith("cuda-v"), (
                f"release-cuda.yml tag pattern {pattern!r} does not start with 'cuda-v'."
            )

    def test_app_release_does_not_match_cuda_tags(self):
        """The app workflow must not fire on cuda-* tags (would build wrong artefact)."""
        wf = self._load("release.yml")
        on = self._on_section(wf)
        tags = on["push"].get("tags", [])
        assert tags, "release.yml has no tag patterns under push"
        for pattern in tags:
            assert not pattern.startswith("cuda-"), (
                f"release.yml pattern {pattern!r} would also match cuda-* tags."
            )
            # The app pattern should use the v[0-9]* prefix, not bare 'v'
            assert pattern.startswith("v"), (
                f"release.yml pattern {pattern!r} should start with 'v' (semver tag)."
            )

    def test_release_cuda_publishes_zip_named_after_tag(self):
        wf = self._load("release-cuda.yml")
        # Find the gh-release step and assert it uploads the expected file
        jobs = wf["jobs"]
        steps = next(iter(jobs.values()))["steps"]
        upload_steps = [
            s for s in steps if isinstance(s.get("uses"), str) and "softprops/action-gh-release" in s["uses"]
        ]
        assert upload_steps, "release-cuda.yml does not call softprops/action-gh-release"
        files_field = upload_steps[0].get("with", {}).get("files", "")
        assert "wispy-${{ github.ref_name }}.zip" in files_field, (
            f"release-cuda.yml uploads {files_field!r}; expected the tag-named ZIP."
        )

    def test_release_cuda_writes_version_marker(self):
        wf_text = (WORKFLOWS / "release-cuda.yml").read_text(encoding="utf-8")
        # The lazy-cuda loader on the wispy side reads cuda/_version.txt to
        # decide whether the local cuda bundle is current. The workflow must
        # write that marker.
        assert "_version.txt" in wf_text, (
            "release-cuda.yml does not produce cuda/_version.txt — the runtime "
            "loader needs that marker to detect outdated bundles."
        )
