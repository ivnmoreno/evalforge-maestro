"""Integration tests for CLI index and query subcommands, auto-sync, recovery, and purity."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evalforge_maestro.cli import main as cli_main
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    CaseQueryPayload,
    CLIErrorPayload,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RunQueryPayload,
    RunRecord,
    SQLiteIndexStatus,
)


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    rc = cli_main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _seed_store(root: Path) -> dict[str, str]:
    store = LocalRunStore(root)
    t0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    specs = [
        ("run-a", t0, "ds-alpha", "glm-5.3", 0.9, False),
        ("run-b", t0 + timedelta(minutes=10), "ds-alpha", "glm-5.3", 0.4, True),
    ]
    for run_id, ts, ds_id, model_id, score, mand_fail in specs:
        c1 = CaseEvaluationRecord(
            case_id="c-1",
            mandatory=True,
            execution=ExecutionResult(
                case_id="c-1",
                input="What is SLA?",
                output="99.9%",
                elapsed_seconds=0.1,
            ),
            metrics={
                "exact_match": MetricResult(
                    metric_id="exact_match",
                    metric_version="1.0.0",
                    score=0.0 if mand_fail else score,
                    status=MetricStatus.FAIL if mand_fail else MetricStatus.PASS,
                    explanation="Mandatory mismatch" if mand_fail else "Matched",
                )
            },
        )
        mean = round(0.0 if mand_fail else score, 6)
        store.save_run(
            RunRecord(
                run_id=run_id,
                timestamp=ts,
                package_version="0.2.1",
                dataset_id=ds_id,
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                model_id=model_id,
                system_version="v1",
                config_fingerprint="b" * 64,
                metric_versions={"exact_match": "1.0.0"},
                aggregates={
                    "exact_match": AggregateMetricSummary(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        mean_score=mean,
                        applicable_count=1,
                        pass_count=0 if mand_fail else 1,
                        fail_count=1 if mand_fail else 0,
                    )
                },
                status_counts={
                    MetricStatus.PASS: 0 if mand_fail else 1,
                    MetricStatus.FAIL: 1 if mand_fail else 0,
                    MetricStatus.WARNING: 0,
                    MetricStatus.INCONCLUSIVE: 0,
                    MetricStatus.NOT_APPLICABLE: 0,
                },
                mandatory_failed_case_ids=["c-1"] if mand_fail else [],
                has_mandatory_failures=mand_fail,
                case_results=[c1],
            )
        )
    store.pin_baseline("run-a", name="release-v1")
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.endswith(".sqlite3")
    }


@pytest.mark.gate_determinism
@pytest.mark.gate_immutability
def test_us3_cli_index_and_query_workflows_recovery_and_cold_start(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Cold-start subprocess check on `evalforge-maestro --help`: sqlite3 must remain unloaded
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from evalforge_maestro.cli.parser import parse_and_dispatch; "
                "rc = parse_and_dispatch(['--help']); "
                "heavy = [m for m in ('sqlite3', 'opentelemetry', 'litellm', "
                "'docpipe_maestro', 'numpy', 'scipy', 'tomllib') if m in sys.modules]; "
                "assert rc == 0 and not heavy, (rc, heavy)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr

    root = tmp_path / ".evalforge"
    pre_hashes = _seed_store(root)

    # 1) index status before build -> exists=False, in_sync=False
    rc, status_out, _ = _run_cli(["index", "status", "--storage-dir", str(root), "--json"], capsys)
    assert rc == 0
    st0 = SQLiteIndexStatus.model_validate_json(status_out)
    assert st0.exists is False
    assert st0.in_sync is False
    assert st0.canonical_run_count == 2

    # 2) query --no-auto-sync before build -> exit code 2
    rc, no_sync_err, _ = _run_cli(
        ["query", "runs", "--storage-dir", str(root), "--no-auto-sync", "--json"],
        capsys,
    )
    assert rc == 2
    assert CLIErrorPayload.model_validate_json(no_sync_err).exit_code == 2

    # 3) index rebuild -> valid SQLite index, canonical files untouched
    rc, rebuild_out, _ = _run_cli(
        ["index", "rebuild", "--storage-dir", str(root), "--json"],
        capsys,
    )
    assert rc == 0
    st1 = SQLiteIndexStatus.model_validate_json(rebuild_out)
    assert st1.exists is True
    assert st1.in_sync is True
    assert st1.indexed_run_count == 2

    # 4) Corrupt SQLite DB bytes -> index sync recovers cleanly
    db_file = Path(st1.db_path)
    db_file.write_bytes(b"corrupted-header-000")
    rc, sync_out, _ = _run_cli(["index", "sync", "--storage-dir", str(root), "--json"], capsys)
    assert rc == 0
    st2 = SQLiteIndexStatus.model_validate_json(sync_out)
    assert st2.in_sync is True and st2.corrupt is False

    # 5) Delete SQLite DB -> query runs auto-syncs deterministically with filters
    db_file.unlink()
    rc, runs_out, _ = _run_cli(
        [
            "query",
            "runs",
            "--storage-dir",
            str(root),
            "--dataset-id",
            "ds-alpha",
            "--metric",
            "exact_match",
            "--min-score",
            "0.5",
            "--json",
        ],
        capsys,
    )
    assert rc == 0
    rq = RunQueryPayload.model_validate_json(runs_out)
    assert rq.total_returned == 1
    assert rq.runs[0].run_id == "run-a"
    assert rq.runs[0].baseline_names == ["release-v1"]

    # 6) query cases -> Markdown default stream & --json & --quiet
    rc, md_cases, _ = _run_cli(
        [
            "query",
            "cases",
            "--storage-dir",
            str(root),
            "--status",
            "FAIL",
            "--mandatory-only",
        ],
        capsys,
    )
    assert rc == 0
    assert "| run-b | c-1 |" in md_cases

    rc, quiet_cases, _ = _run_cli(
        ["query", "cases", "--storage-dir", str(root), "--quiet"],
        capsys,
    )
    assert rc == 0 and quiet_cases == ""

    rc, json_cases, _ = _run_cli(
        [
            "query",
            "cases",
            "--storage-dir",
            str(root),
            "--status",
            "FAIL",
            "--mandatory-only",
            "--json",
        ],
        capsys,
    )
    assert rc == 0
    cq = CaseQueryPayload.model_validate_json(json_cases)
    assert cq.total_returned == 1
    assert cq.cases[0].run_id == "run-b"

    # 7) Invalid filter combination (--min-score without --metric) -> exit code 2
    rc, bad_filter_out, _ = _run_cli(
        ["query", "runs", "--storage-dir", str(root), "--min-score", "0.5", "--json"],
        capsys,
    )
    assert rc == 2
    assert CLIErrorPayload.model_validate_json(bad_filter_out).exit_code == 2

    # Verify canonical JSON artifacts remain bit-for-bit immutable throughout all operations
    post_hashes = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.endswith(".sqlite3")
    }
    assert post_hashes == pre_hashes
