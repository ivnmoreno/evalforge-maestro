---

description: "Task list for Milestone 4 — Model-Based Judge & Calibration Engine"
---

# Tasks: Milestone 4 — Model-Based Judge & Calibration Engine

**Input**: Design documents from `specs/004-judge-calibration-engine/`
**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required), [research.md](research.md), [data-model.md](data-model.md), [contracts/public-api.md](contracts/public-api.md), [contracts/schemas-v1.json](contracts/schemas-v1.json)

**Tests**: Required by project constitution Principles II, III, IV, V, and VII (`tests/test_library_purity.py`, `tests/test_api_stability.py`, `tests/contract/test_m4_schemas.py`, hermetic unit/integration tests, and `@pytest.mark.gate_determinism`). Write test tasks first within each story phase so tests fail before implementation.

**Organization**: Tasks are grouped by user story in priority order (`US1` P1 MVP → `US2` P1 → `US4` P1 → `US3` P2) to enable independent implementation and verification of each increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps task to a user story in `spec.md` (`[US1]`, `[US2]`, `[US3]`, `[US4]`; Setup, Foundational, and Polish phases omit `[Story]`)
- Every task specifies exact repository-relative file paths and explicit `data-model.md` `Entity.field` citations where schema constraints apply

---

## Phase 1: Setup (Packaging & Subsystem Skeleton)

**Purpose**: Declare the optional `[judges]` extra, add judge/locality exceptions, and initialize the `judges/` package cleanly without disturbing minimal-core dependencies.

- [X] T001 Add optional `judges = ["litellm>=1.84.0"]` extra under `[project.optional-dependencies]` in `pyproject.toml` and refresh `uv.lock` verified across Python `3.10`–`3.13` markers while keeping core/default installs free of `litellm`
- [X] T002 [P] Add `JudgeError` and `LocalOnlyPolicyError` subclasses of `EvalforgeError` in `src/evalforge_maestro/exceptions.py`
- [X] T003 [P] Create `src/evalforge_maestro/judges/__init__.py` attaching strictly `logging.NullHandler()`

---

## Phase 2: Foundational (Canonical Schemas, Helpers & Contract Tests)

**Purpose**: Establish single-source M4 data contracts in `types.py`, credential text scrubbing, and schema/contract test harnesses BEFORE starting user stories.

**⚠️ CRITICAL**: No user story work can begin until Phase 2 is complete.

