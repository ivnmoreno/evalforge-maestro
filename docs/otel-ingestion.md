# OpenTelemetry Execution Trace Ingestion Guide

`evalforge-maestro` ingests OpenTelemetry (OTel) execution traces produced by any agent runtime, RAG pipeline, or LLM instrumentation library and converts them into deterministic, secret-scrubbed canonical [`ExecutionResult`](../src/evalforge_maestro/types.py) records—**without requiring any `opentelemetry-*` package at runtime**.

This design allows CI pipelines, local developer workstations, and offline evaluation suites to score production or staging telemetry using all deterministic text, retrieval (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`), embedding (`embedding_similarity`, `context_embedding_similarity`), agent (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`), and judge metrics seamlessly.

---

## 1. Zero-Dependency Architecture & Guarantees

| Property | Behavior in `evalforge-maestro` |
| --- | --- |
| **Runtime Dependencies** | Zero core or optional OTel SDK dependencies required; parsing operates on standard JSON/JSONL or duck-typed in-memory span objects. |
| **Cold-Start Purity** | `import evalforge_maestro` and `evalforge-maestro --help` never import `opentelemetry`, `opentelemetry_sdk`, `litellm`, `docpipe_maestro`, `numpy`, or `scipy`. |
| **Secret Redaction** | API keys (`sk-*`, `AIza*`, `hf_*`, `gsk_*`), `Bearer` tokens, URL credentials (`https://user:pass@`), PII patterns (when scrubbed), and sensitive dict keys (`api_key`, `token`, `password`, `authorization`, `secret`, etc.) are automatically masked with `[REDACTED]` across outputs, tool arguments, tool results, chunk metadata, step metadata, and exception events. |
| **Trace Ordering** | Spans sharing a `trace_id` are ordered by causal parent-child depth-first traversal with chronological sibling sorting and cycle/orphan protection. |
| **Tool Deduplication** | Repeated tool declarations across an LLM assistant span (`llm.output_messages` / `tool_calls`) and its dedicated child execution span (`execute_tool`) sharing a non-empty `call_id` merge into one canonical `ToolCallRecord`—keeping status, latency, parsed arguments, and tool result authoritative. |
| **Malformed Argument Preservation** | Invalid JSON inside tool arguments never aborts trace ingestion: `arguments` stays `{}` while `raw_arguments` and `argument_parse_error` capture the exact diagnostic payload so `ArgumentCorrectnessMetric` and `PolicyComplianceMetric` can score failure modes accurately. |
| **Anti-Double-Counting Tokens** | Descendant-aware token aggregation sums leaf LLM spans while ignoring rolled-up totals on ancestor `AGENT`/`CHAIN` spans when child spans already report token counts. |

---

## 2. Supported Trace Input Formats

`ingest_otel_spans(...)`, `load_otel_executions(...)`, and `ReplayAdapter.from_otel_file(...)` accept four equivalent trace representations:

### 2.1 OTLP/HTTP JSON (`ExportTraceServiceRequest`)

Standard `resourceSpans -> scopeSpans -> spans` envelope exported by OpenTelemetry Collectors, Jaeger, Phoenix, Langfuse, OpenLLMetry, or OTLP file exporters—including nested OTLP `AnyValue` wrappers (`stringValue`, `intValue`, `doubleValue`, `boolValue`, `bytesValue`, `arrayValue`, `kvlistValue`) and `[{"key": ..., "value": ...}]` attribute lists:

```json
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "billing-agent"}},
          {"key": "service.version", "value": {"stringValue": "2.4.0"}}
        ]
      },
      "scopeSpans": [
        {
          "scope": {"name": "openinference.instrumentation"},
          "spans": [
            {
              "traceId": "0102030405060708090a0b0c0d0e0f10",
              "spanId": "1111111111111111",
              "name": "agent.run",
              "startTimeUnixNano": "1700000000000000000",
              "endTimeUnixNano": "1700000001500000000",
              "attributes": [
                {"key": "evalforge.case_id", "value": {"stringValue": "case-inv-1"}},
                {"key": "input.value", "value": {"stringValue": "Check invoice 42"}},
                {"key": "output.value", "value": {"stringValue": "Invoice 42 is paid"}},
                {"key": "openinference.span.kind", "value": {"stringValue": "AGENT"}}
              ],
              "status": {"code": 1}
            }
          ]
        }
      ]
    }
  ]
}
```

