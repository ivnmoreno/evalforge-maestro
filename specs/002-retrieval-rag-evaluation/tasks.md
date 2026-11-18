---

description: "Actionable, dependency-ordered task breakdown for Milestone 2: Retrieval & RAG Evaluation"
---

# Tasks: Milestone 2 — Retrieval & RAG Evaluation

**Input**: Design documents from `specs/002-retrieval-rag-evaluation/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required by project constitution Principles II, V, VI, and VII (AST library purity, cold-start lazy-import verification, API stability pinning, IR formula AST hash guards, `100%` branch coverage on `evalforge_maestro.metrics`, and `>=85%` overall branch coverage).

**Organization**: Tasks are grouped by user story (`US1`–`US4`) so each increment is independently implementable and testable in priority order (`P1` → `P4`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: Maps task to a specific user story (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Exact file paths and canonical `data-model.md` (`Entity.field`) citations are included where applicable

## Path Conventions

- Single Python package layout at repository root: `src/evalforge_maestro/` and `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configure optional `[docpipe]` packaging extra and lockfile metadata without polluting minimal core installs

- [X] T001 Add `[project.optional-dependencies]` extra `docpipe = ["docpipe-maestro>=0.2"]` to `pyproject.toml` and re-lock `uv.lock` while keeping core `uv sync --extra dev` isolated from `docpipe_maestro`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend single-source contracts in `types.py` for graded expected context, active chunk constraints, and declarative RAG extractors

**⚠️ CRITICAL**: No user story work begins until Phase 2 completes

- [X] T002 Add `ExpectedContextItem` model, enforce duplicate-ID and blank-ID validation on `EvaluationCase.expected_context` (`list[str | ExpectedContextItem] | None`), and tighten `RetrievedChunk` constraints (`rank >= 1`, finite non-bool `score`) in `src/evalforge_maestro/types.py` citing `data-model.md` (`ExpectedContextItem.id`, `ExpectedContextItem.text`, `ExpectedContextItem.relevance`, `EvaluationCase.expected_context`, `RetrievedChunk.id`, `RetrievedChunk.text`, `RetrievedChunk.parent_id`, `RetrievedChunk.rank`, `RetrievedChunk.score`, `RetrievedChunk.metadata`)
- [X] T003 Add `RAGExtractorConfig` model in `src/evalforge_maestro/types.py` citing `data-model.md` (`RAGExtractorConfig.output`, `RAGExtractorConfig.chunks`, `RAGExtractorConfig.chunk_id`, `RAGExtractorConfig.chunk_text`, `RAGExtractorConfig.chunk_parent_id`, `RAGExtractorConfig.chunk_rank`, `RAGExtractorConfig.chunk_score`, `RAGExtractorConfig.chunk_metadata`, `RAGExtractorConfig.tokens`)
- [X] T004 [P] Extend `tests/unit/test_types.py` with tests covering `ExpectedContextItem`, duplicate/blank/negative-relevance `EvaluationCase.expected_context` validation, `RetrievedChunk.rank >= 1` and finite `score`, `RAGExtractorConfig`, and JSON Schema parity combining `specs/001-evaluation-foundation/contracts/schemas-v1.json` with `specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json` (`ExpectedContextItem`, `EvaluationCaseExpectedContext`, `RetrievedChunk.rank >= 1`)

**Checkpoint**: Canonical Milestone 002 schemas ready — user stories (`US1`–`US4`) can proceed

---

## Phase 3: User Story 1 — Score Ordered Retrieval Results with Deterministic IR Metrics (Priority: P1) 🎯 MVP

