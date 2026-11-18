"""Unit tests for sliding window OLS linear trend and within-window drift analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.trend import analyze_trend
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    DriftCategory,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    MetricTrendSummary,
    RunManifestEntry,
    RunRecord,
    TrendDataPoint,
    TrendDirection,
    TrendReport,
)


def _manifest(
    run_id: str,
    *,
    offset_minutes: int = 0,
    dataset_id: str = "ds-bench",
    dataset_fp: str = "a" * 64,
    model_id: str | None = "m-1",
    judge_fp: str | None = None,
    dataset_capped: bool = False,
    metric_versions: dict[str, str] | None = None,
    scores: dict[str, float | None] | None = None,
) -> RunManifestEntry:
    versions = metric_versions if metric_versions is not None else {"exact_match": "1.0.0"}
    agg_scores: dict[str, float | None] = (
        dict(scores) if scores is not None else {"exact_match": 1.0}
    )
    return RunManifestEntry(
        run_id=run_id,
        timestamp=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        + timedelta(minutes=offset_minutes),
        package_version="0.3.0",
        dataset_id=dataset_id,
        dataset_fingerprint=dataset_fp,
        evaluated_case_count=10,
        dataset_capped=dataset_capped,
        model_id=model_id,
        judge_config_fingerprint=judge_fp,
        metric_versions=versions,
        aggregate_scores=agg_scores,
        status_counts={},
    )


def test_sliding_window_ols_slopes_and_default_dataset_scoping() -> None:
    # Unordered list including another dataset ("ds-other") + newest 5 runs on "ds-bench"
    runs = [
        _manifest("r0-old", offset_minutes=0, scores={"em": 0.99}),
        _manifest("r5", offset_minutes=50, scores={"em": 0.82}),
        _manifest("r-other", offset_minutes=45, dataset_id="ds-other", scores={"em": 0.1}),
        _manifest("r2", offset_minutes=20, scores={"em": 0.88}),
        _manifest("r4", offset_minutes=40, scores={"em": 0.84}),
        _manifest("r1", offset_minutes=10, scores={"em": 0.90}),
        _manifest("r3", offset_minutes=30, scores={"em": 0.86}),
    ]
    # Note r-other is at +45m, while r5 is latest at +50m ("ds-bench")
    report = analyze_trend(runs, window=5)
    assert report.dataset_id_filter == "ds-bench"
    assert report.inspected_run_ids == ["r1", "r2", "r3", "r4", "r5"]
    em = report.metrics["em"]
    assert em.direction == TrendDirection.DEGRADING
    assert em.slope == -0.02
    assert em.first_score == 0.9
    assert em.last_score == 0.82
    assert em.min_score == 0.82
    assert em.max_score == 0.9
    assert em.mean_score == 0.86

    # Improving & stable metrics
    improving_runs = [
        _manifest(f"imp-{i}", offset_minutes=i, scores={"m": 0.7 + 0.02 * i, "s": 0.8})
        for i in range(4)
    ]
    imp_report = analyze_trend(improving_runs, window=4)
    assert imp_report.metrics["m"].direction == TrendDirection.IMPROVING
    assert imp_report.metrics["m"].slope == 0.02
    assert imp_report.metrics["s"].direction == TrendDirection.STABLE
    assert imp_report.metrics["s"].slope == 0.0

    # Cross-dataset mode includes "ds-other"; explicit dataset_id isolates it cleanly
    all_ds_report = analyze_trend(runs, window=7, all_datasets=True)
    assert all_ds_report.dataset_id_filter is None
    assert "r-other" in all_ds_report.inspected_run_ids
    other_only = analyze_trend(runs, window=5, dataset_id="ds-other")
    assert other_only.dataset_id_filter == "ds-other"
    assert other_only.inspected_run_ids == ["r-other"]
    assert other_only.metrics["em"].direction == TrendDirection.INSUFFICIENT_DATA

    # Direct RunRecord inputs are supported cleanly alongside manifest entries
    run_records = [
        RunRecord(
            run_id=f"rec-{i}",
            timestamp=datetime(2026, 11, 18, 12, i, tzinfo=timezone.utc),
            package_version="0.3.0",
            dataset_id="ds-rec",
            dataset_fingerprint="a" * 64,
            evaluated_case_count=1,
            metric_versions={"em": "1.0.0"},
            aggregates={
                "em": AggregateMetricSummary(
                    metric_id="em",
                    metric_version="1.0.0",
                    mean_score=0.9 - 0.05 * i,
                    applicable_count=1,
                    pass_count=1,
                )
            },
            status_counts={MetricStatus.PASS: 1},
            case_results=[
                CaseEvaluationRecord(
                    case_id="c1",
                    execution=ExecutionResult(
                        case_id="c1", input="q", output="a", elapsed_seconds=0.01
                    ),
                    metrics={
                        "em": MetricResult(
                            metric_id="em",
                            metric_version="1.0.0",
                            score=0.9 - 0.05 * i,
                            status=MetricStatus.PASS,
                            explanation="ok",
                        )
                    },
                )
            ],
        )
        for i in range(3)
    ]
    rec_report = analyze_trend(run_records, window=3)
    assert rec_report.metrics["em"].slope == -0.05
    assert rec_report.metrics["em"].direction == TrendDirection.DEGRADING


def test_trend_tie_breaking_gaps_insufficient_data_and_within_window_drift() -> None:
    same_ts = [
        _manifest("run-b", offset_minutes=0, model_id="m2", scores={"m": 0.6}),
        _manifest("run-a", offset_minutes=0, model_id="m1", scores={"m": 0.9}),
    ]
    tie_report = analyze_trend(same_ts, window=2)
    assert tie_report.inspected_run_ids == ["run-a", "run-b"]
    assert tie_report.metrics["m"].slope == -0.3

    filtered_model = analyze_trend(same_ts, window=2, model_id="m1")
    assert filtered_model.inspected_run_ids == ["run-a"]
    assert filtered_model.metrics["m"].valid_points == 1
    assert filtered_model.metrics["m"].slope is None
    assert filtered_model.metrics["m"].direction == TrendDirection.INSUFFICIENT_DATA

    # Empty & <2 valid numeric points with None gaps
    assert analyze_trend([], window=3).inspected_run_ids == []
    gapped = [
        _manifest("g0", offset_minutes=0, dataset_fp="a" * 64, judge_fp="j1", scores={"m": 0.8}),
        _manifest("g1", offset_minutes=1, dataset_fp="b" * 64, judge_fp="j2", scores={"m": None}),
        _manifest(
            "g2",
            offset_minutes=2,
            dataset_fp="b" * 64,
            judge_fp="j2",
            dataset_capped=True,
            scores={"m": None},
        ),
    ]
    gapped_report = analyze_trend(gapped, window=5, metric_ids=["m"])
    assert gapped_report.metrics["m"].valid_points == 1
    assert gapped_report.metrics["m"].missing_points == 2
    assert gapped_report.metrics["m"].slope is None
    assert gapped_report.metrics["m"].direction == TrendDirection.INSUFFICIENT_DATA
    drift_cats = {w.category for w in gapped_report.drift_warnings}
    assert {
        DriftCategory.DATASET_FINGERPRINT,
        DriftCategory.JUDGE_CONFIG,
        DriftCategory.DATASET_CAPPED,
    }.issubset(drift_cats)


def test_trend_validation_and_error_guards() -> None:
    with pytest.raises(ConfigurationError, match="window"):
        analyze_trend([], window=1)
    with pytest.raises(ConfigurationError, match="window"):
        analyze_trend([], window=True)
    with pytest.raises(ConfigurationError, match="slope_threshold"):
        analyze_trend([], slope_threshold=0.0)
    with pytest.raises(ConfigurationError, match="slope_threshold"):
        analyze_trend([], slope_threshold=True)

    with pytest.raises(ValidationError):
        MetricTrendSummary(
            metric_id="m",
            window_runs=2,
            valid_points=1,
            missing_points=1,
            slope=-0.1,
            direction=TrendDirection.INSUFFICIENT_DATA,
            explanation="Invalid slope with <2 valid points",
        )
    with pytest.raises(ValidationError):
        MetricTrendSummary(
            metric_id="m",
            window_runs=2,
            valid_points=1,
            missing_points=1,
            slope=None,
            direction=TrendDirection.DEGRADING,
            explanation="Invalid direction with <2 valid points",
        )
    with pytest.raises(ValidationError):
        TrendReport(window=True)
    with pytest.raises(ValidationError):
        TrendDataPoint(
            run_id="r",
            timestamp=datetime(2026, 11, 18, 12, 0),
            index=True,
            dataset_fingerprint="a" * 64,
        )