- [X] T004 [P] Add `round_percentage` (`[0.0, 100.0]`, 6 decimals) and `scrub_secret_text` (masking API key tokens, `Bearer` headers, and URL query credentials in diagnostic strings) in `src/evalforge_maestro/_canonical.py`
- [X] T005 Implement canonical M4 contracts in `src/evalforge_maestro/types.py` strictly per `data-model.md`: `CalibrationDisagreementType`, `JudgeConfig` (`JudgeConfig.schema_version`, `JudgeConfig.model`, `JudgeConfig.api_base`, `JudgeConfig.temperature`, `JudgeConfig.pass_threshold`, `JudgeConfig.max_retries`, `JudgeConfig.retry_backoff_seconds`, `JudgeConfig.timeout_seconds`, `JudgeConfig.local_only`, `JudgeConfig.mock_mode`, `JudgeConfig.seed`, `JudgeConfig.prompt_version`, `JudgeConfig.extra_params`, and computed `fingerprint`), `JudgeResponse` (`JudgeResponse.score`, `JudgeResponse.rationale`, `JudgeResponse.verdict`, `JudgeResponse.supported_claims`, `JudgeResponse.unsupported_claims`), `HumanCalibrationSample` (`HumanCalibrationSample.schema_version`, `HumanCalibrationSample.case_id`, `HumanCalibrationSample.input`, `HumanCalibrationSample.output`, `HumanCalibrationSample.reference`, `HumanCalibrationSample.retrieved_chunks`, `HumanCalibrationSample.human_score`, `HumanCalibrationSample.human_passed`, `HumanCalibrationSample.notes`, `HumanCalibrationSample.metadata`), `CalibrationDisagreement` (`CalibrationDisagreement.case_id`, `CalibrationDisagreement.disagreement_type`, `CalibrationDisagreement.human_score`, `CalibrationDisagreement.human_passed`, `CalibrationDisagreement.judge_score`, `CalibrationDisagreement.judge_status`, `CalibrationDisagreement.judge_passed`, `CalibrationDisagreement.score_delta`, `CalibrationDisagreement.judge_rationale`, `CalibrationDisagreement.human_notes`), `CalibrationReport` (`CalibrationReport.schema_version`, `CalibrationReport.metric_id`, `CalibrationReport.metric_version`, `CalibrationReport.judge_config`, `CalibrationReport.judge_config_fingerprint`, `CalibrationReport.total_cases`, `CalibrationReport.valid_cases`, `CalibrationReport.inconclusive_cases`, `CalibrationReport.pass_threshold_evaluated`, `CalibrationReport.human_threshold_evaluated`, `CalibrationReport.score_divergence_threshold`, `CalibrationReport.exact_agreement_rate`, `CalibrationReport.too_generous_rate`, `CalibrationReport.too_harsh_rate`, `CalibrationReport.mean_human_score`, `CalibrationReport.mean_judge_score`, `CalibrationReport.mean_score_delta`, `CalibrationReport.disagreements`, `CalibrationReport.recommended_pass_threshold`), and `@runtime_checkable` `AsyncBatchMetric` protocol (`metadata`, `judge_config_fingerprint`, `evaluate`, `aevaluate_batch`)
- [X] T006 [P] Extend `tests/unit/test_types.py` with tests covering all M4 model validators (bool/`NaN`/`Inf`/out-of-bounds rejection, `JudgeConfig.api_base` URL userinfo/query/fragment rejection, `JudgeConfig.extra_params` redaction and `fingerprint` stability, `HumanCalibrationSample` non-null `human_score`/`human_passed` invariant, and `CalibrationReport` count/nullable consistency)
- [X] T007 [P] Create `tests/contract/test_m4_schemas.py` validating M4 Pydantic runtime payloads against merged Draft 2020-12 definitions in `specs/004-judge-calibration-engine/contracts/schemas-v1.json`

**Checkpoint**: Foundational contracts and validation tests ready — User Story implementation can begin.

---

## Phase 3: User Story 1 — Provider-Independent Evidence-Aware Judges with Injection Isolation & `INCONCLUSIVE` Validation (Priority: P1) 🎯 MVP

**Goal**: Deliver five evidence-aware judge metrics (`groundedness`, `answer_relevance`, `context_relevance`, `answer_correctness`, `custom_rubric`) with randomized XML/nonce prompt-injection delimiters, strict JSON response validation, bounded transient retries, `NOT_APPLICABLE` handling on absent inputs, and deterministic `INCONCLUSIVE` fallback on invalid/malformed judge outputs.

**Independent Test**: Verified by executing judge metrics against injected `completion_fn` responses covering adversarial prompt-injection payloads (`</untrusted_target_output>` breakout attempts), valid decoupled RAG evidence scenarios (accurate answer + off-topic context), missing-reference/context `NOT_APPLICABLE` cases, upstream `ExecutionResult.errors`, and malformed/out-of-range JSON outputs verifying `max_retries` recovery and `INCONCLUSIVE` (`score = None`) fallback.

### Tests for User Story 1

> **NOTE: Write these tests FIRST and verify they fail before implementing US1 modules**

