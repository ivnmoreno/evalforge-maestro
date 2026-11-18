"""Unit tests for anti-masking anomaly and inter-metric disagreement detection."""

from __future__ import annotations

from datetime import datetime, timezone

from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.regression.compare import compare_runs
from evalforge_maestro.types import (
    AggregateMetricSummary,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    CaseEvaluationRecord,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    RunRecord,
)


def _make_run(
    run_id: str,
    *,
    dataset_capped: bool = False,
    cases: list[tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]]],
) -> RunRecord:
    case_records: list[CaseEvaluationRecord] = []
    per_metric_scores: dict[str, list[float]] = {}
    per_metric_counts: dict[str, dict[MetricStatus, int]] = {}
    metric_versions: dict[str, str] = {}
    mandatory_failed: list[str] = []
    status_counts = {status: 0 for status in MetricStatus}

    for case_id, mandatory, metric_specs, errors in cases:
        metric_results: dict[str, MetricResult] = {}
        case_has_fail = False
        for metric_id, (score, status, version) in metric_specs.items():
            metric_versions[metric_id] = version
            metric_results[metric_id] = MetricResult(
                metric_id=metric_id,
                metric_version=version,
                score=score,
                status=status,
                explanation=f"{metric_id}={status.value}",
            )
            status_counts[status] += 1
            counts = per_metric_counts.setdefault(metric_id, {s: 0 for s in MetricStatus})
            counts[status] += 1
            if score is not None:
                per_metric_scores.setdefault(metric_id, []).append(score)
            if status == MetricStatus.FAIL:
                case_has_fail = True
        if mandatory and case_has_fail:
            mandatory_failed.append(case_id)
        case_records.append(
            CaseEvaluationRecord(
                case_id=case_id,
                mandatory=mandatory,
                execution=ExecutionResult(
                    case_id=case_id,
                    input=f"q-{case_id}",
                    output=None if errors else f"a-{case_id}",
                    elapsed_seconds=0.01,
                    errors=errors,
                ),
                metrics=metric_results,
            )
        )

    aggregates: dict[str, AggregateMetricSummary] = {}
    for metric_id, version in metric_versions.items():
        scores = per_metric_scores.get(metric_id, [])
        counts = per_metric_counts[metric_id]
        aggregates[metric_id] = AggregateMetricSummary(
            metric_id=metric_id,
            metric_version=version,
            mean_score=sum(scores) / len(scores) if scores else None,
            applicable_count=len(scores),
            pass_count=counts[MetricStatus.PASS],
            fail_count=counts[MetricStatus.FAIL],
            warning_count=counts[MetricStatus.WARNING],
            inconclusive_count=counts[MetricStatus.INCONCLUSIVE],
            not_applicable_count=counts[MetricStatus.NOT_APPLICABLE],
        )

    return RunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
        package_version="0.3.0",
        dataset_id="ds-1",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=len(case_records),
        dataset_capped=dataset_capped,
        metric_versions=metric_versions,
        aggregates=aggregates,
        status_counts=status_counts,
        mandatory_failed_case_ids=mandatory_failed,
        has_mandatory_failures=bool(mandatory_failed),
        case_results=case_records,
    )


def test_disagreement_threshold_precision_at_0_3_boundary() -> None:
    # Exact 0.3 divergence (0.8 - 0.5 == 0.30000000000000004 in IEEE 754) must NOT trigger
    run_exact = _make_run(
        "r-exact",
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (0.8, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.5, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    assert [
        a for a in detect_anomalies(run_exact) if a.anomaly_type == AnomalyType.METRIC_DISAGREEMENT
    ] == []

    # Strictly above 0.3 (0.801 - 0.5) MUST trigger both case and run disagreement flags
    run_above = _make_run(
        "r-above",
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (0.801, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.5, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    disagreements = [
        a for a in detect_anomalies(run_above) if a.anomaly_type == AnomalyType.METRIC_DISAGREEMENT
    ]
    assert {a.scope for a in disagreements} == {AnomalyScope.CASE, AnomalyScope.RUN}
    assert all(a.severity == AnomalySeverity.WARNING for a in disagreements)
    assert all(a.spread == 0.301 for a in disagreements)


def test_masked_mandatory_failure_and_floor_breach_detection() -> None:
    run = _make_run(
        "r-mask",
        cases=[
            (
                "c-ok",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "precision_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c-crit",
                True,
                {
                    "exact_match": (0.0, MetricStatus.FAIL, "1.0.0"),
                    "precision_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
        ],
    )
    policy = QualityGatePolicy(min_metric_scores={"exact_match": 0.75})
    anomalies = detect_anomalies(run, policy=policy)
    by_type = {a.anomaly_type: a for a in anomalies}

    assert AnomalyType.MANDATORY_CASE_FAILURE in by_type
    assert by_type[AnomalyType.MANDATORY_CASE_FAILURE].severity == AnomalySeverity.FAIL
    assert by_type[AnomalyType.MANDATORY_CASE_FAILURE].case_id == "c-crit"

    masked = [a for a in anomalies if a.anomaly_type == AnomalyType.AGGREGATE_MASKED_DROP]
    assert len(masked) == 2  # mandatory mask + exact_match floor breach


def test_pairwise_masked_metric_drop_and_single_case_drop_boundary() -> None:
    base = _make_run(
        "r-base",
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (0.8, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c2",
                False,
                {
                    "exact_match": (0.8, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c3",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c4",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c5",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
        ],
    )
    # Candidate: exact_match mean drops only -0.0325 (0.92 -> 0.8875, <= 0.05) while
    # c1 drops by exactly 0.25 (0.8 -> 0.55) and c2 drops 0.24 on recall (<0.25 non-trigger).
    cand = _make_run(
        "r-cand",
        dataset_capped=True,
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (0.55, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.9, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c2",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.56, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c3",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c4",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
            (
                "c5",
                False,
                {
                    "exact_match": (None, MetricStatus.INCONCLUSIVE, "1.0.0"),
                    "recall_at_k": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                ["case error"],
            ),
        ],
    )
    report = compare_runs(base, cand)
    types = {a.anomaly_type for a in report.anomalies}
    assert AnomalyType.DATASET_CAPPED in types
    assert AnomalyType.INCONCLUSIVE_SPIKE in types

    case_masks = [
        a
        for a in report.anomalies
        if a.anomaly_type == AnomalyType.AGGREGATE_MASKED_DROP and a.scope == AnomalyScope.CASE
    ]
    assert len(case_masks) == 1
    assert case_masks[0].case_id == "c1"
    assert case_masks[0].metric_ids == ["exact_match"]

    # When one sub-metric improves (+0.20) enough to offset another metric's -0.10 drop (> 0.05)
    base_macro = _make_run(
        "rbm",
        cases=[
            (
                "c1",
                False,
                {
                    "ans": (0.8, MetricStatus.PASS, "1.0.0"),
                    "ret": (0.6, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    cand_macro = _make_run(
        "rcm",
        cases=[
            (
                "c1",
                False,
                {
                    "ans": (0.7, MetricStatus.PASS, "1.0.0"),
                    "ret": (0.9, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    macro_report = compare_runs(base_macro, cand_macro)
    assert any(
        a.anomaly_type == AnomalyType.AGGREGATE_MASKED_DROP
        and a.scope == AnomalyScope.RUN
        and a.metric_ids == ["ans"]
        for a in macro_report.anomalies
    )
