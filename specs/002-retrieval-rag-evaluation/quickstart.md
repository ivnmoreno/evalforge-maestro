# Quickstart Validation Guide: Milestone 2 — Retrieval & RAG Evaluation

**Feature**: `002-retrieval-rag-evaluation` | **Date**: 2026-11-18
**References**: [spec.md](spec.md) | [data-model.md](data-model.md) | [public-api.md](contracts/public-api.md) | [schemas-v1.json](contracts/schemas-v1.json)

This guide defines end-to-end verification scenarios and gate commands for Milestone 002.

## Prerequisites

- Python `3.10+` inside `.venv` (`uv sync --extra dev`)
- Milestone 001 foundation tests passing (`evalforge_maestro`)
- Note: core test suites run **without** `[docpipe-maestro]` installed so cold-start isolation and `MissingExtraError` behavior are verified directly

## Scenario 1: Deterministic IR Metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`)

1. Evaluate `EvaluationCase` items containing binary chunk IDs and graded `ExpectedContextItem` weights (`relevance >= 0`) against ordered `ExecutionResult.retrieved_chunks`.
2. Verify rank-sorting (`(rank, original_index)`), duplicate chunk ID deduplication, `match_parent_id=False` vs. `match_parent_id=True`, threshold precedence (`metric_thresholds` > `pass_threshold` > metric default), and 6-decimal score rounding (`FR-004`–`FR-008`, `SC-001`, `SC-002`).
3. Verify non-empty `ExecutionResult.errors` returns `score = None` with `status = INCONCLUSIVE` (taking precedence over missing ground truth), while error-free cases with empty ground truth or all-zero relevance weights (`|G_pos| == 0`) return `score = None` with `status = NOT_APPLICABLE`.

## Scenario 2: Protocol-Based `RAGAdapter` & Decoupled Evidence Runs

1. Wrap synchronous and asynchronous RAG callables returning both nested dictionaries and attribute objects inside `RAGAdapter` using `RAGExtractorConfig`.
2. Execute a multi-case batch in `EvaluationOrchestrator` combining IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) and answer metrics (`exact_match`, `normalized_match`) (`FR-009`–`FR-015`, `SC-003`, `SC-004`).
3. Verify:
   - Correct answer + irrelevant context passes `exact_match` (`1.0`) and fails retrieval metrics (`0.0`).
   - Relevant context + incorrect answer passes retrieval metrics and fails `exact_match` (`0.0`).
   - Mandatory case (`criteria.mandatory = True`) failing retrieval surfaces in `RunRecord.has_mandatory_failures` / `mandatory_failed_case_ids`.
   - Post-scoring `max_context_chars` truncation preserves full IR scoring prior to truncating stored `RetrievedChunk.text`.

## Scenario 3: Optional `DocpipeAdapter`, Lazy Isolation & Fixture Importer

1. Import `evalforge_maestro` and `evalforge_maestro.adapters` without `docpipe_maestro` installed; verify `docpipe_maestro` does not appear in `sys.modules` and calling `DocpipeAdapter()` without `client=` raises `MissingExtraError` pointing to `[docpipe-maestro]` (`FR-002`, `FR-003`, `SC-005`).
2. Test `DocpipeAdapter(client=...)` in both `mode="retrieve"` and `mode="answer_detailed"` against simulated `docpipe_maestro` doubles matching `RetrievedChunk` and `GenerationResult` shapes (`FR-012`).
3. Import sample `docpipe-maestro` `EvalFixture` JSON (`queries` envelope), JSON array, and JSONL files via `load_docpipe_fixture` / `DatasetEngine.from_docpipe_fixture` without `docpipe_maestro` installed (`FR-013`, `SC-006`).

## Verification Gate Commands

```bash
uv lock --check
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/ruff check --select S src/
.venv/bin/mypy --strict src tests
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro.metrics --cov-branch --cov-fail-under=100 tests/unit/test_metrics.py tests/unit/test_ir_metrics.py tests/contract/test_metric_formulas.py
.venv/bin/pytest --strict-markers -W error -m "gate_determinism or gate_immutability"
uv build && .venv/bin/twine check --strict dist/*
uv run --no-dev --isolated python -c "import sys, evalforge_maestro; assert 'docpipe_maestro' not in sys.modules
try:
    evalforge_maestro.DocpipeAdapter()
except evalforge_maestro.MissingExtraError as exc:
    assert 'docpipe' in str(exc)
else:
    raise AssertionError('Expected MissingExtraError')"
```
