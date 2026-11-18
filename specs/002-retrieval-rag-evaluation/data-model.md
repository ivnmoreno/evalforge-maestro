# Data Model: Milestone 2 — Retrieval & RAG Evaluation

**Feature**: `002-retrieval-rag-evaluation` | **Date**: 2026-11-18 | **Schema Source**: `src/evalforge_maestro/types.py`

All Milestone 002 models extend `src/evalforge_maestro/types.py` while preserving backward compatibility with Milestone 001 `schema_version = "1.0"` contracts.

## New & Updated Core Contracts

### 1. `ExpectedContextItem`

Typed ground-truth relevance entry used inside `EvaluationCase.expected_context`.

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `id` | `str` | Yes | — | Non-empty after strip (`min_length=1`) |
| `text` | `str \| None` | No | `None` | Optional reference context snippet |
| `relevance` | `int` | No | `1` | Integer `>= 0` (rejects `bool` and `NaN`/`float`) |

### 2. `EvaluationCase` (M2 Refinement of `expected_context`)

| Field | Type | Required | Default | Validation Rules |
|---|---|---|---|---|
| `expected_context` | `list[str \| ExpectedContextItem] \| None` | No | `None` | String items stripped and required non-empty; duplicate effective `id` values within the same case raise validation error |

*(All other `EvaluationCase` fields from Milestone 001 remain unchanged.)*

### 3. `RetrievedChunk` (Promoted Active in M2)

| Field | Type | Required | Default | Validation Rules |
|---|---|---|---|---|
| `id` | `str` | Yes | — | Non-empty after strip |
| `text` | `str` | Yes | — | Chunk content (truncated post-scoring if `max_context_chars` set) |
| `parent_id` | `str \| None` | No | `None` | Optional parent section/document identifier |
| `rank` | `int \| None` | No | `None` | Integer `>= 1` when present (`RAGAdapter` assigns `1..N` when omitted) |
| `score` | `float \| None` | No | `None` | Finite float when present (rejects `bool`, `NaN`, `Inf`) |
| `metadata` | `dict[str, Any]` | No | `{}` | JSON-serializable, secret-redacted metadata |

### 4. `RAGExtractorConfig`

Declarative field-extraction configuration for `RAGAdapter` (`extra="forbid"`, `arbitrary_types_allowed=True`).

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `output` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` uses fallback keys/attrs `("output", "answer", "response")`; explicit path/callable is strict |
| `chunks` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` uses fallback keys/attrs `("retrieved_chunks", "chunks", "contexts", "documents")` |
| `chunk_id` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` uses fallback keys/attrs `("id", "chunk_id", "doc_id")` |
| `chunk_text` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` uses fallback keys/attrs `("text", "content", "page_content")` |
| `chunk_parent_id` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` checks `"parent_id"` / `"metadata.parent_id"` if present |
| `chunk_rank` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` checks `"rank"` if present (else auto-ranks `1..N`) |
| `chunk_score` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` checks `"score"` if present |
| `chunk_metadata` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` checks `"metadata"` if present |
| `tokens` | `str \| Callable[[Any], Any] \| None` | No | `None` | `None` checks `("tokens", "usage", "token_usage")` if present |

## IR Metric Configuration & Threshold Precedence

| Metric ID | Version | Default `k` | Default `match_parent_id` | Default `threshold` |
|---|---|---|---|---|
| `precision_at_k` | `"1.0.0"` | `5` (`>= 1`) | `False` | `0.5` |
| `recall_at_k` | `"1.0.0"` | `5` (`>= 1`) | `False` | `0.5` |
| `mrr` | `"1.0.0"` | N/A | `False` | `0.5` |
| `ndcg_at_k` | `"1.0.0"` | `5` (`>= 1`) | `False` | `0.5` |
| `hit_rate_at_k` | `"1.0.0"` | `5` (`>= 1`) | `False` | `1.0` |

Effective pass/fail threshold resolution inside every IR metric follows `CaseCriteria.metric_thresholds[metric_id] > CaseCriteria.pass_threshold > metric threshold`.

## State & Calculation Pipeline

```text
ExecutionResult (errors != [])   ────────▶ [errors present]──▶ MetricResult(score=None, status=INCONCLUSIVE)
                                         │
EvaluationCase.expected_context  ────────┴─▶ G_pos = {id: rel for id, rel in G if rel > 0}
                                               │
                                               ├─[|G_pos| == 0]──▶ MetricResult(score=None, status=NOT_APPLICABLE)
                                               │
ExecutionResult.retrieved_chunks ──────────────┴─▶ stable sort by (rank or idx+1, idx)
                                                     └─▶ map id = (parent_id or id) if match_parent_id else id
                                                     └─▶ deduplicate keeping first occurrence -> R
                                                     └─▶ compute IR score in [0.0, 1.0] (round 6) -> PASS | FAIL
```
