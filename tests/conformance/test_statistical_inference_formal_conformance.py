"""Dual-mode Python-to-Lean conformance suite for Statistical Inference & Significance Semantics.

Default mode validates Python's `compute_paired_case_statistics`, `compute_welch_run_statistics`,
`compute_one_sample_run_statistics`, `_finalize_inference`, `_extract_aligned_case_pairs`,
`compare_run_cohorts`, and `QualityGate` statistical-regression escalation offline against the
checked-in Lean oracle golden fixture
(`tests/conformance/golden/statistical_inference_oracle.json`).

Live mode (`--lean-live-oracle`) additionally executes the compiled Lean binary
(`evalforge-stats-oracle`) fail-closed to verify byte-for-byte golden parity, evaluate canonical,
direct-finalization, permutation, swap, cohort-dispatch, aligned-pair, and gate-bridge requests
via stdin/stdout, and confirm malformed requests fail closed.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import round_delta, round_score
from evalforge_maestro.regression.compare import (
    _extract_aligned_case_pairs,
    compare_run_cohorts,
    compare_runs,
)
from evalforge_maestro.regression.gate import QualityGate
from evalforge_maestro.regression.stats import (
    _finalize_inference,
    compute_one_sample_run_statistics,
    compute_paired_case_statistics,
    compute_welch_run_statistics,
    student_t_critical,
    student_t_two_tailed_p,
)
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    RunRecord,
    SignificanceStatus,
    StatisticalMethod,
    StatisticalSummary,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_STATS_PATH = Path(__file__).resolve().parent / "golden" / "statistical_inference_oracle.json"


def _rat_to_fraction(payload: dict[str, int]) -> Fraction:
    return Fraction(int(payload["num"]), int(payload["den"]))


def _opt_rat_to_fraction(payload: dict[str, int] | None) -> Fraction | None:
    if payload is None:
        return None
    return _rat_to_fraction(payload)


def _float_to_rat_json(value: float) -> dict[str, int]:
    frac = Fraction(str(round(value, 6)))
    return {"num": frac.numerator, "den": frac.denominator}


def _resolve_oracle_bin(request: pytest.FixtureRequest) -> Path:
    raw = str(request.config.getoption("--lean-stats-oracle-bin"))
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def _run_live_oracle(
    oracle_bin: Path,
    args: list[str],
    *,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if not oracle_bin.is_file():
        raise FileNotFoundError(f"Lean stats oracle binary not found at: {oracle_bin}")
    return subprocess.run(
        [str(oracle_bin), *args],
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _eval_live_oracle(oracle_bin: Path, payload: dict[str, Any]) -> dict[str, Any]:
    proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=json.dumps(payload))
    assert proc.returncode == 0, (
        f"evalforge-stats-oracle eval-stdin failed (exit={proc.returncode}): {proc.stderr}"
    )
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed


def _make_run(
    run_id: str,
    case_scores: dict[str, tuple[float | None, bool]],
    *,
    metric_id: str = "exact_match",
) -> RunRecord:
    """Build a canonical RunRecord where each entry is `(score, metric_present)`."""
    records: list[CaseEvaluationRecord] = []
    valid_scores: list[float] = []
    counts = {s: 0 for s in MetricStatus}

    for cid, (score, present) in case_scores.items():
        metrics: dict[str, MetricResult] = {}
        if present:
            if score is None:
                status = MetricStatus.NOT_APPLICABLE
            else:
                valid_scores.append(score)
                status = MetricStatus.PASS if score >= 0.5 else MetricStatus.FAIL
            counts[status] += 1
            metrics[metric_id] = MetricResult(
                metric_id=metric_id,
                metric_version="1.0.0",
                score=score,
                status=status,
                explanation="conformance synthetic score",
            )
        records.append(
            CaseEvaluationRecord(
                case_id=cid,
                mandatory=False,
                execution=ExecutionResult(
                    case_id=cid,
                    input=f"q-{cid}",
                    output=f"a-{cid}",
                    elapsed_seconds=0.01,
                ),
                metrics=metrics,
            )
        )

    mean_score = sum(valid_scores) / len(valid_scores) if valid_scores else None
    agg = AggregateMetricSummary(
        metric_id=metric_id,
        metric_version="1.0.0",
        mean_score=mean_score,
        applicable_count=len(valid_scores),
        pass_count=counts[MetricStatus.PASS],
        fail_count=counts[MetricStatus.FAIL],
        warning_count=counts[MetricStatus.WARNING],
        inconclusive_count=counts[MetricStatus.INCONCLUSIVE],
        not_applicable_count=counts[MetricStatus.NOT_APPLICABLE],
    )
    return RunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 26, 12, 0, tzinfo=UTC),
        package_version="0.5.0",
        dataset_id="formal-stats-ds",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=max(1, len(records)),
        system_version="sys-v1",
        model_id="mock-model",
        metric_versions={metric_id: "1.0.0"},
        aggregates={metric_id: agg},
        status_counts=counts,
        mandatory_failed_case_ids=[],
        has_mandatory_failures=False,
        case_results=records,
    )


def _run_python_stats_case(vector_input: dict[str, Any]) -> StatisticalSummary:
    method = StatisticalMethod(str(vector_input["method"]))
    base = [float(_rat_to_fraction(x)) for x in vector_input["baseline_scores"]]
    cand = [float(_rat_to_fraction(x)) for x in vector_input["candidate_scores"]]
    conf = float(_rat_to_fraction(vector_input["confidence_level"]))
    min_samples = int(vector_input["min_samples"])
    excluded = int(vector_input["excluded_pair_count"])

    if method == StatisticalMethod.PAIRED_T_CASE:
        return compute_paired_case_statistics(
            base,
            cand,
            confidence_level=conf,
            min_samples=min_samples,
            excluded_pair_count=excluded,
        )
    if method == StatisticalMethod.WELCH_T_RUN:
        return compute_welch_run_statistics(
            base,
            cand,
            confidence_level=conf,
            min_samples=min_samples,
        )
    return compute_one_sample_run_statistics(
        base,
        cand,
        confidence_level=conf,
        min_samples=min_samples,
    )


def _assert_summary_matches_oracle(
    summary: StatisticalSummary,
    oracle_expected: dict[str, Any],
) -> None:
    """Assert full categorical, count, CI, effect-size, and rounded numeric parity."""
    assert summary.method.value == oracle_expected["method"]
    assert summary.significance.value == oracle_expected["significance"]
    assert summary.statistically_significant == oracle_expected["statistically_significant"]
    assert summary.sample_size == oracle_expected["sample_size"]
    assert summary.baseline_sample_size == oracle_expected["baseline_sample_size"]
    assert summary.candidate_sample_size == oracle_expected["candidate_sample_size"]
    assert summary.excluded_pair_count == oracle_expected["excluded_pair_count"]

    exp_mean = _opt_rat_to_fraction(oracle_expected["mean_delta_exact"])
    if exp_mean is None:
        assert summary.mean_delta is None
    else:
        assert summary.mean_delta == round_delta(float(exp_mean))

    exp_se_sq = _opt_rat_to_fraction(oracle_expected["se_sq_exact"])
    if exp_se_sq is None:
        assert summary.standard_error is None
    else:
        assert summary.standard_error is not None
        assert math.isclose(summary.standard_error, math.sqrt(float(exp_se_sq)), abs_tol=1e-6)

    exp_df = _opt_rat_to_fraction(oracle_expected["df_exact"])
    if exp_df is None:
        assert summary.degrees_of_freedom is None
    else:
        assert summary.degrees_of_freedom is not None
        assert math.isclose(summary.degrees_of_freedom, float(exp_df), abs_tol=1e-6)

    exp_p = _opt_rat_to_fraction(oracle_expected["p_value_exact"])
    if exp_p is None:
        assert summary.p_value is None
    else:
        assert summary.p_value is not None
        assert 0.0 <= summary.p_value <= 1.0
        assert math.isclose(summary.p_value, float(exp_p), abs_tol=1e-6)

    exp_lo = _opt_rat_to_fraction(oracle_expected["ci_low_exact"])
    exp_hi = _opt_rat_to_fraction(oracle_expected["ci_high_exact"])
    if exp_lo is None or exp_hi is None:
        assert summary.ci_low is None and summary.ci_high is None
    else:
        assert summary.ci_low is not None and summary.ci_high is not None
        assert summary.mean_delta is not None
        assert -1.0 <= summary.ci_low <= summary.mean_delta <= summary.ci_high <= 1.0
        assert math.isclose(summary.ci_low, float(exp_lo), abs_tol=1e-5)
        assert math.isclose(summary.ci_high, float(exp_hi), abs_tol=1e-5)

    exp_eff = oracle_expected["effect_size"]
    if not exp_eff["defined"]:
        assert summary.effect_size is None
    else:
        assert summary.effect_size is not None
        exp_sign = str(exp_eff["sign"])
        if exp_sign == "positive":
            assert summary.effect_size > 0.0
        elif exp_sign == "negative":
            assert summary.effect_size < 0.0
        else:
            assert summary.effect_size == 0.0
        exp_sq_mag = _opt_rat_to_fraction(exp_eff["sq_mag_exact"])
        assert exp_sq_mag is not None
        assert math.isclose(abs(summary.effect_size), math.sqrt(float(exp_sq_mag)), abs_tol=1e-5)


def _live_stats_request_from_python(
    case_id: str,
    method: StatisticalMethod,
    base: list[float],
    cand: list[float],
    *,
    confidence_level: float = 0.95,
    min_samples: int = 2,
    excluded_pair_count: int = 0,
) -> tuple[StatisticalSummary, dict[str, Any]]:
    """Run Python stats and package exact-rational inputs + Python t-outputs for Lean."""
    if method == StatisticalMethod.PAIRED_T_CASE:
        summary = compute_paired_case_statistics(
            base,
            cand,
            confidence_level=confidence_level,
            min_samples=min_samples,
            excluded_pair_count=excluded_pair_count,
        )
    elif method == StatisticalMethod.WELCH_T_RUN:
        summary = compute_welch_run_statistics(
            base,
            cand,
            confidence_level=confidence_level,
            min_samples=min_samples,
        )
    else:
        summary = compute_one_sample_run_statistics(
            base,
            cand,
            confidence_level=confidence_level,
            min_samples=min_samples,
        )

    if (
        summary.standard_error is not None
        and summary.standard_error > 1e-9
        and summary.degrees_of_freedom is not None
        and summary.mean_delta is not None
    ):
        t_crit = student_t_critical(summary.degrees_of_freedom, confidence_level)
        margin = t_crit * summary.standard_error
        p_val = round_score(
            student_t_two_tailed_p(
                summary.mean_delta / summary.standard_error,
                summary.degrees_of_freedom,
            )
        )
    else:
        margin = 0.0
        p_val = 1.0 if summary.p_value is None else summary.p_value

    payload: dict[str, Any] = {
        "kind": "stats_case",
        "case_id": case_id,
        "method": method.value,
        "baseline_scores": [_float_to_rat_json(x) for x in base],
        "candidate_scores": [_float_to_rat_json(x) for x in cand],
        "confidence_level": _float_to_rat_json(confidence_level),
        "min_samples": min_samples,
        "excluded_pair_count": excluded_pair_count,
        "direct_p_value": _float_to_rat_json(p_val),
        "direct_margin": _float_to_rat_json(margin),
    }
    return summary, payload


def test_golden_statistical_oracle_schema_and_enums() -> None:
    """Verify checked-in golden statistical oracle matches Python schema and enum values."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))
    assert golden["schema_version"] == "1.0"
    assert golden["lean_toolchain"] == "leanprover/lean4:v4.36.0"
    assert golden["statistical_methods"] == [m.value for m in StatisticalMethod]
    assert golden["significance_statuses"] == [s.value for s in SignificanceStatus]
    assert len(golden["canonical_vectors"]) == 18
    assert len(golden["cohort_dispatch_matrix"]) == 16
    assert len(golden["gate_escalation_truth_table"]) == 8
    assert len(golden["aligned_pair_vectors"]) == 4


