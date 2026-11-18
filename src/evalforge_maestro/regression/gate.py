"""Pure QualityGate acceptance evaluator enforcing FAIL > INCONCLUSIVE > WARNING > PASS."""

from __future__ import annotations

from evalforge_maestro._canonical import FLOAT_EPSILON, round_delta, round_score
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.types import (
    AnomalyFlag,
    AnomalyType,
    DriftWarning,
    GateDecision,
    GateRuleCheck,
    MetricComparison,
    MetricStatus,
    QualityGatePolicy,
    QualityGateResult,
    RunComparisonReport,
    RunRecord,
    TrendReport,
)

_ACTIVE_WARNING_ANOMALIES = frozenset(
    {
        AnomalyType.METRIC_DISAGREEMENT,
        AnomalyType.AGGREGATE_MASKED_DROP,
        AnomalyType.DATASET_CAPPED,
    }
)


class _RuleRecorder:
    def __init__(self) -> None:
        self.checks: list[GateRuleCheck] = []
        self.failure_reasons: list[str] = []
        self.inconclusive_reasons: list[str] = []
        self.warning_reasons: list[str] = []

    def add(
        self,
        status: GateDecision,
        rule_id: str,
        message: str,
        *,
        metric_id: str | None = None,
        observed: float | int | str | None = None,
        threshold: float | int | str | None = None,
    ) -> None:
        self.checks.append(
            GateRuleCheck(
                rule_id=rule_id,
                status=status,
                message=message,
                metric_id=metric_id,
                observed=observed,
                threshold=threshold,
            )
        )
        if status == GateDecision.FAIL:
            self.failure_reasons.append(message)
        elif status == GateDecision.INCONCLUSIVE:
            self.inconclusive_reasons.append(message)
        elif status == GateDecision.WARNING:
            self.warning_reasons.append(message)


def _evaluate_mandatory_cases(run: RunRecord, recorder: _RuleRecorder) -> None:
    if run.has_mandatory_failures:
        recorder.add(
            GateDecision.FAIL,
            "mandatory_cases",
            f"Mandatory evaluation case(s) failed: {run.mandatory_failed_case_ids}.",
            observed=len(run.mandatory_failed_case_ids),
            threshold=0,
        )
    else:
        recorder.add(
            GateDecision.PASS,
            "mandatory_cases",
            "All mandatory evaluation cases passed.",
            observed=0,
            threshold=0,
        )


def _evaluate_metric_floors(
    run: RunRecord,
    policy: QualityGatePolicy,
    recorder: _RuleRecorder,
) -> None:
    for metric_id in sorted(set(run.aggregates) | set(policy.min_metric_scores)):
        floor = policy.min_metric_scores.get(metric_id, policy.min_score)
        if floor is None:
            continue
        agg = run.aggregates.get(metric_id)
        if agg is None or agg.mean_score is None:
            if metric_id in policy.min_metric_scores or agg is None or agg.inconclusive_count > 0:
                recorder.add(
                    GateDecision.INCONCLUSIVE,
                    f"metric_floor:{metric_id}",
                    f"Metric {metric_id!r} lacks a valid numeric aggregate score for floor check.",
                    metric_id=metric_id,
                    threshold=floor,
                )
            continue
        if agg.mean_score < floor - FLOAT_EPSILON:
            recorder.add(
                GateDecision.FAIL,
                f"metric_floor:{metric_id}",
                f"Metric {metric_id!r} mean score {agg.mean_score} is below floor {floor}.",
                metric_id=metric_id,
                observed=agg.mean_score,
                threshold=floor,
            )
        else:
            recorder.add(
                GateDecision.PASS,
                f"metric_floor:{metric_id}",
                f"Metric {metric_id!r} mean score {agg.mean_score} meets floor {floor}.",
                metric_id=metric_id,
                observed=agg.mean_score,
                threshold=floor,
            )


def _evaluate_inconclusive_evidence(
    run: RunRecord,
    policy: QualityGatePolicy,
    recorder: _RuleRecorder,
) -> float:
    inconclusive_cases = sum(
        1
        for case in run.case_results
        if case.execution.errors
        or any(m.status == MetricStatus.INCONCLUSIVE for m in case.metrics.values())
    )
    inconclusive_rate = round_score(inconclusive_cases / run.evaluated_case_count)

    if not any(summary.mean_score is not None for summary in run.aggregates.values()):
        recorder.add(
            GateDecision.INCONCLUSIVE,
            "applicable_evidence",
            "Run produced zero metrics with applicable numeric evidence.",
            observed=0,
        )

    if inconclusive_rate > policy.max_inconclusive_rate + FLOAT_EPSILON:
        recorder.add(
            GateDecision.INCONCLUSIVE,
            "inconclusive_rate",
            f"Inconclusive case rate {inconclusive_rate} exceeds policy limit "
            f"{policy.max_inconclusive_rate}.",
            observed=inconclusive_rate,
            threshold=policy.max_inconclusive_rate,
        )
    elif inconclusive_rate > FLOAT_EPSILON:
        recorder.add(
            GateDecision.WARNING,
            "inconclusive_rate",
            f"Partial inconclusive case rate {inconclusive_rate} within limit "
            f"{policy.max_inconclusive_rate}.",
            observed=inconclusive_rate,
            threshold=policy.max_inconclusive_rate,
        )
    else:
        recorder.add(
            GateDecision.PASS,
            "inconclusive_rate",
            "Zero inconclusive or execution-errored cases detected.",
            observed=0.0,
            threshold=policy.max_inconclusive_rate,
        )
    return inconclusive_rate


