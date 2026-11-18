# Quickstart Validation Guide: Milestone 1 — Evaluation Foundation

**Feature**: `001-evaluation-foundation` | **Date**: 2026-11-18
**References**: [spec.md](spec.md) | [data-model.md](data-model.md) | [public-api.md](contracts/public-api.md) | [schemas-v1.json](contracts/schemas-v1.json) | [storage-layout.md](contracts/storage-layout.md)

This guide defines the end-to-end validation scenarios and gate commands used to verify Milestone 001 once implemented.

## Prerequisites

- Python `3.10+` inside the repository `.venv` (`uv sync` / `.venv/bin/python`)
- Minimal core dependencies installed (`pydantic` v2, `jsonschema`) plus `[dev]` test/lint/type tools for gate runs
- Isolated temporary workspace (`tmp_path`) for `.evalforge/` artifacts during verification

## Scenario 1: Streaming Validation, Duplicate Rejection & Canonical Fingerprinting

1. Prepare two semantically equivalent JSONL datasets containing valid `EvaluationCase` records (`schema_version = "1.0"`) with differing JSON key ordering and whitespace.
2. Stream both files through `DatasetEngine.iter_cases()` and verify lazy record-by-record intake and identical SHA-256 `dataset_fingerprint` values (`FR-005`, `FR-008`, `SC-003`).
3. Verify `DatasetEngine.fingerprint(max_cases=N)` hashes only the `N` evaluated cases (`dataset_capped = True` in `RunRecord`) without scanning unread tail records (`Clarification Q1`).
4. Feed malformed JSONL lines, empty files (`0` cases), and duplicate `EvaluationCase.id` records and confirm immediate `DatasetError`, `EmptyDatasetError`, or `DuplicateCaseIdError` exceptions identifying the offending case/line (`FR-006`, `FR-007`, `FR-009`, `SC-002`).

## Scenario 2: Sync/Async Execution, Bounded Concurrency & Fault Isolation

1. Wrap both a synchronous function and an `async def` coroutine inside `CallableAdapter`, supplying `system_version` and redacted `config` metadata (`FR-010`, `FR-011`).
2. Execute a multi-case batch through `EvaluationOrchestrator.run(...)` / `arun(...)` with `OrchestratorConfig(max_concurrency=2, case_timeout_seconds=0.5, max_context_chars=256)` (`FR-019`, `FR-020`, `FR-021`).
3. Include healthy cases, a slow hanging case exceeding `case_timeout_seconds`, an exception-raising case, and a valid case producing an oversized JSON output `> 256` characters (`SC-004`, `SC-005`).
4. Verify:
   - Active in-flight calls never exceed `max_concurrency = 2`.
   - The failing and timed-out cases capture error strings on `ExecutionResult.errors` and record `MetricStatus.INCONCLUSIVE` (`score = None`) without halting remaining cases (`FR-018`, `FR-020`).
   - The oversized valid JSON case scores `1.0` (`PASS`) in `json_schema_validation` before persistence truncates its stored output and flags `ExecutionResult.truncated = True` (`FR-012`, `Clarification Q3`).

## Scenario 3: Deterministic Metrics & Mandatory Failure Surfacing

1. Evaluate cases combining `ExactMatchMetric`, `NormalizedMatchMetric`, and `JsonSchemaValidationMetric` (`FR-013`–`FR-017`).
2. Confirm schema precedence for `json_schema_validation`: `criteria.json_schema` overrides `reference`, falling back to `reference` when it is a JSON Schema mapping, then metric-level default schema (`Clarification Q2`), and returning `score = None` (`NOT_APPLICABLE`) when no schema or reference applies (`FR-017`).
3. Include a mandatory case (`criteria.mandatory = True`) that fails a metric alongside passing standard cases, and confirm `RunRecord.has_mandatory_failures == True` and `mandatory_failed_case_ids` lists that case (`FR-022`, `SC-006`).

## Scenario 4: Checkpointing, Atomic Commit, Immutability & Quality Gates

1. Run an interrupted/failing batch with `fail_fast=True` and confirm `.evalforge/tmp/<run_id>.jsonl` retains completed checkpoint entries while `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` remain absent (`FR-024`, `SC-007`).
2. Complete a full run and confirm `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` exist with canonical JSON formatting, `0o700`/`0o600` permissions on POSIX, zero plaintext credential keys, and cleanup of `.evalforge/tmp/<run_id>.jsonl` (`FR-025`, `FR-027`, `SC-008`, `Clarification Q4`).
3. Attempt to call `LocalRunStore.save_run(...)` again with the same `run_id` and confirm `ImmutabilityError` leaves the persisted run untouched (`FR-026`, `@pytest.mark.gate_immutability`).

## Verification Gate Commands

Run all automated constitution and quality gates from the repository root using `.venv`:

```bash
uv lock --check
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/ruff check --select S src/
.venv/bin/mypy --strict src tests
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85
.venv/bin/pytest --strict-markers -m "gate_determinism or gate_immutability"
uv build
uv run --isolated --no-dev --with dist/*.whl python -c "import evalforge_maestro; print(evalforge_maestro.__all__)"
```

Expected outcomes: lockfile consistent, zero lint/security/type errors, cold-start and AST purity tests passing (`tests/test_library_purity.py`, `tests/test_api_stability.py`), `>= 85%` branch coverage (`100%` on `src/evalforge_maestro/metrics/deterministic.py`), all determinism/immutability gate tests green, and isolated `--no-dev` built wheel imports cleanly without dev dependencies.
