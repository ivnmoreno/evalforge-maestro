"""Dual-mode Python-to-Lean 4 conformance suite for QualityGate decision semantics.

Modes:
- Default (offline): validates `QualityGate.evaluate()`, `QualityGate.evaluate_cohort()`,
  and `_RuleRecorder` partitioning deterministically against the CI-verified golden oracle
  artifact (`tests/conformance/golden/quality_gate_oracle.json`) without requiring Lean.
- Live (`pytest --lean-live-oracle`): fail-closed mode that requires the compiled Lean
  oracle executable (`formal/.lake/build/bin/evalforge-gate-oracle`), verifies byte-for-byte
  parity with `quality_gate_oracle.json` via `export-golden`, and cross-checks every
  exercised Python case directly against `evalforge-gate-oracle eval-stdin`.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import FLOAT_EPSILON
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.regression.compare import compare_run_cohorts, compare_runs
from evalforge_maestro.regression.gate import QualityGate, _RuleRecorder
from evalforge_maestro.regression.trend import analyze_trend
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    ExecutionResult,
    GateDecision,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    QualityGateResult,
    RunManifestEntry,
    RunRecord,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ORACLE_PATH = Path(__file__).resolve().parent / "golden" / "quality_gate_oracle.json"
LEAN_TOOLCHAIN_PATH = REPO_ROOT / "formal" / "lean-toolchain"
EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_TOOLCHAIN = "leanprover/lean4:v4.36.0"
EXPECTED_PRECEDENCE_ORDER = ["FAIL", "INCONCLUSIVE", "WARNING", "PASS"]
VALID_DECISIONS = frozenset(EXPECTED_PRECEDENCE_ORDER)
ALL_EIGHT_PRESENCE_STATES: tuple[tuple[bool, bool, bool], ...] = (
    (False, False, False),
    (False, False, True),
    (False, True, False),
    (False, True, True),
    (True, False, False),
    (True, False, True),
    (True, True, False),
    (True, True, True),
)


def _expected_decision_for_presence(
    has_failures: bool,
    has_inconclusive: bool,
    has_warnings: bool,
) -> str:
    if has_failures:
        return "FAIL"
    if has_inconclusive:
        return "INCONCLUSIVE"
    if has_warnings:
        return "WARNING"
    return "PASS"


def validate_golden_artifact(
    payload: dict[str, Any],
) -> dict[tuple[bool, bool, bool], dict[str, Any]]:
    """Validate `GoldenOracleArtifact` structure and return indexed 8-state truth table."""
    assert payload.get("schema_version") == EXPECTED_SCHEMA_VERSION, (
        f"Unexpected golden schema_version: {payload.get('schema_version')!r}"
    )
    toolchain = payload.get("lean_toolchain")
    assert toolchain == EXPECTED_TOOLCHAIN, (
        f"Unexpected golden lean_toolchain: {toolchain!r} (expected {EXPECTED_TOOLCHAIN!r})"
    )
    if LEAN_TOOLCHAIN_PATH.exists():
        pinned = LEAN_TOOLCHAIN_PATH.read_text(encoding="utf-8").strip()
        assert toolchain == pinned, (
            f"Golden lean_toolchain {toolchain!r} diverges from formal/lean-toolchain {pinned!r}"
        )

    assert payload.get("precedence_order") == EXPECTED_PRECEDENCE_ORDER, (
        f"Unexpected precedence_order: {payload.get('precedence_order')!r}"
    )

    raw_table = payload.get("reason_presence_truth_table")
    table_desc = len(raw_table) if isinstance(raw_table, list) else type(raw_table)
    assert isinstance(raw_table, list) and len(raw_table) == 8, (
        f"Expected exactly 8 truth table entries, got {table_desc}"
    )

    indexed: dict[tuple[bool, bool, bool], dict[str, Any]] = {}
    observed_order: list[tuple[bool, bool, bool]] = []
    for entry in raw_table:
        assert isinstance(entry, dict), f"TruthTableEntry must be dict, got {type(entry)}"
        hf = entry.get("has_failures")
        hi = entry.get("has_inconclusive")
        hw = entry.get("has_warnings")
        decision = entry.get("decision")
        passed = entry.get("passed")
        blocking = entry.get("blocking")
        assert isinstance(hf, bool) and isinstance(hi, bool) and isinstance(hw, bool)
        assert isinstance(decision, str) and decision in VALID_DECISIONS
        assert isinstance(passed, bool) and isinstance(blocking, bool)

        expected_dec = _expected_decision_for_presence(hf, hi, hw)
        assert decision == expected_dec, (
            f"Tampered/inconsistent truth table decision for {(hf, hi, hw)}: "
            f"got {decision!r}, expected {expected_dec!r}"
        )
        assert passed is (decision == "PASS"), (
            f"Tampered/inconsistent passed flag for {(hf, hi, hw)}: {passed!r}"
        )
        assert blocking is (decision == "FAIL"), (
            f"Tampered/inconsistent blocking flag for {(hf, hi, hw)}: {blocking!r}"
        )

        key = (hf, hi, hw)
        observed_order.append(key)
        indexed[key] = entry

    assert tuple(observed_order) == ALL_EIGHT_PRESENCE_STATES, (
        f"Truth table ordering mismatch: {observed_order!r}"
    )

    vectors = payload.get("rule_check_vectors")
    assert isinstance(vectors, list) and len(vectors) >= 8, (
        "rule_check_vectors must be a non-empty list of canonical sequences"
    )
    for vec in vectors:
        assert isinstance(vec, dict)
        assert isinstance(vec.get("vector_id"), str) and vec["vector_id"]
        assert isinstance(vec.get("checks"), list)
        assert isinstance(vec.get("expected_failure_count"), int)
        assert isinstance(vec.get("expected_inconclusive_count"), int)
        assert isinstance(vec.get("expected_warning_count"), int)
        assert vec.get("decision") in VALID_DECISIONS
        assert isinstance(vec.get("passed"), bool)
        assert isinstance(vec.get("blocking"), bool)

    return indexed


def load_golden_artifact() -> tuple[
    bytes, dict[str, Any], dict[tuple[bool, bool, bool], dict[str, Any]]
]:
    """Load and validate the checked-in `GoldenOracleArtifact`."""
    raw_bytes = GOLDEN_ORACLE_PATH.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))
    assert isinstance(payload, dict)
    truth_table = validate_golden_artifact(payload)
    return raw_bytes, payload, truth_table


def assert_golden_parity(expected_bytes: bytes, actual_bytes: bytes) -> None:
    """Assert byte-for-byte deterministic parity between live Lean output and golden JSON."""
    if expected_bytes != actual_bytes:
        raise AssertionError(
            "Golden oracle artifact drift detected: checked-in "
            f"{GOLDEN_ORACLE_PATH.name} does not match compiled Lean oracle output."
        )


def require_live_oracle_binary(raw_path: str | Path) -> Path:
    """Resolve and verify the compiled Lean oracle binary fail-closed (never falls back)."""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if not candidate.exists() or not candidate.is_file():
        raise AssertionError(
            f"Live Lean oracle mode (--lean-live-oracle) failed closed: binary not found at "
            f"{candidate}. Build it first with `cd formal && lake build`."
        )
    if not os.access(candidate, os.X_OK):
        raise AssertionError(
            "Live Lean oracle mode (--lean-live-oracle) failed closed: "
            f"{candidate} is not executable."
        )
    return candidate


def resolve_optional_live_oracle(request: pytest.FixtureRequest) -> Path | None:
    """Return verified live oracle binary when `--lean-live-oracle` is set, else `None`."""
    live_enabled = bool(request.config.getoption("--lean-live-oracle"))
    if not live_enabled:
        return None
    bin_opt = str(request.config.getoption("--lean-oracle-bin"))
    return require_live_oracle_binary(bin_opt)


def run_live_oracle_export_golden(oracle_bin: Path) -> bytes:
    """Invoke `evalforge-gate-oracle export-golden` fail-closed."""
    proc = subprocess.run(
        [str(oracle_bin), "export-golden"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"evalforge-gate-oracle export-golden failed (exit={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout


def run_live_oracle_eval_stdin(oracle_bin: Path, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke `evalforge-gate-oracle eval-stdin` fail-closed with a batched JSON request."""
    proc = subprocess.run(
        [str(oracle_bin), "eval-stdin"],
        input=json.dumps(request_payload).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"evalforge-gate-oracle eval-stdin failed (exit={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    response = json.loads(proc.stdout.decode("utf-8"))
    assert isinstance(response, dict)
    assert response.get("schema_version") == EXPECTED_SCHEMA_VERSION
    return response


def assert_result_conforms(
    result: QualityGateResult,
    *,
    expected_decision: str,
    expected_passed: bool,
    expected_blocking: bool,
    context: str,
) -> None:
    """Compare Python `QualityGateResult` against formal reference decision and derived flags."""
    reason_signature = (
        bool(result.failure_reasons),
        bool(result.inconclusive_reasons),
        bool(result.warning_reasons),
    )
    if (
        result.decision.value != expected_decision
        or result.passed is not expected_passed
        or result.blocking is not expected_blocking
    ):
        py_summary = (
            f"decision={result.decision.value}, passed={result.passed}, blocking={result.blocking}"
        )
        formal_summary = (
            f"decision={expected_decision}, passed={expected_passed}, blocking={expected_blocking}"
        )
        raise AssertionError(
            f"Python-to-Lean conformance mismatch in {context}: "
            f"reason_state(fail, inconclusive, warning)={reason_signature}, "
            f"python=({py_summary}), formal=({formal_summary})."
        )


def assert_rule_recorder_parity(result: QualityGateResult, *, context: str) -> None:
    """Assert `_RuleRecorder` partitioning parity between `checks` and the three reason lists."""
    expected_failures = [c.message for c in result.checks if c.status == GateDecision.FAIL]
    expected_inconclusives = [
        c.message for c in result.checks if c.status == GateDecision.INCONCLUSIVE
    ]
    expected_warnings = [c.message for c in result.checks if c.status == GateDecision.WARNING]

    assert result.failure_reasons == expected_failures, (
        f"{context}: failure_reasons mismatch with FAIL checks"
    )
    assert result.inconclusive_reasons == expected_inconclusives, (
        f"{context}: inconclusive_reasons mismatch with INCONCLUSIVE checks"
    )
    assert result.warning_reasons == expected_warnings, (
        f"{context}: warning_reasons mismatch with WARNING checks"
    )


def _build_run(
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
        timestamp=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc),
        package_version="0.3.0",
        dataset_id="ds-conformance",
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


def _cross_check_results_with_live_oracle(
    oracle_bin: Path,
    labeled_results: list[tuple[str, QualityGateResult]],
) -> None:
    """Batch Python `QualityGateResult` reason lists and checks through live `eval-stdin`."""
    req_payload: dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "reason_cases": [
            {
                "case_id": case_id,
                "failure_reasons": res.failure_reasons,
                "inconclusive_reasons": res.inconclusive_reasons,
                "warning_reasons": res.warning_reasons,
            }
            for case_id, res in labeled_results
        ],
        "check_cases": [
            {
                "case_id": case_id,
                "checks": [
                    {"status": chk.status.value, "message": chk.message} for chk in res.checks
                ],
            }
            for case_id, res in labeled_results
        ],
    }
    response = run_live_oracle_eval_stdin(oracle_bin, req_payload)
    reason_by_id = {entry["case_id"]: entry for entry in response["reason_results"]}
    check_by_id = {entry["case_id"]: entry for entry in response["check_results"]}

    for case_id, res in labeled_results:
        r_out = reason_by_id[case_id]
        assert_result_conforms(
            res,
            expected_decision=r_out["decision"],
            expected_passed=r_out["passed"],
            expected_blocking=r_out["blocking"],
            context=f"live-oracle reason_case {case_id}",
        )
        c_out = check_by_id[case_id]
        assert_result_conforms(
            res,
            expected_decision=c_out["decision"],
            expected_passed=c_out["passed"],
            expected_blocking=c_out["blocking"],
            context=f"live-oracle check_case {case_id}",
        )
        assert c_out["failure_count"] == len(res.failure_reasons)
        assert c_out["inconclusive_count"] == len(res.inconclusive_reasons)
        assert c_out["warning_count"] == len(res.warning_reasons)


