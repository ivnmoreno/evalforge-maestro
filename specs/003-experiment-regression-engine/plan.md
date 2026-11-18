# Implementation Plan: Milestone 3 — Experiment & Regression Engine

**Branch**: `003-experiment-regression-engine` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/003-experiment-regression-engine/spec.md](spec.md)

## Summary

Milestone 3 adds experiment comparison, regression detection, and deterministic release acceptance gating cleanly atop Milestone 1–2 contracts: signed canonical delta rounding (`_canonical.round_delta`), centralized baseline/drift/anomaly/comparison/trend/gate Pydantic v2 contracts in `src/evalforge_maestro/types.py` (including additive nullable `judge_config_fingerprint` and `RunManifestEntry.model_id` for M1–M2 backward compatibility), atomic `.evalforge/baselines.json` lifecycle management in `src/evalforge_maestro/storage/local.py`, and pure computational regression analysis (`compare_runs`, `detect_drift`, `detect_anomalies`, `analyze_trend`, and `QualityGate`) in a new `src/evalforge_maestro/regression/` subsystem delivering 100% branch-covered `QualityGate` decision logic (`FAIL > INCONCLUSIVE > WARNING > PASS`).

## Technical Context

**Language/Version**: Python 3.10+ (verified locally on CPython 3.13.17 and cross-OS matrix `ubuntu-latest`, `macos-latest`, `windows-latest` × `3.10`/`3.13`)

**Primary Dependencies**: Core dependencies remain strictly `pydantic>=2.7,<3` and `jsonschema>=4.23,<5`; M3 uses zero new third-party dependencies (pure Python stdlib `math`, `datetime`, `re`, `os`, `json` alongside canonical helpers).

**Storage**: Extends `LocalRunStore` (`.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`, `.evalforge/tmp/<run_id>.jsonl`) with atomic, secret-redacted, restricted-permission `.evalforge/baselines.json` persistence (`0o700` dir / `0o600` file, `os.replace`) while guaranteeing zero in-place mutation of persisted `RunRecord` or `manifest.jsonl` files.

**Testing**: `pytest` with `--strict-markers`, `filterwarnings = ["error"]`, `>=85%` branch coverage overall, **`100%` branch coverage** on `src/evalforge_maestro/regression/gate.py` (plus existing `metrics/`), `tests/test_library_purity.py` AST boundary & cold-start enforcement, `tests/test_api_stability.py` signature/`__all__` pinning, `@pytest.mark.gate_determinism`, and `@pytest.mark.gate_immutability`.

**Target Platform**: Local developer workstations and Linux/macOS/Windows CI runners (`Python 3.10+`).

**Project Type**: Standalone Python library / SDK (`src/evalforge_maestro/`).

**Performance Goals**: Manifest-driven sliding window trends (`RunManifestEntry` lookup without loading heavy trace JSONs unless explicitly requested), $O(|cases|)$ pairwise `case_id` dictionary alignment, closed-form OLS linear slope over small sequential series with zero `numpy`/`scipy` overhead.

**Constraints**: Strict unidirectional imports (`types.py`, `_canonical.py`, `exceptions.py` remain leaf modules; `regression/` NEVER imports `adapters/`, `cli`, `tomllib`, or `dotenv`), zero wall-clock or random non-determinism inside pure comparison/trend/gate outputs, signed 6-decimal rounding (`1e-9` epsilon tolerance), strict `FAIL > INCONCLUSIVE > WARNING > PASS` gate precedence, `NOT_APPLICABLE` optional-metric safety.

