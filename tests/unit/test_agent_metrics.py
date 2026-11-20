"""Unit tests covering 100% branch behavior of deterministic M6 agent metrics."""

from __future__ import annotations

import pytest

from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.metrics import (
    ArgumentCorrectnessMetric,
    ExecutionSequenceMetric,
    FailureRecoveryMetric,
    PolicyComplianceMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
    argument_correctness,
    execution_sequence,
    failure_recovery,
    policy_compliance,
    tool_efficiency,
    tool_selection,
)
from evalforge_maestro.types import (
    AgentTraceStep,
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    ExpectedToolCall,
    Metric,
    MetricStatus,
    ToolCallRecord,
)


def _exec(
    *,
    output: object = "done",
    tool_calls: list[dict[str, object] | ToolCallRecord] | None = None,
    trace: list[dict[str, object] | AgentTraceStep] | None = None,
    errors: list[str] | None = None,
) -> ExecutionResult:
    return ExecutionResult.model_validate(
        {
            "case_id": "agent-c1",
            "input": "run task",
            "output": output,
            "tool_calls": tool_calls or [],
            "trace": trace or [],
            "elapsed_seconds": 0.05,
            "errors": errors or [],
        }
    )


def test_tool_selection_all_branches_and_modes() -> None:
    assert isinstance(tool_selection, Metric)
    assert tool_selection.metadata.metric_id == "tool_selection"
    assert tool_selection.metadata.metric_version == "1.0.0"

    with pytest.raises(MetricError, match="mode"):
        ToolSelectionMetric(mode="invalid")  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="threshold"):
        ToolSelectionMetric(threshold=1.5)

    case_none = EvaluationCase(id="agent-c1", input="q")
    assert tool_selection.evaluate(case_none, _exec()).status == MetricStatus.NOT_APPLICABLE

    err_res = tool_selection.evaluate(
        EvaluationCase(id="agent-c1", input="q", expected_tools=[ExpectedToolCall(name="search")]),
        _exec(errors=["Adapter crashed"]),
    )
    assert err_res.status == MetricStatus.INCONCLUSIVE
    assert err_res.score is None

    # Exact match with optional tool allowed without precision penalty
    case_opt = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[
            ExpectedToolCall(name="search"),
            ExpectedToolCall(name="format_helper", optional=True),
        ],
    )
    exact_ok = tool_selection.evaluate(
        case_opt,
        _exec(tool_calls=[{"name": "search"}, {"name": "format_helper"}]),
    )
    assert exact_ok.status == MetricStatus.PASS
    assert exact_ok.score == 1.0

    # All-optional expected tools falls back to allowed set for required denominator
    case_all_opt = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[ExpectedToolCall(name="search", optional=True)],
    )
    assert (
        tool_selection.evaluate(case_all_opt, _exec(tool_calls=[{"name": "search"}])).score == 1.0
    )

    # Extra unexpected call hurts default F1, passes recall, fails exact_set
    case_req = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[ExpectedToolCall(name="search"), ExpectedToolCall(name="calc")],
    )
    exec_extra = _exec(
        trace=[
            {"kind": "tool_call", "name": "search"},
            {
                "kind": "llm_response",
                "tool_calls": [{"name": "calc"}, {"name": "unexpected_tool"}],
            },
        ]
    )
    f1_res = tool_selection.evaluate(case_req, exec_extra)
    assert f1_res.score == 0.8
    assert f1_res.status == MetricStatus.PASS

    recall_res = ToolSelectionMetric(mode="recall").evaluate(case_req, exec_extra)
    assert recall_res.score == 1.0
    assert recall_res.status == MetricStatus.PASS

    exact_set_fail = ToolSelectionMetric(mode="exact_set").evaluate(case_req, exec_extra)
    assert exact_set_fail.score == 0.0
    assert exact_set_fail.status == MetricStatus.FAIL

    zero_hit = tool_selection.evaluate(case_req, _exec(tool_calls=[]))
    assert zero_hit.score == 0.0
    assert zero_hit.status == MetricStatus.FAIL


