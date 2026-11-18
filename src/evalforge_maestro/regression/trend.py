"""Pure chronological sliding window OLS trend and within-window drift analyzer."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import timezone

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta, round_score
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.drift import detect_window_drift
from evalforge_maestro.types import (
    MetricTrendSummary,
    RunManifestEntry,
    RunRecord,
    TrendDataPoint,
    TrendDirection,
    TrendReport,
)


def _extract_scores(entry: RunRecord | RunManifestEntry) -> dict[str, float | None]:
    if isinstance(entry, RunRecord):
        return {metric_id: agg.mean_score for metric_id, agg in entry.aggregates.items()}
    return dict(entry.aggregate_scores)


def _compute_ols_slope(scores: Sequence[float]) -> float:
    m = len(scores)
    x_mean = (m - 1) / 2.0
    y_mean = sum(scores) / m
    denom = m * (m * m - 1) / 12.0
    num = sum((idx - x_mean) * (score - y_mean) for idx, score in enumerate(scores))
    return round_delta(num / denom)


def _summarize_metric_trend(
    metric_id: str,
    window_runs: Sequence[RunRecord | RunManifestEntry],
    slope_threshold: float,
) -> MetricTrendSummary:
    points: list[TrendDataPoint] = []
    valid_scores: list[float] = []

    for idx, entry in enumerate(window_runs):
        score_map = _extract_scores(entry)
        score = score_map.get(metric_id)
        if score is not None:
            valid_scores.append(score)
        points.append(
            TrendDataPoint(
                run_id=entry.run_id,
                timestamp=entry.timestamp,
                index=idx,
                score=score,
                metric_version=entry.metric_versions.get(metric_id),
                dataset_fingerprint=entry.dataset_fingerprint,
                judge_config_fingerprint=entry.judge_config_fingerprint,
            )
        )

    valid_count = len(valid_scores)
    missing_count = len(window_runs) - valid_count

    first_score = round_score(valid_scores[0]) if valid_count >= 1 else None
    last_score = round_score(valid_scores[-1]) if valid_count >= 1 else None
    min_score = round_score(min(valid_scores)) if valid_count >= 1 else None
    max_score = round_score(max(valid_scores)) if valid_count >= 1 else None
    mean_score = round_score(sum(valid_scores) / valid_count) if valid_count >= 1 else None

    if valid_count < 2:
        return MetricTrendSummary(
            metric_id=metric_id,
            window_runs=len(window_runs),
            valid_points=valid_count,
            missing_points=missing_count,
            slope=None,
            direction=TrendDirection.INSUFFICIENT_DATA,
            first_score=first_score,
            last_score=last_score,
            min_score=min_score,
            max_score=max_score,
            mean_score=mean_score,
            points=points,
            explanation=(
                f"Metric {metric_id!r} has {valid_count} valid point(s) in window "
                f"(minimum 2 required for linear trend estimation)."
            ),
        )

    slope = _compute_ols_slope(valid_scores)
    if slope < -slope_threshold - FLOAT_EPSILON:
        direction = TrendDirection.DEGRADING
    elif slope > slope_threshold + FLOAT_EPSILON:
        direction = TrendDirection.IMPROVING
    else:
        direction = TrendDirection.STABLE

    return MetricTrendSummary(
        metric_id=metric_id,
        window_runs=len(window_runs),
        valid_points=valid_count,
        missing_points=missing_count,
        slope=slope,
        direction=direction,
        first_score=first_score,
        last_score=last_score,
        min_score=min_score,
        max_score=max_score,
        mean_score=mean_score,
        points=points,
        explanation=(
            f"Metric {metric_id!r} OLS slope across {valid_count} valid run(s) is "
            f"{slope:+.6f}/run ({direction.value}; threshold=+/-{slope_threshold})."
        ),
    )


def analyze_trend(
    runs: Sequence[RunRecord | RunManifestEntry],
    *,
    window: int = 5,
    dataset_id: str | None = None,
    all_datasets: bool = False,
    model_id: str | None = None,
    metric_ids: Sequence[str] | None = None,
    slope_threshold: float = 0.01,
) -> TrendReport:
    """Analyze OLS linear trend slopes across up to the latest `window` chronological runs.

    Unfiltered queries default to the most recent run's `dataset_id` unless
    `all_datasets=True` or an explicit `dataset_id` is passed. Adjacent chronological pairs
    within the selected window are inspected for provenance drift.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 2:
        raise ConfigurationError(f"Trend window must be an integer >= 2, got {window!r}")
    if (
        isinstance(slope_threshold, bool)
        or not isinstance(slope_threshold, (int, float))
        or not math.isfinite(slope_threshold)
        or slope_threshold <= 0.0
        or slope_threshold > 1.0
    ):
        raise ConfigurationError(
            f"Trend slope_threshold must be within (0.0, 1.0], got {slope_threshold!r}"
        )

    sorted_runs = sorted(
        runs,
        key=lambda item: (item.timestamp.astimezone(timezone.utc), item.run_id),
    )

    if dataset_id is not None:
        effective_dataset: str | None = dataset_id
        scoped_runs = [item for item in sorted_runs if item.dataset_id == dataset_id]
    elif not all_datasets and sorted_runs:
        effective_dataset = sorted_runs[-1].dataset_id
        scoped_runs = [item for item in sorted_runs if item.dataset_id == effective_dataset]
    else:
        effective_dataset = None
        scoped_runs = sorted_runs

    if model_id is not None:
        scoped_runs = [item for item in scoped_runs if item.model_id == model_id]

    window_runs = scoped_runs[-window:]
    resolved_metric_ids = (
        list(dict.fromkeys(metric_ids))
        if metric_ids is not None
        else sorted(
            {
                m_id
                for item in window_runs
                for m_id in (*item.metric_versions.keys(), *_extract_scores(item).keys())
            }
        )
    )

    metrics = {
        metric_id: _summarize_metric_trend(metric_id, window_runs, slope_threshold)
        for metric_id in resolved_metric_ids
    }
    drift_warnings = detect_window_drift(window_runs)

    return TrendReport(
        window=window,
        dataset_id_filter=effective_dataset,
        model_id_filter=model_id,
        inspected_run_ids=[item.run_id for item in window_runs],
        slope_threshold=slope_threshold,
        metrics=metrics,
        drift_warnings=drift_warnings,
    )