### 2.2 Flat JSON Span Array

A top-level JSON list `[span_1, span_2, ...]` where spans from multiple traces may appear in arbitrary order using either camelCase (`traceId`, `spanId`, `parentSpanId`, `startTimeUnixNano`) or snake_case (`trace_id`, `span_id`, `parent_span_id`, `start_time`, `end_time`) keys and plain dict attributes:

```json
[
  {
    "trace_id": "trace-b",
    "span_id": "sb1",
    "name": "agent.run",
    "start_time": 1700000002000000,
    "end_time": 1700000003000000,
    "attributes": {
      "evalforge.case_id": "c-beta",
      "input.value": "Who manages keys?",
      "output.value": "Security team"
    }
  }
]
```

### 2.3 Interleaved JSONL Span Stream

Line-delimited JSON (`.jsonl`), where each non-blank line is either a flat span object or an `ExportTraceServiceRequest` envelope. Interleaved spans from concurrent traces are automatically grouped by `trace_id` while preserving first-seen trace order:

```jsonl
{"trace_id": "t1", "span_id": "s1", "name": "agent", "attributes": {"evalforge.case_id": "c1", "input.value": "Q1"}}
{"trace_id": "t2", "span_id": "s1", "name": "agent", "attributes": {"evalforge.case_id": "c2", "input.value": "Q2"}}
{"trace_id": "t1", "span_id": "s2", "parent_span_id": "s1", "name": "llm.chat", "attributes": {"gen_ai.operation.name": "chat", "gen_ai.completion": "A1"}}
```

### 2.4 In-Memory Duck-Typed Python SDK `ReadableSpan` Objects

When integrating with OpenTelemetry Python SDK tests (`InMemorySpanExporter.get_finished_spans()`), pass the list of `ReadableSpan`-like objects directly to `ingest_otel_spans(exporter.get_finished_spans())` without serializing to JSON or importing `opentelemetry` inside `evalforge-maestro`. Any object exposing `.context` (or `.get_span_context()`), `.parent`, `.name`, `.start_time`, `.end_time`, `.attributes`, `.events`, `.status` (with `.status_code` + `.description`), and `.resource` is normalized cleanly—including integer/bytes `trace_id` and `span_id` conversion to lowercase hexadecimal (`32` / `16` hex characters).

---

## 3. Semantic Conventions & Attribute Precedence

Attribute lookup checks **explicit overrides** (`OtelExtractorConfig` / `[otel]` / `--otel-*`) **first**, then falls back across standard OpenTelemetry semantic conventions in deterministic priority order:

| Target Field | Custom Override (`OtelExtractorConfig`) | Built-in Fallback Keys (in Priority Order) |
| --- | --- | --- |
| `case_id` | `case_id_attribute` | `evalforge.case_id`, `case_id` *(see Section 5 for full precedence)* |
| `input` | `input_attribute` | `gen_ai.input.messages`, `gen_ai.prompt`, `input.value`, `traceloop.entity.input`, `llm.input_messages`, `input` |
| `output` | `output_attribute` | Root span: `output.value`, `traceloop.entity.output`, `output`; fallback reverse-span: `output.value`, `gen_ai.output.messages`, `gen_ai.completion`, `traceloop.entity.output`, `llm.output_messages`, `output` |
| `model_id` | `model_attribute` | `gen_ai.response.model`, `gen_ai.request.model`, `llm.model_name`, `model` |
| `system_version` | `service_version_attribute` | Span or `Resource` attributes: `service.version`, `app.version` |
| `TraceStepKind` | `step_kind_attribute` | `gen_ai.operation.name` (`execute_tool`/`chat`/etc.), `openinference.span.kind` (`LLM`/`TOOL`/`AGENT`/`RETRIEVER`), `traceloop.span.kind`, or signature tool/LLM keys |
| Tool `name` | `tool_name_attribute` | `gen_ai.tool.name`, `tool.name`, `tool_name`, `traceloop.entity.name`, or span name minus `"tool."` |
| Tool `id` | — | `gen_ai.tool.call.id`, `tool.call.id`, `tool_call.id`, `tool_call_id` |
| Tool `arguments` | `tool_arguments_attribute` | `gen_ai.tool.call.arguments`, `tool.parameters`, `tool.arguments`, `tool.input`, `input.value` |
| Tool `result` | `tool_result_attribute` | `gen_ai.tool.call.result`, `tool.result`, `tool.output`, `output.value` |
| `retrieved_chunks` | `retrieval_documents_attribute` | `retrieval.documents`, `retriever.documents`, `retrieval_documents`, `documents` |
| Prompt tokens | — | `gen_ai.usage.input_tokens`, `gen_ai.usage.prompt_tokens`, `llm.token_count.prompt` |
| Completion tokens | — | `gen_ai.usage.output_tokens`, `gen_ai.usage.completion_tokens`, `llm.token_count.completion` |
| Reasoning tokens | — | `gen_ai.usage.reasoning_tokens`, `llm.token_count.completion_details.reasoning`, `llm.token_count.reasoning` |
| Total tokens | — | `gen_ai.usage.total_tokens`, `llm.token_count.total` *(otherwise `prompt + completion`)* |