**Goal**: Implement versioned `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and `hit_rate_at_k` metrics supporting binary/graded relevance, stable rank sorting, `match_parent_id`, duplicate deduplication, and `NOT_APPLICABLE`/`INCONCLUSIVE` guards

**Independent Test**: Pass `EvaluationCase` and `ExecutionResult` pairs directly to each IR metric verifying exact 6-decimal calculations, `|G_pos| == 0` (empty ground truth or all-zero relevance) `NOT_APPLICABLE`, `ExecutionResult.errors` `INCONCLUSIVE` taking precedence, duplicate chunk handling, out-of-order `rank` sorting, and `match_parent_id`

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [P] [US1] Write unit tests achieving 100% branch coverage on `PrecisionAtKMetric`, `RecallAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, and `HitRateAtKMetric` (binary and graded integer weights, `|G_pos| == 0` empty-ground-truth and all-zero-relevance `NOT_APPLICABLE`, empty retrieval, `|R| < k`, duplicate chunk ID deduplication, out-of-order `rank` sorting, `match_parent_id=False/True`, threshold defaults and `CaseCriteria` precedence, `ExecutionResult.errors` `INCONCLUSIVE` taking precedence over `|G_pos| == 0`, and `k < 1` / invalid threshold `MetricError`) in `tests/unit/test_ir_metrics.py`
- [X] T006 [P] [US1] Extend normalized AST formula hash pinning tests for `_prepare_retrieval_inputs`, `_score_precision_at_k`, `_score_recall_at_k`, `_score_hit_rate_at_k`, `_score_mrr`, and `_score_ndcg_at_k` in `tests/contract/test_metric_formulas.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement `PrecisionAtKMetric`, `RecallAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, and `HitRateAtKMetric` (with `_prepare_retrieval_inputs` stable sort on `(rank, original_index)`, `match_parent_id` projection, first-seen deduplication, `MetricMetadata` declarations, `metric_version = "1.0.0"`, `k >= 1` validation, `ExecutionResult.errors` `INCONCLUSIVE` check followed by `|G_pos| == 0` `NOT_APPLICABLE` guard, threshold defaults `1.0` for `hit_rate_at_k` and `0.5` for others with `CaseCriteria` precedence, and 6-decimal rounding) plus singleton exports in `src/evalforge_maestro/metrics/retrieval.py` citing `data-model.md` (`ExpectedContextItem.id`, `ExpectedContextItem.relevance`, `EvaluationCase.expected_context`, `RetrievedChunk.id`, `RetrievedChunk.parent_id`, `RetrievedChunk.rank`)
- [X] T008 [US1] Export `PrecisionAtKMetric`, `RecallAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, `HitRateAtKMetric`, `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and `hit_rate_at_k` per `contracts/public-api.md` in `src/evalforge_maestro/metrics/__init__.py`

**Checkpoint**: User Story 1 IR metrics are independently complete, version-pinned, and 100% branch-covered

---

## Phase 4: User Story 2 — Adapt Arbitrary RAG Pipelines via Configurable `RAGAdapter` (Priority: P2)

**Goal**: Wrap synchronous and asynchronous RAG targets behind `TargetAdapter` with configurable dotted-path/callable extractors normalizing `output`, ordered `RetrievedChunk` entries, `TokenUsage`, and redacted fingerprints

**Independent Test**: Wrap sync/async stub RAG callables returning dicts and custom attribute objects with configured/default extractors and verify `ExecutionResult` normalization, auto 1-based ranking, secret redaction, and per-case error isolation

### Tests for User Story 2

- [X] T009 [P] [US2] Write unit tests for `RAGAdapter` covering sync/async/awaitable targets, nested mapping and attribute extractors, callable extractors, default fallback resolution, auto 1-based rank assignment, optional `TokenUsage` normalization, secret redaction on chunk `metadata` and `config_fingerprint`, and extraction/target error isolation in `tests/unit/test_rag_adapter.py`

### Implementation for User Story 2

- [X] T010 [US2] Implement `RAGAdapter` conforming to `TargetAdapter` (sync via `asyncio.to_thread`, async/awaitable execution, `RAGExtractorConfig` dotted-path/callable extraction with default fallback keys, sequential 1-based auto-ranking when `rank` is omitted, `TokenUsage` mapping, secret redaction on `metadata` and `config`, and per-case error capture) in `src/evalforge_maestro/adapters/rag.py` citing `data-model.md` (`RAGExtractorConfig.output`, `RAGExtractorConfig.chunks`, `RAGExtractorConfig.chunk_id`, `RAGExtractorConfig.chunk_text`, `RAGExtractorConfig.chunk_parent_id`, `RAGExtractorConfig.chunk_rank`, `RAGExtractorConfig.chunk_score`, `RAGExtractorConfig.chunk_metadata`, `RAGExtractorConfig.tokens`, `RetrievedChunk.id`, `RetrievedChunk.text`, `RetrievedChunk.parent_id`, `RetrievedChunk.rank`, `RetrievedChunk.score`, `RetrievedChunk.metadata`)
- [X] T011 [US2] Export `RAGAdapter` per `contracts/public-api.md` in `src/evalforge_maestro/adapters/__init__.py`

