"""Pure anti-masking anomaly and inter-metric disagreement detector."""

from __future__ import annotations

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta, round_score
from evalforge_maestro.types import (
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    MetricStatus,
    QualityGatePolicy,
    RunComparisonReport,
    RunRecord,
)


def _check_disagreements(run: RunRecord, threshold: float) -> list[AnomalyFlag]:
    flags: list[AnomalyFlag] = []

    for case in run.case_results:
        numeric_pairs = [
            (metric_id, result.score)
            for metric_id, result in sorted(case.metrics.items())
            if result.score is not None
        ]
        if len(numeric_pairs) >= 2:
            scores = [score for _, score in numeric_pairs]
            raw_spread = max(scores) - min(scores)
            if raw_spread > threshold + FLOAT_EPSILON:
                spread = round_delta(raw_spread)
                metric_ids = [metric_id for metric_id, _ in numeric_pairs]
                flags.append(
                    AnomalyFlag(
                        anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
                        severity=AnomalySeverity.WARNING,
                        scope=AnomalyScope.CASE,
                        case_id=case.case_id,
                        metric_ids=metric_ids,
                        spread=spread,
                        explanation=(
                            f"Case {case.case_id!r} sub-metrics diverged by {spread} "
                            f"(>{threshold}) across {metric_ids}."
                        ),
                    )
                )

    run_pairs = [
        (metric_id, summary.mean_score)
        for metric_id, summary in sorted(run.aggregates.items())
        if summary.mean_score is not None
    ]
    if len(run_pairs) >= 2:
        run_scores = [score for _, score in run_pairs]
        raw_run_spread = max(run_scores) - min(run_scores)
        if raw_run_spread > threshold + FLOAT_EPSILON:
            spread = round_delta(raw_run_spread)
            metric_ids = [metric_id for metric_id, _ in run_pairs]
            flags.append(
                AnomalyFlag(
                    anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
                    severity=AnomalySeverity.WARNING,
                    scope=AnomalyScope.RUN,
                    metric_ids=metric_ids,
                    spread=spread,
                    explanation=(
                        f"Run {run.run_id!r} aggregate metric means diverged by {spread} "
                        f"(>{threshold}) across {metric_ids}."
                    ),
                )
            )

    return flags