Document entries inside retrieval lists recognize both OpenInference dotted keys (`document.id`, `document.content`, `document.score`, `document.rank`, `document.parent_id`, `document.metadata`) and flat dictionary keys (`id` / `doc_id` / `chunk_id`, `text` / `content` / `page_content` / `body`, `score` / `similarity`, `rank`, `parent_id`, `metadata`), as well as plain strings and JSON-encoded document arrays.

---

## 4. Normalization Details: Timestamps, Errors & Tool Merging

### 4.1 Timestamp Units & Clock Skew
`OtelTimestampUnit` controls numeric timestamp interpretation (`AUTO`, `NS`, `US`, `MS`, `S`). ISO-8601 strings (with `Z` or explicit timezone offsets) and `datetime` objects are always supported.

Under default `timestamp_unit = "auto"`:
- Magnitude `>= 1e17`: nanoseconds (`ns`)
- `1e14 <= magnitude < 1e17`: microseconds (`us`)
- `1e11 <= magnitude < 1e14`: milliseconds (`ms`)
- `< 1e11`: seconds (`s`)

If a span has `end_time < start_time`, `evalforge-maestro` clamps step duration (and negative trace duration) to `0.0` seconds and appends a diagnostic warning containing `"Negative clock skew detected..."` to `ExecutionResult.warnings`.

### 4.2 Fatal Root Errors vs. Recovered Child Tool Failures
EvalForge metrics treat non-empty `ExecutionResult.errors` as a target execution outage (`MetricStatus.INCONCLUSIVE`). Accordingly:
- **Child tool span error with healthy root span** (`status.code = 2` on `tool.audit_log`, while root `agent.run` succeeded with `output`): Recorded cleanly on `ToolCallRecord.status` (`ERROR` / `TIMEOUT` / `BLOCKED`), `ToolCallRecord.error`, and `AgentTraceStep.error`, leaving `ExecutionResult.errors == []` so downstream M2/M6 metrics—including `FailureRecoveryMetric`—can evaluate recovery.
- **Root / orphan span error or fatal failure without output**: Populates `ExecutionResult.errors` with scrubbed span status messages and `"exception"` event messages (`exception.type: exception.message`).

### 4.3 Tool Status Inference & Call Deduplication
Tool span statuses map automatically to `ToolCallStatus`:
- Contains `"timeout"`, `"timed out"`, or `"deadline exceeded"` -> `ToolCallStatus.TIMEOUT`
- Contains `"blocked"`, `"denied"`, `"forbidden"`, `"unauthorized"`, or `"policy"` -> `ToolCallStatus.BLOCKED`
- Non-OK span status, non-empty error string, or `argument_parse_error` -> `ToolCallStatus.ERROR`
- Otherwise -> `ToolCallStatus.SUCCESS`

When an LLM span proposes tool calls (`llm.output_messages`) with `id = "call_123"` and a subsequent `execute_tool` span runs with `gen_ai.tool.call.id = "call_123"`, both records merge into a single `ToolCallRecord` at its original timeline index.

