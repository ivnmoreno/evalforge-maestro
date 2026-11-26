"""Dual-mode Python-to-Lean conformance suite for Deterministic Agent Trace & Tool-Use Metrics.

Default mode validates Python's six AST-pinned agent metric classes (`ToolSelectionMetric`,
`ArgumentCorrectnessMetric`, `ExecutionSequenceMetric`, `ToolEfficiencyMetric`,
`PolicyComplianceMetric`, `FailureRecoveryMetric`), `_prepare_agent_inputs`, and
`_resolve_threshold` offline against the checked-in Lean oracle golden fixture
(`tests/conformance/golden/agent_metrics_oracle.json`).

Live mode (`--lean-live-oracle`) additionally executes the compiled Lean binary
(`evalforge-agent-oracle`) fail-closed to verify byte-for-byte golden parity, evaluate
canonical, threshold, permutation, duplication, suffix-extension, schema, and policy sweeps
via stdin/stdout, and confirm malformed payloads fail closed.
"""

from __future__ import annotations

import copy
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

import jsonschema
import pytest

from evalforge_maestro._canonical import canonical_json_str, round_score
from evalforge_maestro.metrics.agent import (
    ArgumentCorrectnessMetric,
    ExecutionSequenceMetric,
    FailureRecoveryMetric,
    PolicyComplianceMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
    _prepare_agent_inputs,
)
from evalforge_maestro.metrics.deterministic import _resolve_threshold
from evalforge_maestro.types import (
    AgentTraceStep,
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    ExpectedToolCall,
    MetricResult,
    MetricStatus,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_AGENT_PATH = Path(__file__).resolve().parent / "golden" / "agent_metrics_oracle.json"

_GOLDEN_SCHEMAS: dict[tuple[str, int], dict[str, Any]] = {
    ("argument_correctness_schema_and_dict_blend", 0): {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q", "must_exist"],
    },
    ("argument_correctness_parse_error_zero", 0): {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
    },
}


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
    raw = str(request.config.getoption("--lean-agent-oracle-bin"))
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
        raise FileNotFoundError(f"Lean agent oracle binary not found at: {oracle_bin}")
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
        f"evalforge-agent-oracle eval-stdin failed (exit={proc.returncode}): {proc.stderr}"
    )
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed


def _kv_list_to_dict(kvs: list[dict[str, str]]) -> dict[str, Any]:
    return {entry["key"]: json.loads(entry["value_json"]) for entry in kvs}


