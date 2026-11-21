"""Framework-agnostic OpenTelemetry trace ingestion into canonical ExecutionResult."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from evalforge_maestro._canonical import redact_secrets, scrub_secret_text
from evalforge_maestro.adapters._shared import (
    build_validated_execution_result,
    redact_adapter_config,
)
from evalforge_maestro.adapters._trace_norm import (
    _scrub_any,
    redact_tool_call_record,
    redact_trace_step,
)
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import AdapterError, DatasetError
from evalforge_maestro.types import (
    AgentTraceStep,
    EvaluationCase,
    ExecutionResult,
    OtelExtractorConfig,
    OtelTimestampUnit,
    RetrievedChunk,
    TokenUsage,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
)

_OTLP_VALUE_KEYS = frozenset(
    {
        "stringValue",
        "intValue",
        "doubleValue",
        "boolValue",
        "bytesValue",
        "arrayValue",
        "kvlistValue",
    }
)
_NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

_INPUT_ATTRS: tuple[str, ...] = (
    "gen_ai.input.messages",
    "gen_ai.prompt",
    "input.value",
    "traceloop.entity.input",
    "llm.input_messages",
    "input",
)
_OUTPUT_ATTRS: tuple[str, ...] = (
    "output.value",
    "gen_ai.output.messages",
    "gen_ai.completion",
    "traceloop.entity.output",
    "llm.output_messages",
    "output",
)
_MODEL_ATTRS: tuple[str, ...] = (
    "gen_ai.response.model",
    "gen_ai.request.model",
    "llm.model_name",
    "model",
)
_SERVICE_VERSION_ATTRS: tuple[str, ...] = (
    "service.version",
    "app.version",
)
_STEP_KIND_ALIASES: dict[str, TraceStepKind] = {
    "user_input": TraceStepKind.USER_INPUT,
    "input": TraceStepKind.USER_INPUT,
    "reasoning": TraceStepKind.REASONING,
    "thought": TraceStepKind.REASONING,
    "plan": TraceStepKind.REASONING,
    "llm_response": TraceStepKind.LLM_RESPONSE,
    "llm": TraceStepKind.LLM_RESPONSE,
    "chat": TraceStepKind.LLM_RESPONSE,
    "generation": TraceStepKind.LLM_RESPONSE,
    "tool_call": TraceStepKind.TOOL_CALL,
    "tool": TraceStepKind.TOOL_CALL,
    "execute_tool": TraceStepKind.TOOL_CALL,
    "tool_result": TraceStepKind.TOOL_RESULT,
    "error": TraceStepKind.ERROR,
    "final_output": TraceStepKind.FINAL_OUTPUT,
    "output": TraceStepKind.FINAL_OUTPUT,
    "other": TraceStepKind.OTHER,
    "agent": TraceStepKind.OTHER,
    "chain": TraceStepKind.OTHER,
    "retriever": TraceStepKind.OTHER,
}
_TOOL_NAME_ATTRS: tuple[str, ...] = (
    "gen_ai.tool.name",
    "tool.name",
    "tool_name",
    "traceloop.entity.name",
)
_TOOL_ID_ATTRS: tuple[str, ...] = (
    "gen_ai.tool.call.id",
    "tool.call.id",
    "tool_call.id",
    "tool_call_id",
)
_TOOL_ARGS_ATTRS: tuple[str, ...] = (
    "gen_ai.tool.call.arguments",
    "tool.parameters",
    "tool.arguments",
    "tool.input",
    "input.value",
)
_TOOL_RESULT_ATTRS: tuple[str, ...] = (
    "gen_ai.tool.call.result",
    "tool.result",
    "tool.output",
    "output.value",
)
_RETRIEVAL_ATTRS: tuple[str, ...] = (
    "retrieval.documents",
    "retriever.documents",
    "retrieval_documents",
    "documents",
)
_PROMPT_TOKEN_ATTRS: tuple[str, ...] = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.token_count.prompt",
)
_COMPLETION_TOKEN_ATTRS: tuple[str, ...] = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.token_count.completion",
)
_REASONING_TOKEN_ATTRS: tuple[str, ...] = (
    "gen_ai.usage.reasoning_tokens",
    "llm.token_count.completion_details.reasoning",
    "llm.token_count.reasoning",
)
_TOTAL_TOKEN_ATTRS: tuple[str, ...] = (
    "gen_ai.usage.total_tokens",
    "llm.token_count.total",
)


@dataclass(slots=True)
class _NormalizedEvent:
    name: str
    timestamp_ns: int | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _NormalizedSpan:
    index: int
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_ns: int | None
    end_ns: int | None
    attributes: dict[str, Any]
    resource_attributes: dict[str, Any]
    scope_name: str | None
    events: list[_NormalizedEvent]
    status_error: bool
    status_message: str | None


def _decode_any_value(raw: Any) -> Any:
    """Decode OTLP AnyValue wrappers recursively into native Python JSON-safe values."""
    if isinstance(raw, Mapping):
        if len(raw) == 1:
            key, val = next(iter(raw.items()))
            if key in _OTLP_VALUE_KEYS:
                if key == "intValue":
                    try:
                        return int(val)
                    except (TypeError, ValueError):
                        return val
                if key == "doubleValue":
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return val
                if key == "arrayValue":
                    values = val.get("values", ()) if isinstance(val, Mapping) else ()
                    return [_decode_any_value(item) for item in values]
                if key == "kvlistValue":
                    entries = val.get("values", ()) if isinstance(val, Mapping) else ()
                    return _decode_kv_entries(entries)
                return val
        return {str(k): _decode_any_value(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_decode_any_value(item) for item in raw]
    if isinstance(raw, tuple):
        return [_decode_any_value(item) for item in raw]
    return raw


def _decode_kv_entries(entries: Any) -> dict[str, Any]:
    """Decode OTLP KeyValue list (`[{"key": ..., "value": ...}]`) into a plain dict."""
    if not isinstance(entries, Iterable) or isinstance(entries, (str, bytes, Mapping)):
        return {}
    result: dict[str, Any] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("key") is not None:
            result[str(entry["key"])] = _decode_any_value(entry.get("value"))
    return result


def _decode_attributes(raw: Any) -> dict[str, Any]:
    """Normalize dict or OTLP KeyValue list attributes into a plain Python dictionary."""
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return {str(k): _decode_any_value(v) for k, v in raw.items()}
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return _decode_kv_entries(raw)
    return {}


def _read_attr_or_key(obj: Any, *keys: str) -> Any:
    """Read the first present key/attribute across dicts and duck-typed objects."""
    if obj is None:
        return None
    for key in keys:
        if isinstance(obj, Mapping):
            if key in obj and obj[key] is not None:
                return obj[key]
        elif hasattr(obj, key):
            val = getattr(obj, key)
            if val is not None:
                return val
    return None


def _format_otel_id(value: Any, *, hex_width: int) -> str | None:
    """Convert hex strings, integers, or byte buffers into canonical non-empty OTel IDs."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value <= 0:
            return None
        return f"{value:0{hex_width}x}"
    if isinstance(value, (bytes, bytearray)):
        hexed = bytes(value).hex()
        return hexed or None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _parse_timestamp_ns(raw: Any, unit: OtelTimestampUnit) -> int | None:
    """Parse span timestamps (str/int/float/ISO-8601/datetime) into integer nanoseconds."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, datetime):
        return round(raw.timestamp() * 1_000_000_000)

    numeric_val: int | float | None = None
    if isinstance(raw, int):
        numeric_val = raw
    elif isinstance(raw, float):
        if not math.isfinite(raw):
            raise AdapterError("OTel span timestamp must be finite")
        numeric_val = raw
    elif isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return None
        if _NUMERIC_RE.fullmatch(cleaned):
            numeric_val = int(cleaned) if "." not in cleaned else float(cleaned)
        else:
            try:
                parsed_dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            except ValueError as exc:
                raise AdapterError(f"Unparseable OTel span timestamp: {raw!r}") from exc
            return round(parsed_dt.timestamp() * 1_000_000_000)
    else:
        raise AdapterError(f"Unsupported OTel timestamp type: {type(raw).__name__}")

    effective_unit = unit
    if effective_unit == OtelTimestampUnit.AUTO:
        magnitude = abs(float(numeric_val))
        if magnitude >= 1e17:
            effective_unit = OtelTimestampUnit.NS
        elif magnitude >= 1e14:
            effective_unit = OtelTimestampUnit.US
        elif magnitude >= 1e11:
            effective_unit = OtelTimestampUnit.MS
        else:
            effective_unit = OtelTimestampUnit.S

    multipliers = {
        OtelTimestampUnit.NS: 1,
        OtelTimestampUnit.US: 1_000,
        OtelTimestampUnit.MS: 1_000_000,
        OtelTimestampUnit.S: 1_000_000_000,
    }
    factor = multipliers[effective_unit]
    if isinstance(numeric_val, int):
        return numeric_val * factor
    return round(numeric_val * factor)


def _normalize_status(span_obj: Any) -> tuple[bool, str | None]:
    """Normalize OTLP status dicts and SDK Status objects into (is_error, message)."""
    raw_status = _read_attr_or_key(span_obj, "status")
    if raw_status is None:
        return False, None

    raw_code = _read_attr_or_key(raw_status, "code", "status_code")
    if raw_code is not None and not isinstance(raw_code, (int, str)) and hasattr(raw_code, "name"):
        raw_code = raw_code.name

    is_error = False
    if isinstance(raw_code, int) and not isinstance(raw_code, bool):
        is_error = raw_code == 2
    elif isinstance(raw_code, str):
        norm = raw_code.strip().upper()
        is_error = norm in {"ERROR", "STATUS_CODE_ERROR", "2"}

    msg = _read_attr_or_key(raw_status, "message", "description")
    cleaned_msg = str(msg).strip() if isinstance(msg, str) and msg.strip() else None
    return is_error, cleaned_msg


def _normalize_events(raw_events: Any, unit: OtelTimestampUnit) -> list[_NormalizedEvent]:
    """Decode OTel span events across dict and SDK Event instances."""
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)):
        return []
    events: list[_NormalizedEvent] = []
    for event in raw_events:
        raw_name = _read_attr_or_key(event, "name")
        name = str(raw_name).strip() if raw_name is not None else "event"
        raw_ts = _read_attr_or_key(event, "timeUnixNano", "time_unix_nano", "timestamp")
        ts_ns = _parse_timestamp_ns(raw_ts, unit) if raw_ts is not None else None
        attrs = _decode_attributes(_read_attr_or_key(event, "attributes"))
        events.append(_NormalizedEvent(name=name or "event", timestamp_ns=ts_ns, attributes=attrs))
    return events


def _extract_resource_attrs(obj: Any, base_attrs: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge OTLP or duck-typed Resource attributes."""
    merged = dict(base_attrs) if base_attrs else {}
    res_obj = _read_attr_or_key(obj, "resource")
    if res_obj is not None:
        raw_res_attrs = _read_attr_or_key(res_obj, "attributes")
        if raw_res_attrs is None and isinstance(res_obj, Mapping):
            raw_res_attrs = res_obj
        merged.update(_decode_attributes(raw_res_attrs))
    return merged


