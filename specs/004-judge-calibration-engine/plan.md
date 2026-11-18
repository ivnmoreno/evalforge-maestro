# Implementation Plan: Milestone 4 — Model-Based Judge & Calibration Engine

**Branch**: `004-judge-calibration-engine` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [specs/004-judge-calibration-engine/spec.md](spec.md)

## Summary

Milestone 4 introduces a configurable, provider-independent model-based judge and human-calibration subsystem in `src/evalforge_maestro/judges/` alongside canonical judge & calibration contracts in `src/evalforge_maestro/types.py`. It delivers: (1) five decoupled judge metrics (`groundedness`, `answer_relevance`, `context_relevance`, `answer_correctness`, and `custom_rubric`) satisfying the canonical `Metric` and `AsyncBatchMetric` protocols; (2) per-invocation randomized XML/nonce prompt-injection boundary isolation with breakout sanitization and anti-override instructions; (3) strict `JudgeResponse` Pydantic validation with transient retries and mandatory `INCONCLUSIVE` fallback (`score = None`) on malformed or errored outputs; (4) pre-network `local_only` loopback enforcement (`localhost`, `127.0.0.1`, `::1`, plus automatic `LITELLM_LOCAL_MODEL_COST_MAP=True` air-gap suppression) and lazy `litellm` loading behind optional extra `[judges]`; (5) deterministic, evidence-aware offline `--mock` evaluation (`mock_mode=True`) plus optional scripted mock overrides routed through the canonical validator; (6) context-grouped bounded async scheduling preserving per-case isolation inside `EvaluationOrchestrator` and automatic redacted `judge_config_fingerprint` stamping; and (7) deterministic judge calibration (`calibrate_judge` / `acalibrate_judge`) emitting schema-validated `CalibrationReport` diagnostics against `HumanCalibrationSample` sets.

## Technical Context

**Language/Version**: Python 3.10+ (verified locally on CPython 3.13.17 and cross-OS matrix `ubuntu-latest`, `macos-latest`, `windows-latest` × `3.10`/`3.13`)

**Primary Dependencies**: Core runtime remains strictly `pydantic>=2.7,<3` and `jsonschema>=4.23,<5`. Live external model routing adds an optional extra `judges = ["litellm>=1.84.0"]` under `[project.optional-dependencies]` in `pyproject.toml`, strictly lazy-imported only when non-mock evaluation runs so cold-start imports and minimal `--no-dev` installs never load `litellm`.

**Storage**: Zero new storage file formats on disk; reuses existing `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` (`judge_config_fingerprint` slots added cleanly in M3). Calibration reports (`CalibrationReport`) are pure schema-validated Pydantic models returned directly in memory (with canonical `.model_dump(mode="json")` serialization ready for M5 CLI export).

**Testing**: `pytest` with `--strict-markers`, `filterwarnings = ["error"]`, `>=85%` branch coverage overall (`100%` preserved on `metrics/` and `regression/gate.py`), `tests/test_library_purity.py` AST boundary & cold-start enforcement, `tests/test_api_stability.py` signature/`__all__`/exception pinning, `tests/contract/test_m4_schemas.py`, hermetic zero-socket tests under `tests/conftest.py`, `@pytest.mark.gate_determinism`, and optional `[judges]` CI smoke checks.

**Target Platform**: Local developer workstations and Linux/macOS/Windows CI runners (`Python 3.10+`).

**Project Type**: Standalone Python library / SDK (`src/evalforge_maestro/`).

**Performance Goals**: Bounded async semaphore concurrency (`<= max_concurrency`) grouped by canonical retrieved-context digest (`EvaluationOrchestrator` + `aevaluate_batch`), zero event-loop blocking during network waits or retry backoffs, $O(n \log n)$ single-pass calibration threshold sweeps, and sub-millisecond mock heuristic scoring with zero unnecessary `litellm` imports.