def _dict_to_kv_list(mapping: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": k, "value_json": canonical_json_str(mapping[k])} for k in sorted(mapping)]


def _build_criteria(raw: dict[str, Any]) -> CaseCriteria:
    metric_thresholds = {
        entry["metric_id"]: round_score(float(_rat_to_fraction(entry["threshold"])))
        for entry in raw["metric_thresholds"]
    }
    pass_thr_raw = raw["pass_threshold"]
    pass_thr = (
        round_score(float(_rat_to_fraction(pass_thr_raw))) if pass_thr_raw is not None else None
    )
    return CaseCriteria(
        metric_thresholds=metric_thresholds,
        pass_threshold=pass_thr,
        forbidden_tools=list(raw["forbidden_tools"]),
        forbidden_argument_patterns=list(raw["forbidden_arg_patterns"]),
        max_steps=raw["max_steps"],
        max_tool_calls=raw["max_tool_calls"],
        allow_redundant_failures=int(raw["allow_redundant_failures"]),
    )


def _build_tool_call(raw: dict[str, Any], *, verify_boundary: bool = True) -> ToolCallRecord:
    args_dict = _kv_list_to_dict(raw["arguments"])
    rec = ToolCallRecord(
        id=raw["id"],
        name=raw["name"],
        arguments=args_dict,
        argument_parse_error=raw["argument_parse_error"],
        status=ToolCallStatus(raw["status"]),
        error="call error" if raw["has_error"] else None,
        result="call result" if raw["has_result"] else None,
    )
    if verify_boundary:
        expected_sig = canonical_json_str(
            {"name": rec.name, "arguments": rec.arguments, "raw": rec.raw_arguments}
        )
        expected_blob = canonical_json_str(
            {"arguments": rec.arguments, "raw": rec.raw_arguments}
        ).casefold()
        assert expected_sig == raw["canonical_sig"], (
            f"Canonical signature boundary mismatch for {rec.name!r}: "
            f"{expected_sig!r} != {raw['canonical_sig']!r}"
        )
        assert expected_blob == raw["arg_blob_lower"]
        assert rec.name.casefold() == raw["name_lower"]
    return rec


def _build_trace_step(raw: dict[str, Any]) -> AgentTraceStep:
    nested = [_build_tool_call(nc) for nc in raw["tool_calls"]]
    status_raw = raw["status"]
    return AgentTraceStep(
        kind=TraceStepKind(raw["kind"]),
        name=raw["name"],
        tool_calls=nested,
        tool_call_id=raw["tool_call_id"],
        status=ToolCallStatus(status_raw) if status_raw is not None else None,
        error="step error" if raw["has_error"] else None,
        content="step content" if raw["has_content"] else None,
    )


def _build_expected_tool(
    case_id: str,
    exp_idx: int,
    raw: dict[str, Any],
) -> ExpectedToolCall:
    raw_args = raw["arguments"]
    args_dict = _kv_list_to_dict(raw_args) if raw_args is not None else None
    has_schema = bool(raw["has_schema"])
    schema = _GOLDEN_SCHEMAS.get((case_id, exp_idx)) if has_schema else None
    if has_schema:
        assert schema is not None, f"Missing golden JSON schema for ({case_id!r}, {exp_idx})"
    mode: Literal["subset", "exact"] = (
        "exact" if raw["argument_match_mode"] == "exact" else "subset"
    )
    return ExpectedToolCall(
        name=raw["name"],
        arguments=args_dict,
        arguments_schema=schema,
        argument_match_mode=mode,
        optional=bool(raw["optional"]),
        order=raw["order"],
    )


def _build_case_and_execution(
    inp: dict[str, Any],
) -> tuple[EvaluationCase, ExecutionResult]:
    case_id = str(inp["case_id"])
    expected_tools = [
        _build_expected_tool(case_id, idx, item) for idx, item in enumerate(inp["expected_tools"])
    ]
    criteria = _build_criteria(inp["criteria"])
    case = EvaluationCase(
        id=case_id,
        input=f"agent task {case_id}",
        expected_tools=expected_tools,
        criteria=criteria,
    )
    tool_calls = [_build_tool_call(tc) for tc in inp["tool_calls"]]
    trace = [_build_trace_step(step) for step in inp["trace"]]
    execution = ExecutionResult(
        case_id=case_id,
        input=f"agent task {case_id}",
        tool_calls=tool_calls,
        trace=trace,
        errors=list(inp["errors"]),
        elapsed_seconds=0.01,
    )
    return case, execution


def _assert_schema_results_match_jsonschema(
    case: EvaluationCase,
    execution: ExecutionResult,
    schema_results: list[dict[str, Any]],
) -> None:
    expected, prepared = _prepare_agent_inputs(case, execution)
    constrained = [
        item for item in expected if item.arguments is not None or item.arguments_schema is not None
    ]
    for entry in schema_results:
        exp = constrained[int(entry["constrained_exp_idx"])]
        call = prepared[int(entry["call_idx"])]
        assert exp.arguments_schema is not None
        try:
            jsonschema.validate(instance=call.arguments, schema=exp.arguments_schema)
            actual_valid = True
        except jsonschema.ValidationError:
            actual_valid = False
        assert actual_valid is bool(entry["valid"])


def _assert_metric_matches_oracle(
    actual: MetricResult,
    expected_oracle: dict[str, Any],
    *,
    label: str,
) -> None:
    assert actual.status.value == expected_oracle["status"], (
        f"[{label}] status mismatch: python={actual.status.value!r} "
        f"oracle={expected_oracle['status']!r}"
    )
    exp_score_frac = _opt_rat_to_fraction(expected_oracle["score_exact"])
    if exp_score_frac is None:
        assert actual.score is None, f"[{label}] expected None score, got {actual.score!r}"
    else:
        assert actual.score is not None, f"[{label}] expected numeric score, got None"
        assert actual.score == round_score(float(exp_score_frac)), (
            f"[{label}] score mismatch: python={actual.score!r} "
            f"oracle={round_score(float(exp_score_frac))!r} ({exp_score_frac})"
        )
    exp_thr_frac = _rat_to_fraction(expected_oracle["threshold_exact"])
    assert actual.config_snapshot["threshold"] == round_score(float(exp_thr_frac)), (
        f"[{label}] threshold mismatch: python={actual.config_snapshot['threshold']!r} "
        f"oracle={round_score(float(exp_thr_frac))!r}"
    )


def _evaluate_all_python_metrics(
    case: EvaluationCase,
    execution: ExecutionResult,
    inp: dict[str, Any],
) -> dict[str, MetricResult]:
    t_sel = round_score(float(_rat_to_fraction(inp["tool_selection_threshold"])))
    t_arg = round_score(float(_rat_to_fraction(inp["argument_correctness_threshold"])))
    t_seq = round_score(float(_rat_to_fraction(inp["execution_sequence_threshold"])))
    t_eff = round_score(float(_rat_to_fraction(inp["tool_efficiency_threshold"])))
    t_pol = round_score(float(_rat_to_fraction(inp["policy_compliance_threshold"])))
    t_rec = round_score(float(_rat_to_fraction(inp["failure_recovery_threshold"])))
    loop_penalty = float(_rat_to_fraction(inp["loop_penalty"]))

    return {
        "tool_selection_f1": ToolSelectionMetric(mode="f1", threshold=t_sel).evaluate(
            case, execution
        ),
        "tool_selection_recall": ToolSelectionMetric(mode="recall", threshold=t_sel).evaluate(
            case, execution
        ),
        "tool_selection_exact_set": ToolSelectionMetric(mode="exact_set", threshold=t_sel).evaluate(
            case, execution
        ),
        "argument_correctness_non_strict": ArgumentCorrectnessMetric(
            strict_mode=False, threshold=t_arg
        ).evaluate(case, execution),
        "argument_correctness_strict": ArgumentCorrectnessMetric(
            strict_mode=True, threshold=t_arg
        ).evaluate(case, execution),
        "execution_sequence_subsequence": ExecutionSequenceMetric(
            mode="subsequence", threshold=t_seq
        ).evaluate(case, execution),
        "execution_sequence_prefix": ExecutionSequenceMetric(
            mode="prefix", threshold=t_seq
        ).evaluate(case, execution),
        "execution_sequence_exact": ExecutionSequenceMetric(mode="exact", threshold=t_seq).evaluate(
            case, execution
        ),
        "tool_efficiency": ToolEfficiencyMetric(
            default_max_steps=inp["default_max_steps"],
            default_max_tool_calls=inp["default_max_calls"],
            allow_redundant_failures=int(inp["default_allow_redundant_failures"]),
            loop_penalty=loop_penalty,
            threshold=t_eff,
        ).evaluate(case, execution),
        "policy_compliance": PolicyComplianceMetric(
            forbidden_tools=tuple(inp["metric_forbidden_tools"]),
            forbidden_argument_patterns=tuple(inp["metric_forbidden_patterns"]),
            threshold=t_pol,
        ).evaluate(case, execution),
        "failure_recovery": FailureRecoveryMetric(threshold=t_rec).evaluate(case, execution),
    }


def _assert_case_matches_oracle_response(
    inp: dict[str, Any],
    expected_oracle: dict[str, Any],
) -> None:
    case, execution = _build_case_and_execution(inp)
    _assert_schema_results_match_jsonschema(case, execution, inp["schema_results"])

    _, prepared = _prepare_agent_inputs(case, execution)
    py_prepared_summary = [
        {
            "has_error": c.error is not None,
            "has_result": c.result is not None,
            "id": c.id,
            "name": c.name,
            "status": c.status.value,
        }
        for c in prepared
    ]
    assert py_prepared_summary == expected_oracle["prepared_calls"], (
        f"[{inp['case_id']}] prepared_calls mismatch: {py_prepared_summary!r} != "
        f"{expected_oracle['prepared_calls']!r}"
    )

    results = _evaluate_all_python_metrics(case, execution, inp)
    for key, metric_result in results.items():
        _assert_metric_matches_oracle(
            metric_result,
            expected_oracle[key],
            label=f"{inp['case_id']}:{key}",
        )


def _serialize_python_case_for_oracle(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    default_max_steps: int | None = None,
    default_max_calls: int | None = None,
    default_allow_redundant_failures: int = 0,
    loop_penalty: float = 0.5,
    metric_forbidden_tools: list[str] | None = None,
    metric_forbidden_patterns: list[str] | None = None,
) -> dict[str, Any]:
    expected_list, prepared = _prepare_agent_inputs(case, execution)
    constrained = [
        item
        for item in expected_list
        if item.arguments is not None or item.arguments_schema is not None
    ]
    schema_results: list[dict[str, Any]] = []
    for e_idx, exp in enumerate(constrained):
        if exp.arguments_schema is None:
            continue
        for c_idx, call in enumerate(prepared):
            try:
                jsonschema.validate(instance=call.arguments, schema=exp.arguments_schema)
                valid = True
            except jsonschema.ValidationError:
                valid = False
            schema_results.append({"constrained_exp_idx": e_idx, "call_idx": c_idx, "valid": valid})

    def _ser_call(c: ToolCallRecord) -> dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "name_lower": c.name.casefold(),
            "arguments": _dict_to_kv_list(c.arguments),
            "canonical_sig": canonical_json_str(
                {"name": c.name, "arguments": c.arguments, "raw": c.raw_arguments}
            ),
            "arg_blob_lower": canonical_json_str(
                {"arguments": c.arguments, "raw": c.raw_arguments}
            ).casefold(),
            "argument_parse_error": c.argument_parse_error,
            "status": c.status.value,
            "has_error": c.error is not None,
            "has_result": c.result is not None,
        }

    def _ser_step(s: AgentTraceStep) -> dict[str, Any]:
        sig = (
            canonical_json_str({"name": s.name, "arguments": {}, "raw": None})
            if s.name is not None
            else ""
        )
        return {
            "kind": s.kind.value,
            "name": s.name,
            "name_lower": s.name.casefold() if s.name is not None else None,
            "tool_calls": [_ser_call(nc) for nc in s.tool_calls],
            "tool_call_id": s.tool_call_id,
            "status": s.status.value if s.status is not None else None,
            "has_error": s.error is not None,
            "has_content": s.content is not None,
            "canonical_sig": sig,
            "arg_blob_lower": canonical_json_str({"arguments": {}, "raw": None}).casefold(),
        }

    criteria = case.criteria
    return {
        "kind": "agent_case",
        "case_id": case.id,
        "errors": list(execution.errors),
        "expected_tools": [
            {
                "name": e.name,
                "arguments": _dict_to_kv_list(e.arguments) if e.arguments is not None else None,
                "has_schema": e.arguments_schema is not None,
                "argument_match_mode": e.argument_match_mode,
                "optional": e.optional,
                "order": e.order,
            }
            for e in (case.expected_tools or [])
        ],
        "tool_calls": [_ser_call(c) for c in execution.tool_calls],
        "trace": [_ser_step(s) for s in execution.trace],
        "criteria": {
            "metric_thresholds": [
                {"metric_id": mid, "threshold": _float_to_rat_json(val)}
                for mid, val in sorted(criteria.metric_thresholds.items())
            ],
            "pass_threshold": (
                _float_to_rat_json(criteria.pass_threshold)
                if criteria.pass_threshold is not None
                else None
            ),
            "forbidden_tools": [t.casefold() for t in criteria.forbidden_tools],
            "forbidden_arg_patterns": [p.casefold() for p in criteria.forbidden_argument_patterns],
            "max_steps": criteria.max_steps,
            "max_tool_calls": criteria.max_tool_calls,
            "allow_redundant_failures": criteria.allow_redundant_failures,
        },
        "schema_results": schema_results,
        "default_max_steps": default_max_steps,
        "default_max_calls": default_max_calls,
        "default_allow_redundant_failures": default_allow_redundant_failures,
        "loop_penalty": _float_to_rat_json(loop_penalty),
        "metric_forbidden_tools": [t.casefold() for t in (metric_forbidden_tools or [])],
        "metric_forbidden_patterns": [p.casefold() for p in (metric_forbidden_patterns or [])],
        "tool_selection_threshold": _float_to_rat_json(0.8),
        "argument_correctness_threshold": _float_to_rat_json(0.8),
        "execution_sequence_threshold": _float_to_rat_json(1.0),
        "tool_efficiency_threshold": _float_to_rat_json(0.7),
        "policy_compliance_threshold": _float_to_rat_json(1.0),
        "failure_recovery_threshold": _float_to_rat_json(0.5),
    }