def _extract_one_span(
    span_obj: Any,
    *,
    index: int,
    resource_attrs: Mapping[str, Any],
    scope_name: str | None,
    unit: OtelTimestampUnit,
) -> _NormalizedSpan:
    """Convert one OTLP dict, flat dict, or duck-typed SDK span into _NormalizedSpan."""
    ctx = _read_attr_or_key(span_obj, "context")
    if ctx is None and callable(getattr(span_obj, "get_span_context", None)):
        ctx = span_obj.get_span_context()

    raw_trace = _read_attr_or_key(span_obj, "traceId", "trace_id")
    if raw_trace is None:
        raw_trace = _read_attr_or_key(ctx, "trace_id", "traceId")
    raw_span = _read_attr_or_key(span_obj, "spanId", "span_id")
    if raw_span is None:
        raw_span = _read_attr_or_key(ctx, "span_id", "spanId")

    trace_id = _format_otel_id(raw_trace, hex_width=32)
    span_id = _format_otel_id(raw_span, hex_width=16)
    if trace_id is None or span_id is None:
        raise AdapterError(f"OTel span at index {index} is missing required trace_id or span_id")

    parent_obj = _read_attr_or_key(span_obj, "parent")
    raw_parent = _read_attr_or_key(span_obj, "parentSpanId", "parent_span_id")
    if raw_parent is None:
        raw_parent = _read_attr_or_key(parent_obj, "span_id", "spanId")
    parent_span_id = _format_otel_id(raw_parent, hex_width=16)

    raw_name = _read_attr_or_key(span_obj, "name")
    name = str(raw_name).strip() if raw_name is not None else f"span-{index}"
    if not name:
        name = f"span-{index}"

    raw_start = _read_attr_or_key(
        span_obj,
        "startTimeUnixNano",
        "start_time_unix_nano",
        "start_time",
    )
    raw_end = _read_attr_or_key(
        span_obj,
        "endTimeUnixNano",
        "end_time_unix_nano",
        "end_time",
    )
    start_ns = _parse_timestamp_ns(raw_start, unit)
    end_ns = _parse_timestamp_ns(raw_end, unit)

    attrs = _decode_attributes(_read_attr_or_key(span_obj, "attributes"))
    span_resource_attrs = _extract_resource_attrs(span_obj, resource_attrs)

    scope_obj = _read_attr_or_key(span_obj, "instrumentation_scope", "instrumentation_library")
    resolved_scope = scope_name or (
        str(_read_attr_or_key(scope_obj, "name"))
        if _read_attr_or_key(scope_obj, "name") is not None
        else None
    )

    events = _normalize_events(_read_attr_or_key(span_obj, "events"), unit)
    status_error, status_message = _normalize_status(span_obj)

    return _NormalizedSpan(
        index=index,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        start_ns=start_ns,
        end_ns=end_ns,
        attributes=attrs,
        resource_attributes=span_resource_attrs,
        scope_name=resolved_scope,
        events=events,
        status_error=status_error,
        status_message=status_message,
    )


