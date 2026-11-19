"""Integration tests verifying examples/ci/ workflow templates in offline mode."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from evalforge_maestro.types import (
    ConfigValidationPayload,
    GateDecision,
    MetricStatus,
    ReportDocument,
)


def test_examples_ci_template_executes_end_to_end(tmp_path: Path) -> None:
    repo_ci_dir = Path("examples/ci")
    workflow_text = (repo_ci_dir / "evalforge-ci.yml").read_text(encoding="utf-8")
    assert "evalforge-maestro config validate" in workflow_text
    assert "evalforge-maestro run" in workflow_text
    assert "--mock" in workflow_text
    assert "--local-only" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text

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
