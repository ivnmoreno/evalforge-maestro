# Feature Specification: OpenTelemetry Execution Trace Ingestion

**Feature Branch**: `008-otel-trace-ingestion`

**Created**: 2026-11-21

**Status**: Draft

**Input**: Post-M6 Capability 2 (`docs/future-features.md`) — OpenTelemetry Execution Trace Ingestion: normalized span/event importers mapping OTel LLM/tool spans into canonical `ExecutionResult.trace` and `tool_calls` records without coupling core orchestration to an OTel backend.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Normalize OpenTelemetry Spans into Canonical Execution Traces (Priority: P1)

As an AI/agent engineer whose runtime application already emits OpenTelemetry spans (following OTel GenAI Semantic Conventions, OpenInference/Traceloop conventions, or custom span attributes), I want to convert a trace's spans into a canonical `ExecutionResult` containing ordered `AgentTraceStep` steps, `ToolCallRecord` invocations, `RetrievedChunk` context, `TokenUsage`, latency, and error flags so all existing deterministic agent, retrieval, and answer metrics can evaluate production or staging traces without rewriting my application.

**Why this priority**: Production LLM and agent systems routinely export OTel telemetry rather than custom eval schemas. Mapping those spans directly into `ExecutionResult` immediately unlocks M6 process/outcome decoupling, tool checks, retrieval checks, and Quality Gates on real telemetry without coupling core evaluation to an OTel runtime.

**Independent Test**: Pass synthetic grouped OTel span payloads covering LLM calls, tool invocations (successful, failed with error status/arguments, timed out/blocked), retrieval spans, token usage attributes, and nested parent-child spans; verify deterministic step ordering, `ToolCallRecord` argument parsing, token summation, secret scrubbing, and downstream evaluation with built-in agent and retrieval metrics.

**Acceptance Scenarios**:

1. **Given** a trace containing root/chain, LLM generation, retrieval, and tool execution spans with timestamps, attributes, and span events, **When** ingested into an `ExecutionResult`, **Then** steps are deterministically ordered chronologically (with hierarchy/span-ID tie-breaking), tool calls map into `ToolCallRecord` (`id`, `name`, JSON-decoded `arguments`, `raw_arguments`, `argument_parse_error`, `result`, `status`, `error`, `step_index`, `elapsed_seconds`), retrieval spans/events map into `RetrievedChunk`, and final output, model identifier, service version, latency, and `TokenUsage` populate accurately.
2. **Given** malformed tool arguments, span error status/exceptions, or spans containing embedded API keys, bearer tokens, or secret attribute keys (`api_key`, `authorization`, `token`), **When** span normalization runs, **Then** malformed JSON arguments record explicit `argument_parse_error` without crashing normalization, span errors map to error steps/statuses and `ExecutionResult.errors`, and secrets/credentials are masked or scrubbed before returning canonical records.
3. **Given** a Python environment lacking third-party OpenTelemetry SDK packages installed, **When** ingesting JSON/OTLP span dictionaries or importing the package, **Then** core ingestion works without requiring an external OTel backend or SDK runtime and keeps cold-start imports free of heavy optional dependencies.

---

### User Story 2 - Multi-Format OTel Export Loading & Dataset Case Correlation (Priority: P1)

As an evaluation engineer working with trace exports from collectors, CI runs, or observability dumps, I want to load standard OTLP trace JSON files (`resourceSpans` / `scopeSpans` / `spans`), flat JSON span arrays, or newline-delimited JSONL span streams and correlate multi-span traces cleanly to `EvaluationCase.id` values without silent mismatches or overwrites.

**Why this priority**: Real exporters emit OTLP JSON envelopes or flat span lists where spans belonging to multiple traces/cases are interleaved. Reliable grouping by trace ID, multi-convention attribute decoding (both OTLP key/value typed attribute arrays and plain key-value maps), and unambiguous case correlation are essential for trustworthy offline replay.

**Independent Test**: Load OTLP `ExportTraceServiceRequest` JSON files, flat span arrays, and interleaved JSONL span files containing multiple `trace_id` groups and test correlation via explicit trace-level case ID attributes, custom configured attribute paths, explicit trace-to-case ID mappings, normalized prompt-input fallback matching against a dataset, and rejection of duplicate or uncorrelatable traces.

**Acceptance Scenarios**:

1. **Given** an OTLP JSON export (with `resourceSpans`, `scopeSpans`, nanosecond timestamps, and typed `{"key": ..., "value": {"stringValue" | "intValue" | "doubleValue" | "boolValue" | "arrayValue" | "kvlistValue"}}` attributes), a flat span JSON array, or an interleaved JSONL span file, **When** loaded through the trace importer, **Then** spans are grouped deterministically per `trace_id`, timestamps convert accurately to seconds, and each trace yields one validated canonical `ExecutionResult`.
2. **Given** configurable correlation options (`case_id_attribute`, explicit `trace_id -> case_id` lookup map, or optional dataset prompt-matching fallback), **When** traces are matched against an evaluation dataset, **Then** explicit attributes and mappings resolve `case_id` deterministically, optional input matching works unambiguously on unique prompts, and ambiguous or duplicate `case_id` mappings fail explicitly with a clear configuration/dataset error.
3. **Given** two runs whose traces use custom vendor span attribute names (e.g., custom `app.prompt`, `app.answer`, `app.tool_name`, `app.docs`), **When** configured via typed extractor rules, **Then** custom attributes take precedence cleanly alongside standard GenAI (`gen_ai.*`) and OpenInference/Traceloop conventions.