def _evaluate_comparison(
    comparison: RunComparisonReport | None,
    policy: QualityGatePolicy,
    recorder: _RuleRecorder,
) -> None:
    if comparison is None:
        if policy.require_baseline:
            recorder.add(
                GateDecision.INCONCLUSIVE,
                "baseline_required",
                "Baseline comparison is required by policy but was not provided.",
            )
        return

    comparable: list[tuple[MetricComparison, float]] = [
        (mc, mc.delta)
        for mc in sorted(comparison.metric_comparisons.values(), key=lambda item: item.metric_id)
        if mc.delta is not None
    ]
    if not comparable:
        recorder.add(
            GateDecision.INCONCLUSIVE,
            "baseline_comparable_metrics",
            "Baseline comparison contains zero comparable numeric shared metrics.",
            observed=0,
        )

    for mc, delta in comparable:
        drop = round_delta(-delta)
        allowed = policy.max_metric_regression_drops.get(mc.metric_id, policy.max_regression_drop)
        if drop > allowed + FLOAT_EPSILON:
            recorder.add(
                GateDecision.FAIL,
                f"baseline_regression:{mc.metric_id}",
                f"Metric {mc.metric_id!r} regressed by {drop} exceeding limit {allowed}.",
                metric_id=mc.metric_id,
                observed=drop,
                threshold=allowed,
            )
        elif policy.soft_regression_warning and drop > FLOAT_EPSILON:
            recorder.add(
                GateDecision.WARNING,
                f"soft_regression:{mc.metric_id}",
                f"Metric {mc.metric_id!r} minor regression {drop} within tolerance {allowed}.",
                metric_id=mc.metric_id,
                observed=drop,
                threshold=allowed,
            )
        else:
            recorder.add(
                GateDecision.PASS,
                f"baseline_regression:{mc.metric_id}",
                f"Metric {mc.metric_id!r} delta {delta} satisfies regression limit {allowed}.",
                metric_id=mc.metric_id,
                observed=drop,
                threshold=allowed,
            )

    if policy.fail_on_mandatory_regression and comparison.mandatory_regressed_case_ids:
        recorder.add(
            GateDecision.FAIL,
            "mandatory_regression",
            f"Mandatory case(s) regressed vs. baseline: {comparison.mandatory_regressed_case_ids}.",
            observed=len(comparison.mandatory_regressed_case_ids),
            threshold=0,
        )

    if policy.max_regressed_cases is not None:
        reg_count = len(comparison.regressed_case_ids)
        if reg_count > policy.max_regressed_cases:
            recorder.add(
                GateDecision.FAIL,
                "max_regressed_cases",
                f"{reg_count} regressed case(s) exceed maximum allowed "
                f"{policy.max_regressed_cases}.",
                observed=reg_count,
                threshold=policy.max_regressed_cases,
            )
        else:
            recorder.add(
                GateDecision.PASS,
                "max_regressed_cases",
                f"{reg_count} regressed case(s) within limit {policy.max_regressed_cases}.",
                observed=reg_count,
                threshold=policy.max_regressed_cases,
            )

    if comparison.added_case_ids or comparison.removed_case_ids:
        unmatched_count = len(comparison.added_case_ids) + len(comparison.removed_case_ids)
        added_cnt = len(comparison.added_case_ids)
        removed_cnt = len(comparison.removed_case_ids)
        recorder.add(
            GateDecision.WARNING,
            "unmatched_cases",
            f"Baseline and candidate case sets differ ({added_cnt} added, {removed_cnt} removed).",
            observed=unmatched_count,
        )


