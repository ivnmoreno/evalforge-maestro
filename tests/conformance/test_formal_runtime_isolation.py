"""Runtime-independence and packaging-boundary tests for the Formal Assurance Layer."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

from evalforge_maestro import QualityGate

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
SRC_DIR = REPO_ROOT / "src" / "evalforge_maestro"
GOLDEN_ORACLE_PATH = Path(__file__).resolve().parent / "golden" / "quality_gate_oracle.json"
FORBIDDEN_ARCHIVE_FILENAMES = frozenset({"lean-toolchain", "lakefile.toml"})
FORBIDDEN_RUNTIME_MARKERS = ("evalforge-gate-oracle", "lean-toolchain", "lakefile.toml")


def is_forbidden_sdist_member(member_name: str) -> bool:
    """Segment-exact check rejecting top-level `formal/` and Lean project files in `sdist`."""
    parts = PurePosixPath(member_name).parts
    return bool(parts) and (
        parts[0] == "formal"
        or (len(parts) >= 2 and parts[1] == "formal")
        or member_name.endswith(".lean")
        or parts[-1] in FORBIDDEN_ARCHIVE_FILENAMES
    )


def is_forbidden_wheel_member(member_name: str) -> bool:
    """Segment-exact check rejecting any `formal` path segment or Lean files in built wheels."""
    parts = PurePosixPath(member_name).parts
    return bool(parts) and (
        "formal" in parts
        or member_name.endswith(".lean")
        or parts[-1] in FORBIDDEN_ARCHIVE_FILENAMES
    )


def test_pyproject_excludes_formal_from_wheel_and_sdist_and_has_no_lean_deps() -> None:
    """Verify Hatchling packaging excludes `/formal` and dependencies declare zero Lean packages."""
    data: dict[str, Any] = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    hatch_targets = data["tool"]["hatch"]["build"]["targets"]
    assert hatch_targets["wheel"]["packages"] == ["src/evalforge_maestro"]
    sdist_exclude = hatch_targets["sdist"]["exclude"]
    assert "/formal" in sdist_exclude

    all_deps: list[str] = list(data["project"].get("dependencies", []))
    for extra_deps in data["project"].get("optional-dependencies", {}).values():
        all_deps.extend(extra_deps)
    for dep in all_deps:
        lower = dep.lower()
        assert "lean" not in lower, f"Unexpected Lean dependency in pyproject.toml: {dep!r}"
        assert "elan" not in lower, f"Unexpected Elan dependency in pyproject.toml: {dep!r}"


def test_src_package_has_zero_lean_imports_or_subprocess_references() -> None:
    """Verify `src/evalforge_maestro/` stays strictly independent of Lean, Lake, and subprocess."""
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".", 1)[0]
                    assert root_mod not in {"subprocess", "lean", "lake", "elan"}, (
                        f"Forbidden import {alias.name!r} in {py_file.relative_to(REPO_ROOT)}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                root_mod = node.module.split(".", 1)[0]
                assert root_mod not in {"subprocess", "lean", "lake", "elan"}, (
                    f"Forbidden import from {node.module!r} in {py_file.relative_to(REPO_ROOT)}"
                )
        for marker in FORBIDDEN_RUNTIME_MARKERS:
            assert marker not in source, (
                f"Forbidden Lean artifact reference {marker!r} in {py_file.relative_to(REPO_ROOT)}"
            )


def test_segment_exact_archive_filter_allows_docs_and_blocks_formal_project() -> None:
    """Ensure sdist/wheel guards reject `formal/` and `.lean` without false-positiving on docs."""
    assert not is_forbidden_sdist_member("evalforge_maestro-0.3.0/docs/formal-assurance.md")
    assert not is_forbidden_sdist_member(
        "evalforge_maestro-0.3.0/tests/conformance/test_formal_runtime_isolation.py"
    )
    assert is_forbidden_sdist_member("evalforge_maestro-0.3.0/formal/lakefile.toml")
    assert is_forbidden_sdist_member(
        "evalforge_maestro-0.3.0/formal/EvalForgeFormal/QualityGate/Decision.lean"
    )
    assert is_forbidden_sdist_member("evalforge_maestro-0.3.0/extra/probe.lean")
    assert is_forbidden_sdist_member("evalforge_maestro-0.3.0/lean-toolchain")

    assert not is_forbidden_wheel_member("evalforge_maestro/regression/gate.py")
    assert is_forbidden_wheel_member("formal/EvalForgeFormal.lean")
    assert is_forbidden_wheel_member("evalforge_maestro/formal/Decision.lean")


def test_offline_golden_artifact_and_quality_gate_work_without_lean() -> None:
    """Confirm `QualityGate` and golden oracle fixture are usable purely offline in Python."""
    assert QualityGate().policy.max_inconclusive_rate == 0.1
    golden = json.loads(GOLDEN_ORACLE_PATH.read_text(encoding="utf-8"))
    assert golden["schema_version"] == "1.0"
    assert len(golden["reason_presence_truth_table"]) == 8
