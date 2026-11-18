# EvalForge Maestro

**Evaluate. Compare. Verify.**

> *"EvalForge Maestro is an independent evaluation and regression verification engine — never an LLM runtime, RAG indexer, or agent framework."*

## Milestone 1: Evaluation Foundation (`001-evaluation-foundation`)

- **Canonical Contracts (`evalforge_maestro.types`):** Single Pydantic v2 schema source (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`, `RunManifestEntry`) with `schema_version = "1.0"`.
- **Streaming Dataset Engine (`evalforge_maestro.datasets.DatasetEngine`):** Lazy JSONL streaming intake, duplicate `id` rejection, and canonical SHA-256 dataset fingerprinting.
- **Target Adapter (`evalforge_maestro.adapters.CallableAdapter`):** Generic synchronous/asynchronous callable wrapper capturing output, latency, errors, and secret-redacted configuration fingerprints.
- **Deterministic Baseline Metrics (`evalforge_maestro.metrics`):** Versioned `exact_match`, `normalized_match`, and `json_schema_validation` with formal metadata declarations and `NOT_APPLICABLE` / `INCONCLUSIVE` guards.
- **Bounded Orchestration (`evalforge_maestro.execution.EvaluationOrchestrator`):** Bounded concurrency, per-case fault isolation, optional timeouts, post-scoring payload truncation, and resident memory guardrails.
- **Immutable Storage (`evalforge_maestro.storage.LocalRunStore`):** Incremental `.evalforge/tmp/<run_id>.jsonl` checkpointing and atomic non-overwrite persistence to `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl`.
