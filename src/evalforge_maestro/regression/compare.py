"""Pure pairwise and cohort RunRecord comparison calculator."""

from __future__ import annotations

from collections.abc import Sequence

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta, round_score
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.regression.drift import detect_cohort_drift, detect_drift
from evalforge_maestro.regression.stats import (
    compute_one_sample_run_statistics,
    compute_paired_case_statistics,
    compute_welch_run_statistics,
)
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseComparison,
    CaseEvaluationRecord,
    CaseMetricDelta,
    ComparisonDirection,
    MetricComparison,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    RunCohortSummary,
    RunComparisonReport,
    RunRecord,
    StatisticalSummary,
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


def _extract_aligned_case_pairs(
    baseline: RunRecord,
    candidate: RunRecord,
    metric_id: str,
) -> tuple[list[float], list[float], int]:
    cand_by_id = {case.case_id: case for case in candidate.case_results}
    base_scores: list[float] = []
    cand_scores: list[float] = []
    excluded_count = 0
    for base_case in baseline.case_results:
        cand_case = cand_by_id.get(base_case.case_id)
        if cand_case is None:
            continue
        base_res = base_case.metrics.get(metric_id)
        cand_res = cand_case.metrics.get(metric_id)
        if (
            base_res is not None
            and base_res.score is not None
            and cand_res is not None
            and cand_res.score is not None
        ):
            base_scores.append(base_res.score)
            cand_scores.append(cand_res.score)
        elif base_res is not None or cand_res is not None:
            excluded_count += 1
    return base_scores, cand_scores, excluded_count


