"""Unit tests for pairwise RunRecord comparison and provenance drift detection."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from evalforge_maestro.regression.compare import compare_runs
from evalforge_maestro.regression.drift import detect_drift, detect_window_drift
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    CaseMetricDelta,
    ComparisonDirection,
    DriftCategory,
    ExecutionResult,
    MetricComparison,
    MetricResult,
    MetricStatus,
    RunComparisonReport,
    RunManifestEntry,
    RunRecord,
)


def _make_run(
    run_id: str,
    *,
    dataset_fp: str = "a" * 64,
    system_version: str | None = "sys-1",
    model_id: str | None = "model-1",
    config_fp: str | None = "b" * 64,
    judge_fp: str | None = None,
    dataset_capped: bool = False,
    cases: list[tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]]],
    agg_overrides: dict[str, tuple[str, float | None]] | None = None,
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
        mean_val = sum(scores) / len(scores) if scores else None
        if agg_overrides and metric_id in agg_overrides:
            version, mean_val = agg_overrides[metric_id]
        aggregates[metric_id] = AggregateMetricSummary(
            metric_id=metric_id,
            metric_version=version,
            mean_score=mean_val,
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
        dataset_fingerprint=dataset_fp,
        evaluated_case_count=len(case_records),
        dataset_capped=dataset_capped,
        system_version=system_version,
        model_id=model_id,
        config_fingerprint=config_fp,
        judge_config_fingerprint=judge_fp,
        metric_versions=metric_versions,
        aggregates=aggregates,
        status_counts=status_counts,
        mandatory_failed_case_ids=mandatory_failed,
        has_mandatory_failures=bool(mandatory_failed),
        case_results=case_records,
    )


def test_pairwise_comparison_deltas_directions_case_transitions_and_target_isolation() -> None:
    baseline = _make_run(
        "base-1",
        cases=[
            (
                "c1",
                True,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.5, MetricStatus.PASS, "1.0.0"),
                    "removed_m": (0.8, MetricStatus.PASS, "1.0.0"),
                    "na_m": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                ["transient base err"],
            ),
            (
                "c2",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.6, MetricStatus.PASS, "1.0.0"),
                    "removed_m": (0.8, MetricStatus.PASS, "1.0.0"),
                    "na_m": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                [],
            ),
            (
                "c-removed",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
        ],
    )
    candidate = _make_run(
        "cand-2",
        system_version="sys-2",
        model_id="model-2",
        config_fp="e" * 64,
        cases=[
            (
                "c1",
                True,
                {
                    "exact_match": (0.0, MetricStatus.FAIL, "1.0.0"),
                    "recall_at_k": (0.9, MetricStatus.PASS, "1.0.0"),
                    "added_m": (1.0, MetricStatus.PASS, "1.0.0"),
                    "na_m": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                [],
            ),
            (
                "c2",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.6, MetricStatus.PASS, "1.0.0"),
                    "added_m": (1.0, MetricStatus.PASS, "1.0.0"),
                    "na_m": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                ["cand new error"],
            ),
            (
                "c-added",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                [],
            ),
        ],
    )

    report = compare_runs(baseline, candidate, baseline_name="default")
    assert report.baseline_run_id == "base-1"
    assert report.candidate_run_id == "cand-2"
    assert report.baseline_name == "default"
    assert report.matched_case_count == 2
    assert report.added_case_ids == ["c-added"]
    assert report.removed_case_ids == ["c-removed"]
    assert report.regressed_case_ids == ["c1", "c2"]
    assert report.mandatory_regressed_case_ids == ["c1"]

    # Contextual target changes populated cleanly
    assert report.target_changes.system_version_changed is True
    assert report.target_changes.model_id_changed is True
    assert report.target_changes.config_fingerprint_changed is True

    em = report.metric_comparisons["exact_match"]
    assert em.direction == ComparisonDirection.REGRESSED
    assert em.delta == -0.333333
    rec = report.metric_comparisons["recall_at_k"]
    assert rec.direction == ComparisonDirection.IMPROVED
    assert rec.delta == 0.2
    assert report.metric_comparisons["added_m"].direction == ComparisonDirection.ADDED
    assert report.metric_comparisons["added_m"].delta is None
    assert report.metric_comparisons["removed_m"].direction == ComparisonDirection.REMOVED
    assert report.metric_comparisons["removed_m"].delta is None
    assert report.metric_comparisons["na_m"].direction == ComparisonDirection.INCONCLUSIVE
    assert report.metric_comparisons["na_m"].delta is None

    c1_cmp = report.case_comparisons[0]
    assert c1_cmp.error_resolved is True
    assert c1_cmp.mandatory_regressed is True
    assert c1_cmp.metrics["exact_match"].baseline_status == MetricStatus.PASS
    assert c1_cmp.metrics["exact_match"].candidate_status == MetricStatus.FAIL
    assert c1_cmp.metrics["exact_match"].regressed is True
    c2_cmp = report.case_comparisons[1]
    assert c2_cmp.error_introduced is True
    assert c2_cmp.metrics["recall_at_k"].delta == 0.0
    assert math.copysign(1.0, c2_cmp.metrics["recall_at_k"].delta or 0.0) == 1.0


def test_identical_provenance_with_target_change_produces_zero_drift_warnings() -> None:
    case: tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]] = (
        "c1",
        False,
        {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")},
        [],
    )
    r1 = _make_run("r1", system_version="v1", model_id="m1", cases=[case])
    r2 = _make_run("r2", system_version="v2", model_id="m2", cases=[case])

    report = compare_runs(r1, r2)
    assert report.target_changes.model_id_changed is True
    assert report.drift_warnings == []
    assert report.metric_comparisons["exact_match"].direction == ComparisonDirection.UNCHANGED
    assert report.metric_comparisons["exact_match"].delta == 0.0
    assert math.copysign(1.0, report.metric_comparisons["exact_match"].delta or 0.0) == 1.0


def test_all_six_drift_categories_and_window_rollback_transitions() -> None:
    base = _make_run(
        "r1",
        dataset_fp="a" * 64,
        judge_fp="j" * 64,
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "m_old": (1.0, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    cand = _make_run(
        "r2",
        dataset_fp="d" * 64,
        judge_fp=None,
        dataset_capped=True,
        cases=[
            (
                "c2",
                False,
                {
                    "exact_match": (0.8, MetricStatus.PASS, "2.0.0"),
                    "m_new": (0.8, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )

    warnings = detect_drift(base, cand)
    categories = {w.category for w in warnings}
    assert categories == {
        DriftCategory.DATASET_FINGERPRINT,
        DriftCategory.METRIC_VERSION,
        DriftCategory.METRIC_SET,
        DriftCategory.JUDGE_CONFIG,
        DriftCategory.DATASET_CAPPED,
        DriftCategory.CASE_SET_MISMATCH,
    }

    # Window drift detects adjacent step transitions including rollbacks (v1 -> v2 -> v1)
    m1 = RunManifestEntry.from_run_record(base)
    m2 = RunManifestEntry.from_run_record(cand)
    m3 = RunManifestEntry.from_run_record(
        _make_run(
            "r3",
            dataset_fp="a" * 64,
            judge_fp="j" * 64,
            cases=[
                (
                    "c1",
                    False,
                    {
                        "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                        "m_old": (1.0, MetricStatus.PASS, "1.0.0"),
                    },
                    [],
                )
            ],
        )
    )
    win_drift = detect_window_drift([m1, m2, m3])
    assert any(
        w.category == DriftCategory.DATASET_FINGERPRINT
        and w.baseline_run_id == "r2"
        and w.candidate_run_id == "r3"
        for w in win_drift
    )
    assert any(
        w.category == DriftCategory.DATASET_CAPPED and w.candidate_run_id == "r2" for w in win_drift
    )


def test_comparison_model_validation_edge_cases() -> None:
    with pytest.raises(ValidationError):
        MetricComparison(metric_id="m", direction=ComparisonDirection.UNCHANGED, delta=1.5)
    with pytest.raises(ValidationError):
        MetricComparison(
            metric_id="m",
            direction=ComparisonDirection.UNCHANGED,
            status_count_deltas={MetricStatus.PASS: True},
        )
    with pytest.raises(ValidationError):
        CaseMetricDelta(metric_id=" ", direction=ComparisonDirection.UNCHANGED)
    with pytest.raises(ValidationError):
        CaseMetricDelta(metric_id="m", baseline_score=True, direction=ComparisonDirection.UNCHANGED)

    bad_args: dict[str, Any] = {
        "baseline_run_id": "r1",
        "candidate_run_id": "r2",
        "target_changes": {},
        "metric_comparisons": {},
        "case_comparisons": [],
        "matched_case_count": True,
    }
    with pytest.raises(ValidationError):
        RunComparisonReport(**bad_args)
