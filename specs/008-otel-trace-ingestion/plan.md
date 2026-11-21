# Implementation Plan: OpenTelemetry Execution Trace Ingestion

**Branch**: `008-otel-trace-ingestion` | **Date**: 2026-11-21 | **Spec**: [`spec.md`](spec.md)

## Summary

Implement dependency-free OpenTelemetry span ingestion mapping OTLP JSON (`ExportTraceServiceRequest`), flat JSON span arrays, JSONL span streams, and duck-typed runtime span objects into canonical `ExecutionResult` payloads (`trace`, `tool_calls`, `retrieved_chunks`, `tokens`, `elapsed_seconds`, `errors`, `system_version`, `model_id`, and secret-redacted `adapter_metadata`) under a new typed `OtelExtractorConfig` contract, integrated with `ReplayAdapter.from_otel_file`, `run --otel-traces`, and `ingest-otel` CLI workflows.

## Technical Context

**Language/Version**: Python 3.10+ (tested on 3.10–3.13)  
**Primary Dependencies**: Core package (`pydantic>=2.7` + stdlib `json`, `datetime`, `pathlib`, `collections`); zero new core or optional dependencies required for OTel trace parsing  
**Storage**: Reads OTLP JSON / span JSON / JSONL artifacts; persists immutable canonical `RunRecord` / `manifest.jsonl` under `.evalforge/`  
**Testing**: `pytest --strict-markers -W error`, `--cov-branch --cov-fail-under=85` (100% preserved on `metrics/` and `regression/gate.py`), `mypy --strict src tests`, `ruff format/check` + Bandit `S`  
**Target Platform**: Linux / macOS / Windows CLI and Python SDK  
**Project Type**: Standalone Python evaluation library + CLI (`src/evalforge_maestro/`)  
**Constraints**: Zero heavy OTel SDK dependencies in core; cold-start `sys.modules` purity (`tests/test_library_purity.py`); unidirectional import layering (`types` <- `adapters` <- `cli`); mandatory credential/secret scrubbing at ingestion time  

## Constitution Check

*GATE: Checked before Phase 0 research and re-checked post Phase 1 design.*

- **I. One-Sentence Scope Tiebreaker**: PASS — `evalforge_maestro` strictly ingests pre-recorded exported spans (or caller-passed span objects) for offline evaluation and never hosts an OTel collector daemon or agent runtime.
- **II. Library Purity & Unidirectional Dependencies**: PASS — `OtelExtractorConfig`/`OtelTimestampUnit` live in `types.py`; OTel normalization/loading lives solely inside `adapters/otel.py` and `adapters/replay.py` (never imported by `metrics`, `judges`, `regression`, or `datasets`); `adapters/` never imports `cli`, `tomllib`, or `.env`.
- **III. Single Schema Source of Truth**: PASS — `OtelTimestampUnit`, `OtelExtractorConfig`, and additive `CLIResolvedConfig` fields reside strictly in `src/evalforge_maestro/types.py`. Existing `ExecutionResult`, `AgentTraceStep`, `ToolCallRecord`, `TokenUsage`, and `RunRecord` schemas remain backward compatible without structural churn.
- **IV. Evidence-Aware & Anomaly-Safe Evaluation**: PASS — Parsed OTel traces preserve process steps (`trace`), tool invocations (`tool_calls`), retrieval chunks (`retrieved_chunks`), errors, and final outputs separately so M6 agent metrics, M2 IR metrics, decoupled diagnostics, and anti-masking anomalies operate natively.
- **V. Immutable Artifacts & Determinism**: PASS — Span ordering (`(start_time, depth, span_id, index)`), timestamp normalization, and tool-call deduplication are strictly deterministic, producing identical `ExecutionResult` and `RunRecord` hashes across re-runs.
- **VI. Stream & Secret Hygiene**: PASS — Span attributes, tool payloads, events, errors, and resource metadata are scrubbed through `_trace_norm` + `_canonical` redactors before returning or printing (`--json` clean on `stdout`, diagnostics on `stderr`).
- **VII. Automated Quality Gates**: PASS — Contracts pinned in `tests/test_api_stability.py` and `tests/contract/test_m8_schemas.py`; `gate_determinism` covered on re-ingested OTLP payloads.

## Project Structure

### Documentation (`specs/008-otel-trace-ingestion/`)

```text
specs/008-otel-trace-ingestion/
├── spec.md              # Functional & non-functional requirements (FR-001..FR-007)
├── checklists/
│   └── requirements.md  # Spec completeness validation (all checked)
├── plan.md              # This file
├── research.md          # Phase 0 architectural decisions
├── data-model.md        # OtelTimestampUnit, OtelExtractorConfig, mapping specification
├── contracts/
│   └── otel-ingestion-and-cli.md
└── quickstart.md        # End-to-end verification scenarios
```

### Source Code & Test Extensions

```text
src/evalforge_maestro/
├── types.py                         # Add OtelTimestampUnit, OtelExtractorConfig, CLIResolvedConfig.{otel_traces,otel}
├── __init__.py                      # Export OtelTimestampUnit, OtelExtractorConfig, ingest_otel_spans, load_otel_executions
├── adapters/
│   ├── __init__.py                  # Export ingest_otel_spans, load_otel_executions
│   ├── otel.py                      # New pure OTel OTLP/JSON/JSONL/duck-span normalizer & correlator
│   └── replay.py                    # Add ReplayAdapter.from_otel_file(...)
└── cli/
    ├── config.py                    # Add _TomlRunSection.otel_traces, _TomlOtelSection, EVALFORGE_OTEL_* precedence
    ├── parser.py                    # Add --otel-* flags on run & new `ingest-otel` subcommand
    ├── targets.py                   # Resolve ReplayAdapter.from_otel_file when resolved.otel_traces is set
    └── commands.py                  # Add _handle_ingest_otel handler & update _args_to_cli_overrides

tests/
├── contract/
│   ├── test_m5_schemas.py           # Project additive CLIResolvedConfig M8 fields for frozen M5 parity
│   ├── test_m6_schemas.py           # Project additive CLIResolvedConfig M8 fields for frozen M6 parity
│   └── test_m8_schemas.py           # Strict Draft 2020-12 / Pydantic parity checks for OTel contracts
├── unit/
│   ├── test_otel_ingestion.py       # Span ordering, OTLP AnyValue, GenAI/OpenInference/custom extractors, dedup, tokens, skew, redaction
│   └── test_cli_config.py           # [otel] TOML, EVALFORGE_OTEL_*, unknown-key validation
├── integration/
│   └── test_otel_pipeline.py        # CLI `ingest-otel`, `run --otel-traces` with agent+RAG metrics & gate_determinism
├── test_library_purity.py           # Verify AST boundaries on adapters/otel.py & zero opentelemetry import on --help
└── test_api_stability.py            # Pin new exports, signatures, and schema fields
```

## Complexity Tracking

No Constitution violations cleanly exist or require exceptions.
