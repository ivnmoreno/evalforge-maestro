"""Pure pairwise RunRecord comparison calculator."""

from __future__ import annotations

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta
from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.regression.drift import detect_drift
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseComparison,
    CaseMetricDelta,
    ComparisonDirection,
    MetricComparison,
    MetricStatus,
    QualityGatePolicy,
    RunComparisonReport,
    RunRecord,
    TargetChangeSummary,
)


def _classify_delta(
    baseline_score: float | None,
    candidate_score: float | None,
    *,
    in_baseline: bool,
    in_candidate: bool,
) -> tuple[float | None, ComparisonDirection]:
    if not in_baseline:
        return None, ComparisonDirection.ADDED
    if not in_candidate:
        return None, ComparisonDirection.REMOVED
    if baseline_score is None or candidate_score is None:
        return None, ComparisonDirection.INCONCLUSIVE

    delta = round_delta(candidate_score - baseline_score)
    if delta > FLOAT_EPSILON:
        return delta, ComparisonDirection.IMPROVED
    if delta < -FLOAT_EPSILON:
        return delta, ComparisonDirection.REGRESSED
    return 0.0, ComparisonDirection.UNCHANGED


def _status_counts_for_summary(summary: AggregateMetricSummary | None) -> dict[MetricStatus, int]:
    if summary is None:
        return {status: 0 for status in MetricStatus}
    return {
        MetricStatus.PASS: summary.pass_count,
        MetricStatus.FAIL: summary.fail_count,
        MetricStatus.WARNING: summary.warning_count,
        MetricStatus.INCONCLUSIVE: summary.inconclusive_count,
        MetricStatus.NOT_APPLICABLE: summary.not_applicable_count,
    }


def _build_metric_comparisons(
    baseline: RunRecord,
    candidate: RunRecord,
) -> dict[str, MetricComparison]:
    comparisons: dict[str, MetricComparison] = {}
    all_metrics = sorted(set(baseline.aggregates) | set(candidate.aggregates))
    for metric_id in all_metrics:
        base_agg = baseline.aggregates.get(metric_id)
        cand_agg = candidate.aggregates.get(metric_id)
        base_score = base_agg.mean_score if base_agg is not None else None
        cand_score = cand_agg.mean_score if cand_agg is not None else None
        delta, direction = _classify_delta(
            base_score,
            cand_score,
            in_baseline=base_agg is not None,
            in_candidate=cand_agg is not None,
        )
        base_counts = _status_counts_for_summary(base_agg)
        cand_counts = _status_counts_for_summary(cand_agg)
        status_deltas = {
            status: cand_counts[status] - base_counts[status] for status in MetricStatus
        }
        comparisons[metric_id] = MetricComparison(
            metric_id=metric_id,
            baseline_version=base_agg.metric_version if base_agg is not None else None,
            candidate_version=cand_agg.metric_version if cand_agg is not None else None,
            baseline_score=base_score,
            candidate_score=cand_score,
            delta=delta,
            direction=direction,
            status_count_deltas=status_deltas,
        )
    return comparisons