def test_argument_correctness_all_branches() -> None:
    assert isinstance(argument_correctness, Metric)
    assert argument_correctness.metadata.metric_id == "argument_correctness"
    assert argument_correctness.metadata.metric_version == "1.0.0"

    with pytest.raises(MetricError, match="threshold"):
        ArgumentCorrectnessMetric(threshold=-0.1)

    case_err = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[ExpectedToolCall(name="search", arguments={"q": "x"})],
    )
    assert (
        argument_correctness.evaluate(case_err, _exec(errors=["boom"])).status
        == MetricStatus.INCONCLUSIVE
    )

    # No expected tools OR expected tools without argument constraints -> NOT_APPLICABLE
    case_unconstrained = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[ExpectedToolCall(name="search")],
    )
    assert argument_correctness.evaluate(case_unconstrained, _exec()).status == (
        MetricStatus.NOT_APPLICABLE
    )

    # Subset match, empty dict constraint, JSON Schema check, and parse errors
    case_mixed = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[
            ExpectedToolCall(
                name="search",
                arguments={"q": "refund", "top_k": 3},
                arguments_schema={"type": "object", "required": ["q"]},
            ),
            ExpectedToolCall(name="ping", arguments={}),
            ExpectedToolCall(
                name="calc",
                arguments={"days": 14},
                argument_match_mode="exact",
            ),
        ],
    )
    res_good = argument_correctness.evaluate(
        case_mixed,
        _exec(
            tool_calls=[
                {"name": "search", "arguments": {"q": "refund", "top_k": 3, "extra": True}},
                {"name": "ping", "arguments": {"verbose": False}},
                {"name": "calc", "arguments": {"days": 14}},
            ]
        ),
    )
    assert res_good.status == MetricStatus.PASS
    assert res_good.score == 1.0

    # Strict mode rejects extra subset keys; malformed JSON arguments & missing tool score 0.0
    res_strict = ArgumentCorrectnessMetric(strict_mode=True).evaluate(
        case_mixed,
        _exec(
            tool_calls=[
                {"name": "search", "arguments": "{bad-json"},
                {"name": "ping", "arguments": {}},
            ]
        ),
    )
    assert res_strict.status == MetricStatus.FAIL
    assert res_strict.score == 0.333333

    # Schema failure + partial subset match
    case_schema = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[
            ExpectedToolCall(
                name="search",
                arguments={"q": "refund", "limit": 5},
                arguments_schema={"type": "object", "required": ["limit"]},
            )
        ],
    )
    res_partial = argument_correctness.evaluate(
        case_schema,
        _exec(tool_calls=[{"name": "search", "arguments": {"q": "refund"}}]),
    )
    assert res_partial.status == MetricStatus.FAIL
    assert res_partial.score == 0.25

    # Schema-only expectation (arguments=None) + best-match selection across duplicate calls
    case_schema_only = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[
            ExpectedToolCall(
                name="search",
                arguments_schema={"type": "object", "required": ["q"]},
            )
        ],
    )
    res_dup = argument_correctness.evaluate(
        case_schema_only,
        _exec(
            tool_calls=[
                {"name": "search", "arguments": {"q": "ok"}},
                {"name": "search", "arguments": "{bad"},
            ]
        ),
    )
    assert res_dup.status == MetricStatus.PASS
    assert res_dup.score == 1.0


