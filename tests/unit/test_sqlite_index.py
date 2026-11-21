"""Unit tests for SQLiteRunIndex lifecycle, recovery, filtering, SQLi safety, and parity."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evalforge_maestro.exceptions import StorageError
from evalforge_maestro.storage import LocalRunStore, SQLiteRunIndex
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    CaseQueryFilter,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RunQueryFilter,
    RunRecord,
    RunSortOrder,
)


def _sha256_tree(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".sqlite3"):
            digests[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return digests


def _make_run(
    run_id: str,
    *,
    ts: datetime,
    dataset_id: str = "ds-alpha",
    dataset_version: str | None = "1.0",
    model_id: str | None = "glm-5.3",
    system_version: str | None = "v1.0",
    exact_score: float = 1.0,
    prec_score: float = 1.0,
    mandatory_fail: bool = False,
    with_error: bool = False,
    with_anomaly: bool = False,
) -> RunRecord:
    case1_status = MetricStatus.FAIL if mandatory_fail else MetricStatus.PASS
    case1_exact = 0.0 if mandatory_fail else exact_score
    m_exact = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=case1_exact,
        status=case1_status,
        explanation=(
            "Check failed sk-live-secret-12345" if mandatory_fail else "Matched reference cleanly"
        ),
        anomaly_flags=["mandatory_case_failed"] if with_anomaly else [],
    )
    m_prec = MetricResult(
        metric_id="precision_at_k",
        metric_version="1.0.0",
        score=prec_score,
        status=MetricStatus.PASS if prec_score >= 0.5 else MetricStatus.FAIL,
        explanation="Precision computed",
    )
    exec1 = ExecutionResult(
        case_id="c-1",
        input="Q1",
        output="A1",
        elapsed_seconds=0.12,
        errors=["AdapterTimeout sk-secret-err-999"] if with_error else [],
    )
    exec2 = ExecutionResult(case_id="c-2", input="Q2", output="A2", elapsed_seconds=0.08)
    m2_exact = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=exact_score,
        status=MetricStatus.PASS if exact_score >= 0.5 else MetricStatus.FAIL,
        explanation="Case 2 matched",
    )
    m2_prec = MetricResult(
        metric_id="precision_at_k",
        metric_version="1.0.0",
        score=prec_score,
        status=MetricStatus.PASS if prec_score >= 0.5 else MetricStatus.FAIL,
        explanation="Case 2 precision",
    )
    mean_exact = round((case1_exact + exact_score) / 2.0, 6)
    status_counts: dict[MetricStatus, int] = {
        MetricStatus.PASS: 0,
        MetricStatus.FAIL: 0,
        MetricStatus.WARNING: 0,
        MetricStatus.INCONCLUSIVE: 0,
        MetricStatus.NOT_APPLICABLE: 0,
    }
    cases = [
        CaseEvaluationRecord(
            case_id="c-1",
            mandatory=True,
            execution=exec1,
            metrics={"exact_match": m_exact, "precision_at_k": m_prec},
        ),
        CaseEvaluationRecord(
            case_id="c-2",
            mandatory=False,
            execution=exec2,
            metrics={"exact_match": m2_exact, "precision_at_k": m2_prec},
        ),
    ]
    for c in cases:
        for mr in c.metrics.values():
            status_counts[mr.status] += 1

    return RunRecord(
        run_id=run_id,
        timestamp=ts,
        package_version="0.2.1",
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_fingerprint="a" * 64,
        evaluated_case_count=2,
        system_version=system_version,
        model_id=model_id,
        config_fingerprint="b" * 64,
        metric_versions={"exact_match": "1.0.0", "precision_at_k": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=mean_exact,
                applicable_count=2,
                pass_count=sum(
                    1 for c in cases if c.metrics["exact_match"].status == MetricStatus.PASS
                ),
                fail_count=sum(
                    1 for c in cases if c.metrics["exact_match"].status == MetricStatus.FAIL
                ),
            ),
            "precision_at_k": AggregateMetricSummary(
                metric_id="precision_at_k",
                metric_version="1.0.0",
                mean_score=prec_score,
                applicable_count=2,
                pass_count=2 if prec_score >= 0.5 else 0,
                fail_count=0 if prec_score >= 0.5 else 2,
            ),
        },
        status_counts=status_counts,
        mandatory_failed_case_ids=["c-1"] if mandatory_fail else [],
        has_mandatory_failures=mandatory_fail,
        case_results=cases,
    )


@pytest.mark.gate_immutability
def test_us1_sqlite_rebuild_sync_corruption_and_immutability(tmp_path: Path) -> None:
    root = tmp_path / ".evalforge"
    store = LocalRunStore(root)
    idx = SQLiteRunIndex(store)

    # Empty store diagnostics & rebuild
    empty_status = idx.status()
    assert empty_status.exists is False
    assert empty_status.in_sync is True
    assert empty_status.canonical_run_count == 0
    assert empty_status.indexed_run_count == 0

    rebuilt_empty = idx.rebuild()
    assert rebuilt_empty.exists is True
    assert rebuilt_empty.in_sync is True
    assert idx.query_runs() == []
    assert idx.query_cases() == []

    # Persist canonical runs & baseline
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    r1 = _make_run("run-01", ts=t0, exact_score=0.9, prec_score=0.8)
    r2 = _make_run(
        "run-02",
        ts=t0 + timedelta(hours=1),
        model_id="ollama/qwen",
        exact_score=0.4,
        prec_score=0.4,
        mandatory_fail=True,
        with_error=True,
        with_anomaly=True,
    )
    store.save_run(r1)
    store.save_run(r2)
    store.pin_baseline("run-01", name="main")

    pre_hashes = _sha256_tree(root)
    stale_before = idx.status()
    assert stale_before.in_sync is False
    assert stale_before.canonical_run_count == 2
    assert stale_before.pending_run_ids == ["run-01", "run-02"]

    rebuilt = idx.rebuild()
    assert rebuilt.exists is True
    assert rebuilt.corrupt is False
    assert rebuilt.in_sync is True
    assert rebuilt.canonical_run_count == 2
    assert rebuilt.indexed_run_count == 2
    assert rebuilt.baseline_count == 1
    assert not (root / "index.sqlite3-wal").exists()
    assert not (root / "index.sqlite3-shm").exists()
    if os.name == "posix":
        assert stat.S_IMODE(idx.db_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert _sha256_tree(root) == pre_hashes

    # Baseline mutation triggers baseline staleness cleanly fixed by sync()
    store.pin_baseline("run-02", name="main", overwrite=True)
    assert idx.status().in_sync is False
    synced_baseline = idx.sync()
    assert synced_baseline.in_sync is True
    main_runs = idx.query_runs(RunQueryFilter(baseline_name="main"), auto_sync=False)
    assert [r.run_id for r in main_runs] == ["run-02"]

    # Incremental catch-up for newly committed run + extra orphan runs/<id>.json file
    r3 = _make_run("run-03", ts=t0 + timedelta(hours=2), dataset_id="ds-beta")
    store.save_run(r3)
    orphan = _make_run("run-04-orphan", ts=t0 + timedelta(hours=3), dataset_id="ds-beta")
    store.run_path("run-04-orphan").write_text(orphan.model_dump_json(indent=2), encoding="utf-8")

    pending = idx.status()
    assert pending.in_sync is False
    assert set(pending.pending_run_ids) == {"run-03", "run-04-orphan"}
    synced = idx.sync()
    assert synced.in_sync is True
    assert synced.indexed_run_count == 4

    # Recovery from full DB deletion & byte-level corruption
    snapshot_runs = idx.query_runs()
    idx.db_path.unlink()
    assert idx.status().exists is False
    assert idx.rebuild().in_sync is True
    assert idx.query_runs() == snapshot_runs

    idx.db_path.write_bytes(b"corrupt-sqlite-bytes-123456")
    corrupt_stat = idx.status()
    assert corrupt_stat.exists is True
    assert corrupt_stat.corrupt is True
    assert corrupt_stat.in_sync is False
    recovered = idx.sync()
    assert recovered.corrupt is False
    assert recovered.in_sync is True
    assert idx.query_runs() == snapshot_runs

    # Corrupted canonical JSON or missing manifest-referenced run fails loudly with StorageError
    store.run_path("run-04-orphan").unlink()
    store.run_path("bad-json").write_text("{broken-json", encoding="utf-8")
    with pytest.raises(StorageError):
        idx.rebuild()

    store.run_path("bad-json").unlink()
    store.run_path("run-01").unlink()  # referenced by manifest.jsonl!
    with pytest.raises(StorageError):
        idx.rebuild()


@pytest.mark.gate_determinism
def test_us2_sqlite_queries_filters_sqli_and_canonical_parity(tmp_path: Path) -> None:
    root = tmp_path / ".evalforge"
    store = LocalRunStore(root)
    t0 = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    runs = [
        _make_run(
            "r-alpha-1",
            ts=t0,
            dataset_id="ds-alpha",
            dataset_version="1.0",
            model_id="glm-5.3",
            system_version="sys-1",
            exact_score=0.8,
            prec_score=0.9,
        ),
        _make_run(
            "r-alpha-2",
            ts=t0 + timedelta(hours=2),
            dataset_id="ds-alpha",
            dataset_version="2.0",
            model_id="glm-5.3",
            system_version="sys-2",
            exact_score=1.0,
            prec_score=0.3,
            mandatory_fail=True,
            with_error=True,
            with_anomaly=True,
        ),
        _make_run(
            "r-beta-1",
            ts=t0 + timedelta(hours=4),
            dataset_id="ds-beta",
            dataset_version="1.0",
            model_id="ollama/llama3",
            system_version="sys-1",
            exact_score=0.95,
            prec_score=0.85,
        ),
    ]
    for r in runs:
        store.save_run(r)
    # Pin TWO baselines onto the same run to ensure non-duplicating JOIN + sorted names
    store.pin_baseline("r-alpha-1", name="release-v1")
    store.pin_baseline("r-alpha-1", name="alpha-gold")

    idx = SQLiteRunIndex(store)

    # auto_sync=False fails cleanly before index exists, then succeeds read-only after rebuild()
    with pytest.raises(StorageError):
        idx.query_runs(auto_sync=False)

    idx.rebuild()
    all_desc = idx.query_runs(auto_sync=False)
    assert [r.run_id for r in all_desc] == ["r-beta-1", "r-alpha-2", "r-alpha-1"]
    assert all_desc[2].baseline_names == ["alpha-gold", "release-v1"]

    all_asc = idx.query_runs(RunQueryFilter(order_by=RunSortOrder.TIMESTAMP_ASC, limit=2, offset=1))
    assert [r.run_id for r in all_asc] == ["r-alpha-2", "r-beta-1"]

    by_baseline = idx.query_runs(RunQueryFilter(baseline_name="release-v1"))
    assert len(by_baseline) == 1
    assert by_baseline[0].run_id == "r-alpha-1"
    assert by_baseline[0].baseline_names == ["alpha-gold", "release-v1"]

    by_metric_bounds = idx.query_runs(
        RunQueryFilter(
            dataset_id="ds-alpha",
            metric_id="precision_at_k",
            min_mean_score=0.8,
            has_mandatory_failures=False,
        )
    )
    assert [r.run_id for r in by_metric_bounds] == ["r-alpha-1"]

    by_date = idx.query_runs(
        RunQueryFilter(
            since=t0 + timedelta(hours=1),
            until=t0 + timedelta(hours=3),
        )
    )
    assert [r.run_id for r in by_date] == ["r-alpha-2"]

    # Case-level failure triage & secret redaction check
    failed_mandatory = idx.query_cases(
        CaseQueryFilter(
            dataset_id="ds-alpha",
            metric_id="exact_match",
            status=MetricStatus.FAIL,
            mandatory_only=True,
            has_errors=True,
            has_anomaly_flags=True,
        )
    )
    assert len(failed_mandatory) == 1
    row = failed_mandatory[0]
    assert (row.run_id, row.case_id) == ("r-alpha-2", "c-1")
    assert "sk-live-secret-12345" not in row.explanation
    assert "[REDACTED]" in row.explanation

    # Metric history latest-N chronologically ascending
    hist = idx.metric_history("exact_match", dataset_id="ds-alpha", model_id="glm-5.3", limit=2)
    assert [h.run_id for h in hist] == ["r-alpha-1", "r-alpha-2"]
    assert hist[0].mean_score == pytest.approx(0.8)
    assert hist[1].mean_score == pytest.approx(0.5)

    # Parameterized SQLi neutralization
    sqli_runs = idx.query_runs(
        RunQueryFilter(dataset_id="ds-alpha' OR '1'='1'; DROP TABLE runs; --")
    )
    assert sqli_runs == []
    assert len(idx.query_runs()) == 3

    # Canonical parity vs LocalRunStore.load_runs()
    canonical = {r.run_id: r for r in store.load_runs()}
    for summary in all_desc:
        canon = canonical[summary.run_id]
        assert summary.dataset_fingerprint == canon.dataset_fingerprint
        assert summary.aggregate_scores == {
            mid: agg.mean_score for mid, agg in canon.aggregates.items()
        }
        assert summary.status_counts == canon.status_counts
