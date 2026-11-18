# Implementation Plan: Milestone 1 — Evaluation Foundation

**Branch**: `001-evaluation-foundation` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/001-evaluation-foundation/spec.md](spec.md)

## Summary

Milestone 001 establishes the core programmatic evaluation foundation of `evalforge_maestro`: canonical Pydantic v2 data contracts and protocols in `src/evalforge_maestro/types.py`, lazy streaming JSONL intake with duplicate-ID rejection and canonical SHA-256 fingerprinting in `DatasetEngine`, generic synchronous/asynchronous `CallableAdapter` execution, three versioned deterministic baseline metrics (`exact_match`, `normalized_match`, `json_schema_validation`), bounded-concurrency fault-isolated orchestration in `EvaluationOrchestrator` with post-scoring payload truncation and memory guardrails, and crash-safe incremental checkpointing (`.evalforge/tmp/<run_id>.jsonl`) plus immutable atomic persistence (`.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl`).

## Technical Context

**Language/Version**: Python 3.10+ (verified locally on CPython 3.13.17; cross-OS target `ubuntu-latest`, `macos-latest`, `windows-latest`)

**Primary Dependencies**: `pydantic>=2.7,<3` (canonical schemas & strict boundary validation) and `jsonschema>=4.23,<5` (lazy-imported inside `json_schema_validation` for RFC-compliant JSON Schema validation; zero heavy optional ML/LLM packages in core)

**Storage**: Local filesystem artifacts under `.evalforge/` (`runs/<run_id>.json`, `manifest.jsonl`, `tmp/<run_id>.jsonl`) written via canonical JSON/JSONL, atomic hardlink/rename non-overwrite commit, file locking on manifest appends, and `0o700`/`0o600` POSIX permissions

**Testing**: `pytest` with `--strict-markers`, `filterwarnings = ["error"]`, `pytest-cov` (`>=85%` branch coverage overall; `100%` on deterministic metric formulas), global `autouse` env/network socket isolation fixture, `tests/test_library_purity.py` (AST boundaries + cold-start `sys.modules` subprocess check), `tests/test_api_stability.py` (signature/`__all__` pinning), normalized metric formula hash checks, and `@pytest.mark.gate_determinism` / `@pytest.mark.gate_immutability`

**Target Platform**: Local developer workstations and Linux/macOS/Windows CI runners (`Python 3.10+`, PEP 561 `py.typed`)

**Project Type**: Standalone Python library / SDK (`src/` layout managed with `uv` and `hatchling` + `hatch-vcs`; CLI deferred to Milestone 005)

**Performance Goals**: Stream and fingerprint 10,000 JSONL `EvaluationCase` records in `< 5` seconds on standard developer hardware with `O(1)` per-line intake buffering (excluding compact seen-ID index); bound active in-flight executions strictly to `max_concurrency` (default `4`)

**Constraints**: Strict unidirectional imports (zero CLI/config-loader imports in library modules; zero concrete `adapters` imports in `core`/`metrics`), `NullHandler`-only library logging, zero leaked credentials in persisted artifacts, deterministic 6-decimal float rounding (`1e-9` tolerance), immutable non-overwritable `RunRecord` storage