- [X] T008 [P] [US1] Write unit tests in `tests/unit/test_judge_provider.py` for prompt delimiter nonce randomization and breakout escaping, markdown-fenced and raw JSON extraction, strict `JudgeResponse` rejection of bool/`NaN`/`Inf`/`>1.0`/`<0.0`/empty-rationale outputs, retry recovery (`max_retries`), and `INCONCLUSIVE` (`score=None`) fallback on exhaustion
- [X] T009 [P] [US1] Write unit tests in `tests/unit/test_judge_metrics.py` covering all five judge metrics (`GroundednessMetric`, `AnswerRelevanceMetric`, `ContextRelevanceMetric`, `AnswerCorrectnessMetric`, `CustomRubricJudgeMetric` plus factory functions), formal `MetricMetadata`, RAG answer-vs-retrieval decoupling via injected `completion_fn`, missing-input `NOT_APPLICABLE`, `ExecutionResult.errors` -> `INCONCLUSIVE`, and `CaseCriteria` threshold overrides

### Implementation for User Story 1

- [X] T010 [US1] Implement randomized per-call delimiter generation (`secrets.token_hex`), tag-breakout neutralization, and safe prompt-block framing helpers in `src/evalforge_maestro/judges/security.py`
- [X] T011 [P] [US1] Implement versioned system anti-injection instructions and grading prompt templates for `groundedness`, `answer_relevance`, `context_relevance`, `answer_correctness`, and `custom_rubric` in `src/evalforge_maestro/judges/prompts.py`
- [X] T012 [US1] Implement strict JSON extractor, `JudgeResponse` parsing (`JudgeResponse.score`, `JudgeResponse.rationale`, `JudgeResponse.verdict`, `JudgeResponse.supported_claims`, `JudgeResponse.unsupported_claims` per `data-model.md`), retry loop (`JudgeConfig.max_retries`, `JudgeConfig.retry_backoff_seconds`), lazy `litellm.acompletion` adapter, and `INCONCLUSIVE` outcome normalization in `src/evalforge_maestro/judges/provider.py` (depends on T010)
- [X] T013 [US1] Implement `BaseJudgeMetric` (`Metric` sync `evaluate`, native async `aevaluate`, input presence `NOT_APPLICABLE` checks, `ExecutionResult.errors` short-circuit, `CaseCriteria` threshold resolution, `round_score` + `MetricStatus`, redacted `config_snapshot`, and composite `judge_config_fingerprint` hashing redacted `JudgeConfig` + `metric_id` + `metric_version` + prompt/rubric digest per `contracts/public-api.md`) in `src/evalforge_maestro/judges/base.py` (depends on T010, T011, T012)
- [X] T014 [US1] Implement `GroundednessMetric`, `AnswerRelevanceMetric`, `ContextRelevanceMetric`, `AnswerCorrectnessMetric`, `CustomRubricJudgeMetric` (validating non-empty `rubric`, `metric_id`, and `metric_version` via `MetricError`), and functional factories (`groundedness`, `answer_relevance`, `context_relevance`, `answer_correctness`, `custom_rubric_judge`) per `contracts/public-api.md` in `src/evalforge_maestro/judges/metrics.py` (depends on T013)

**Checkpoint**: User Story 1 is independently functional and verifiable via injected `completion_fn` tests without network access.

---

## Phase 4: User Story 2 — Deterministic Offline `--mock` Mode & Pre-Network `local_only` Security Enforcement (Priority: P1)

**Goal**: Deliver zero-API-key, network-free deterministic `--mock` evaluation (`mock_mode=True` with evidence-sensitive heuristics plus optional scripted mock overrides) alongside strict pre-network `local_only` loopback enforcement (`localhost`, `127.0.0.1`, `::1`, `LITELLM_LOCAL_MODEL_COST_MAP=True`), lazy `litellm` missing-extra hints, and zero-leak secret hygiene.

**Independent Test**: Verified by running mock judges across identical datasets under `tests/conftest.py` socket blocking (`@pytest.mark.gate_determinism`) asserting identical scores, RAG decoupling, and non-contamination by prompt nonces, plus asserting immediate `LocalOnlyPolicyError` pre-network rejection on cloud/LAN hosts, `LITELLM_LOCAL_MODEL_COST_MAP=True` injection before fake `litellm` import, and `MissingExtraError(extra="judges", package="litellm")` when `[judges]` is uninstalled.

