"""Deterministic agent trace and tool-use evaluation metrics with pinned formula versions."""

from __future__ import annotations

import math
from typing import Any, Literal

from evalforge_maestro._canonical import canonical_json_str, round_score
from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.metrics.deterministic import (
    _inconclusive_result,
    _resolve_threshold,
    _validate_threshold,
)
from evalforge_maestro.types import (
    AgentTraceStep,
    EvaluationCase,
    ExecutionResult,
    ExpectedToolCall,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
)

_TOOL_FAILURE_STATUSES = frozenset({ToolCallStatus.ERROR, ToolCallStatus.TIMEOUT})


def _prepare_agent_inputs(
    case: EvaluationCase,
    execution: ExecutionResult,
) -> tuple[list[ExpectedToolCall], list[ToolCallRecord]]:
    """Collect expected tools and chronologically merged ToolCallRecord items."""
    expected = list(case.expected_tools or ())
    calls: list[ToolCallRecord] = list(execution.tool_calls)
    seen_ids = {call.id for call in calls if call.id is not None}

    tool_results: dict[str, AgentTraceStep] = {}
    for step in execution.trace:
        if step.kind == TraceStepKind.TOOL_RESULT and step.tool_call_id is not None:
            tool_results[step.tool_call_id] = step
        if step.tool_calls:
            for nested in step.tool_calls:
                if nested.id is None or nested.id not in seen_ids:
                    calls.append(nested)
                    if nested.id is not None:
                        seen_ids.add(nested.id)
        elif step.kind == TraceStepKind.TOOL_CALL and step.name is not None:
            if step.tool_call_id is not None and step.tool_call_id in seen_ids:
                continue
            calls.append(
                ToolCallRecord(
                    id=step.tool_call_id,
                    name=step.name,
                    step_index=step.step_index,
                    status=step.status if step.status is not None else ToolCallStatus.SUCCESS,
                    error=step.error,
                )
            )
            if step.tool_call_id is not None:
                seen_ids.add(step.tool_call_id)

    enriched: list[ToolCallRecord] = []
    for call in calls:
        res_step = tool_results.get(call.id) if call.id is not None else None
        if res_step is None:
            enriched.append(call)
            continue
        updates: dict[str, Any] = {}
        if res_step.status is not None:
            updates["status"] = res_step.status
        if res_step.error is not None and call.error is None:
            updates["error"] = res_step.error
            if res_step.status is None:
                updates["status"] = ToolCallStatus.ERROR
        if res_step.content is not None and call.result is None:
            updates["result"] = res_step.content
        enriched.append(call.model_copy(update=updates) if updates else call)

    return expected, enriched


def _ordered_expected_tools(expected: list[ExpectedToolCall]) -> list[ExpectedToolCall]:
    if any(item.order is not None for item in expected):
        return [
            item
            for _, item in sorted(
                enumerate(expected),
                key=lambda pair: (
                    pair[1].order if pair[1].order is not None else len(expected),
                    pair[0],
                ),
            )
        ]
    return expected


def _score_single_call_args(
    exp: ExpectedToolCall,
    call: ToolCallRecord,
    *,
    strict_mode: bool,
) -> float:
    if call.argument_parse_error is not None:
        return 0.0

    sub_scores: list[float] = []
    if exp.arguments_schema is not None:
        import jsonschema

        try:
            jsonschema.validate(instance=call.arguments, schema=exp.arguments_schema)
            sub_scores.append(1.0)
        except jsonschema.ValidationError:
            sub_scores.append(0.0)

    if exp.arguments is not None:
        if strict_mode or exp.argument_match_mode == "exact":
            sub_scores.append(1.0 if call.arguments == exp.arguments else 0.0)
        elif not exp.arguments:
            sub_scores.append(1.0)
        else:
            matched_keys = sum(
                1
                for k, v in exp.arguments.items()
                if k in call.arguments and call.arguments[k] == v
            )
            sub_scores.append(matched_keys / len(exp.arguments))

    return sum(sub_scores) / len(sub_scores)


