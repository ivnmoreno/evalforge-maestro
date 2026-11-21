# Feature Specification: Milestone 2 — Retrieval & RAG Evaluation

**Feature Branch**: `002-retrieval-rag-evaluation`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Start Milestone 2: Retrieval & RAG Evaluation (002-retrieval-rag-evaluation) per docs/intent.md Sections 5.2 (M2), 5.4, 6.1, 6.2, 6.3, 7.1, 8.2, and 8.3: protocol-based RAGAdapter with configurable dict/object field extractors, optional lazy-imported DocpipeAdapter behind the [docpipe-maestro] extra (wrapping retrieve() and answer_detailed(), plus docpipe fixture import), deterministic IR metrics (precision_at_k, recall_at_k, mrr, ndcg_at_k, hit_rate_at_k with binary and graded integer relevance and NOT_APPLICABLE safety when |G| == 0), and decoupled retrieval vs. answer evaluation."

## Clarifications

### Session 2026-11-18

- Q: What default pass thresholds should the five deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and `hit_rate_at_k`) use when a caller does not specify a custom threshold? → A: Default `hit_rate_at_k` to `1.0` and default `precision_at_k`, `recall_at_k`, `mrr`, and `ndcg_at_k` to `0.5`, overridable via metric `threshold` or `CaseCriteria`.
- Q: How should the IR metrics match retrieved chunks against ground-truth identifiers when ground truth may reference either specific chunk IDs (`chunk.id`) or parent document IDs (`chunk.parent_id`)? → A: Match strictly on `chunk.id` by default (`match_parent_id = False`) and support opt-in `match_parent_id = True` to match and deduplicate on `chunk.parent_id or chunk.id`.
- Q: How should the IR metrics determine the effective chunk ordering when `ExecutionResult.retrieved_chunks` contains explicit `rank` values that differ from list position order? → A: Sort stably by `(chunk.rank if chunk.rank is not None else original_index + 1, original_index)` prior to deduplication and `@K` cutoffs.
- Q: How should `DocpipeAdapter` invoke `docpipe-maestro` targets when evaluating either retrieval-only pipelines or full RAG pipelines? → A: Support an explicit `mode` parameter (`"answer_detailed"` default or `"retrieve"`) accepting either an injected target/client or lazy `docpipe_maestro` module resolution with pass-through collection/query options.
- Q: Should importing `docpipe-maestro` evaluation fixture files work purely from JSON or JSONL files without requiring `docpipe_maestro` to be installed, and which input shapes should it accept? → A: Load fixtures purely from JSON/JSONL without requiring `docpipe_maestro`, supporting JSONL streams, JSON arrays, and `{"queries": [...]}` (`EvalFixture`) / `{"cases": [...]}` / `{"items": [...]}` envelope objects into `DatasetEngine` (generating deterministic 1-based `case-{index}` IDs when entries omit `id`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Score Ordered Retrieval Results with Deterministic IR Metrics (Priority: P1)

An AI/ML engineer evaluates retrieved context chunks (`ExecutionResult.retrieved_chunks`) against ground-truth relevant context expectations (`EvaluationCase.expected_context`) using five versioned deterministic Information Retrieval (IR) metrics: `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and `hit_rate_at_k`. Both binary relevance sets and graded integer relevance weights are supported, and cases lacking ground-truth relevant chunks cleanly report `NOT_APPLICABLE` instead of failing with division-by-zero or `NaN`.

**Why this priority**: Silent retrieval failures are a primary failure mode in RAG systems. Deterministic, reproducible IR metrics provide the zero-cost verification layer required to prove whether a retriever surfaces the right evidence at the right ranks.

**Independent Test**: Can be fully tested by passing constructed `EvaluationCase` and `ExecutionResult` pairs directly to each IR metric and verifying exact mathematical outputs across empty ground truth, empty retrieval, duplicate chunks, graded relevance rankings, and rank cutoffs (`K`).

**Acceptance Scenarios**:

1. **Given** an `EvaluationCase` with ground-truth relevant chunk identifiers `G_pos` (`|G_pos| > 0`, where items have positive integer relevance) and an `ExecutionResult` with ordered `retrieved_chunks` $R$, **When** `precision_at_k`, `recall_at_k`, `hit_rate_at_k`, `mrr`, and `ndcg_at_k` evaluate the case, **Then** each emits a bounded `MetricResult` rounded to 6 decimal places matching canonical IR definitions (`|R_1..K ∩ G_pos| / K`, `|R_1..K ∩ G_pos| / |G_pos|`, `1.0`/`0.0`, `1 / rank_1`, and `DCG@K / IDCG@K`).
2. **Given** an `EvaluationCase` specifying graded integer relevance weights (`rel_i >= 0`) across expected context items, **When** `ndcg_at_k` evaluates the ordered retrieved chunks, **Then** ideal discounted cumulative gain (`IDCG@K`) orders all known graded relevant items optimally and `NDCG@K` scores rank ordering accurately within `[0.0, 1.0]`.
3. **Given** an error-free `ExecutionResult` paired with an `EvaluationCase` having empty or absent `expected_context` or all-zero relevance weights (`|G_pos| == 0`), **When** any of the five IR metrics runs, **Then** it returns `score = None` with `status = NOT_APPLICABLE` and a clear explanation rather than dividing by zero or emitting `0.0` or `NaN` (while non-empty `ExecutionResult.errors` takes precedence and emits `INCONCLUSIVE`).
4. **Given** an `ExecutionResult` whose retrieved list contains duplicate chunk identifiers or zero retrieved chunks while `|G_pos| > 0`, **When** IR metrics score the case, **Then** empty retrieval scores `0.0` (`FAIL`), and duplicate retrieved chunk identifiers do not inflate intersection counts past unique relevant matches.

---

### User Story 2 - Adapt Arbitrary RAG Pipelines via Configurable `RAGAdapter` (Priority: P2)

An engineer wraps any synchronous or asynchronous RAG system—without adopting third-party orchestration frameworks—inside `RAGAdapter` using configurable dictionary-key, object-attribute, or callable extractors. The adapter maps target outputs, ordered retrieved chunks (`id`, `text`, `parent_id`, `rank`, `score`, `metadata`), optional token usage, system/config fingerprints, and runtime errors into a standard `ExecutionResult`.

**Why this priority**: Real RAG pipelines vary widely in return shapes (plain mappings, custom dataclasses, SDK response objects). A flexible protocol-based adapter lets `evalforge_maestro` evaluate any RAG runtime without forcing application code changes.

**Independent Test**: Can be fully tested by wrapping sync and async stub RAG callables returning dictionaries and custom attribute objects with configured extractors and verifying normalized `ExecutionResult` payloads, latency tracking, error isolation, and secret redaction.

**Acceptance Scenarios**:

1. **Given** a synchronous or asynchronous RAG callable returning either a mapping or an object with custom field names for answer text, retrieved chunks, chunk identifiers, texts, scores, parent IDs, and token counts, **When** `RAGAdapter` executes an `EvaluationCase`, **Then** all extracted fields normalize cleanly into `ExecutionResult.output`, ordered `ExecutionResult.retrieved_chunks`, and `ExecutionResult.tokens` alongside `elapsed_seconds` and redacted `config_fingerprint`.
2. **Given** a target RAG callable returning retrieved chunks without explicit numeric `rank` values, **When** `RAGAdapter` normalizes `retrieved_chunks`, **Then** 1-based rank positions (`1, 2, ...`) are assigned automatically in returned order.
3. **Given** a target RAG callable that raises an exception, returns unextractable chunk payloads, or lacks optional chunk fields (`parent_id`, `score`, `metadata`), **When** `RAGAdapter` executes under `EvaluationOrchestrator`, **Then** missing optional chunk metadata defaults cleanly, while unhandled runtime or extraction errors are captured inside `ExecutionResult.errors` so dependent IR and answer metrics mark `INCONCLUSIVE` without crashing the batch.

---

### User Story 3 - Decouple Retrieval Quality from Answer Quality in Multi-Metric Runs (Priority: P3)

An engineer runs a single `EvaluationOrchestrator` batch combining deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) and answer metrics (`exact_match`, `normalized_match`, `json_schema_validation`) over the same `ExecutionResult` records. Cases where a model answers accurately from pretrained knowledge despite bad retrieval—or retrieves relevant context yet produces a wrong answer—are scored independently so neither dimension hides the other.

**Why this priority**: Evaluating final answer text alone hides silent retrieval failures; evaluating retrieval and answer evidence independently from the same trace is a core promise of EvalForge Maestro.

**Independent Test**: Can be fully tested by running `EvaluationOrchestrator` over a multi-case RAG dataset containing (a) right answer + wrong retrieval, (b) right retrieval + wrong answer, and (c) mandatory case retrieval failure, verifying independent `MetricResult` outcomes, decoupled aggregates, and preserved mandatory failure flags.

**Acceptance Scenarios**:

1. **Given** a case where `RAGAdapter` produces an exact match final output alongside completely irrelevant `retrieved_chunks`, **When** `EvaluationOrchestrator` runs both `exact_match` and `precision_at_k`/`recall_at_k`, **Then** `exact_match` scores `1.0` (`PASS`) while retrieval metrics score `0.0` (`FAIL`) on that exact same `CaseEvaluationRecord`.
2. **Given** a case where `RAGAdapter` returns relevant `retrieved_chunks` alongside an incorrect or malformed final output, **When** `EvaluationOrchestrator` evaluates both retrieval and answer metrics, **Then** retrieval metrics score `PASS` (`> 0.0` meeting threshold) while answer metrics score `0.0` (`FAIL`).
3. **Given** a dataset where a mandatory case (`criteria.mandatory = True`) passes answer matching but fails a retrieval metric (`status = FAIL`), **When** `RunRecord` summaries are committed, **Then** `RunRecord.has_mandatory_failures` is `True` and `mandatory_failed_case_ids` includes that case so aggregate scores never mask mandatory retrieval failures.

---

### User Story 4 - Integrate Optional `docpipe-maestro` Pipelines and Evaluation Fixtures Safely (Priority: P4)

An engineer using `docpipe-maestro` evaluates either retrieval-only pipelines (`retrieve()`) or full RAG pipelines (`answer_detailed()`) via an optional `DocpipeAdapter` and imports existing `docpipe-maestro` evaluation fixture files into `EvaluationCase` streams. Core installations without the `[docpipe-maestro]` extra incur zero cold-start import overhead and receive a clear `MissingExtraError` install hint only if `DocpipeAdapter` is instantiated without `docpipe_maestro` available.

**Why this priority**: Providing first-class integration with `docpipe-maestro` demonstrates clean separation between a RAG runtime and its independent verification engine while keeping core installs minimal and dependency-clean.

**Independent Test**: Can be fully tested by simulating `docpipe_maestro` pipelines (`retrieve()` and `answer_detailed()`), importing sample `docpipe-maestro` evaluation fixtures via `DatasetEngine` / fixture loader, and running an isolated check verifying `MissingExtraError` when `docpipe_maestro` is absent and zero eager imports on package startup.

**Acceptance Scenarios**:

1. **Given** a `docpipe-maestro` pipeline supporting `retrieve()` or `answer_detailed()`, **When** `DocpipeAdapter` executes an `EvaluationCase` in retrieval-only or full-RAG mode, **Then** retrieved documents normalize into `ExecutionResult.retrieved_chunks` (and generated answers/tokens populate `output`/`tokens` in `answer_detailed` mode while leaving `output = None` in `retrieve` mode so retrieval metrics score and answer metrics report `NOT_APPLICABLE` or appropriate status).
2. **Given** an existing `docpipe-maestro` evaluation fixture file (JSONL, JSON array, or `{"cases": [...]}`/`{"items": [...]}` envelope) in an environment with or without `[docpipe-maestro]` installed, **When** loaded through the `docpipe` fixture importer into `DatasetEngine`, **Then** records convert cleanly into validated `EvaluationCase` streams with canonical SHA-256 dataset fingerprints without requiring `docpipe_maestro`.
3. **Given** an environment where `docpipe_maestro` is not installed, **When** `evalforge_maestro` is imported or Milestone 001 / core IR workflows run, **Then** zero import errors occur and `docpipe_maestro` is never loaded; attempting to instantiate `DocpipeAdapter` raises `MissingExtraError` referencing the `[docpipe-maestro]` optional extra.

---

### Edge Cases

- What happens when `K <= 0` is configured on `precision_at_k`, `recall_at_k`, `hit_rate_at_k`, or `ndcg_at_k`? Metric initialization MUST raise an explicit `MetricError` rather than dividing by zero or producing meaningless cutoffs.
- What happens when `|R| < K` (the retriever returns fewer than `K` chunks)? `Precision@K` MUST keep `K` as its denominator (`|R_1..K ∩ G_pos| / K`, penalizing under-retrieval per canonical IR definition), while `DCG@K` sums up to `min(K, |R|)` and `IDCG@K` sums up to `min(K, |G_pos|)` where `G_pos` contains ground-truth items with positive relevance.
- What happens when `retrieved_chunks` contains duplicate chunk IDs in $R$? IR metrics MUST deduplicate $R$ while preserving first-seen rank order (keeping the highest rank position of each unique chunk ID) so repeating one relevant chunk cannot artificially inflate `Precision@K`, `Recall@K`, or `DCG@K`.
- What happens when `EvaluationCase.expected_context` mixes plain string IDs and structured expected-context items (with optional graded integer weights `relevance`)? Boundary schema validation MUST support both shapes uniformly while rejecting negative or non-integer relevance weights and duplicate expected-context IDs within a single case.
- What happens when `ExecutionResult.retrieved_chunks` has chunk text exceeding `max_context_chars`? Consistent with Milestone 001 post-scoring truncation, IR metrics MUST score against full chunk IDs/metadata before persistence truncates oversized `RetrievedChunk.text` fields and sets `ExecutionResult.truncated = True`.
- What happens when `DocpipeAdapter` is imported inside `evalforge_maestro.adapters` when `docpipe_maestro` is missing? Importing `evalforge_maestro` or `evalforge_maestro.adapters` MUST NOT fail or import `docpipe_maestro` eagerly; `docpipe_maestro` MUST be lazy-imported only when `DocpipeAdapter` executes or resolves its client.
- What happens when a batch evaluates retrieval metrics alongside `exact_match` on a `retrieve()`-only `DocpipeAdapter` (`output = None`, `errors = []`)? If `case.reference` is `None`, `exact_match` returns `NOT_APPLICABLE`; if `case.reference` is a non-empty string while `output = None` in `retrieve` mode, `exact_match` scores `0.0` (`FAIL`), reflecting that a retrieval-only pipeline did not produce an answer.

## Requirements *(mandatory)*

### Scope Boundaries

- **In Scope (002-retrieval-rag-evaluation):**
  - Extended `EvaluationCase.expected_context` structured relevance contract (`ExpectedContextItem` alongside string ID compatibility) in the canonical schema module (`types.py`).
  - Five versioned deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) with formal metadata declarations, `K >= 1` validation, binary and graded integer relevance support, duplicate-chunk deduplication, and `NOT_APPLICABLE` / `INCONCLUSIVE` guards.
  - Protocol-based `RAGAdapter` supporting sync/async targets and configurable dict-key, attribute-path, or callable field extractors mapping outputs, `retrieved_chunks`, and `tokens` into `ExecutionResult`.
  - Optional lazy-imported `DocpipeAdapter` (behind the `[docpipe-maestro]` optional extra) supporting `retrieve()` and `answer_detailed()` pipeline interfaces plus `docpipe-maestro` evaluation fixture conversion into `DatasetEngine`.
  - Decoupled multi-metric execution of retrieval and answer metrics from a single `ExecutionResult`, preserving mandatory-case failure visibility.
- **Explicitly Out of Scope (Deferred to Milestones 003–005 / Excluded Permanently):**
  - Baseline pinning/comparison, sliding trend windows, cross-metric disagreement anomaly detection (`> 0.3` divergence engine), and `QualityGate` -> Milestone `003`.
  - LLM-as-a-judge retrieval/groundedness metrics, LiteLLM routing, `--mock` judge mode, and calibration -> Milestone `004`.
  - Full CLI subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`) and Markdown report generation -> Milestone `005`.
  - Document parsing, text chunking, index embedding generation, vector database management, or executing production retrieval inside core evaluation engines -> Permanently excluded per Constitution Principle I.