@pytest.fixture(scope="module")
def golden_agent_oracle() -> dict[str, Any]:
    """Load the deterministic Lean-exported golden agent metrics oracle artifact."""
    data: dict[str, Any] = json.loads(GOLDEN_AGENT_PATH.read_text(encoding="utf-8"))
    return data


def test_golden_agent_oracle_metadata_and_enum_coverage(
    golden_agent_oracle: dict[str, Any],
) -> None:
    """Verify golden fixture schema, Lean toolchain, canonical enums, and vector counts."""
    assert golden_agent_oracle["schema_version"] == "1.0"
    assert golden_agent_oracle["lean_toolchain"] == "leanprover/lean4:v4.36.0"
    assert golden_agent_oracle["tool_call_statuses"] == [s.value for s in ToolCallStatus]
    assert golden_agent_oracle["trace_step_kinds"] == [k.value for k in TraceStepKind]
    assert golden_agent_oracle["tool_selection_modes"] == ["f1", "recall", "exact_set"]
    assert golden_agent_oracle["sequence_modes"] == ["subsequence", "prefix", "exact"]
    assert len(golden_agent_oracle["threshold_resolution_vectors"]) == 4
    assert len(golden_agent_oracle["canonical_vectors"]) == 20


def test_threshold_resolution_matches_golden_oracle(
    golden_agent_oracle: dict[str, Any],
) -> None:
    """Confirm `_resolve_threshold` enforces 3-tier precedence across all golden vectors."""
    for vec in golden_agent_oracle["threshold_resolution_vectors"]:
        criteria = _build_criteria(vec["criteria"])
        case = EvaluationCase(id=vec["case_id"], input="q", criteria=criteria)
        def_thr = round_score(float(_rat_to_fraction(vec["default_threshold"])))
        actual = _resolve_threshold(case, vec["metric_id"], def_thr)
        expected = round_score(float(_rat_to_fraction(vec["expected_threshold_exact"])))
        assert actual == expected, f"Threshold mismatch on {vec['case_id']!r}"