def _score_tool_selection(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    mode: Literal["f1", "recall", "exact_set"],
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for tool_selection v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"mode": mode, "threshold": threshold}
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    expected, calls = _prepare_agent_inputs(case, execution)
    if not expected:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation="EvaluationCase.expected_tools is empty; tool_selection is not applicable.",
            config_snapshot=snapshot,
        )

    req_names = {item.name for item in expected if not item.optional} or {
        item.name for item in expected
    }
    allowed_names = {item.name for item in expected}
    called_names = {call.name for call in calls}

    matched = sorted(called_names & req_names)
    missing = sorted(req_names - called_names)
    extra = sorted(called_names - allowed_names)

    tp = len(matched)
    fp = len(extra)
    recall = tp / len(req_names)

    if mode == "recall":
        raw_score = recall
    elif mode == "exact_set":
        raw_score = 1.0 if (not missing and not extra) else 0.0
    else:
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        raw_score = (
            (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0.0 else 0.0
        )

    score = round_score(raw_score)
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    evidence = [f"matched:{n}" for n in matched] + [f"missing:{n}" for n in missing]
    evidence.extend(f"unexpected:{n}" for n in extra)
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="pass" if status == MetricStatus.PASS else "fail",
        explanation=(
            f"Tool selection ({mode}) matched {tp}/{len(req_names)} required tools "
            f"with {fp} unexpected tool(s)."
        ),
        evidence=evidence,
        config_snapshot=snapshot,
    )


def _score_argument_correctness(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    strict_mode: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for argument_correctness v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"strict_mode": strict_mode, "threshold": threshold}
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    expected, calls = _prepare_agent_inputs(case, execution)
    constrained = [
        item for item in expected if item.arguments is not None or item.arguments_schema is not None
    ]
    if not constrained:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                "No expected_tools declare argument or schema expectations; "
                "argument_correctness is not applicable."
            ),
            config_snapshot=snapshot,
        )

    used_indices: set[int] = set()
    item_scores: list[float] = []
    evidence: list[str] = []

    for exp in constrained:
        best_idx: int | None = None
        best_score = -1.0
        for idx, call in enumerate(calls):
            if idx in used_indices or call.name != exp.name:
                continue
            cand = _score_single_call_args(exp, call, strict_mode=strict_mode)
            if cand > best_score:
                best_score = cand
                best_idx = idx
        if best_idx is None:
            item_scores.append(0.0)
            evidence.append(f"missing_call:{exp.name}")
        else:
            used_indices.add(best_idx)
            item_scores.append(best_score)
            evidence.append(f"{exp.name}:{round_score(best_score)}")

    score = round_score(sum(item_scores) / len(constrained))
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="pass" if status == MetricStatus.PASS else "fail",
        explanation=(
            f"Evaluated {len(constrained)} constrained tool expectation(s) "
            f"with mean argument score {score}."
        ),
        evidence=evidence,
        config_snapshot=snapshot,
    )


def _score_execution_sequence(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    mode: Literal["subsequence", "prefix", "exact"],
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for execution_sequence v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"mode": mode, "threshold": threshold}
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    expected, calls = _prepare_agent_inputs(case, execution)
    if not expected:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                "EvaluationCase.expected_tools is empty; execution_sequence is not applicable."
            ),
            config_snapshot=snapshot,
        )

    ordered = _ordered_expected_tools(expected)
    req_items = [item for item in ordered if not item.optional] or ordered
    exp_seq = [item.name for item in req_items]
    act_seq = [call.name for call in calls]

    if mode == "exact":
        raw_score = 1.0 if act_seq == exp_seq else 0.0
    elif mode == "prefix":
        matched = 0
        for idx in range(min(len(exp_seq), len(act_seq))):
            if act_seq[idx] != exp_seq[idx]:
                break
            matched += 1
        raw_score = matched / len(exp_seq)
    else:
        matched = 0
        for name in act_seq:
            if name == exp_seq[matched]:
                matched += 1
                if matched == len(exp_seq):
                    break
        raw_score = matched / len(exp_seq)

    score = round_score(raw_score)
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="pass" if status == MetricStatus.PASS else "fail",
        explanation=(
            f"Sequence ({mode}) expected {exp_seq} against actual {act_seq}; score={score}."
        ),
        evidence=act_seq,
        config_snapshot=snapshot,
    )