### Tests for User Story 2

- [X] T015 [P] [US2] Write security unit tests in `tests/unit/test_judge_security.py` verifying pre-network `LocalOnlyPolicyError` on cloud models, non-loopback `api_base` hosts, `0.0.0.0`, and remote `OLLAMA_API_BASE` overrides; loopback permission (`localhost`, `127.0.0.1`, `::1`); `LITELLM_LOCAL_MODEL_COST_MAP=True` forced before lazy `litellm` import; `MissingExtraError(extra="judges", package="litellm")` when missing; and zero secret/`api_key` leakage across snapshots, fingerprints, errors, and logs
- [X] T016 [P] [US2] Extend `tests/unit/test_judge_metrics.py` with offline deterministic `--mock` tests covering `@pytest.mark.gate_determinism`, evidence-aware retrieval-failure vs hallucination decoupling, zero dependence on randomized prompt nonces, and scripted `mock_responses` overrides (including malformed->retry->`INCONCLUSIVE`)

### Implementation for User Story 2

- [X] T017 [US2] Implement pre-network `local_only` loopback endpoint validator (enforcing `JudgeConfig.local_only`, `JudgeConfig.mock_mode`, `JudgeConfig.api_base`, and `JudgeConfig.model` against `{localhost, loopback IP}` and `OLLAMA_API_BASE` per `data-model.md`), runtime credential isolation (`api_key` excluded from persisted configs/logs via `scrub_secret_text`), and `LITELLM_LOCAL_MODEL_COST_MAP=True` + `MissingExtraError(extra="judges", package="litellm")` lazy import guard in `src/evalforge_maestro/judges/security.py` and `src/evalforge_maestro/judges/provider.py`
- [X] T018 [US2] Implement evidence-aware deterministic mock judge scorer (normalized claim/token/coverage heuristics per rubric dimension plus scripted `mock_responses` sequence dispatch using `0.0s` sleep backoff, single-pass execution on heuristics/single-payload overrides, and retry sequences up to `JudgeConfig.max_retries` routed through `JudgeResponse` parser per `data-model.md`) in `src/evalforge_maestro/judges/mock.py` and integrate `mock_mode=True` execution cleanly into `src/evalforge_maestro/judges/base.py`

**Checkpoint**: User Stories 1 and 2 work cleanly end-to-end offline (`mock_mode`) and under enforced `local_only` security gates.

---

## Phase 5: User Story 4 — Calibrate Automated Judges Against Human Ground-Truth Labels (Priority: P1)

**Goal**: Provide `calibrate_judge` / `acalibrate_judge` diagnostics computing `exact_agreement_rate`, `too_generous_rate`, `too_harsh_rate`, `mean_human_score`, `mean_judge_score`, signed `mean_score_delta`, ordered per-case `CalibrationDisagreement` findings (including `> 0.25` `score_divergence` and `inconclusive`), and agreement-maximizing `recommended_pass_threshold` optimization.

**Independent Test**: Verified independently by passing `HumanCalibrationSample` sets simulating overly generous judges, overly harsh judges, perfectly calibrated judges, mixed numeric/binary human labels, `> 0.25` same-verdict score divergences, `INCONCLUSIVE` judge outputs, and threshold tie-breakers into `calibrate_judge` / `acalibrate_judge` and asserting exact `CalibrationReport` metrics and threshold recommendations.

### Tests for User Story 4

- [X] T019 [P] [US4] Write unit tests in `tests/unit/test_calibration.py` verifying `calibrate_judge` and `acalibrate_judge` on lenient/generous, strict/harsh, balanced, `score_divergence` (`> 0.25`), binary-only vs continuous `HumanCalibrationSample`, `INCONCLUSIVE` and zero-valid-pair cases, `EmptyDatasetError` / `DuplicateCaseIdError` / `ConfigurationError` validation, and deterministic threshold optimization tie-breakers