def _evaluate_trend(
    trend: TrendReport | None,
    policy: QualityGatePolicy,
    recorder: _RuleRecorder,
) -> None:
    if trend is None:
        if policy.require_trend:
            recorder.add(
                GateDecision.INCONCLUSIVE,
                "trend_required",
                "Sliding window trend report is required by policy but was not provided.",
            )
        return

    if policy.require_trend and len(trend.inspected_run_ids) < policy.min_trend_runs:
        recorder.add(
            GateDecision.INCONCLUSIVE,
            "trend_history",
            f"Trend window contains {len(trend.inspected_run_ids)} run(s); "
            f"at least {policy.min_trend_runs} required.",
            observed=len(trend.inspected_run_ids),
            threshold=policy.min_trend_runs,
        )

    degrading = sorted(
        metric_id
        for metric_id, summary in trend.metrics.items()
        if summary.slope is not None
        and summary.slope < -policy.trend_slope_threshold - FLOAT_EPSILON
    )
    if degrading:
        status = GateDecision.FAIL if policy.fail_on_degrading_trend else GateDecision.WARNING
        recorder.add(
            status,
            "trend_degradation",
            f"Degrading trend slope detected for metrics {degrading} "
            f"(slope < -{policy.trend_slope_threshold}).",
            observed=len(degrading),
        )
    else:
        recorder.add(
            GateDecision.PASS,
            "trend_degradation",
            "No metrics show degrading trend beyond slope threshold.",
            observed=0,
        )


def _evaluate_drift_and_anomalies(
    drift_warnings: list[DriftWarning],
    anomalies: list[AnomalyFlag],
    policy: QualityGatePolicy,
    recorder: _RuleRecorder,
) -> None:
    if drift_warnings:
        drift_status = GateDecision.FAIL if policy.fail_on_drift else GateDecision.WARNING
        recorder.add(
            drift_status,
            "provenance_drift",
            f"{len(drift_warnings)} cross-version provenance drift warning(s) detected.",
            observed=len(drift_warnings),
        )
    else:
        recorder.add(
            GateDecision.PASS,
            "provenance_drift",
            "Zero cross-version provenance drift warnings detected.",
            observed=0,
        )

    active_anomalies = [a for a in anomalies if a.anomaly_type in _ACTIVE_WARNING_ANOMALIES]
    if active_anomalies:
        anomaly_status = GateDecision.FAIL if policy.fail_on_anomaly else GateDecision.WARNING
        recorder.add(
            anomaly_status,
            "anomalies",
            f"{len(active_anomalies)} anti-masking/coverage anomaly flag(s) detected.",
            observed=len(active_anomalies),
        )
    else:
        recorder.add(
            GateDecision.PASS,
            "anomalies",
            "Zero anti-masking or coverage anomaly flags detected.",
            observed=0,
        )


class QualityGate:
    """Pure deterministic policy evaluator enforcing FAIL > INCONCLUSIVE > WARNING > PASS."""

    def __init__(self, policy: QualityGatePolicy | None = None) -> None:
        self._policy = policy or QualityGatePolicy()

    @property
    def policy(self) -> QualityGatePolicy:
        """Return immutable acceptance policy configured on this QualityGate."""
        return self._policy

    def evaluate(
        self,
        run: RunRecord,
        *,
        comparison: RunComparisonReport | None = None,
        trend: TrendReport | None = None,
    ) -> QualityGateResult:
        """Evaluate candidate run acceptance strictly without wall-clock or I/O side effects."""
        if comparison is not None and comparison.candidate_run_id != run.run_id:
            raise ConfigurationError(
                f"Comparison candidate_run_id {comparison.candidate_run_id!r} does not match "
                f"evaluated run_id {run.run_id!r}."
            )

        recorder = _RuleRecorder()
        _evaluate_mandatory_cases(run, recorder)
        _evaluate_metric_floors(run, self._policy, recorder)
        inconclusive_rate = _evaluate_inconclusive_evidence(run, self._policy, recorder)
        _evaluate_comparison(comparison, self._policy, recorder)
        _evaluate_trend(trend, self._policy, recorder)

        drift_warnings: list[DriftWarning] = []
        if comparison is not None:
            drift_warnings.extend(comparison.drift_warnings)
        if trend is not None:
            drift_warnings.extend(trend.drift_warnings)

        anomalies = detect_anomalies(run, comparison=comparison, policy=self._policy)
        _evaluate_drift_and_anomalies(drift_warnings, anomalies, self._policy, recorder)

        if recorder.failure_reasons:
            decision = GateDecision.FAIL
        elif recorder.inconclusive_reasons:
            decision = GateDecision.INCONCLUSIVE
        elif recorder.warning_reasons:
            decision = GateDecision.WARNING
        else:
            decision = GateDecision.PASS

        return QualityGateResult(
            decision=decision,
            candidate_run_id=run.run_id,
            baseline_run_id=comparison.baseline_run_id if comparison is not None else None,
            passed=decision == GateDecision.PASS,
            blocking=decision == GateDecision.FAIL,
            inconclusive_rate=inconclusive_rate,
            checks=recorder.checks,
            failure_reasons=recorder.failure_reasons,
            inconclusive_reasons=recorder.inconclusive_reasons,
            warning_reasons=recorder.warning_reasons,
            drift_warnings=drift_warnings,
            anomalies=anomalies,
            summary=(
                f"QualityGate={decision.value} for run {run.run_id!r} "
                f"({len(recorder.failure_reasons)} failures, "
                f"{len(recorder.inconclusive_reasons)} inconclusive, "
                f"{len(recorder.warning_reasons)} warnings)."
            ),
        )