def test_canonical_agent_vectors_match_golden_oracle(
    golden_agent_oracle: dict[str, Any],
) -> None:
    """Confirm all 6 Python agent metrics and `_prepare_agent_inputs` match all 20 vectors."""
    for vec in golden_agent_oracle["canonical_vectors"]:
        _assert_case_matches_oracle_response(vec["input"], vec["expected"])


def test_agent_metric_hierarchies_invariances_and_boundaries_offline() -> None:
    """Verify proved mathematical properties empirically across Python agent metrics."""
    # 1. tool_selection: order & duplicate invariance + harmonic-mean sandwich
    exp_tools = [
        ExpectedToolCall(name="search"),
        ExpectedToolCall(name="fetch"),
        ExpectedToolCall(name="audit", optional=True),
    ]
    case = EvaluationCase(id="inv-sel", input="q", expected_tools=exp_tools)
    calls_base = [ToolCallRecord(name="search"), ToolCallRecord(name="extra")]
    calls_perm_dup = [
        ToolCallRecord(name="extra"),
        ToolCallRecord(name="search"),
        ToolCallRecord(name="search"),
        ToolCallRecord(name="audit"),
    ]
    for mode in ("f1", "recall", "exact_set"):
        m = ToolSelectionMetric(mode=mode)
        r1 = m.evaluate(
            case,
            ExecutionResult(
                case_id="inv-sel", input="q", tool_calls=calls_base, elapsed_seconds=0.01
            ),
        )
        r2 = m.evaluate(
            case,
            ExecutionResult(
                case_id="inv-sel", input="q", tool_calls=calls_perm_dup, elapsed_seconds=0.01
            ),
        )
        assert r1.score == r2.score

    # 2. execution_sequence: exact <= prefix <= subsequence & suffix monotonicity
    seq_case = EvaluationCase(
        id="inv-seq",
        input="q",
        expected_tools=[
            ExpectedToolCall(name="a", order=0),
            ExpectedToolCall(name="b", order=1),
            ExpectedToolCall(name="c", order=2),
        ],
    )
    base_calls = [ToolCallRecord(name="a"), ToolCallRecord(name="c")]
    ext_calls = [*base_calls, ToolCallRecord(name="b"), ToolCallRecord(name="c")]
    exec_base = ExecutionResult(
        case_id="inv-seq", input="q", tool_calls=base_calls, elapsed_seconds=0.01
    )
    exec_ext = ExecutionResult(
        case_id="inv-seq", input="q", tool_calls=ext_calls, elapsed_seconds=0.01
    )

    s_exact = ExecutionSequenceMetric(mode="exact").evaluate(seq_case, exec_base).score
    s_prefix = ExecutionSequenceMetric(mode="prefix").evaluate(seq_case, exec_base).score
    s_subseq = ExecutionSequenceMetric(mode="subsequence").evaluate(seq_case, exec_base).score
    assert s_exact is not None and s_prefix is not None and s_subseq is not None
    assert s_exact <= s_prefix <= s_subseq

    s_prefix_ext = ExecutionSequenceMetric(mode="prefix").evaluate(seq_case, exec_ext).score
    s_subseq_ext = ExecutionSequenceMetric(mode="subsequence").evaluate(seq_case, exec_ext).score
    assert s_prefix_ext is not None and s_subseq_ext is not None
    assert s_prefix <= s_prefix_ext
    assert s_subseq <= s_subseq_ext

    # 3. policy_compliance: casefold normalization + append irreversibility
    pol_case = EvaluationCase(
        id="inv-pol",
        input="q",
        criteria=CaseCriteria(
            forbidden_tools=["DROP_TABLE"], forbidden_argument_patterns=["SECRET"]
        ),
    )
    viol_calls = [ToolCallRecord(name="drop_table", arguments={"x": "ok"})]
    extended_calls = [*viol_calls, ToolCallRecord(name="safe_read", arguments={"k": "v"})]
    assert (
        PolicyComplianceMetric()
        .evaluate(
            pol_case,
            ExecutionResult(
                case_id="inv-pol", input="q", tool_calls=viol_calls, elapsed_seconds=0.01
            ),
        )
        .score
        == 0.0
    )
    assert (
        PolicyComplianceMetric()
        .evaluate(
            pol_case,
            ExecutionResult(
                case_id="inv-pol", input="q", tool_calls=extended_calls, elapsed_seconds=0.01
            ),
        )
        .score
        == 0.0
    )

    # 4. failure_recovery: trailing failure strictly < 1, terminal SUCCESS achieves 1.0
    rec_case = EvaluationCase(id="inv-rec", input="q")
    trailing_fail = ExecutionResult(
        case_id="inv-rec",
        input="q",
        tool_calls=[
            ToolCallRecord(name="a", status=ToolCallStatus.ERROR),
            ToolCallRecord(name="b", status=ToolCallStatus.SUCCESS),
            ToolCallRecord(name="c", status=ToolCallStatus.TIMEOUT),
        ],
        elapsed_seconds=0.01,
    )
    r_trail = FailureRecoveryMetric().evaluate(rec_case, trailing_fail)
    assert r_trail.score is not None and r_trail.score < 1.0

    recovered_all = ExecutionResult(
        case_id="inv-rec",
        input="q",
        tool_calls=[
            *trailing_fail.tool_calls,
            ToolCallRecord(name="d", status=ToolCallStatus.SUCCESS),
        ],
        elapsed_seconds=0.01,
    )
    r_full = FailureRecoveryMetric().evaluate(rec_case, recovered_all)
    assert r_full.score == 1.0


