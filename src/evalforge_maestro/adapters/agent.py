"""Protocol-based dependency-free AgentAdapter with trace normalization and secret redaction."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from evalforge_maestro._canonical import round_score, scrub_secret_text
from evalforge_maestro.adapters._shared import (
    build_target_arg,
    build_validated_execution_result,
    extract_adapter_field,
    invoke_callable,
    normalize_token_usage,
    redact_adapter_config,
    validate_callable_target_options,
)
from evalforge_maestro.adapters._trace_norm import (
    _looks_like_chat_message,
    normalize_agent_trace,
    normalize_tool_calls,
)
from evalforge_maestro.types import (
    AgentExtractorConfig,
    AgentTraceStep,
    EvaluationCase,
    ExecutionResult,
    TokenUsage,
    ToolCallRecord,
    TraceStepKind,
)


def _extract_agent_payload(
    raw_out: Any,
    extractors: AgentExtractorConfig,
) -> tuple[Any, list[ToolCallRecord], list[AgentTraceStep], TokenUsage | None, list[str]]:
    if (
        isinstance(raw_out, Sequence)
        and not isinstance(raw_out, (str, bytes))
        and extractors.output is None
        and extractors.trace is None
        and extractors.tool_calls is None
        and all(_looks_like_chat_message(item) for item in raw_out)
    ):
        trace = normalize_agent_trace(raw_out, extractors=extractors)
        tool_calls = normalize_tool_calls(raw_out, extractors=extractors)
        final_output: Any = None
        for step in reversed(trace):
            if step.kind in (TraceStepKind.FINAL_OUTPUT, TraceStepKind.LLM_RESPONSE) and (
                step.content is not None
                and not (isinstance(step.content, str) and not step.content)
            ):
                final_output = step.content
                break
        return final_output, tool_calls, trace, None, []

    output = extract_adapter_field(
        raw_out,
        extractors.output,
        ("output", "answer", "response", "final_output"),
        required=False,
        default=None,
        field_label="output",
        adapter_label="Agent",
    )
    if isinstance(output, str):
        output = scrub_secret_text(output)

    raw_trace = extract_adapter_field(
        raw_out,
        extractors.trace,
        ("trace", "steps", "messages"),
        required=False,
        default=[],
        field_label="trace",
        adapter_label="Agent",
    )
    trace = normalize_agent_trace(raw_trace or [], extractors=extractors)

    raw_calls = extract_adapter_field(
        raw_out,
        extractors.tool_calls,
        ("tool_calls", "calls"),
        required=False,
        default=None,
        field_label="tool_calls",
        adapter_label="Agent",
    )
    if raw_calls is not None:
        tool_calls = normalize_tool_calls(raw_calls, extractors=extractors)
    elif trace:
        tool_calls = [call for step in trace for call in step.tool_calls]
    else:
        tool_calls = []

    raw_tokens = extract_adapter_field(
        raw_out,
        extractors.tokens,
        ("tokens", "usage", "token_usage"),
        required=False,
        default=None,
        field_label="tokens",
        adapter_label="Agent",
    )
    tokens = normalize_token_usage(raw_tokens)

    raw_errors = extract_adapter_field(
        raw_out,
        extractors.errors,
        ("errors",),
        required=False,
        default=[],
        field_label="errors",
        adapter_label="Agent",
    )
    errors = (
        [scrub_secret_text(str(item)) for item in raw_errors]
        if isinstance(raw_errors, Sequence) and not isinstance(raw_errors, (str, bytes))
        else ([scrub_secret_text(str(raw_errors))] if raw_errors is not None else [])
    )

    if output is None and trace:
        for step in reversed(trace):
            if step.kind in (TraceStepKind.FINAL_OUTPUT, TraceStepKind.LLM_RESPONSE) and (
                step.content is not None
            ):
                output = step.content
                break

    return output, tool_calls, trace, tokens, errors


class AgentAdapter:
    """Protocol-based agent target adapter normalizing output, tool calls, and traces."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        extractors: AgentExtractorConfig | None = None,
        system_version: str | None = None,
        model_id: str | None = None,
        config: Mapping[str, Any] | None = None,
        pass_case: bool = False,
        input_mapper: Callable[[EvaluationCase], Any] | None = None,
    ) -> None:
        self._is_coro_fn = validate_callable_target_options(
            fn,
            adapter_name="AgentAdapter",
            pass_case=pass_case,
            input_mapper=input_mapper,
        )
        self._fn = fn
        self._extractors = extractors or AgentExtractorConfig()
        self._system_version = system_version
        self._model_id = model_id
        self._pass_case = pass_case
        self._input_mapper = input_mapper
        self._config_fingerprint, self._adapter_metadata = redact_adapter_config(config)

    @property
    def system_version(self) -> str | None:
        """Return declared agent system version."""
        return self._system_version

    @property
    def model_id(self) -> str | None:
        """Return declared agent model identifier."""
        return self._model_id

    @property
    def config_fingerprint(self) -> str | None:
        """Return canonical SHA-256 fingerprint of redacted adapter configuration."""
        return self._config_fingerprint

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Invoke agent callable and normalize output, tool calls, trace steps, and tokens."""
        arg = build_target_arg(case, pass_case=self._pass_case, input_mapper=self._input_mapper)
        errors: list[str] = []
        output: Any = None
        tool_calls: list[ToolCallRecord] = []
        trace: list[AgentTraceStep] = []
        tokens: TokenUsage | None = None
        start = time.perf_counter()

        try:
            raw_out = await invoke_callable(self._fn, arg, is_coro_fn=self._is_coro_fn)
            output, tool_calls, trace, tokens, extracted_errors = _extract_agent_payload(
                raw_out, self._extractors
            )
            errors.extend(extracted_errors)
        except Exception as exc:
            errors.append(scrub_secret_text(f"{type(exc).__name__}: {exc}"))

        elapsed = round_score(max(0.0, time.perf_counter() - start))
        return build_validated_execution_result(
            case=case,
            output=output,
            retrieved_chunks=(),
            trace=trace,
            tool_calls=tool_calls,
            tokens=tokens,
            elapsed_seconds=elapsed,
            truncated=False,
            errors=errors,
            warnings=[],
            system_version=self._system_version,
            model_id=self._model_id,
            config_fingerprint=self._config_fingerprint,
            adapter_metadata=self._adapter_metadata,
        )