def test_golden_artifact_schema_and_live_parity(request: pytest.FixtureRequest) -> None:
    """Validate checked-in golden artifact and verify live `export-golden` parity when enabled."""
    raw_bytes, _, truth_table = load_golden_artifact()
    assert len(truth_table) == 8

    oracle_bin = resolve_optional_live_oracle(request)
    if oracle_bin is not None:
        live_bytes = run_live_oracle_export_golden(oracle_bin)
        assert_golden_parity(live_bytes, raw_bytes)


def test_exhaustive_eight_reason_presence_states_conformance(
    request: pytest.FixtureRequest,
) -> None:
    """Verify all 8/8 `(fail, inconclusive, warning)` states via real `QualityGate.evaluate()`."""
    _, _, truth_table = load_golden_artifact()

    fixtures: list[tuple[tuple[bool, bool, bool], str, QualityGateResult]] = []

    def _run_for(score: float, *, dataset_capped: bool = False) -> RunRecord:
        return _build_run(
            f"run-{score}-{dataset_capped}",
            dataset_capped=dataset_capped,
            cases=[("c1", False, {"exact_match": (score, MetricStatus.PASS, "1.0.0")}, [])],
        )

    # All 8 combinations of (has_failures, has_inconclusive, has_warnings)
    specs: list[tuple[tuple[bool, bool, bool], str, RunRecord, QualityGatePolicy]] = [
        ((False, False, False), "state_000_pass", _run_for(1.0), QualityGatePolicy(min_score=0.8)),
        (
            (False, False, True),
            "state_001_warning",
            _run_for(1.0, dataset_capped=True),
            QualityGatePolicy(min_score=0.8),
        ),
        (
            (False, True, False),
            "state_010_inconclusive",
            _run_for(1.0),
            QualityGatePolicy(min_score=0.8, require_baseline=True),
        ),
        (
            (False, True, True),
            "state_011_inconclusive_over_warning",
            _run_for(1.0, dataset_capped=True),
            QualityGatePolicy(min_score=0.8, require_baseline=True),
        ),
        ((True, False, False), "state_100_fail", _run_for(0.4), QualityGatePolicy(min_score=0.8)),
        (
            (True, False, True),
            "state_101_fail_over_warning",
            _run_for(0.4, dataset_capped=True),
            QualityGatePolicy(min_score=0.8),
        ),
        (
            (True, True, False),
            "state_110_fail_over_inconclusive",
            _run_for(0.4),
            QualityGatePolicy(min_score=0.8, require_baseline=True),
        ),
        (
            (True, True, True),
            "state_111_fail_over_all",
            _run_for(0.4, dataset_capped=True),
            QualityGatePolicy(min_score=0.8, require_baseline=True),
        ),
    ]

    seen_signatures: set[tuple[bool, bool, bool]] = set()
    labeled_results: list[tuple[str, QualityGateResult]] = []

    for expected_sig, case_id, run, policy in specs:
        res = QualityGate(policy).evaluate(run)
        observed_sig = (
            bool(res.failure_reasons),
            bool(res.inconclusive_reasons),
            bool(res.warning_reasons),
        )
        assert observed_sig == expected_sig, (
            f"Fixture {case_id} failed to realize target reason signature {expected_sig}: "
            f"got {observed_sig}"
        )
        seen_signatures.add(observed_sig)
        assert_rule_recorder_parity(res, context=case_id)

        oracle_row = truth_table[observed_sig]
        assert_result_conforms(
            res,
            expected_decision=oracle_row["decision"],
            expected_passed=oracle_row["passed"],
            expected_blocking=oracle_row["blocking"],
            context=f"golden truth table {case_id}",
        )
        fixtures.append((observed_sig, case_id, res))
        labeled_results.append((case_id, res))

    assert seen_signatures == set(ALL_EIGHT_PRESENCE_STATES)

    # Simultaneous FAIL + INCONCLUSIVE + WARNING must preserve all diagnostic lists
    all_three_res = next(res for sig, _, res in fixtures if sig == (True, True, True))
    assert all_three_res.failure_reasons
    assert all_three_res.inconclusive_reasons
    assert all_three_res.warning_reasons

    oracle_bin = resolve_optional_live_oracle(request)
    if oracle_bin is not None:
        _cross_check_results_with_live_oracle(oracle_bin, labeled_results)


