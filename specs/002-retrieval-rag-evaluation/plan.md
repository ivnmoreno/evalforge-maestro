# Implementation Plan: Milestone 2 — Retrieval & RAG Evaluation

**Branch**: `002-retrieval-rag-evaluation` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/002-retrieval-rag-evaluation/spec.md](spec.md)

## Summary

Milestone 002 adds retrieval and RAG evaluation atop Milestone 001's foundation: `ExpectedContextItem` and `RAGExtractorConfig` contracts in `types.py`; five pure deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) in `metrics/retrieval.py` with binary and graded integer relevance, rank sorting, `match_parent_id`, duplicate deduplication, and `NOT_APPLICABLE` / `INCONCLUSIVE` guards; protocol-based `RAGAdapter` supporting sync/async targets and configurable mapping/attribute/callable extractors; lazy-imported `DocpipeAdapter` behind `[docpipe-maestro]` wrapping `retrieve()` and `answer_detailed()`; and a dependency-free `docpipe-maestro` fixture loader (`load_docpipe_fixture` / `DatasetEngine.from_docpipe_fixture`).

## Technical Context

**Language/Version**: Python 3.10+ (verified locally on CPython 3.13.17; cross-OS target `ubuntu-latest`, `macos-latest`, `windows-latest`)

**Primary Dependencies**: Core dependencies remain strictly `pydantic>=2.7,<3` and `jsonschema>=4.23,<5`; `docpipe-maestro>=0.2` is added strictly as optional extra `[docpipe-maestro]` under `[project.optional-dependencies]` and lazy-imported only when `DocpipeAdapter` resolves `docpipe_maestro`

**Storage**: Reuses Milestone 001 `LocalRunStore` (`.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`, `.evalforge/tmp/<run_id>.jsonl`) with `RetrievedChunk` and `TokenUsage` actively populated on `ExecutionResult`

**Testing**: `pytest` with `--strict-markers`, `filterwarnings = ["error"]`, `>=85%` branch coverage overall (`100%` branch coverage across both `metrics/deterministic.py` and `metrics/retrieval.py`), normalized AST formula hash pins (`tests/contract/test_metric_formulas.py`), `tests/test_library_purity.py` (verifying `docpipe_maestro`/`langchain`/`llama_index` absent from core & cold-start `sys.modules`), `tests/test_api_stability.py` (pinned M1 + M2 signatures/`__all__`), and release gates

**Target Platform**: Local workstations and Linux/macOS/Windows CI runners (`Python 3.10+`)

**Project Type**: Standalone Python library / SDK (`src/evalforge_maestro/`)

**Performance Goals**: Pure-stdlib IR calculations (`math.log2`, `dict`/`set` intersections) with zero `numpy`/`scipy` overhead; zero extra cold-start import latency when `[docpipe-maestro]` is absent

**Constraints**: Strict unidirectional imports (`types`, `datasets`, `metrics`, `execution`, `storage` NEVER import `adapters` or `docpipe_maestro`), 6-decimal rounding, decoupled retrieval vs. answer scoring, mandatory case failure preservation

**Scale/Scope**: Milestone 002 covers `ExpectedContextItem`, 5 IR metrics, `RAGAdapter`, `DocpipeAdapter`, and `docpipe` fixture import; regression/trend/quality gates (`003`), LLM judges/LiteLLM (`004`), and CLI/Markdown reports (`005`) remain deferred

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design Status | Post-Design Verification | Notes |
|---|---|---|---|
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | Evaluates retrieval outputs without parsing documents, chunking text, generating embeddings, or managing vector DBs. `003`–`005` cleanly deferred. |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | `metrics/retrieval.py` and `datasets/docpipe_fixture.py` import only `types`, `exceptions`, `_canonical`, and stdlib; `DocpipeAdapter` sits in `adapters/` and lazy-imports `docpipe_maestro` with `MissingExtraError`. Cold-start test confirms `docpipe_maestro` never loaded on `import evalforge_maestro`. |
| **III. Single Schema Source of Truth** | PASS | PASS | `ExpectedContextItem`, `RAGExtractorConfig`, and refined `EvaluationCase.expected_context` & `RetrievedChunk` constraints live in `src/evalforge_maestro/types.py`. |
| **IV. Evidence-Aware & Anomaly-Safe** | PASS | PASS | IR metrics score `ExecutionResult.retrieved_chunks` independently of `ExecutionResult.output`; `ExecutionResult.errors` emits `INCONCLUSIVE` ahead of `\|G_pos\| == 0` `NOT_APPLICABLE`; mandatory retrieval failures surface in `RunRecord`. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | Deterministic stable rank sort `(rank, idx)`, duplicate chunk deduplication, 6-decimal rounding, and AST/source-hash formula pinning in `tests/contract/test_metric_formulas.py`. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | `NullHandler`-only logging; secret redaction applied to extracted chunk `metadata` and adapter config fingerprints; hermetic `autouse` isolation unchanged. |
| **VII. Automated Quality Gates** | PASS | PASS | Enforces `ruff` + Bandit `S` rules, `mypy --strict`, `filterwarnings=["error"]`, `>=85%` branch coverage (`100%` on `metrics/deterministic.py` and `metrics/retrieval.py`), and `uv lock --check`. |