def test_offline_canonical_statistical_vectors_match_python() -> None:
    """Validate all 18 canonical golden vectors against real Python statistical entrypoints."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))
    for vector in golden["canonical_vectors"]:
        summary = _run_python_stats_case(vector["input"])
        _assert_summary_matches_oracle(summary, vector["expected"])


def test_offline_cohort_dispatch_matrix_matches_python() -> None:
    """Verify all 16 `(k, m)` cohort dispatch entries against real `compare_run_cohorts`."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))

    for entry in golden["cohort_dispatch_matrix"]:
        k = int(entry["baseline_run_count"])
        m = int(entry["candidate_run_count"])
        expected_route = str(entry["route"])

        base_runs: list[RunRecord] = []
        if k == 0:
            # Single run whose metric is NOT_APPLICABLE -> mean_score=None -> 0 numeric run scores
            base_runs.append(_make_run("b-na-0", {"q1": (None, True), "q2": (None, True)}))
        else:
            for idx in range(k):
                base_runs.append(
                    _make_run(
                        f"b-{idx}",
                        {"q1": (0.8 + 0.01 * idx, True), "q2": (0.85, True)},
                    )
                )

        cand_runs: list[RunRecord] = []
        if m == 0:
            cand_runs.append(_make_run("c-na-0", {"q1": (None, True), "q2": (None, True)}))
        else:
            for idx in range(m):
                cand_runs.append(
                    _make_run(
                        f"c-{idx}",
                        {"q1": (0.6 + 0.01 * idx, True), "q2": (0.65, True)},
                    )
                )

        if k == 1 and m == 1:
            # compare_run_cohorts([b0], [c0]) routes directly to compare_runs (PAIRED_T_CASE)
            report = compare_run_cohorts(base_runs, cand_runs)
            stats = report.metric_comparisons["exact_match"].statistics
            assert stats is not None
            assert expected_route == "paired_t_case_fallback"
            assert stats.method == StatisticalMethod.PAIRED_T_CASE
        else:
            # Ensure >=2 runs on at least one side when k==0 or m==0 so cohort branch runs
            if len(base_runs) == 1 and len(cand_runs) == 1:
                base_runs.append(_make_run("b-na-1", {"q1": (None, True), "q2": (None, True)}))
            report = compare_run_cohorts(base_runs, cand_runs)
            stats = report.metric_comparisons["exact_match"].statistics
            assert stats is not None
            if expected_route == "welch_t_run":
                assert stats.method == StatisticalMethod.WELCH_T_RUN
                if k == 0 or m == 0:
                    assert stats.significance == SignificanceStatus.INSUFFICIENT_DATA
            elif expected_route == "one_sample_t_run":
                assert stats.method == StatisticalMethod.ONE_SAMPLE_T_RUN
            else:
                raise AssertionError(f"Unexpected cohort route: {expected_route!r}")


