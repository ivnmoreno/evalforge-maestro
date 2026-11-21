# Phase 0 Research: OpenTelemetry Execution Trace Ingestion

**Feature**: `008-otel-trace-ingestion`  
**Date**: 2026-11-21  
**Spec**: [`spec.md`](spec.md)

## Research Decisions

### 1. Zero Core Dependency Footprint vs. Optional OTel SDK Interop
- **Decision**: Implement OTLP JSON (`ExportTraceServiceRequest`), flat JSON span array, JSONL span stream, and in-memory span ingestion using pure Python stdlib (`json`, `datetime`, `re`) + `pydantic` v2, using structural attribute/duck-typing (`getattr`) when given Python span objects (e.g., `opentelemetry.sdk.trace.ReadableSpan` or compatible mocks).
- **Rationale**: Keeps `pyproject.toml` core dependencies strictly limited to `pydantic>=2.7` per Constitution Technical Constraints, avoids heavy transitive protobuf/gRPC/OTel dependencies or import-time overhead in `--help`, and supports live in-memory SDK spans seamlessly without extra optional packages.
- **Alternatives rejected**: Adding `opentelemetry-proto` or `opentelemetry-sdk` to core or mandatory runtime extras (unnecessary heavyweight footprint when OTLP JSON exports use standard JSON envelopes and in-memory span reading only needs simple attribute inspection).

### 2. OTLP JSON Encoding & Typed `AnyValue` Unwrapping
- **Decision**: Support both simplified JSON dicts (`{"key": val}`) and full OTLP protobuf-JSON format (`resourceSpans[*].scopeSpans[*].spans[*]` with typed `attributes: [{"key": k, "value": {"stringValue" | "intValue" | "doubleValue" | "boolValue" | "bytesValue" | "arrayValue" | "kvlistValue"}}]` and event attributes). Unwrap integers encoded as JSON strings inside OTLP `intValue` (`"123"` -> `123`) and decode `startTimeUnixNano` / `endTimeUnixNano` consistently alongside `auto`/`ns`/`us`/`ms`/`s` units.
- **Rationale**: Real OpenTelemetry Collector file exporters, Grafana Tempo exports, Jaeger OTLP JSON dumps, and Honeycomb/Phoenix JSON exports frequently serialize 64-bit `intValue` and `*UnixNano` fields as JSON strings. Supporting both stringified ints and native JSON numbers prevents real-world parse failures.
- **Alternatives rejected**: Requiring pre-flattened custom JSON wrappers (defeats direct ingestion of collector exports).

### 3. Semantic Conventions & Custom Extractor Precedence
- **Decision**: Resolve fields in priority order:
  1. Explicit `OtelExtractorConfig` custom attribute keys (`case_id_attribute`, `input_attribute`, `output_attribute`, `model_attribute`, `service_version_attribute`, `step_kind_attribute`, `tool_name_attribute`, `tool_arguments_attribute`, `tool_result_attribute`, `retrieval_documents_attribute`), supporting dot-path traversal inside nested JSON objects/KV lists;
  2. Official OTel GenAI Semantic Conventions (`gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.choice`, `gen_ai.retrieval.documents`);
  3. Community OTel conventions (OpenInference `openinference.span.kind`, `llm.*`, `input.value`, `output.value`, `tool.*`, `retrieval.documents`; Traceloop `traceloop.*`, `entity.input`, `entity.output`).
- **Rationale**: Covers all major instrumentation libraries (official OTel GenAI SIG, Arize OpenInference, Traceloop/OpenLLMetry, custom internal telemetry) deterministically via one declarative table.
- **Alternatives rejected**: Hardcoding a single vendor namespace.

### 4. Span Ordering, Tool-Call Deduplication & Token Aggregation
- **Decision**:
  - Group spans by normalized lowercase hex `trace_id` and compute parent-child depth within the trace (handling missing/orphan parents gracefully at depth `0`).
  - Order steps deterministically by `(start_seconds_or_inf, tree_depth, span_id, encounter_index)`.
  - Deduplicate/merge tool call intents emitted inside an `LLM_RESPONSE` span with matching child `TOOL_CALL` execution spans sharing the same normalized `tool_call_id`, preferring runtime `status`/`result`/`error`/`elapsed_seconds` from the child tool span so `ToolEfficiencyMetric` never double-counts one tool call as two.
  - Aggregate `TokenUsage` across `LLM_RESPONSE` spans (avoiding naive double-counting of non-LLM chain wrapper spans unless no `LLM_RESPONSE` span carries usage), computing missing `total_tokens` when `prompt_tokens` and `completion_tokens` are present.
- **Rationale**: Directly prevents inflated step counts, double-counted tool calls in `ToolEfficiencyMetric` / `ExecutionSequenceMetric`, and inflated token usage totals on nested trace trees.

### 5. Unambiguous Case Correlation & Immutability / Secret Safety
- **Decision**: Resolve `case_id` cleanly in order: (1) explicit caller `case_id_map[trace_id]`, (2) `config.case_id_attribute` / built-in `evalforge.case_id` / `evalforge_case_id` / `case.id` / `case_id` attribute on spans in the trace, (3) opt-in (`match_dataset_by_input=True`) exact whitespace-normalized match against `dataset` case `input` (failing on `0` or `>1` ambiguous matches). Duplicate `case_id` or missing `case_id` raises `AdapterError` (mapped cleanly to `DatasetError` / POSIX exit code `2` at CLI/file boundaries). Apply `_trace_norm` secret redaction & `_canonical.scrub_secret_text` across every trace field and span metadata at ingestion time.
- **Rationale**: Preserves Constitution Principles V & VI (deterministic correlation, zero silent overwrites, zero leaked credentials in replay or `RunRecord` artifacts).
