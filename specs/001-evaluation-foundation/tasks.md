---

description: "Actionable, dependency-ordered task breakdown for Milestone 1: Evaluation Foundation"
---

# Tasks: Milestone 1 — Evaluation Foundation

**Input**: Design documents from `specs/001-evaluation-foundation/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required by project constitution Principles II, V, VI, and VII (AST library purity, API stability pinning, formula source-hash guards, `>=85%` branch coverage / `100%` on deterministic metrics, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, and hermetic `autouse` isolation).

**Organization**: Tasks are grouped by user story (`US1`–`US4`) so each increment can be implemented and validated independently in priority order (`P1` → `P4`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: Maps task to a specific user story (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Exact file paths and canonical `data-model.md` (`Entity.field`) citations are included where applicable

## Path Conventions

- Single Python package layout at repository root: `src/evalforge_maestro/` and `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize packaging, formatting, typing, test markers, line-ending discipline, and hermetic test isolation

- [X] T001 Create package and test directory hierarchy (`src/evalforge_maestro/{datasets,adapters,metrics,execution,storage}/` and `tests/{unit,integration,contract}/`) per `specs/001-evaluation-foundation/plan.md`
- [X] T002 Create LF line-ending enforcement rules for Python, Markdown, JSON/JSONL, TOML, and YAML files in `.gitattributes`
- [X] T003 Configure project metadata (`hatchling` + `hatch-vcs`, Python `>=3.10`, `pydantic>=2.7,<3`, `jsonschema>=4.23,<5`), `[dev]` extras, `ruff` (`E,W,F,I,UP,B,SIM,RUF` and `S` Bandit rules on `src/`), `mypy` (`strict`), `pytest` (`--strict-markers`, `filterwarnings=["error"]`, `gate_determinism`/`gate_immutability` markers), and branch coverage thresholds in `pyproject.toml`, then lock `uv.lock` and sync `.venv`
- [X] T004 [P] Create PEP 561 marker in `src/evalforge_maestro/py.typed` and base package bootstrap (`NullHandler`-only root package logger and version lookup) in `src/evalforge_maestro/__init__.py`
- [X] T005 [P] Implement global `autouse` hermetic isolation fixture (clearing `EVALFORGE_*` and provider credential env vars, blocking outbound network sockets) and shared test fixtures in `tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core exception hierarchy, canonical utilities, protocols, and single-source schemas in `types.py` required before any user story

**⚠️ CRITICAL**: No user story work begins until Phase 2 completes

- [X] T006 [P] Implement `EvalforgeError` exception hierarchy (`ConfigurationError`, `MissingExtraError`, `DatasetError`, `EmptyDatasetError`, `DuplicateCaseIdError`, `AdapterError`, `MetricError`, `ExecutionError`, `MemoryLimitExceededError`, `StorageError`, `ImmutabilityError`) per `contracts/public-api.md` in `src/evalforge_maestro/exceptions.py`
- [X] T007 [P] Implement canonical JSON serialization, incremental/one-shot SHA-256 hashing, 6-decimal float rounding (`1e-9` tolerance helper), and recursive credential-key redaction in `src/evalforge_maestro/_canonical.py`
- [X] T008 Implement strict base model configuration (`extra="forbid"`, `validate_assignment=True`), `MetricStatus` and `CaseSplit` enumerations, and `TargetAdapter` and `Metric` protocols per `data-model.md` (`MetricStatus`, `CaseSplit`) and `contracts/public-api.md` in `src/evalforge_maestro/types.py`
- [X] T009 Implement `CaseMetadata`, `CaseCriteria`, and `EvaluationCase` contracts in `src/evalforge_maestro/types.py` per `data-model.md` (`CaseMetadata.tags`, `CaseMetadata.split`, `CaseMetadata.difficulty`, `CaseMetadata.domain`, `CaseMetadata.source`, `CaseMetadata.extra`, `CaseCriteria.mandatory`, `CaseCriteria.json_schema`, `CaseCriteria.pass_threshold`, `CaseCriteria.metric_thresholds`, `EvaluationCase.schema_version`, `EvaluationCase.id`, `EvaluationCase.input`, `EvaluationCase.reference`, `EvaluationCase.expected_context`, `EvaluationCase.expected_tools`, `EvaluationCase.metadata`, `EvaluationCase.criteria`)
- [X] T010 Implement `TokenUsage`, `RetrievedChunk`, `ExecutionResult`, `MetricMetadata`, and `MetricResult` contracts in `src/evalforge_maestro/types.py` per `data-model.md` (`TokenUsage.prompt_tokens`, `TokenUsage.completion_tokens`, `TokenUsage.reasoning_tokens`, `TokenUsage.total_tokens`, `RetrievedChunk.id`, `RetrievedChunk.text`, `RetrievedChunk.parent_id`, `RetrievedChunk.rank`, `RetrievedChunk.score`, `RetrievedChunk.metadata`, `ExecutionResult.schema_version`, `ExecutionResult.case_id`, `ExecutionResult.input`, `ExecutionResult.output`, `ExecutionResult.retrieved_chunks`, `ExecutionResult.trace`, `ExecutionResult.tool_calls`, `ExecutionResult.tokens`, `ExecutionResult.elapsed_seconds`, `ExecutionResult.truncated`, `ExecutionResult.errors`, `ExecutionResult.warnings`, `ExecutionResult.system_version`, `ExecutionResult.model_id`, `ExecutionResult.config_fingerprint`, `ExecutionResult.adapter_metadata`, `MetricMetadata.metric_id`, `MetricMetadata.metric_version`, `MetricMetadata.what_it_measures`, `MetricMetadata.required_case_fields`, `MetricMetadata.required_execution_fields`, `MetricMetadata.calculation_method`, `MetricMetadata.known_limitations`, `MetricResult.schema_version`, `MetricResult.metric_id`, `MetricResult.metric_version`, `MetricResult.score`, `MetricResult.status`, `MetricResult.label`, `MetricResult.explanation`, `MetricResult.evidence`, `MetricResult.anomaly_flags`, `MetricResult.config_snapshot`)
- [X] T011 Implement `CaseEvaluationRecord`, `AggregateMetricSummary`, `RunRecord`, `RunManifestEntry`, and `OrchestratorConfig` contracts in `src/evalforge_maestro/types.py` per `data-model.md` (`CaseEvaluationRecord.schema_version`, `CaseEvaluationRecord.case_id`, `CaseEvaluationRecord.mandatory`, `CaseEvaluationRecord.execution`, `CaseEvaluationRecord.metrics`, `AggregateMetricSummary.metric_id`, `AggregateMetricSummary.metric_version`, `AggregateMetricSummary.mean_score`, `AggregateMetricSummary.applicable_count`, `AggregateMetricSummary.pass_count`, `AggregateMetricSummary.fail_count`, `AggregateMetricSummary.warning_count`, `AggregateMetricSummary.inconclusive_count`, `AggregateMetricSummary.not_applicable_count`, `RunRecord.schema_version`, `RunRecord.run_id`, `RunRecord.timestamp`, `RunRecord.package_version`, `RunRecord.dataset_id`, `RunRecord.dataset_version`, `RunRecord.dataset_fingerprint`, `RunRecord.evaluated_case_count`, `RunRecord.dataset_capped`, `RunRecord.max_dataset_cases`, `RunRecord.system_version`, `RunRecord.model_id`, `RunRecord.config_fingerprint`, `RunRecord.metric_versions`, `RunRecord.seed`, `RunRecord.aggregates`, `RunRecord.status_counts`, `RunRecord.mandatory_failed_case_ids`, `RunRecord.has_mandatory_failures`, `RunRecord.case_results`, `RunManifestEntry.schema_version`, `RunManifestEntry.run_id`, `RunManifestEntry.timestamp`, `RunManifestEntry.package_version`, `RunManifestEntry.dataset_id`, `RunManifestEntry.dataset_version`, `RunManifestEntry.dataset_fingerprint`, `RunManifestEntry.evaluated_case_count`, `RunManifestEntry.dataset_capped`, `RunManifestEntry.system_version`, `RunManifestEntry.config_fingerprint`, `RunManifestEntry.metric_versions`, `RunManifestEntry.aggregate_scores`, `RunManifestEntry.status_counts`, `RunManifestEntry.has_mandatory_failures`, `RunManifestEntry.mandatory_failed_case_ids`, `OrchestratorConfig.max_concurrency`, `OrchestratorConfig.max_dataset_cases`, `OrchestratorConfig.max_context_chars`, `OrchestratorConfig.case_timeout_seconds`, `OrchestratorConfig.max_memory_mb`, `OrchestratorConfig.memory_limit_action`, `OrchestratorConfig.fail_fast`, `OrchestratorConfig.retain_checkpoints`, `OrchestratorConfig.seed`)
- [X] T012 [P] Write unit tests for canonical JSON serialization, streaming SHA-256 digests, float rounding, and recursive credential redaction in `tests/unit/test_canonical.py`
- [X] T013 [P] Write unit tests for `EvalforgeError` hierarchy and strict Pydantic v2 constraints (`NaN`/`Inf` rejection, `[0.0, 1.0]` score bounds, `extra="forbid"`, JSON Schema parity against `contracts/schemas-v1.json`) in `tests/unit/test_types.py`

**Checkpoint**: Foundation ready — user story phases (`US1`–`US4`) can proceed independently in priority order

---

## Phase 3: User Story 1 — Define, Validate, Stream, and Fingerprint Evaluation Datasets (Priority: P1) 🎯 MVP

**Goal**: Enable lazy streaming JSONL dataset ingestion, strict `EvaluationCase` validation, duplicate ID rejection, empty-dataset rejection, and canonical SHA-256 dataset fingerprinting over evaluated cases

**Independent Test**: Pass valid, key-reordered, whitespace-varied, malformed, empty, duplicate-ID, capped (`max_cases`), and 10,000-line JSONL files to `DatasetEngine` and verify lazy iteration, field-level errors, and deterministic fingerprints

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Write unit tests for `DatasetEngine` streaming iteration, schema error line/field reporting, `DuplicateCaseIdError`, `EmptyDatasetError`, canonical SHA-256 equivalence under key/whitespace permutations, `max_cases` partial-slice fingerprinting (including 1-line lookahead boundary `total == max_cases` vs `total > max_cases`), default `dataset_id` handling, and a 10,000-case `< 5s` streaming/bounded-memory (`tracemalloc`) test in `tests/unit/test_datasets.py`

### Implementation for User Story 1

- [X] T015 [US1] Implement `DatasetStreamResult` and `DatasetEngine` (`iter_cases`, `fingerprint`) with lazy line-by-line JSONL intake, default `dataset_id` resolution (`Path.stem` for files / `"in-memory"` for iterables), 1-line non-blank lookahead at `max_cases` without scanning tail lines, boundary validation, seen-ID tracking, empty-dataset guard, and incremental canonical SHA-256 hashing in `src/evalforge_maestro/datasets/engine.py` citing `data-model.md` (`EvaluationCase.id`, `EvaluationCase.schema_version`, `EvaluationCase.input`, `RunRecord.dataset_id`, `RunRecord.dataset_fingerprint`, `RunRecord.evaluated_case_count`, `RunRecord.dataset_capped`, `RunRecord.max_dataset_cases`)
- [X] T016 [US1] Export `DatasetEngine` and `DatasetStreamResult` per `contracts/public-api.md` in `src/evalforge_maestro/datasets/__init__.py`

**Checkpoint**: User Story 1 is independently functional and verifiable without adapters, metrics, or storage

---

## Phase 4: User Story 2 — Execute Synchronous and Asynchronous Targets Through a Standard Adapter (Priority: P2)

**Goal**: Wrap sync/async callables via `CallableAdapter` capturing output, latency, errors, and redacted fingerprints, and orchestrate bounded-concurrency execution with timeouts, fault isolation, post-scoring payload truncation, and resident memory guardrails

**Independent Test**: Run `EvaluationOrchestrator` with sync and async `CallableAdapter` targets across normal, concurrent-throttled, slow-timeout, oversized-output, and exception-raising cases without external storage or downstream metrics

### Tests for User Story 2

- [X] T017 [P] [US2] Write unit tests for `CallableAdapter` covering sync functions, `async def` coroutines, awaitable returns, `pass_case` and `input_mapper`, `elapsed_seconds`, exception capture, and secret-redacted `config_fingerprint` in `tests/unit/test_adapters.py`
- [X] T018 [P] [US2] Write unit tests for `EvaluationOrchestrator` covering `max_concurrency` enforcement, `case_timeout_seconds` isolation, `fail_fast` abort behavior, `max_dataset_cases` capping, `max_context_chars` truncation flags, and `max_memory_mb` warn/abort guardrails in `tests/unit/test_execution.py`

### Implementation for User Story 2

- [X] T019 [P] [US2] Implement `CallableAdapter` satisfying `TargetAdapter` protocol (sync via `asyncio.to_thread`, async/awaitable support, latency measurement, error capture, secret-redacted `config_fingerprint`) in `src/evalforge_maestro/adapters/callable.py` and export from `src/evalforge_maestro/adapters/__init__.py` citing `data-model.md` (`ExecutionResult.case_id`, `ExecutionResult.input`, `ExecutionResult.output`, `ExecutionResult.elapsed_seconds`, `ExecutionResult.errors`, `ExecutionResult.system_version`, `ExecutionResult.model_id`, `ExecutionResult.config_fingerprint`, `ExecutionResult.adapter_metadata`)
- [X] T020 [US2] Implement bounded async worker pool execution (`arun` / `run`), `case_timeout_seconds` enforcement, per-case fault isolation / `fail_fast`, `max_dataset_cases` streaming cap, post-scoring `max_context_chars` truncation helper, and cross-OS resident memory guardrail (`resource.getrusage` with Windows fallback) in `src/evalforge_maestro/execution/orchestrator.py` and export `EvaluationOrchestrator` from `src/evalforge_maestro/execution/__init__.py` citing `data-model.md` (`OrchestratorConfig.max_concurrency`, `OrchestratorConfig.max_dataset_cases`, `OrchestratorConfig.max_context_chars`, `OrchestratorConfig.case_timeout_seconds`, `OrchestratorConfig.max_memory_mb`, `OrchestratorConfig.memory_limit_action`, `OrchestratorConfig.fail_fast`, `ExecutionResult.truncated`, `ExecutionResult.output`, `ExecutionResult.errors`)

**Checkpoint**: User Stories 1 and 2 work independently and together for target execution evidence capture

---

## Phase 5: User Story 3 — Score Execution Evidence with Versioned Deterministic Metrics (Priority: P3)

**Goal**: Provide `exact_match`, `normalized_match`, and `json_schema_validation` metrics with `MetricMetadata`, `metric_version`, schema precedence, `NOT_APPLICABLE` / `INCONCLUSIVE` safety, formula version pinning, and mandatory-case failure preservation in `RunRecord`

**Independent Test**: Supply `EvaluationCase` and `ExecutionResult` pairs directly to each metric and verify deterministic scores, explanations, `NOT_APPLICABLE` / `INCONCLUSIVE` statuses, schema resolution precedence, AST formula hash guards, and mandatory failure flagging

### Tests for User Story 3

- [X] T021 [P] [US3] Write unit tests achieving 100% branch coverage on `exact_match`, `normalized_match` (NFC, whitespace, `case_sensitive`, `strip_punctuation`), `json_schema_validation` (`criteria.json_schema` > schema-like `reference` > metric default), missing references (`NOT_APPLICABLE`), upstream errors (`INCONCLUSIVE`), and incompatible output types in `tests/unit/test_metrics.py`
- [X] T022 [P] [US3] Write contract tests verifying `MetricMetadata` declarations and pinning normalized AST/source hashes of built-in deterministic scoring functions against declared `metric_version` values in `tests/contract/test_metric_formulas.py`

### Implementation for User Story 3

- [X] T023 [US3] Implement `ExactMatchMetric`, `NormalizedMatchMetric`, and `JsonSchemaValidationMetric` (lazy-importing `jsonschema`, exposing `MetricMetadata`, pinning `metric_version = "1.0.0"`, enforcing strict `isinstance(output, str)` type mismatch `0.0`/`FAIL` semantics for text metrics, resolving thresholds via `CaseCriteria.metric_thresholds[metric_id] > CaseCriteria.pass_threshold > metric threshold`, enforcing schema precedence, rounding scores to 6 decimals, handling `NOT_APPLICABLE` and `INCONCLUSIVE`) in `src/evalforge_maestro/metrics/deterministic.py` and export classes plus `exact_match`, `normalized_match`, `json_schema_validation` aliases in `src/evalforge_maestro/metrics/__init__.py` citing `data-model.md` (`MetricMetadata.metric_id`, `MetricMetadata.metric_version`, `MetricMetadata.what_it_measures`, `MetricMetadata.required_case_fields`, `MetricMetadata.required_execution_fields`, `MetricMetadata.calculation_method`, `MetricMetadata.known_limitations`, `MetricResult.metric_id`, `MetricResult.metric_version`, `MetricResult.score`, `MetricResult.status`, `MetricResult.explanation`, `MetricResult.evidence`, `MetricResult.config_snapshot`, `CaseCriteria.json_schema`, `CaseCriteria.pass_threshold`, `CaseCriteria.metric_thresholds`, `EvaluationCase.reference`)
- [X] T024 [US3] Integrate metric execution on untruncated active output before persistence truncation, `AggregateMetricSummary` aggregation (excluding `NOT_APPLICABLE` from denominator), zero-initialized 5-key `status_counts`, and mandatory-case failure tracking into `EvaluationOrchestrator` in `src/evalforge_maestro/execution/orchestrator.py` citing `data-model.md` (`CaseEvaluationRecord.schema_version`, `CaseEvaluationRecord.case_id`, `CaseEvaluationRecord.mandatory`, `CaseEvaluationRecord.execution`, `CaseEvaluationRecord.metrics`, `AggregateMetricSummary.metric_id`, `AggregateMetricSummary.metric_version`, `AggregateMetricSummary.mean_score`, `AggregateMetricSummary.applicable_count`, `AggregateMetricSummary.pass_count`, `AggregateMetricSummary.fail_count`, `AggregateMetricSummary.warning_count`, `AggregateMetricSummary.inconclusive_count`, `AggregateMetricSummary.not_applicable_count`, `RunRecord.aggregates`, `RunRecord.status_counts`, `RunRecord.mandatory_failed_case_ids`, `RunRecord.has_mandatory_failures`, `CaseCriteria.mandatory`)

**Checkpoint**: User Stories 1, 2, and 3 deliver full deterministic evaluation scoring and mandatory-case safety

---

## Phase 6: User Story 4 — Checkpoint Progress Incrementally and Persist Immutable Run Records (Priority: P4)

**Goal**: Flush per-case progress incrementally to `.evalforge/tmp/<run_id>.jsonl`, commit canonical `RunRecord` artifacts atomically without overwrite to `.evalforge/runs/<run_id>.json`, append `RunManifestEntry` to `.evalforge/manifest.jsonl` under file locking, and enforce `0o700`/`0o600` permissions and zero secret leakage

**Independent Test**: Run `LocalRunStore` unit tests, interrupted/truncated integration runs, and `@pytest.mark.gate_determinism` / `@pytest.mark.gate_immutability` gate suites verifying crash checkpoint retention, post-commit cleanup, atomic non-overwrite rejection, permissions, and secret-free persistence

### Tests for User Story 4

- [X] T025 [P] [US4] Write unit tests for `LocalRunStore` covering `run_id` path-traversal rejection, `0o700`/`0o600` POSIX permissions, incremental checkpoint append/read/remove, canonical JSON layout, `ImmutabilityError` on existing `run_id`, and `manifest.jsonl` locked appends in `tests/unit/test_storage.py`
- [X] T026 [P] [US4] Write end-to-end integration tests verifying full sync/async runs from JSONL dataset through `LocalRunStore` commit and manifest indexing in `tests/integration/test_end_to_end_run.py`
- [X] T027 [P] [US4] Write crash-recovery and truncation integration tests verifying `.evalforge/tmp/<run_id>.jsonl` retention on `fail_fast`/abort without corrupting committed runs, post-commit checkpoint cleanup, and post-scoring `max_context_chars` truncation in `tests/integration/test_crash_and_truncation.py`
- [X] T028 [P] [US4] Implement `@pytest.mark.gate_determinism` release gate tests verifying identical datasets, adapters, and seeds produce identical scores, `dataset_fingerprint`, and aggregates in `tests/contract/test_determinism_gate.py`
- [X] T029 [P] [US4] Implement `@pytest.mark.gate_immutability` release gate tests verifying committed `.evalforge/runs/<run_id>.json` artifacts and canonical dataset fingerprints reject overwrite and tampering in `tests/contract/test_immutability_gate.py`

### Implementation for User Story 4

- [X] T030 [US4] Implement `LocalRunStore` (`checkpoint_path`, `run_path`, `manifest_path`, `append_checkpoint`, `read_checkpoints`, `remove_checkpoint`, `save_run`, `load_run`, `read_manifest`) with `run_id` validation, `0o700`/`0o600` permissions, POSIX `os.link` / cross-OS non-overwrite commit, and locked `manifest.jsonl` append per `contracts/storage-layout.md` in `src/evalforge_maestro/storage/local.py` and export from `src/evalforge_maestro/storage/__init__.py` citing `data-model.md` (`RunRecord.schema_version`, `RunRecord.run_id`, `RunRecord.timestamp`, `RunRecord.package_version`, `RunRecord.dataset_id`, `RunRecord.dataset_version`, `RunRecord.dataset_fingerprint`, `RunRecord.evaluated_case_count`, `RunRecord.dataset_capped`, `RunRecord.max_dataset_cases`, `RunRecord.system_version`, `RunRecord.model_id`, `RunRecord.config_fingerprint`, `RunRecord.metric_versions`, `RunRecord.seed`, `RunRecord.case_results`, `RunManifestEntry.schema_version`, `RunManifestEntry.run_id`, `RunManifestEntry.timestamp`, `RunManifestEntry.package_version`, `RunManifestEntry.dataset_id`, `RunManifestEntry.dataset_version`, `RunManifestEntry.dataset_fingerprint`, `RunManifestEntry.evaluated_case_count`, `RunManifestEntry.dataset_capped`, `RunManifestEntry.system_version`, `RunManifestEntry.config_fingerprint`, `RunManifestEntry.metric_versions`, `RunManifestEntry.aggregate_scores`, `RunManifestEntry.status_counts`, `RunManifestEntry.has_mandatory_failures`, `RunManifestEntry.mandatory_failed_case_ids`)
- [X] T031 [US4] Wire `LocalRunStore` incremental checkpointing, atomic `RunRecord` commit, default post-commit checkpoint deletion (`retain_checkpoints=False`), and aborted-run checkpoint preservation into `EvaluationOrchestrator` in `src/evalforge_maestro/execution/orchestrator.py` citing `data-model.md` (`OrchestratorConfig.retain_checkpoints`, `OrchestratorConfig.seed`)

**Checkpoint**: All four Milestone 001 user stories are complete, crash-safe, immutable, and independently testable

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Public API stabilization, architectural purity enforcement, cold-start lazy-import verification, and full constitution quality gate validation

- [X] T032 [P] Export clean Milestone 001 public API and explicit `__all__` in `src/evalforge_maestro/__init__.py` per `contracts/public-api.md` while keeping heavy optional modules unimported at package load
- [X] T033 [P] Implement AST import boundary checks (verifying `types`, `exceptions`, `_canonical`, `datasets`, `metrics`, `execution`, and `storage` never import `cli`, `tomllib`, `dotenv`, or concrete `adapters`, while allowing top-level package façade re-exports in `src/evalforge_maestro/__init__.py`) plus subprocess cold-start `sys.modules` verification in `tests/test_library_purity.py`
- [X] T034 [P] Implement `__all__` stability, `EvalforgeError` inheritance, and `inspect.signature` parameter pinning tests in `tests/test_api_stability.py`
- [X] T035 Run all constitution verification gates (`uv lock --check`, `ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`, `pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85`, 100% deterministic metric coverage check, `gate_determinism`/`gate_immutability` markers, and `uv build` + isolated `--no-dev` minimal install smoke test) and validate scenarios in `specs/001-evaluation-foundation/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — starts immediately (`T001` → `T002` → `T003`, then `T004` / `T005` in parallel)
- **Phase 2 (Foundational)**: Depends on Phase 1 (`T006` / `T007` in parallel, then sequential schema assembly `T008` → `T009` → `T010` → `T011` in `types.py`, followed by `T012` / `T013` in parallel) — BLOCKS all user stories
- **Phase 3 (`US1`, P1 — MVP)**: Depends on Phase 2 (`T014` → `T015` → `T016`)
- **Phase 4 (`US2`, P2)**: Depends on Phase 2; integrates cleanly with `DatasetEngine` (`US1` optional until orchestrator integration tests; `T017`/`T018`/`T019` can start directly after Phase 2, then `T020` wires `DatasetEngine` + `TargetAdapter`)
- **Phase 5 (`US3`, P3)**: Depends on Phase 2 for metric implementations (`T021`–`T023`) and Phase 4 (`T020`) for orchestrator scoring integration (`T024`)
- **Phase 6 (`US4`, P4)**: Depends on Phase 2 for `LocalRunStore` (`T025`, `T030`) and Phase 5 (`T024`) for end-to-end checkpointing/commit orchestration (`T026`–`T029`, `T031`)
- **Phase 7 (Polish & Gates)**: Depends on Phases 3–6 (`T032`, `T033`, `T034` in parallel, then `T035`)

