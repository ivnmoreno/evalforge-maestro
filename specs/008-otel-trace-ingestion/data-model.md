# Data Model: OpenTelemetry Execution Trace Ingestion

**Feature**: `008-otel-trace-ingestion`  
**Date**: 2026-11-21  
**Spec**: [`spec.md`](spec.md)

All public models live in [`src/evalforge_maestro/types.py`](../../src/evalforge_maestro/types.py) (`_StrictModel`, `extra="forbid"`, JSON-safe, zero NaN/Inf/bool-as-int coercion).

## 1. Enumerations (`types.py`)

### `OtelTimestampUnit(str, Enum)`
- `AUTO = "auto"` (auto-detects ns `>= 1e14`, us `>= 1e11`, ms `>= 1e10`? Wait: s epoch in 2020-2100 is `~1.6e9-4.1e9`; ms is `~1.6e12`; us is `~1.6e15`; ns is `~1.6e18`; small relative offsets `< 1e9` in seconds or explicit units cleanly)
- `NS = "ns"`
- `US = "us"`
- `MS = "ms"`
- `S = "s"`

## 2. Configuration Schema Extensions (`types.py`)

### `OtelExtractorConfig(_StrictModel)`
Typed configuration governing OpenTelemetry attribute extraction, timestamp normalization, and case-ID correlation:
- `case_id_attribute: str | None = None` — Custom attribute key/path inspected first for dataset `case_id`.
- `input_attribute: str | None = None` — Custom attribute key/path overriding default prompt/input lookup.
- `output_attribute: str | None = None` — Custom attribute key/path overriding default response/output lookup.
- `model_attribute: str | None = None` — Custom attribute key/path overriding default `gen_ai.*.model` lookup.
- `service_version_attribute: str | None = None` — Custom attribute key/path overriding `service.version`.
- `step_kind_attribute: str | None = None` — Custom attribute key/path overriding span kind classification.
- `tool_name_attribute: str | None = None` — Custom attribute key/path for tool names.
- `tool_arguments_attribute: str | None = None` — Custom attribute key/path for tool arguments JSON/dict.
- `tool_result_attribute: str | None = None` — Custom attribute key/path for tool output/result payloads.
- `retrieval_documents_attribute: str | None = None` — Custom attribute key/path for retrieved chunks.
- `timestamp_unit: OtelTimestampUnit = OtelTimestampUnit.AUTO`
- `match_dataset_by_input: bool = False` — Explicitly enables unambiguous whitespace-normalized input matching against dataset cases when trace lacks an explicit `case_id` attribute.

Validators:
- All optional string attribute fields validated with `_validate_optional_str` (non-empty when set).
- `redacted_dict()` / strict `extra="forbid"`.

### `CLIResolvedConfig` Extensions (`types.py`)
Additive optional fields preserving legacy M5/M6/M7 backward compatibility:
- `otel_traces: str | None = None` — Optional path to an OTLP JSON, flat span JSON array, or JSONL span file loaded as offline replay source during `run`.
- `otel: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)` — Effective resolved OTel extractor/correlation settings.

Notice:
- Existing persisted contracts (`RunRecord`, `RunManifestEntry`, `ExecutionResult`, `ToolCallRecord`, `AgentTraceStep`, `TokenUsage`, `RetrievedChunk`, `QualityGatePolicy`, `ReportDocument`) require **zero** schema changes! Imported OTel traces map directly into canonical `ExecutionResult` instances with OTel provenance (`trace_id`, `span_count`, `resource_attributes` redacted) inside `ExecutionResult.adapter_metadata["otel"]`.

## 3. Trace Mapping Table (`OTel` -> Canonical `ExecutionResult`)

| OTel Source | Canonical Target | Normalization Rule |
|---|---|---|
| Trace ID (`trace_id` / `traceId`) | `ExecutionResult.adapter_metadata["otel"]["trace_id"]` + grouping key | Hex/int/bytes normalized to 32-char lowercase hex |
| Case ID (`case_id_map`, `config.case_id_attribute`, `evalforge.case_id`, `case.id`, `case_id`, opt-in input match) | `ExecutionResult.case_id` | Fail explicitly on missing, ambiguous, or duplicate `case_id` |
| Resource `service.version` / `config.service_version_attribute` | `ExecutionResult.system_version` | Overridden by explicit caller/CLI `--system-version` if provided |
| Span `gen_ai.response.model` / `gen_ai.request.model` / `llm.model_name` | `ExecutionResult.model_id` | First non-empty LLM model identifier in trace, overridden by caller `--model-id` |
| Trace min(start)..max(end) duration | `ExecutionResult.elapsed_seconds` | Clamped >= `0.0` (appending warning on clock skew) |
| Root/chain input -> LLM prompt -> dataset input | `ExecutionResult.input` | Scrubbed string or JSON-safe structure |
| Root/chain output -> last non-empty `FINAL_OUTPUT` / `LLM_RESPONSE` | `ExecutionResult.output` | Scrubbed string or JSON-safe structure |
| `gen_ai.usage.*`, `llm.token_count.*` | `ExecutionResult.tokens` (`TokenUsage`) + step `tokens` | Non-negative ints; summed across LLM spans avoiding wrapper double-count |
| Tool spans (`gen_ai.tool.*`, `tool.*`, `TOOL`) + LLM tool-call intents | `ExecutionResult.tool_calls` (`list[ToolCallRecord]`) | Deduplicated/merged on `id`; invalid JSON args preserve `raw_arguments` + `argument_parse_error`; status mapped cleanly (`SUCCESS`, `ERROR`, `TIMEOUT`, `BLOCKED`) |
| Ordered spans (`(start, depth, span_id)`) | `ExecutionResult.trace` (`list[AgentTraceStep]`) | Sequential `step_index = 0..K-1`, `TraceStepKind`, secret-scrubbed |
| Retrieval spans/events (`retrieval.documents`, `gen_ai.retrieval.documents`) | `ExecutionResult.retrieved_chunks` (`list[RetrievedChunk]`) | 1-based normalized `rank` defaulted cleanly if missing |
| Span `status == ERROR` & exception events | `ExecutionResult.errors`, step `error`, tool `status=ERROR` | Secret-scrubbed error summaries |