def test_offline_aligned_pair_extraction_matches_python() -> None:
    """Verify all 4 aligned-pair golden vectors against real `_extract_aligned_case_pairs`."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))

    for vector in golden["aligned_pair_vectors"]:
        base_cases: dict[str, tuple[float | None, bool]] = {"only_base": (0.9, True)}
        cand_cases: dict[str, tuple[float | None, bool]] = {"only_cand": (0.4, True)}
        for row in vector["shared_rows"]:
            cid = str(row["case_id"])
            b_frac = _opt_rat_to_fraction(row["baseline_score"])
            c_frac = _opt_rat_to_fraction(row["candidate_score"])
            base_cases[cid] = (
                None if b_frac is None else float(b_frac),
                bool(row["baseline_metric_present"]),
            )
            cand_cases[cid] = (
                None if c_frac is None else float(c_frac),
                bool(row["candidate_metric_present"]),
            )

        base_run = _make_run("base-pairs", base_cases)
        cand_run = _make_run("cand-pairs", cand_cases)
        got_base, got_cand, got_excl = _extract_aligned_case_pairs(
            base_run, cand_run, "exact_match"
        )
        exp = vector["expected"]
        exp_base = [float(_rat_to_fraction(x)) for x in exp["baseline_scores"]]
        exp_cand = [float(_rat_to_fraction(x)) for x in exp["candidate_scores"]]
        assert got_base == exp_base
        assert got_cand == exp_cand
        assert got_excl == int(exp["excluded_pair_count"])


def test_offline_gate_escalation_truth_table_matches_python() -> None:
    """Verify all 8 `(significance, fail_on_significant_regression)` rows against `QualityGate`."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))

    scenario_runs: dict[str, tuple[RunRecord, RunRecord]] = {
        "significant_improvement": (
            _make_run("b-imp", {"q1": (0.5, True), "q2": (0.6, True), "q3": (0.5, True)}),
            _make_run("c-imp", {"q1": (0.9, True), "q2": (1.0, True), "q3": (0.9, True)}),
        ),
        "significant_regression": (
            _make_run("b-reg", {"q1": (0.9, True), "q2": (1.0, True), "q3": (0.9, True)}),
            _make_run("c-reg", {"q1": (0.5, True), "q2": (0.6, True), "q3": (0.5, True)}),
        ),
        "not_significant": (
            _make_run("b-ns", {"q1": (0.8, True), "q2": (0.9, True), "q3": (0.7, True)}),
            _make_run("c-ns", {"q1": (0.8, True), "q2": (0.9, True), "q3": (0.7, True)}),
        ),
        "insufficient_data": (
            _make_run("b-ins", {"q1": (0.9, True)}),
            _make_run("c-ins", {"q1": (0.5, True)}),
        ),
    }

    for row in golden["gate_escalation_truth_table"]:
        sig_key = str(row["significance"])
        fail_flag = bool(row["fail_on_significant_regression"])
        base_run, cand_run = scenario_runs[sig_key]
        policy = QualityGatePolicy(
            min_metric_scores={},
            max_regression_drop=1.0,
            max_regressed_cases=None,
            case_drop_warning_threshold=1.0,
            max_inconclusive_rate=1.0,
            fail_on_drift=False,
            fail_on_anomaly=False,
            fail_on_mandatory_regression=False,
            soft_regression_warning=False,
            fail_on_significant_regression=fail_flag,
        )
        comparison = compare_runs(base_run, cand_run, policy=policy)
        gate_res = QualityGate(policy=policy).evaluate(cand_run, comparison=comparison)
        stats = comparison.metric_comparisons["exact_match"].statistics
        assert stats is not None
        assert stats.significance.value == sig_key
        assert gate_res.decision.value == row["decision"]
        assert gate_res.passed == row["passed"]
        assert gate_res.blocking == row["blocking"]