def _flatten_payload(
    payload: Any,
    *,
    unit: OtelTimestampUnit,
    inherited_resource: Mapping[str, Any] | None = None,
    inherited_scope: str | None = None,
    start_index: int = 0,
) -> list[_NormalizedSpan]:
    """Unfold OTLP envelopes, flat span lists, JSONL records, and duck-typed spans."""
    collected: list[_NormalizedSpan] = []

    if isinstance(payload, Mapping):
        if "resourceSpans" in payload or "resource_spans" in payload:
            entries = payload.get("resourceSpans") or payload.get("resource_spans") or ()
            if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
                raise AdapterError("OTLP resourceSpans field must be a sequence")
            for rs in entries:
                rs_attrs = _extract_resource_attrs(rs, inherited_resource)
                scope_entries = _read_attr_or_key(rs, "scopeSpans", "scope_spans") or ()
                for ss in scope_entries:
                    scope_obj = _read_attr_or_key(ss, "scope", "instrumentationScope")
                    s_name = _read_attr_or_key(scope_obj, "name") or inherited_scope
                    spans = _read_attr_or_key(ss, "spans") or ()
                    for span in spans:
                        collected.append(
                            _extract_one_span(
                                span,
                                index=start_index + len(collected),
                                resource_attrs=rs_attrs,
                                scope_name=str(s_name) if s_name is not None else None,
                                unit=unit,
                            )
                        )
            return collected

        if "scopeSpans" in payload or "scope_spans" in payload:
            scope_entries = payload.get("scopeSpans") or payload.get("scope_spans") or ()
            rs_attrs = _extract_resource_attrs(payload, inherited_resource)
            for ss in scope_entries:
                scope_obj = _read_attr_or_key(ss, "scope", "instrumentationScope")
                s_name = _read_attr_or_key(scope_obj, "name") or inherited_scope
                for span in _read_attr_or_key(ss, "spans") or ():
                    collected.append(
                        _extract_one_span(
                            span,
                            index=start_index + len(collected),
                            resource_attrs=rs_attrs,
                            scope_name=str(s_name) if s_name is not None else None,
                            unit=unit,
                        )
                    )
            return collected

        if "spans" in payload and isinstance(payload["spans"], Sequence):
            rs_attrs = _extract_resource_attrs(payload, inherited_resource)
            for span in payload["spans"]:
                collected.append(
                    _extract_one_span(
                        span,
                        index=start_index + len(collected),
                        resource_attrs=rs_attrs,
                        scope_name=inherited_scope,
                        unit=unit,
                    )
                )
            return collected

        if _read_attr_or_key(payload, "traceId", "trace_id", "spanId", "span_id") is not None:
            collected.append(
                _extract_one_span(
                    payload,
                    index=start_index,
                    resource_attrs=inherited_resource or {},
                    scope_name=inherited_scope,
                    unit=unit,
                )
            )
            return collected

        raise AdapterError("Unrecognized OTel mapping payload without resourceSpans or span fields")

    if isinstance(payload, (str, bytes)):
        raise AdapterError("ingest_otel_spans expected parsed span objects, got raw string/bytes")

    if isinstance(payload, Iterable):
        for item in payload:
            if isinstance(item, Mapping) and (
                "resourceSpans" in item
                or "resource_spans" in item
                or "scopeSpans" in item
                or "scope_spans" in item
                or "spans" in item
            ):
                collected.extend(
                    _flatten_payload(
                        item,
                        unit=unit,
                        inherited_resource=inherited_resource,
                        inherited_scope=inherited_scope,
                        start_index=start_index + len(collected),
                    )
                )
            else:
                collected.append(
                    _extract_one_span(
                        item,
                        index=start_index + len(collected),
                        resource_attrs=inherited_resource or {},
                        scope_name=inherited_scope,
                        unit=unit,
                    )
                )
        return collected

    # Single duck-typed SDK span instance
    collected.append(
        _extract_one_span(
            payload,
            index=start_index,
            resource_attrs=inherited_resource or {},
            scope_name=inherited_scope,
            unit=unit,
        )
    )
    return collected