def test_execution_sequence_all_branches_and_modes() -> None:
    assert isinstance(execution_sequence, Metric)
    assert execution_sequence.metadata.metric_id == "execution_sequence"
    assert execution_sequence.metadata.metric_version == "1.0.0"

    with pytest.raises(MetricError, match="mode"):
        ExecutionSequenceMetric(mode="bad")  # type: ignore[arg-type]

    assert (
        execution_sequence.evaluate(EvaluationCase(id="agent-c1", input="q"), _exec()).status
        == MetricStatus.NOT_APPLICABLE
    )

    case_ordered = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[
            ExpectedToolCall(name="b", order=1),
            ExpectedToolCall(name="a", order=0),
            ExpectedToolCall(name="opt_helper", optional=True),
        ],
    )
    assert (
        execution_sequence.evaluate(case_ordered, _exec(errors=["err"])).status
        == MetricStatus.INCONCLUSIVE
    )

    exec_with_helper = _exec(
        tool_calls=[{"name": "opt_helper"}, {"name": "a"}, {"name": "other"}, {"name": "b"}]
    )
    sub_ok = execution_sequence.evaluate(case_ordered, exec_with_helper)
    assert sub_ok.status == MetricStatus.PASS
    assert sub_ok.score == 1.0

    sub_partial = execution_sequence.evaluate(
        case_ordered,
        _exec(tool_calls=[{"name": "b"}, {"name": "a"}]),
    )
    assert sub_partial.status == MetricStatus.FAIL
    assert sub_partial.score == 0.5

    pref_fail = ExecutionSequenceMetric(mode="prefix", threshold=0.5).evaluate(
        case_ordered,
        exec_with_helper,
    )
    assert pref_fail.status == MetricStatus.FAIL
    assert pref_fail.score == 0.0

    pref_pass = ExecutionSequenceMetric(mode="prefix", threshold=0.5).evaluate(
        case_ordered,
        _exec(tool_calls=[{"name": "a"}, {"name": "x"}]),
    )
    assert pref_pass.status == MetricStatus.PASS
    assert pref_pass.score == 0.5

    pref_full = ExecutionSequenceMetric(mode="prefix").evaluate(
        case_ordered,
        _exec(tool_calls=[{"name": "a"}, {"name": "b"}, {"name": "c"}]),
    )
    assert pref_full.status == MetricStatus.PASS
    assert pref_full.score == 1.0

    exact_ok = ExecutionSequenceMetric(mode="exact").evaluate(
        case_ordered,
        _exec(tool_calls=[{"name": "a"}, {"name": "b"}]),
    )
    assert exact_ok.status == MetricStatus.PASS
    assert exact_ok.score == 1.0

    exact_bad = ExecutionSequenceMetric(mode="exact").evaluate(case_ordered, exec_with_helper)
    assert exact_bad.status == MetricStatus.FAIL
    assert exact_bad.score == 0.0

    case_only_opt = EvaluationCase(
        id="agent-c1",
        input="q",
        expected_tools=[ExpectedToolCall(name="a", optional=True)],
    )
    assert (
        execution_sequence.evaluate(case_only_opt, _exec(tool_calls=[{"name": "a"}])).score == 1.0
    )


