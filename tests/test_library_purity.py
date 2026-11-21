"""AST architectural boundary, logging purity, and cold-start lazy-import tests."""

from __future__ import annotations

import ast
import importlib.util
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
_FORBIDDEN_RAG_FRAMEWORK_PREFIXES = (
    "docpipe_maestro",
    "langchain",
    "llama_index",
)
_HEAVY_OPTIONAL_MODULES = (
    "litellm",
    "docpipe_maestro",
    "langchain",
    "llama_index",
    "numpy",
    "scipy",
    "opentelemetry",
    "opentelemetry_sdk",
    "sqlite3",
    "http.server",
    "jsonschema",
    "tomllib",
    "tomli",
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

        # CLI layer is the explicit configuration/boundary entrypoint
        if rel.startswith("cli/"):
            for mod in imports:
                assert mod not in {"dotenv", "python_dotenv"}, (
                    f"CLI module {rel} must not depend on external dotenv ({mod!r})"
                )
            if rel in {"cli/__init__.py", "cli/parser.py", "cli/logging_utils.py"}:
                for mod in imports:
                    assert mod not in {
                        "tomllib",
                        "tomli",
                        "litellm",
                        "docpipe_maestro",
                    }, f"Cold-start CLI module {rel} must not import {mod!r}"
                module_ast = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for top_node in module_ast.body:
                    top_names: list[str] = []
                    if isinstance(top_node, ast.Import):
                        top_names.extend(alias.name for alias in top_node.names)
                    elif isinstance(top_node, ast.ImportFrom) and top_node.module:
                        top_names.append(top_node.module)
                    for top_mod in top_names:
                        for forbidden_cold in (
                            "evalforge_maestro.cli.commands",
                            "evalforge_maestro.cli.targets",
                            "evalforge_maestro.cli.config",
                        ):
                            assert not top_mod.startswith(forbidden_cold), (
                                f"Cold-start CLI module {rel} must keep {top_mod!r} lazy"
                            )
            assert "print" not in calls, f"CLI module {rel} must not call print()"
            assert "basicConfig" not in calls, f"CLI module {rel} must not call basicConfig()"
            assert "StreamHandler" not in calls, f"CLI module {rel} must not attach StreamHandler"
            assert "FileHandler" not in calls, f"CLI module {rel} must not attach FileHandler"
            continue

        # Zero CLI, tomllib, or dotenv imports anywhere in library code
        for mod in imports:
            assert mod not in _FORBIDDEN_CONFIG_AND_CLI_MODULES, f"{rel} must not import {mod!r}"
            assert not mod.startswith("evalforge_maestro.cli"), (
                f"{rel} must not import CLI module {mod!r}"
            )

        # Core library modules & adapters must never import the optional HTTP service wrapper
        if not rel.startswith("service/") and rel != "__init__.py":
            for mod in imports:
                assert mod not in {
                    "http",
                    "http.server",
                    "socketserver",
                    "evalforge_maestro.service",
                } and not mod.startswith("evalforge_maestro.service."), (
                    f"Core module {rel} must not import service/server module {mod!r}"
                )

        # Optional service wrapper keeps HTTP transport lazy in server.py & limits adapter imports
        if rel.startswith("service/"):
            if rel != "service/server.py":
                for mod in imports:
                    assert mod not in {"http", "http.server", "socketserver"}, (
                        f"Service module {rel} must not import HTTP server transport ({mod!r})"
                    )
            else:
                module_ast = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for top_node in module_ast.body:
                    top_names_srv: list[str] = []
                    if isinstance(top_node, ast.Import):
                        top_names_srv.extend(alias.name for alias in top_node.names)
                    elif isinstance(top_node, ast.ImportFrom) and top_node.module:
                        top_names_srv.append(top_node.module)
                    for top_mod in top_names_srv:
                        assert top_mod not in {"http", "http.server", "socketserver"}, (
                            f"{rel} must keep HTTP server import {top_mod!r} lazy"
                        )
            for mod in imports:
                if mod in _FORBIDDEN_ADAPTER_MODULES or mod.startswith(
                    "evalforge_maestro.adapters"
                ):
                    assert mod in {
                        "evalforge_maestro.adapters.replay",
                        "evalforge_maestro.adapters.otel",
                    }, f"Service module {rel} must not import live target adapter {mod!r}"

        # Core/domain subsystems must never import adapters (only boundary entrypoints may)
        if (
            not rel.startswith("adapters/")
            and not rel.startswith("service/")
            and rel != "__init__.py"
        ):
            for mod in imports:
                assert mod not in _FORBIDDEN_ADAPTER_MODULES and not mod.startswith(
                    "evalforge_maestro.adapters"
                ), f"Library module {rel} must not import target adapters ({mod!r})"

        # Reporting subsystem imports only types, _canonical, exceptions, and stdlib
        if rel.startswith("reporting/"):
            for mod in imports:
                for forbidden_sub in (
                    "adapters",
                    "datasets",
                    "execution",
                    "metrics",
                    "judges",
                    "embeddings",
                    "regression",
                    "storage",
                ):
                    assert not mod.startswith(f"evalforge_maestro.{forbidden_sub}"), (
                        f"Reporting module {rel} must not import {mod!r}"
                    )

        # Leaf modules types.py, exceptions.py, _canonical.py, _locality.py stay domain-free
        if rel in {"types.py", "exceptions.py", "_canonical.py", "_locality.py"}:
            for mod in imports:
                for sub in (
                    "datasets",
                    "adapters",
                    "metrics",
                    "judges",
                    "embeddings",
                    "execution",
                    "storage",
                    "regression",
                    "reporting",
                ):
                    assert not mod.startswith(f"evalforge_maestro.{sub}"), (
                        f"Leaf module {rel} must not import {mod!r}"
                    )
                if rel != "_locality.py":
                    assert mod != "evalforge_maestro._locality" and not mod.startswith(
                        "evalforge_maestro._locality."
                    ), f"Leaf module {rel} must not import {mod!r}"

        # Pure computational modules (regression/, metrics/) never import I/O/adapters/judges
        if rel.startswith(("regression/", "metrics/")):
            for mod in imports:
                for forbidden_sub in (
                    "adapters",
                    "execution",
                    "storage",
                    "judges",
                    "embeddings",
                    "reporting",
                ):
                    assert not mod.startswith(f"evalforge_maestro.{forbidden_sub}"), (
                        f"Pure module {rel} must not import {mod!r}"
                    )

        # Judge subsystem imports only leaf contracts/helpers and keeps litellm lazy
        if rel.startswith("judges/"):
            for mod in imports:
                for forbidden_sub in (
                    "adapters",
                    "datasets",
                    "execution",
                    "storage",
                    "metrics",
                    "embeddings",
                    "regression",
                    "reporting",
                ):
                    assert not mod.startswith(f"evalforge_maestro.{forbidden_sub}"), (
                        f"Judge module {rel} must not import {mod!r}"
                    )
            module_ast = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for top_node in module_ast.body:
                if isinstance(top_node, ast.Import):
                    for alias in top_node.names:
                        assert not alias.name.startswith("litellm")
                elif isinstance(top_node, ast.ImportFrom) and top_node.module:
                    assert not top_node.module.startswith("litellm")

        # Embeddings subsystem keeps numpy, scipy, and litellm lazy and avoids domain leaks
        if rel.startswith("embeddings/"):
            for mod in imports:
                for forbidden_sub in (
                    "adapters",
                    "datasets",
                    "execution",
                    "storage",
                    "metrics",
                    "judges",
                    "regression",
                    "reporting",
                ):
                    assert not mod.startswith(f"evalforge_maestro.{forbidden_sub}"), (
                        f"Embeddings module {rel} must not import {mod!r}"
                    )
            module_ast = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for top_node in module_ast.body:
                if isinstance(top_node, ast.Import):
                    for alias in top_node.names:
                        assert not alias.name.startswith(("numpy", "scipy", "litellm"))
                elif isinstance(top_node, ast.ImportFrom) and top_node.module:
                    assert not top_node.module.startswith(("numpy", "scipy", "litellm"))

        # Core/domain modules must never import docpipe_maestro, langchain, or llama_index
        source_text = py_file.read_text(encoding="utf-8")
        if not rel.startswith("adapters/"):
            for mod in imports:
                for forbidden in _FORBIDDEN_RAG_FRAMEWORK_PREFIXES:
                    assert mod != forbidden and not mod.startswith(f"{forbidden}."), (
                        f"Non-adapter module {rel} must not import {mod!r}"
                    )
            for forbidden in _FORBIDDEN_RAG_FRAMEWORK_PREFIXES:
                assert forbidden not in source_text, (
                    f"Non-adapter module {rel} must not reference optional package {forbidden!r}"
                )
        elif rel == "adapters/docpipe.py":
            # Ensure adapters/docpipe.py keeps docpipe_maestro lazy (no top-level import)
            module_ast = ast.parse(source_text, filename=str(py_file))
            for top_node in module_ast.body:
                if isinstance(top_node, ast.Import):
                    for alias in top_node.names:
                        assert not alias.name.startswith("docpipe_maestro")
                elif isinstance(top_node, ast.ImportFrom) and top_node.module:
                    assert not top_node.module.startswith("docpipe_maestro")

        # Zero stdout print() or root logger mutation in library modules
        assert "print" not in calls, f"Library module {rel} must not call print()"
        assert "basicConfig" not in calls, f"Library module {rel} must not call basicConfig()"
        assert "StreamHandler" not in calls, f"Library module {rel} must not attach StreamHandler"
        assert "FileHandler" not in calls, f"Library module {rel} must not attach FileHandler"


def test_package_logger_uses_null_handler_only() -> None:
    import evalforge_maestro

    _ = evalforge_maestro
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

    # Offline mock judge + calibration execution also keeps litellm absent from sys.modules
    mock_probe = (
        "import sys; "
        "from evalforge_maestro import GroundednessMetric, HumanCalibrationSample, "
        "JudgeConfig, RetrievedChunk, calibrate_judge; "
        "m = GroundednessMetric(config=JudgeConfig(mock_mode=True, local_only=True)); "
        "s = HumanCalibrationSample(case_id='p1', input='SLA', output='99.9% SLA', "
        "retrieved_chunks=[RetrievedChunk(id='c1', text='99.9% SLA')], human_passed=True); "
        "rep = calibrate_judge(m, [s]); "
        "assert rep.exact_agreement_rate == 100.0; "
        "assert 'litellm' not in sys.modules"
    )
    proc_mock = subprocess.run(
        [sys.executable, "-c", mock_probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc_mock.returncode == 0, proc_mock.stderr or proc_mock.stdout

    # Embedding mock execution preserves litellm absence when [embeddings] is installed,
    # and fails fast with MissingExtraError when [embeddings] (numpy) is absent.
    if importlib.util.find_spec("numpy") is not None:
        emb_probe = (
            "import sys; "
            "from evalforge_maestro.embeddings import EmbeddingSimilarityMetric; "
            "from evalforge_maestro.types import EmbeddingConfig, EvaluationCase, "
            "ExecutionResult; "
            "m = EmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True)); "
            "res = m.evaluate("
            "EvaluationCase(id='e1', input='hi', reference='semantic cache'), "
            "ExecutionResult(case_id='e1', input='hi', output='semantic cache', "
            "elapsed_seconds=0.0)); "
            "assert res.score == 1.0; "
            "assert 'litellm' not in sys.modules"
        )
    else:
        emb_probe = (
            "import sys\n"
            "from evalforge_maestro.embeddings import EmbeddingSimilarityMetric\n"
            "from evalforge_maestro.exceptions import MissingExtraError\n"
            "from evalforge_maestro.types import EmbeddingConfig, EvaluationCase, "
            "ExecutionResult\n"
            "m = EmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True))\n"
            "try:\n"
            "    m.evaluate(EvaluationCase(id='e1', input='hi'), "
            "ExecutionResult(case_id='e1', input='hi', output='ok', elapsed_seconds=0.0))\n"
            "except MissingExtraError as exc:\n"
            "    assert 'embeddings' in str(exc)\n"
            "else:\n"
            "    raise AssertionError('Expected MissingExtraError without [embeddings]')\n"
            "assert 'numpy' not in sys.modules and 'litellm' not in sys.modules"
        )
    proc_emb = subprocess.run(
        [sys.executable, "-c", emb_probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc_emb.returncode == 0, proc_emb.stderr or proc_emb.stdout

    # CLI `--help` cold start (root and subcommand) must also leave heavy/config modules unloaded
    for help_argv in (
        ["evalforge-maestro", "--help"],
        ["evalforge_maestro", "--help"],
        ["evalforge-maestro", "run", "--help"],
    ):
        cli_probe = (
            "import sys; "
            "from evalforge_maestro.cli import main; "
            f"code = main({help_argv[1:]!r}); "
            "assert code == 0; "
            f"forbidden = {list(_HEAVY_OPTIONAL_MODULES)!r}; "
            "loaded = [m for m in forbidden if any(k == m or k.startswith(m + '.') "
            "for k in sys.modules)]; "
            "assert not loaded, f'Unexpected CLI --help cold-start imports: {loaded}'"
        )
        proc_cli = subprocess.run(
            [sys.executable, "-c", cli_probe],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc_cli.returncode == 0, proc_cli.stderr or proc_cli.stdout