## Project Structure

### Documentation (this feature)

```text
specs/002-retrieval-rag-evaluation/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 design & docpipe_maestro integration findings
├── data-model.md        # Phase 1 contracts for ExpectedContextItem, RetrievedChunk & RAGExtractorConfig
├── quickstart.md        # Phase 1 runnable validation scenarios & gate commands
├── contracts/
│   ├── public-api.md    # M2 public Python API signatures & exports
│   └── schemas-v1.json  # JSON Schema definitions for ExpectedContextItem & RetrievedChunk
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
pyproject.toml                                 # Add optional extra: docpipe-maestro = ["docpipe-maestro>=0.2"]
uv.lock                                        # Re-locked with optional docpipe extra metadata
src/
└── evalforge_maestro/
    ├── __init__.py                            # Re-export M2 IR metrics, adapters, ExpectedContextItem, RAGExtractorConfig, fixture loader
    ├── types.py                               # Add ExpectedContextItem, RAGExtractorConfig; refine EvaluationCase.expected_context & RetrievedChunk
    ├── datasets/
    │   ├── __init__.py                        # Export DatasetEngine, DatasetStreamResult, load_docpipe_fixture
    │   ├── engine.py                          # Add DatasetEngine.from_docpipe_fixture(...)
    │   └── docpipe_fixture.py                 # Dependency-free JSON/JSONL docpipe-maestro EvalFixture converter
    ├── adapters/
    │   ├── __init__.py                        # Export CallableAdapter, RAGAdapter, DocpipeAdapter
    │   ├── rag.py                             # Protocol-based RAGAdapter with configurable dotted-path/callable extractors
    │   └── docpipe.py                         # Lazy DocpipeAdapter wrapping docpipe_maestro retrieve() & answer_detailed()
    └── metrics/
        ├── __init__.py                        # Re-export M1 + M2 metrics & aliases
        └── retrieval.py                       # precision_at_k, recall_at_k, mrr, ndcg_at_k, hit_rate_at_k + MetricMetadata

tests/
├── test_library_purity.py                     # Extend AST & cold-start checks for docpipe_maestro / framework isolation
├── test_api_stability.py                      # Pin M2 __all__ exports & signatures alongside M1 contracts
├── unit/
│   ├── test_types.py                          # Extend tests for ExpectedContextItem, duplicate IDs, RAGExtractorConfig, RetrievedChunk bounds
│   ├── test_ir_metrics.py                     # 100% branch tests for all 5 IR metrics (binary/graded, |G_pos|=0, dupes, rank order, match_parent_id)
│   ├── test_rag_adapter.py                    # Sync/async RAGAdapter, dict/object extractors, auto-ranking, redaction, error isolation
│   └── test_docpipe_adapter.py                # DocpipeAdapter retrieve/answer_detailed doubles, MissingExtraError, fixture importer
├── integration/
│   └── test_rag_decoupled_eval.py             # Decoupled retrieval vs answer scoring, mandatory retrieval failure, post-score chunk truncation
└── contract/
    └── test_metric_formulas.py                # Pin AST source hashes for all 5 IR metric scoring functions & preprocessing helper
```

**Structure Decision**: Extends the existing Milestone 001 single-package `src/evalforge_maestro/` layout seamlessly while keeping all unidirectional module boundaries intact (`metrics/retrieval.py` and `datasets/docpipe_fixture.py` never import `adapters/` or `docpipe_maestro`; `DocpipeAdapter` isolates optional `[docpipe-maestro]` runtime imports behind lazy loading).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations. All 7 principles pass without exceptions.
