# EvalForge Maestro

**Evaluate. Compare. Verify.**

> *"EvalForge Maestro is an independent evaluation and regression verification engine — never an LLM runtime, RAG indexer, or agent framework."*

## Installation

```bash
pip install evalforge-maestro
# With optional docpipe-maestro integration:
pip install "evalforge-maestro[docpipe]"
```

For contributor development using [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
```

## Quickstart (Python SDK)

```python
from evalforge_maestro import (
    DatasetEngine,
    EvaluationOrchestrator,
    PrecisionAtKMetric,
    RAGAdapter,
    RecallAtKMetric,
    exact_match,
)

dataset = DatasetEngine(
    [
        {
            "id": "q1",
            "input": "What is the capital of France?",
            "reference": "Paris",
            "expected_context": ["doc-paris"],
        }
    ]
)

adapter = RAGAdapter(
    lambda q: {
        "answer": "Paris",
        "chunks": [{"id": "doc-paris", "text": "Paris is the capital of France."}],
    }
)

run = EvaluationOrchestrator().run(
    dataset,
    adapter,
    [exact_match, PrecisionAtKMetric(k=1), RecallAtKMetric(k=1)],
)
print(run.aggregates["recall_at_k"].mean_score)
```

## Implemented Milestones

### Milestone 1: Evaluation Foundation (`001-evaluation-foundation`)

- **Canonical Contracts (`evalforge_maestro.types`):** Single Pydantic v2 schema source (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`, `RunManifestEntry`) with `schema_version = "1.0"`.
- **Streaming Dataset Engine (`evalforge_maestro.datasets.DatasetEngine`):** Lazy JSONL streaming intake, duplicate `id` rejection, and canonical SHA-256 dataset fingerprinting.
- **Target Adapter (`evalforge_maestro.adapters.CallableAdapter`):** Generic synchronous/asynchronous callable wrapper capturing output, latency, errors, and secret-redacted configuration fingerprints.
- **Deterministic Baseline Metrics (`evalforge_maestro.metrics`):** Versioned `exact_match`, `normalized_match`, and `json_schema_validation` with formal metadata declarations and `NOT_APPLICABLE` / `INCONCLUSIVE` guards.
- **Bounded Orchestration (`evalforge_maestro.execution.EvaluationOrchestrator`):** Bounded concurrency, per-case fault isolation, optional timeouts, post-scoring payload truncation, and resident memory guardrails.
- **Immutable Storage (`evalforge_maestro.storage.LocalRunStore`):** Incremental `.evalforge/tmp/<run_id>.jsonl` checkpointing and atomic non-overwrite persistence to `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl`.

### Milestone 2: Retrieval & RAG Evaluation (`002-retrieval-rag-evaluation`)

- **Graded Context Contracts (`evalforge_maestro.types`):** `ExpectedContextItem` (binary or graded integer `relevance >= 0`), duplicate-ID-checked `EvaluationCase.expected_context`, active `RetrievedChunk` (`rank >= 1`), and `RAGExtractorConfig`.
- **Deterministic IR Metrics (`evalforge_maestro.metrics`):** Versioned `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, and `hit_rate_at_k` with stable `(rank, index)` sorting, `match_parent_id` matching, duplicate chunk deduplication, `CaseCriteria` threshold precedence, AST formula hash pinning, and `INCONCLUSIVE` / `NOT_APPLICABLE` safety.
- **Protocol-Based `RAGAdapter` (`evalforge_maestro.adapters.RAGAdapter`):** Sync/async target wrapper extracting answers, ordered chunks, and `TokenUsage` from mappings, attribute objects, dotted paths, or callables with secret redaction.
- **Optional `[docpipe]` Integration (`DocpipeAdapter` & `load_docpipe_fixture`):** Lazy-imported `DocpipeAdapter` (`mode="answer_detailed"` / `"retrieve"`, raising `MissingExtraError` when `evalforge-maestro[docpipe]` is absent) plus dependency-free `load_docpipe_fixture` / `DatasetEngine.from_docpipe_fixture` conversion for JSON, JSONL, and `docpipe-maestro` `EvalFixture` files.
- **Decoupled Evidence Verification:** Combined retrieval and answer metrics evaluate identically captured `ExecutionResult` artifacts prior to post-scoring `max_context_chars` truncation, surfacing mandatory retrieval failures cleanly.

## CI/CD & PyPI Trusted Publishing Setup

- **CI Pipeline (`.github/workflows/ci.yml`):** Enforces `uv lock --check`, `ruff format --check`, `ruff check`, Bandit `S` checks, `mypy --strict`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics`, `@pytest.mark.gate_determinism` / `@pytest.mark.gate_immutability`, `pip-audit`, `cz check`, cross-OS testing (`ubuntu-latest`, `macos-latest`, `windows-latest`), `uv build` + `twine check --strict`, clean-venv wheel/sdist installs, and `--no-dev` `MissingExtraError` isolation.
- **Release Pipeline (`.github/workflows/release.yml`):** Triggered on `v*` tags; re-runs all verification gates, verifies `hatch-vcs` wheel version matches the Git tag, publishes via OIDC Trusted Publishing (`id-token: write`) to `TestPyPI`, validates clean installation from `TestPyPI`, promotes to `PyPI`, and creates the GitHub Release.
  - One-time repository prerequisite before pushing the first `v*` tag: configure GitHub environments named `testpypi` and `pypi` and register matching OIDC Trusted Publishers on `test.pypi.org` and `pypi.org` targeting `.github/workflows/release.yml`.