def _build_target_changes(baseline: RunRecord, candidate: RunRecord) -> TargetChangeSummary:
    return TargetChangeSummary(
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


def _build_metric_comparisons(
    baseline: RunRecord,
    candidate: RunRecord,
    *,
    policy: QualityGatePolicy | None = None,
) -> dict[str, MetricComparison]:
    active_policy = policy or QualityGatePolicy()
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
        statistics: StatisticalSummary | None = None
        if base_agg is not None and cand_agg is not None:
            base_pairs, cand_pairs, excluded_count = _extract_aligned_case_pairs(
                baseline, candidate, metric_id
            )
            statistics = compute_paired_case_statistics(
                base_pairs,
                cand_pairs,
                confidence_level=active_policy.confidence_level,
                min_samples=active_policy.min_statistical_samples,
                excluded_pair_count=excluded_count,
            )
        comparisons[metric_id] = MetricComparison(
            metric_id=metric_id,
            baseline_version=base_agg.metric_version if base_agg is not None else None,
            candidate_version=cand_agg.metric_version if cand_agg is not None else None,
            baseline_score=base_score,
            candidate_score=cand_score,
            delta=delta,
            direction=direction,
            status_count_deltas=status_deltas,
            statistics=statistics,
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
    target_changes = _build_target_changes(baseline, candidate)
    metric_comparisons = _build_metric_comparisons(baseline, candidate, policy=active_policy)
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


def build_pooled_cohort_run(runs: Sequence[RunRecord]) -> RunRecord:
    """Build a pooled cohort RunRecord keeping representative run_id = runs[-1].run_id."""
    if not runs:
        raise ConfigurationError("Cannot build pooled cohort run from an empty sequence of runs.")
    if len(runs) == 1:
        return runs[0]

    rep = runs[-1]
    all_metrics = sorted({metric_id for run in runs for metric_id in run.aggregates})
    pooled_aggregates: dict[str, AggregateMetricSummary] = {}
    for metric_id in all_metrics:
        aggs = [run.aggregates[metric_id] for run in runs if metric_id in run.aggregates]
        means = [agg.mean_score for agg in aggs if agg.mean_score is not None]
        pooled_mean = round_score(sum(means) / len(means)) if means else None
        version = rep.metric_versions.get(metric_id, aggs[-1].metric_version)
        pooled_aggregates[metric_id] = AggregateMetricSummary(
            metric_id=metric_id,
            metric_version=version,
            mean_score=pooled_mean,
            applicable_count=sum(agg.applicable_count for agg in aggs),
            pass_count=sum(agg.pass_count for agg in aggs),
            fail_count=sum(agg.fail_count for agg in aggs),
            warning_count=sum(agg.warning_count for agg in aggs),
            inconclusive_count=sum(agg.inconclusive_count for agg in aggs),
            not_applicable_count=sum(agg.not_applicable_count for agg in aggs),
        )

    pooled_status_counts = {
        status: sum(run.status_counts.get(status, 0) for run in runs) for status in MetricStatus
    }
    mandatory_failed = sorted({cid for run in runs for cid in run.mandatory_failed_case_ids})
    pooled_cases = [case for run in runs for case in run.case_results]

    return RunRecord(
        schema_version=rep.schema_version,
        run_id=rep.run_id,
        timestamp=rep.timestamp,
        package_version=rep.package_version,
        dataset_id=rep.dataset_id,
        dataset_version=rep.dataset_version,
        dataset_fingerprint=rep.dataset_fingerprint,
        evaluated_case_count=sum(run.evaluated_case_count for run in runs),
        dataset_capped=any(run.dataset_capped for run in runs),
        max_dataset_cases=rep.max_dataset_cases,
        system_version=rep.system_version,
        model_id=rep.model_id,
        config_fingerprint=rep.config_fingerprint,
        judge_config_fingerprint=rep.judge_config_fingerprint,
        embedding_config_fingerprint=rep.embedding_config_fingerprint,
        metric_versions=dict(rep.metric_versions),
        seed=rep.seed,
        aggregates=pooled_aggregates,
        status_counts=pooled_status_counts,
        mandatory_failed_case_ids=mandatory_failed,
        has_mandatory_failures=bool(mandatory_failed),
        case_results=pooled_cases,
    )


def _pool_case_status(statuses: set[MetricStatus]) -> MetricStatus:
    if MetricStatus.FAIL in statuses:
        return MetricStatus.FAIL
    if MetricStatus.INCONCLUSIVE in statuses:
        return MetricStatus.INCONCLUSIVE
    if MetricStatus.WARNING in statuses:
        return MetricStatus.WARNING
    if MetricStatus.PASS in statuses:
        return MetricStatus.PASS
    return MetricStatus.NOT_APPLICABLE


def _pool_cohort_cases_run(runs: Sequence[RunRecord], pooled_summary: RunRecord) -> RunRecord:
    by_case_id: dict[str, list[CaseEvaluationRecord]] = {}
    for run in runs:
        for case in run.case_results:
            by_case_id.setdefault(case.case_id, []).append(case)

    averaged_cases: list[CaseEvaluationRecord] = []
    for case_id, recs in by_case_id.items():
        mandatory = any(rec.mandatory for rec in recs)
        errors = list(dict.fromkeys(err for rec in recs for err in rec.execution.errors))
        execution = recs[-1].execution.model_copy(update={"errors": errors})
        metric_ids = sorted({m_id for rec in recs for m_id in rec.metrics})
        pooled_metrics: dict[str, MetricResult] = {}
        for metric_id in metric_ids:
            results = [rec.metrics[metric_id] for rec in recs if metric_id in rec.metrics]
            scores = [res.score for res in results if res.score is not None]
            mean_score = round_score(sum(scores) / len(scores)) if scores else None
            status = _pool_case_status({res.status for res in results})
            pooled_metrics[metric_id] = results[-1].model_copy(
                update={"score": mean_score, "status": status}
            )
        averaged_cases.append(
            CaseEvaluationRecord(
                case_id=case_id,
                mandatory=mandatory,
                execution=execution,
                metrics=pooled_metrics,
            )
        )

    return pooled_summary.model_copy(
        update={
            "evaluated_case_count": max(1, len(averaged_cases)),
            "case_results": averaged_cases,
        }
    )


def compare_run_cohorts(
    baseline_runs: Sequence[RunRecord],
    candidate_runs: Sequence[RunRecord],
    *,
    baseline_name: str | None = None,
    policy: QualityGatePolicy | None = None,
) -> RunComparisonReport:
    """Compare baseline and candidate cohorts using Welch/one-sample and paired statistics."""
    if not baseline_runs or not candidate_runs:
        raise ConfigurationError(
            "compare_run_cohorts requires at least one baseline run and one candidate run."
        )

    active_policy = policy or QualityGatePolicy()
    if len(baseline_runs) == 1 and len(candidate_runs) == 1:
        return compare_runs(
            baseline_runs[0],
            candidate_runs[0],
            baseline_name=baseline_name,
            policy=active_policy,
        )

    rep_base = baseline_runs[-1]
    rep_cand = candidate_runs[-1]
    base_pooled = build_pooled_cohort_run(baseline_runs)
    cand_pooled = build_pooled_cohort_run(candidate_runs)
    base_case_run = _pool_cohort_cases_run(baseline_runs, base_pooled)
    cand_case_run = _pool_cohort_cases_run(candidate_runs, cand_pooled)

    target_changes = _build_target_changes(rep_base, rep_cand)

    metric_comparisons: dict[str, MetricComparison] = {}
    all_metrics = sorted(set(base_pooled.aggregates) | set(cand_pooled.aggregates))
    for metric_id in all_metrics:
        base_agg = base_pooled.aggregates.get(metric_id)
        cand_agg = cand_pooled.aggregates.get(metric_id)
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

        statistics: StatisticalSummary | None = None
        case_statistics: StatisticalSummary | None = None
        if base_agg is not None and cand_agg is not None:
            base_pairs, cand_pairs, excluded_count = _extract_aligned_case_pairs(
                base_case_run, cand_case_run, metric_id
            )
            case_statistics = compute_paired_case_statistics(
                base_pairs,
                cand_pairs,
                confidence_level=active_policy.confidence_level,
                min_samples=active_policy.min_statistical_samples,
                excluded_pair_count=excluded_count,
            )
            base_run_scores: list[float] = []
            for run in baseline_runs:
                agg = run.aggregates.get(metric_id)
                if agg is not None and agg.mean_score is not None:
                    base_run_scores.append(agg.mean_score)
            cand_run_scores: list[float] = []
            for run in candidate_runs:
                agg = run.aggregates.get(metric_id)
                if agg is not None and agg.mean_score is not None:
                    cand_run_scores.append(agg.mean_score)

            k_scores = len(base_run_scores)
            m_scores = len(cand_run_scores)
            if k_scores >= 2 and m_scores >= 2:
                statistics = compute_welch_run_statistics(
                    base_run_scores,
                    cand_run_scores,
                    confidence_level=active_policy.confidence_level,
                    min_samples=active_policy.min_statistical_samples,
                )
            elif (k_scores == 1 and m_scores >= 2) or (m_scores == 1 and k_scores >= 2):
                statistics = compute_one_sample_run_statistics(
                    base_run_scores,
                    cand_run_scores,
                    confidence_level=active_policy.confidence_level,
                    min_samples=active_policy.min_statistical_samples,
                )
            elif k_scores == 1 and m_scores == 1:
                statistics = case_statistics
            else:
                statistics = compute_welch_run_statistics(
                    base_run_scores,
                    cand_run_scores,
                    confidence_level=active_policy.confidence_level,
                    min_samples=active_policy.min_statistical_samples,
                )

        metric_comparisons[metric_id] = MetricComparison(
            metric_id=metric_id,
            baseline_version=base_agg.metric_version if base_agg is not None else None,
            candidate_version=cand_agg.metric_version if cand_agg is not None else None,
            baseline_score=base_score,
            candidate_score=cand_score,
            delta=delta,
            direction=direction,
            status_count_deltas=status_deltas,
            statistics=statistics,
            case_statistics=case_statistics,
        )

    (
        case_comparisons,
        added_case_ids,
        removed_case_ids,
        regressed_case_ids,
        mandatory_regressed_case_ids,
    ) = _build_case_comparisons(base_case_run, cand_case_run, active_policy)
    drift_warnings = detect_cohort_drift(baseline_runs, candidate_runs)

    cohort = RunCohortSummary(
        baseline_run_ids=[run.run_id for run in baseline_runs],
        candidate_run_ids=[run.run_id for run in candidate_runs],
        baseline_run_count=len(baseline_runs),
        candidate_run_count=len(candidate_runs),
        baseline_names=[baseline_name] if baseline_name is not None else [],
    )
    report = RunComparisonReport(
        baseline_run_id=rep_base.run_id,
        candidate_run_id=rep_cand.run_id,
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
        cohort=cohort,
    )
    anomalies = detect_anomalies(cand_case_run, comparison=report, policy=active_policy)
    return report.model_copy(update={"anomalies": anomalies})