def test_rule_recorder_partitioning_and_permutation_parity(
    request: pytest.FixtureRequest,
) -> None:
    """Verify `_RuleRecorder` partitioning counts and decision parity across canonical vectors."""
    _, payload, _ = load_golden_artifact()
    vectors: list[dict[str, Any]] = payload["rule_check_vectors"]

    live_check_cases: list[dict[str, Any]] = []
    observed_by_id: dict[str, tuple[int, int, int, str, bool, bool]] = {}

    for vec in vectors:
        recorder = _RuleRecorder()
        for idx, chk in enumerate(vec["checks"]):
            recorder.add(
                GateDecision(chk["status"]),
                f"vec:{vec['vector_id']}:{idx}",
                chk["message"],
            )

        assert len(recorder.failure_reasons) == vec["expected_failure_count"]
        assert len(recorder.inconclusive_reasons) == vec["expected_inconclusive_count"]
        assert len(recorder.warning_reasons) == vec["expected_warning_count"]

        if recorder.failure_reasons:
            decision = GateDecision.FAIL
        elif recorder.inconclusive_reasons:
            decision = GateDecision.INCONCLUSIVE
        elif recorder.warning_reasons:
            decision = GateDecision.WARNING
        else:
            decision = GateDecision.PASS

        passed = decision == GateDecision.PASS
        blocking = decision == GateDecision.FAIL

        assert decision.value == vec["decision"]
        assert passed is vec["passed"]
        assert blocking is vec["blocking"]

        observed_by_id[vec["vector_id"]] = (
            len(recorder.failure_reasons),
            len(recorder.inconclusive_reasons),
            len(recorder.warning_reasons),
            decision.value,
            passed,
            blocking,
        )
        live_check_cases.append({"case_id": vec["vector_id"], "checks": vec["checks"]})

    # Explicit permutation invariance check on canonical pairs
    assert (
        observed_by_id["warning_then_inconclusive"][3:]
        == (observed_by_id["inconclusive_then_warning_perm"][3:])
    )
    assert (
        observed_by_id["warning_inconclusive_fail"][3:]
        == (observed_by_id["fail_pass_warning_inconclusive_perm"][3:])
    )

    oracle_bin = resolve_optional_live_oracle(request)
    if oracle_bin is not None:
        resp = run_live_oracle_eval_stdin(
            oracle_bin,
            {
                "schema_version": EXPECTED_SCHEMA_VERSION,
                "reason_cases": [],
                "check_cases": live_check_cases,
            },
        )
        for item in resp["check_results"]:
            obs = observed_by_id[item["case_id"]]
            assert obs == (
                item["failure_count"],
                item["inconclusive_count"],
                item["warning_count"],
                item["decision"],
                item["passed"],
                item["blocking"],
            )