---

### User Story 3 - Offline OTel Replay Evaluation & CLI Export Workflow (Priority: P2)

As a CI or platform operator, I want to evaluate an OpenTelemetry trace export directly via the CLI (`run --otel-traces <path>`) or convert raw trace exports into canonical replay files (`ingest-otel`) under standard configuration precedence, security redaction, truncation, and exit codes so OTel-instrumented agents and RAG pipelines participate seamlessly in `compare`, `--repeats`, `trend`, and Quality Gates.

**Why this priority**: First-class CLI integration lets teams drop existing collector or CI trace exports directly into `evalforge-maestro` gates and inspect Three-Way Markdown/JSON diagnostics without writing bespoke glue scripts.

**Independent Test**: Execute CLI `ingest-otel` and `run --otel-traces ... --dataset ...` end-to-end on OTLP and JSONL trace fixtures paired with agent/RAG evaluation metrics, verifying canonical JSON/Markdown reports, secret scrubbing on `stdout`/`stderr`, deterministic repeat gating, conflicting-flag validation (exit code `2`), and zero regressions in existing `evalforge-maestro` workflows.

**Acceptance Scenarios**:

1. **Given** a dataset JSONL file and an OTel trace export (OTLP JSON or JSONL), **When** running `evalforge-maestro run --dataset <ds> --otel-traces <traces> --metric tool_selection --metric policy_compliance --json`, **Then** the evaluator ingests the OTel spans offline via replay semantics, scores agent/retrieval/answer metrics independently, persists an immutable `RunRecord` with redacted trace metadata, and enforces POSIX exit codes (`0`–`4`).
2. **Given** a raw OTel export file, **When** invoking `evalforge-maestro ingest-otel <traces> --json` or `--output <executions.jsonl>`, **Then** canonical secret-scrubbed `ExecutionResult` records are emitted ready for subsequent `--executions` replay or inspection.
3. **Given** conflicting execution flags (`--otel-traces` paired with `--executions` or `--target`), unreadable/malformed OTel exports, or unaligned case IDs vs the active dataset, **When** CLI validation runs, **Then** it fails fast with an explicit error payload and exit code `2` without mutating run storage.

---

### Edge Cases