### Implementation for User Story 4

- [X] T020 [US4] Implement `acalibrate_judge` and `calibrate_judge` in `src/evalforge_maestro/judges/calibration.py` per `contracts/public-api.md` and `data-model.md`: consume and validate `HumanCalibrationSample` fields (`HumanCalibrationSample.schema_version`, `HumanCalibrationSample.case_id` with `EmptyDatasetError` / `DuplicateCaseIdError`, `HumanCalibrationSample.input`, `HumanCalibrationSample.output`, `HumanCalibrationSample.reference`, `HumanCalibrationSample.retrieved_chunks`, `HumanCalibrationSample.human_score`, `HumanCalibrationSample.human_passed` authoritative over `human_score` when both supplied, `HumanCalibrationSample.notes`, `HumanCalibrationSample.metadata`), construct `CalibrationDisagreement` (`CalibrationDisagreement.case_id`, `CalibrationDisagreement.disagreement_type` via `CalibrationDisagreementType`, `CalibrationDisagreement.human_score`, `CalibrationDisagreement.human_passed`, `CalibrationDisagreement.judge_score`, `CalibrationDisagreement.judge_status`, `CalibrationDisagreement.judge_passed`, `CalibrationDisagreement.score_delta`, `CalibrationDisagreement.judge_rationale`, `CalibrationDisagreement.human_notes`), run bounded concurrent evaluation, compute exact pass/fail verdict statistics and candidate threshold sweep optimization, and return `CalibrationReport` (`CalibrationReport.schema_version`, `CalibrationReport.metric_id`, `CalibrationReport.metric_version`, `CalibrationReport.judge_config`, `CalibrationReport.judge_config_fingerprint`, `CalibrationReport.total_cases`, `CalibrationReport.valid_cases`, `CalibrationReport.inconclusive_cases`, `CalibrationReport.pass_threshold_evaluated`, `CalibrationReport.human_threshold_evaluated`, `CalibrationReport.score_divergence_threshold`, `CalibrationReport.exact_agreement_rate`, `CalibrationReport.too_generous_rate`, `CalibrationReport.too_harsh_rate`, `CalibrationReport.mean_human_score`, `CalibrationReport.mean_judge_score`, `CalibrationReport.mean_score_delta`, `CalibrationReport.disagreements`, `CalibrationReport.recommended_pass_threshold`)

**Checkpoint**: User Stories 1, 2, and 4 complete — judges evaluate, enforce locality/mock safety, and calibrate cleanly against human labels.

---

## Phase 6: User Story 3 — Context-Grouped Bounded Async Concurrency, Fault Isolation & Orchestrator Provenance Fingerprinting (Priority: P2)

**Goal**: Enable bounded async judge batching grouped by canonical shared retrieved-context digest (preserving isolated per-case boundaries, `INCONCLUSIVE` single-case fault isolation, and original case order) cleanly integrated into `EvaluationOrchestrator.arun` with automatic redacted `RunRecord.judge_config_fingerprint` and `RunManifestEntry.judge_config_fingerprint` derivation.

**Independent Test**: Verified independently by running `aevaluate_batch` and end-to-end `EvaluationOrchestrator.arun` batches containing repeated shared contexts, injected concurrency trackers (`active <= max_concurrency`), single-case timeouts/errors, and two runs with altered judge rubric/model versions confirming automatic `RunRecord.judge_config_fingerprint` diffs trigger M3 `DriftCategory.JUDGE_CONFIG` and `METRIC_DISAGREEMENT` anomaly alerts in `QualityGate`.

### Tests for User Story 3