**Constraints**: Strict unidirectional imports (`types.py`, `_canonical.py`, `exceptions.py` remain leaf modules; `judges/` imports only `types`, `_canonical`, `exceptions`, stdlib, and lazy `litellm`; `execution/` delegates via `AsyncBatchMetric` protocol in `types.py` without importing `judges/`); zero credential leakage into prompts, fingerprints, snapshots, or exceptions; pre-network loopback check before socket calls under `local_only=True`; deterministic offline mock results independent of randomized prompt nonces.

**Scale/Scope**: Milestone 004 covers `JudgeConfig`, `JudgeResponse`, randomized delimiter prompts, LiteLLM lazy gateway (`[judges]`), `local_only` guard, offline deterministic `--mock` scoring, context-grouped bounded async judge batching, five built-in judge metrics, `RunRecord.judge_config_fingerprint` auto-derivation, and human ground-truth calibration (`calibrate_judge` / `acalibrate_judge` -> `CalibrationReport`). CLI subcommands (`run --mock --local-only`, `calibrate`), `evalforge.toml`/`.env` loading, and Markdown rendering remain deferred to Milestone 005.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design Status | Post-Design Verification | Notes |
|---|---|---|---|
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | `judges/` evaluates outputs & evidence purely as downstream verification via adapters/execution artifacts; hosts zero LLM inference runtime, zero RAG chunking/indexing, and zero CLI/Markdown formatting (`005`). |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | `judges/` imports only `types`, `_canonical`, `exceptions`, and stdlib (with lazy `litellm` inside provider runtime path). Never imports `adapters`, `cli`, `tomllib`, `dotenv`, `execution`, `storage`, `datasets`, `metrics`, or `regression`. `execution/` accesses batch judge behavior strictly via `AsyncBatchMetric` protocol in `types.py`. Enforced via `tests/test_library_purity.py`. |
| **III. Single Schema Source of Truth** | PASS | PASS | All M4 contracts (`JudgeConfig`, `JudgeResponse`, `HumanCalibrationSample`, `CalibrationDisagreement`, `CalibrationDisagreementType`, `CalibrationReport`, `AsyncBatchMetric`) live exclusively in `src/evalforge_maestro/types.py` with `schema_version = "1.0"`, strict extra forbids, bool/NaN/Inf rejection, and Draft 2020-12 schema parity. |
| **IV. Evidence-Aware & Anomaly-Safe** | PASS | PASS | Built-in `groundedness`, `answer_relevance`, `context_relevance`, and `answer_correctness` evaluate claims, context, and answers independently; missing required inputs yield `NOT_APPLICABLE`; randomized XML/nonce tags isolate untrusted payloads; invalid/unparseable responses yield `INCONCLUSIVE` (`score=None`) cleanly; `calibrate_judge` measures exact agreement, `too_generous_rate`, `too_harsh_rate`, score divergence, and optimal threshold. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | Persisted `RunRecord` immutability untouched; M4 derives deterministic SHA-256 `judge_config_fingerprint` from redacted `JudgeConfig`; `mock_mode=True` emits identical results across identical runs (`@pytest.mark.gate_determinism`) independent of prompt nonces; `local_only=True` blocks remote endpoints pre-network with `LocalOnlyPolicyError` and sets `LITELLM_LOCAL_MODEL_COST_MAP=True`. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | `judges/` attaches only `logging.NullHandler()` (`0` prints/root logger changes); raw API keys remain strictly runtime-only outside persisted `JudgeConfig`/`MetricResult`/`CalibrationReport` payloads, paired with `redact_secrets` + regex secret scrubbing on errors. |
| **VII. Automated Quality Gates** | PASS | PASS | Preserves `ruff format/check`, Bandit `S`, `mypy --strict`, `>=85%` total branch cov (`100%` kept on `metrics/` & `regression/gate.py`), AST & cold-start purity (`litellm` absent on import), `@pytest.mark.gate_determinism`, `--no-dev` `MissingExtraError` check, and optional `[judges]` CI check. |

## Project Structure

### Documentation (this feature)

