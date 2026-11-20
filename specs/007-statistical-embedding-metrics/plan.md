# Implementation Plan: Statistical & Embedding Similarity Metrics

**Branch**: `007-statistical-embedding-metrics` | **Date**: 2026-11-20 | **Spec**: [`spec.md`](spec.md)

**Input**: Feature specification from `specs/007-statistical-embedding-metrics/spec.md`

## Summary

Feature `007` adds two orthogonal Post-M6 capabilities from `docs/future-features.md` while keeping the core install minimal (`pydantic` + `jsonschema`) and cold-start pure:

1. **Lazy `[embeddings]` Similarity Evaluation (`src/evalforge_maestro/embeddings/`)**: Adds `EmbeddingSimilarityMetric` (`output` vs `reference`) and `ContextEmbeddingSimilarityMetric` (`output` vs retrieved chunks via `max`/`mean` aggregation) behind `evalforge-maestro[embeddings]` (`numpy` + `litellm`). Uses clamped cosine similarity `max(0.0, cosine) in [0.0, 1.0]`, fail-fast `[embeddings]` extra check on metric invocation (even under `--mock` or missing references) while keeping cold imports `numpy`/`litellm`-free, strict `[embedding]` vs `[judge]` config isolation (default `mock-embedding`), deterministic feature-hashed offline `--mock` vectors, shared pre-network `--local-only` / `--block-pii` safety (`_locality.py`), caller-supplied `embed_fn`, and bounded async batching (`AsyncBatchMetric`). Also extends `drift.py` (`DriftCategory.EMBEDDING_CONFIG`) and `reporting/builder.py` (answer vs context-alignment decoupling diagnostics).
2. **Pure-Stdlib Statistical Distribution Comparisons & Multi-Run Cohorts (`src/evalforge_maestro/regression/stats.py`, `compare.py`, `gate.py`)**: Enriches single-run `compare_runs` with exact Student's `paired_t_case` confidence intervals, dispersion metrics, p-values, and significance classifications; adds `compare_run_cohorts` (`welch_t_run` / `one_sample_t_run` primary + secondary per-case `paired_t_case` + cohort drift detection, default `min_statistical_samples = 2`), `--repeats N` trial execution on `run`, `QualityGate.evaluate_cohort` (any-repeat mandatory failure + pooled cohort metric floor checks), advisory `WARNING` checks on **any** statistically significant drop (`ci_high < 0`, escalatable to `FAIL` via `--strict` or `fail_on_significant_regression`), and Markdown/JSON report rendering.

## Technical Context

**Language/Version**: Python 3.10+ (`3.10`..`3.13` tested in CI)  
**Primary Dependencies**: Core unchanged (`pydantic>=2.7,<3`, `jsonschema>=4.23,<5`, `tomli`); optional extra `embeddings = ["numpy>=1.26,<3", "litellm>=1.84.0"]`; statistical math pure stdlib (`math`)  
**Storage**: Immutable JSON/JSONL canonical store (`.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`), `1.0` schema backward compatible  
**Testing**: `pytest --strict-markers -W error`, `--cov-branch --cov-fail-under=85` global, `100%` branch coverage on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`, AST purity + API stability + release gates (`gate_determinism`, `gate_immutability`), optional extra matrix (`[embeddings]`)  
**Target Platform**: Cross-OS (Linux, macOS, Windows) CLI & Python SDK  
**Project Type**: Library + CLI tool (`evalforge-maestro`)  
**Performance Goals**: Zero cold-start import latency overhead (`numpy`/`litellm`/`scipy` absent on import & `--help`); batched deduplicated embedding calls under `max_concurrency`; microsecond stdlib Student's $t$ / incomplete-beta evaluation  
**Constraints**: Unidirectional architecture (`types`/`metrics`/`regression`/`embeddings` never import `cli`/`adapters`, `metrics`/`regression` never import `embeddings`/`judges`); zero `NaN`/`Inf` or zero-division crashes; zero unredacted secrets  
**Scale/Scope**: Post-M6 minor capability (`v0.3.0`), preserving 100% `v0.1.x`/`v0.2.0` schema and CLI compatibility

## Constitution Check

*GATE: Checked before Phase 0 research and re-checked after Phase 1 design.*

| Principle | Compliance Strategy | Status |
| --- | --- | --- |
| **I. Scope Tiebreaker** | Evaluates already-captured outputs, references, and retrieved chunks; never parses documents, chunks files, builds vector indexes, or bundles multi-GB models. | PASS |
| **II. Library Purity & Unidirectional Layers** | Shared pre-network locality helper lives in `_locality.py` (leaf-only imports). `embeddings/` imports only `_canonical`, `_locality`, `exceptions`, `types`; keeps `numpy` and `litellm` lazy; `metrics/` and `regression/` stay zero-I/O stdlib pure; `reporting/` imports only `types`, `_canonical`, `exceptions`. Enforced in `tests/test_library_purity.py`. | PASS |
| **III. Single Schema Source of Truth** | All new contracts (`EmbeddingConfig`, `ResolvedEmbeddingSettings`, `StatisticalSummary`, `SignificanceStatus`, `StatisticalMethod`, `RunCohortSummary`, backward-compatible extensions on `MetricComparison`, `RunComparisonReport`, `QualityGatePolicy`, `CLIResolvedConfig`, `ReportDocument`) live strictly in `src/evalforge_maestro/types.py` with `schema_version = "1.0"`. | PASS |
| **IV. Evidence-Aware & Anomaly-Safe** | Zero-clamped `[0.0, 1.0]` cosine scores; `NOT_APPLICABLE` for missing ground truth; `INCONCLUSIVE` on zero-norm/mismatched/non-finite vectors; `context_embedding_similarity` integrated into decoupled evidence diagnostics; constant-shift & small-sample guards prevent silent false passes. | PASS |
| **V. Immutable Artifacts & Determinism** | `--repeats` writes distinct immutable `RunRecord` artifacts with deterministic seed progression; `--mock` uses `sha256` feature hashing; statistical math rounds cleanly (`6` decimals + `FLOAT_EPSILON`); `--local-only` blocks remote endpoints pre-network with exit code `4`. | PASS |
| **VI. Stream & Secret Hygiene** | `[embedding].api_key` and `EVALFORGE_EMBEDDING_API_KEY` masked identically to judge secrets; `--block-pii` scans remote payloads pre-network; library code remains `NullHandler`-only. | PASS |
| **VII. Automated Quality Gates** | Maintains `100%` branch coverage on `regression/gate.py` & `metrics/`, `>= 85%` global branch coverage, `ruff`/`S`/`mypy --strict`, `tests/test_api_stability.py` updated deliberately for new public exports, plus CI `[embeddings]` & minimal-core `--no-dev` checks. | PASS |

*Post-Design Re-Check*: Confirmed `src/evalforge_maestro/metrics/` stays untouched by optional `numpy`/`litellm` dependencies so CI's standalone 100%-branch `evalforge_maestro.metrics` gate remains green, while `evalforge_maestro.embeddings/` mirrors `judges/` cleanly. No Constitution deviations exist.

## Project Structure

### Documentation (this feature)

```text
specs/007-statistical-embedding-metrics/
├── spec.md                              # Feature specification (clarifications resolved)
├── checklists/
│   └── requirements.md                  # Spec quality checklist (all passed)
├── plan.md                              # This implementation plan
├── research.md                          # Phase 0 architectural & math decisions
├── data-model.md                        # Phase 1 canonical schema extensions
├── quickstart.md                        # Phase 1 end-to-end validation scenarios
└── contracts/
    ├── public-api-and-metrics.md        # SDK exports, metric & statistical comparison contracts
    └── cli-and-config.md                # CLI flags, TOML, env precedence & exit codes