def test_python_permutation_invariance_and_swap_duality_sweeps() -> None:
    """Verify permutation invariance and baseline/candidate swap duality in Python."""
    # Paired permutation + swap
    pairs = [(0.90, 0.65), (0.85, 0.63), (0.88, 0.64), (0.92, 0.70), (0.87, 0.65)]
    rev_pairs = list(reversed(pairs))
    p_orig = compute_paired_case_statistics([b for b, _ in pairs], [c for _, c in pairs])
    p_perm = compute_paired_case_statistics([b for b, _ in rev_pairs], [c for _, c in rev_pairs])
    p_swap = compute_paired_case_statistics([c for _, c in pairs], [b for b, _ in pairs])

    assert p_perm.mean_delta == p_orig.mean_delta
    assert p_perm.standard_error == p_orig.standard_error
    assert p_perm.degrees_of_freedom == p_orig.degrees_of_freedom
    assert p_perm.p_value == p_orig.p_value
    assert p_perm.significance == p_orig.significance

    assert p_orig.mean_delta is not None and p_swap.mean_delta == -p_orig.mean_delta
    assert p_swap.standard_error == p_orig.standard_error
    assert p_swap.degrees_of_freedom == p_orig.degrees_of_freedom
    assert p_swap.p_value == p_orig.p_value
    assert p_orig.ci_low is not None and p_orig.ci_high is not None
    assert p_swap.ci_low == -p_orig.ci_high
    assert p_swap.ci_high == -p_orig.ci_low
    assert p_orig.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert p_swap.significance == SignificanceStatus.SIGNIFICANT_IMPROVEMENT

    # Welch permutation + swap
    wb = [0.50, 0.52, 0.51]
    wc = [0.85, 0.88, 0.86, 0.89, 0.87]
    w_orig = compute_welch_run_statistics(wb, wc)
    w_perm = compute_welch_run_statistics(list(reversed(wb)), list(reversed(wc)))
    w_swap = compute_welch_run_statistics(wc, wb)
    assert w_perm.mean_delta == w_orig.mean_delta
    assert w_perm.degrees_of_freedom == w_orig.degrees_of_freedom
    assert w_perm.significance == w_orig.significance
    assert w_orig.mean_delta is not None and w_swap.mean_delta == -w_orig.mean_delta
    assert w_swap.degrees_of_freedom == w_orig.degrees_of_freedom
    assert w_orig.significance == SignificanceStatus.SIGNIFICANT_IMPROVEMENT
    assert w_swap.significance == SignificanceStatus.SIGNIFICANT_REGRESSION

    # One-sample permutation + swap
    ob = [0.90]
    oc = [0.60, 0.62, 0.61, 0.59]
    o_orig = compute_one_sample_run_statistics(ob, oc)
    o_perm = compute_one_sample_run_statistics(ob, list(reversed(oc)))
    o_swap = compute_one_sample_run_statistics(oc, ob)
    assert o_perm.mean_delta == o_orig.mean_delta
    assert o_perm.significance == o_orig.significance
    assert o_orig.mean_delta is not None and o_swap.mean_delta == -o_orig.mean_delta
    assert o_swap.sample_size == o_orig.sample_size
    assert o_orig.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert o_swap.significance == SignificanceStatus.SIGNIFICANT_IMPROVEMENT


