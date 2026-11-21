"""Unit tests for pure-stdlib statistical inference, cohort comparisons, and cohort drift."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression import build_pooled_cohort_run, compare_run_cohorts, compare_runs
from evalforge_maestro.regression.drift import detect_cohort_drift
from evalforge_maestro.regression.stats import (
    compute_one_sample_run_statistics,
    compute_paired_case_statistics,
    compute_welch_run_statistics,
    student_t_critical,
    student_t_two_tailed_p,
)
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    DriftCategory,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    SignificanceStatus,
    StatisticalMethod,
)
from evalforge_maestro.types import (
    RunRecord as EvalRunRecord,
)


def _make_run(
    run_id: str,
    case_scores: dict[str, float | None],
    *,
    metric_id: str = "exact_match",
    dataset_fp: str = "a" * 64,
    metric_version: str = "1.0.0",
    mandatory_cases: set[str] | None = None,
) -> EvalRunRecord:
    mandatory_set = mandatory_cases or set()
    records: list[CaseEvaluationRecord] = []
    valid_scores: list[float] = []
    mandatory_failed: list[str] = []
    counts = {s: 0 for s in MetricStatus}

    for cid, score in case_scores.items():
        if score is None:
            status = MetricStatus.NOT_APPLICABLE
        else:
            valid_scores.append(score)
            status = MetricStatus.PASS if score >= 0.5 else MetricStatus.FAIL
        counts[status] += 1
        is_mandatory = cid in mandatory_set
        if is_mandatory and status == MetricStatus.FAIL:
            mandatory_failed.append(cid)
        records.append(
            CaseEvaluationRecord(
                case_id=cid,
                mandatory=is_mandatory,
                execution=ExecutionResult(
                    case_id=cid,
                    input=f"prompt-{cid}",
                    output=f"out-{cid}",
                    elapsed_seconds=0.01,
                ),
                metrics={
                    metric_id: MetricResult(
                        metric_id=metric_id,
                        metric_version=metric_version,
                        score=score,
                        status=status,
                        explanation="synthetic test score",
                    )
                },
            )
        )

    mean_score = sum(valid_scores) / len(valid_scores) if valid_scores else None
    agg = AggregateMetricSummary(
        metric_id=metric_id,
        metric_version=metric_version,
        mean_score=mean_score,
        applicable_count=len(valid_scores),
        pass_count=counts[MetricStatus.PASS],
        fail_count=counts[MetricStatus.FAIL],
        warning_count=counts[MetricStatus.WARNING],
        inconclusive_count=counts[MetricStatus.INCONCLUSIVE],
        not_applicable_count=counts[MetricStatus.NOT_APPLICABLE],
    )
    return EvalRunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
        package_version="0.2.0",
        dataset_id="stat-ds",
        dataset_fingerprint=dataset_fp,
        evaluated_case_count=max(1, len(records)),
        system_version="sys-v1",
        model_id="mock-model",
        metric_versions={metric_id: metric_version},
        aggregates={metric_id: agg},
        status_counts=counts,
        mandatory_failed_case_ids=sorted(mandatory_failed),
        has_mandatory_failures=bool(mandatory_failed),
        case_results=records,
    )


def test_student_t_critical_and_p_value_accuracy() -> None:
    # Exact analytical benchmarks for Student's t critical values
    t_df1 = student_t_critical(1.0, 0.95)
    t_df2 = student_t_critical(2.0, 0.95)
    t_df10 = student_t_critical(10.0, 0.95)
    t_df100 = student_t_critical(100.0, 0.95)
    t_df5_99 = student_t_critical(5.0, 0.99)

    assert math.isclose(t_df1, 1.0 / math.tan(0.025 * math.pi), abs_tol=1e-7)
    assert math.isclose(t_df2, 0.95 * math.sqrt(2.0) / math.sqrt(1.0 - 0.95**2), abs_tol=1e-7)
    assert math.isclose(t_df10, 2.2281388519, abs_tol=1e-6)
    assert math.isclose(t_df100, 1.9839715184, abs_tol=1e-6)
    assert math.isclose(t_df5_99, 4.0321429835, abs_tol=1e-6)

    assert student_t_two_tailed_p(0.0, 5.0) == 1.0
    assert math.isclose(student_t_two_tailed_p(t_df10, 10.0), 0.05, abs_tol=1e-7)
    assert math.isclose(student_t_two_tailed_p(-t_df5_99, 5.0), 0.01, abs_tol=1e-7)


def test_paired_case_statistics_edge_cases_and_determinism() -> None:
    # Zero variance, zero delta
    same = compute_paired_case_statistics([0.8, 0.9, 0.7], [0.8, 0.9, 0.7])
    assert same.method == StatisticalMethod.PAIRED_T_CASE
    assert same.ci_low == 0.0 and same.ci_high == 0.0
    assert same.p_value == 1.0
    assert same.significance == SignificanceStatus.NOT_SIGNIFICANT
    assert same.statistically_significant is False

    # Zero variance, constant positive improvement
    pos_const = compute_paired_case_statistics([0.2, 0.3, 0.4, 0.5], [0.7, 0.8, 0.9, 1.0])
    assert pos_const.mean_delta == 0.5
    assert pos_const.ci_low == 0.5 and pos_const.ci_high == 0.5
    assert pos_const.p_value == 0.0
    assert pos_const.significance == SignificanceStatus.SIGNIFICANT_IMPROVEMENT
    assert pos_const.statistically_significant is True

    # Zero variance, constant regression
    neg_const = compute_paired_case_statistics([0.8, 0.9, 0.7], [0.5, 0.6, 0.4])
    assert neg_const.mean_delta == -0.3
    assert neg_const.ci_low == -0.3 and neg_const.ci_high == -0.3
    assert neg_const.p_value == 0.0
    assert neg_const.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert neg_const.statistically_significant is True

    # Consistent non-zero noisy regression across cases
    reg = compute_paired_case_statistics(
        [0.9, 0.85, 0.88, 0.92, 0.87],
        [0.65, 0.63, 0.64, 0.70, 0.65],
    )
    assert reg.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert reg.ci_low is not None and reg.ci_high is not None and reg.ci_high < 0.0
    assert reg.effect_size is not None and reg.effect_size < 0.0

    # Wide CI clamped within [-1.0, 1.0] for n=2 noisy sample
    wide = compute_paired_case_statistics([0.1, 0.9], [0.9, 0.1])
    assert wide.significance == SignificanceStatus.NOT_SIGNIFICANT
    assert wide.ci_low is not None and -1.0 <= wide.ci_low <= wide.ci_high <= 1.0  # type: ignore[operator]

    # Insufficient sample guards
    tiny = compute_paired_case_statistics([0.8], [0.5])
    assert tiny.significance == SignificanceStatus.INSUFFICIENT_DATA
    assert tiny.ci_low is None and tiny.p_value is None

    under_min = compute_paired_case_statistics(
        [0.8, 0.9], [0.5, 0.6], min_samples=3, excluded_pair_count=2
    )
    assert under_min.significance == SignificanceStatus.INSUFFICIENT_DATA
    assert under_min.excluded_pair_count == 2


def test_welch_and_one_sample_cohort_statistics() -> None:
    # Welch min(K, M) check (Clarification B1 fix)
    under_welch = compute_welch_run_statistics([0.8, 0.82], [0.5, 0.52], min_samples=3)
    assert under_welch.significance == SignificanceStatus.INSUFFICIENT_DATA
    assert under_welch.sample_size == 2

    # One side zero-variance, other positive variance
    mixed_var = compute_welch_run_statistics([0.9, 0.9, 0.9], [0.5, 0.52, 0.51], min_samples=2)
    assert mixed_var.method == StatisticalMethod.WELCH_T_RUN
    assert mixed_var.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert mixed_var.degrees_of_freedom == 2.0

    # Noisy overlapping run cohorts -> NOT_SIGNIFICANT
    noisy = compute_welch_run_statistics([0.5, 0.9, 0.7], [0.6, 0.8, 0.65], min_samples=2)
    assert noisy.significance == SignificanceStatus.NOT_SIGNIFICANT
    assert noisy.baseline_std is not None and noisy.candidate_std is not None

    # One-sample: 1 baseline vs 4 repeated candidates -> regression
    one_vs_many = compute_one_sample_run_statistics([0.9], [0.60, 0.62, 0.61, 0.59], min_samples=2)
    assert one_vs_many.method == StatisticalMethod.ONE_SAMPLE_T_RUN
    assert one_vs_many.sample_size == 4
    assert one_vs_many.mean_delta is not None and one_vs_many.mean_delta < 0.0
    assert one_vs_many.significance == SignificanceStatus.SIGNIFICANT_REGRESSION

    # One-sample mirrored: 4 repeated baselines vs 1 candidate -> sign stays candidate - baseline!
    many_vs_one = compute_one_sample_run_statistics([0.60, 0.62, 0.61, 0.59], [0.9], min_samples=2)
    assert many_vs_one.mean_delta is not None and many_vs_one.mean_delta > 0.0
    assert many_vs_one.significance == SignificanceStatus.SIGNIFICANT_IMPROVEMENT


def test_compare_runs_and_cohorts_and_drift() -> None:
    with pytest.raises(ConfigurationError):
        build_pooled_cohort_run([])
    with pytest.raises(ConfigurationError):
        compare_run_cohorts([], [_make_run("c1", {"q1": 1.0})])

    b1 = _make_run("b1", {"q1": 1.0, "q2": 0.9, "q3": 0.9, "extra_b": 1.0, "na": None})
    b2 = _make_run("b2", {"q1": 0.98, "q2": 0.88, "q3": 0.92, "extra_b": 0.9, "na": None})
    c1 = _make_run("c1", {"q1": 0.7, "q2": 0.6, "q3": 0.6, "extra_c": 0.4, "na": 1.0})
    c2 = _make_run(
        "c2",
        {"q1": 0.68, "q2": 0.62, "q3": 0.58, "extra_c": 0.4, "na": 1.0},
        mandatory_cases={"q1"},
    )

    single = compare_runs(b1, c1)
    assert single.cohort is None
    mc_single = single.metric_comparisons["exact_match"]
    assert mc_single.statistics is not None
    assert mc_single.statistics.method == StatisticalMethod.PAIRED_T_CASE
    assert mc_single.statistics.sample_size == 3  # q1, q2, q3 valid pairs; na/extra excluded
    assert mc_single.statistics.excluded_pair_count >= 1
    assert mc_single.case_statistics is None

    single_cohort_equiv = compare_run_cohorts([b1], [c1])
    assert single_cohort_equiv.cohort is None

    cohort_report = compare_run_cohorts(
        [b1, b2],
        [c1, c2],
        baseline_name="v1-cohort",
        policy=QualityGatePolicy(confidence_level=0.95, min_statistical_samples=2),
    )
    assert cohort_report.cohort is not None
    assert cohort_report.baseline_run_id == "b2"
    assert cohort_report.candidate_run_id == "c2"
    assert cohort_report.cohort.baseline_run_ids == ["b1", "b2"]
    assert cohort_report.cohort.candidate_run_ids == ["c1", "c2"]
    mc_cohort = cohort_report.metric_comparisons["exact_match"]
    assert mc_cohort.statistics is not None
    assert mc_cohort.statistics.method == StatisticalMethod.WELCH_T_RUN
    assert mc_cohort.statistics.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert mc_cohort.case_statistics is not None
    assert mc_cohort.case_statistics.method == StatisticalMethod.PAIRED_T_CASE

    pooled = build_pooled_cohort_run([c1, c2])
    assert pooled.run_id == "c2"
    assert pooled.aggregates["exact_match"].mean_score is not None

    # Intra-cohort drift detection
    b_drift = _make_run("b3", {"q1": 1.0}, dataset_fp="b" * 64)
    drift_warnings = detect_cohort_drift([b1, b_drift], [c1, c2])
    assert any(w.category == DriftCategory.DATASET_FINGERPRINT for w in drift_warnings)