def _build_case_comparisons(
    baseline: RunRecord,
    candidate: RunRecord,
    policy: QualityGatePolicy,
) -> tuple[list[CaseComparison], list[str], list[str], list[str], list[str]]:
    base_by_id = {case.case_id: case for case in baseline.case_results}
    cand_by_id = {case.case_id: case for case in candidate.case_results}

    added_ids = [case.case_id for case in candidate.case_results if case.case_id not in base_by_id]
    removed_ids = [case.case_id for case in baseline.case_results if case.case_id not in cand_by_id]

    case_comparisons: list[CaseComparison] = []
    regressed_ids: list[str] = []
    mandatory_regressed_ids: list[str] = []

    for base_case in baseline.case_results:
        cand_case = cand_by_id.get(base_case.case_id)
        if cand_case is None:
            continue

        mandatory = base_case.mandatory or cand_case.mandatory
        error_introduced = (not base_case.execution.errors) and bool(cand_case.execution.errors)
        error_resolved = bool(base_case.execution.errors) and (not cand_case.execution.errors)

        metric_deltas: dict[str, CaseMetricDelta] = {}
        severe_mandatory_drop = False
        for metric_id in sorted(set(base_case.metrics) | set(cand_case.metrics)):
            base_res = base_case.metrics.get(metric_id)
            cand_res = cand_case.metrics.get(metric_id)
            base_score = base_res.score if base_res is not None else None
            cand_score = cand_res.score if cand_res is not None else None
            base_status = base_res.status if base_res is not None else None
            cand_status = cand_res.status if cand_res is not None else None
            delta, direction = _classify_delta(
                base_score,
                cand_score,
                in_baseline=base_res is not None,
                in_candidate=cand_res is not None,
            )
            status_degraded = base_status == MetricStatus.PASS and cand_status == MetricStatus.FAIL
            score_dropped = delta is not None and delta < -FLOAT_EPSILON
            metric_regressed = status_degraded or score_dropped
            allowed_drop = policy.max_metric_regression_drops.get(
                metric_id, policy.max_regression_drop
            )
            if (
                status_degraded
                or cand_status == MetricStatus.FAIL
                or (delta is not None and -delta > allowed_drop + FLOAT_EPSILON)
            ):
                severe_mandatory_drop = True
            metric_deltas[metric_id] = CaseMetricDelta(
                metric_id=metric_id,
                baseline_score=base_score,
                candidate_score=cand_score,
                delta=delta,
                baseline_status=base_status,
                candidate_status=cand_status,
                regressed=metric_regressed,
                direction=direction,
            )

        case_regressed = error_introduced or any(md.regressed for md in metric_deltas.values())
        mandatory_regressed = mandatory and (error_introduced or severe_mandatory_drop)
        if case_regressed:
            regressed_ids.append(base_case.case_id)
        if mandatory_regressed:
            mandatory_regressed_ids.append(base_case.case_id)

        case_comparisons.append(
            CaseComparison(
                case_id=base_case.case_id,
                mandatory=mandatory,
                regressed=case_regressed,
                mandatory_regressed=mandatory_regressed,
                error_introduced=error_introduced,
                error_resolved=error_resolved,
                metrics=metric_deltas,
            )
        )

    return case_comparisons, added_ids, removed_ids, regressed_ids, mandatory_regressed_ids


def compare_runs(
    baseline: RunRecord,
    candidate: RunRecord,
    *,
    baseline_name: str | None = None,
    policy: QualityGatePolicy | None = None,
) -> RunComparisonReport:
    """Compute signed 6-decimal aggregate and per-case deltas, contextual target changes,
    drift warnings, and anomaly flags between two RunRecord artifacts.

    To compare a candidate run against a named pinned baseline without filesystem I/O here,
    resolve the baseline via `store.load_baseline_run(name)` and pass `baseline_name=name`.
    """
    active_policy = policy or QualityGatePolicy()
    target_changes = TargetChangeSummary(
        system_version_changed=baseline.system_version != candidate.system_version,
        baseline_system_version=baseline.system_version,
        candidate_system_version=candidate.system_version,
        model_id_changed=baseline.model_id != candidate.model_id,
        baseline_model_id=baseline.model_id,
        candidate_model_id=candidate.model_id,
        config_fingerprint_changed=baseline.config_fingerprint != candidate.config_fingerprint,
        baseline_config_fingerprint=baseline.config_fingerprint,
        candidate_config_fingerprint=candidate.config_fingerprint,
    )
    metric_comparisons = _build_metric_comparisons(baseline, candidate)
    (
        case_comparisons,
        added_case_ids,
        removed_case_ids,
        regressed_case_ids,
        mandatory_regressed_case_ids,
    ) = _build_case_comparisons(baseline, candidate, active_policy)
    drift_warnings = detect_drift(baseline, candidate)

    report = RunComparisonReport(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        baseline_name=baseline_name,
        target_changes=target_changes,
        metric_comparisons=metric_comparisons,
        case_comparisons=case_comparisons,
        matched_case_count=len(case_comparisons),
        added_case_ids=added_case_ids,
        removed_case_ids=removed_case_ids,
        regressed_case_ids=regressed_case_ids,
        mandatory_regressed_case_ids=mandatory_regressed_case_ids,
        drift_warnings=drift_warnings,
        anomalies=[],
    )
    anomalies = detect_anomalies(candidate, comparison=report, policy=active_policy)
    return report.model_copy(update={"anomalies": anomalies})