def _span_sort_key(span: _NormalizedSpan) -> tuple[bool, int, int]:
    return (span.start_ns is None, span.start_ns or 0, span.index)


def _order_trace_spans(spans: Sequence[_NormalizedSpan]) -> list[_NormalizedSpan]:
    """Order trace spans preserving parent-before-child causality and chronological siblings."""
    by_id: dict[str, _NormalizedSpan] = {}
    duplicates: list[_NormalizedSpan] = []
    for span in spans:
        if span.span_id in by_id:
            duplicates.append(span)
        else:
            by_id[span.span_id] = span

    children: dict[str, list[_NormalizedSpan]] = {sid: [] for sid in by_id}
    roots: list[_NormalizedSpan] = []
    for span in by_id.values():
        parent_id = span.parent_span_id
        if parent_id is not None and parent_id in by_id and parent_id != span.span_id:
            children[parent_id].append(span)
        else:
            roots.append(span)

    roots.sort(key=_span_sort_key)
    for child_list in children.values():
        child_list.sort(key=_span_sort_key)

    ordered: list[_NormalizedSpan] = []
    visited: set[str] = set()

    def _visit(node: _NormalizedSpan) -> None:
        if node.span_id in visited:
            return
        visited.add(node.span_id)
        ordered.append(node)
        for child in children.get(node.span_id, ()):
            _visit(child)

    for root in roots:
        _visit(root)

    # Append any cyclic or duplicate-id spans deterministically by start timestamp.
    leftovers = [s for s in by_id.values() if s.span_id not in visited] + duplicates
    leftovers.sort(key=_span_sort_key)
    for item in leftovers:
        ordered.append(item)
    return ordered


def _first_attr(attrs: Mapping[str, Any], *keys: str, custom: str | None = None) -> Any:
    """Return first non-None value matching optional custom key or fallback attribute list."""
    if custom is not None and custom in attrs and attrs[custom] is not None:
        return attrs[custom]
    for key in keys:
        if key in attrs and attrs[key] is not None:
            return attrs[key]
    return None


