# Research & Architecture Decisions: Milestone 2 — Retrieval & RAG Evaluation

**Feature**: `002-retrieval-rag-evaluation` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## 1. Backward-Compatible Extension of `EvaluationCase.expected_context`

- **Decision**: Define `ExpectedContextItem` (`id: str`, `text: str | None = None`, `relevance: int = 1`) in `src/evalforge_maestro/types.py` and refine `EvaluationCase.expected_context` to `list[str | ExpectedContextItem] | None = None` with duplicate-ID rejection and whitespace-stripping validation.
- **Rationale**: Preserves 100% compatibility with Milestone 001 JSONL datasets and `schemas-v1.json` while supporting both simple ground-truth chunk ID lists and graded integer relevance weights required by `NDCG@K` (`FR-001`, `FR-008`). Rejecting `bool` values on `relevance` avoids `True`/`False` coercing to `1`/`0`.
- **Alternatives Considered**:
  - *Separate `expected_context_weights: dict[str, int]` field*: Rejected because splitting identifiers from relevance metadata complicates JSONL authoring and invites ID/key drift.

## 2. Deterministic IR Metric Purity, Ranking, Parent Matching & Deduplication

- **Decision**: Implement pure scoring functions (`_score_precision_at_k`, `_score_recall_at_k`, `_score_hit_rate_at_k`, `_score_mrr`, `_score_ndcg_at_k`) and shared canonical preprocessing (`_prepare_retrieval_inputs`) in `src/evalforge_maestro/metrics/retrieval.py`. Preprocess `ExecutionResult.retrieved_chunks` by (1) sorting stably on `(chunk.rank if chunk.rank is not None else idx + 1, idx)`, (2) projecting effective ID as `(chunk.parent_id or chunk.id)` when `match_parent_id=True` else `chunk.id`, and (3) deduplicating preserving first-seen rank order.
- **Rationale**: Enforces Clarification Q1–Q3 and `FR-004`–`FR-008` uniformly across all five IR metrics without duplicating ranking or deduplication logic. Isolating pure scoring functions enables normalized AST source-hash pinning in `tests/contract/test_metric_formulas.py` and 100% branch coverage without `numpy`/`scipy` dependencies.
- **Alternatives Considered**:
  - *Using `scikit-learn` or `ranx` for IR math*: Rejected per Constitution Principle I & II to keep core dependencies minimal and avoid heavy optional package imports on cold start.

## 3. Configurable Field Extraction in Protocol-Based `RAGAdapter`

- **Decision**: Define `RAGExtractorConfig` in `src/evalforge_maestro/types.py` accepting dotted path strings or callables (`str | Callable[[Any], Any] | None`) for answer output, chunk sequence, chunk fields (`id`, `text`, `parent_id`, `rank`, `score`, `metadata`), and token usage. When optional extractors are omitted (`None`), apply sensible fallback key/attribute resolution (`output` -> `answer` -> `response`; `retrieved_chunks` -> `chunks` -> `contexts` -> `documents`; `id` -> `chunk_id` -> `doc_id`; `text` -> `content` -> `page_content`; `tokens` -> `usage` -> `token_usage`). When an explicit extractor path or callable is configured, evaluate it strictly and capture missing/invalid extractions into `ExecutionResult.errors`.
- **Rationale**: Supports heterogeneous dict, dataclass, and Pydantic RAG outputs with zero framework lock-in (`FR-009`–`FR-011`) while isolating malformed payloads per case (`SC-003`).
- **Alternatives Considered**:
  - *Requiring users to subclass `TargetAdapter` for every RAG shape*: Rejected as unnecessarily verbose compared with declarative `RAGExtractorConfig`.

## 4. Real `docpipe-maestro` API Alignment, Lazy `[docpipe-maestro]` Extra & Fixture Import

- **Decision**: Align `DocpipeAdapter` (`src/evalforge_maestro/adapters/docpipe.py`) directly with `docpipe_maestro`'s real public API:
  - `mode="retrieve"` calls `retrieve(question, **retrieve_kwargs)` returning `list[docpipe_maestro.types.RetrievedChunk]` (`id`, `text`, `parent_id`, `metadata`, `score`), setting `ExecutionResult.output = None`.
  - `mode="answer_detailed"` retrieves sections via `retrieve(question, **retrieve_kwargs)`, constructs grounded messages via `build_chat_messages(question, sections)` (or `build_prompt` / direct query fallback on minimal injected clients), and calls `answer_detailed(prompt, has_context=bool(sections), **answer_kwargs)`, mapping `GenerationResult.text` -> `output`, token fields (`prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `total_tokens`) -> `TokenUsage`, and finish/truncation metadata cleanly into `adapter_metadata` / `warnings`.
  - Lazy-import `docpipe_maestro` inside `DocpipeAdapter.__init__` only when `client is None`, raising `MissingExtraError(extra="docpipe-maestro", package="docpipe-maestro")` when absent (`FR-003`, `FR-012`). Declare `docpipe-maestro = ["docpipe-maestro>=0.2"]` under `[project.optional-dependencies]` in `pyproject.toml`.
  - Implement dependency-free `load_docpipe_fixture` (`src/evalforge_maestro/datasets/docpipe_fixture.py`, also exposed via `DatasetEngine.from_docpipe_fixture(...)`) accepting real `docpipe_maestro` `EvalFixture` envelopes (`{"collection": ..., "profile": ..., "queries": [{"question": ..., "relevant_ids": [...], "notes": ...}]}`), JSON arrays, `cases`/`items` envelopes, and JSONL files without importing `docpipe_maestro`.
- **Rationale**: Guarantees seamless interoperability with `docpipe-maestro` (`>=0.2`) while ensuring `import evalforge_maestro` and minimal `--no-dev` installs never load `docpipe_maestro`, `chromadb`, or `litellm` at cold start.
- **Alternatives Considered**:
  - *Calling `answer_detailed(question)` directly without `retrieve()`*: Rejected because `docpipe_maestro.answer_detailed` expects a grounded prompt/messages payload built from `retrieve()` sections rather than performing vector search itself.