**Scale/Scope**: Milestone 001 foundational evaluation layer (`types`, `exceptions`, `datasets`, `adapters.callable`, `metrics.deterministic`, `execution`, `storage`) supporting multi-thousand-case JSONL runs safely within workstation memory caps; retrieval (`002`), regression/gates (`003`), LLM judges (`004`), and full CLI/Markdown reports (`005`) are explicitly deferred

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design Status | Post-Design Verification | Notes |
|---|---|---|---|
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | Pure evaluation engine only; no RAG indexing, LLM runtime, framework lock-in, or web UI. `002`–`005` deferred cleanly. |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | `TargetAdapter` & `Metric` Protocols live in `types.py`; `datasets`, `metrics`, `execution`, `storage` have zero imports from `adapters`, `cli`, `tomllib`, or `dotenv`. Enforced by `tests/test_library_purity.py` & `tests/test_api_stability.py`. |
| **III. Single Schema Source of Truth** | PASS | PASS | All contracts (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`, `RunManifestEntry`, etc.) defined in `src/evalforge_maestro/types.py` with `schema_version = "1.0"` and `extra="forbid"`. |
| **IV. Evidence-Aware & Anomaly-Safe** | PASS | PASS | `ExecutionResult` captures output, latency, errors, truncation, fingerprints, plus reserved slots (`retrieved_chunks`, `trace`, `tool_calls`, `tokens`). Missing references yield `NOT_APPLICABLE`; target errors/timeouts yield `INCONCLUSIVE`; `mandatory_failed_case_ids` / `has_mandatory_failures` prevent aggregate score masking. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | Streaming canonical SHA-256 over evaluated cases, 6-decimal rounding, formula AST-hash guard tests, atomic `os.link` non-overwrite commit for `runs/<run_id>.json`, locked append for `manifest.jsonl`, `.evalforge/tmp/<run_id>.jsonl` failure retention, and `0o700`/`0o600` permissions. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | `NullHandler()`-only logging across all modules, zero `stdout` output, recursive sensitive-key redaction before config fingerprinting/persistence, and global `autouse` test fixture blocking network/env leaks. |
| **VII. Automated Quality Gates** | PASS | PASS | `pyproject.toml` configures `ruff` (`E,W,F,I,UP,B,SIM,RUF` + `S` Bandit on `src/`), `mypy --strict src tests`, `pytest --strict-markers` with `filterwarnings=["error"]`, `>=85%` branch coverage (`100%` on metric formulas), `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, and LF `.gitattributes`. |

*Note on Core Footprint (`Constitution §Technical Constraints`)*: Including `jsonschema>=4.23,<5` alongside `pydantic>=2.7,<3` in core runtime dependencies is justified because `json_schema_validation` is an in-scope M1 deterministic metric required in `--no-dev` minimal core installs (`FR-013`, `FR-016`), and lazy-importing `jsonschema` inside metric evaluation ensures zero cold-start module bloat on `import evalforge_maestro`.

## Project Structure

### Documentation (this feature)

```text
specs/001-evaluation-foundation/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 architecture & tradeoff decisions
├── data-model.md        # Phase 1 canonical entities, fields & state transitions
├── quickstart.md        # Phase 1 runnable validation scenarios & gate commands
├── contracts/
│   ├── public-api.md    # M1 public Python API, Protocols & exception hierarchy
│   ├── schemas-v1.json  # JSON Schema representations of M1 contracts (v1.0)
│   └── storage-layout.md # .evalforge/ directory layout, permissions & atomicity rules
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
.gitattributes
pyproject.toml
uv.lock
src/
└── evalforge_maestro/
    ├── __init__.py                # Public M1 exports (__all__), package version, NullHandler root logger
    ├── py.typed                   # PEP 561 typed package marker
    ├── exceptions.py              # EvalforgeError hierarchy
    ├── types.py                   # Single schema source of truth + TargetAdapter & Metric protocols
    ├── _canonical.py              # Canonical JSON, SHA-256 streaming/hashing, 6-decimal rounding, redaction
    ├── datasets/
    │   ├── __init__.py
    │   └── engine.py              # DatasetEngine (streaming JSONL, duplicate ID check, SHA-256 fingerprint)
    ├── adapters/
    │   ├── __init__.py
    │   └── callable.py            # CallableAdapter (sync/async execution, latency, error, config fingerprint)
    ├── metrics/
    │   ├── __init__.py
    │   └── deterministic.py       # exact_match, normalized_match, json_schema_validation + MetricMetadata
    ├── execution/
    │   ├── __init__.py
    │   └── orchestrator.py        # EvaluationOrchestrator (bounded workers, timeout, post-score truncation, RAM guard)
    └── storage/
        ├── __init__.py
        └── local.py               # LocalRunStore (tmp checkpoints, atomic immutable RunRecord + manifest.jsonl)

tests/
├── conftest.py                    # Global autouse env/network isolation + shared test fixtures
├── test_library_purity.py         # AST boundary verification + subprocess cold-start sys.modules check
├── test_api_stability.py          # __all__, EvalforgeError inheritance & inspect.signature pinning
├── unit/
│   ├── test_canonical.py
│   ├── test_types.py
│   ├── test_datasets.py
│   ├── test_adapters.py
│   ├── test_metrics.py
│   ├── test_execution.py
│   └── test_storage.py
├── integration/
│   ├── test_end_to_end_run.py
│   └── test_crash_and_truncation.py
└── contract/
    ├── test_metric_formulas.py    # Normalized AST/source hash guard per metric_version
    ├── test_determinism_gate.py   # @pytest.mark.gate_determinism
    └── test_immutability_gate.py  # @pytest.mark.gate_immutability
```

**Structure Decision**: Single-package `src/evalforge_maestro/` layout matching `docs/intent.md` §1 & §7.1 and Constitution Principle II. All domain contracts and protocols live in `types.py` (with exception types in leaf `exceptions.py`) so `datasets`, `metrics`, `execution`, and `storage` maintain strictly acyclic downward imports with zero import dependency on `adapters` or future `cli`/`config` modules. `tests/test_library_purity.py` and `tests/test_api_stability.py` sit directly under `tests/` to match the exact paths codified in `docs/intent.md` and `constitution.md`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Core dependency addition: `jsonschema>=4.23,<5` alongside `pydantic>=2.7,<3` | `json_schema_validation` is an in-scope M1 baseline metric (`FR-013`, `FR-016`) that must function in `--no-dev` minimal core installs | Hand-rolling JSON Schema Draft 2020-12 / Draft-07 validation in pure Python is error-prone across `$defs`, `anyOf`/`oneOf`, `additionalProperties`, and pattern/numeric constraints; mitigated via lazy import inside `JsonSchemaValidationMetric` so cold-start import stays lightweight |