```text
specs/004-judge-calibration-engine/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 architectural, security, mock & calibration math decisions
├── data-model.md        # Phase 1 contracts for JudgeConfig, JudgeResponse, CalibrationReport, etc.
├── quickstart.md        # Phase 1 end-to-end validation & verification commands
├── contracts/
│   ├── public-api.md    # M4 public Python API exports, signatures & exception classes
│   └── schemas-v1.json  # JSON Schema Draft 2020-12 definitions for all M4 contracts
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
pyproject.toml                        # Add optional extra: judges = ["litellm>=1.84.0"]
uv.lock                               # Locked dependency graph updated for [judges] extra
.github/workflows/ci.yml              # Add optional-judges-compat / clean-core MissingExtraError(judges) assertions

src/
└── evalforge_maestro/
    ├── __init__.py                   # Re-export M4 types, exceptions, built-in judges, and calibration entrypoints
    ├── exceptions.py                 # Add JudgeError(EvalforgeError) and LocalOnlyPolicyError(EvalforgeError)
    ├── types.py                      # Add M4 Enums/Models (JudgeConfig, JudgeResponse, Calibration*) + AsyncBatchMetric protocol
    ├── _canonical.py                 # (Optional minor extension if regex secret scrubbing helper for error text is shared)
    ├── execution/
    │   └── orchestrator.py           # Support AsyncBatchMetric context-grouped execution & auto-derive RunRecord.judge_config_fingerprint
    └── judges/
        ├── __init__.py               # Public exports for M4 judge classes, factories, and calibration functions
        ├── security.py               # Pre-network local_only loopback guard, randomized XML/nonce delimiters, credential scrubbing
        ├── provider.py               # Lazy LiteLLM async completion wrapper, LITELLM_LOCAL_MODEL_COST_MAP=True, retry & strict JSON parser
        ├── mock.py                   # Deterministic evidence-aware offline scorer & scripted mock responder
        ├── prompts.py                # Formal prompt templates & rubrics (groundedness, answer_relevance, context_relevance, answer_correctness, custom_rubric)
        ├── base.py                   # BaseJudgeMetric implementing Metric + AsyncBatchMetric (context-grouped semaphore concurrency & INCONCLUSIVE isolation)
        ├── metrics.py                # GroundednessMetric, AnswerRelevanceMetric, ContextRelevanceMetric, AnswerCorrectnessMetric, CustomRubricJudgeMetric (+ factories)
        └── calibration.py            # calibrate_judge / acalibrate_judge & optimal pass_threshold search producing CalibrationReport

tests/
├── test_library_purity.py            # Extend AST import rules for judges/ & verify cold-start excludes litellm
├── test_api_stability.py             # Pin M4 __all__ exports, JudgeError/LocalOnlyPolicyError, and public signatures/fields
├── contract/
│   └── test_m4_schemas.py            # Validate runtime M4 Pydantic dumps against specs/004.../contracts/schemas-v1.json
├── unit/
│   ├── test_types.py                 # Validate M4 schema constraints (NaN/Inf/bool rejection, HumanCalibrationSample XOR/range checks)
│   ├── test_judge_security.py        # Prompt-injection nonce breakout, credential scrubbing, local_only loopback vs remote pre-network block
│   ├── test_judge_provider.py        # Lazy litellm import, LITELLM_LOCAL_MODEL_COST_MAP=True, fake litellm retries, malformed->INCONCLUSIVE, MissingExtraError
│   ├── test_judge_metrics.py         # All 5 judge metrics, RAG evidence decoupling, NOT_APPLICABLE rules, context-grouped bounded concurrency, fault isolation
│   └── test_calibration.py           # Exact agreement %, too_generous/too_harsh bias, score_divergence, threshold sweep tie-breaks, inconclusive & mixed labels
└── integration/
    └── test_judge_pipeline.py        # End-to-end DatasetEngine -> EvaluationOrchestrator + judges -> LocalRunStore (auto judge_config_fingerprint) -> compare_runs/QualityGate drift -> calibrate (@pytest.mark.gate_determinism)
```

**Structure Decision**: Cleanly extends the existing modular library layout under `src/evalforge_maestro/` with a self-contained `judges/` subsystem alongside schema single-sourcing in `types.py` and protocol-decoupled batch hooks in `execution/orchestrator.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations exist; all principles I–VII pass without structural exceptions.
