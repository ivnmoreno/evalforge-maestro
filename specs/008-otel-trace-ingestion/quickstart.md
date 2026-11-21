# Quickstart Validation Guide: OpenTelemetry Execution Trace Ingestion

**Feature**: `008-otel-trace-ingestion`  
**References**: [`spec.md`](spec.md) | [`data-model.md`](data-model.md) | [`contracts/otel-ingestion-and-cli.md`](contracts/otel-ingestion-and-cli.md)

## Scenario 1 — Convert an OTLP JSON Export via `ingest-otel`

```bash
evalforge-maestro ingest-otel path/to/otlp-traces.json \
  --dataset path/to/eval-dataset.jsonl \
  --output executions-from-otel.jsonl \
  --json
```

**Expected**:
- Unwraps OTLP `resourceSpans` / `scopeSpans` / `spans` and typed `AnyValue` attributes without needing `opentelemetry-sdk` installed.
- Emits secret-scrubbed canonical `ExecutionResult` records on `stdout` (`--json`) and writes replay-ready JSONL to `executions-from-otel.jsonl`.
- Fails with exit code `2` cleanly on unreadable files or duplicate/missing case correlations.

## Scenario 2 — Evaluate Directly via `run --otel-traces` with Agent & RAG Metrics

```bash
evalforge-maestro run \
  --dataset path/to/eval-dataset.jsonl \
  --otel-traces path/to/otlp-traces.json \
  --metric exact_match \
  --metric tool_selection \
  --metric argument_correctness \
  --metric policy_compliance \
  --metric precision_at_k:k=3 \
  --strict \
  --json
```

**Expected**:
- Loads OTel spans offline via `ReplayAdapter.from_otel_file` and validates dataset alignment.
- Evaluates deterministic agent trace metrics, retrieval metrics, and decoupled diagnostics independently from answer text.
- Persists immutable `RunRecord` artifacts under `.evalforge/` and enforces deterministic POSIX exit codes (`0`–`4`).

## Scenario 3 — Custom Attribute Conventions & Prompt-Input Fallback Matching

```bash
evalforge-maestro run \
  --dataset path/to/eval-dataset.jsonl \
  --otel-traces path/to/custom-spans.jsonl \
  --otel-case-id-attr app.eval.case \
  --otel-tool-name-attr custom.tool.id \
  --otel-match-input \
  --otel-timestamp-unit us \
  --metric tool_efficiency \
  --json
```

**Expected**:
- Decodes microsecond spans, extracts custom tool/case attributes cleanly, and unambiguously matches unlabeled single traces by normalized prompt text.