- [X] T021 [P] [US3] Extend `tests/unit/test_judge_metrics.py` with tests asserting `BaseJudgeMetric.aevaluate_batch` groups dispatch scheduling by canonical retrieved-context digest, enforces peak concurrency `<= max_concurrency`, isolates per-case exceptions/timeouts to `INCONCLUSIVE` without affecting sibling cases, and returns results in exact caller index order
- [X] T022 [P] [US3] Create `tests/integration/test_judge_pipeline.py` testing full `DatasetEngine` → `EvaluationOrchestrator` (deterministic + judge metrics) → `LocalRunStore` → `compare_runs` / `analyze_trend` / `QualityGate` → `calibrate_judge` pipelines, verifying automatic `RunRecord.judge_config_fingerprint` stamping, M3 `DriftCategory.JUDGE_CONFIG` + `METRIC_DISAGREEMENT` triggers, and `@pytest.mark.gate_determinism` repeatability

### Implementation for User Story 3

- [X] T023 [US3] Implement context-grouped bounded async scheduling (`aevaluate_batch`) using canonical retrieved-context digests, `asyncio.Semaphore(max_concurrency)`, isolated per-case execution, and original-order reassembly in `src/evalforge_maestro/judges/base.py`
- [X] T024 [US3] Extend `EvaluationOrchestrator.arun` in `src/evalforge_maestro/execution/orchestrator.py` to batch-dispatch `AsyncBatchMetric` implementations under `OrchestratorConfig.max_concurrency`, honor `fail_fast=True` across bounded chunks (aborting via `ExecutionError` cleanly on judge `INCONCLUSIVE`/zero-valid outcomes while preserving per-case `INCONCLUSIVE` isolation when `fail_fast=False`) alongside incremental checkpointing, and auto-derive redacted `RunRecord.judge_config_fingerprint` / `RunManifestEntry.judge_config_fingerprint` when not overridden by `OrchestratorConfig.judge_config_fingerprint`

**Checkpoint**: All 4 user stories (US1, US2, US4, US3) complete and integrated cleanly.

---

## Phase 7: Polish, Public API Pinning & Verification Gates

**Purpose**: Wire public exports, harden AST import/cold-start purity and signature pinning, update CI `[judges]` compatibility checks, and execute full verification suite.

- [X] T025 [P] Export M4 judge classes/factories and calibration functions in `src/evalforge_maestro/judges/__init__.py` and top-level M4 contracts, exceptions, judges, and calibration symbols in `src/evalforge_maestro/__init__.py`
- [X] T026 [P] Extend `tests/test_library_purity.py` to enforce AST import isolation on `src/evalforge_maestro/judges/` (forbidding `adapters`, `cli`, `tomllib`, `dotenv`, `datasets`, `storage`, `execution`, and asserting `types`/`_canonical`/`exceptions` never import `judges`) and cold-start / mock exclusion of `litellm` from `sys.modules`
- [X] T027 [P] Extend `tests/test_api_stability.py` to pin M4 `__all__` exports (`evalforge_maestro`, `evalforge_maestro.judges`), `JudgeError`/`LocalOnlyPolicyError` inheritance, public signatures (`BaseJudgeMetric`, 5 judge metrics/factories, `calibrate_judge`, `acalibrate_judge`), and M4 Pydantic model field sets
- [X] T028 [P] Extend `.github/workflows/ci.yml` with clean `--no-dev` minimal check asserting `"litellm" not in sys.modules` + `MissingExtraError(extra="judges", package="litellm")` message and an `optional-judges-compat` job verifying `--extra dev --extra judges` cold-start purity, `pip-audit`, and `LITELLM_LOCAL_MODEL_COST_MAP=True` air-gap safety
- [X] T029 Execute full verification suite (`ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`, `pytest -W error -m "gate_determinism or gate_immutability"`, `pytest -W error --cov=evalforge_maestro`, `100%` coverage gates on `metrics/` and `regression/gate.py`, `uv lock --check`, `pip-audit`, and `specs/004-judge-calibration-engine/quickstart.md` validation scenarios)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately — `T001` updates `pyproject.toml`/`uv.lock` while `T002` and `T003` run in parallel.
- **Foundational (Phase 2)**: Depends on Setup (`T002`, `T003`) — `T004` + `T005` create M4 helpers/types, enabling parallel validation tests `T006` and `T007`. **BLOCKS all user stories.**
- **User Story 1 (Phase 3, P1 MVP)**: Depends on Phase 2 — TDD tests `T008`–`T009` first, then `T010` + `T011` -> `T012` -> `T013` -> `T014`.
- **User Story 2 (Phase 4, P1)**: Depends on Phase 3 (`T010`, `T012`, `T013`) — tests `T015`–`T016` first, then `T017` -> `T018`.
- **User Story 4 (Phase 5, P1)**: Depends on Phase 3 & Phase 4 (can test cleanly once judges + offline mock run) — test `T019` first, then implement `T020`.
- **User Story 3 (Phase 6, P2)**: Depends on Phase 3 & Phase 4 (integrates `AsyncBatchMetric` in `base.py` and `orchestrator.py`) — tests `T021`–`T022` first, then `T023` + `T024`.
- **Polish (Phase 7)**: Depends on Phases 3–6 completion — `T025`–`T028` run in parallel, followed by final verification gate `T029`.