def test_negative_drift_probes_detect_statistical_mismatches() -> None:
    """Confirm conformance assertions fail closed on deliberate significance or CI drift."""
    golden = json.loads(GOLDEN_STATS_PATH.read_text(encoding="utf-8"))
    vector = golden["canonical_vectors"][6]  # paired_noisy_regression
    summary = _run_python_stats_case(vector["input"])

    drifted_sig = copy.deepcopy(vector["expected"])
    drifted_sig["significance"] = "not_significant"
    with pytest.raises(AssertionError):
        _assert_summary_matches_oracle(summary, drifted_sig)

    drifted_flag = copy.deepcopy(vector["expected"])
    drifted_flag["statistically_significant"] = False
    with pytest.raises(AssertionError):
        _assert_summary_matches_oracle(summary, drifted_flag)

    drifted_ci = copy.deepcopy(vector["expected"])
    drifted_ci["ci_high_exact"] = {"num": 1, "den": 1}
    with pytest.raises(AssertionError):
        _assert_summary_matches_oracle(summary, drifted_ci)

    drifted_eff = copy.deepcopy(vector["expected"])
    drifted_eff["effect_size"]["sign"] = "positive"
    with pytest.raises(AssertionError):
        _assert_summary_matches_oracle(summary, drifted_eff)


