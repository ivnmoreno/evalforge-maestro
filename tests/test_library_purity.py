"""AST architectural boundary, logging purity, and cold-start lazy-import tests."""

from __future__ import annotations

import ast
import logging
import subprocess
import sys
from pathlib import Path

SRC_ROOT = Path("src/evalforge_maestro")

_FORBIDDEN_CONFIG_AND_CLI_MODULES = frozenset(
    {
        "cli",
        "evalforge_maestro.cli",
        "tomllib",
        "tomli",
        "dotenv",
        "python_dotenv",
        "configparser",
    }
)
_FORBIDDEN_ADAPTER_MODULES = frozenset({"adapters", "evalforge_maestro.adapters"})
_HEAVY_OPTIONAL_MODULES = (
    "litellm",
    "docpipe_maestro",
    "numpy",
    "scipy",
    "jsonschema",
    "tomllib",
    "dotenv",
)


def _iter_imported_modules(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    return imported


def _iter_call_names(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
    return names


def test_library_ast_import_and_logging_boundaries() -> None:
    py_files = sorted(SRC_ROOT.rglob("*.py"))
    assert py_files

    for py_file in py_files:
        rel = py_file.relative_to(SRC_ROOT).as_posix()
        imports = _iter_imported_modules(py_file)
        calls = _iter_call_names(py_file)

        # Zero CLI, tomllib, or dotenv imports anywhere in library code
        for mod in imports:
            assert mod not in _FORBIDDEN_CONFIG_AND_CLI_MODULES, f"{rel} must not import {mod!r}"
            assert not mod.startswith("evalforge_maestro.cli"), (
                f"{rel} must not import CLI module {mod!r}"
            )

        # Core/domain subsystems must never import adapters (only top-level __init__.py façade may)
        if not rel.startswith("adapters/") and rel != "__init__.py":
            for mod in imports:
                assert mod not in _FORBIDDEN_ADAPTER_MODULES and not mod.startswith(
                    "evalforge_maestro.adapters"
                ), f"Library module {rel} must not import target adapters ({mod!r})"

        # Leaf modules types.py, exceptions.py, _canonical.py must not import domain subpackages
        if rel in {"types.py", "exceptions.py", "_canonical.py"}:
            for mod in imports:
                for sub in ("datasets", "adapters", "metrics", "execution", "storage"):
                    assert not mod.startswith(f"evalforge_maestro.{sub}"), (
                        f"Leaf module {rel} must not import {mod!r}"
                    )

        # Zero stdout print() or root logger mutation in library modules
        assert "print" not in calls, f"Library module {rel} must not call print()"
        assert "basicConfig" not in calls, f"Library module {rel} must not call basicConfig()"
        assert "StreamHandler" not in calls, f"Library module {rel} must not attach StreamHandler"
        assert "FileHandler" not in calls, f"Library module {rel} must not attach FileHandler"


def test_package_logger_uses_null_handler_only() -> None:
    pkg_logger = logging.getLogger("evalforge_maestro")
    assert any(isinstance(h, logging.NullHandler) for h in pkg_logger.handlers)
    assert all(isinstance(h, logging.NullHandler) for h in pkg_logger.handlers)


def test_cold_start_import_loads_no_heavy_optional_dependencies() -> None:
    probe = (
        "import sys, evalforge_maestro; "
        f"forbidden = {list(_HEAVY_OPTIONAL_MODULES)!r}; "
        "loaded = [m for m in forbidden if any(k == m or k.startswith(m + '.') "
        "for k in sys.modules)]; "
        "assert not loaded, f'Unexpected cold-start imports: {loaded}'"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