---

## 5. Case Correlation Precedence (Fail-Closed)

Every trace must resolve deterministically to a unique `case_id`. Precedence is evaluated strictly in order:

1. **Explicit caller mapping**: `case_id_map[trace_id]` (Python SDK).
2. **Custom attribute override**: `extractors.case_id_attribute` (if configured on `OtelExtractorConfig`, `[otel]`, or `--otel-case-id-attr`).
3. **Standard EvalForge / trace attributes**: `"evalforge.case_id"` or `"case_id"`.
4. **Opt-in dataset input matching**: Only when `match_dataset_by_input=True` (`--otel-match-input` / `EVALFORGE_OTEL_MATCH_INPUT=true`) and `dataset` is supplied. Compares whitespace-collapsed, lowercased trace input against dataset `EvaluationCase.input`.

**Fail-closed rejections**:
- Missing correlation -> `AdapterError` (SDK) / `DatasetError` (CLI exit code `2`).
- Two traces resolving to the same `case_id` -> `AdapterError` (`Duplicate case_id ...`) / exit code `2`.
- Multiple dataset cases sharing the same input text under `match_dataset_by_input=True` -> `AdapterError` (`Ambiguous dataset input match ...`) / exit code `2`.
- Missing or extra dataset cases during `evalforge-maestro run --otel-traces` -> alignment failure (exit code `2`) identical to `--executions`.

---

## 6. CLI Workflows & Configuration Reference

### 6.1 Subcommand `evalforge-maestro ingest-otel`

Normalize an OTel trace export into schema-validated, secret-scrubbed `ExecutionResult` JSON or JSONL replay artifacts:

```bash
evalforge-maestro ingest-otel traces/otel.json \
  --dataset dataset.jsonl \
  --output replays.jsonl \
  --system-version billing-agent-v2.4 \
  --model-id glm-5.3 \
  --json
```

Options:
- `otel_path` *(positional)*: Path to OTLP JSON, flat span array JSON, or JSONL trace file.
- `--dataset PATH`, `--dataset-id STR`, `--dataset-version STR`: Optional dataset alignment for input fallback matching (`--otel-match-input`) or canonical input backfill.
- `--output PATH`: Write `.json` (pretty JSON array when filename ends in `.json`) or `.jsonl` (one canonical `ExecutionResult` JSON object per line, ready for `run --executions`).
- `--system-version STR`, `--model-id STR`: Metadata overrides.
- Extractor overrides: `--otel-case-id-attr`, `--otel-input-attr`, `--otel-output-attr`, `--otel-model-attr`, `--otel-service-version-attr`, `--otel-step-kind-attr`, `--otel-tool-name-attr`, `--otel-tool-args-attr`, `--otel-tool-result-attr`, `--otel-retrieval-attr`, `--otel-timestamp-unit {auto,ns,us,ms,s}`, `--otel-match-input`.
- `--json`, `--quiet`, `--config`, `--env-file`, `--log-level`, `--log-json`.

### 6.2 Offline Evaluation via `evalforge-maestro run --otel-traces`

Evaluate an OTel export directly against a golden dataset with full orchestrator controls (`--max-context-chars`, `--repeats`, `--baseline`, `--strict`, `--fail-on-significant-regression`):

```bash
evalforge-maestro run \
  --dataset examples/ci/golden-sample.jsonl \
  --otel-traces examples/ci/otel-traces-sample.json \
  --metric normalized_match \
  --metric precision_at_k:k=1 \
  --metric tool_selection \
  --strict \
  --json \
  --json-out report.json \
  --markdown-out report.md
```

> [!IMPORTANT]
> `--otel-traces` is mutually exclusive with `--executions` and live target flags (`--target`, `--target-type callable|rag|docpipe|agent`). Combining them raises `ConfigurationError` and exits with code `2`.

### 6.3 5-Tier Precedence (`evalforge.toml`, `.env`, Env Vars, CLI)

All settings follow `CLI flags > OS env (EVALFORGE_OTEL_*) > --env-file > CWD/specified evalforge.toml > defaults`:

