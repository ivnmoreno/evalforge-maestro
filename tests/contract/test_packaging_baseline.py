"""Offline contract tests pinning the Python >=3.11.5 baseline, dependency bounds, and CI matrix."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_pyproject() -> dict[str, Any]:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_pyproject_python_3115_baseline_and_tooling_targets() -> None:
    """Pin requires-python, classifiers, core deps, Ruff/Mypy targets, and sdist excludes."""
    data = _load_pyproject()
    project = data["project"]

    assert project["requires-python"] == ">=3.11.5"

    classifiers: list[str] = project["classifiers"]
    assert "Programming Language :: Python :: 3.10" not in classifiers
    for minor in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {minor}" in classifiers

    core_deps: list[str] = project["dependencies"]
    assert core_deps == ["pydantic>=2.7,<3", "jsonschema>=4.23,<5"]
    assert all("tomli" not in dep.lower() for dep in core_deps)

    opt_deps: dict[str, list[str]] = project["optional-dependencies"]
    assert "docpipe-maestro>=0.5.0" in opt_deps["docpipe-maestro"]
    assert "litellm>=1.108.0" in opt_deps["judges"]
    assert "litellm>=1.108.0" in opt_deps["embeddings"]
    assert "numpy>=1.26,<3" in opt_deps["embeddings"]
    assert "pytest>=9.0.3" in opt_deps["dev"]

    hatch_targets = data["tool"]["hatch"]["build"]["targets"]
    assert hatch_targets["wheel"]["packages"] == ["src/evalforge_maestro"]
    sdist_excludes: list[str] = hatch_targets["sdist"]["exclude"]
    assert "/formal" in sdist_excludes
    assert "/agy-logs" in sdist_excludes

    ruff_cfg = data["tool"]["ruff"]
    assert ruff_cfg["target-version"] == "py311"
    assert "UP042" in ruff_cfg["lint"]["ignore"]

    mypy_cfg = data["tool"]["mypy"]
    assert mypy_cfg["python_version"] == "3.11"
    assert mypy_cfg["strict"] is True


def test_ci_workflow_python_matrix_and_docpipe_0_5_compat_probe() -> None:
    """Verify CI matrix drops Python 3.10 and checks docpipe-maestro>=0.5.0 lazily."""
    ci_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")

    os_match = re.search(r"os:\s*\[([^\]]+)\]", ci_text)
    assert os_match is not None, "Missing cross-OS matrix definition in ci.yml"
    os_entries = [item.strip().strip("'\"") for item in os_match.group(1).split(",")]
    assert os_entries == ["ubuntu-latest", "macos-latest", "windows-latest"]

    py_match = re.search(r"python-version:\s*\[([^\]]+)\]", ci_text)
    assert py_match is not None, "Missing Python version matrix in ci.yml"
    py_versions = [item.strip().strip("'\"") for item in py_match.group(1).split(",")]
    assert "3.10" not in py_versions
    assert py_versions == ["3.11", "3.13"]

    assert 'assert "tomli" not in sys.modules' in ci_text

    docpipe_job_idx = ci_text.index("optional-docpipe-compat:")
    judges_job_idx = ci_text.index("optional-judges-compat:")
    docpipe_section = ci_text[docpipe_job_idx:judges_job_idx]

    assert "uv sync --frozen --extra dev --extra docpipe-maestro" in docpipe_section
    assert 'version("docpipe-maestro")' in docpipe_section
    assert "(0, 5, 0)" in docpipe_section
    assert 'mode="retrieve"' in docpipe_section
    assert 'mode="answer_detailed"' in docpipe_section