def test_negative_drift_probes_detect_agent_metric_divergence(
    golden_agent_oracle: dict[str, Any],
) -> None:
    """Confirm conformance assertions fail deterministically under mutated oracle verdicts."""
    vec_perfect = next(
        v for v in golden_agent_oracle["canonical_vectors"] if v["case_id"] == "perfect_single_call"
    )
    mutated_score = copy.deepcopy(vec_perfect["expected"])
    mutated_score["tool_selection_f1"]["score_exact"] = {"num": 1, "den": 2}
    with pytest.raises(AssertionError, match="score mismatch"):
        _assert_case_matches_oracle_response(vec_perfect["input"], mutated_score)

    mutated_status = copy.deepcopy(vec_perfect["expected"])
    mutated_status["policy_compliance"]["status"] = MetricStatus.FAIL.value
    with pytest.raises(AssertionError, match="status mismatch"):
        _assert_case_matches_oracle_response(vec_perfect["input"], mutated_status)

    vec_err = next(
        v
        for v in golden_agent_oracle["canonical_vectors"]
        if v["case_id"] == "errors_inconclusive_all_six"
    )
    mutated_guard = copy.deepcopy(vec_err["expected"])
    mutated_guard["failure_recovery"]["status"] = MetricStatus.NOT_APPLICABLE.value
    with pytest.raises(AssertionError, match="status mismatch"):
        _assert_case_matches_oracle_response(vec_err["input"], mutated_guard)