def _score_tool_efficiency(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    default_max_steps: int | None,
    default_max_tool_calls: int | None,
    allow_redundant_failures: int,
    loop_penalty: float,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for tool_efficiency v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    max_steps = (
        case.criteria.max_steps if case.criteria.max_steps is not None else default_max_steps
    )
    max_calls = (
        case.criteria.max_tool_calls
        if case.criteria.max_tool_calls is not None
        else default_max_tool_calls
    )
    max_repeats = (
        case.criteria.allow_redundant_failures
        if case.criteria.allow_redundant_failures > 0
        else allow_redundant_failures
    )
    snapshot: dict[str, Any] = {
        "max_steps": max_steps,
        "max_tool_calls": max_calls,
        "allow_redundant_failures": max_repeats,
        "loop_penalty": loop_penalty,
        "threshold": threshold,
    }
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    _, calls = _prepare_agent_inputs(case, execution)
    actual_steps = len(execution.trace) if execution.trace else len(calls)
    actual_calls = len(calls)

    seen_failed_sigs: set[str] = set()
    redundant_loops: list[str] = []
    for call in calls:
        sig = canonical_json_str(
            {"name": call.name, "arguments": call.arguments, "raw": call.raw_arguments}
        )
        if call.status != ToolCallStatus.SUCCESS:
            if sig in seen_failed_sigs:
                redundant_loops.append(call.name)
            else:
                seen_failed_sigs.add(sig)

    factors = [1.0]
    evidence: list[str] = []
    if max_steps is not None and actual_steps > max_steps:
        factors.append(max_steps / actual_steps)
        evidence.append(f"steps:{actual_steps}>{max_steps}")
    if max_calls is not None and actual_calls > max_calls:
        factors.append(max_calls / actual_calls)
        evidence.append(f"calls:{actual_calls}>{max_calls}")

    excess_loops = max(0, len(redundant_loops) - max_repeats)
    if excess_loops > 0:
        factors.append(max(0.0, 1.0 - excess_loops * loop_penalty))
        evidence.extend(f"redundant_loop:{name}" for name in redundant_loops)

    score = round_score(min(factors))
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="pass" if status == MetricStatus.PASS else "fail",
        explanation=(
            f"Agent executed {actual_steps} step(s) and {actual_calls} tool call(s) "
            f"with {len(redundant_loops)} redundant failing repeat(s)."
        ),
        evidence=evidence,
        config_snapshot=snapshot,
    )


def _score_policy_compliance(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    forbidden_tools: tuple[str, ...],
    forbidden_argument_patterns: tuple[str, ...],
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for policy_compliance v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    all_forbidden_tools = sorted(
        {
            *(t.casefold() for t in forbidden_tools),
            *(t.casefold() for t in case.criteria.forbidden_tools),
        }
    )
    all_patterns = sorted(
        {
            *(p.casefold() for p in forbidden_argument_patterns),
            *(p.casefold() for p in case.criteria.forbidden_argument_patterns),
        }
    )
    snapshot: dict[str, Any] = {
        "forbidden_tools": all_forbidden_tools,
        "forbidden_argument_patterns": all_patterns,
        "threshold": threshold,
    }
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    _, calls = _prepare_agent_inputs(case, execution)
    violations: list[str] = []
    forbidden_set = set(all_forbidden_tools)

    for call in calls:
        if call.status == ToolCallStatus.BLOCKED:
            violations.append(f"blocked_tool_call:{call.name}")
        if call.name.casefold() in forbidden_set:
            violations.append(f"forbidden_tool:{call.name}")
        arg_blob = canonical_json_str(
            {"arguments": call.arguments, "raw": call.raw_arguments}
        ).casefold()
        for pat in all_patterns:
            if pat in arg_blob:
                violations.append(f"forbidden_arg_pattern:{call.name}:{pat}")

    for idx, step in enumerate(execution.trace):
        if step.status == ToolCallStatus.BLOCKED:
            violations.append(f"blocked_trace_step:{idx}")

    score = round_score(0.0 if violations else 1.0)
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="compliant" if not violations else "violation",
        explanation=(
            "Agent trace complied with tool policy constraints."
            if not violations
            else f"Detected {len(violations)} policy violation(s): {violations[0]}."
        ),
        evidence=violations,
        config_snapshot=snapshot,
    )


