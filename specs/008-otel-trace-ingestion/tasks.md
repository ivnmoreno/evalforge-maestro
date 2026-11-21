# Tasks: OpenTelemetry Execution Trace Ingestion

**Input**: Design documents from `/specs/008-otel-trace-ingestion/`  
**Prerequisites**: [`plan.md`](plan.md), [`spec.md`](spec.md), [`research.md`](research.md), [`data-model.md`](data-model.md), [`contracts/otel-ingestion-and-cli.md`](contracts/otel-ingestion-and-cli.md)

**Tests**: Included across all user stories — contract, unit, integration, AST purity, and determinism tests MUST be authored first and observed failing before implementing production modules.

**Organization**: Grouped into Setup, Foundational Schemas & Purity, User Story 1 (P1 MVP — Span Normalization), User Story 2 (P1 — Multi-Format OTLP/JSON/JSONL & Case Correlation), User Story 3 (P2 — CLI `run --otel-traces` & `ingest-otel` + SDK Exports), and Polish & CI Verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can execute in parallel (different files, no unresolved dependencies)
- **[Story]**: `US1`, `US2`, or `US3`

---

## Phase 1: Setup & Contract Baseline

**Purpose**: Initialize test scaffolding and verify clean core purity baselines before editing schemas or adapters.

- [X] T001 Create test file skeletons / imports and update `_HEAVY_OPTIONAL_MODULES` (`opentelemetry`) in `tests/test_library_purity.py` to assert cold-start purity and unidirectional `adapters/otel.py` boundaries per [contracts/otel-ingestion-and-cli.md](contracts/otel-ingestion-and-cli.md)
- [X] T002 [P] Define Pydantic schema and Draft 2020-12 contract test suite skeleton for `OtelTimestampUnit` and `OtelExtractorConfig` in `tests/contract/test_m8_schemas.py`

---

## Phase 2: Foundational Canonical Schemas & Compatibility

**Purpose**: Establish single-source Pydantic v2 models in `src/evalforge_maestro/types.py` required by all stories (`MUST` complete before US1–US3 implementation).

- [X] T003 Define `OtelTimestampUnit` (`AUTO`, `NS`, `US`, `MS`, `S`), `OtelExtractorConfig` (`OtelExtractorConfig.case_id_attribute`, `OtelExtractorConfig.input_attribute`, `OtelExtractorConfig.output_attribute`, `OtelExtractorConfig.model_attribute`, `OtelExtractorConfig.service_version_attribute`, `OtelExtractorConfig.step_kind_attribute`, `OtelExtractorConfig.tool_name_attribute`, `OtelExtractorConfig.tool_arguments_attribute`, `OtelExtractorConfig.tool_result_attribute`, `OtelExtractorConfig.retrieval_documents_attribute`, `OtelExtractorConfig.timestamp_unit`, `OtelExtractorConfig.match_dataset_by_input`), plus `CLIResolvedConfig.otel_traces` and `CLIResolvedConfig.otel` in `src/evalforge_maestro/types.py` per [data-model.md](data-model.md)
- [X] T004 [P] Project additive `CLIResolvedConfig.{otel_traces, otel}` fields cleanly in frozen historical parity tests `tests/contract/test_m5_schemas.py` and `tests/contract/test_m6_schemas.py` while validating strict Feature `008` models in `tests/contract/test_m8_schemas.py` (depends on T003)

**Checkpoint**: Canonical `OtelTimestampUnit`, `OtelExtractorConfig`, and `CLIResolvedConfig` fields validate cleanly with zero M1–M7 regressions.

---

## Phase 3: User Story 1 — Normalize OpenTelemetry Spans into Canonical Execution Traces (Priority: P1 🎯 MVP)

**Goal**: Convert grouped spans from a single OTel trace (OTLP dicts, flat dicts, or duck-typed runtime span objects) into a canonical, secret-scrubbed `ExecutionResult` containing ordered `AgentTraceStep`, deduplicated `ToolCallRecord`, `RetrievedChunk`, summed `TokenUsage`, `elapsed_seconds` (clock-skew guarded), `model_id`, `system_version`, and span/exception `errors`.

**Independent Test**: Run `uv run pytest tests/unit/test_otel_ingestion.py -k us1` verifying span attribute decoding, chronological/hierarchical ordering, tool-call merging, malformed JSON tool arguments (`argument_parse_error`), retrieval extraction, token usage aggregation, negative clock skew warnings, and secret redaction across nested attributes and events.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [P] [US1] Write US1 unit tests in `tests/unit/test_otel_ingestion.py` covering OTLP `AnyValue` decoding, GenAI (`gen_ai.*`), OpenInference (`openinference.span.kind`, `llm.*`), Traceloop, duck-typed Python `ReadableSpan`-style objects, chronological + parent-depth ordering, orphan spans, LLM+tool span call deduplication, malformed JSON tool args (`raw_arguments` + `argument_parse_error`), retrieval chunk extraction (`RetrievedChunk`), clock skew clamping (`0.0` + warning), `TokenUsage` non-double-counting summation, error/exception spans, and credential/bearer-token redaction

