# Feature Specification: Milestone 1 — Evaluation Foundation

**Feature Branch**: `001-evaluation-foundation`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Reference docs/intent.md for overall system context and core data contracts, and specify Milestone 1: Evaluation Foundation (001-evaluation-foundation). In Scope for 001: Core data models in types.py (EvaluationCase, ExecutionResult, MetricResult, RunRecord with schema_version); DatasetEngine (streaming JSONL loader, Pydantic boundary validation, duplicate ID rejection, canonical SHA-256 dataset fingerprinting); CallableAdapter (generic sync/async Python callable wrapper capturing output, latency, errors, and system/config fingerprints); Deterministic baseline metrics (exact_match, normalized_match, json_schema_validation with explicit metric_version and formula metadata); EvaluationOrchestrator (bounded concurrency, per-case fault isolation, incremental temporary journaling .evalforge/tmp/<run_id>.jsonl, memory guardrails); Immutable local storage (.evalforge/runs/<run_id>.json + manifest.jsonl) with atomic file writes. Explicitly Out of Scope for 001 (deferred to 002–005): RAGAdapter/DocpipeAdapter/IR metrics -> 002; baseline comparison/trend/quality gates -> 003; LLM judges/LiteLLM/--mock judge/calibration -> 004; full CLI subcommands and Markdown reports -> 005."

## Clarifications

### Session 2026-11-18

- Q: When a run limits how many cases are read (`max_dataset_cases`), should the dataset fingerprint (`dataset_fingerprint`) represent only the evaluated subset or the entire source file? → A: Compute `dataset_fingerprint` strictly over the evaluated case subset and record partial-limit metadata (`evaluated_case_count` and applied cap indicator) in `RunRecord`.
- Q: Where should `json_schema_validation` read the expected JSON Schema for an `EvaluationCase` when a case may also provide a text `reference` for `exact_match` or `normalized_match`? → A: Prefer `criteria.json_schema` first, fall back to `EvaluationCase.reference` when it is a JSON Schema mapping, then use a metric-configured default schema if supplied.
- Q: When a target output or captured context exceeds `max_context_chars`, should payload truncation happen before metric scoring or only when persisting checkpoints and run artifacts after scoring? → A: Evaluate metrics against the full single-case output in memory first, then truncate oversized output or context fields before persisting checkpoints and `RunRecord` (`truncated = True`).
- Q: How should Milestone 001 manage the temporary checkpoint journal (`.evalforge/tmp/<run_id>.jsonl`) after a run completes or fails? → A: Retain `.evalforge/tmp/<run_id>.jsonl` on aborted or failed runs for diagnostics, remove it by default upon successful atomic commit (unless retention is explicitly configured), and omit automatic mid-run resume/replay from Milestone 001.
- Q: Should `EvaluationOrchestrator` enforce an optional per-case execution timeout (`case_timeout_seconds`), and how should timed-out cases affect the evaluation batch? → A: Support optional `case_timeout_seconds` (default `None`); capture timeouts as `ExecutionResult` errors, mark dependent metrics `INCONCLUSIVE`, and continue remaining cases unless `fail_fast` is enabled.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define, Validate, Stream, and Fingerprint Evaluation Datasets (Priority: P1)

An AI engineer or dataset curator supplies a versioned JSON Lines (JSONL) dataset file containing evaluation cases (inputs, optional reference answers or schemas, metadata, and pass/mandatory criteria) and loads it through the `DatasetEngine` without modifying their target AI system or loading the entire dataset into memory at once. The system validates every record against the canonical `EvaluationCase` contract, rejects duplicate case identifiers or malformed lines with clear diagnostics, and computes a deterministic SHA-256 fingerprint over the canonicalized dataset content.

**Why this priority**: Every evaluation, metric calculation, and historical comparison depends on trustworthy, reproducible, validated input datasets. Without streaming intake, duplicate rejection, and canonical dataset fingerprinting, downstream results cannot be audited or reproduced.