def _score_failure_recovery(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for failure_recovery v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"threshold": threshold}
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    _, calls = _prepare_agent_inputs(case, execution)
    timeline: list[tuple[str, bool, bool]] = []
    for call in calls:
        is_fail = call.status in _TOOL_FAILURE_STATUSES
        is_ok = call.status == ToolCallStatus.SUCCESS
        timeline.append((f"tool:{call.name}", is_fail, is_ok))

    seen_call_ids = {call.id for call in calls if call.id is not None}
    for idx, step in enumerate(execution.trace):
        if step.kind == TraceStepKind.ERROR and (
            step.tool_call_id is None or step.tool_call_id not in seen_call_ids
        ):
            timeline.append((f"trace_error:{idx}", True, False))

    failure_indices = [i for i, (_, is_fail, _) in enumerate(timeline) if is_fail]
    if not failure_indices:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                "Zero tool or trace errors encountered; failure_recovery is not applicable."
            ),
            config_snapshot=snapshot,
        )

    recovered = 0
    evidence: list[str] = []
    for fail_idx in failure_indices:
        label = timeline[fail_idx][0]
        if any(is_ok for _, _, is_ok in timeline[fail_idx + 1 :]):
            recovered += 1
            evidence.append(f"recovered:{label}")
        else:
            evidence.append(f"unrecovered:{label}")

    score = round_score(recovered / len(failure_indices))
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="recovered" if status == MetricStatus.PASS else "unrecovered",
        explanation=f"Recovered {recovered}/{len(failure_indices)} tool/trace failure event(s).",
        evidence=evidence,
        config_snapshot=snapshot,
    )


class ToolSelectionMetric:
    """Evaluates whether expected agent tools were invoked (`mode='f1'|'recall'|'exact_set'`)."""

    _METADATA = MetricMetadata(
        metric_id="tool_selection",
        metric_version="1.0.0",
        what_it_measures=(
            "Precision/recall/F1 or exact-set match of invoked tools against expected_tools."
        ),
        required_case_fields=("expected_tools",),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Deduplicates called tool names against required and allowed expected_tools; "
            "computes F1 (default), recall, or exact_set match without penalizing optional tools."
        ),
        known_limitations=(
            "Evaluates unique tool selection coverage independently of step counts or arguments."
        ),
    )

    def __init__(
        self,
        *,
        mode: Literal["f1", "recall", "exact_set"] = "f1",
        threshold: float = 0.8,
    ) -> None:
        if mode not in ("f1", "recall", "exact_set"):
            raise MetricError(f"Unsupported tool_selection mode {mode!r}")
        self._mode: Literal["f1", "recall", "exact_set"] = mode
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for tool_selection."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate tool selection deterministically."""
        return _score_tool_selection(
            case,
            execution,
            metadata=self._METADATA,
            mode=self._mode,
            default_threshold=self._threshold,
        )


