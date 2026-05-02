"""Architecture tests for the wispy module dependency graph.

Uses static AST parsing rather than dynamic imports because most runtime
modules (audio, hotkey, output, feedback, transcribe) require Windows
hardware or large GPU libraries that we cannot install in CI.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "wispy"


def _wispy_modules() -> Dict[str, Path]:
    return {p.stem: p for p in SRC_DIR.glob("*.py") if p.stem != "__init__"}


def _intra_package_imports(path: Path) -> Set[str]:
    """Return the set of wispy.* modules imported by this file.

    Picks up both `from .X import Y` (relative) and `from wispy.X import Y`
    (absolute), but ignores stdlib and third-party imports.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level >= 1 and node.module:
                # `from .module import X` -> module name is the first segment
                imports.add(node.module.split(".")[0])
            elif node.module and node.module.startswith("wispy."):
                imports.add(node.module.split(".")[1])
            elif node.module == "wispy":
                # `from wispy import X`
                pass  # X may be a module — handled by subsequent ast.alias scan
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("wispy."):
                    imports.add(alias.name.split(".")[1])
    return imports


@pytest.mark.architecture
class TestNoCircularImports:
    def test_module_graph_is_acyclic(self):
        modules = _wispy_modules()
        graph: Dict[str, Set[str]] = {
            name: _intra_package_imports(path) & set(modules)
            for name, path in modules.items()
        }

        # Detect cycles via DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in graph}
        cycles: list[list[str]] = []

        def dfs(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            stack.append(node)
            for neighbour in sorted(graph.get(node, set())):
                if color[neighbour] == GRAY:
                    cycle_start = stack.index(neighbour)
                    cycles.append(stack[cycle_start:] + [neighbour])
                elif color[neighbour] == WHITE:
                    dfs(neighbour, stack)
            stack.pop()
            color[node] = BLACK

        for module in sorted(graph):
            if color[module] == WHITE:
                dfs(module, [])

        assert cycles == [], f"Detected import cycles: {cycles}"


@pytest.mark.architecture
class TestLayerBoundaries:
    """Soft layering: low-level helpers must not import high-level orchestration."""

    PURE_HELPERS = {"paths", "config"}
    """Modules that should not depend on app composition."""

    def test_pure_helpers_do_not_import_main(self):
        for helper in self.PURE_HELPERS:
            path = SRC_DIR / f"{helper}.py"
            assert path.exists(), f"Helper {helper}.py missing"
            imports = _intra_package_imports(path)
            assert "main" not in imports, (
                f"{helper}.py imports main — that inverts the dependency layer."
            )

    def test_paths_has_no_intra_package_dependencies(self):
        """paths.py is the foundation: it cannot depend on any other wispy module."""
        modules = _wispy_modules()
        imports = _intra_package_imports(modules["paths"])
        assert imports & set(modules) == set(), (
            f"paths.py is meant to be standalone but imports: {imports & set(modules)}"
        )