**Independent Test**: Can be fully tested by feeding valid, malformed, whitespace-varied, duplicate-ID, and multi-thousand-record JSONL datasets into `DatasetEngine` and verifying lazy streaming iteration, schema error reporting, duplicate rejection, and deterministic fingerprint equivalence.

**Acceptance Scenarios**:

1. **Given** a valid JSONL dataset file with unique case identifiers and `schema_version` metadata, **When** the engineer loads the dataset via `DatasetEngine`, **Then** cases are yielded lazily one record at a time as validated `EvaluationCase` contracts without buffering the full file payload in memory.
2. **Given** two JSONL dataset files representing the exact same sequence of evaluation cases with differing JSON key ordering or non-semantic whitespace, **When** `DatasetEngine` computes each dataset's canonical SHA-256 fingerprint, **Then** both datasets yield the identical SHA-256 digest; changing a single character of case content produces a distinct digest.
3. **Given** a dataset containing a duplicate `EvaluationCase.id` or a record failing schema validation (such as missing required `id` or `input`, or unsupported `schema_version`), **When** `DatasetEngine` streams the dataset, **Then** validation fails explicitly with an informative error identifying the offending case index/line and field without silently overwriting prior records.

---

### User Story 2 - Execute Synchronous and Asynchronous Targets Through a Standard Adapter (Priority: P2)

An AI engineer wraps an existing synchronous or asynchronous target application function inside `CallableAdapter` and runs it against evaluation cases via `EvaluationOrchestrator`. The adapter captures the target's output alongside execution evidence (wall-clock latency, captured runtime errors, truncation indicators, and target system/configuration fingerprints) inside an `ExecutionResult` contract, while the orchestrator bounds concurrency, protects workstation memory, and isolates individual case failures.

**Why this priority**: EvalForge Maestro must remain an independent verification engine decoupled from how target systems are built. A standardized adapter plus bounded, fault-isolated orchestration allows any target function to be evaluated safely on developer workstations and CI runners.

**Independent Test**: Can be fully tested by running `EvaluationOrchestrator` with both synchronous and asynchronous `CallableAdapter` instances across mixed normal, slow, oversized-output, and exception-raising test cases without needing external metrics or storage.

**Acceptance Scenarios**:

1. **Given** a synchronous or asynchronous target callable wrapped in `CallableAdapter` with declared system version and configuration metadata, **When** `EvaluationOrchestrator` executes a batch of `EvaluationCase` records, **Then** each execution produces a typed `ExecutionResult` containing `case_id`, `input`, `output`, measured `elapsed_seconds`, target/configuration fingerprints, and `truncated` status.
2. **Given** a dataset where one target invocation raises an unhandled exception, exceeds an optional `case_timeout_seconds` limit, or exceeds a configured context-character guardrail (`max_context_chars`), **When** `EvaluationOrchestrator` runs in standard fault-isolated mode (`fail_fast` disabled), **Then** the failing or timed-out case captures the diagnostic error inside its `ExecutionResult` (and records dependent metrics as `INCONCLUSIVE`), metrics evaluate against the full active output for oversized cases before oversized persisted fields are truncated with `truncated = True` in checkpoints and `RunRecord`, and all remaining valid cases continue executing to completion.
3. **Given** a multi-case dataset and a configured concurrency cap (`max_concurrency`, defaulting to `4`) and case limit (`max_dataset_cases`), **When** `EvaluationOrchestrator` processes the stream, **Then** active concurrent target executions never exceed `max_concurrency`, at most `max_dataset_cases` cases are processed when configured, and a resident memory soft-cap check warns or aborts cleanly if exceeded.
4. **Given** `fail_fast` mode is enabled and a target invocation raises an unhandled error, **When** `EvaluationOrchestrator` executes the batch, **Then** execution halts cleanly after recording the failing case error rather than continuing remaining cases.

---

### User Story 3 - Score Execution Evidence with Versioned Deterministic Metrics (Priority: P3)