def test_boundary_escalation_and_cohort_conformance(request: pytest.FixtureRequest) -> None:
    """Verify epsilon boundaries, NOT_APPLICABLE vs zero-evidence, escalations, and cohorts."""
    _, _, truth_table = load_golden_artifact()
    labeled_results: list[tuple[str, QualityGateResult]] = []

    def _record(case_id: str, res: QualityGateResult, expected: GateDecision) -> None:
        assert res.decision == expected, (
            f"Scenario {case_id} expected {expected.value}, got {res.decision.value}"
        )
        labeled_results.append((case_id, res))

    # 1. min_score epsilon boundary
    run_floor_pass = _build_run(
        "floor-pass",
        cases=[
            (
                "c1",
                False,
                {"exact_match": (0.8 - FLOAT_EPSILON * 0.5, MetricStatus.PASS, "1.0.0")},
                [],
            )
        ],
    )
    run_floor_fail = _build_run(
        "floor-fail",
        cases=[("c1", False, {"exact_match": (0.7999, MetricStatus.PASS, "1.0.0")}, [])],
    )
    _record(
        "floor_epsilon_pass",
        QualityGate(QualityGatePolicy(min_score=0.8)).evaluate(run_floor_pass),
        GateDecision.PASS,
    )
    _record(
        "floor_epsilon_fail",
        QualityGate(QualityGatePolicy(min_score=0.8)).evaluate(run_floor_fail),
        GateDecision.FAIL,
    )

    # 2. max_regression_drop boundary (exact 0.05 passes, 0.06 fails)
    base_reg = _build_run(
        "reg-base",
        cases=[("c1", False, {"exact_match": (0.90, MetricStatus.PASS, "1.0.0")}, [])],
    )
    cand_reg_ok = _build_run(
        "reg-ok",
        cases=[("c1", False, {"exact_match": (0.85, MetricStatus.PASS, "1.0.0")}, [])],
    )
    cand_reg_fail = _build_run(
        "reg-fail",
        cases=[("c1", False, {"exact_match": (0.84, MetricStatus.PASS, "1.0.0")}, [])],
    )
    reg_policy = QualityGatePolicy(max_regression_drop=0.05)
    _record(
        "regression_drop_boundary_pass",
        QualityGate(reg_policy).evaluate(
            cand_reg_ok, comparison=compare_runs(base_reg, cand_reg_ok)
        ),
        GateDecision.PASS,
    )
    _record(
        "regression_drop_boundary_fail",
        QualityGate(reg_policy).evaluate(
            cand_reg_fail, comparison=compare_runs(base_reg, cand_reg_fail)
        ),
        GateDecision.FAIL,
    )

    # 3. max_inconclusive_rate boundary (0.10 == limit -> WARNING; 0.20 > limit -> INCONCLUSIVE)
    def _inc_run(run_id: str, inc_count: int) -> RunRecord:
        cases_list: list[
            tuple[str, bool, dict[str, tuple[float | None, MetricStatus, str]], list[str]]
        ] = []
        for idx in range(10):
            if idx < inc_count:
                cases_list.append(
                    (
                        f"c{idx}",
                        False,
                        {"exact_match": (None, MetricStatus.INCONCLUSIVE, "1.0.0")},
                        [],
                    )
                )
            else:
                cases_list.append(
                    (f"c{idx}", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, [])
                )
        return _build_run(run_id, cases=cases_list)

    inc_policy = QualityGatePolicy(max_inconclusive_rate=0.10)
    _record(
        "inconclusive_rate_at_limit_warn",
        QualityGate(inc_policy).evaluate(_inc_run("inc-1", 1)),
        GateDecision.WARNING,
    )
    _record(
        "inconclusive_rate_over_limit_inc",
        QualityGate(inc_policy).evaluate(_inc_run("inc-2", 2)),
        GateDecision.INCONCLUSIVE,
    )

    # 4. Optional NOT_APPLICABLE metric vs zero applicable numeric evidence
    run_opt_na = _build_run(
        "opt-na",
        cases=[
            (
                "c1",
                False,
                {
                    "exact_match": (1.0, MetricStatus.PASS, "1.0.0"),
                    "precision_at_k": (None, MetricStatus.NOT_APPLICABLE, "1.0.0"),
                },
                [],
            )
        ],
    )
    run_zero_ev = _build_run(
        "zero-ev",
        cases=[("c1", False, {"exact_match": (None, MetricStatus.NOT_APPLICABLE, "1.0.0")}, [])],
    )
    _record("optional_not_applicable_pass", QualityGate().evaluate(run_opt_na), GateDecision.PASS)
    _record(
        "zero_applicable_evidence_inc",
        QualityGate().evaluate(run_zero_ev),
        GateDecision.INCONCLUSIVE,
    )

    # 5. Mandatory failure alongside warnings and inconclusive reasons
    run_mand_all = _build_run(
        "mand-all",
        dataset_capped=True,
        cases=[
            ("m1", True, {"exact_match": (0.0, MetricStatus.FAIL, "1.0.0")}, []),
            ("c2", False, {"exact_match": (None, MetricStatus.INCONCLUSIVE, "1.0.0")}, ["err"]),
        ],
    )
    mand_res = QualityGate(QualityGatePolicy(max_inconclusive_rate=0.1)).evaluate(run_mand_all)
    _record("mandatory_fail_with_warn_and_inc", mand_res, GateDecision.FAIL)
    assert mand_res.failure_reasons and mand_res.inconclusive_reasons and mand_res.warning_reasons

    # 6. Policy escalations: drift, anomaly, degrading trend, and statistical significance
    base_d = _build_run(
        "drift-base",
        cases=[("c1", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, [])],
    )
    cand_d = _build_run(
        "drift-cand",
        dataset_fp="f" * 64,
        cases=[("c1", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, [])],
    )
    comp_d = compare_runs(base_d, cand_d)
    _record("drift_warn", QualityGate().evaluate(cand_d, comparison=comp_d), GateDecision.WARNING)
    _record(
        "drift_fail",
        QualityGate(QualityGatePolicy(fail_on_drift=True)).evaluate(cand_d, comparison=comp_d),
        GateDecision.FAIL,
    )

    run_capped = _build_run(
        "anom-capped",
        dataset_capped=True,
        cases=[("c1", False, {"exact_match": (1.0, MetricStatus.PASS, "1.0.0")}, [])],
    )
    _record("anomaly_warn", QualityGate().evaluate(run_capped), GateDecision.WARNING)
    _record(
        "anomaly_fail",
        QualityGate(QualityGatePolicy(fail_on_anomaly=True)).evaluate(run_capped),
        GateDecision.FAIL,
    )

    degrading_trend = analyze_trend(
        [
            RunManifestEntry(
                run_id=f"tr-{i}",
                timestamp=datetime(2026, 11, 24, 10, i, tzinfo=timezone.utc),
                package_version="0.3.0",
                dataset_id="ds-conformance",
                dataset_fingerprint="a" * 64,
                evaluated_case_count=1,
                metric_versions={"exact_match": "1.0.0"},
                aggregate_scores={"exact_match": 0.9 - 0.05 * i},
                status_counts={MetricStatus.PASS: 1},
            )
            for i in range(3)
        ]
    )
    _record(
        "trend_warn", QualityGate().evaluate(base_d, trend=degrading_trend), GateDecision.WARNING
    )
    _record(
        "trend_fail",
        QualityGate(QualityGatePolicy(fail_on_degrading_trend=True)).evaluate(
            base_d, trend=degrading_trend
        ),
        GateDecision.FAIL,
    )

    base_stat = _build_run(
        "stat-b",
        cases=[
            (f"c{i}", False, {"exact_match": (0.90, MetricStatus.PASS, "1.0.0")}, [])
            for i in range(5)
        ],
    )
    cand_stat = _build_run(
        "stat-c",
        cases=[
            (f"c{i}", False, {"exact_match": (0.88, MetricStatus.PASS, "1.0.0")}, [])
            for i in range(5)
        ],
    )
    comp_stat = compare_runs(
        base_stat, cand_stat, policy=QualityGatePolicy(max_regression_drop=0.05)
    )
    _record(
        "stat_sig_warn",
        QualityGate(
            QualityGatePolicy(max_regression_drop=0.05, fail_on_significant_regression=False)
        ).evaluate(cand_stat, comparison=comp_stat),
        GateDecision.WARNING,
    )
    _record(
        "stat_sig_fail",
        QualityGate(
            QualityGatePolicy(max_regression_drop=0.05, fail_on_significant_regression=True)
        ).evaluate(cand_stat, comparison=comp_stat),
        GateDecision.FAIL,
    )

    # 7. Multi-run cohort evaluation (PASS, WARNING, FAIL)
    base_cohorts = [
        _build_run(
            f"cb-{i}",
            cases=[("c1", False, {"exact_match": (score, MetricStatus.PASS, "1.0.0")}, [])],
        )
        for i, score in enumerate((0.90, 0.905, 0.91), start=1)
    ]
    cand_cohorts = [
        _build_run(
            f"cc-{i}",
            cases=[("c1", False, {"exact_match": (score, MetricStatus.PASS, "1.0.0")}, [])],
        )
        for i, score in enumerate((0.88, 0.885, 0.89), start=1)
    ]
    coh_cmp = compare_run_cohorts(base_cohorts, cand_cohorts)
    _record(
        "cohort_pass",
        QualityGate(QualityGatePolicy(min_score=0.85)).evaluate_cohort(cand_cohorts),
        GateDecision.PASS,
    )
    _record(
        "cohort_stat_warn",
        QualityGate(QualityGatePolicy(max_regression_drop=0.05)).evaluate_cohort(
            cand_cohorts, comparison=coh_cmp
        ),
        GateDecision.WARNING,
    )
    _record(
        "cohort_stat_fail",
        QualityGate(
            QualityGatePolicy(max_regression_drop=0.05, fail_on_significant_regression=True)
        ).evaluate_cohort(cand_cohorts, comparison=coh_cmp),
        GateDecision.FAIL,
    )

    # Pre-aggregation ConfigurationError guards remain untouched
    with pytest.raises(ConfigurationError):
        QualityGate().evaluate(base_d, comparison=comp_d)
    with pytest.raises(ConfigurationError):
        QualityGate().evaluate_cohort([])

    # Validate every scenario against golden truth table and _RuleRecorder parity
    for case_id, res in labeled_results:
        assert_rule_recorder_parity(res, context=case_id)
        sig = (
            bool(res.failure_reasons),
            bool(res.inconclusive_reasons),
            bool(res.warning_reasons),
        )
        oracle_row = truth_table[sig]
        assert_result_conforms(
            res,
            expected_decision=oracle_row["decision"],
            expected_passed=oracle_row["passed"],
            expected_blocking=oracle_row["blocking"],
            context=f"golden scenario {case_id}",
        )

    oracle_bin = resolve_optional_live_oracle(request)
    if oracle_bin is not None:
        _cross_check_results_with_live_oracle(oracle_bin, labeled_results)