class ArgumentCorrectnessMetric:
    """Evaluates invoked tool arguments against expected dicts and/or JSON Schemas."""

    _METADATA = MetricMetadata(
        metric_id="argument_correctness",
        metric_version="1.0.0",
        what_it_measures="Structural, subset/exact, and JSON Schema accuracy of tool arguments.",
        required_case_fields=("expected_tools",),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Greedily pairs each constrained ExpectedToolCall with its best unconsumed matching "
            "ToolCallRecord, combining JSON Schema validity and key-wise/exact argument checks."
        ),
        known_limitations=(
            "Requires expected_tools entries specifying arguments or arguments_schema; returns "
            "NOT_APPLICABLE when none are defined."
        ),
    )

    def __init__(
        self,
        *,
        strict_mode: bool = False,
        threshold: float = 0.8,
    ) -> None:
        self._strict_mode = bool(strict_mode)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for argument_correctness."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate tool argument correctness deterministically."""
        return _score_argument_correctness(
            case,
            execution,
            metadata=self._METADATA,
            strict_mode=self._strict_mode,
            default_threshold=self._threshold,
        )


class ExecutionSequenceMetric:
    """Evaluates chronological tool ordering (`mode='subsequence'|'prefix'|'exact'`)."""

    _METADATA = MetricMetadata(
        metric_id="execution_sequence",
        metric_version="1.0.0",
        what_it_measures=(
            "Ordered alignment between invoked tool sequence and expected_tools order."
        ),
        required_case_fields=("expected_tools",),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Sorts expected_tools by explicit order then declaration index and scores greedy "
            "ordered subsequence (default), common prefix ratio, or exact sequence equality."
        ),
        known_limitations=(
            "Default subsequence mode permits helper calls interleaved between required milestones."
        ),
    )

    def __init__(
        self,
        *,
        mode: Literal["subsequence", "prefix", "exact"] = "subsequence",
        threshold: float = 1.0,
    ) -> None:
        if mode not in ("subsequence", "prefix", "exact"):
            raise MetricError(f"Unsupported execution_sequence mode {mode!r}")
        self._mode: Literal["subsequence", "prefix", "exact"] = mode
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for execution_sequence."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate chronological tool sequence deterministically."""
        return _score_execution_sequence(
            case,
            execution,
            metadata=self._METADATA,
            mode=self._mode,
            default_threshold=self._threshold,
        )


class ToolEfficiencyMetric:
    """Evaluates step/tool-call budgets and detects redundant identical failing loops."""

    _METADATA = MetricMetadata(
        metric_id="tool_efficiency",
        metric_version="1.0.0",
        what_it_measures=(
            "Adherence to step/call budgets and absence of repeated failing call loops."
        ),
        required_case_fields=(),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Takes the minimum of max_steps ratio, max_tool_calls ratio, and excess redundant "
            "identical failing tool-call loop penalties."
        ),
        known_limitations=(
            "Single retries that recover cleanly without failing repeatedly are permitted; relies "
            "on declared step/call budgets when checking non-looping verbosity."
        ),
    )

    def __init__(
        self,
        *,
        default_max_steps: int | None = None,
        default_max_tool_calls: int | None = None,
        allow_redundant_failures: int = 0,
        loop_penalty: float = 0.5,
        threshold: float = 0.7,
    ) -> None:
        for label, val in (
            ("default_max_steps", default_max_steps),
            ("default_max_tool_calls", default_max_tool_calls),
        ):
            if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val < 1):
                raise MetricError(f"{label} must be an integer >= 1 when set, got {val!r}")
        if (
            isinstance(allow_redundant_failures, bool)
            or not isinstance(allow_redundant_failures, int)
            or allow_redundant_failures < 0
        ):
            raise MetricError(
                "allow_redundant_failures must be an integer >= 0, "
                f"got {allow_redundant_failures!r}"
            )
        if (
            isinstance(loop_penalty, bool)
            or not math.isfinite(loop_penalty)
            or not 0.0 < loop_penalty <= 1.0
        ):
            raise MetricError(
                f"loop_penalty must be a finite float in (0.0, 1.0], got {loop_penalty!r}"
            )
        self._default_max_steps = default_max_steps
        self._default_max_tool_calls = default_max_tool_calls
        self._allow_redundant_failures = allow_redundant_failures
        self._loop_penalty = float(loop_penalty)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for tool_efficiency."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate tool efficiency deterministically."""
        return _score_tool_efficiency(
            case,
            execution,
            metadata=self._METADATA,
            default_max_steps=self._default_max_steps,
            default_max_tool_calls=self._default_max_tool_calls,
            allow_redundant_failures=self._allow_redundant_failures,
            loop_penalty=self._loop_penalty,
            default_threshold=self._threshold,
        )