**Scale/Scope**: Milestone 003 covers baselines, pairwise comparison, provenance drift, anti-masking anomalies (`> 0.3` divergence, `>= 0.25` single-case drops, mandatory failures, inconclusive rates), chronological sliding window OLS trends, and deterministic `QualityGate`. LiteLLM judges & calibration (`004`) and CLI/Markdown reporting (`005`) remain deferred.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design Status | Post-Design Verification | Notes |
|---|---|---|---|
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | Strictly preserves 3-way separation: Evaluation (`RunRecord`), Regression (`RunComparisonReport` / `TrendReport` / `DriftWarning` / `AnomalyFlag`), Acceptance (`QualityGateResult`). Zero judge runtime (`004`) or CLI/Markdown (`005`) creep. |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | `src/evalforge_maestro/regression/` imports only `types`, `_canonical`, `exceptions`, and stdlib; AST test in `tests/test_library_purity.py` expanded to enforce leaf-module isolation against `regression` and zero `adapters`/`cli`/`tomllib`/`dotenv` imports inside `regression/`. |
| **III. Single Schema Source of Truth** | PASS | PASS | Every M3 entity (`BaselineEntry`, `BaselineRegistry`, `DriftWarning`, `AnomalyFlag`, `MetricComparison`, `CaseComparison`, `RunComparisonReport`, `TrendReport`, `QualityGatePolicy`, `QualityGateResult`, etc.) resides exclusively in `src/evalforge_maestro/types.py` with explicit `schema_version = "1.0"` and strict validation. |
| **IV. Evidence-Aware & Anomaly-Safe** | PASS | PASS | Anti-masking flags inter-metric disagreement (`> 0.3` with `1e-9`), masked drops (`> 0.05` metric or `>= 0.25` case), mandatory failures, inconclusive spikes, and all three drift dimensions (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`), distinguishing `NOT_APPLICABLE` from `INCONCLUSIVE`. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | Pinning/unpinning baselines never mutates `.evalforge/runs/*.json` or `manifest.jsonl`; unforced baseline overwrites raise `ImmutabilityError`; pure analysis functions avoid `datetime.now()`/`uuid` and apply `round_delta` / `1e-9` epsilon. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | Zero `print`, root logger mutations, or external config reads; baseline `note`/`tags` pass through `redact_secrets`; `.evalforge/baselines.json` inherits `0o700`/`0o600` locking & permissions. |
| **VII. Automated Quality Gates** | PASS | PASS | Enforces `ruff` + Bandit `S`, `mypy --strict`, `>=85%` branch coverage overall + dedicated **`100%` branch coverage** gate on `regression/gate.py`, mandatory drift/anomaly gate tests, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, and `uv lock --check`. |

## Project Structure

### Documentation (this feature)

```text
specs/003-experiment-regression-engine/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 architectural & numerical precision decisions
├── data-model.md        # Phase 1 contracts for Baseline, Drift, Anomaly, Compare, Trend & QualityGate
├── quickstart.md        # Phase 1 end-to-end validation & verification gate commands
├── contracts/
│   ├── public-api.md    # M3 public Python API signatures & exports
│   └── schemas-v1.json  # JSON Schema Draft 2020-12 definitions for all M3 contracts
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/
└── evalforge_maestro/
    ├── __init__.py                  # Re-export M3 contracts, BaselineRegistry/Entry, compare_runs, detect_*, analyze_trend, QualityGate
    ├── _canonical.py                # Add round_delta() signed 6-decimal epsilon helper (normalizing abs(v) <= 1e-9 / -0.0 -> 0.0)
    ├── types.py                     # Add M3 Enums & models; extend RunRecord/RunManifestEntry/OrchestratorConfig with judge_config_fingerprint (+ model_id on manifest)
    ├── execution/
    │   └── orchestrator.py          # Stamp RunRecord.judge_config_fingerprint from OrchestratorConfig.judge_config_fingerprint
    ├── storage/
    │   ├── __init__.py              # Export LocalRunStore
    │   └── local.py                 # Extend LocalRunStore with atomic baselines.json CRUD (pin/get/list/unpin/load_baseline_run/load_runs) & manifest validation
    └── regression/
        ├── __init__.py              # Public exports: QualityGate, analyze_trend, compare_runs, detect_anomalies, detect_drift
        ├── drift.py                 # Pure pairwise & sliding-window provenance drift detection
        ├── anomaly.py               # Pure inter-metric disagreement (>0.3), masked drop, mandatory failure & inconclusive detection
        ├── compare.py               # Pure pairwise RunComparisonReport calculator (aggregate & per-case deltas + target changes)
        ├── trend.py                 # Pure chronological sliding window OLS linear slope analyzer (default latest dataset_id scope)
        └── gate.py                  # Pure deterministic QualityGate evaluator (FAIL > INCONCLUSIVE > WARNING > PASS, 100% branch target)

tests/
├── test_library_purity.py           # Enforce leaf-module & regression/ AST import isolation + zero new cold-start deps
├── test_api_stability.py            # Pin M1 + M2 + M3 __all__ exports, signatures & schema field names
├── contract/
│   └── test_m3_schemas.py           # Validate runtime model JSON dumps against specs/003-experiment-regression-engine/contracts/schemas-v1.json & M1/M2 artifact compatibility
├── unit/
│   ├── test_types.py                # Validate M3 contracts, round_delta, NaN/Inf/bool rejection, model invariants
│   ├── test_baselines.py            # Atomic baselines.json CRUD, ImmutabilityError protection, secret redaction, POSIX perms (@pytest.mark.gate_immutability)
│   ├── test_compare_and_drift.py    # Pairwise deltas, PASS->FAIL transitions, added/removed cases, all 6 DriftCategory checks, target change isolation
│   ├── test_anomalies.py            # >0.3 disagreement boundary (0.8-0.5 vs 0.801-0.5), >=0.25 masked drops, mandatory failures, inconclusive spikes
│   ├── test_trend.py                # OLS slopes, dataset_id default scoping, equal timestamp tie-breaking, <2 points INSUFFICIENT_DATA, window drift
│   └── test_quality_gate.py         # 100% branch coverage across PASS/FAIL/WARNING/INCONCLUSIVE, strict precedence, NOT_APPLICABLE safety, drift & anomaly mandatory gates
└── integration/
    └── test_regression_pipeline.py  # End-to-end M1+M2 dataset->orchestrator->storage->baseline->compare->trend->QualityGate flow (@pytest.mark.gate_determinism, @pytest.mark.gate_immutability)
```

**Structure Decision**: Extends existing single-package `src/evalforge_maestro/` layout seamlessly—isolating filesystem I/O inside `storage/local.py`, centralizing all schemas inside `types.py`, and introducing a pure, zero-I/O `regression/` package aligned strictly with Constitution Principle II.

## Complexity Tracking

> Zero constitutional violations; no complexity exceptions required.