```

### Source & Configuration Layout (repository root)

```text
pyproject.toml                           # Add [project.optional-dependencies].embeddings
.github/workflows/ci.yml                 # Add optional-embeddings-compat job & minimal-core checks
examples/ci/                             # Preserve existing templates; verify compatibility
src/evalforge_maestro/
├── __init__.py                          # Export new M7/007 public types, metrics & cohort compare
├── _locality.py                         # Shared loopback/airgap/PII pre-network guards (refactored from judges/security.py)
├── types.py                             # EmbeddingConfig, StatisticalSummary, RunCohortSummary, policy/report extensions
├── embeddings/
│   ├── __init__.py                      # Export EmbeddingSimilarityMetric, ContextEmbeddingSimilarityMetric
│   ├── mock.py                          # Deterministic SHA-256 token+trigram mock vector generator
│   ├── provider.py                      # Lazy numpy/litellm resolution, retry wrapper, clamped cosine math
│   └── metrics.py                       # Metric + AsyncBatchMetric + PII guard implementations
├── judges/
│   └── security.py                      # Delegate shared loopback/airgap/PII helpers to _locality.py
├── regression/
│   ├── __init__.py                      # Export compare_run_cohorts
│   ├── stats.py                         # Pure-stdlib Student-t incomplete beta CDF/quantile, paired/Welch/one-sample tests
│   ├── drift.py                         # Add EMBEDDING_CONFIG drift check & detect_cohort_drift helper
│   ├── compare.py                       # Enrich compare_runs with paired stats; add build_pooled_cohort_run & compare_run_cohorts
│   └── gate.py                          # Add QualityGate.evaluate_cohort & 100%-branch-covered statistical significance gate rule
├── reporting/
│   ├── builder.py                       # Register embedding/context metrics cleanly in decoupling diagnostics
│   └── markdown.py                      # Render statistical CI / significance / cohort tables & explanations
└── cli/
    ├── config.py                        # [embedding], [run].repeats, [gate] statistical fields & secret masking
    ├── parser.py                        # --embedding-*, --repeats, compare multi-candidate/--baseline-run, gate flags
    ├── targets.py                       # Build embedding metrics; enforce preflight locality/PII checks
    └── commands.py                      # Execute repeats/cohorts seamlessly in `run` and `compare`

tests/
├── test_library_purity.py               # Enforce AST boundaries & cold-start absence for embeddings/
├── test_api_stability.py                # Pin new exports & verify backward compatibility of signatures
├── contract/
│   └── test_m7_schemas.py               # Schema defaults, legacy 1.0 backwards compat, formula determinism
├── unit/
│   ├── test_embedding_metrics.py        # Cosine math, mock determinism, edge/error cases, MissingExtraError
│   ├── test_embedding_provider.py       # Lazy numpy/litellm resolution, retries, local_only/PII preflight
│   ├── test_statistical_compare.py      # Exact t-critical accuracy, zero-variance/small-n/unmatched/cohort tests
│   └── test_quality_gate.py             # Extended to keep 100% branch coverage on statistical gate branches
└── integration/
    └── test_statistical_embedding_pipeline.py  # End-to-end CLI & SDK flows (--repeats, cohorts, --mock, reports)
```

**Structure Decision**: Mirror the existing `judges/` architectural pattern cleanly via a standalone `embeddings/` subpackage plus a leaf-only `_locality.py` helper so `metrics/`, `regression/`, `judges/`, and `embeddings/` maintain strict unidirectional boundaries without circular imports or extra bloat in minimal installs.

## Complexity Tracking

No Constitution violations or exceptions required.