def test_tool_efficiency_all_branches() -> None:
    assert isinstance(tool_efficiency, Metric)
    assert tool_efficiency.metadata.metric_id == "tool_efficiency"
    assert tool_efficiency.metadata.metric_version == "1.0.0"

    for bad_kwargs in (
        {"default_max_steps": 0},
        {"default_max_steps": True},
        {"default_max_tool_calls": -1},
        {"default_max_tool_calls": True},
        {"allow_redundant_failures": -1},
        {"allow_redundant_failures": True},
        {"loop_penalty": 0.0},
        {"loop_penalty": 1.5},
        {"loop_penalty": True},
    ):
        with pytest.raises(MetricError):
            ToolEfficiencyMetric(**bad_kwargs)

    case_plain = EvaluationCase(id="agent-c1", input="q")
    assert tool_efficiency.evaluate(case_plain, _exec(errors=["err"])).status == (
        MetricStatus.INCONCLUSIVE
    )
    clean = tool_efficiency.evaluate(
        case_plain,
        _exec(
            tool_calls=[
                {"name": "calc", "arguments": {"n": 1}, "status": "error", "error": "blip"},
                {"name": "calc", "arguments": {"n": 1}, "status": "success"},
            ]
        ),
    )
    assert clean.status == MetricStatus.PASS
    assert clean.score == 1.0

    # Budget overrun + duplicate failing call loop
    case_budget = EvaluationCase(
        id="agent-c1",
        input="q",
        criteria=CaseCriteria(max_steps=2, max_tool_calls=2, allow_redundant_failures=0),
    )
    looped = tool_efficiency.evaluate(
        case_budget,
        _exec(
            trace=[
                {"kind": "reasoning", "content": "step1"},
                {"kind": "tool_call", "name": "api", "tool_calls": []},
                {"kind": "reasoning", "content": "step3"},
                {"kind": "final_output", "content": "done"},
            ],
            tool_calls=[
                {"id": "1", "name": "api", "arguments": {"p": 1}, "status": "error"},
                {"id": "2", "name": "api", "arguments": {"p": 1}, "status": "error"},
                {"id": "3", "name": "api", "arguments": {"p": 2}, "status": "success"},
            ],
        ),
    )
    assert looped.status == MetricStatus.FAIL
    assert looped.score == 0.5

    # Case criteria allow_redundant_failures=1 tolerates one repeated failing signature
    tolerant_case = EvaluationCase(
        id="agent-c1",
        input="q",
        criteria=CaseCriteria(allow_redundant_failures=1),
    )
    tolerated = tool_efficiency.evaluate(
        tolerant_case,
        _exec(
            tool_calls=[
                {"name": "api", "arguments": {"p": 1}, "status": "error"},
                {"name": "api", "arguments": {"p": 1}, "status": "error"},
            ]
        ),
    )
    assert tolerated.status == MetricStatus.PASS
    assert tolerated.score == 1.0


def test_policy_compliance_all_branches() -> None:
    assert isinstance(policy_compliance, Metric)
    assert policy_compliance.metadata.metric_id == "policy_compliance"
    assert policy_compliance.metadata.metric_version == "1.0.0"

    assert (
        policy_compliance.evaluate(
            EvaluationCase(id="agent-c1", input="q"),
            _exec(errors=["err"]),
        ).status
        == MetricStatus.INCONCLUSIVE
    )

    # Compliant when rules satisfied and no blocked steps
    ok_case = EvaluationCase(
        id="agent-c1",
        input="q",
        criteria=CaseCriteria(
            forbidden_tools=["drop_table"],
            forbidden_argument_patterns=["--force"],
        ),
    )
    ok_res = policy_compliance.evaluate(
        ok_case,
        _exec(
            tool_calls=[{"name": "select_rows", "arguments": {"limit": 5}}],
            trace=[{"kind": "final_output", "content": "ok"}],
        ),
    )
    assert ok_res.status == MetricStatus.PASS
    assert ok_res.score == 1.0

    # Forbidden tool violation
    bad_tool = policy_compliance.evaluate(
        ok_case,
        _exec(tool_calls=[{"name": "DROP_TABLE"}]),
    )
    assert bad_tool.status == MetricStatus.FAIL
    assert bad_tool.score == 0.0

    # Forbidden argument pattern violation
    bad_arg = policy_compliance.evaluate(
        ok_case,
        _exec(tool_calls=[{"name": "cli", "arguments": {"flags": "--Force"}}]),
    )
    assert bad_arg.status == MetricStatus.FAIL
    assert bad_arg.score == 0.0

    # Blocked call or blocked trace step without case rules still fails
    blocked_call = policy_compliance.evaluate(
        EvaluationCase(id="agent-c1", input="q"),
        _exec(tool_calls=[{"name": "shell", "status": "blocked"}]),
    )
    assert blocked_call.status == MetricStatus.FAIL
    assert blocked_call.score == 0.0

    blocked_step = policy_compliance.evaluate(
        EvaluationCase(id="agent-c1", input="q"),
        _exec(trace=[{"kind": "tool_result", "status": "blocked"}]),
    )
    assert blocked_step.status == MetricStatus.FAIL
    assert blocked_step.score == 0.0

    custom_policy = PolicyComplianceMetric(
        forbidden_tools=["exec_shell"],
        forbidden_argument_patterns=["rm -rf"],
    )
    assert (
        custom_policy.evaluate(
            EvaluationCase(id="agent-c1", input="q"),
            _exec(tool_calls=[{"name": "exec_shell"}]),
        ).status
        == MetricStatus.FAIL
    )