class PolicyComplianceMetric:
    """Evaluates forbidden tool usage, disallowed arguments, and blocked execution steps."""

    _METADATA = MetricMetadata(
        metric_id="policy_compliance",
        metric_version="1.0.0",
        what_it_measures=(
            "Compliance with forbidden_tools, restricted arguments, and guardrail blocks."
        ),
        required_case_fields=(),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Scans all tool calls and trace steps for blocked statuses, forbidden tool names, and "
            "restricted argument substrings; returns 0.0 (FAIL) on any breach else 1.0 (PASS)."
        ),
        known_limitations=(
            "Uses deterministic literal case-insensitive matching for forbidden tool names and "
            "argument patterns."
        ),
    )

    def __init__(
        self,
        *,
        forbidden_tools: tuple[str, ...] | list[str] = (),
        forbidden_argument_patterns: tuple[str, ...] | list[str] = (),
        threshold: float = 1.0,
    ) -> None:
        self._forbidden_tools = tuple(forbidden_tools)
        self._forbidden_argument_patterns = tuple(forbidden_argument_patterns)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for policy_compliance."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate tool policy compliance deterministically."""
        return _score_policy_compliance(
            case,
            execution,
            metadata=self._METADATA,
            forbidden_tools=self._forbidden_tools,
            forbidden_argument_patterns=self._forbidden_argument_patterns,
            default_threshold=self._threshold,
        )


class FailureRecoveryMetric:
    """Evaluates whether in-trace tool or step failures were followed by clean tool recovery."""

    _METADATA = MetricMetadata(
        metric_id="failure_recovery",
        metric_version="1.0.0",
        what_it_measures=(
            "Proportion of encountered tool/step errors followed by successful recovery."
        ),
        required_case_fields=(),
        required_execution_fields=("tool_calls", "trace", "errors"),
        calculation_method=(
            "Identifies tool ERROR/TIMEOUT calls and standalone trace ERROR steps; returns "
            "NOT_APPLICABLE when zero failures occurred, else fraction followed by a later SUCCESS."
        ),
        known_limitations=(
            "Measures tool-level recovery independently of final text plausibility; clean traces "
            "with zero tool failures emit NOT_APPLICABLE rather than 1.0."
        ),
    )

    def __init__(self, *, threshold: float = 0.5) -> None:
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for failure_recovery."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate failure recovery deterministically."""
        return _score_failure_recovery(
            case,
            execution,
            metadata=self._METADATA,
            default_threshold=self._threshold,
        )


tool_selection = ToolSelectionMetric()
argument_correctness = ArgumentCorrectnessMetric()
execution_sequence = ExecutionSequenceMetric()
tool_efficiency = ToolEfficiencyMetric()
policy_compliance = PolicyComplianceMetric()
failure_recovery = FailureRecoveryMetric()

__all__ = [
    "ArgumentCorrectnessMetric",
    "ExecutionSequenceMetric",
    "FailureRecoveryMetric",
    "PolicyComplianceMetric",
    "ToolEfficiencyMetric",
    "ToolSelectionMetric",
    "argument_correctness",
    "execution_sequence",
    "failure_recovery",
    "policy_compliance",
    "tool_efficiency",
    "tool_selection",
]