def _check_mandatory_and_masked_drops(
    run: RunRecord,
    comparison: RunComparisonReport | None,
    policy: QualityGatePolicy,
) -> list[AnomalyFlag]:
    flags: list[AnomalyFlag] = []
    case_by_id = {case.case_id: case for case in run.case_results}

    for case_id in run.mandatory_failed_case_ids:
        case = case_by_id.get(case_id)
        failed_metrics = (
            sorted(m_id for m_id, m in case.metrics.items() if m.status == MetricStatus.FAIL)
            if case is not None
            else []
        )
        flags.append(
            AnomalyFlag(
                anomaly_type=AnomalyType.MANDATORY_CASE_FAILURE,
                severity=AnomalySeverity.FAIL,
                scope=AnomalyScope.CASE,
                case_id=case_id,
                metric_ids=failed_metrics,
                explanation=(f"Mandatory case {case_id!r} failed metrics {failed_metrics}."),
            )
        )

    agg_scores = [
        summary.mean_score for summary in run.aggregates.values() if summary.mean_score is not None
    ]
    macro_mean = sum(agg_scores) / len(agg_scores) if agg_scores else None
    macro_passing = macro_mean is not None and macro_mean >= 0.5 - FLOAT_EPSILON

    if macro_passing:
        if run.has_mandatory_failures:
            flags.append(
                AnomalyFlag(
                    anomaly_type=AnomalyType.AGGREGATE_MASKED_DROP,
                    severity=AnomalySeverity.WARNING,
                    scope=AnomalyScope.RUN,
                    metric_ids=sorted(run.aggregates),
                    spread=round_delta(macro_mean) if macro_mean is not None else None,
                    explanation=(
                        f"Passing macro aggregate ({round_score(macro_mean or 0.0)}) masks "
                        f"mandatory case failures: {run.mandatory_failed_case_ids}."
                    ),
                )
            )

        for metric_id, summary in sorted(run.aggregates.items()):
            if summary.mean_score is None:
                continue
            floor = policy.min_metric_scores.get(metric_id, policy.min_score)
            if floor is not None and summary.mean_score < floor - FLOAT_EPSILON:
                flags.append(
                    AnomalyFlag(
                        anomaly_type=AnomalyType.AGGREGATE_MASKED_DROP,
                        severity=AnomalySeverity.WARNING,
                        scope=AnomalyScope.RUN,
                        metric_ids=[metric_id],
                        spread=round_delta(summary.mean_score - floor),
                        explanation=(
                            f"Passing macro aggregate masks {metric_id!r} floor breach "
                            f"({summary.mean_score} < {floor})."
                        ),
                    )
                )

    if comparison is not None:
        shared_deltas = [
            mc.delta for mc in comparison.metric_comparisons.values() if mc.delta is not None
        ]
        macro_non_regressing = (
            bool(shared_deltas) and (sum(shared_deltas) / len(shared_deltas)) >= -FLOAT_EPSILON
        )
        if macro_passing or macro_non_regressing:
            for metric_id, mc in sorted(comparison.metric_comparisons.items()):
                if mc.delta is None:
                    continue
                allowed_drop = policy.max_metric_regression_drops.get(
                    metric_id, policy.max_regression_drop
                )
                if -mc.delta > allowed_drop + FLOAT_EPSILON:
                    flags.append(
                        AnomalyFlag(
                            anomaly_type=AnomalyType.AGGREGATE_MASKED_DROP,
                            severity=AnomalySeverity.WARNING,
                            scope=AnomalyScope.RUN,
                            metric_ids=[metric_id],
                            spread=mc.delta,
                            explanation=(
                                f"Overall summary masks metric {metric_id!r} drop of "
                                f"{round_delta(-mc.delta)} exceeding limit {allowed_drop}."
                            ),
                        )
                    )

        for cc in comparison.case_comparisons:
            for metric_id, cmd in sorted(cc.metrics.items()):
                if cmd.delta is None:
                    continue
                mc_or_none = comparison.metric_comparisons.get(metric_id)
                allowed_drop = policy.max_metric_regression_drops.get(
                    metric_id, policy.max_regression_drop
                )
                metric_aggregate_healthy = mc_or_none is not None and (
                    mc_or_none.delta is None or -mc_or_none.delta <= allowed_drop + FLOAT_EPSILON
                )
                if (
                    metric_aggregate_healthy
                    and -cmd.delta >= policy.case_drop_warning_threshold - FLOAT_EPSILON
                ):
                    flags.append(
                        AnomalyFlag(
                            anomaly_type=AnomalyType.AGGREGATE_MASKED_DROP,
                            severity=AnomalySeverity.WARNING,
                            scope=AnomalyScope.CASE,
                            case_id=cc.case_id,
                            metric_ids=[metric_id],
                            spread=cmd.delta,
                            explanation=(
                                f"Passing/non-regressing aggregate for {metric_id!r} masks "
                                f"case {cc.case_id!r} drop of {round_delta(-cmd.delta)} "
                                f"(>= {policy.case_drop_warning_threshold})."
                            ),
                        )
                    )

    return flags


def detect_anomalies(
    run: RunRecord,
    *,
    comparison: RunComparisonReport | None = None,
    policy: QualityGatePolicy | None = None,
) -> list[AnomalyFlag]:
    """Detect case/run inter-metric disagreements, masked drops, mandatory failures,
    dataset capping, and inconclusive execution rates.
    """
    active_policy = policy or QualityGatePolicy()
    flags: list[AnomalyFlag] = []
    flags.extend(_check_disagreements(run, active_policy.disagreement_threshold))
    flags.extend(_check_mandatory_and_masked_drops(run, comparison, active_policy))

    if run.dataset_capped:
        flags.append(
            AnomalyFlag(
                anomaly_type=AnomalyType.DATASET_CAPPED,
                severity=AnomalySeverity.WARNING,
                scope=AnomalyScope.RUN,
                explanation=(
                    f"Run {run.run_id!r} evaluated a capped dataset subset "
                    f"({run.evaluated_case_count} cases)."
                ),
            )
        )

    inconclusive_cases = sum(
        1
        for case in run.case_results
        if case.execution.errors
        or any(m.status == MetricStatus.INCONCLUSIVE for m in case.metrics.values())
    )
    inconclusive_rate = round_score(inconclusive_cases / run.evaluated_case_count)
    if inconclusive_rate > FLOAT_EPSILON:
        flags.append(
            AnomalyFlag(
                anomaly_type=AnomalyType.INCONCLUSIVE_SPIKE,
                severity=AnomalySeverity.WARNING,
                scope=AnomalyScope.RUN,
                spread=inconclusive_rate,
                explanation=(
                    f"{inconclusive_cases}/{run.evaluated_case_count} evaluated cases "
                    f"({inconclusive_rate:.4f}) reported execution errors or INCONCLUSIVE metrics."
                ),
            )
        )

    return flags