def test_live_lean_agent_oracle_parity_and_sweeps(
    request: pytest.FixtureRequest,
    golden_agent_oracle: dict[str, Any],
) -> None:
    """Fail-closed live verification against compiled `evalforge-agent-oracle`."""
    if not request.config.getoption("--lean-live-oracle"):
        return

    oracle_bin = _resolve_oracle_bin(request)

    # 1. Exact byte-for-byte parity with checked-in golden JSON
    export_proc = _run_live_oracle(oracle_bin, ["export-golden"])
    assert export_proc.returncode == 0, f"export-golden failed: {export_proc.stderr}"
    assert export_proc.stdout == GOLDEN_AGENT_PATH.read_text(encoding="utf-8"), (
        "evalforge-agent-oracle export-golden drifted from "
        "tests/conformance/golden/agent_metrics_oracle.json"
    )

    # 2. Live eval-stdin verification for all 4 threshold vectors
    for vec in golden_agent_oracle["threshold_resolution_vectors"]:
        live_thr = _eval_live_oracle(
            oracle_bin,
            {
                "kind": "resolve_threshold",
                "criteria": vec["criteria"],
                "metric_id": vec["metric_id"],
                "default_threshold": vec["default_threshold"],
            },
        )
        assert live_thr["threshold_exact"] == vec["expected_threshold_exact"]

    # 3. Live eval-stdin verification for all 20 canonical vectors
    for vec in golden_agent_oracle["canonical_vectors"]:
        payload = {"kind": "agent_case", **vec["input"]}
        live_out = _eval_live_oracle(oracle_bin, payload)
        assert live_out == vec["expected"], f"Live/golden drift on {vec['case_id']!r}"
        _assert_case_matches_oracle_response(vec["input"], live_out)

    # 4. Live sweep on freshly constructed Python cases (Unicode casefold, real schemas, retries)
    sweep_cases: list[tuple[EvaluationCase, ExecutionResult, dict[str, Any]]] = [
        (
            EvaluationCase(
                id="live-sweep-unicode-and-schema",
                input="check user",
                expected_tools=[
                    ExpectedToolCall(
                        name="Lookup",
                        arguments={"id": 42, "tags": ["a", "b"]},
                        arguments_schema={
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["id", "tags"],
                        },
                        order=0,
                    ),
                    ExpectedToolCall(name="Notify", optional=True, order=1),
                ],
                criteria=CaseCriteria(
                    forbidden_tools=["SHELL"],
                    forbidden_argument_patterns=["DROP TABLE"],
                    max_steps=4,
                    max_tool_calls=3,
                    metric_thresholds={"tool_selection": 0.9},
                ),
            ),
            ExecutionResult(
                case_id="live-sweep-unicode-and-schema",
                input="check user",
                tool_calls=[
                    ToolCallRecord(
                        id="t1",
                        name="Lookup",
                        arguments={"tags": ["a", "b"], "id": 42},
                        status=ToolCallStatus.ERROR,
                        error="transient",
                    ),
                    ToolCallRecord(
                        id="t2",
                        name="Lookup",
                        arguments={"id": 42, "tags": ["a", "b"]},
                        status=ToolCallStatus.SUCCESS,
                    ),
                ],
                elapsed_seconds=0.02,
            ),
            {"loop_penalty": 0.25},
        ),
        (
            EvaluationCase(
                id="live-sweep-multi-greedy-and-trace-error",
                input="multi-tool",
                expected_tools=[
                    ExpectedToolCall(name="fetch", arguments={"url": "https://a.test", "retry": 1}),
                    ExpectedToolCall(name="fetch", arguments={"url": "https://b.test"}),
                ],
                criteria=CaseCriteria(allow_redundant_failures=1),
            ),
            ExecutionResult(
                case_id="live-sweep-multi-greedy-and-trace-error",
                input="multi-tool",
                tool_calls=[
                    ToolCallRecord(
                        id="f1",
                        name="fetch",
                        arguments={"url": "https://b.test"},
                        status=ToolCallStatus.ERROR,
                        error="503",
                    ),
                    ToolCallRecord(
                        id="f2",
                        name="fetch",
                        arguments={"url": "https://b.test"},
                        status=ToolCallStatus.ERROR,
                        error="503",
                    ),
                    ToolCallRecord(
                        id="f3",
                        name="fetch",
                        arguments={"url": "https://a.test", "retry": 1},
                        status=ToolCallStatus.SUCCESS,
                    ),
                ],
                trace=[
                    AgentTraceStep(
                        kind=TraceStepKind.ERROR,
                        tool_call_id="f1",
                        error="already linked to f1",
                    ),
                    AgentTraceStep(
                        kind=TraceStepKind.ERROR,
                        error="unlinked terminal error",
                    ),
                ],
                elapsed_seconds=0.03,
            ),
            {"loop_penalty": 0.5, "default_max_steps": 10, "default_max_calls": 5},
        ),
    ]

    for case, execution, cfg in sweep_cases:
        req = _serialize_python_case_for_oracle(
            case,
            execution,
            default_max_steps=cfg.get("default_max_steps"),
            default_max_calls=cfg.get("default_max_calls"),
            loop_penalty=float(cfg.get("loop_penalty", 0.5)),
        )
        live_out = _eval_live_oracle(oracle_bin, req)
        results = _evaluate_all_python_metrics(case, execution, req)
        for key, metric_result in results.items():
            _assert_metric_matches_oracle(
                metric_result,
                live_out[key],
                label=f"{case.id}:{key}",
            )

    # 5. Fail-closed malformed stdin & CLI rejection checks
    valid_base = {"kind": "agent_case", **golden_agent_oracle["canonical_vectors"][0]["input"]}
    malformed_payloads: list[str] = [
        "{not valid json",
        json.dumps({"kind": "unknown_kind"}),
        json.dumps({**valid_base, "loop_penalty": {"num": 0, "den": 1}}),
        json.dumps({**valid_base, "loop_penalty": {"num": 3, "den": 2}}),
        json.dumps({**valid_base, "tool_selection_threshold": {"num": 1, "den": 0}}),
        json.dumps({**valid_base, "tool_selection_threshold": {"num": 2, "den": 1}}),
        json.dumps({**valid_base, "default_max_steps": 0}),
        json.dumps({**valid_base, "default_max_calls": 0}),
        json.dumps(
            {
                **valid_base,
                "tool_calls": [
                    {
                        **golden_agent_oracle["canonical_vectors"][2]["input"]["tool_calls"][0],
                        "status": "invalid_status",
                    }
                ],
            }
        ),
        json.dumps(
            {
                **valid_base,
                "trace": [
                    {
                        **golden_agent_oracle["canonical_vectors"][18]["input"]["trace"][0],
                        "kind": "invalid_kind",
                    }
                ],
            }
        ),
        json.dumps(
            {
                **valid_base,
                "expected_tools": [
                    {
                        **golden_agent_oracle["canonical_vectors"][2]["input"]["expected_tools"][0],
                        "argument_match_mode": "fuzzy",
                    }
                ],
            }
        ),
    ]
    for raw in malformed_payloads:
        proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=raw)
        assert proc.returncode != 0, f"Malformed payload unexpectedly succeeded: {raw!r}"

    bad_cmd = _run_live_oracle(oracle_bin, ["unknown-subcommand"])
    assert bad_cmd.returncode != 0