def test_failure_recovery_and_trace_enrichment_branches() -> None:
    assert isinstance(failure_recovery, Metric)
    assert failure_recovery.metadata.metric_id == "failure_recovery"
    assert failure_recovery.metadata.metric_version == "1.0.0"

    case = EvaluationCase(id="agent-c1", input="q")
    assert failure_recovery.evaluate(case, _exec(errors=["err"])).status == (
        MetricStatus.INCONCLUSIVE
    )

    # Zero tool or trace failures -> NOT_APPLICABLE
    clean = failure_recovery.evaluate(
        case,
        _exec(tool_calls=[{"id": "1", "name": "search", "status": "success"}]),
    )
    assert clean.status == MetricStatus.NOT_APPLICABLE
    assert clean.score is None

    # Deduplicated trace + tool_calls enrichment: tool_result trace step propagates error status
    enrichment_unrecovered = failure_recovery.evaluate(
        case,
        _exec(
            tool_calls=[{"id": "tc-1", "name": "search"}],
            trace=[
                {
                    "kind": "tool_call",
                    "tool_call_id": "tc-1",
                    "tool_calls": [{"id": "tc-1", "name": "search"}],
                },
                {
                    "kind": "tool_result",
                    "tool_call_id": "tc-1",
                    "status": "error",
                    "error": "db offline",
                },
            ],
        ),
    )
    assert enrichment_unrecovered.status == MetricStatus.FAIL
    assert enrichment_unrecovered.score == 0.0

    # One recovered timeout + one unrecovered standalone trace error -> 0.5 recovery
    partial = failure_recovery.evaluate(
        case,
        _exec(
            tool_calls=[
                {"id": "1", "name": "api", "status": "timeout"},
                {"id": "2", "name": "api", "status": "success"},
            ],
            trace=[
                {"kind": "error", "error": "post-step serialization failure"},
            ],
        ),
    )
    assert partial.status == MetricStatus.PASS
    assert partial.score == 0.5
    strict_recovery = FailureRecoveryMetric(threshold=0.8).evaluate(
        case,
        _exec(
            tool_calls=[
                {"id": "1", "name": "api", "status": "timeout"},
                {"id": "2", "name": "api", "status": "success"},
            ],
            trace=[{"kind": "error", "error": "trailing err"}],
        ),
    )
    assert strict_recovery.status == MetricStatus.FAIL

    # Standalone trace ERROR followed by successful recovery call + tool_result enrichment branches
    full_recovered = failure_recovery.evaluate(
        case,
        _exec(
            tool_calls=[
                {"id": "tc-dup", "name": "search"},
                {"id": "tc-empty", "name": "ping"},
            ],
            trace=[
                {"kind": "tool_call", "tool_call_id": "tc-dup", "name": "search"},
                {
                    "kind": "tool_result",
                    "tool_call_id": "tc-dup",
                    "error": "cache miss",
                    "content": "err",
                },
                {"kind": "tool_result", "tool_call_id": "tc-empty"},
                {"kind": "tool_call", "tool_call_id": "tx", "name": "primary", "status": "error"},
                {"kind": "tool_result", "tool_call_id": "ty", "name": "fallback", "status": "ok"},
                {
                    "kind": "llm_response",
                    "tool_calls": [{"id": "ty", "name": "fallback", "status": "success"}],
                },
            ],
        ),
    )
    assert full_recovered.status == MetricStatus.PASS
    assert full_recovered.score == 1.0