def _parse_json_maybe(value: Any) -> Any:
    """Parse structured JSON strings for tool results/messages while leaving prose untouched."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _extract_error_messages(span: _NormalizedSpan) -> list[str]:
    """Collect sanitized error descriptions from span status and exception events."""
    errors: list[str] = []
    if span.status_error:
        msg = span.status_message or f"Span {span.name!r} failed"
        errors.append(scrub_secret_text(msg))
    for ev in span.events:
        if ev.name == "exception" or "exception.message" in ev.attributes:
            exc_type = ev.attributes.get("exception.type")
            exc_msg = ev.attributes.get("exception.message")
            if exc_type and exc_msg:
                text = f"{exc_type}: {exc_msg}"
            elif exc_msg:
                text = str(exc_msg)
            elif exc_type:
                text = str(exc_type)
            else:
                text = ev.name
            errors.append(scrub_secret_text(text))
    return errors


def _infer_tool_status(
    *,
    status_error: bool,
    status_message: str | None,
    error_text: str | None,
    has_parse_error: bool,
) -> ToolCallStatus:
    """Infer canonical ToolCallStatus from span status and error prose."""
    combined = f"{status_message or ''} {error_text or ''}".lower()
    if any(tok in combined for tok in ("timeout", "timed out", "deadline exceeded")):
        return ToolCallStatus.TIMEOUT
    if any(tok in combined for tok in ("blocked", "denied", "forbidden", "unauthorized", "policy")):
        return ToolCallStatus.BLOCKED
    if status_error or bool(error_text and error_text.strip()) or has_parse_error:
        return ToolCallStatus.ERROR
    return ToolCallStatus.SUCCESS


def _resolve_step_kind(span: _NormalizedSpan, extractors: OtelExtractorConfig) -> TraceStepKind:
    """Classify span into canonical TraceStepKind using semantic conventions and overrides."""
    attrs = span.attributes
    if extractors.step_kind_attribute and extractors.step_kind_attribute in attrs:
        raw_custom = str(attrs[extractors.step_kind_attribute]).strip().lower()
        if raw_custom in _STEP_KIND_ALIASES:
            return _STEP_KIND_ALIASES[raw_custom]

    gen_op = attrs.get("gen_ai.operation.name")
    if isinstance(gen_op, str):
        norm_op = gen_op.strip().lower()
        if norm_op in {"execute_tool", "tool"}:
            return TraceStepKind.TOOL_CALL
        if norm_op in {"chat", "text_completion", "generate_content", "completions"}:
            return TraceStepKind.LLM_RESPONSE
        if norm_op in {"embeddings", "retrieve"}:
            return TraceStepKind.OTHER

    oi_kind = attrs.get("openinference.span.kind")
    if isinstance(oi_kind, str):
        norm_oi = oi_kind.strip().lower()
        if norm_oi == "llm":
            return TraceStepKind.LLM_RESPONSE
        if norm_oi == "tool":
            return TraceStepKind.TOOL_CALL
        if norm_oi in {"agent", "chain", "retriever"}:
            return TraceStepKind.OTHER

    traceloop_kind = attrs.get("traceloop.span.kind")
    if isinstance(traceloop_kind, str):
        norm_tl = traceloop_kind.strip().lower()
        if norm_tl in _STEP_KIND_ALIASES:
            return _STEP_KIND_ALIASES[norm_tl]

    if any(k in attrs for k in ("gen_ai.tool.name", "tool.name", "gen_ai.tool.call.id")):
        return TraceStepKind.TOOL_CALL
    if any(
        k in attrs
        for k in (
            "gen_ai.prompt",
            "gen_ai.completion",
            "llm.output_messages",
            "llm.input_messages",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
        )
    ):
        return TraceStepKind.LLM_RESPONSE
    if span.status_error:
        return TraceStepKind.ERROR
    return TraceStepKind.OTHER


def _extract_llm_tool_calls(span: _NormalizedSpan, *, step_index: int) -> list[ToolCallRecord]:
    """Extract declared tool_calls from LLM response messages when present."""
    attrs = span.attributes
    raw_msgs = _first_attr(
        attrs,
        "llm.output_messages",
        "gen_ai.output.messages",
        "gen_ai.completion",
        "llm.completions",
    )
    parsed = _parse_json_maybe(raw_msgs)
    messages: list[Any]
    if isinstance(parsed, Mapping):
        messages = [parsed]
    elif isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes)):
        messages = list(parsed)
    else:
        return []

    records: list[ToolCallRecord] = []
    for msg in messages:
        if not isinstance(msg, Mapping):
            continue
        raw_calls = msg.get("tool_calls") or msg.get("function_calls")
        if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
            continue
        for tc in raw_calls:
            if not isinstance(tc, Mapping):
                continue
            payload = dict(tc)
            payload.setdefault("step_index", step_index)
            records.append(redact_tool_call_record(ToolCallRecord.model_validate(payload)))
    return records


def _extract_span_tool_call(
    span: _NormalizedSpan,
    *,
    step_index: int,
    elapsed_seconds: float | None,
    error_text: str | None,
    extractors: OtelExtractorConfig,
) -> ToolCallRecord | None:
    """Build normalized ToolCallRecord for a TOOL_CALL span."""
    attrs = span.attributes
    raw_name = _first_attr(attrs, *_TOOL_NAME_ATTRS, custom=extractors.tool_name_attribute)
    if raw_name is None:
        raw_name = span.name.removeprefix("tool.") if span.name.startswith("tool.") else span.name
    name = str(raw_name).strip()
    if not name:
        return None

    call_id_raw = _first_attr(attrs, *_TOOL_ID_ATTRS)
    call_id = str(call_id_raw).strip() if call_id_raw is not None else None
    if call_id == "":
        call_id = None

    raw_args = _first_attr(attrs, *_TOOL_ARGS_ATTRS, custom=extractors.tool_arguments_attribute)
    raw_result = _first_attr(attrs, *_TOOL_RESULT_ATTRS, custom=extractors.tool_result_attribute)
    decoded_result = _parse_json_maybe(raw_result)

    payload: dict[str, Any] = {
        "id": call_id,
        "name": name,
        "result": _scrub_any(decoded_result) if decoded_result is not None else None,
        "step_index": step_index,
        "elapsed_seconds": elapsed_seconds,
        "error": error_text,
    }
    if raw_args is not None:
        payload["arguments"] = raw_args
    prelim = ToolCallRecord.model_validate(payload)
    inferred_status = _infer_tool_status(
        status_error=span.status_error,
        status_message=span.status_message,
        error_text=error_text,
        has_parse_error=prelim.argument_parse_error is not None,
    )
    final = prelim.model_copy(update={"status": inferred_status})
    return redact_tool_call_record(final)


def _extract_llm_content(span: _NormalizedSpan) -> Any:
    """Extract compact assistant response text/structure from an LLM span."""
    attrs = span.attributes
    raw = _first_attr(
        attrs,
        "output.value",
        "gen_ai.completion",
        "gen_ai.output.messages",
        "llm.output_messages",
    )
    parsed = _parse_json_maybe(raw)
    if isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes)):
        for item in parsed:
            if isinstance(item, Mapping) and item.get("content"):
                return _scrub_any(item["content"])
    return _scrub_any(parsed)


def _extract_retrieved_chunks(
    spans: Sequence[_NormalizedSpan],
    extractors: OtelExtractorConfig,
) -> list[RetrievedChunk]:
    """Extract and scrub RetrievedChunk records across span attributes and events."""
    chunks: list[RetrievedChunk] = []
    seen_ids: set[str] = set()

    def _add_doc(raw_doc: Any, *, fallback_id: str, rank: int) -> None:
        if isinstance(raw_doc, str):
            chunk_id = fallback_id
            if chunk_id in seen_ids:
                return
            seen_ids.add(chunk_id)
            chunks.append(RetrievedChunk(id=chunk_id, text=scrub_secret_text(raw_doc), rank=rank))
            return
        if not isinstance(raw_doc, Mapping):
            return

        doc_id_raw = _read_attr_or_key(raw_doc, "document.id", "id", "doc_id", "chunk_id")
        chunk_id = str(doc_id_raw).strip() if doc_id_raw is not None else fallback_id
        if not chunk_id:
            chunk_id = fallback_id
        if chunk_id in seen_ids:
            return
        seen_ids.add(chunk_id)

        raw_text = _read_attr_or_key(
            raw_doc,
            "document.content",
            "content",
            "text",
            "page_content",
            "body",
        )
        text = scrub_secret_text(str(raw_text)) if raw_text is not None else ""
        score_raw = _read_attr_or_key(raw_doc, "document.score", "score", "similarity")
        score = (
            float(score_raw)
            if isinstance(score_raw, (int, float)) and not isinstance(score_raw, bool)
            else None
        )
        rank_raw = _read_attr_or_key(raw_doc, "document.rank", "rank")
        doc_rank = (
            int(rank_raw)
            if isinstance(rank_raw, int) and not isinstance(rank_raw, bool) and rank_raw >= 1
            else rank
        )
        parent_raw = _read_attr_or_key(raw_doc, "document.parent_id", "parent_id")
        parent_id = str(parent_raw).strip() if parent_raw is not None else None
        if parent_id == "":
            parent_id = None
        meta_raw = _read_attr_or_key(raw_doc, "document.metadata", "metadata")
        metadata = redact_secrets(dict(meta_raw)) if isinstance(meta_raw, Mapping) else {}
        chunks.append(
            RetrievedChunk(
                id=chunk_id,
                text=text,
                parent_id=parent_id,
                rank=doc_rank,
                score=score,
                metadata=metadata,
            )
        )

    for span in spans:
        raw_docs = _first_attr(
            span.attributes,
            *_RETRIEVAL_ATTRS,
            custom=extractors.retrieval_documents_attribute,
        )
        parsed_docs = _parse_json_maybe(raw_docs)
        if isinstance(parsed_docs, Mapping):
            _add_doc(parsed_docs, fallback_id=f"{span.span_id}-doc-1", rank=len(chunks) + 1)
        elif isinstance(parsed_docs, Sequence) and not isinstance(parsed_docs, (str, bytes)):
            for idx, item in enumerate(parsed_docs, start=1):
                _add_doc(item, fallback_id=f"{span.span_id}-doc-{idx}", rank=len(chunks) + 1)

    return chunks


def _span_token_counts(attrs: Mapping[str, Any]) -> TokenUsage | None:
    """Read token counts from one span's attributes if any recognized token field exists."""

    def _opt_int(keys: tuple[str, ...]) -> int | None:
        val = _first_attr(attrs, *keys)
        if val is None or isinstance(val, bool):
            return None
        if isinstance(val, (int, float)):
            return max(0, int(val))
        return None

    prompt = _opt_int(_PROMPT_TOKEN_ATTRS)
    completion = _opt_int(_COMPLETION_TOKEN_ATTRS)
    reasoning = _opt_int(_REASONING_TOKEN_ATTRS)
    total = _opt_int(_TOTAL_TOKEN_ATTRS)
    if prompt is None and completion is None and reasoning is None and total is None:
        return None
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
        total_tokens=total,
    )