An engineer configures deterministic baseline metrics (`exact_match`, `normalized_match`, and `json_schema_validation`) to score target outputs produced in `ExecutionResult` against reference expectations in `EvaluationCase`. Each metric emits a bounded, explainable `MetricResult` coupled to a pinned `metric_version` and formal metric metadata, cleanly handles absent references, and preserves mandatory case failure visibility.

**Why this priority**: Deterministic baseline metrics establish the zero-cost, reproducible scoring layer required before regression detection or model-based judges can be trusted.

**Independent Test**: Can be fully tested by passing pairs of `EvaluationCase` and `ExecutionResult` instances directly to each metric and verifying exact scores, normalization behavior, schema validation diagnostics, `NOT_APPLICABLE` handling, `metric_version` presence, and metric metadata declarations.

**Acceptance Scenarios**:

1. **Given** an `EvaluationCase` with a reference text and an `ExecutionResult` with output text, **When** `exact_match` and `normalized_match` evaluate the case, **Then** `exact_match` scores `1.0` (`PASS`) only on exact string equality and `0.0` (`FAIL`) otherwise, while `normalized_match` applies canonical normalization (Unicode normalization, whitespace trimming/collapsing, and configurable case folding) before comparison, each returning scores rounded to 6 decimal places.
2. **Given** an `EvaluationCase` specifying a target JSON Schema expectation and an `ExecutionResult` containing serialized JSON or structured object output, **When** `json_schema_validation` evaluates the case, **Then** valid conforming payloads score `1.0` (`PASS`), malformed JSON or schema violations score `0.0` (`FAIL`) with a human-readable validation failure explanation, and cases lacking a schema expectation return `score = None` with `status = NOT_APPLICABLE`.
3. **Given** any deterministic baseline metric implementation, **When** inspected or invoked, **Then** it formally declares what it measures, required fields from `EvaluationCase` and `ExecutionResult`, its calculation method, known limitations, and an explicit `metric_version` recorded on every emitted `MetricResult`.
4. **Given** an evaluation batch containing both high-scoring standard cases and a failed case flagged with `criteria.mandatory = True`, **When** run-level summaries are computed, **Then** the mandatory case failure is explicitly surfaced in the run summary and status flags so aggregate averages never mask the critical failure.

---

### User Story 4 - Checkpoint Progress Incrementally and Persist Immutable Run Records (Priority: P4)

An AI engineer or compliance auditor runs an evaluation batch and relies on incremental checkpointing during execution followed by atomic persistence of an immutable `RunRecord` and run ledger entry in `.evalforge/`. Partial crashes leave diagnostic checkpoints isolated from committed history, and committed run artifacts cannot be silently altered or leaked with sensitive credentials.

**Why this priority**: Reproducible engineering evidence and auditability require crash-safe incremental persistence during large runs and tamper-evident immutability once a run record is committed.

**Independent Test**: Can be fully tested by running an evaluation to persist `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl`, inspecting file permissions and canonical JSON serialization, verifying rejection of duplicate `run_id` overwrites, and simulating a mid-run failure to confirm `.evalforge/tmp/<run_id>.jsonl` retains partial progress without corrupting committed storage.

**Acceptance Scenarios**:

1. **Given** an active evaluation run with a unique `run_id`, **When** cases complete incrementally, **Then** case-level `ExecutionResult` and `MetricResult` entries are flushed progressively to `.evalforge/tmp/<run_id>.jsonl` without holding all full payloads in memory, and upon completion the final `RunRecord` is committed atomically to `.evalforge/runs/<run_id>.json` alongside a summary entry appended to `.evalforge/manifest.jsonl`.
2. **Given** a run that fails fatally or is interrupted mid-batch before final commit, **When** inspecting `.evalforge/`, **Then** no half-written or corrupted file exists in `.evalforge/runs/<run_id>.json` or `.evalforge/manifest.jsonl`, while completed checkpoint entries remain inspectable in `.evalforge/tmp/<run_id>.jsonl`.
3. **Given** a persisted `RunRecord` at `.evalforge/runs/<run_id>.json`, **When** a subsequent process attempts to write or overwrite the same `run_id`, **Then** the storage layer rejects the mutation with an explicit immutability error rather than modifying the historical artifact in place.
4. **Given** `.evalforge/` artifacts created on a POSIX filesystem, **When** inspecting directory and file permissions and persisted JSON contents, **Then** `.evalforge/` directories use owner-restricted permissions (`0o700`), artifact files use owner-only read/write permissions (`0o600`), timestamps use ISO-8601 UTC format, and zero credential/API key secrets appear in any persisted record.

