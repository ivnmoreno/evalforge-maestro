"""100%-branch unit and determinism tests for QualityGate decision logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evalforge_maestro._canonical import canonical_json_bytes
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.compare import compare_run_cohorts, compare_runs
from evalforge_maestro.regression.gate import QualityGate
from evalforge_maestro.regression.trend import analyze_trend
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    DriftCategory,
    ExecutionResult,
    GateDecision,
    GateRuleCheck,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    QualityGateResult,
    RunManifestEntry,
    RunRecord,
    SignificanceStatus,
)


def _run_fixture(
    run_id: str,
    *,
    dataset_fp: str = "a" * 64,
    judge_fp: str | None = None,
    dataset_capped: bool = False,
    cases: list[tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]]],
) -> RunRecord:
    case_records: list[CaseEvaluationRecord] = []
    per_metric_scores: dict[str, list[float]] = {}
    per_metric_counts: dict[str, dict[MetricStatus, int]] = {}
    metric_versions: dict[str, str] = {}
    mandatory_failed: list[str] = []
    status_counts = {s: 0 for s in MetricStatus}

    for case_id, mandatory, spec_map, errors in cases:
        metrics: dict[str, MetricResult] = {}
        case_fail = False
        for m_id, (score, status, ver) in spec_map.items():
            metric_versions[m_id] = ver
            metrics[m_id] = MetricResult(
                metric_id=m_id,
                metric_version=ver,
                score=score,
                status=status,
                explanation=f"{m_id}={status.value}",
            )
            status_counts[status] += 1
            counts = per_metric_counts.setdefault(m_id, {s: 0 for s in MetricStatus})
            counts[status] += 1
            if score is not None:
                per_metric_scores.setdefault(m_id, []).append(score)
            if status == MetricStatus.FAIL:
                case_fail = True
        if mandatory and case_fail:
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
                metrics=metrics,
            )
        )

    aggregates: dict[str, AggregateMetricSummary] = {}
    for m_id, ver in metric_versions.items():
        scores = per_metric_scores.get(m_id, [])
        counts = per_metric_counts[m_id]
        aggregates[m_id] = AggregateMetricSummary(
            metric_id=m_id,
            metric_version=ver,
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
        timestamp=datetime(2026, 11, 18, 12, 0, tzinfo=UTC),
        package_version="0.3.0",
        dataset_id="ds-gate",
        dataset_fingerprint=dataset_fp,
        evaluated_case_count=len(case_records),
        dataset_capped=dataset_capped,
        judge_config_fingerprint=judge_fp,
        metric_versions=metric_versions,
        aggregates=aggregates,
        status_counts=status_counts,
        mandatory_failed_case_ids=mandatory_failed,
        has_mandatory_failures=bool(mandatory_failed),
        case_results=case_records,
    )


@pytest.mark.gate_determinism
def test_quality_gate_pass_not_applicable_safety_and_determinism() -> None:
    gate = QualityGate(QualityGatePolicy(min_score=0.8, max_regressed_cases=1))
    assert gate.policy.min_score == 0.8

    # Answer-only run where optional retrieval metric is purely NOT_APPLICABLE (0 inconclusive)
    base = _run_fixture(
        "base",
        cases=[
            (
                "c1",
                True,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "precision_at_k": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                [],
            ),
        ],
    )
    cand = _run_fixture(
        "cand",
        cases=[
            (
                "c1",
                True,
                {
                    "exact_match": (0.96, MetricStatus.PASS, "1.0.0"),
                    "precision_at_k": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                [],
            ),
        ],
    )
    comp = compare_runs(base, cand, policy=gate.policy)
    trend = analyze_trend(
        [
            RunManifestEntry(
                run_id="t0",
                timestamp=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
                package_version="0.3.0",
                dataset_id="ds-gate",
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                metric_versions={"exact_match": "1.0.0"},
                aggregate_scores={"exact_match": 0.96},
                status_counts={MetricStatus.PASS: 1},
            ),
            RunManifestEntry(
                run_id="t1",
                timestamp=datetime(2026, 11, 18, 11, 0, tzinfo=UTC),
                package_version="0.3.0",
                dataset_id="ds-gate",
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                metric_versions={"exact_match": "1.0.0"},
                aggregate_scores={"exact_match": 0.96},
                status_counts={MetricStatus.PASS: 1},
            ),
        ]
    )

    res1 = gate.evaluate(cand, comparison=comp, trend=trend)
    res2 = gate.evaluate(cand, comparison=comp, trend=trend)
    assert res1.decision == GateDecision.PASS
    assert res1.passed is True
    assert res1.blocking is False
    assert canonical_json_bytes(res1.model_dump(mode="json")) == canonical_json_bytes(
        res2.model_dump(mode="json")
    )

    # Purely clean single run with default policy
    assert QualityGate().evaluate(base).decision == GateDecision.PASS


def test_quality_gate_fail_branches_and_precedence_over_inconclusive_and_warning() -> None:
    # Mandatory case fail + high inconclusive rate + drift warning -> FAIL wins strictly
    base = _run_fixture(
        "base",
        cases=[
            ("c1", True, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, []),
            ("c2", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, []),
        ],
    )
    cand_fail = _run_fixture(
        "cand-fail",
        dataset_fp="d" * 64,
        cases=[
            ("c1", True, {"exact_match": (0.0, MetricStatus.FAIL, "1.0.0")}, []),
            ("c2", False, {"exact_match": (None, MetricStatus.INCONCLUSIVE, "1.0.0")}, ["err"]),
        ],
    )
    comp = compare_runs(base, cand_fail)
    res = QualityGate(
        QualityGatePolicy(
            min_score=0.8,
            max_regression_drop=0.05,
            max_regressed_cases=0,
            max_inconclusive_rate=0.10,
            fail_on_mandatory_regression=True,
        )
    ).evaluate(cand_fail, comparison=comp)

    assert res.decision == GateDecision.FAIL
    assert res.passed is False
    assert res.blocking is True
    assert res.failure_reasons
    assert res.inconclusive_reasons  # recorded cleanly while FAIL holds precedence
    assert res.drift_warnings

    # Floor breach without mandatory failure
    cand_low = _run_fixture(
        "cand-low",
        cases=[("c1", False, {"exact_match": (0.6, MetricStatus.PASS, "1.0.0")}, [])],
    )
    res_low = QualityGate(QualityGatePolicy(min_metric_scores={"exact_match": 0.75})).evaluate(
        cand_low
    )
    assert res_low.decision == GateDecision.FAIL
    assert any("below floor" in r for r in res_low.failure_reasons)


def test_quality_gate_inconclusive_branches_and_precedence_over_warning() -> None:
    # 1) Required baseline / required trend missing
    run_ok = _run_fixture(
        "ok",
        dataset_capped=True,
        cases=[("c1", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, [])],
    )
    res_missing = QualityGate(
        QualityGatePolicy(require_baseline=True, require_trend=True)
    ).evaluate(run_ok)
    assert res_missing.decision == GateDecision.INCONCLUSIVE
    assert len(res_missing.inconclusive_reasons) == 2

    # 2) Zero applicable evidence across entire run
    run_none = _run_fixture(
        "all-none",
        cases=[("c1", False, {"exact_match": (None, MetricStatus.NOT_APPLICABLE, "1.0.0")}, [])],
    )
    res_none = QualityGate().evaluate(run_none)
    assert res_none.decision == GateDecision.INCONCLUSIVE

    # 3) Explicitly required metric missing score
    res_req_metric = QualityGate(QualityGatePolicy(min_metric_scores={"missing_m": 0.8})).evaluate(
        run_ok
    )
    assert res_req_metric.decision == GateDecision.INCONCLUSIVE

    # 4) Pairwise baseline comparison with zero comparable shared metrics
    run_other = _run_fixture(
        "other-metric",
        cases=[("c1", False, {"recall_at_k": (1.0, MetricStatus.PASS, "1.0.0")}, [])],
    )
    comp_disjoint = compare_runs(run_other, run_ok)
    res_disjoint = QualityGate().evaluate(run_ok, comparison=comp_disjoint)
    assert res_disjoint.decision == GateDecision.INCONCLUSIVE

    # 5) Trend history below min_trend_runs when require_trend=True
    short_trend = analyze_trend(
        [
            RunManifestEntry(
                run_id="t0",
                timestamp=datetime(2026, 11, 18, 12, 0, tzinfo=UTC),
                package_version="0.3.0",
                dataset_id="ds-gate",
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                metric_versions={"exact_match": "1.0.0"},
                aggregate_scores={"exact_match": 1.0},
                status_counts={MetricStatus.PASS: 1},
            )
        ]
    )
    res_short_trend = QualityGate(QualityGatePolicy(require_trend=True, min_trend_runs=3)).evaluate(
        run_ok, trend=short_trend
    )
    assert res_short_trend.decision == GateDecision.INCONCLUSIVE


def test_quality_gate_mandatory_drift_and_anomaly_gates_and_escalations() -> None:
    base = _run_fixture(
        "base",
        judge_fp="j1",
        cases=[("c1", False, {"exact_match": (0.95, MetricStatus.PASS, "1.0.0")}, [])],
    )
    # Candidate differs in dataset, metric_version, judge fingerprint + soft regression 0.03
    cand_drift = _run_fixture(
        "cand-drift",
        dataset_fp="f" * 64,
        judge_fp="j2",
        cases=[
            ("c1", False, {"exact_match": (0.92, MetricStatus.PASS, "2.0.0")}, []),
            ("c2-added", False, {"exact_match": (0.92, MetricStatus.PASS, "2.0.0")}, []),
        ],
    )
    comp_drift = compare_runs(base, cand_drift)

    # Default policy flags WARNING on cross-version drift, unmatched cases, and soft regression
    res_warn = QualityGate(QualityGatePolicy(soft_regression_warning=True)).evaluate(
        cand_drift, comparison=comp_drift
    )
    assert res_warn.decision == GateDecision.WARNING
    drift_cats = {d.category for d in res_warn.drift_warnings}
    assert {
        DriftCategory.DATASET_FINGERPRINT,
        DriftCategory.METRIC_VERSION,
        DriftCategory.JUDGE_CONFIG,
        DriftCategory.CASE_SET_MISMATCH,
    }.issubset(drift_cats)

    # Escalating fail_on_drift turns drift into FAIL
    res_fail_drift = QualityGate(QualityGatePolicy(fail_on_drift=True)).evaluate(
        cand_drift, comparison=comp_drift
    )
    assert res_fail_drift.decision == GateDecision.FAIL

    # Mandatory anomaly gate: >0.3 disagreement warns by default, FAIL when fail_on_anomaly=True.
    # Also demonstrates 10% (<= 0.10) inconclusive rate triggering WARNING, never INCONCLUSIVE.
    cases_disagree: list[
        tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]]
    ] = [
        (
            f"c{i}",
            False,
            {
                "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                "precision_at_k": (0.0, MetricStatus.FAIL, "1.0.0"),
            },
            [],
        )
        for i in range(9)
    ]
    cases_disagree.append(
        (
            "c9",
            False,
            {
                "exact_match": (None, MetricStatus.INCONCLUSIVE, "1.0.0"),
                "precision_at_k": (None, MetricStatus.INCONCLUSIVE, "1.0.0"),
            },
            ["timeout"],
        )
    )
    run_anom = _run_fixture("run-anom", cases=cases_disagree)
    res_anom_warn = QualityGate().evaluate(run_anom)
    assert res_anom_warn.decision == GateDecision.WARNING
    assert res_anom_warn.inconclusive_rate == 0.1
    assert any(a.anomaly_type.value == "METRIC_DISAGREEMENT" for a in res_anom_warn.anomalies)

    res_anom_fail = QualityGate(QualityGatePolicy(fail_on_anomaly=True)).evaluate(run_anom)
    assert res_anom_fail.decision == GateDecision.FAIL

    # Active-policy re-evaluation check (gate relaxes disagreement_threshold to 0.5 -> PASS)
    run_04 = _run_fixture(
        "r04",
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (0.9, MetricStatus.PASS, "1.0.0"),
                    "recall_at_k": (0.5, MetricStatus.PASS, "1.0.0"),
                },
                [],
            )
        ],
    )
    assert QualityGate(QualityGatePolicy(disagreement_threshold=0.5)).evaluate(run_04).decision == (
        GateDecision.PASS
    )

    # Trend degradation: WARNING by default, FAIL when fail_on_degrading_trend=True
    degrading_trend = analyze_trend(
        [
            RunManifestEntry(
                run_id=f"t{i}",
                timestamp=datetime(2026, 11, 18, 10, i, tzinfo=UTC),
                package_version="0.3.0",
                dataset_id="ds-gate",
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                metric_versions={"exact_match": "1.0.0"},
                aggregate_scores={"exact_match": 0.9 - 0.05 * i},
                status_counts={MetricStatus.PASS: 1},
            )
            for i in range(3)
        ]
    )
    clean_run = _run_fixture(
        "clean-single",
        cases=[("c1", False, {"exact_match": (0.8, MetricStatus.PASS, "1.0.0")}, [])],
    )
    assert QualityGate().evaluate(clean_run, trend=degrading_trend).decision == GateDecision.WARNING
    assert (
        QualityGate(QualityGatePolicy(fail_on_degrading_trend=True))
        .evaluate(clean_run, trend=degrading_trend)
        .decision
        == GateDecision.FAIL
    )


def test_quality_gate_mismatch_guard_and_result_model_validators() -> None:
    run_a = _run_fixture("run-a", cases=[("c1", False, {"em": (1.0, MetricStatus.PASS, "1")}, [])])
    run_b = _run_fixture("run-b", cases=[("c1", False, {"em": (1.0, MetricStatus.PASS, "1")}, [])])
    comp = compare_runs(run_a, run_b)

    with pytest.raises(ConfigurationError, match="does not match"):
        QualityGate().evaluate(run_a, comparison=comp)

    assert (
        GateRuleCheck(
            rule_id="r",
            status=GateDecision.PASS,
            message="ok",
            observed=0.0,
            threshold=1,
        ).observed
        == 0.0
    )
    with pytest.raises(ValidationError):
        GateRuleCheck(rule_id="r", status=GateDecision.PASS, message="ok", observed=True)
    with pytest.raises(ValidationError):
        QualityGateResult(
            decision=GateDecision.PASS,
            candidate_run_id="r",
            passed=False,
            blocking=False,
            inconclusive_rate=0.0,
            checks=[],
            summary="mismatched flag",
        )
    with pytest.raises(ValidationError):
        QualityGateResult(
            decision=GateDecision.PASS,
            candidate_run_id="r",
            passed=True,
            blocking=False,
            inconclusive_rate=1.2,
            checks=[],
            summary="bad rate",
        )


def test_quality_gate_statistical_significance_and_cohort_evaluation() -> None:
    # Q1: Tiny -0.02 drop stays within max_regression_drop=0.05 but is statistically significant
    base_tiny = _run_fixture(
        "stat-base",
        cases=[
            (f"c{i}", False, {"exact_match": (0.90, MetricStatus.PASS, "1.0.0")}, [])
            for i in range(5)
        ],
    )
    cand_tiny = _run_fixture(
        "stat-cand",
        cases=[
            (f"c{i}", False, {"exact_match": (0.88, MetricStatus.PASS, "1.0.0")}, [])
            for i in range(5)
        ],
    )
    comp_tiny = compare_runs(
        base_tiny,
        cand_tiny,
        policy=QualityGatePolicy(max_regression_drop=0.05),
    )
    assert comp_tiny.metric_comparisons["exact_match"].statistics is not None
    assert (
        comp_tiny.metric_comparisons["exact_match"].statistics.significance
        == SignificanceStatus.SIGNIFICANT_REGRESSION
    )

    advisory_res = QualityGate(
        QualityGatePolicy(max_regression_drop=0.05, fail_on_significant_regression=False)
    ).evaluate(cand_tiny, comparison=comp_tiny)
    assert advisory_res.decision == GateDecision.WARNING
    stat_rule = next(
        c for c in advisory_res.checks if c.rule_id == "statistical_regression:exact_match"
    )
    assert stat_rule.status == GateDecision.WARNING

    strict_stat_res = QualityGate(
        QualityGatePolicy(max_regression_drop=0.05, fail_on_significant_regression=True)
    ).evaluate(cand_tiny, comparison=comp_tiny)
    assert strict_stat_res.decision == GateDecision.FAIL
    strict_rule = next(
        c for c in strict_stat_res.checks if c.rule_id == "statistical_regression:exact_match"
    )
    assert strict_rule.status == GateDecision.FAIL

    # Non-significant comparison exercises PASS "statistical_significance" branch
    cand_same = _run_fixture(
        "stat-same",
        cases=[
            (f"c{i}", False, {"exact_match": (0.90, MetricStatus.PASS, "1.0.0")}, [])
            for i in range(5)
        ],
    )
    comp_same = compare_runs(base_tiny, cand_same)
    pass_stat_res = QualityGate().evaluate(cand_same, comparison=comp_same)
    assert pass_stat_res.decision == GateDecision.PASS
    assert any(
        c.rule_id == "statistical_significance" and c.status == GateDecision.PASS
        for c in pass_stat_res.checks
    )

    # Cohort gate validation + Q2 any-repeat mandatory fail + pooled floor check
    with pytest.raises(ConfigurationError):
        QualityGate().evaluate_cohort([])

    r1_mand_fail = _run_fixture(
        "coh-r1",
        cases=[
            ("m1", True, {"exact_match": (0.0, MetricStatus.FAIL, "1.0.0")}, []),
            ("c2", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, []),
        ],
    )
    r2_pass = _run_fixture(
        "coh-r2",
        cases=[
            ("m1", True, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, []),
            ("c2", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, []),
        ],
    )
    mand_cohort_res = QualityGate().evaluate_cohort([r1_mand_fail, r2_pass])
    assert mand_cohort_res.decision == GateDecision.FAIL
    assert mand_cohort_res.candidate_run_id == "coh-r2"
    assert any(
        c.rule_id == "mandatory_cases" and c.status == GateDecision.FAIL
        for c in mand_cohort_res.checks
    )

    r_low = _run_fixture(
        "pool-r1",
        cases=[("c1", False, {"exact_match": (0.60, MetricStatus.PASS, "1.0.0")}, [])],
    )
    r_high = _run_fixture(
        "pool-r2",
        cases=[("c1", False, {"exact_match": (0.80, MetricStatus.PASS, "1.0.0")}, [])],
    )
    assert (
        QualityGate(QualityGatePolicy(min_score=0.65)).evaluate_cohort([r_low, r_high]).decision
        == GateDecision.PASS
    )
    assert (
        QualityGate(QualityGatePolicy(min_score=0.75)).evaluate_cohort([r_low, r_high]).decision
        == GateDecision.FAIL
    )

    # Multi-run cohort comparison integrated with evaluate_cohort (K=3 vs M=3)
    b_cohs = [
        _run_fixture(
            f"b-coh-{i}",
            cases=[("c1", False, {"exact_match": (score, MetricStatus.PASS, "1.0.0")}, [])],
        )
        for i, score in enumerate((0.90, 0.905, 0.91), start=1)
    ]
    c_cohs = [
        _run_fixture(
            f"c-coh-{i}",
            cases=[("c1", False, {"exact_match": (score, MetricStatus.PASS, "1.0.0")}, [])],
        )
        for i, score in enumerate((0.88, 0.885, 0.89), start=1)
    ]
    coh_cmp = compare_run_cohorts(b_cohs, c_cohs)
    assert (
        QualityGate(QualityGatePolicy(max_regression_drop=0.05))
        .evaluate_cohort(c_cohs, comparison=coh_cmp)
        .decision
        == GateDecision.WARNING
    )
    with pytest.raises(ConfigurationError):
        QualityGate().evaluate_cohort(b_cohs, comparison=coh_cmp)

    single_vs_cohort = compare_runs(b_cohs[-1], c_cohs[-1])
    assert QualityGate().evaluate_cohort(c_cohs, comparison=single_vs_cohort).passed