def _aggregate_token_usage(spans: Sequence[_NormalizedSpan]) -> TokenUsage | None:
    """Aggregate TokenUsage across spans without double-counting ancestor rollups."""
    token_spans = [(span, _span_token_counts(span.attributes)) for span in spans]
    reporting_ids = {span.span_id for span, tok in token_spans if tok is not None}
    if not reporting_ids:
        return None

    # Build direct children map to skip parent spans whose descendants already report tokens.
    parent_with_token_descendant: set[str] = set()
    parent_map = {span.span_id: span.parent_span_id for span in spans}
    for sid in reporting_ids:
        cursor = parent_map.get(sid)
        visited: set[str] = {sid}
        while cursor is not None and cursor not in visited:
            visited.add(cursor)
            if cursor in reporting_ids:
                parent_with_token_descendant.add(cursor)
            cursor = parent_map.get(cursor)

    prompt_sum = 0
    completion_sum = 0
    reasoning_sum = 0
    total_sum = 0
    has_prompt = has_completion = has_reasoning = has_total = False

    for span, tok in token_spans:
        if tok is None or span.span_id in parent_with_token_descendant:
            continue
        if tok.prompt_tokens is not None:
            has_prompt = True
            prompt_sum += tok.prompt_tokens
        if tok.completion_tokens is not None:
            has_completion = True
            completion_sum += tok.completion_tokens
        if tok.reasoning_tokens is not None:
            has_reasoning = True
            reasoning_sum += tok.reasoning_tokens
        if tok.total_tokens is not None:
            has_total = True
            total_sum += tok.total_tokens

    return TokenUsage(
        prompt_tokens=prompt_sum if has_prompt else None,
        completion_tokens=completion_sum if has_completion else None,
        reasoning_tokens=reasoning_sum if has_reasoning else None,
        total_tokens=total_sum if has_total else None,
    )


def _merge_tool_calls(candidates: Sequence[ToolCallRecord]) -> list[ToolCallRecord]:
    """Merge repeated ToolCallRecord entries sharing a non-empty call_id cleanly."""
    merged: list[ToolCallRecord] = []
    index_by_id: dict[str, int] = {}

    for rec in candidates:
        if rec.id is None or rec.id not in index_by_id:
            if rec.id is not None:
                index_by_id[rec.id] = len(merged)
            merged.append(rec)
            continue

        pos = index_by_id[rec.id]
        existing = merged[pos]
        merged[pos] = existing.model_copy(
            update={
                "name": rec.name or existing.name,
                "arguments": rec.arguments
                if rec.arguments or rec.raw_arguments
                else existing.arguments,
                "raw_arguments": rec.raw_arguments
                if rec.raw_arguments is not None
                else existing.raw_arguments,
                "argument_parse_error": (
                    rec.argument_parse_error
                    if rec.argument_parse_error is not None
                    else existing.argument_parse_error
                ),
                "result": rec.result if rec.result is not None else existing.result,
                "status": rec.status,
                "error": rec.error if rec.error is not None else existing.error,
                "step_index": rec.step_index if rec.step_index is not None else existing.step_index,
                "elapsed_seconds": (
                    rec.elapsed_seconds
                    if rec.elapsed_seconds is not None
                    else existing.elapsed_seconds
                ),
                "metadata": {**existing.metadata, **rec.metadata},
            }
        )

    return merged


def _normalize_match_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).lower()
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _build_dataset_indices(
    dataset: DatasetEngine | Sequence[EvaluationCase] | None,
) -> tuple[dict[str, EvaluationCase], dict[str, list[EvaluationCase]]]:
    """Index dataset cases by id and normalized input string for correlation."""
    by_id: dict[str, EvaluationCase] = {}
    by_input: dict[str, list[EvaluationCase]] = {}
    if dataset is None:
        return by_id, by_input

    cases: Iterable[EvaluationCase] = (
        dataset.iter_cases() if isinstance(dataset, DatasetEngine) else dataset
    )
    for case in cases:
        by_id[case.id] = case
        by_input.setdefault(_normalize_match_text(case.input), []).append(case)
    return by_id, by_input


