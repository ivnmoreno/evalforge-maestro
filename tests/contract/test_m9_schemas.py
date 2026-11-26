"""Contract tests pinning Feature 009 SQLite query index schemas and filters."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evalforge_maestro.types import (
    SCHEMA_VERSION,
    CaseQueryFilter,
    CaseQueryPayload,
    IndexedCaseMetricRow,
    IndexedMetricPoint,
    IndexedRunSummary,
    MetricStatus,
    RunQueryFilter,
    RunQueryPayload,
    RunSortOrder,
    SQLiteIndexStatus,
)


def test_m9_query_filter_validation_and_bounds() -> None:
    rf = RunQueryFilter(
        dataset_id="ds-1",
        metric_id="exact_match",
        min_mean_score=0.5,
        max_mean_score=0.95,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        until=datetime(2026, 12, 31, tzinfo=UTC),
        order_by=RunSortOrder.TIMESTAMP_ASC,
        limit=25,
        offset=5,
    )
    assert rf.order_by == RunSortOrder.TIMESTAMP_ASC
    assert rf.limit == 25

    with pytest.raises(ValidationError):
        RunQueryFilter(min_mean_score=0.5)  # missing metric_id

    with pytest.raises(ValidationError):
        RunQueryFilter(metric_id="exact_match", min_mean_score=0.9, max_mean_score=0.4)

    with pytest.raises(ValidationError):
        RunQueryFilter(
            since=datetime(2026, 5, 1, tzinfo=UTC),
            until=datetime(2026, 1, 1, tzinfo=UTC),
        )

    with pytest.raises(ValidationError):
        RunQueryFilter(metric_id="exact_match", min_mean_score=True)

    with pytest.raises(ValidationError):
        RunQueryFilter(metric_id="exact_match", max_mean_score=math.nan)

    with pytest.raises(ValidationError):
        RunQueryFilter(limit=True)

    with pytest.raises(ValidationError):
        RunQueryFilter(limit=0)

    cf = CaseQueryFilter(
        metric_id="precision_at_k",
        status=MetricStatus.FAIL,
        mandatory_only=True,
        min_score=0.0,
        max_score=0.8,
        limit=100,
    )
    assert cf.mandatory_only is True

    with pytest.raises(ValidationError):
        CaseQueryFilter(min_score=0.8, max_score=0.2)

    with pytest.raises(ValidationError):
        CaseQueryFilter(offset=-1)


def test_m9_result_status_and_payload_contracts() -> None:
    now = datetime(2026, 11, 21, 9, 0, 0)
    run_sum = IndexedRunSummary(
        run_id="run-001",
        timestamp=now,
        dataset_id="ds-1",
        dataset_version="v1",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=10,
        dataset_capped=False,
        system_version="sys-1",
        model_id="glm-5.3",
        config_fingerprint="b" * 64,
        has_mandatory_failures=False,
        mandatory_failed_case_ids=[],
        baseline_names=["main"],
        aggregate_scores={"exact_match": 0.9123456},
        status_counts={MetricStatus.PASS: 10},
    )
    assert run_sum.schema_version == SCHEMA_VERSION
    assert run_sum.timestamp.tzinfo == UTC
    assert run_sum.aggregate_scores["exact_match"] == pytest.approx(0.912346)

    case_row = IndexedCaseMetricRow(
        run_id="run-001",
        timestamp=now,
        dataset_id="ds-1",
        model_id="glm-5.3",
        system_version="sys-1",
        case_id="c-1",
        metric_id="exact_match",
        metric_version="1.0.0",
        status=MetricStatus.PASS,
        score=1.0,
        mandatory=True,
        elapsed_seconds=0.25,
        has_errors=False,
        anomaly_count=0,
        explanation="Exact match succeeded sk-secret-1234567890",
    )
    assert "sk-secret-1234567890" not in case_row.explanation
    assert "[REDACTED]" in case_row.explanation

    point = IndexedMetricPoint(
        metric_id="exact_match",
        run_id="run-001",
        timestamp=now,
        dataset_id="ds-1",
        model_id="glm-5.3",
        system_version="sys-1",
        mean_score=0.9123456,
        applicable_count=10,
        pass_count=9,
        fail_count=1,
    )
    assert point.mean_score == pytest.approx(0.912346)

    status = SQLiteIndexStatus(
        db_path=".evalforge/index.sqlite3",
        exists=True,
        corrupt=False,
        in_sync=True,
        index_schema_version="1",
        db_size_bytes=4096,
        canonical_run_count=1,
        indexed_run_count=1,
        baseline_count=1,
    )
    assert status.schema_version == SCHEMA_VERSION

    r_payload = RunQueryPayload(storage_dir=".evalforge", total_returned=1, runs=[run_sum])
    c_payload = CaseQueryPayload(storage_dir=".evalforge", total_returned=1, cases=[case_row])
    assert r_payload.runs[0].run_id == "run-001"
    assert c_payload.cases[0].case_id == "c-1"