### Implementation for User Story 1

- [X] T006 [US1] Implement OTLP `AnyValue` & timestamp unwrapper, duck-typed span reader (`_RawOtelSpan`), attribute lookup precedence, span classification (`TraceStepKind`), tool-call merging/deduplication (`ToolCallRecord`), retrieval chunk extraction (`RetrievedChunk`), token aggregation (`TokenUsage`), clock-skew handling, and secret scrubbing in `src/evalforge_maestro/adapters/otel.py` (depends on T003, T005)
- [X] T007 [US1] Add deterministic trace-to-`ExecutionResult` assembler (`_spans_to_execution_result`) inside `src/evalforge_maestro/adapters/otel.py` preserving `adapter_metadata["otel"]` provenance and passing existing `_trace_norm` redactors (depends on T006)

**Checkpoint**: User Story 1 (`ingest_otel_spans` for single-trace OTel span normalization) passes all unit and redaction tests independently (**MVP complete**).

---

## Phase 4: User Story 2 — Multi-Format OTel Export Loading & Dataset Case Correlation (Priority: P1)

**Goal**: Parse multi-trace OTLP `ExportTraceServiceRequest` files/dicts, flat span JSON arrays, and interleaved JSONL span files; group spans deterministically by `trace_id`; correlate every trace to `EvaluationCase.id` cleanly (`case_id_map`, custom/built-in attributes, or opt-in `match_dataset_by_input`); and integrate into `ReplayAdapter.from_otel_file`.

**Independent Test**: Run `uv run pytest tests/unit/test_otel_ingestion.py -k us2` covering multi-format file ingestion (OTLP JSON, span array JSON, JSONL spans), unambiguous `case_id` resolution, custom `OtelExtractorConfig` paths, explicit rejection (`AdapterError` / `DatasetError`) on missing, ambiguous, or duplicate `case_id`s, and `ReplayAdapter.from_otel_file`.

### Tests for User Story 2 ⚠️

- [X] T008 [P] [US2] Write US2 unit tests in `tests/unit/test_otel_ingestion.py` covering `load_otel_executions` across OTLP JSON envelopes, flat JSON arrays, and interleaved JSONL spans; multi-trace grouping by `trace_id`; correlation precedence (`case_id_map` > `OtelExtractorConfig.case_id_attribute` > `evalforge.case_id` > opt-in `OtelExtractorConfig.match_dataset_by_input`); explicit failure on missing, duplicate, or ambiguous `case_id`s; custom attribute extractor overrides; and `ReplayAdapter.from_otel_file`

### Implementation for User Story 2

- [X] T009 [US2] Implement multi-format OTel file/payload parser (`_extract_raw_spans`), trace grouping (`_group_spans_by_trace`), unambiguous case-ID correlator (`ingest_otel_spans`, `load_otel_executions`) in `src/evalforge_maestro/adapters/otel.py` (depends on T007, T008)
- [X] T010 [P] [US2] Implement `ReplayAdapter.from_otel_file` (computing deterministic redacted SHA-256 `config_fingerprint` and delegating error translation cleanly to `DatasetError`) in `src/evalforge_maestro/adapters/replay.py` (depends on T009)
- [X] T011 [P] [US2] Export `ingest_otel_spans` and `load_otel_executions` in `src/evalforge_maestro/adapters/__init__.py` (depends on T009)

**Checkpoint**: User Stories 1 and 2 are fully functional offline via Python SDK (`ingest_otel_spans`, `load_otel_executions`, `ReplayAdapter.from_otel_file`).

---

## Phase 5: User Story 3 — Offline OTel Replay Evaluation & CLI Export Workflow (Priority: P2)

**Goal**: Wire `[otel]` / `[run].otel_traces` config precedence, CLI `run --otel-traces`, and CLI `ingest-otel` subcommand across `cli/config.py`, `cli/parser.py`, `cli/targets.py`, `cli/commands.py`, and top-level `evalforge_maestro.__init__.py`, and pin all new APIs in `tests/test_api_stability.py`.

**Independent Test**: Run `uv run pytest --strict-markers -W error tests/unit/test_cli_config.py tests/integration/test_otel_pipeline.py tests/test_api_stability.py tests/test_library_purity.py` verifying 5-tier config precedence, CLI `ingest-otel` (`--json`, `--output` `.jsonl`/`.json`), `run --otel-traces` with agent & retrieval metrics + `--max-context-chars` + `--repeats` + `gate_determinism`, exit code `2` conflict errors, secret masking, cold-start `--help` purity, and API stability.

