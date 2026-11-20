"""Dependency-free structural trace and tool-call normalizers with secret redaction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from evalforge_maestro._canonical import redact_secrets, scrub_secret_text
from evalforge_maestro.adapters._shared import extract_adapter_field
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import (
    AgentExtractorConfig,
    AgentTraceStep,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
)


def _scrub_any(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_secret_text(value)
    if isinstance(value, Mapping):
        return {str(k): _scrub_any(v) for k, v in redact_secrets(dict(value)).items()}
    if isinstance(value, list):
        return [_scrub_any(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_any(item) for item in value]
    return value


def redact_tool_call_record(call: ToolCallRecord) -> ToolCallRecord:
    """Return a copy of ToolCallRecord with secrets scrubbed from arguments/result/error."""
    return call.model_copy(
        update={
            "arguments": _scrub_any(call.arguments),
            "raw_arguments": scrub_secret_text(call.raw_arguments)
            if call.raw_arguments is not None
            else None,
            "argument_parse_error": scrub_secret_text(call.argument_parse_error)
            if call.argument_parse_error is not None
            else None,
            "result": _scrub_any(call.result),
            "error": scrub_secret_text(call.error) if call.error is not None else None,
            "metadata": _scrub_any(call.metadata),
        }
    )


def redact_trace_step(step: AgentTraceStep) -> AgentTraceStep:
    """Return a copy of AgentTraceStep with secrets scrubbed across step fields and calls."""
    return step.model_copy(
        update={
            "content": _scrub_any(step.content),
            "tool_calls": [redact_tool_call_record(c) for c in step.tool_calls],
            "error": scrub_secret_text(step.error) if step.error is not None else None,
            "metadata": _scrub_any(step.metadata),
        }
    )


def _looks_like_chat_message(item: Any) -> bool:
    return (
        isinstance(item, Mapping)
        and ("role" in item or "content" in item)
        and (
            "tool_calls" in item
            or "tool_call_id" in item
            or isinstance(item.get("content"), list)
            or "role" in item
        )
    )


def _normalize_single_tool_call(
    raw_item: Any,
    *,
    extractors: AgentExtractorConfig,
    step_index: int | None = None,
) -> ToolCallRecord:
    if isinstance(raw_item, ToolCallRecord):
        return redact_tool_call_record(
            raw_item
            if (raw_item.step_index is not None or step_index is None)
            else raw_item.model_copy(update={"step_index": step_index})
        )

    custom_fields = any(
        spec is not None
        for spec in (
            extractors.tool_id,
            extractors.tool_name,
            extractors.tool_arguments,
            extractors.tool_result,
            extractors.tool_status,
            extractors.tool_error,
        )
    )
    if custom_fields or not isinstance(raw_item, Mapping):
        payload: dict[str, Any] = {
            "name": extract_adapter_field(
                raw_item,
                extractors.tool_name,
                ("name", "tool", "tool_name", "function.name"),
                required=True,
                field_label="tool_call.name",
                adapter_label="Agent",
            ),
            "id": extract_adapter_field(
                raw_item,
                extractors.tool_id,
                ("id", "tool_call_id", "call_id"),
                required=False,
                default=None,
                field_label="tool_call.id",
                adapter_label="Agent",
            ),
            "arguments": extract_adapter_field(
                raw_item,
                extractors.tool_arguments,
                ("arguments", "args", "input", "parameters", "function.arguments"),
                required=False,
                default={},
                field_label="tool_call.arguments",
                adapter_label="Agent",
            ),
            "result": extract_adapter_field(
                raw_item,
                extractors.tool_result,
                ("result", "output", "response"),
                required=False,
                default=None,
                field_label="tool_call.result",
                adapter_label="Agent",
            ),
            "status": extract_adapter_field(
                raw_item,
                extractors.tool_status,
                ("status",),
                required=False,
                default=None,
                field_label="tool_call.status",
                adapter_label="Agent",
            ),
            "error": extract_adapter_field(
                raw_item,
                extractors.tool_error,
                ("error",),
                required=False,
                default=None,
                field_label="tool_call.error",
                adapter_label="Agent",
            ),
            "step_index": step_index,
        }
    else:
        payload = dict(raw_item)
        if "step_index" not in payload and step_index is not None:
            payload["step_index"] = step_index

    try:
        record = ToolCallRecord.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise AdapterError(f"Invalid tool call payload: {exc}") from exc
    return redact_tool_call_record(record)


def _extract_anthropic_assistant(
    blocks: list[Any],
    *,
    step_index: int,
    extractors: AgentExtractorConfig,
) -> AgentTraceStep:
    texts: list[str] = []
    calls: list[ToolCallRecord] = []
    saw_thinking = False
    saw_other = False
    for block in blocks:
        if not isinstance(block, Mapping):
            texts.append(str(block))
            saw_other = True
            continue
        b_type = str(block.get("type", "")).strip().lower()
        if b_type == "tool_use":
            calls.append(
                _normalize_single_tool_call(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": block.get("input", {}),
                    },
                    extractors=extractors,
                    step_index=step_index,
                )
            )
        elif b_type == "thinking":
            thinking_txt = block.get("thinking")
            if thinking_txt is not None:
                texts.append(str(thinking_txt))
            saw_thinking = True
        elif b_type == "text" and block.get("text") is not None:
            texts.append(str(block["text"]))
            saw_other = True
        else:
            texts.append(str(block))
            saw_other = True

    kind = (
        TraceStepKind.REASONING
        if (saw_thinking and not saw_other and not calls)
        else TraceStepKind.LLM_RESPONSE
    )
    content: Any = "\n".join(texts) if texts else None
    return redact_trace_step(
        AgentTraceStep(step_index=step_index, kind=kind, content=content, tool_calls=calls)
    )


def _normalize_single_step(
    raw_step: Any,
    *,
    index: int,
    extractors: AgentExtractorConfig,
) -> list[AgentTraceStep]:
    if isinstance(raw_step, AgentTraceStep):
        step = (
            raw_step
            if raw_step.step_index is not None
            else raw_step.model_copy(update={"step_index": index})
        )
        return [redact_trace_step(step)]

    if (
        isinstance(raw_step, Mapping)
        and extractors.step_kind is None
        and extractors.step_content is None
        and _looks_like_chat_message(raw_step)
    ):
        role = str(raw_step.get("role", "other")).strip().lower()
        raw_content = raw_step.get("content")
        # Anthropic user message with tool_result content blocks
        if role == "user" and isinstance(raw_content, list):
            out_steps: list[AgentTraceStep] = []
            for blk in raw_content:
                if isinstance(blk, Mapping) and str(blk.get("type", "")).lower() == "tool_result":
                    is_err = bool(blk.get("is_error", False))
                    res_text = blk.get("content")
                    out_steps.append(
                        redact_trace_step(
                            AgentTraceStep(
                                step_index=index + len(out_steps),
                                kind=TraceStepKind.TOOL_RESULT,
                                tool_call_id=blk.get("tool_use_id"),
                                status=(ToolCallStatus.ERROR if is_err else ToolCallStatus.SUCCESS),
                                error=str(res_text) if is_err and res_text is not None else None,
                                content=res_text,
                            )
                        )
                    )
            if out_steps:
                return out_steps

        # Anthropic assistant message with structured content block list
        if role == "assistant" and isinstance(raw_content, list):
            return [
                _extract_anthropic_assistant(raw_content, step_index=index, extractors=extractors)
            ]

        # OpenAI message shape
        raw_tcs = raw_step.get("tool_calls") or ()
        if not isinstance(raw_tcs, Sequence) or isinstance(raw_tcs, (str, bytes)):
            raise AdapterError("Trace step tool_calls must be a sequence")
        norm_tcs = [
            _normalize_single_tool_call(tc, extractors=extractors, step_index=index)
            for tc in raw_tcs
        ]
        step_payload: dict[str, Any] = {
            "step_index": raw_step.get("step_index", index),
            "role": role,
            "name": raw_step.get("name"),
            "content": raw_content,
            "tool_calls": norm_tcs,
            "tool_call_id": raw_step.get("tool_call_id"),
            "status": raw_step.get("status"),
            "error": raw_step.get("error"),
        }
        return [redact_trace_step(AgentTraceStep.model_validate(step_payload))]

    if (
        extractors.step_kind is not None
        or extractors.step_content is not None
        or not isinstance(raw_step, Mapping)
    ):
        kind_val = extract_adapter_field(
            raw_step,
            extractors.step_kind,
            ("kind", "type", "role"),
            required=False,
            default="other",
            field_label="trace.kind",
            adapter_label="Agent",
        )
        content_val = extract_adapter_field(
            raw_step,
            extractors.step_content,
            ("content", "text", "message", "observation"),
            required=False,
            default=None,
            field_label="trace.content",
            adapter_label="Agent",
        )
        raw_nested = extract_adapter_field(
            raw_step,
            None,
            ("tool_calls",),
            required=False,
            default=[],
            field_label="trace.tool_calls",
            adapter_label="Agent",
        )
        nested_calls = normalize_tool_calls(raw_nested or [], extractors=extractors)
        step_dict = {
            "step_index": index,
            "kind": kind_val if kind_val is not None else "other",
            "content": content_val,
            "tool_calls": nested_calls,
        }
    else:
        step_dict = dict(raw_step)
        if "step_index" not in step_dict:
            step_dict["step_index"] = index
        if "tool_calls" in step_dict and step_dict["tool_calls"] is not None:
            step_dict["tool_calls"] = normalize_tool_calls(
                step_dict["tool_calls"], extractors=extractors
            )

    try:
        step_model = AgentTraceStep.model_validate(step_dict)
    except (ValidationError, ValueError) as exc:
        raise AdapterError(f"Invalid agent trace step payload: {exc}") from exc
    return [redact_trace_step(step_model)]


def normalize_agent_trace(
    raw: Any,
    *,
    extractors: AgentExtractorConfig | None = None,
) -> list[AgentTraceStep]:
    """Normalize arbitrary step dicts, OpenAI/Anthropic messages, or models to AgentTraceStep."""
    if raw is None:
        return []
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
        raise AdapterError(f"Agent trace must be a sequence, got {type(raw).__name__}")

    cfg = extractors or AgentExtractorConfig()
    steps: list[AgentTraceStep] = []
    for raw_step in raw:
        expanded = _normalize_single_step(raw_step, index=len(steps), extractors=cfg)
        for item in expanded:
            if item.step_index != len(steps) and item.step_index is None:
                item = item.model_copy(update={"step_index": len(steps)})
            steps.append(item)
    return steps


def normalize_tool_calls(
    raw: Any,
    *,
    extractors: AgentExtractorConfig | None = None,
) -> list[ToolCallRecord]:
    """Normalize tool calls from direct lists or OpenAI/Anthropic chat message sequences."""
    if raw is None:
        return []
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
        raise AdapterError(f"Tool calls must be a sequence, got {type(raw).__name__}")

    cfg = extractors or AgentExtractorConfig()
    items = list(raw)
    if items and all(_looks_like_chat_message(it) for it in items):
        steps = normalize_agent_trace(items, extractors=cfg)
        calls: list[ToolCallRecord] = []
        by_id: dict[str, int] = {}
        for step in steps:
            if step.tool_calls:
                for call in step.tool_calls:
                    idx = len(calls)
                    calls.append(call)
                    if call.id is not None:
                        by_id[call.id] = idx
            elif step.kind == TraceStepKind.TOOL_RESULT and step.tool_call_id is not None:
                target_idx = by_id.get(step.tool_call_id)
                if target_idx is not None:
                    existing = calls[target_idx]
                    updates: dict[str, Any] = {}
                    if step.content is not None:
                        updates["result"] = step.content
                    if step.status is not None:
                        updates["status"] = step.status
                    if step.error is not None:
                        updates["error"] = step.error
                    if updates:
                        calls[target_idx] = redact_tool_call_record(
                            existing.model_copy(update=updates)
                        )
        return calls

    return [_normalize_single_tool_call(item, extractors=cfg) for item in items]