def test_live_lean_stats_oracle_conformance_and_golden_parity(
    request: pytest.FixtureRequest,
) -> None:
    """Fail-closed live verification against compiled `evalforge-stats-oracle` binary."""
    if not request.config.getoption("--lean-live-oracle"):
        return

    oracle_bin = _resolve_oracle_bin(request)

    # 1. Exact byte-for-byte golden parity
    export_proc = _run_live_oracle(oracle_bin, ["export-golden"])
    assert export_proc.returncode == 0, (
        f"evalforge-stats-oracle export-golden failed: {export_proc.stderr}"
    )
    checked_in = GOLDEN_STATS_PATH.read_text(encoding="utf-8")
    assert export_proc.stdout == checked_in, (
        "Checked-in tests/conformance/golden/statistical_inference_oracle.json drifted from "
        "live `evalforge-stats-oracle export-golden` output."
    )

    golden = json.loads(checked_in)

    # 2. Re-evaluate all 18 canonical vectors live via eval-stdin
    for vector in golden["canonical_vectors"]:
        req = {"kind": "stats_case", **vector["input"]}
        live_resp = _eval_live_oracle(oracle_bin, req)
        assert live_resp == vector["expected"]
        summary = _run_python_stats_case(vector["input"])
        _assert_summary_matches_oracle(summary, live_resp)

    # 3. Live cross-check of fresh Python permutations & baseline/candidate swaps
    live_sweep_cases: list[tuple[str, StatisticalMethod, list[float], list[float], int]] = [
        (
            "live_paired_perm",
            StatisticalMethod.PAIRED_T_CASE,
            [0.87, 0.92, 0.88, 0.85, 0.90],
            [0.65, 0.70, 0.64, 0.63, 0.65],
            2,
        ),
        (
            "live_welch_swap",
            StatisticalMethod.WELCH_T_RUN,
            [0.85, 0.88, 0.86, 0.89, 0.87],
            [0.50, 0.52, 0.51],
            2,
        ),
        (
            "live_one_sample_min3",
            StatisticalMethod.ONE_SAMPLE_T_RUN,
            [0.90],
            [0.60, 0.62],
            3,
        ),
        (
            "live_welch_zero_var_eq",
            StatisticalMethod.WELCH_T_RUN,
            [0.75, 0.75, 0.75],
            [0.75, 0.75, 0.75],
            2,
        ),
    ]
    for cid, method, base, cand, min_s in live_sweep_cases:
        summary, payload = _live_stats_request_from_python(
            cid, method, base, cand, min_samples=min_s
        )
        live_resp = _eval_live_oracle(oracle_bin, payload)
        _assert_summary_matches_oracle(summary, live_resp)

    # 4. Direct `_finalize_inference` live verification (zero-variance + clamping)
    py_direct_zero = _finalize_inference(
        method=StatisticalMethod.PAIRED_T_CASE,
        confidence_level=0.95,
        sample_size=4,
        baseline_sample_size=4,
        candidate_sample_size=4,
        excluded_pair_count=0,
        mean_delta=0.25,
        delta_std=0.0,
        standard_error=0.0,
        baseline_std=0.1,
        candidate_std=0.1,
        effect_size=None,
        df=3.0,
        has_enough_samples=True,
    )
    lean_direct_zero = _eval_live_oracle(
        oracle_bin,
        {
            "kind": "finalize_direct",
            "method": "paired_t_case",
            "confidence_level": {"num": 95, "den": 100},
            "sample_size": 4,
            "baseline_sample_size": 4,
            "candidate_sample_size": 4,
            "excluded_pair_count": 0,
            "mean_delta": {"num": 1, "den": 4},
            "se_sq": {"num": 0, "den": 1},
            "df": {"num": 3, "den": 1},
            "effect_denom_var": {"num": 0, "den": 1},
            "has_enough_samples": True,
            "direct_p_value": {"num": 0, "den": 1},
            "direct_margin": {"num": 0, "den": 1},
        },
    )
    _assert_summary_matches_oracle(py_direct_zero, lean_direct_zero)

    # 5. Live cohort_dispatch, aligned_pairs, and gate_bridge verification
    for entry in golden["cohort_dispatch_matrix"]:
        resp = _eval_live_oracle(
            oracle_bin,
            {
                "kind": "cohort_dispatch",
                "baseline_run_count": entry["baseline_run_count"],
                "candidate_run_count": entry["candidate_run_count"],
            },
        )
        assert resp == {"route": entry["route"]}

    for vector in golden["aligned_pair_vectors"]:
        resp = _eval_live_oracle(
            oracle_bin,
            {"kind": "aligned_pairs", "shared_rows": vector["shared_rows"]},
        )
        assert resp == vector["expected"]

    for row in golden["gate_escalation_truth_table"]:
        resp = _eval_live_oracle(
            oracle_bin,
            {
                "kind": "gate_bridge",
                "statuses": [row["significance"]],
                "fail_on_significant_regression": row["fail_on_significant_regression"],
            },
        )
        assert resp == {
            "blocking": row["blocking"],
            "decision": row["decision"],
            "passed": row["passed"],
        }

    # 6. Fail-closed malformed stdin & CLI rejection
    bad_payloads: list[str] = [
        "{not-json",
        json.dumps({"kind": "unknown_kind"}),
        json.dumps(
            {
                "kind": "gate_bridge",
                "statuses": ["bogus"],
                "fail_on_significant_regression": False,
            }
        ),
        json.dumps(
            {
                "kind": "stats_case",
                "case_id": "bad_den",
                "method": "paired_t_case",
                "baseline_scores": [{"num": 1, "den": 0}],
                "candidate_scores": [{"num": 1, "den": 2}],
                "confidence_level": {"num": 95, "den": 100},
                "min_samples": 2,
                "excluded_pair_count": 0,
                "direct_p_value": {"num": 1, "den": 2},
                "direct_margin": {"num": 0, "den": 1},
            }
        ),
        json.dumps(
            {
                "kind": "stats_case",
                "case_id": "bad_conf",
                "method": "paired_t_case",
                "baseline_scores": [{"num": 1, "den": 2}, {"num": 1, "den": 2}],
                "candidate_scores": [{"num": 1, "den": 2}, {"num": 1, "den": 2}],
                "confidence_level": {"num": 1, "den": 1},
                "min_samples": 2,
                "excluded_pair_count": 0,
                "direct_p_value": {"num": 1, "den": 2},
                "direct_margin": {"num": 0, "den": 1},
            }
        ),
        json.dumps(
            {
                "kind": "stats_case",
                "case_id": "bad_paired_len",
                "method": "paired_t_case",
                "baseline_scores": [{"num": 1, "den": 2}],
                "candidate_scores": [{"num": 1, "den": 2}, {"num": 1, "den": 2}],
                "confidence_level": {"num": 95, "den": 100},
                "min_samples": 2,
                "excluded_pair_count": 0,
                "direct_p_value": {"num": 1, "den": 2},
                "direct_margin": {"num": 0, "den": 1},
            }
        ),
        json.dumps(
            {
                "kind": "stats_case",
                "case_id": "bad_one_sample_card",
                "method": "one_sample_t_run",
                "baseline_scores": [{"num": 1, "den": 2}, {"num": 1, "den": 2}],
                "candidate_scores": [{"num": 1, "den": 2}, {"num": 1, "den": 2}],
                "confidence_level": {"num": 95, "den": 100},
                "min_samples": 2,
                "excluded_pair_count": 0,
                "direct_p_value": {"num": 1, "den": 2},
                "direct_margin": {"num": 0, "den": 1},
            }
        ),
    ]
    for raw in bad_payloads:
        proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=raw)
        assert proc.returncode != 0, f"Malformed payload unexpectedly succeeded: {raw}"

    bad_cli = _run_live_oracle(oracle_bin, ["unknown-cmd"])
    assert bad_cli.returncode != 0