### User Story Dependencies

- **`US1` (DatasetEngine)**: Depends only on Phase 2 (`types.py`, `exceptions.py`, `_canonical.py`) — zero dependency on `US2`, `US3`, or `US4`
- **`US2` (CallableAdapter & Orchestrator Core)**: Depends on Phase 2 + `US1` iterator contract (`DatasetEngine` input to `EvaluationOrchestrator.arun`)
- **`US3` (Deterministic Baseline Metrics)**: Metric classes (`ExactMatchMetric`, `NormalizedMatchMetric`, `JsonSchemaValidationMetric`) depend only on Phase 2; orchestrator metric aggregation (`T024`) integrates with `US2` (`T020`)
- **`US4` (Checkpointing & Immutable Storage)**: `LocalRunStore` (`T030`) depends only on Phase 2; end-to-end orchestrator commit (`T031`) integrates `US2` + `US3`

### Within Each User Story

- Write tests FIRST and confirm they fail before implementing production modules
- Contracts/models in `types.py` (Phase 2) before domain services
- Domain implementations (`engine.py`, `callable.py`, `deterministic.py`, `local.py`) before orchestrator wiring and package `__init__.py` exports
- Validate story-level checkpoint tests before advancing

---

## Parallel Opportunities

- **Phase 1**: `T004` (`py.typed` / `__init__.py`) and `T005` (`tests/conftest.py`) run in parallel after `T003`
- **Phase 2**: `T006` (`exceptions.py`) and `T007` (`_canonical.py`) run in parallel; `T012` (`test_canonical.py`) and `T013` (`test_types.py`) run in parallel after `T011`
- **Phase 4 (`US2`)**: `T017` (`test_adapters.py`), `T018` (`test_execution.py`), and `T019` (`CallableAdapter`) run in parallel before `T020` (`orchestrator.py`)
- **Phase 5 (`US3`)**: `T021` (`test_metrics.py`) and `T022` (`test_metric_formulas.py`) run in parallel before `T023` (`deterministic.py`)
- **Phase 6 (`US4`)**: `T025`–`T029` (storage unit tests, E2E/crash integration tests, determinism/immutability gates) can be authored in parallel alongside `T030` (`storage/local.py`) before `T031` (`orchestrator.py`)
- **Phase 7**: `T032` (`__init__.py`), `T033` (`test_library_purity.py`), and `T034` (`test_api_stability.py`) run in parallel before final gate run `T035`

