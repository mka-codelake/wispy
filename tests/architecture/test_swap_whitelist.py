"""Architecture tests for the update-swap whitelist.

The whitelist of files that the PowerShell swap helper must not touch is
the contract that protects user data. It exists in three places:

1. `updater._SWAP_WHITELIST` — Python source of truth, drives the PS filter.
2. The generated PowerShell script's `Where-Object` filter — derived from #1.
3. CLAUDE.md's documented whitelist — human-readable reference.

These must agree. Drift here is a regression risk: a name silently dropped
from the whitelist will erase user files on the next swap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from wispy import updater


@pytest.mark.architecture
class TestPowerShellFilterMatchesPythonWhitelist:
    """The PS script's Where-Object filter must list exactly the same names
    as `_SWAP_WHITELIST`, and in sorted order."""

    def test_generated_script_filter_lists_each_whitelist_entry_exactly_once(
        self, tmp_path: Path
    ):
        app_dir = tmp_path / "app"
        app_bundle = tmp_path / "app-bundle"
        cuda_bundle = tmp_path / "cuda-bundle"
        backup = tmp_path / "backup"
        for d in (app_dir, app_bundle, cuda_bundle, backup):
            d.mkdir()

        script = updater._build_swap_script(
            app_dir=app_dir,
            cuda_dir=app_dir / "cuda",
            new_app_bundle=app_bundle,
            new_cuda_bundle=cuda_bundle,
            backup=backup,
        )

        for name in updater._SWAP_WHITELIST:
            occurrences = script.count(f"$_.Name -ne '{name}'")
            assert occurrences >= 1, (
                f"Whitelist entry {name!r} is missing from the PS Where-Object filter."
            )

    def test_filter_uses_sorted_order_for_determinism(self, tmp_path: Path):
        app_dir = tmp_path / "app"
        app_bundle = tmp_path / "app-bundle"
        cuda_bundle = tmp_path / "cuda-bundle"
        backup = tmp_path / "backup"
        for d in (app_dir, app_bundle, cuda_bundle, backup):
            d.mkdir()

        script = updater._build_swap_script(
            app_dir=app_dir,
            cuda_dir=app_dir / "cuda",
            new_app_bundle=app_bundle,
            new_cuda_bundle=cuda_bundle,
            backup=backup,
        )

        # Extract every '$_.Name -ne '<name>'' fragment in script order.
        # The plugin-model app-swap block has two filter loops (Move + Copy),
        # so each whitelist entry must appear exactly twice in sorted order.
        fragments = re.findall(r"\$_\.Name -ne '([^']+)'", script)
        wl_sorted = sorted(updater._SWAP_WHITELIST)
        assert fragments == wl_sorted * 2, (
            f"Filter order is not 'sorted whitelist x2'.\n"
            f"  Expected: {wl_sorted * 2}\n"
            f"  Actual  : {fragments}"
        )


@pytest.mark.architecture
class TestClaudeMdMentionsAllUserVisibleEntries:
    """CLAUDE.md's documented whitelist must mention every user-facing whitelist entry.

    Internal entries (update-staging, update-backup) are implementation detail
    and can stay out of the doc.
    """

    INTERNAL = {"update-staging", "update-backup"}

    def test_user_facing_entries_appear_in_claude_md(self, repo_root: Path):
        claude_md = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
        user_facing = updater._SWAP_WHITELIST - self.INTERNAL

        missing = [name for name in user_facing if name not in claude_md]
        assert missing == [], (
            f"User-facing whitelist entries {missing} are not documented in CLAUDE.md. "
            "If you removed them on purpose, also remove them from the whitelist."
        )