**Checkpoint**: User Stories 1 and 2 enable end-to-end RAG evaluation with deterministic IR scoring

---

## Phase 5: User Story 3 — Decouple Retrieval Quality from Answer Quality in Multi-Metric Runs (Priority: P3)

**Goal**: Verify single-run evaluation across combined retrieval and answer metrics (`exact_match`, `normalized_match`, `json_schema_validation`), enforcing decoupled diagnostics, mandatory retrieval failure surfacing, and post-scoring chunk text truncation

**Independent Test**: Run `EvaluationOrchestrator` over multi-case RAG datasets containing (a) right answer + bad retrieval, (b) good retrieval + wrong answer, and (c) mandatory case retrieval failure + oversized chunk text truncation

### Tests for User Story 3

- [X] T012 [P] [US3] Write integration tests verifying independent retrieval vs. answer scoring on identical `ExecutionResult` records, mandatory retrieval failure propagation into `RunRecord.has_mandatory_failures` / `mandatory_failed_case_ids`, and post-scoring `max_context_chars` truncation preserving full IR chunk matching in `tests/integration/test_rag_decoupled_eval.py`

### Implementation for User Story 3

- [X] T013 [US3] Verify and refine `EvaluationOrchestrator` handling of combined IR + answer metrics, `RetrievedChunk.text` post-scoring truncation, and mandatory retrieval failure tracking in `src/evalforge_maestro/execution/orchestrator.py` (ensuring zero adapter imports and preserving M1 invariants)

**Checkpoint**: Decoupled retrieval and answer evaluation verified end-to-end

---

## Phase 6: User Story 4 — Integrate Optional `docpipe-maestro` Pipelines and Evaluation Fixtures Safely (Priority: P4)

**Goal**: Provide lazy-imported `DocpipeAdapter` (`mode="answer_detailed"` / `"retrieve"`, raising `MissingExtraError` when `[docpipe]` absent) and dependency-free `load_docpipe_fixture` / `DatasetEngine.from_docpipe_fixture` supporting real `docpipe-maestro` `EvalFixture` files

**Independent Test**: Test `DocpipeAdapter` with simulated `docpipe_maestro` doubles (`retrieve()` and `answer_detailed()`), confirm `MissingExtraError` when `docpipe_maestro` is absent, and import JSONL, JSON array, and `EvalFixture` `"queries"`/`"cases"`/`"items"` files without `docpipe_maestro` installed

### Tests for User Story 4

- [X] T014 [P] [US4] Write unit tests for `DocpipeAdapter` (`mode="retrieve"` and `mode="answer_detailed"` via injected `docpipe_maestro` doubles matching `RetrievedChunk` & `GenerationResult`, invalid `mode` `AdapterError`, `collection`/`persist_dir` precedence over `retrieve_kwargs`, `str`/dict `case.input` query extraction, redacted `config_fingerprint`, `MissingExtraError` when `docpipe_maestro` absent, error capture) and `load_docpipe_fixture` / `DatasetEngine.from_docpipe_fixture` (`"queries"` `EvalFixture`, `"cases"`/`"items"` envelopes, JSON array, JSONL, deterministic 1-based `case-{index}` synthetic IDs when omitted, `CaseMetadata` `collection`/`profile`/`notes` mapping, invalid payload errors, canonical SHA-256 fingerprint) in `tests/unit/test_docpipe_adapter.py`

### Implementation for User Story 4