### Tests for User Story 3 ⚠️

- [X] T012 [P] [US3] Extend `tests/unit/test_cli_config.py` with tests covering `[run].otel_traces`, `[otel]` TOML keys, `EVALFORGE_OTEL_*` env vars, 5-tier precedence (`CLI > ENV > --env-file > TOML > defaults`), unknown-key rejection, and invalid `timestamp_unit` validation
- [X] T013 [P] [US3] Write end-to-end integration tests in `tests/integration/test_otel_pipeline.py` (including `@pytest.mark.gate_determinism`) verifying CLI `ingest-otel` (`.json`/`.jsonl` export, `--json`, `--quiet`, exit code `2` on corrupt/unaligned trace), `run --otel-traces` evaluated against `tool_selection` / `argument_correctness` / `policy_compliance` / `precision_at_k`, conflict rejection with `--executions` / `--target` (exit code `2`), `--max-context-chars` truncation, secret redaction across JSON/Markdown reports, and subprocess `--help` cold-start purity

### Implementation for User Story 3

- [X] T014 [US3] Extend TOML schemas (`_TomlRunSection.otel_traces`, `_TomlOtelSection`) and `EVALFORGE_OTEL_*` resolution into `CLIResolvedConfig.{otel_traces, otel}` in `src/evalforge_maestro/cli/config.py` (depends on T003, T012)
- [X] T015 [P] [US3] Add `--otel-traces` & `--otel-*` flags to `run` and add `ingest-otel` subcommand (`--dataset`, `--output`, `--system-version`, `--model-id`, `--otel-*`, `--json`, `--quiet`) in `src/evalforge_maestro/cli/parser.py` preserving cold-start purity
- [X] T016 [US3] Update `build_target_adapter` (loading `ReplayAdapter.from_otel_file` when `resolved.otel_traces` is set, enforcing mutual exclusion with `--executions`/`--target` and running `_validate_replay_alignment`) and `preflight_run_security` (preserving existing checks cleanly) in `src/evalforge_maestro/cli/targets.py` (depends on T010, T014)
- [X] T017 [US3] Implement `_handle_ingest_otel`, extend `_args_to_cli_overrides`, and route `cmd == "ingest-otel"` in `dispatch_command` in `src/evalforge_maestro/cli/commands.py` (depends on T009, T014, T015, T016)
- [X] T018 [P] [US3] Export `OtelTimestampUnit`, `OtelExtractorConfig`, `ingest_otel_spans`, and `load_otel_executions` in `src/evalforge_maestro/__init__.py` (depends on T003, T011)
- [X] T019 [US3] Update `tests/test_api_stability.py` to pin all new exports, signatures (`ingest_otel_spans`, `load_otel_executions`, `ReplayAdapter.from_otel_file`), and schema fields (`OtelExtractorConfig`, `CLIResolvedConfig.{otel_traces,otel}`) cleanly without altering prior M1–M7 contracts (depends on T018)

**Checkpoint**: All 3 user stories complete; CLI, SDK, and public API contracts pinned.

---

## Phase 6: Polish & CI Verification

**Purpose**: Update user-facing documentation, validate all Feature `008` quickstart workflows, and pass every Constitution release gate.

- [X] T020 [P] Document OTel execution trace ingestion (`ingest-otel`, `run --otel-traces`, SDK `ingest_otel_spans`/`ReplayAdapter.from_otel_file`, `[otel]`) in `README.md` and update `docs/future-features.md` milestone status
- [X] T021 Validate full test, coverage, static, security, lockfile, and packaging gates (`uv lock --check`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ruff check --select S src/`, `uv run mypy --strict src tests`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` & `evalforge_maestro.regression.gate`, `-m "gate_determinism or gate_immutability"`, `uv run pip-audit --skip-editable`, `uv build && uv run twine check --strict dist/*`) plus `specs/008-otel-trace-ingestion/quickstart.md` scenarios

---

## Dependencies & Execution Order

- **Phase 1–2 (`T001`–`T004`)**: Blocking schema foundation (`types.py`).
- **Phase 3 (`US1`, `T005`–`T007`)**: Depends on Phase 2; delivers single-trace OTel span normalization MVP.
- **Phase 4 (`US2`, `T008`–`T011`)**: Depends on `US1` trace assembly (`T007`); delivers multi-format loading, correlation, and `ReplayAdapter.from_otel_file`.
- **Phase 5 (`US3`, `T012`–`T019`)**: Depends on `US2` (`T009`–`T011`); delivers CLI config/parser/commands and top-level SDK exports.
- **Phase 6 (`T020`–`T021`)**: Depends on US1–US3 completion.