def _resolve_case_id(
    trace_id: str,
    ordered_spans: Sequence[_NormalizedSpan],
    extracted_input: Any,
    *,
    extractors: OtelExtractorConfig,
    case_id_map: Mapping[str, str] | None,
    by_input: Mapping[str, list[EvaluationCase]],
) -> str:
    """Resolve deterministic case_id for one trace using explicit map, attribute, or input."""
    if case_id_map and trace_id in case_id_map:
        mapped = str(case_id_map[trace_id]).strip()
        if not mapped:
            raise AdapterError(f"case_id_map mapped trace {trace_id!r} to an empty case_id")
        return mapped

    attr_candidates = (
        (extractors.case_id_attribute,)
        if extractors.case_id_attribute is not None
        else ("evalforge.case_id", "case_id")
    )
    for span in ordered_spans:
        raw_cid = _first_attr(span.attributes, *attr_candidates)
        if raw_cid is not None:
            cleaned = str(raw_cid).strip()
            if cleaned:
                return cleaned

    if extractors.match_dataset_by_input and by_input and extracted_input is not None:
        key = _normalize_match_text(extracted_input)
        matches = by_input.get(key, [])
        if len(matches) == 1:
            return matches[0].id
        if len(matches) > 1:
            raise AdapterError(
                f"Ambiguous dataset input match for OTel trace {trace_id!r}: "
                f"{len(matches)} cases matched"
            )
        raise AdapterError(
            f"OTel trace {trace_id!r} unmatched: no dataset case matched input by "
            "match_dataset_by_input"
        )

    raise AdapterError(
        f"Missing case_id for OTel trace {trace_id!r}: supply evalforge.case_id, "
        "case_id_map, or match_dataset_by_input=True with dataset"
    )


def _trace_to_execution_result(
    trace_id: str,
    raw_spans: Sequence[_NormalizedSpan],
    *,
    extractors: OtelExtractorConfig,
    case_id_map: Mapping[str, str] | None,
    by_id: Mapping[str, EvaluationCase],
    by_input: Mapping[str, list[EvaluationCase]],
    system_version_override: str | None,
    model_id_override: str | None,
    config_fingerprint: str | None,
) -> ExecutionResult:
    """Transform all spans sharing one trace_id into a validated ExecutionResult."""
    ordered = _order_trace_spans(raw_spans)
    span_ids = {s.span_id for s in ordered}
    warnings: list[str] = []
    root_errors: list[str] = []
    all_errors: list[str] = []
    trace_steps: list[AgentTraceStep] = []
    tool_candidates: list[ToolCallRecord] = []

    valid_starts: list[int] = []
    valid_ends: list[int] = []

    for step_idx, span in enumerate(ordered):
        step_elapsed: float | None = None
        if span.start_ns is not None:
            valid_starts.append(span.start_ns)
        if span.end_ns is not None:
            valid_ends.append(span.end_ns)
        if span.start_ns is not None and span.end_ns is not None:
            if span.end_ns < span.start_ns:
                warnings.append(
                    f"Negative clock skew detected on span {span.name!r} ({span.span_id}); "
                    "clamped duration to 0.0s"
                )
                step_elapsed = 0.0
            else:
                step_elapsed = (span.end_ns - span.start_ns) / 1_000_000_000.0

        span_errors = _extract_error_messages(span)
        all_errors.extend(span_errors)
        if span.parent_span_id is None or span.parent_span_id not in span_ids:
            root_errors.extend(span_errors)
        first_err = span_errors[0] if span_errors else None
        kind = _resolve_step_kind(span, extractors)
        tok = _span_token_counts(span.attributes)

        step_tool_calls: list[ToolCallRecord] = []
        step_content: Any = None
        tool_call_id: str | None = None

        if kind == TraceStepKind.LLM_RESPONSE:
            step_tool_calls = _extract_llm_tool_calls(span, step_index=step_idx)
            tool_candidates.extend(step_tool_calls)
            step_content = _extract_llm_content(span)
        elif kind == TraceStepKind.TOOL_CALL:
            tc = _extract_span_tool_call(
                span,
                step_index=step_idx,
                elapsed_seconds=step_elapsed,
                error_text=first_err,
                extractors=extractors,
            )
            if tc is not None:
                tool_candidates.append(tc)
                tool_call_id = tc.id
                step_content = tc.result
        else:
            raw_out = _first_attr(
                span.attributes, *_OUTPUT_ATTRS, custom=extractors.output_attribute
            )
            if raw_out is not None:
                step_content = _scrub_any(raw_out)

        step_status = (
            _infer_tool_status(
                status_error=span.status_error,
                status_message=span.status_message,
                error_text=first_err,
                has_parse_error=False,
            )
            if (span.status_error or first_err is not None or kind == TraceStepKind.TOOL_CALL)
            else None
        )
        step_meta = redact_secrets(
            {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                **({"parent_span_id": span.parent_span_id} if span.parent_span_id else {}),
                **({"scope": span.scope_name} if span.scope_name else {}),
            }
        )
        step = AgentTraceStep(
            step_index=step_idx,
            kind=kind,
            name=span.name,
            content=step_content,
            tool_calls=step_tool_calls,
            tool_call_id=tool_call_id,
            status=step_status,
            error=first_err,
            elapsed_seconds=step_elapsed,
            tokens=tok,
            metadata=step_meta,
        )
        trace_steps.append(redact_trace_step(step))

    if valid_starts and valid_ends:
        span_min = min(valid_starts)
        span_max = max(valid_ends)
        elapsed_seconds = 0.0 if span_max < span_min else (span_max - span_min) / 1_000_000_000.0
    else:
        elapsed_seconds = 0.0

    # Extract case input (preferring root/first spans) and output (root or last LLM output)
    extracted_input: Any = None
    for span in ordered:
        candidate_in = _first_attr(
            span.attributes, *_INPUT_ATTRS, custom=extractors.input_attribute
        )
        if candidate_in is not None:
            extracted_input = _scrub_any(candidate_in)
            break

    extracted_output: Any = None
    if extractors.output_attribute is not None:
        for span in ordered:
            custom_out = _first_attr(span.attributes, custom=extractors.output_attribute)
            if custom_out is not None:
                extracted_output = _scrub_any(custom_out)
                break
    if extracted_output is None:
        # Prefer top-level root span output first; otherwise fall back to last span output
        for span in ordered:
            if span.parent_span_id is None:
                root_out = _first_attr(
                    span.attributes, "output.value", "traceloop.entity.output", "output"
                )
                if root_out is not None:
                    extracted_output = _scrub_any(root_out)
                    break
    if extracted_output is None:
        for span in reversed(ordered):
            fallback_out = _first_attr(span.attributes, *_OUTPUT_ATTRS)
            if fallback_out is not None:
                extracted_output = _scrub_any(_parse_json_maybe(fallback_out))
                break

    case_id = _resolve_case_id(
        trace_id,
        ordered,
        extracted_input,
        extractors=extractors,
        case_id_map=case_id_map,
        by_input=by_input,
    )
    matched_case = by_id.get(case_id)
    final_input = (
        extracted_input
        if extracted_input is not None
        else (matched_case.input if matched_case else None)
    )

    resolved_model = model_id_override
    if resolved_model is None:
        for span in ordered:
            raw_m = _first_attr(span.attributes, *_MODEL_ATTRS, custom=extractors.model_attribute)
            if raw_m is not None and str(raw_m).strip():
                resolved_model = str(raw_m).strip()
                break

    resolved_version = system_version_override
    if resolved_version is None:
        for span in ordered:
            raw_v = _first_attr(
                span.attributes,
                *_SERVICE_VERSION_ATTRS,
                custom=extractors.service_version_attribute,
            ) or _first_attr(
                span.resource_attributes,
                *_SERVICE_VERSION_ATTRS,
                custom=extractors.service_version_attribute,
            )
            if raw_v is not None and str(raw_v).strip():
                resolved_version = str(raw_v).strip()
                break

    chunks = _extract_retrieved_chunks(ordered, extractors)
    merged_tools = _merge_tool_calls(tool_candidates)
    tokens = _aggregate_token_usage(ordered)

    # Deduplicate exact warning/error strings; only escalate fatal trace-level errors so
    # recovered child tool timeouts remain scorable by downstream M2/M6 metrics.
    dedup_warnings = list(dict.fromkeys(warnings))
    if root_errors:
        dedup_errors = list(dict.fromkeys(root_errors))
    elif extracted_output is None and all_errors:
        dedup_errors = list(dict.fromkeys(all_errors))
    else:
        dedup_errors = []
    meta = redact_secrets(
        {
            "source": "otel",
            "trace_id": trace_id,
            "span_count": len(ordered),
            **(
                {"service_name": ordered[0].resource_attributes["service.name"]}
                if "service.name" in ordered[0].resource_attributes
                else {}
            ),
        }
    )

    synthetic_case = (
        matched_case.model_copy(update={"input": final_input})
        if matched_case is not None
        else EvaluationCase(id=case_id, input=final_input)
    )
    return build_validated_execution_result(
        case=synthetic_case,
        output=extracted_output,
        retrieved_chunks=chunks,
        trace=trace_steps,
        tool_calls=merged_tools,
        tokens=tokens,
        elapsed_seconds=elapsed_seconds,
        truncated=False,
        errors=dedup_errors,
        warnings=dedup_warnings,
        system_version=resolved_version,
        model_id=resolved_model,
        config_fingerprint=config_fingerprint,
        adapter_metadata=meta,
    )


