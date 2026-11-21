# Contract Specification: OTel Trace Ingestion SDK, Adapter & CLI

**Feature**: `008-otel-trace-ingestion`  
**Contract Scope**: Library entrypoints (`evalforge_maestro.adapters`, `evalforge_maestro`), CLI subcommands (`run`, `ingest-otel`), TOML `[otel]` & `EVALFORGE_OTEL_*`, POSIX exit codes (`0`–`4`).

## 1. Python Library & Adapter Contracts

### Public Functions & Class Extensions
Exported from `evalforge_maestro.adapters` and top-level `evalforge_maestro` (`__all__`):
- `OtelTimestampUnit` (enum)
- `OtelExtractorConfig` (Pydantic model)
- `ingest_otel_spans(payload: Any, *, extractors: OtelExtractorConfig | None = None, dataset: DatasetEngine | Sequence[EvaluationCase] | None = None, case_id_map: Mapping[str, str] | None = None, system_version: str | None = None, model_id: str | None = None) -> list[ExecutionResult]`
  - Accepts parsed OTLP `ExportTraceServiceRequest` dict, flat span sequence/dicts, or duck-typed in-memory OTel span objects.
  - Pure library function (zero `cli`/`tomllib`/env file reads). Raises `AdapterError` on malformed inputs, missing/ambiguous/duplicate `case_id`, or invalid span fields.
- `load_otel_executions(path: Path | str, *, extractors: OtelExtractorConfig | None = None, dataset: DatasetEngine | Sequence[EvaluationCase] | None = None, case_id_map: Mapping[str, str] | None = None, system_version: str | None = None, model_id: str | None = None) -> list[ExecutionResult]`
  - Reads OTLP JSON file, flat span JSON array file, or JSONL span lines file. Raises `DatasetError` on missing/unreadable/malformed file or uncorrelatable traces.
- `ReplayAdapter.from_otel_file(path: Path | str, *, extractors: OtelExtractorConfig | None = None, dataset: DatasetEngine | Sequence[EvaluationCase] | None = None, case_id_map: Mapping[str, str] | None = None, system_version: str | None = None, model_id: str | None = None, config_fingerprint: str | None = None) -> ReplayAdapter`
  - Returns an initialized offline `ReplayAdapter` populated with sanitized, secret-scrubbed canonical `ExecutionResult` objects and derived SHA-256 `config_fingerprint` incorporating redacted extractor config + trace metadata.

### Library Purity & Boundary Rules
- `evalforge_maestro.types`: defines `OtelTimestampUnit`, `OtelExtractorConfig`, and `CLIResolvedConfig.{otel_traces, otel}` only; zero imports from `adapters`, `cli`, or third-party OTel packages.
- `evalforge_maestro.adapters.otel`: zero imports from `cli`, `tomllib`, `dotenv`, `requests`, `fastapi`, or heavy optional extras.
- Cold-start imports (`import evalforge_maestro`, `evalforge-maestro --help`) must keep `opentelemetry`, `litellm`, `docpipe_maestro`, `numpy`, and `scipy` absent from `sys.modules`.

---

## 2. CLI Surface Contracts

### 2.1 `evalforge-maestro run` Extensions
New flags (following `CLI > EVALFORGE_* > --env-file > evalforge.toml > defaults`):
- `--otel-traces PATH` (`EVALFORGE_OTEL_TRACES`, `[run].otel_traces`): Evaluate dataset against offline OTel span export (incompatible with `--executions` or `--target` / live target type; conflict fails with exit code `2`).
- `--otel-case-id-attr ATTR` (`EVALFORGE_OTEL_CASE_ID_ATTR`, `[otel].case_id_attribute`)
- `--otel-input-attr ATTR` (`EVALFORGE_OTEL_INPUT_ATTR`, `[otel].input_attribute`)
- `--otel-output-attr ATTR` (`EVALFORGE_OTEL_OUTPUT_ATTR`, `[otel].output_attribute`)
- `--otel-model-attr ATTR` (`EVALFORGE_OTEL_MODEL_ATTR`, `[otel].model_attribute`)
- `--otel-tool-name-attr ATTR` (`EVALFORGE_OTEL_TOOL_NAME_ATTR`, `[otel].tool_name_attribute`)
- `--otel-tool-args-attr ATTR` (`EVALFORGE_OTEL_TOOL_ARGS_ATTR`, `[otel].tool_arguments_attribute`)
- `--otel-tool-result-attr ATTR` (`EVALFORGE_OTEL_TOOL_RESULT_ATTR`, `[otel].tool_result_attribute`)
- `--otel-retrieval-attr ATTR` (`EVALFORGE_OTEL_RETRIEVAL_ATTR`, `[otel].retrieval_documents_attribute`)
- `--otel-timestamp-unit {auto,ns,us,ms,s}` (`EVALFORGE_OTEL_TIMESTAMP_UNIT`, `[otel].timestamp_unit`)
- `--otel-match-input` (`EVALFORGE_OTEL_MATCH_INPUT`, `[otel].match_dataset_by_input`)

Also supports optional `--target-type otel`? Keep `TargetType` untouched (`REPLAY` handles both `--executions` and `--otel-traces` cleanly without altering `TargetType` enum assumptions in prior M5 tests — or resolve `effective_type = TargetType.REPLAY` when `resolved.otel_traces is not None`, raising `ConfigurationError` if combined with `--executions` or live targets).

### 2.2 New Subcommand: `evalforge-maestro ingest-otel`
```text
evalforge-maestro ingest-otel <OTEL_PATH>
  [--dataset PATH]
  [--output PATH]
  [--system-version STR]
  [--model-id STR]
  [--otel-case-id-attr ATTR]
  [--otel-input-attr ATTR]
  [--otel-output-attr ATTR]
  [--otel-match-input]
  [--otel-timestamp-unit {auto,ns,us,ms,s}]
  [--json] [--quiet]
```
Behavior:
- Ingests `<OTEL_PATH>` via `load_otel_executions(...)` (paired with `DatasetEngine` when `--dataset` is provided).
- If `--output <PATH>` is provided: writes schema-validated `.json` array when filename ends in `.json`, otherwise writes `.jsonl` (one canonical JSON `ExecutionResult` per line) ready for `run --executions <PATH>`.
- `--json`: writes canonical secret-scrubbed JSON array of `ExecutionResult` objects to `stdout` (`indent=None` canonical serialization).
- Non-`--json` default: writes concise Markdown/text ingestion summary (`count`, `case_ids`, token/tool/error summary) to `stdout` (suppressed with `--quiet`).
- Exit codes:
  - `0`: Ingestion & optional export succeeded.
  - `2`: Missing/unreadable OTel file, malformed JSON/JSONL, correlation failure, or config validation error.

### 2.3 TOML Schema Additions (`evalforge.toml`)
```toml
[run]
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
timestamp_unit = "auto"
match_dataset_by_input = false
```
