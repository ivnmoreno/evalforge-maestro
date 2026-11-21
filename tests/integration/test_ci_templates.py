"""Integration tests verifying examples/ci/ workflow templates in offline mode."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from evalforge_maestro.types import (
    CLIResolvedConfig,
    ConfigValidationPayload,
    GateDecision,
    MetricStatus,
    ReportDocument,
    TargetType,
)


def test_examples_ci_template_executes_end_to_end(tmp_path: Path) -> None:
    repo_ci_dir = Path("examples/ci")
    workflow_text = (repo_ci_dir / "evalforge-ci.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v6" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "evalforge-maestro>=0.1.4" in workflow_text
    assert "evalforge-maestro config validate" in workflow_text
    assert "evalforge-maestro run" in workflow_text
    assert "--mock" in workflow_text
    assert "--local-only" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text

    readme_text = (repo_ci_dir / "README.md").read_text(encoding="utf-8")
    assert "evalforge.toml" in readme_text
    assert "evalforge-docpipe.toml" in readme_text
    assert "evalforge-otel.toml" in readme_text

    work_ci_dir = tmp_path / "examples" / "ci"
    work_ci_dir.mkdir(parents=True)
    for fname in (
        "evalforge.toml",
        "golden-sample.jsonl",
        "executions-sample.jsonl",
    ):
        shutil.copy2(repo_ci_dir / fname, work_ci_dir / fname)

    # Validate template configuration cleanly via console entrypoint module
    val_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['config', 'validate', '--config', "
                "'examples/ci/evalforge.toml', '--json']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert val_proc.returncode == 0, val_proc.stderr
    val_payload = ConfigValidationPayload.model_validate_json(val_proc.stdout.strip())
    assert val_payload.valid is True

    # Execute exact offline gate command documented in evalforge-ci.yml
    run_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['run', '--config', 'examples/ci/evalforge.toml', "
                "'--dataset', 'examples/ci/golden-sample.jsonl', "
                "'--executions', 'examples/ci/executions-sample.jsonl', "
                "'--mock', '--local-only', '--strict', '--json', "
                "'--json-out', 'evalforge-report.json', '--markdown-out', 'evalforge-report.md']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_proc.returncode == 0, run_proc.stderr
    doc = ReportDocument.model_validate_json(run_proc.stdout.strip())
    assert doc.gate is not None
    assert doc.gate.decision == GateDecision.PASS
    assert doc.evaluation is not None
    for case_res in doc.evaluation.case_results:
        gr = case_res.metrics["groundedness"]
        assert gr.status == MetricStatus.PASS
        assert gr.label == "pass"
        assert gr.anomaly_flags == []
    assert (tmp_path / "evalforge-report.json").is_file()
    md_text = (tmp_path / "evalforge-report.md").read_text(encoding="utf-8")
    assert "## Evaluation" in md_text
    assert "## Acceptance / Quality Gate" in md_text


def test_examples_ci_docpipe_template_validates_and_executes_end_to_end(tmp_path: Path) -> None:
    repo_ci_dir = Path("examples/ci")
    work_ci_dir = tmp_path / "examples" / "ci"
    work_ci_dir.mkdir(parents=True)
    for fname in ("evalforge-docpipe.toml", "golden-sample.jsonl"):
        shutil.copy2(repo_ci_dir / fname, work_ci_dir / fname)

    val_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['config', 'validate', '--config', "
                "'examples/ci/evalforge-docpipe.toml', '--json']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert val_proc.returncode == 0, val_proc.stderr
    val_payload = ConfigValidationPayload.model_validate_json(val_proc.stdout.strip())
    assert val_payload.valid is True

    show_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['config', 'show', '--config', "
                "'examples/ci/evalforge-docpipe.toml', '--json']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert show_proc.returncode == 0, show_proc.stderr
    resolved = CLIResolvedConfig.model_validate_json(show_proc.stdout.strip())
    assert resolved.target.target_type == TargetType.DOCPIPE
    assert resolved.target.docpipe_mode == "retrieve"
    assert resolved.target.docpipe_collection == "docs"
    assert resolved.target.docpipe_persist_dir == "./.docpipe/chroma"
    assert resolved.target.docpipe_top_k == 4
    assert resolved.target.docpipe_searcher == "fts5_hybrid"
    assert resolved.target.docpipe_rerank is False
    assert resolved.security.local_only is True

    stub_pkg_dir = tmp_path / "stub_pkg"
    (stub_pkg_dir / "docpipe_maestro").mkdir(parents=True)
    (stub_pkg_dir / "docpipe_maestro" / "__init__.py").write_text(
        "def retrieve(\n"
        "    query: str,\n"
        "    *,\n"
        "    collection: str,\n"
        "    persist_dir: str,\n"
        "    top_k: int,\n"
        "    searcher: str,\n"
        ") -> list[dict[str, object]]:\n"
        '    assert collection == "docs"\n'
        '    assert persist_dir == "./.docpipe/chroma"\n'
        "    assert top_k == 4\n"
        '    assert searcher == "fts5_hybrid"\n'
        "    q_low = query.lower()\n"
        '    if "sla" in q_low:\n'
        '        doc_id = "doc-sla"\n'
        '    elif "refund" in q_low:\n'
        '        doc_id = "doc-refund"\n'
        "    else:\n"
        '        doc_id = "doc-security"\n'
        '    return [{"id": doc_id, "text": f"context for {doc_id}", "rank": 1}]\n',
        encoding="utf-8",
    )

    child_env = dict(os.environ)
    src_dir = Path("src").resolve()
    py_parts = [str(stub_pkg_dir), str(src_dir)]
    if child_env.get("PYTHONPATH"):
        py_parts.append(child_env["PYTHONPATH"])
    child_env["PYTHONPATH"] = os.pathsep.join(py_parts)

    run_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['run', '--config', 'examples/ci/evalforge-docpipe.toml', "
                "'--strict', '--json', '--json-out', 'docpipe-report.json', "
                "'--markdown-out', 'docpipe-report.md']))"
            ),
        ],
        cwd=tmp_path,
        env=child_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_proc.returncode == 0, run_proc.stderr
    doc = ReportDocument.model_validate_json(run_proc.stdout.strip())
    assert doc.gate is not None
    assert doc.gate.decision == GateDecision.PASS
    assert doc.evaluation is not None
    assert doc.evaluation.evaluated_case_count == 3
    assert len(doc.evaluation.case_results) == 3
    for case_res in doc.evaluation.case_results:
        for metric_id in ("precision_at_k", "recall_at_k", "mrr"):
            assert case_res.metrics[metric_id].status == MetricStatus.PASS
            assert case_res.metrics[metric_id].score == 1.0
    assert (tmp_path / "docpipe-report.json").is_file()
    assert "## Acceptance / Quality Gate" in (tmp_path / "docpipe-report.md").read_text(
        encoding="utf-8"
    )


def test_examples_ci_otel_template_validates_and_executes_end_to_end(tmp_path: Path) -> None:
    repo_ci_dir = Path("examples/ci")
    work_ci_dir = tmp_path / "examples" / "ci"
    work_ci_dir.mkdir(parents=True)
    for fname in ("evalforge-otel.toml", "golden-sample.jsonl", "otel-traces-sample.json"):
        shutil.copy2(repo_ci_dir / fname, work_ci_dir / fname)

    val_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['config', 'validate', '--config', "
                "'examples/ci/evalforge-otel.toml', '--json']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert val_proc.returncode == 0, val_proc.stderr
    assert ConfigValidationPayload.model_validate_json(val_proc.stdout.strip()).valid is True

    run_proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['run', '--config', 'examples/ci/evalforge-otel.toml', "
                "'--strict', '--json', '--json-out', 'otel-report.json', "
                "'--markdown-out', 'otel-report.md']))"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run_proc.returncode == 0, run_proc.stderr
    doc = ReportDocument.model_validate_json(run_proc.stdout.strip())
    assert doc.gate is not None
    assert doc.gate.decision == GateDecision.PASS
    assert doc.evaluation is not None
    assert doc.evaluation.evaluated_case_count == 3
    for case_res in doc.evaluation.case_results:
        assert case_res.metrics["normalized_match"].status == MetricStatus.PASS
        assert case_res.metrics["precision_at_k"].score == 1.0
        assert case_res.metrics["recall_at_k"].score == 1.0
    assert (tmp_path / "otel-report.json").is_file()
    assert "## Acceptance / Quality Gate" in (tmp_path / "otel-report.md").read_text(
        encoding="utf-8"
    )