- [X] T015 [P] [US4] Implement dependency-free `load_docpipe_fixture` supporting JSONL streams, JSON arrays, and `{"queries": [...]}` / `{"cases": [...]}` / `{"items": [...]}` envelopes (mapping `id`/`case_id` or deterministic 1-based `case-{index}`, `question`/`query`/`input`, `relevant_ids`/`expected_ids`/`expected_context`, optional `reference`/`expected_answer`/`answer`/`relevance`, and `CaseMetadata` `collection`/`profile`/`notes`) into `DatasetEngine` in `src/evalforge_maestro/datasets/docpipe_fixture.py` citing `data-model.md` (`EvaluationCase.expected_context`, `ExpectedContextItem.id`, `ExpectedContextItem.relevance`)
- [X] T016 [US4] Add `DatasetEngine.from_docpipe_fixture` classmethod in `src/evalforge_maestro/datasets/engine.py` and export `load_docpipe_fixture` per `contracts/public-api.md` in `src/evalforge_maestro/datasets/__init__.py`
- [X] T017 [P] [US4] Implement lazy `DocpipeAdapter` (validating `mode` with `AdapterError`, `case.input` `str`/mapping query extraction, explicit `collection`/`persist_dir` precedence over `retrieve_kwargs`, `mode="answer_detailed"` calling `retrieve()` + `build_chat_messages()`/`build_prompt()` + `answer_detailed()` mapping `ExecutionResult.output`/`TokenUsage`/`truncated`/`warnings`/`adapter_metadata`, `mode="retrieve"` calling `retrieve()` with `output=None`, raising `MissingExtraError(extra="docpipe", package="docpipe-maestro")` when `client is None` and `docpipe_maestro` missing, secret redaction & `config_fingerprint`) in `src/evalforge_maestro/adapters/docpipe.py` citing `data-model.md` (`RetrievedChunk.id`, `RetrievedChunk.text`, `RetrievedChunk.parent_id`, `RetrievedChunk.rank`, `RetrievedChunk.score`, `RetrievedChunk.metadata`)
- [X] T018 [US4] Export `DocpipeAdapter` per `contracts/public-api.md` in `src/evalforge_maestro/adapters/__init__.py` without eagerly importing `docpipe_maestro`
- [X] T019 [US4] Add end-to-end `DocpipeAdapter` + `load_docpipe_fixture` persistence integration tests (`retrieve` and `answer_detailed` runs saved to `LocalRunStore`) in `tests/integration/test_rag_decoupled_eval.py`

**Checkpoint**: All four Milestone 002 user stories are independently functional and cleanly isolated from `[docpipe]`

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Public API exports, library purity & cold-start enforcement, signature pinning, and full quality/packaging gate verification

- [X] T020 Export Milestone 002 public API (`ExpectedContextItem`, `RAGExtractorConfig`, `PrecisionAtKMetric`, `RecallAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, `HitRateAtKMetric`, `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`, `RAGAdapter`, `DocpipeAdapter`, `load_docpipe_fixture`) in `src/evalforge_maestro/__init__.py` and update `README.md` with Milestone 2 capabilities
- [X] T021 [P] Extend `tests/test_library_purity.py` to enforce zero `docpipe_maestro`, `langchain`, or `llama_index` imports in core/domain ASTs and cold-start `sys.modules` (confirming lazy-only import inside `DocpipeAdapter`)
- [X] T022 [P] Update `tests/test_api_stability.py` to pin Milestone 002 `__all__` exports and entrypoint signatures (`ExpectedContextItem`, `RAGExtractorConfig`, `PrecisionAtKMetric`, `RecallAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, `HitRateAtKMetric`, `RAGAdapter`, `DocpipeAdapter`, `load_docpipe_fixture`, `DatasetEngine.from_docpipe_fixture`) alongside Milestone 001 pins
- [X] T023 Run all Milestone 002 constitution verification gates (`uv lock --check`, `ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`, `pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85`, `100%` branch coverage on `evalforge_maestro.metrics`, `gate_determinism`/`gate_immutability`, `uv build` + `twine check --strict dist/*`, and `--no-dev` minimal install smoke test) and validate scenarios in `specs/002-retrieval-rag-evaluation/quickstart.md`
- [X] T024 Add GitHub Actions CI & OIDC TestPyPI/PyPI release workflows (`.github/workflows/ci.yml`, `.github/workflows/release.yml`), configure `pip-audit` + `commitizen` (`cz check`), add PyPI classifiers/`[project.urls]` metadata in `pyproject.toml`, and document SDK/PyPI/OIDC usage in `README.md`
- [X] T025 Explicitly clarify `M2`–`M5` CI, gate coverage, `--mock`/`--local-only`, CLI cold-start, and release scope in `docs/intent.md` and close defensive error-branch coverage across `tests/unit/test_rag_adapter.py` and `tests/unit/test_docpipe_adapter.py` (`96.19%` total branch coverage)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately (`T001`)
- **Phase 2 (Foundational)**: Depends on Phase 1 (`T002` → `T003`, then `T004`) — BLOCKS all user stories
- **Phase 3 (`US1`, P1 — MVP)**: Depends on Phase 2 (`T005`/`T006` in parallel → `T007` → `T008`)
- **Phase 4 (`US2`, P2)**: Depends on Phase 2 (`T009` → `T010` → `T011`)
- **Phase 5 (`US3`, P3)**: Depends on Phase 3 (`US1`) and Phase 4 (`US2`) (`T012` → `T013`)
- **Phase 6 (`US4`, P4)**: Depends on Phase 2 (`T014`/`T015`/`T017` in parallel → `T016`/`T018`), and Phase 5 (`T019` extends `test_rag_decoupled_eval.py` after `T012`)
- **Phase 7 (Polish & Gates)**: Depends on Phases 3–6 (`T020`, `T021`, `T022` → `T023`)