---

### Edge Cases

- What happens when a JSONL dataset file is empty (0 cases) or contains only blank/whitespace lines? Empty or whitespace-only datasets MUST fail validation clearly (rejecting evaluation with a dataset validation error rather than silently returning a misleading `PASS`), while benign trailing newlines in valid JSONL files MUST be ignored cleanly.
- What happens when an `EvaluationCase` lacks a `reference` field required by `exact_match` or `normalized_match`, or lacks a reference schema for `json_schema_validation`? The metric MUST return `score = None` with `status = NOT_APPLICABLE` and a clear explanation rather than raising a division-by-zero error or emitting `0.0` or `NaN`.
- What happens when a target callable returns a non-string object (such as a structured dictionary, list, number, or `None`)? `CallableAdapter` MUST capture the value cleanly inside `ExecutionResult` according to schema rules, and string-based metrics (`exact_match`, `normalized_match`) MUST require string `output` values when `reference` is a string and return `score = 0.0` (`FAIL`) with a clear type-mismatch diagnostic rather than coercing or crashing the batch (reserving `INCONCLUSIVE` strictly for upstream `ExecutionResult.errors`).
- What happens when `EvaluationOrchestrator` encounters an adapter failure on a single case whose `ExecutionResult` holds an error? Metrics requiring target output MUST record `INCONCLUSIVE` (with `score = None` and explanatory reference to the execution error) rather than scoring `0.0` as if the model answered incorrectly.
- What happens when `max_dataset_cases` is set smaller than the file length? `DatasetEngine` / `EvaluationOrchestrator` MUST stop reading after the configured limit without scanning unread tail records, compute `dataset_fingerprint` strictly over the evaluated case subset, and record `evaluated_case_count` along with partial-limit metadata (`dataset_capped` / applied `max_dataset_cases`) in `RunRecord`.
- What happens when `.evalforge/` does not yet exist in the working directory? Storage initialization MUST create `.evalforge/`, `.evalforge/runs/`, and `.evalforge/tmp/` safely with owner-restricted permissions (`0o700`).
- What happens when two evaluations run concurrently in the same `.evalforge/` workspace? Distinct `run_id` values prevent `.evalforge/tmp/<run_id>.jsonl` and `.evalforge/runs/<run_id>.json` collisions, and appends to `.evalforge/manifest.jsonl` MUST remain line-atomic without interleaved bytes.

## Requirements *(mandatory)*

### Scope Boundaries

- **In Scope (001-evaluation-foundation):**
  - Core typed contracts (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`) defined in a single canonical contract schema (`types.py`) with `schema_version`.
  - `DatasetEngine` supporting lazy JSONL streaming, strict boundary validation, duplicate case ID rejection, and canonical SHA-256 fingerprinting.
  - `CallableAdapter` supporting synchronous and asynchronous target callables with output, latency, error, truncation, and target/config fingerprint capture.
  - Deterministic baseline metrics (`exact_match`, `normalized_match`, `json_schema_validation`) with explicit `metric_version`, formal formula/limitation metadata, and `[0.0, 1.0]` / `None` + status semantics.
  - `EvaluationOrchestrator` enforcing bounded concurrency, per-case fault isolation, incremental `.evalforge/tmp/<run_id>.jsonl` checkpointing, and memory/context guardrails.
  - Immutable local persistence to `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` using atomic writes and restricted file permissions.
- **Explicitly Out of Scope (Deferred to Milestones 002–005):**
  - `RAGAdapter`, `DocpipeAdapter`, and IR retrieval metrics (`Precision@K`, `Recall@K`, `MRR`, `NDCG@K`, `Hit Rate@K`) -> Milestone `002`.
  - Baseline pinning/comparison, sliding trend windows, cross-run anomaly disagreement scoring, and acceptance quality gates -> Milestone `003`.
  - LLM judges, LiteLLM integration, `--mock` judge mode, and human ground-truth calibration -> Milestone `004`.
  - Full CLI subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`) and Markdown report generation -> Milestone `005`.