### Parallel Example: User Story 2 & User Story 4

```bash
# User Story 2 parallel batch (after Phase 2):
Task T017: "tests/unit/test_adapters.py"
Task T018: "tests/unit/test_execution.py"
Task T019: "src/evalforge_maestro/adapters/callable.py"

# User Story 4 parallel test & storage batch:
Task T025: "tests/unit/test_storage.py"
Task T028: "tests/contract/test_determinism_gate.py"
Task T029: "tests/contract/test_immutability_gate.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup: `T001`–`T005`) and Phase 2 (Foundational Contracts: `T006`–`T013`)
2. Complete Phase 3 (User Story 1: `T014`–`T016`)
3. **STOP and VALIDATE**: Run `tests/unit/test_canonical.py`, `tests/unit/test_types.py`, and `tests/unit/test_datasets.py` to prove streaming JSONL intake, schema enforcement, duplicate rejection, and canonical SHA-256 dataset fingerprinting work end-to-end

### Incremental Delivery

1. **Setup + Foundational (`T001`–`T013`)** → Canonical `types.py` contracts, exception hierarchy, and hermetic test harness ready
2. **Add `US1` (`T014`–`T016`)** → Validated streaming dataset engine & canonical fingerprinting (MVP increment)
3. **Add `US2` (`T017`–`T020`)** → Sync/async `CallableAdapter` + bounded, fault-isolated `EvaluationOrchestrator`
4. **Add `US3` (`T021`–`T024`)** → Versioned deterministic baseline metrics + mandatory-case anti-masking aggregation
5. **Add `US4` (`T025`–`T031`)** → Incremental checkpointing + immutable atomic `.evalforge/` storage + release gates
6. **Polish (`T032`–`T035`)** → Public API exports, AST library purity checks, signature pinning, and full static/coverage/determinism/immutability verification

---

## Notes

- All `[P]` tasks operate on distinct files without unfinished upstream dependencies on the same file
- All `data-model.md` constrained entity fields are explicitly cited in their implementing tasks (`T008`–`T011`, `T015`, `T019`, `T020`, `T023`, `T024`, `T030`, `T031`)
- Deferred out-of-scope milestones (`002` RAG/IR, `003` regression/gates, `004` LLM judges, `005` CLI/Markdown reports) MUST NOT be introduced in `001-evaluation-foundation` tasks