### Parallel Opportunities

- `T005` (`test_ir_metrics.py`) and `T006` (`test_metric_formulas.py`) run in parallel
- `US1` (`T005`–`T008`) and `US2` (`T009`–`T011`) can proceed in parallel after Phase 2 (`T002`–`T004`)
- In `US4`, `T014` (`test_docpipe_adapter.py`), `T015` (`datasets/docpipe_fixture.py`), and `T017` (`adapters/docpipe.py`) operate on distinct files and run in parallel
- `T021` (`test_library_purity.py`) and `T022` (`test_api_stability.py`) run in parallel after `T020`

### Parallel Example: User Story 1 & User Story 4

```bash
# User Story 1 parallel tests (after Phase 2):
Task T005: "tests/unit/test_ir_metrics.py"
Task T006: "tests/contract/test_metric_formulas.py"

# User Story 4 parallel implementation (after Phase 2):
Task T015: "src/evalforge_maestro/datasets/docpipe_fixture.py"
Task T017: "src/evalforge_maestro/adapters/docpipe.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (`T001`) and Phase 2 (`T002`–`T004`)
2. Complete Phase 3 (`US1`: `T005`–`T008`)
3. **STOP and VALIDATE**: Run `tests/unit/test_ir_metrics.py` and `tests/contract/test_metric_formulas.py` verifying 100% branch coverage across all 5 IR metrics

### Incremental Delivery

1. **Setup + Foundational (`T001`–`T004`)** → Canonical `ExpectedContextItem`, `RetrievedChunk`, and `RAGExtractorConfig` ready
2. **Add `US1` (`T005`–`T008`)** → Deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`)
3. **Add `US2` (`T009`–`T011`)** → Configurable protocol-based `RAGAdapter`
4. **Add `US3` (`T012`–`T013`)** → Verified decoupled retrieval vs. answer scoring
5. **Add `US4` (`T014`–`T019`)** → Lazy `DocpipeAdapter` & dependency-free `docpipe-maestro` fixture import
6. **Polish (`T020`–`T023`)** → Exports, AST purity, signature pinning, and full gate validation

---

## Notes

- All `[P]` tasks operate on distinct files with zero same-file race conditions
- All `data-model.md` constrained entity fields (`ExpectedContextItem.*`, `EvaluationCase.expected_context`, `RetrievedChunk.*`, `RAGExtractorConfig.*`) are explicitly cited in their implementing tasks
- Deferred milestones (`003` regression/trends/gates, `004` LLM judges/calibration, `005` CLI/Markdown reports) remain out of scope