### Functional Requirements

#### Core Contracts & Architectural Purity

- **FR-001**: System MUST define all shared domain contracts (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`) in a single canonical schema source (`types.py`), each carrying an explicit `schema_version` field (defaulting to `"1.0"`).
- **FR-002**: System MUST reject untyped ad-hoc dictionary payloads across subsystem boundaries and persisted artifacts; all inputs, execution results, metric outputs, and run records MUST conform to validated schema contracts.
- **FR-003**: System MUST maintain strict library purity across Milestone 001 core and domain modules (`types`, `datasets`, `execution`, `metrics`, `storage`): library modules MUST NEVER import CLI layers, configuration loaders, or environment-file parsers, and MUST NEVER read external files such as `evalforge.toml` or `.env`; `metrics` and core data/storage modules (`types`, `datasets`, `storage`) MUST NEVER import concrete target adapters, and `execution` MUST depend only on an abstract adapter contract rather than concrete adapter implementations.
- **FR-004**: Library modules MUST emit diagnostics exclusively through passive host-controlled logging (`NullHandler` semantics) and MUST NEVER write directly to standard output or reconfigure global/root logging.

#### Dataset Engine (`DatasetEngine`)

- **FR-005**: `DatasetEngine` MUST stream JSONL evaluation dataset records lazily via incremental iteration so memory usage does not scale with full dataset size.
- **FR-006**: `DatasetEngine` MUST validate every incoming record against `EvaluationCase` (`id`, `input`, optional `reference`, `expected_context`, `expected_tools`, `metadata`, `criteria`, `schema_version`) and raise an explicit validation error identifying the offending line/case ID and invalid field on any schema violation.
- **FR-007**: `DatasetEngine` MUST track seen `EvaluationCase.id` values during loading/streaming and raise an explicit duplicate-ID error immediately if any `id` recurs within a dataset.
- **FR-008**: `DatasetEngine` MUST compute a canonical SHA-256 `dataset_fingerprint` over canonicalized JSON representation (sorted keys, UTF-8 encoding, `\n` line endings) across the streamed/evaluated cases so non-semantic formatting or key-order variations produce identical digests while any content change alters the digest. When `max_dataset_cases` caps dataset intake, `dataset_fingerprint` MUST hash only the evaluated subset and `RunRecord` MUST record partial-limit metadata (`evaluated_case_count` and whether intake was capped).
- **FR-009**: `DatasetEngine` MUST reject empty datasets (zero valid cases) with a clear dataset validation error before execution begins.

#### Target Invocation (`CallableAdapter`)

- **FR-010**: `CallableAdapter` MUST wrap both synchronous and asynchronous target callables behind a uniform adapter protocol returning an `ExecutionResult` for each `EvaluationCase`.
- **FR-011**: `CallableAdapter` MUST record `case_id`, `input`, actual `output`, measured wall-clock `elapsed_seconds` (non-negative float), runtime error details (when raised), `truncated` status flag, and declared target `system_version` / model / configuration fingerprints on every `ExecutionResult`.
- **FR-012**: When a target output or captured context exceeds configured character limits (`max_context_chars`), metrics MUST evaluate against the full single-case output held in active memory, and the orchestrator/persistence boundary MUST truncate oversized payload fields prior to writing checkpoints (`.evalforge/tmp/<run_id>.jsonl`) and `RunRecord` while setting `ExecutionResult.truncated = True`.

#### Deterministic Baseline Metrics

- **FR-013**: System MUST provide three deterministic baseline metrics: `exact_match`, `normalized_match`, and `json_schema_validation`, each returning a `MetricResult` with `score` constrained to `float | None` within `[0.0, 1.0]` (never `NaN` or `Inf`), rounded to 6 decimal places, paired with `metric_version`, explicit `status` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, or `NOT_APPLICABLE`), human-readable `explanation`, supporting evidence references, `anomaly_flags`, and metric config snapshot. Effective pass/fail thresholds MUST resolve in precedence order: `CaseCriteria.metric_thresholds[metric_id]` > `CaseCriteria.pass_threshold` > metric-configured `threshold` (default `1.0`).
- **FR-014**: Every metric MUST formally declare and expose metadata specifying: what it measures, required fields on `EvaluationCase` and `ExecutionResult`, its calculation method, its `metric_version`, and known limitations.
- **FR-015**: `exact_match` and `normalized_match` MUST compare string `output` against string `reference` (when `output` is `None` or a non-string object while `reference` is a string, both MUST return `score = 0.0` / `FAIL` with an explicit type-mismatch explanation rather than coercing via `str()`); `exact_match` MUST verify strict string equality (`1.0` / `PASS` on match, `0.0` / `FAIL` on mismatch), while `normalized_match` MUST apply Unicode normalization (NFC), whitespace trimming and internal whitespace collapsing, and configurable case-folding (case-insensitive by default, plus optional punctuation stripping disabled by default) prior to comparison.
- **FR-016**: `json_schema_validation` MUST resolve the expected JSON Schema in priority order: (1) `EvaluationCase.criteria.json_schema` when present, (2) `EvaluationCase.reference` when it is a JSON Schema mapping, and (3) a metric-configured default schema if supplied; it MUST then verify that target output parses as valid JSON (or structured JSON-compatible mapping/list) and conforms to that schema (`1.0` / `PASS` when valid, `0.0` / `FAIL` with specific schema/parse failure explanation when invalid).
- **FR-017**: When a required reference (`reference` text or reference schema) is absent on an `EvaluationCase`, the applicable metric MUST return `score = None` with `status = NOT_APPLICABLE` rather than throwing a runtime error or emitting `0.0` or `NaN`.
- **FR-018**: When `ExecutionResult` contains a target execution error (`error` present), metrics dependent on valid target output MUST record `score = None` with `status = INCONCLUSIVE` and explain the upstream execution failure rather than scoring `0.0`.

#### Evaluation Orchestration & Workstation Guardrails (`EvaluationOrchestrator`)

- **FR-019**: `EvaluationOrchestrator` MUST execute evaluation cases with bounded concurrency (`max_concurrency`, defaulting to `4`) across both synchronous and asynchronous target adapters without exceeding the configured concurrency cap.
- **FR-020**: `EvaluationOrchestrator` MUST support an optional per-case execution timeout (`case_timeout_seconds`, defaulting to `None`) and isolate faults per case: an unhandled exception or exceeded `case_timeout_seconds` during target invocation or metric evaluation on one case MUST be captured inside that case's `ExecutionResult` (with dependent metrics marked `INCONCLUSIVE`) without crashing remaining cases, unless `fail_fast` is enabled.
- **FR-021**: `EvaluationOrchestrator` MUST enforce workstation resource guardrails including configurable `max_dataset_cases` cap, `max_context_chars` payload truncation, and optional resident memory soft-cap monitoring that logs a warning or halts execution cleanly before exhausting system memory.
- **FR-022**: `EvaluationOrchestrator` MUST preserve mandatory case failure visibility in `RunRecord`: if any case marked `criteria.mandatory = True` fails any evaluated metric (or ends `INCONCLUSIVE`/errored), `RunRecord` MUST flag the mandatory case failure explicitly alongside aggregate scores so aggregate means never mask mandatory failures.
- **FR-023**: Aggregate metric scores in `RunRecord` MUST be rounded to 6 decimal places, exclude `NOT_APPLICABLE` results from the average denominator, and explicitly report counts of `PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, and `NOT_APPLICABLE` outcomes.

#### Incremental Checkpointing & Immutable Local Storage

- **FR-024**: During execution, `EvaluationOrchestrator` MUST incrementally checkpoint completed case `ExecutionResult` and `MetricResult` entries to `.evalforge/tmp/<run_id>.jsonl` so progress is flushed progressively rather than buffered solely in RAM. Aborted or failed runs MUST retain `.evalforge/tmp/<run_id>.jsonl` for post-mortem inspection, whereas successful atomic commits MUST remove it by default unless retention is explicitly configured; automatic mid-run resume/replay is out of scope for Milestone 001.
- **FR-025**: Upon completion, storage MUST write the final `RunRecord` atomically (via temporary file write and atomic rename) to `.evalforge/runs/<run_id>.json` using canonical JSON formatting (sorted keys, UTF-8, `\n` LF endings) and append a corresponding run summary line to `.evalforge/manifest.jsonl`.
- **FR-026**: Storage MUST enforce artifact immutability: attempting to persist a `RunRecord` whose `run_id` already exists at `.evalforge/runs/<run_id>.json` MUST fail with an explicit immutability error and leave the existing artifact untouched.
- **FR-027**: Local artifact persistence MUST create `.evalforge/` subdirectories with owner-restricted permissions (`0o700`) and artifact files with `0o600` permissions, and MUST ensure no secrets or credentials are persisted into `RunRecord`, `manifest.jsonl`, or temporary checkpoints.

### Key Entities *(include if feature involves data)*

- **`EvaluationCase`**: Represents a single immutable test item within an evaluation dataset. Key attributes: `schema_version`, unique dataset-scoped `id`, `input` payload, optional `reference` expectation (text or structured schema/value), optional `expected_context` (reserved for retrieval cases), optional `expected_tools` (reserved for agent cases), `metadata` (tags, split such as `eval`/`train`/`few_shot`, difficulty, domain, provenance), and `criteria` (including `mandatory` flag, optional `json_schema`, and metric/threshold overrides).
- **`ExecutionResult`**: Captures raw target behavior and execution evidence for one `EvaluationCase`. Key attributes: `schema_version`, `case_id`, `input`, `output`, `elapsed_seconds`, `truncated` boolean, `errors` / runtime warnings, target `system_version` and config/model fingerprints, plus optional reserved fields for retrieved context chunks, trace steps, tool calls, and token counts.
- **`MetricResult`**: Captures one metric's evaluation outcome on one `ExecutionResult`. Key attributes: `schema_version`, `metric_id`, `metric_version`, `score` (`float | None` in `[0.0, 1.0]`), `status` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, `NOT_APPLICABLE`), optional categorical `label`, human-readable `explanation`, supporting `evidence` references, `anomaly_flags`, and metric config snapshot.
- **`RunRecord`**: Represents the complete immutable audit artifact for one evaluation run. Key attributes: `schema_version`, unique `run_id`, ISO-8601 UTC `timestamp`, `package_version`, `dataset_id`, `dataset_version`, canonical SHA-256 `dataset_fingerprint` (of the evaluated cases), `evaluated_case_count` and partial-limit metadata (`dataset_capped` / applied `max_dataset_cases`), `system_version`, config/prompt fingerprints, `metric_versions`, controllable random `seed` (optional), rounded aggregate metric summaries and status counts, mandatory-case failure indicators, and per-case `ExecutionResult` + `MetricResult` entries.
- **`RunManifestEntry`**: Lightweight summary record appended per committed run to `.evalforge/manifest.jsonl` containing `schema_version`, `run_id`, `timestamp`, `dataset_id`, `dataset_fingerprint`, `system_version`, aggregate scores, and mandatory-case/overall status counts for fast run indexing without reading full run files.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Engineers can stream, validate, and fingerprint a 10,000-case JSONL dataset with constant per-case intake buffering (memory footprint independent of total file line count) and deterministic fingerprint computation completing in under 5 seconds on standard workstation hardware.
- **SC-002**: 100% of malformed dataset records, empty datasets, and duplicate case identifiers are rejected before target evaluation begins, with explicit diagnostic identification of the failing case or line number.
- **SC-003**: Semantically identical datasets differing only in JSON key order or whitespace produce identical SHA-256 dataset fingerprints across 100% of runs, while any single-character modification to case content produces a distinct fingerprint across 100% of runs.
- **SC-004**: Both synchronous and asynchronous target functions execute cleanly through `CallableAdapter`, honoring configured concurrency caps (defaulting to 4 concurrent executions) and truncating oversized context payloads while recording `truncated = True` in 100% of capped cases.
- **SC-005**: In batch runs where individual cases raise target exceptions or timeouts (up to 20% injected failures), 100% of remaining healthy cases complete and receive metric scores when fail-fast is disabled, and 100% of failed cases record structured error details and `INCONCLUSIVE` metric status.
- **SC-006**: Deterministic baseline metrics (`exact_match`, `normalized_match`, `json_schema_validation`) produce 100% identical scores (rounded to 6 decimal places) across repeated identical runs, emit `NOT_APPLICABLE` (`score = None`) on 100% of cases missing required reference expectations, and never mask a failed mandatory case (`criteria.mandatory = True`) in run-level summaries.
- **SC-007**: Simulated process failure prior to final commit leaves 0 corrupted or partial files in committed run storage while preserving completed incremental checkpoints in `.evalforge/tmp/<run_id>.jsonl`, and 100% of attempts to overwrite an existing committed `run_id` are rejected.
- **SC-008**: 100% of persisted artifacts enforce owner-restricted permissions (`0o700` directories / `0o600` files) and contain zero leaked credential fields when credentials are excluded or redacted, while 100% of Milestone 001 core evaluation components execute independently with zero runtime coupling to command-line interfaces, external configuration files, or target AI frameworks.

## Assumptions

- **Core Technology Context**: Per `docs/intent.md` and the project constitution, Milestone 001 is delivered as a standalone evaluation library providing typed schema boundary validation anchored in a single canonical contract module (`types.py`).
- **Programmatic Execution Scope**: Because CLI subcommands are deferred to Milestone 005, Milestone 001 capabilities are exercised and verified through the programmatic evaluation interfaces (`DatasetEngine`, `CallableAdapter`, deterministic baseline metrics, `EvaluationOrchestrator`, and immutable storage APIs).
- **Normalized Match Default Rules**: By default, `normalized_match` applies Unicode NFC normalization, leading/trailing whitespace trimming, collapsing consecutive whitespace runs to a single space, case-insensitive folding, and punctuation preservation (`strip_punctuation = False`), with case-sensitivity and punctuation stripping configurable via metric options (reflected in `config_snapshot` / `metric_version`).
- **JSON Schema Validation Input Contract**: `json_schema_validation` resolves the expected JSON Schema in priority order (`criteria.json_schema`, then `reference` if it is a JSON Schema mapping, then metric-level default schema if configured) and treats an absent schema as `NOT_APPLICABLE`.
- **Run Identifier Uniqueness**: `EvaluationOrchestrator` generates globally unique `run_id` identifiers (timestamp plus unique entropy suffix) unless explicitly supplied by the caller; explicit caller-supplied `run_id` collisions against committed `.evalforge/runs/<run_id>.json` fail via the immutability guard.
- **Checkpoint Cleanup Policy**: Successfully committed runs delete `.evalforge/tmp/<run_id>.jsonl` by default upon atomic commit of `.evalforge/runs/<run_id>.json` (configurable retention option permitted), whereas aborted or crashed runs retain `.evalforge/tmp/<run_id>.jsonl` strictly for diagnostic inspection; automatic mid-run resume/replay is deferred outside Milestone 001.
- **Governance & Quality Verification Baseline**: All Milestone 001 components remain subject to the project constitution's automated library-purity, API stability, static analysis, branch coverage, determinism, and immutability verification gates during implementation planning and delivery.
