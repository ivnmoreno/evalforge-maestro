"""Dual-mode Python-to-Lean conformance suite for Regression Analytics.

Default mode validates Python's real `detect_anomalies`, `_compute_ols_slope`, `analyze_trend`,
`detect_drift`, `detect_window_drift`, and `detect_cohort_drift` implementations offline against
the checked-in golden fixture (`tests/conformance/golden/regression_analytics_oracle.json`).

Live mode (`--lean-live-oracle`) additionally executes the compiled Lean binary
(`evalforge-regression-oracle`) fail-closed to verify byte-for-byte golden export parity,
evaluate canonical and property-sweep payloads via `eval-stdin` across all request kinds, and
confirm malformed inputs and CLI invocations fail closed.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import round_delta, round_score
from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.regression.drift import (
    detect_cohort_drift,
    detect_drift,
    detect_window_drift,
)
from evalforge_maestro.regression.trend import _compute_ols_slope, analyze_trend
from evalforge_maestro.types import (
    AggregateMetricSummary,
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    CaseComparison,
    CaseEvaluationRecord,
    CaseMetricDelta,
    ComparisonDirection,
    DriftCategory,
    DriftWarning,
    ExecutionResult,
    MetricComparison,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    RunComparisonReport,
    RunManifestEntry,
    RunRecord,
    TargetChangeSummary,
    TrendDirection,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_REGRESSION_PATH = (
    Path(__file__).resolve().parent / "golden" / "regression_analytics_oracle.json"
)


def _sha256_hex(label: str) -> str:
    """Map symbolic Lean provenance fingerprint strings injectively to 64-char hex digests."""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


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
    raw = str(request.config.getoption("--lean-regression-oracle-bin"))
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
        raise FileNotFoundError(f"Lean regression oracle binary not found at: {oracle_bin}")
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
        f"evalforge-regression-oracle eval-stdin failed (exit={proc.returncode}): {proc.stderr}"
    )
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed


def _load_golden() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(GOLDEN_REGRESSION_PATH.read_text(encoding="utf-8"))
    return parsed


def _build_policy(raw: dict[str, Any]) -> QualityGatePolicy:
    min_score_raw = raw["min_score"]
    min_score = (
        round_score(float(_rat_to_fraction(min_score_raw))) if min_score_raw is not None else None
    )
    return QualityGatePolicy(
        min_score=min_score,
        min_metric_scores={
            entry["metric_id"]: round_score(float(_rat_to_fraction(entry["value"])))
            for entry in raw["min_metric_scores"]
        },
        max_regression_drop=round_score(float(_rat_to_fraction(raw["max_regression_drop"]))),
        max_metric_regression_drops={
            entry["metric_id"]: round_score(float(_rat_to_fraction(entry["value"])))
            for entry in raw["max_metric_regression_drops"]
        },
        disagreement_threshold=round_score(float(_rat_to_fraction(raw["disagreement_threshold"]))),
        case_drop_warning_threshold=round_score(
            float(_rat_to_fraction(raw["case_drop_warning_threshold"]))
        ),
    )


def _build_run_record_from_anomaly_input(raw: dict[str, Any]) -> RunRecord:
    mandatory_set = set(raw["mandatory_failed_case_ids"])
    status_counts = {status: 0 for status in MetricStatus}
    case_records: list[CaseEvaluationRecord] = []

    for c_raw in raw["cases"]:
        cid = str(c_raw["case_id"])
        failed_set = set(c_raw["failed_metrics"])
        is_inc = bool(c_raw["is_inconclusive"])
        metrics: dict[str, MetricResult] = {}
        for m_entry in c_raw["metric_scores"]:
            mid = str(m_entry["metric_id"])
            score_frac = _opt_rat_to_fraction(m_entry["score"])
            score = round_score(float(score_frac)) if score_frac is not None else None
            if is_inc and score is None:
                status = MetricStatus.INCONCLUSIVE
            elif mid in failed_set:
                status = MetricStatus.FAIL
            elif score is None:
                status = MetricStatus.NOT_APPLICABLE
            else:
                status = MetricStatus.PASS
            status_counts[status] += 1
            metrics[mid] = MetricResult(
                metric_id=mid,
                metric_version="1.0.0",
                score=score,
                status=status,
                explanation=f"{mid}={status.value}",
            )
        case_records.append(
            CaseEvaluationRecord(
                case_id=cid,
                mandatory=cid in mandatory_set,
                execution=ExecutionResult(
                    case_id=cid,
                    input=f"q-{cid}",
                    output=None if is_inc else f"a-{cid}",
                    elapsed_seconds=0.01,
                    errors=["inconclusive"] if is_inc else [],
                ),
                metrics=metrics,
            )
        )

    aggregates: dict[str, AggregateMetricSummary] = {}
    metric_versions: dict[str, str] = {}
    for agg_entry in raw["aggregates"]:
        mid = str(agg_entry["metric_id"])
        metric_versions[mid] = "1.0.0"
        mean_frac = _opt_rat_to_fraction(agg_entry["score"])
        mean_val = round_score(float(mean_frac)) if mean_frac is not None else None
        aggregates[mid] = AggregateMetricSummary(
            metric_id=mid,
            metric_version="1.0.0",
            mean_score=mean_val,
            applicable_count=len(case_records) if mean_val is not None else 0,
            pass_count=len(case_records) if mean_val is not None else 0,
            fail_count=0,
            warning_count=0,
            inconclusive_count=0,
            not_applicable_count=0 if mean_val is not None else len(case_records),
        )

    return RunRecord(
        run_id=str(raw["run_id"]),
        timestamp=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        package_version="0.3.0",
        dataset_id="ds-conformance",
        dataset_fingerprint=_sha256_hex("ds-conformance"),
        evaluated_case_count=int(raw["evaluated_case_count"]),
        dataset_capped=bool(raw["dataset_capped"]),
        metric_versions=metric_versions,
        aggregates=aggregates,
        status_counts=status_counts,
        mandatory_failed_case_ids=list(raw["mandatory_failed_case_ids"]),
        has_mandatory_failures=bool(raw["mandatory_failed_case_ids"]),
        case_results=case_records,
    )


def _direction_for_delta(delta: float | None) -> ComparisonDirection:
    if delta is None:
        return ComparisonDirection.INCONCLUSIVE
    if delta > 0.0:
        return ComparisonDirection.IMPROVED
    if delta < 0.0:
        return ComparisonDirection.REGRESSED
    return ComparisonDirection.UNCHANGED


def _build_comparison_report(raw: dict[str, Any] | None) -> RunComparisonReport | None:
    if raw is None:
        return None
    metric_comparisons: dict[str, MetricComparison] = {}
    for mc_raw in raw["metric_comparisons"]:
        mid = str(mc_raw["metric_id"])
        delta_frac = _opt_rat_to_fraction(mc_raw["delta"])
        delta = round_delta(float(delta_frac)) if delta_frac is not None else None
        metric_comparisons[mid] = MetricComparison(
            metric_id=mid,
            baseline_version="1.0.0",
            candidate_version="1.0.0",
            baseline_score=0.5 if delta is not None else None,
            candidate_score=round_score(max(0.0, min(1.0, 0.5 + delta)))
            if delta is not None
            else None,
            delta=delta,
            direction=_direction_for_delta(delta),
        )
    case_comparisons: list[CaseComparison] = []
    for cc_raw in raw["case_comparisons"]:
        cid = str(cc_raw["case_id"])
        cmd_map: dict[str, CaseMetricDelta] = {}
        any_reg = False
        for cmd_raw in cc_raw["metric_deltas"]:
            mid = str(cmd_raw["metric_id"])
            delta_frac = _opt_rat_to_fraction(cmd_raw["delta"])
            delta = round_delta(float(delta_frac)) if delta_frac is not None else None
            reg = delta is not None and delta < 0.0
            if reg:
                any_reg = True
            cmd_map[mid] = CaseMetricDelta(
                metric_id=mid,
                baseline_score=0.5 if delta is not None else None,
                candidate_score=round_score(max(0.0, min(1.0, 0.5 + delta)))
                if delta is not None
                else None,
                delta=delta,
                baseline_status=MetricStatus.PASS if delta is not None else None,
                candidate_status=MetricStatus.PASS if delta is not None else None,
                regressed=reg,
                direction=_direction_for_delta(delta),
            )
        case_comparisons.append(
            CaseComparison(
                case_id=cid,
                regressed=any_reg,
                metrics=cmd_map,
            )
        )
    return RunComparisonReport(
        baseline_run_id="run-baseline",
        candidate_run_id="run-candidate",
        target_changes=TargetChangeSummary(),
        metric_comparisons=metric_comparisons,
        case_comparisons=case_comparisons,
        matched_case_count=len(case_comparisons),
    )


def _build_run_record_from_provenance(raw: dict[str, Any]) -> RunRecord:
    metric_versions = {str(item["key"]): str(item["value"]) for item in raw["metric_versions"]}
    case_ids = list(raw["case_ids"]) or ["c-default"]
    case_records = [
        CaseEvaluationRecord(
            case_id=cid,
            mandatory=False,
            execution=ExecutionResult(
                case_id=cid,
                input=f"q-{cid}",
                output=f"a-{cid}",
                elapsed_seconds=0.01,
            ),
            metrics={
                mid: MetricResult(
                    metric_id=mid,
                    metric_version=ver,
                    score=1.0,
                    status=MetricStatus.PASS,
                    explanation="ok",
                )
                for mid, ver in metric_versions.items()
            },
        )
        for cid in case_ids
    ]
    aggregates = {
        mid: AggregateMetricSummary(
            metric_id=mid,
            metric_version=ver,
            mean_score=1.0,
            applicable_count=len(case_records),
            pass_count=len(case_records),
            fail_count=0,
            warning_count=0,
            inconclusive_count=0,
            not_applicable_count=0,
        )
        for mid, ver in metric_versions.items()
    }
    return RunRecord(
        run_id=str(raw["run_id"]),
        timestamp=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        package_version="0.3.0",
        dataset_id="ds-drift",
        dataset_fingerprint=_sha256_hex(str(raw["dataset_fingerprint"])),
        evaluated_case_count=len(case_records),
        dataset_capped=bool(raw["dataset_capped"]),
        system_version=raw["system_version"],
        model_id=raw["model_id"],
        config_fingerprint=raw["config_fingerprint"],
        judge_config_fingerprint=raw["judge_config_fingerprint"],
        embedding_config_fingerprint=raw["embedding_config_fingerprint"],
        metric_versions=metric_versions,
        aggregates=aggregates,
        status_counts={MetricStatus.PASS: len(case_records) * len(metric_versions)},
        case_results=case_records,
    )


def _build_manifest_from_trend_entry(raw: dict[str, Any]) -> RunManifestEntry:
    prov = raw["provenance"]
    ts_key = int(raw["timestamp_key"])
    base_dt = datetime(2026, 11, 20, 0, 0, tzinfo=UTC) + timedelta(seconds=ts_key)
    scores: dict[str, float | None] = {}
    for entry in raw["metric_scores"]:
        frac = _opt_rat_to_fraction(entry["score"])
        scores[str(entry["metric_id"])] = round_score(float(frac)) if frac is not None else None
    metric_versions = {str(item["key"]): str(item["value"]) for item in prov["metric_versions"]}
    return RunManifestEntry(
        run_id=str(raw["run_id"]),
        timestamp=base_dt,
        package_version="0.3.0",
        dataset_id=str(raw["dataset_id"]),
        dataset_fingerprint=_sha256_hex(str(prov["dataset_fingerprint"])),
        evaluated_case_count=max(1, len(prov["case_ids"])),
        dataset_capped=bool(prov["dataset_capped"]),
        system_version=prov["system_version"],
        model_id=raw["model_id"],
        config_fingerprint=prov["config_fingerprint"],
        judge_config_fingerprint=prov["judge_config_fingerprint"],
        embedding_config_fingerprint=prov["embedding_config_fingerprint"],
        metric_versions=metric_versions,
        aggregate_scores=scores,
        status_counts={},
    )


def _assert_anomalies_match(
    actual: list[AnomalyFlag],
    expected_json: list[dict[str, Any]],
    *,
    label: str,
    sort_metric_ids: bool = False,
) -> None:
    assert len(actual) == len(expected_json), (
        f"[{label}] anomaly count mismatch: python={len(actual)} vs lean={len(expected_json)}"
    )
    for idx, (py_flag, lean_flag) in enumerate(zip(actual, expected_json, strict=True)):
        assert py_flag.anomaly_type.value == lean_flag["anomaly_type"], f"[{label}#{idx}] type"
        assert py_flag.severity.value == lean_flag["severity"], f"[{label}#{idx}] severity"
        assert py_flag.scope.value == lean_flag["scope"], f"[{label}#{idx}] scope"
        assert py_flag.case_id == lean_flag["case_id"], f"[{label}#{idx}] case_id"
        if sort_metric_ids:
            assert sorted(py_flag.metric_ids) == sorted(lean_flag["metric_ids"]), (
                f"[{label}#{idx}] metric_ids"
            )
        else:
            assert py_flag.metric_ids == lean_flag["metric_ids"], f"[{label}#{idx}] metric_ids"
        lean_spread = _opt_rat_to_fraction(lean_flag["spread_exact"])
        if lean_spread is None:
            assert py_flag.spread is None, f"[{label}#{idx}] expected None spread"
        else:
            assert py_flag.spread is not None, f"[{label}#{idx}] expected numeric spread"
            assert py_flag.spread == pytest.approx(round_delta(float(lean_spread)), abs=1e-6), (
                f"[{label}#{idx}] spread mismatch: {py_flag.spread} vs {float(lean_spread)}"
            )


def _assert_warnings_match(
    actual: list[DriftWarning],
    expected_json: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    assert len(actual) == len(expected_json), (
        f"[{label}] warning count mismatch: python={len(actual)} vs lean={len(expected_json)}"
    )
    for idx, (py_w, lean_w) in enumerate(zip(actual, expected_json, strict=True)):
        assert py_w.category.value == lean_w["category"], f"[{label}#{idx}] category"
        assert py_w.metric_id == lean_w["metric_id"], f"[{label}#{idx}] metric_id"
        assert py_w.baseline_run_id == lean_w["baseline_run_id"], f"[{label}#{idx}] baseline_run_id"
        assert py_w.candidate_run_id == lean_w["candidate_run_id"], (
            f"[{label}#{idx}] candidate_run_id"
        )


def _assert_trend_report_matches(
    actual_report: Any,
    expected: dict[str, Any],
    *,
    label: str,
) -> None:
    assert actual_report.window == expected["window"], f"[{label}] window"
    assert actual_report.dataset_id_filter == expected["dataset_id_filter"], f"[{label}] dataset"
    assert actual_report.model_id_filter == expected["model_id_filter"], f"[{label}] model"
    assert actual_report.inspected_run_ids == expected["inspected_run_ids"], f"[{label}] runs"
    assert list(actual_report.metrics.keys()) == [m["metric_id"] for m in expected["metrics"]], (
        f"[{label}] metric key order"
    )
    for lean_m in expected["metrics"]:
        mid = str(lean_m["metric_id"])
        py_m = actual_report.metrics[mid]
        assert py_m.window_runs == lean_m["window_runs"], f"[{label}.{mid}] window_runs"
        assert py_m.valid_points == lean_m["valid_points"], f"[{label}.{mid}] valid_points"
        assert py_m.missing_points == lean_m["missing_points"], f"[{label}.{mid}] missing_points"
        assert py_m.valid_points + py_m.missing_points == py_m.window_runs
        assert py_m.direction.value == lean_m["direction"], f"[{label}.{mid}] direction"

        lean_slope = _opt_rat_to_fraction(lean_m["slope_exact"])
        if lean_slope is None:
            assert py_m.slope is None, f"[{label}.{mid}] expected None slope"
        else:
            assert py_m.slope is not None
            assert py_m.slope == pytest.approx(round_delta(float(lean_slope)), abs=1e-6)

        for field_name, json_key in (
            ("first_score", "first_score_exact"),
            ("last_score", "last_score_exact"),
            ("min_score", "min_score_exact"),
            ("max_score", "max_score_exact"),
            ("mean_score", "mean_score_exact"),
        ):
            lean_val = _opt_rat_to_fraction(lean_m[json_key])
            py_val = getattr(py_m, field_name)
            if lean_val is None:
                assert py_val is None, f"[{label}.{mid}].{field_name}"
            else:
                assert py_val == pytest.approx(round_score(float(lean_val)), abs=1e-6), (
                    f"[{label}.{mid}].{field_name}"
                )

    _assert_warnings_match(actual_report.drift_warnings, expected["drift_warnings"], label=label)


# ---------------------------------------------------------------------------
# Mode A: Offline Golden Conformance Tests (Default — Zero Lean Required)
# ---------------------------------------------------------------------------


def test_golden_regression_oracle_schema_and_enums() -> None:
    """Verify golden fixture metadata, exact enum sets, and expected canonical vector counts."""
    golden = _load_golden()
    assert golden["schema_version"] == "1.0"
    assert golden["lean_toolchain"] == "leanprover/lean4:v4.36.0"

    assert golden["anomaly_types"] == [e.value for e in AnomalyType]
    assert golden["anomaly_severities"] == [e.value for e in AnomalySeverity]
    assert golden["anomaly_scopes"] == [e.value for e in AnomalyScope]
    assert golden["trend_directions"] == [e.value for e in TrendDirection]
    assert golden["drift_categories"] == [e.value for e in DriftCategory]

    assert len(golden["anomaly_vectors"]) == 8
    assert len(golden["trend_vectors"]) == 8
    assert len(golden["drift_pair_vectors"]) == 5
    assert len(golden["drift_cohort_vectors"]) == 4


def test_offline_canonical_anomaly_vectors() -> None:
    """Validate Python `detect_anomalies` against all 8 Lean golden anomaly vectors."""
    golden = _load_golden()
    for vec in golden["anomaly_vectors"]:
        cid = str(vec["case_id"])
        inp = vec["input"]
        run = _build_run_record_from_anomaly_input(inp["run"])
        cmp = _build_comparison_report(inp["comparison"])
        policy = _build_policy(inp["policy"])
        actual = detect_anomalies(run, comparison=cmp, policy=policy)
        _assert_anomalies_match(actual, vec["expected"]["anomalies"], label=cid)


def test_offline_canonical_trend_vectors() -> None:
    """Validate Python `analyze_trend` and `_compute_ols_slope` against all 8 Lean trend vectors."""
    golden = _load_golden()
    for vec in golden["trend_vectors"]:
        cid = str(vec["case_id"])
        inp = vec["input"]
        entries = [_build_manifest_from_trend_entry(r) for r in inp["runs"]]
        slope_thr = round_score(float(_rat_to_fraction(inp["slope_threshold"])))
        report = analyze_trend(
            entries,
            window=int(inp["window"]),
            dataset_id=inp["dataset_id"],
            all_datasets=bool(inp["all_datasets"]),
            model_id=inp["model_id"],
            metric_ids=inp["metric_ids"],
            slope_threshold=slope_thr,
        )
        _assert_trend_report_matches(report, vec["expected"], label=cid)


def test_offline_canonical_drift_pair_and_window_vectors() -> None:
    """Validate Python `detect_drift` and `detect_window_drift` against all 5 golden vectors."""
    golden = _load_golden()
    pair_categories: dict[str, set[str]] = {}
    for vec in golden["drift_pair_vectors"]:
        cid = str(vec["case_id"])
        mode = str(vec["mode"])
        inp = vec["input"]
        if mode == "pair":
            base = _build_run_record_from_provenance(inp["baseline"])
            cand = _build_run_record_from_provenance(inp["candidate"])
            actual = detect_drift(base, cand)
            pair_categories[cid] = {w.category.value for w in actual}
        else:
            runs = [_build_run_record_from_provenance(r) for r in inp["runs"]]
            actual = detect_window_drift(runs)
        _assert_warnings_match(actual, vec["expected"]["warnings"], label=cid)

    # Verify swap symmetry between all-seven and swapped vectors
    assert (
        pair_categories["pair_all_seven_categories_active"]
        == pair_categories["pair_swap_symmetry_counterpart"]
        == {cat.value for cat in DriftCategory}
    )


def test_offline_canonical_drift_cohort_vectors() -> None:
    """Validate Python `detect_cohort_drift` against all 4 Lean golden cohort drift vectors."""
    golden = _load_golden()
    for vec in golden["drift_cohort_vectors"]:
        cid = str(vec["case_id"])
        inp = vec["input"]
        base_runs = [_build_run_record_from_provenance(r) for r in inp["baseline_runs"]]
        cand_runs = [_build_run_record_from_provenance(r) for r in inp["candidate_runs"]]
        actual = detect_cohort_drift(base_runs, cand_runs)
        _assert_warnings_match(actual, vec["expected"]["warnings"], label=cid)
        keys = [(w.category, w.metric_id, w.baseline_run_id, w.candidate_run_id) for w in actual]
        assert len(keys) == len(set(keys)), f"[{cid}] duplicate cohort drift keys emitted"


def test_offline_anomaly_permutation_invariance() -> None:
    """Verify permuting metric score entries leaves disagreement trigger & spread invariant."""
    scores_list = [("m_a", 0.92), ("m_b", 0.50), ("m_c", 0.74)]
    policy = QualityGatePolicy(disagreement_threshold=0.30)
    expected_spread = round_delta(0.92 - 0.50)

    for perm in itertools.permutations(scores_list):
        run_input: dict[str, Any] = {
            "run_id": "perm-run",
            "evaluated_case_count": 1,
            "dataset_capped": False,
            "mandatory_failed_case_ids": [],
            "aggregates": [{"metric_id": k, "score": _float_to_rat_json(v)} for k, v in perm],
            "cases": [
                {
                    "case_id": "c1",
                    "metric_scores": [
                        {"metric_id": k, "score": _float_to_rat_json(v)} for k, v in perm
                    ],
                    "failed_metrics": [],
                    "is_inconclusive": False,
                }
            ],
        }
        run = _build_run_record_from_anomaly_input(run_input)
        flags = detect_anomalies(run, policy=policy)
        assert len(flags) == 2
        for flag in flags:
            assert flag.anomaly_type == AnomalyType.METRIC_DISAGREEMENT
            assert flag.spread == pytest.approx(expected_spread, abs=1e-9)
            assert flag.metric_ids == ["m_a", "m_b", "m_c"]


def test_offline_ols_algebra_shift_reversal_sharp_bound_and_utc_ordering() -> None:
    """Empirically verify Lean OLS theorems and Python UTC/offset timestamp boundary."""
    # 1. Exact affine recovery, shift invariance, and time-reversal anti-symmetry
    for m in (2, 3, 4, 5, 7):
        base_series = [0.2 + 0.05 * i for i in range(m)]
        slope = _compute_ols_slope(base_series)
        assert slope == pytest.approx(0.05, abs=1e-12)

        shifted = [y + 0.15 for y in base_series]
        assert _compute_ols_slope(shifted) == pytest.approx(slope, abs=1e-12)

        rev_slope = _compute_ols_slope(list(reversed(base_series)))
        assert rev_slope == pytest.approx(-slope, abs=1e-12)

    # 2. Sharp universal unit bound |slope| <= 3m / (2(m^2 - 1)) <= 1 for extreme [0, 1] series
    # (_compute_ols_slope applies 6-decimal round_delta quantization at the Python boundary.)
    for m in range(2, 13):
        sharp = (3.0 * m) / (2.0 * (m * m - 1))
        assert sharp <= 1.0 + 1e-12
        half = m // 2
        step_up = [0.0] * half + [1.0] * (m - half)
        step_down = list(reversed(step_up))
        s_up = _compute_ols_slope(step_up)
        s_down = _compute_ols_slope(step_down)
        assert abs(s_up) <= round_delta(sharp) + 1e-12
        assert abs(s_down) <= round_delta(sharp) + 1e-12
        assert s_down == pytest.approx(-s_up, abs=1e-12)
        if m % 2 == 0:
            assert s_up == pytest.approx(round_delta(sharp), abs=1e-12)

    # 3. Mixed timezone offset UTC normalization + run_id tie-breaking boundary
    tz_plus_2 = timezone(timedelta(hours=2))
    tz_minus_5 = timezone(timedelta(hours=-5))
    t_utc = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    entries = [
        RunManifestEntry(
            run_id="run-b",
            timestamp=t_utc.astimezone(tz_plus_2),
            package_version="0.3.0",
            dataset_id="ds-tz",
            dataset_fingerprint=_sha256_hex("ds-tz"),
            evaluated_case_count=1,
            metric_versions={"m": "1.0.0"},
            aggregate_scores={"m": 0.7},
            status_counts={},
        ),
        RunManifestEntry(
            run_id="run-a",
            timestamp=t_utc.astimezone(tz_minus_5),
            package_version="0.3.0",
            dataset_id="ds-tz",
            dataset_fingerprint=_sha256_hex("ds-tz"),
            evaluated_case_count=1,
            metric_versions={"m": "1.0.0"},
            aggregate_scores={"m": 0.5},
            status_counts={},
        ),
        RunManifestEntry(
            run_id="run-c",
            timestamp=t_utc + timedelta(minutes=1),
            package_version="0.3.0",
            dataset_id="ds-tz",
            dataset_fingerprint=_sha256_hex("ds-tz"),
            evaluated_case_count=1,
            metric_versions={"m": "1.0.0"},
            aggregate_scores={"m": 0.9},
            status_counts={},
        ),
    ]
    report = analyze_trend(entries, window=3)
    assert report.inspected_run_ids == ["run-a", "run-b", "run-c"]
    assert report.metrics["m"].direction == TrendDirection.IMPROVING
    assert report.metrics["m"].slope == pytest.approx(0.2, abs=1e-6)


def test_offline_negative_drift_probes_detect_semantic_divergence() -> None:
    """Confirm conformance assertions immediately catch mutated spreads, slopes, or drift lists."""
    golden = _load_golden()

    # Probe 1: mutated anomaly spread fails
    vec_a = golden["anomaly_vectors"][1]
    run = _build_run_record_from_anomaly_input(vec_a["input"]["run"])
    actual_a = detect_anomalies(run, policy=_build_policy(vec_a["input"]["policy"]))
    corrupted_a = json.loads(json.dumps(vec_a["expected"]["anomalies"]))
    corrupted_a[0]["spread_exact"] = {"num": 1, "den": 100}
    with pytest.raises(AssertionError, match="spread mismatch"):
        _assert_anomalies_match(actual_a, corrupted_a, label="neg-anomaly")

    # Probe 2: mutated trend direction fails
    vec_t = golden["trend_vectors"][0]
    entries = [_build_manifest_from_trend_entry(r) for r in vec_t["input"]["runs"]]
    actual_t = analyze_trend(entries, window=int(vec_t["input"]["window"]))
    corrupted_t = json.loads(json.dumps(vec_t["expected"]))
    corrupted_t["metrics"][0]["direction"] = "IMPROVING"
    with pytest.raises(AssertionError, match="direction"):
        _assert_trend_report_matches(actual_t, corrupted_t, label="neg-trend")

    # Probe 3: missing drift warning fails
    vec_d = golden["drift_pair_vectors"][2]
    actual_d = detect_drift(
        _build_run_record_from_provenance(vec_d["input"]["baseline"]),
        _build_run_record_from_provenance(vec_d["input"]["candidate"]),
    )
    corrupted_d = vec_d["expected"]["warnings"][:-1]
    with pytest.raises(AssertionError, match="warning count mismatch"):
        _assert_warnings_match(actual_d, corrupted_d, label="neg-drift")


# ---------------------------------------------------------------------------
# Mode B: Fail-Closed Live Lean Oracle Tests (`--lean-live-oracle`)
# ---------------------------------------------------------------------------


def test_live_oracle_golden_export_byte_parity(request: pytest.FixtureRequest) -> None:
    """Confirm `evalforge-regression-oracle export-golden` matches the checked-in golden JSON."""
    if not request.config.getoption("--lean-live-oracle"):
        pytest.skip("Pass --lean-live-oracle to execute live Lean regression oracle verification.")

    oracle_bin = _resolve_oracle_bin(request)
    proc = _run_live_oracle(oracle_bin, ["export-golden"])
    assert proc.returncode == 0, f"export-golden failed: {proc.stderr}"
    expected_text = GOLDEN_REGRESSION_PATH.read_text(encoding="utf-8")
    assert proc.stdout == expected_text


def test_live_oracle_eval_stdin_all_kinds_and_sweeps(request: pytest.FixtureRequest) -> None:
    """Evaluate all golden vectors and additional sweeps live via `eval-stdin` against Python."""
    if not request.config.getoption("--lean-live-oracle"):
        pytest.skip("Pass --lean-live-oracle to execute live Lean regression oracle verification.")

    oracle_bin = _resolve_oracle_bin(request)
    golden = _load_golden()

    # 1. All 8 canonical anomaly vectors live
    for vec in golden["anomaly_vectors"]:
        inp = vec["input"]
        live_resp = _eval_live_oracle(oracle_bin, {"kind": "anomaly_case", **inp})
        run = _build_run_record_from_anomaly_input(inp["run"])
        cmp = _build_comparison_report(inp["comparison"])
        policy = _build_policy(inp["policy"])
        actual = detect_anomalies(run, comparison=cmp, policy=policy)
        _assert_anomalies_match(actual, live_resp["anomalies"], label=f"live:{vec['case_id']}")

    # 2. All 8 canonical trend vectors live
    for vec in golden["trend_vectors"]:
        inp = vec["input"]
        live_resp = _eval_live_oracle(oracle_bin, {"kind": "trend_case", **inp})
        entries = [_build_manifest_from_trend_entry(r) for r in inp["runs"]]
        slope_thr = round_score(float(_rat_to_fraction(inp["slope_threshold"])))
        actual_report = analyze_trend(
            entries,
            window=int(inp["window"]),
            dataset_id=inp["dataset_id"],
            all_datasets=bool(inp["all_datasets"]),
            model_id=inp["model_id"],
            metric_ids=inp["metric_ids"],
            slope_threshold=slope_thr,
        )
        _assert_trend_report_matches(actual_report, live_resp, label=f"live:{vec['case_id']}")

    # 3. All 5 pairwise/window drift vectors live
    for vec in golden["drift_pair_vectors"]:
        inp = vec["input"]
        mode = str(vec["mode"])
        if mode == "pair":
            live_resp = _eval_live_oracle(oracle_bin, {"kind": "drift_pair", **inp})
            actual_w = detect_drift(
                _build_run_record_from_provenance(inp["baseline"]),
                _build_run_record_from_provenance(inp["candidate"]),
            )
        else:
            live_resp = _eval_live_oracle(oracle_bin, {"kind": "drift_window", **inp})
            actual_w = detect_window_drift(
                [_build_run_record_from_provenance(r) for r in inp["runs"]]
            )
        _assert_warnings_match(actual_w, live_resp["warnings"], label=f"live:{vec['case_id']}")

    # 4. All 4 cohort drift vectors live
    for vec in golden["drift_cohort_vectors"]:
        inp = vec["input"]
        live_resp = _eval_live_oracle(oracle_bin, {"kind": "drift_cohort", **inp})
        actual_c = detect_cohort_drift(
            [_build_run_record_from_provenance(r) for r in inp["baseline_runs"]],
            [_build_run_record_from_provenance(r) for r in inp["candidate_runs"]],
        )
        _assert_warnings_match(actual_c, live_resp["warnings"], label=f"live:{vec['case_id']}")

    # 5. Live OLS shift & time-reversal sweep on a 5-point asymmetric series
    asymmetric = [0.25, 0.40, 0.35, 0.70, 0.85]
    for tag, series in (
        ("orig", asymmetric),
        ("shifted", [round_score(y + 0.10) for y in asymmetric]),
        ("reversed", list(reversed(asymmetric))),
    ):
        runs_payload = [
            {
                "run_id": f"r-{idx}",
                "timestamp_key": (idx + 1) * 60,
                "dataset_id": "ds-sweep",
                "model_id": "m-1",
                "metric_scores": [{"metric_id": "m", "score": _float_to_rat_json(val)}],
                "provenance": {
                    "run_id": f"r-{idx}",
                    "dataset_fingerprint": "fp-sweep",
                    "metric_versions": [{"key": "m", "value": "1.0.0"}],
                    "judge_config_fingerprint": None,
                    "embedding_config_fingerprint": None,
                    "dataset_capped": False,
                    "case_ids": ["c1"],
                    "system_version": "v1",
                    "model_id": "m-1",
                    "config_fingerprint": "cfg-1",
                },
            }
            for idx, val in enumerate(series)
        ]
        req = {
            "kind": "trend_case",
            "runs": runs_payload,
            "window": 5,
            "dataset_id": None,
            "all_datasets": False,
            "model_id": None,
            "metric_ids": None,
            "slope_threshold": {"num": 1, "den": 100},
        }
        live_resp = _eval_live_oracle(oracle_bin, req)
        py_report = analyze_trend(
            [_build_manifest_from_trend_entry(r) for r in runs_payload],
            window=5,
            slope_threshold=0.01,
        )
        _assert_trend_report_matches(py_report, live_resp, label=f"live-sweep:{tag}")


def test_live_oracle_malformed_inputs_and_cli_fail_closed(request: pytest.FixtureRequest) -> None:
    """Confirm malformed stdin payloads and invalid CLI arguments fail closed (exit != 0)."""
    if not request.config.getoption("--lean-live-oracle"):
        pytest.skip("Pass --lean-live-oracle to execute live Lean regression oracle verification.")

    oracle_bin = _resolve_oracle_bin(request)

    # Unknown CLI subcommand
    bad_cli = _run_live_oracle(oracle_bin, ["unknown-subcmd"])
    assert bad_cli.returncode != 0
    assert "Usage:" in bad_cli.stderr

    golden = _load_golden()
    base_anomaly = golden["anomaly_vectors"][0]["input"]
    base_trend = golden["trend_vectors"][0]["input"]

    bad_payloads: list[str] = [
        "{not-json",
        json.dumps({"kind": "nonexistent_kind"}),
        # window < 2
        json.dumps({"kind": "trend_case", **{**base_trend, "window": 1}}),
        # slope_threshold == 0
        json.dumps(
            {
                "kind": "trend_case",
                **{**base_trend, "slope_threshold": {"num": 0, "den": 100}},
            }
        ),
        # slope_threshold > 1
        json.dumps(
            {
                "kind": "trend_case",
                **{**base_trend, "slope_threshold": {"num": 2, "den": 1}},
            }
        ),
        # slope_threshold den == 0
        json.dumps(
            {
                "kind": "trend_case",
                **{**base_trend, "slope_threshold": {"num": 1, "den": 0}},
            }
        ),
        # evaluated_case_count == 0
        json.dumps(
            {
                "kind": "anomaly_case",
                **{
                    **base_anomaly,
                    "run": {**base_anomaly["run"], "evaluated_case_count": 0},
                },
            }
        ),
        # out-of-range score > 1
        json.dumps(
            {
                "kind": "anomaly_case",
                **{
                    **base_anomaly,
                    "policy": {
                        **base_anomaly["policy"],
                        "disagreement_threshold": {"num": 101, "den": 100},
                    },
                },
            }
        ),
        # out-of-range delta < -1
        json.dumps(
            {
                "kind": "anomaly_case",
                **{
                    **base_anomaly,
                    "comparison": {
                        "metric_comparisons": [
                            {"metric_id": "m1", "delta": {"num": -101, "den": 100}}
                        ],
                        "case_comparisons": [],
                    },
                },
            }
        ),
    ]

    for payload_str in bad_payloads:
        proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=payload_str)
        assert proc.returncode != 0, f"Expected fail-closed rejection for: {payload_str!r}"
        assert proc.stderr.strip() != ""