### Functional Requirements

#### Canonical Retrieval Evidence Contracts & Purity

- **FR-001**: System MUST extend the single canonical schema source (`types.py`) to support `expected_context` entries as either ground-truth chunk identifier strings or typed `ExpectedContextItem` contracts (`id`, optional `text`, optional non-negative integer `relevance` defaulting to `1`), rejecting blank IDs, negative relevance weights, or duplicate expected chunk IDs within a single case.
- **FR-002**: System MUST maintain strict library purity across Milestone 002 modules: core and domain modules (`types`, `datasets`, `execution`, `metrics`, `storage`) MUST NEVER import concrete target adapters (`RAGAdapter`, `DocpipeAdapter`) or external RAG runtime packages (`docpipe_maestro`, `langchain`, `llama_index`), and `import evalforge_maestro` MUST keep `docpipe_maestro` unloaded on cold start.
- **FR-003**: System MUST declare `[docpipe-maestro]` as an optional installation extra (`docpipe-maestro`) and raise an explicit `MissingExtraError` (including installation instructions for `[docpipe-maestro]`) when `DocpipeAdapter` is used without `docpipe_maestro` installed.

#### Deterministic IR Metrics

- **FR-004**: System MUST implement five deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`), each exposing `MetricMetadata` (`metric_id`, pinned `metric_version`, required fields, calculation method, and known limitations), returning `MetricResult` scores bounded in `[0.0, 1.0]` rounded to 6 decimal places, defaulting `hit_rate_at_k` threshold to `1.0` and `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k` thresholds to `0.5`, resolving effective thresholds via `CaseCriteria.metric_thresholds[metric_id]` > `CaseCriteria.pass_threshold` > metric `threshold`, and pinning formula AST hashes per `metric_version`.
- **FR-005**: All five IR metrics MUST validate `k >= 1` (for K-parameterized metrics) at initialization (raising `MetricError` otherwise), order `ExecutionResult.retrieved_chunks` stably by `(chunk.rank if chunk.rank is not None else original_index + 1, original_index)`, resolve effective chunk identifier as `chunk.id` when `match_parent_id=False` (default) or `chunk.parent_id or chunk.id` when `match_parent_id=True` (recording `match_parent_id` in `config_snapshot`), and deduplicate by that effective identifier preserving first-seen rank order prior to calculation.
- **FR-006**: When `ExecutionResult.errors` is non-empty, all five IR metrics MUST return `score = None` with `status = INCONCLUSIVE` rather than scoring `0.0`; this guard MUST run before `NOT_APPLICABLE` checks so failed target executions are never masked as `NOT_APPLICABLE`.
- **FR-007**: When `ExecutionResult.errors` is empty and `EvaluationCase.expected_context` is absent or yields zero positively weighted relevant items (`|G_pos| == 0`, covering empty `expected_context` and all-zero `relevance == 0` weights), all five IR metrics MUST return `score = None` with `status = NOT_APPLICABLE` rather than dividing by zero or emitting `NaN` or `0.0`.
- **FR-008**: Exact deterministic calculations MUST hold across valid inputs (`|G_pos| > 0`, `ExecutionResult.errors == []`, deduplicated ordered list `R`):
  - `precision_at_k`: `|R[0:k] ∩ G_pos| / k`
  - `recall_at_k`: `|R[0:k] ∩ G_pos| / |G_pos|`
  - `hit_rate_at_k`: `1.0` if `|R[0:k] ∩ G_pos| > 0` else `0.0`
  - `mrr`: `1.0 / rank_1` where `rank_1` is the 1-based index of the first element in `R` belonging to `G_pos`, or `0.0` if none match
  - `ndcg_at_k`: `DCG@k / IDCG@k` where `DCG@k = sum_{i=1..min(k, |R|)} (2^{rel_i} - 1) / log2(i + 1)` and `IDCG@k` is the maximum achievable `DCG@k` over `G_pos` sorted by descending relevance weight.

#### Protocol-Based `RAGAdapter`

- **FR-009**: `RAGAdapter` MUST wrap any synchronous or asynchronous RAG target callable behind `TargetAdapter`, returning a validated `ExecutionResult` containing normalized `output`, ordered `retrieved_chunks` (`RetrievedChunk`), optional `tokens` (`TokenUsage`), `elapsed_seconds`, `errors`, `system_version`, `model_id`, and redacted `config_fingerprint`.
- **FR-010**: `RAGAdapter` MUST accept configurable field mapping rules (supporting dictionary keys, dotted attribute/key paths, or custom extractor callables) to extract answer output, retrieved chunk lists, chunk `id`, chunk `text`, `parent_id`, `rank`, `score`, `metadata`, and token usage from heterogeneous target return types.
- **FR-011**: When returned chunks lack explicit `rank` values, `RAGAdapter` MUST assign sequential 1-based ranks (`1, 2, ...`); when target invocation or field extraction fails on a case, `RAGAdapter` MUST capture the diagnostic inside `ExecutionResult.errors` cleanly without aborting remaining batch cases (unless `fail_fast` is enabled).

#### `DocpipeAdapter` & Fixture Integration

- **FR-012**: `DocpipeAdapter` MUST wrap `docpipe-maestro` collection/pipeline targets via lazy import, validating `mode` (`"answer_detailed"` default or `"retrieve"`, raising `AdapterError` otherwise) and accepting either an injected duck-typed client or lazy `docpipe_maestro` module resolution with pass-through options (`retrieve_kwargs` merged with explicit non-`None` `collection`/`persist_dir` taking precedence, plus `answer_kwargs` and redacted `config_fingerprint`). `DocpipeAdapter` MUST extract query strings from `str` inputs or mappings (`question` → `query` → `input`), normalizing `RetrievedChunk` entries with `output = None` in `"retrieve"` mode and normalized `output`, `TokenUsage`, `truncated`, and generation metadata/warnings in `"answer_detailed"` mode.
- **FR-013**: System MUST provide a dependency-free `docpipe` fixture loader/converter (operating purely on JSON/JSONL without requiring `docpipe_maestro` installed) supporting JSONL streams, JSON arrays, and `{"queries": [...]}` (`EvalFixture`) / `{"cases": [...]}` / `{"items": [...]}` envelope objects and translating `docpipe-maestro` fixture payloads (`question`/`query`/`input`, `relevant_ids`/`expected_ids`/`expected_context`, optional `relevance` weights, optional `reference`/`expected_answer`/`answer`, deterministic 1-based synthetic `case-{index}` IDs when `id`/`case_id` is omitted, and `collection`/`profile`/`notes` preserved in `CaseMetadata`) into validated `EvaluationCase` streams compatible with `DatasetEngine` and canonical SHA-256 fingerprinting.

#### Decoupled Evidence Evaluation & Orchestration

- **FR-014**: `EvaluationOrchestrator` MUST evaluate configured retrieval metrics and answer metrics independently over the same `ExecutionResult` for each case so a correct answer paired with irrelevant retrieved context fails retrieval metrics while passing answer metrics, and relevant context paired with a bad answer passes retrieval metrics while failing answer metrics.
- **FR-015**: Consistent with Milestone 001 post-scoring truncation, `EvaluationOrchestrator` MUST score retrieval and answer metrics against full active `ExecutionResult` fields before `max_context_chars` truncation trims stored `output` and `RetrievedChunk.text` fields for persistence.

### Key Entities *(include if feature involves data)*

- **`ExpectedContextItem`**: Typed ground-truth retrieval item on `EvaluationCase.expected_context`. Key attributes: `id` (non-empty chunk/document identifier), optional `text` snippet, and `relevance` (non-negative integer relevance weight defaulting to `1`).
- **`RetrievedChunk`** *(promoted from reserved to active in M2)*: Normalized retrieved evidence item on `ExecutionResult.retrieved_chunks`. Key attributes: `id`, `text`, optional `parent_id`, optional `rank` (`>= 1`), optional `score`, and redacted JSON-serializable `metadata`.
- **`RAGExtractorConfig`** *(or field-mapping configuration)*: Declarative mapping configuration specifying how `RAGAdapter` extracts answer output, chunk sequences, chunk fields (`id`, `text`, `parent_id`, `rank`, `score`, `metadata`), and token counts from dict or object responses.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All five deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) match hand-verified reference calculations across binary and graded integer relevance test cases to 6 decimal places in 100% of runs, and emit `NOT_APPLICABLE` (`score = None`) on 100% of error-free empty-ground-truth or all-zero-relevance cases (`|G_pos| == 0`).
- **SC-002**: Repeated evaluations with duplicate chunk identifiers in retrieved results never inflate `Precision@K`, `Recall@K`, or `NDCG@K` past unique relevant chunk matches across 100% of cases.
- **SC-003**: Heterogeneous synchronous and asynchronous RAG pipelines returning both mapping-based and attribute-based response objects execute cleanly through `RAGAdapter`, accurately normalizing `ExecutionResult.output`, ordered `retrieved_chunks`, and `tokens` across 100% of valid cases while isolating target/extraction failures cleanly into `ExecutionResult.errors`.
- **SC-004**: Single-run multi-metric batches evaluating both retrieval and answer metrics correctly decouple evidence from final outputs across 100% of test cases (passing answer / failing retrieval when context is irrelevant; passing retrieval / failing answer when generation is wrong) while preserving mandatory case failure visibility.
- **SC-005**: Importing `evalforge_maestro` or executing core/RAG workflows without `[docpipe-maestro]` installed succeeds with zero optional-dependency import errors and loads zero `docpipe_maestro` modules on cold start, while invoking `DocpipeAdapter` without `docpipe_maestro` raises an explicit `MissingExtraError` install hint 100% of the time.
- **SC-006**: Existing `docpipe-maestro` evaluation fixtures convert into validated `EvaluationCase` streams with deterministic SHA-256 dataset fingerprints, and simulated `retrieve()` / `answer_detailed()` pipelines normalize completely into immutable `RunRecord` artifacts.

## Assumptions

- **M1 Compatibility**: Milestone 002 builds strictly atop Milestone 001 contracts (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`, `DatasetEngine`, `EvaluationOrchestrator`, `LocalRunStore`) without breaking M1 schemas (`schema_version = "1.0"`) or existing M1 public API signatures.
- **Chunk Matching Basis**: By default (`match_parent_id = False`), all five IR metrics match and deduplicate on `RetrievedChunk.id` against ground-truth identifiers in `EvaluationCase.expected_context`; when `match_parent_id = True` is enabled on a metric, matching and deduplication use `chunk.parent_id or chunk.id`.
- **Default `k` Value**: K-parameterized IR metrics (`Precision@K`, `Recall@K`, `Hit Rate@K`, `NDCG@K`) default `k` to a standard positive integer cutoff (e.g., `k = 5`) unless overridden by the caller at metric initialization, and record `k` in `MetricResult.config_snapshot`.
- **Default Threshold for IR Metrics**: `hit_rate_at_k` defaults to `threshold = 1.0`, while `precision_at_k`, `recall_at_k`, `mrr`, and `ndcg_at_k` default to `threshold = 0.5`; all five honor overrides in order `CaseCriteria.metric_thresholds[metric_id]` > `CaseCriteria.pass_threshold` > metric `threshold`.
- **Docpipe Optional Dependency Boundary**: `docpipe_maestro` is never required for core installation or CI runs without `[docpipe-maestro]`; `DocpipeAdapter` uses lazy imports and clean interface testing against simulated/protocol-compatible `docpipe_maestro` doubles when the external package is absent.