- What happens when an OTLP attribute uses typed wrappers (`stringValue`, `intValue`, `doubleValue`, `boolValue`, `arrayValue`, `kvlistValue`) or nested JSON strings inside string attributes? The importer unwraps OTLP typed `AnyValue` structures recursively and decodes JSON-stringified tool argument/result payloads safely without failing on non-JSON plain strings.
- What happens when parent spans are missing or child spans lack `parent_span_id` (orphan spans or partial trace exports)? Orphan spans within a `trace_id` are still ordered deterministically by timestamp (`start_time`, then depth/span ID) and preserved cleanly without crashing or dropping child tool/LLM evidence.
- What happens when multiple `LLM_RESPONSE` or nested helper spans appear inside a single multi-step trace? Token counts (`TokenUsage`) sum across unique/leaf generation spans without crashing when partial spans omit usage fields, and final answer selection prefers the root span output attribute or last non-empty `FINAL_OUTPUT`/`LLM_RESPONSE` step.
- What happens when nanosecond, microsecond, millisecond, or ISO-8601 string timestamps appear on spans? Duration calculation normalizes numeric epoch nanoseconds (`>= 1e14`), microseconds, milliseconds, or ISO-8601 UTC strings consistently and clamps negative clock skew safely to `0.0` elapsed seconds (recording a warning flag when clock skew occurs).
- What happens when imported traces contain secrets (`sk-...`, Bearer tokens, email/credential metadata) or oversized trace payloads under `--max-context-chars`? All imported attributes/tool arguments/errors are credential-scrubbed on ingestion, PII egress checks work when `--block-pii` applies downstream, and `--max-context-chars` post-scoring truncation bounds persisted artifacts cleanly without mutating live scoring.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide dependency-free OpenTelemetry span ingestion supporting standard OTLP `ExportTraceServiceRequest` JSON envelopes (`resourceSpans`/`scopeSpans`/`spans`, including typed `AnyValue` attributes and span `events`), flat span JSON arrays, and newline-delimited JSONL span files (as well as in-memory duck-typed span sequences) without adding mandatory third-party OTel dependencies or affecting core cold-start imports (`sys.modules` remains free of heavy optional packages).
- **FR-002**: Span ingestion MUST deterministically normalize each grouped `trace_id` into one schema-validated canonical `ExecutionResult` in `src/evalforge_maestro/types.py`, preserving chronological ordering (`start_time`, tree depth/parent link, stable `span_id` tie-breaker) across ordered `AgentTraceStep` records (`TraceStepKind`), `ToolCallRecord` invocations (`ToolCallStatus`, JSON arguments with explicit `raw_arguments` and `argument_parse_error` capture on malformed JSON), `RetrievedChunk` documents, summed/partial `TokenUsage`, `elapsed_seconds`, `model_id`, `system_version`, runtime/span `errors`, and `adapter_metadata`.
- **FR-003**: Attribute extraction MUST support standard OTel GenAI Semantic Conventions (`gen_ai.*`), common community agent/RAG conventions (OpenInference / Traceloop attribute keys and `events`), and explicit configurable attribute overrides defined via a strict typed extractor/ingestion configuration model in `src/evalforge_maestro/types.py`.
- **FR-004**: Case correlation MUST deterministically resolve each imported trace to `EvaluationCase.id` using clear precedence: explicit `case_id_map` override, trace/span attribute (`evalforge.case_id` or configured `case_id_attribute`), and (only when explicitly enabled alongside a dataset) unambiguous prompt-input matching; duplicate `case_id` collisions or missing/ambiguous correlations MUST raise explicit validation errors rather than silently overwriting or guessing.
- **FR-005**: System MUST scrub/redact sensitive credential keys and tokens across imported span attributes, events, tool arguments/results, errors, and `adapter_metadata` at ingestion time, and MUST preserve compatibility with post-scoring `--max-context-chars` truncation and immutable `.evalforge/` canonical run persistence.
- **FR-006**: System MUST expose clean library entrypoints (structured ingestion helpers plus `ReplayAdapter.from_otel_file` / top-level exports pinned in stability contracts) adhering to Constitution Principle II (no `cli`, config-file, or network-server leakage into core/metrics/regression modules).
- **FR-007**: System MUST extend CLI workflows cleanly with `--otel-traces <path>` (plus corresponding `[run].otel_traces` / `EVALFORGE_OTEL_TRACES` and `[otel]` extractor/correlation settings under standard 5-tier config precedence) on `run`, and a dedicated `ingest-otel` subcommand exporting schema-validated canonical `ExecutionResult` records (`--json` JSON array on `stdout` or `--output` JSONL/JSON file), enforcing POSIX exit code `2` on invalid/conflicting arguments, malformed traces, or unaligned case IDs while preserving full backward compatibility on all existing M1–M7 APIs and CLI subcommands.

### Key Entities

- **OTel Trace Extractor / Ingestion Configuration**: Typed configuration specifying case-ID correlation attribute name(s), optional input-matching fallback policy, service/model/step/tool/retrieval attribute override paths, and timestamp unit hints.
- **Raw OTel Span / Resource Context**: Normalized intermediate representation extracted from OTLP JSON, flat span JSON/JSONL, or duck-typed runtime span objects carrying `trace_id`, `span_id`, `parent_span_id`, `name`, `start_time`, `end_time`, decoded `attributes`, `events`, `status`, and resource metadata (`service.version`).
- **Correlated Trace Bundle / ExecutionRecord**: Canonical `ExecutionResult` emitted per resolved `trace_id` with full process/retrieval/outcome fidelity ready for offline evaluation, replay storage, and reporting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ingesting OTLP JSON, flat span JSON, JSONL span streams, and custom-attributed multi-span agent/RAG traces converts 100% of test trace suites accurately into `ExecutionResult` payloads accepted by all existing M1–M7 retrieval, deterministic, agent, judge, and embedding metrics without schema errors.
- **SC-002**: Re-ingesting identical OTel trace exports produces byte-identical canonical `ExecutionResult` JSON payloads (`gate_determinism`) and deterministic `RunRecord` fingerprints across repeated CLI runs.
- **SC-003**: Cold-start subprocess verification (`import evalforge_maestro` and `evalforge-maestro --help`) keeps optional dependencies untouched, secret redaction strips 100% of injected bearer tokens / `api_key` attributes during OTel ingestion, and global branch coverage remains `>= 85%` (with `100%` branch coverage preserved on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`).
- **SC-004**: Zero breaking changes occur across all pinned M1–M7 APIs, CLI flags, exit codes (`0`–`4`), and contract tests.

## Assumptions

- OpenTelemetry execution trace ingestion operates over exported telemetry artifacts (OTLP JSON files/payloads, JSON span arrays, JSONL span streams) and optional caller-passed in-memory span sequences; hosting an always-on OTLP gRPC/HTTP collector daemon is out of scope for Feature `008`.
- Nanosecond integer timestamps (stringified or numeric 64-bit ints, as emitted in OTLP JSON `startTimeUnixNano`/`endTimeUnixNano`) are treated as canonical OTLP epoch nanoseconds when `>= 1e14`, while smaller explicit Unix epoch timestamps or ISO-8601 strings normalize safely to duration seconds.
- Any case present in the selected evaluation dataset that is missing from the correlated OTel trace export fails alignment cleanly unless the caller filters the dataset (consistent with `ReplayAdapter` contract behavior).