def test_negative_fault_detection_python_mismatch_stale_golden_and_fail_closed(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    """Verify negative detection: Python mismatches, tampered golden JSON, and missing binary."""
    raw_bytes, payload, truth_table = load_golden_artifact()

    # (a) Simulated Python semantic mismatch (WARNING when inconclusive_reasons is non-empty)
    simulated_wrong_result = QualityGateResult(
        decision=GateDecision.WARNING,
        candidate_run_id="sim-drift",
        passed=False,
        blocking=False,
        inconclusive_rate=0.25,
        checks=[],
        failure_reasons=[],
        inconclusive_reasons=["Required baseline missing"],
        warning_reasons=["Minor warning"],
        summary="Simulated semantic drift",
    )
    sig = (
        bool(simulated_wrong_result.failure_reasons),
        bool(simulated_wrong_result.inconclusive_reasons),
        bool(simulated_wrong_result.warning_reasons),
    )
    oracle_row = truth_table[sig]
    with pytest.raises(
        AssertionError, match=r"python=\(decision=WARNING.*formal=\(decision=INCONCLUSIVE"
    ):
        assert_result_conforms(
            simulated_wrong_result,
            expected_decision=oracle_row["decision"],
            expected_passed=oracle_row["passed"],
            expected_blocking=oracle_row["blocking"],
            context="negative_mismatch_probe",
        )

    # (b) Offline tampered golden schema / truth-table invariant & parity-helper rejection
    tampered_payload = copy.deepcopy(payload)
    tampered_payload["reason_presence_truth_table"][3]["decision"] = "WARNING"
    with pytest.raises(AssertionError, match="Tampered/inconsistent truth table decision"):
        validate_golden_artifact(tampered_payload)

    tampered_bytes = json.dumps(tampered_payload, indent=2).encode("utf-8") + b"\n"
    with pytest.raises(AssertionError, match="Golden oracle artifact drift detected"):
        assert_golden_parity(raw_bytes, tampered_bytes)

    # (c) Fail-closed missing live-oracle binary never falls back to offline golden mode
    missing_bin = tmp_path / "nonexistent-evalforge-gate-oracle"
    with pytest.raises(AssertionError, match="failed closed: binary not found"):
        require_live_oracle_binary(missing_bin)

    # (d) Live-oracle negative checks when --lean-live-oracle is active
    oracle_bin = resolve_optional_live_oracle(request)
    if oracle_bin is not None:
        live_bytes = run_live_oracle_export_golden(oracle_bin)
        with pytest.raises(AssertionError, match="Golden oracle artifact drift detected"):
            assert_golden_parity(live_bytes, tampered_bytes)

        bad_status_proc = subprocess.run(
            [str(oracle_bin), "eval-stdin"],
            input=json.dumps(
                {
                    "schema_version": EXPECTED_SCHEMA_VERSION,
                    "reason_cases": [],
                    "check_cases": [
                        {
                            "case_id": "invalid",
                            "checks": [{"status": "BOGUS", "message": "bad"}],
                        }
                    ],
                }
            ).encode("utf-8"),
            check=False,
            capture_output=True,
        )
        assert bad_status_proc.returncode != 0
        assert "Invalid GateDecision status string" in bad_status_proc.stderr.decode("utf-8")

        bad_cmd_proc = subprocess.run(
            [str(oracle_bin), "unknown-subcommand"],
            check=False,
            capture_output=True,
        )
        assert bad_cmd_proc.returncode == 2