def ingest_otel_spans(
    payload: Any,
    *,
    extractors: OtelExtractorConfig | None = None,
    dataset: DatasetEngine | Sequence[EvaluationCase] | None = None,
    case_id_map: Mapping[str, str] | None = None,
    system_version: str | None = None,
    model_id: str | None = None,
) -> list[ExecutionResult]:
    """Normalize OTLP JSON, flat span sequences, or duck-typed SDK spans into ExecutionResults."""
    cfg = extractors or OtelExtractorConfig()
    spans = _flatten_payload(payload, unit=cfg.timestamp_unit)
    if not spans:
        raise AdapterError("OTel payload contains zero spans")

    grouped: dict[str, list[_NormalizedSpan]] = {}
    for span in spans:
        grouped.setdefault(span.trace_id, []).append(span)

    by_id, by_input = _build_dataset_indices(dataset)
    config_fp, _ = redact_adapter_config(cfg.model_dump(mode="json"))

    results: list[ExecutionResult] = []
    seen_case_ids: set[str] = set()
    for trace_id, trace_spans in grouped.items():
        exec_res = _trace_to_execution_result(
            trace_id,
            trace_spans,
            extractors=cfg,
            case_id_map=case_id_map,
            by_id=by_id,
            by_input=by_input,
            system_version_override=system_version,
            model_id_override=model_id,
            config_fingerprint=config_fp,
        )
        if exec_res.case_id in seen_case_ids:
            raise AdapterError(
                f"Duplicate case_id {exec_res.case_id!r} resolved across multiple OTel traces"
            )
        seen_case_ids.add(exec_res.case_id)
        results.append(exec_res)

    return results


def load_otel_executions(
    path: Path | str,
    *,
    extractors: OtelExtractorConfig | None = None,
    dataset: DatasetEngine | Sequence[EvaluationCase] | None = None,
    case_id_map: Mapping[str, str] | None = None,
    system_version: str | None = None,
    model_id: str | None = None,
) -> list[ExecutionResult]:
    """Load OTLP JSON, flat span array JSON, or JSONL traces from disk into ExecutionResults."""
    resolved = Path(path)
    if not resolved.is_file():
        raise DatasetError(f"OTel trace file not found: {resolved}")

    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetError(f"Failed reading OTel trace file {resolved}: {exc}") from exc

    if not raw_text.strip():
        raise DatasetError(f"OTel trace file is empty: {resolved}")

    payload: Any
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as full_exc:
        lines: list[Any] = []
        for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                parsed_line = json.loads(stripped)
            except json.JSONDecodeError as line_exc:
                raise DatasetError(
                    f"Invalid JSON in OTel trace file {resolved} at line {line_no}: {line_exc.msg}",
                    line_number=line_no,
                ) from (full_exc if line_no == 1 else line_exc)
            if not isinstance(parsed_line, Mapping):
                raise DatasetError(
                    f"OTel JSONL line {line_no} in {resolved} must decode to a JSON object",
                    line_number=line_no,
                ) from None
            lines.append(parsed_line)
        payload = lines

    return ingest_otel_spans(
        payload,
        extractors=extractors,
        dataset=dataset,
        case_id_map=case_id_map,
        system_version=system_version,
        model_id=model_id,
    )


__all__ = [
    "ingest_otel_spans",
    "load_otel_executions",
]
