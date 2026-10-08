"""Enforce the layering rules by inspecting imports (ARC-04, ARC-05, SRV-10)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = SRC / "buzsak_app"

# Lower rank = lower layer; a layer may import only its own rank or lower (ARC-04).
RANK = {"api": 0, "domain": 1, "state": 2, "ui": 3}
# Pure-data leaf module: importable from anywhere, must import no layer itself.
LEAF_MODULES = {"settings"}


def _imports(path: Path) -> list[str]:
    """Absolute dotted names imported by a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}: use absolute imports"
            if node.module:
                names.append(node.module)
    return names


def _layer(name: str) -> str | None:
    parts = name.split(".")
    if parts[0] == "buzsak_app" and len(parts) > 1 and parts[1] in RANK:
        return parts[1]
    return None


def _modules(layer: str) -> list[Path]:
    return sorted((PKG / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", ["api", "domain", "state"])
def test_only_ui_imports_flet(layer: str) -> None:
    for path in _modules(layer):
        for name in _imports(path):
            assert name.split(".")[0] != "flet", f"{path} imports flet"


@pytest.mark.parametrize("layer", list(RANK))
def test_layers_import_downward_only(layer: str) -> None:
    for path in _modules(layer):
        for name in _imports(path):
            target = _layer(name)
            if target is not None:
                assert RANK[target] <= RANK[layer], f"{path} imports upward: {name}"


def test_only_api_uses_httpx() -> None:
    for path in PKG.rglob("*.py"):
        if path.is_relative_to(PKG / "api"):
            continue
        for name in _imports(path):
            assert name.split(
                ".")[0] != "httpx", f"{path} must go through api/ (SRV-10)"


@pytest.mark.parametrize("module", sorted(LEAF_MODULES))
def test_leaf_modules_import_no_layer_and_no_flet(module: str) -> None:
    for name in _imports(PKG / f"{module}.py"):
        assert _layer(name) is None, f"{module} imports a layer: {name}"
        assert name.split(".")[0] != "flet"