```toml
# evalforge.toml
[run]
dataset = "dataset.jsonl"
otel_traces = "traces/otel-export.json"

[otel]
case_id_attribute = "app.case_id"
input_attribute = "app.input"
output_attribute = "app.output"
model_attribute = "gen_ai.request.model"
service_version_attribute = "service.version"
step_kind_attribute = "openinference.span.kind"
tool_name_attribute = "tool.name"
tool_arguments_attribute = "tool.parameters"
tool_result_attribute = "tool.output"
retrieval_documents_attribute = "retrieval.documents"
timestamp_unit = "auto" # auto | ns | us | ms | s
match_dataset_by_input = false
```

Environment variable mapping:
- `[run].otel_traces` -> `EVALFORGE_OTEL_TRACES`
- `[otel].case_id_attribute` -> `EVALFORGE_OTEL_CASE_ID_ATTR`
- `[otel].input_attribute` -> `EVALFORGE_OTEL_INPUT_ATTR`
- `[otel].output_attribute` -> `EVALFORGE_OTEL_OUTPUT_ATTR`
- `[otel].model_attribute` -> `EVALFORGE_OTEL_MODEL_ATTR`
- `[otel].service_version_attribute` -> `EVALFORGE_OTEL_SERVICE_VERSION_ATTR`
- `[otel].step_kind_attribute` -> `EVALFORGE_OTEL_STEP_KIND_ATTR`
- `[otel].tool_name_attribute` -> `EVALFORGE_OTEL_TOOL_NAME_ATTR`
- `[otel].tool_arguments_attribute` -> `EVALFORGE_OTEL_TOOL_ARGS_ATTR`
- `[otel].tool_result_attribute` -> `EVALFORGE_OTEL_TOOL_RESULT_ATTR`
- `[otel].retrieval_documents_attribute` -> `EVALFORGE_OTEL_RETRIEVAL_ATTR`
- `[otel].timestamp_unit` -> `EVALFORGE_OTEL_TIMESTAMP_UNIT`
- `[otel].match_dataset_by_input` -> `EVALFORGE_OTEL_MATCH_INPUT`

---

## 7. Python SDK Cookbooks

### 7.1 Direct OTel Replay Inside `EvaluationOrchestrator`

```python
from evalforge_maestro import (
    ArgumentCorrectnessMetric,
    DatasetEngine,
    EvaluationOrchestrator,
    OtelExtractorConfig,
    PrecisionAtKMetric,
    ReplayAdapter,
    ToolSelectionMetric,
    exact_match,
)

dataset = DatasetEngine("dataset.jsonl")
adapter = ReplayAdapter.from_otel_file(
    "traces/otel.json",
    extractors=OtelExtractorConfig(
        case_id_attribute="evalforge.case_id",
        match_dataset_by_input=True,
    ),
    dataset=dataset,
    system_version="agent-v2.4.0",
)

run = EvaluationOrchestrator().run(
    dataset,
    adapter,
    [
        exact_match,
        PrecisionAtKMetric(k=1),
        ToolSelectionMetric(),
        ArgumentCorrectnessMetric(),
    ],
)
print(run.aggregates["tool_selection"].mean_score)
```

### 7.2 Custom Attribute Extractors & Explicit `case_id_map`

```python
from evalforge_maestro import (
    OtelExtractorConfig,
    OtelTimestampUnit,
    load_otel_executions,
)

executions = load_otel_executions(
    "traces/interleaved_spans.jsonl",
    extractors=OtelExtractorConfig(
        input_attribute="app.custom.in",
        output_attribute="app.custom.out",
        retrieval_documents_attribute="app.custom.docs",
        timestamp_unit=OtelTimestampUnit.US,
    ),
    case_id_map={
        "trace-a": "c-alpha",
        "trace-b": "c-beta",
    },
    model_id="glm-5.3",
)
```

### 7.3 Evaluating Live Pytest `InMemorySpanExporter` Spans Without JSON Export

```python
from evalforge_maestro import ingest_otel_spans

# spans = in_memory_exporter.get_finished_spans()
executions = ingest_otel_spans(
    spans,
    case_id_map={"0102030405060708090a0b0c0d0e0f10": "case-inv-1"},
)
```