### Parallel Execution Examples

```bash
# Phase 2 parallel schema & helper tests after T005:
Task: "Extend tests/unit/test_types.py for M4 contracts (T006)"
Task: "Create tests/contract/test_m4_schemas.py against schemas-v1.json (T007)"

# Phase 3 (US1) TDD test batch + prompts/security setup:
Task: "Unit tests in tests/unit/test_judge_provider.py (T008)"
Task: "Unit tests in tests/unit/test_judge_metrics.py (T009)"
Task: "Anti-injection prompt templates in src/evalforge_maestro/judges/prompts.py (T011)"

# Phase 7 parallel exports, AST purity, API pinning, and CI hardening:
Task: "Public exports in src/evalforge_maestro/{judges/,}__init__.py (T025)"
Task: "AST & cold-start purity rules in tests/test_library_purity.py (T026)"
Task: "API & signature pinning in tests/test_api_stability.py (T027)"
Task: "CI optional-[judges] compatibility checks in .github/workflows/ci.yml (T028)"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 2)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational schemas/exceptions/contracts).
2. Complete Phase 3 (US1): Core 5 judge metrics, nonce isolation, strict `JudgeResponse` validation, `NOT_APPLICABLE`, and `INCONCLUSIVE` fallback.
3. Complete Phase 4 (US2): Offline deterministic `--mock` scoring + pre-network `local_only` enforcement + `LITELLM_LOCAL_MODEL_COST_MAP=True` air-gap safety.
4. **STOP & VALIDATE**: Offline mock and local-only judge suites pass hermetically with zero API keys.

### Full M4 Delivery

1. Add Phase 5 (US4): `calibrate_judge` / `acalibrate_judge` diagnostics + threshold optimization.
2. Add Phase 6 (US3): Context-grouped bounded concurrency + `EvaluationOrchestrator.arun` batch integration and automatic `judge_config_fingerprint` stamping.
3. Complete Phase 7: Top-level exports, purity/API/schema pinning, CI `[judges]` compatibility workflow, and run `T029` verification gates before PR merge.

---

## Notes

- All library modules under `src/evalforge_maestro/judges/` MUST emit telemetry/logs strictly via `logging.NullHandler()`, NEVER write to `stdout`, NEVER import `cli`/`tomllib`/`dotenv`/`adapters`/`execution`, and NEVER embed raw credentials in `JudgeConfig`, fingerprints, snapshots, or exceptions.
- Every task modifying public exports or schemas MUST preserve M1–M3 backward compatibility (`schema_version = "1.0"`) and pass `mypy --strict src tests`, `ruff check`, Bandit `ruff check --select S src/`, and `>=85%` branch coverage (`100%` on `metrics/` and `regression/gate.py`).
