# Quickstart Validation Guide: Milestone 3 — Experiment & Regression Engine

**Feature**: `003-experiment-regression-engine` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## Prerequisites

- Python `3.10+` with synced development environment (`uv sync --extra dev` or active `.venv`)
- Milestone 1 & 2 passing baseline (`pytest`)
- Contracts defined in [data-model.md](data-model.md) and [contracts/public-api.md](contracts/public-api.md)

## Validation Scenarios (End-to-End Proofs)

### Scenario 1 — Immutable Baseline Lifecycle (`US1`, `gate_immutability`)
1. Commit two runs (`baseline-v1`, `candidate-v2`) to a temporary `.evalforge/` directory via `LocalRunStore.save_run`.
2. Record SHA-256 checksums of `.evalforge/runs/baseline-v1.json` and `.evalforge/manifest.jsonl`.
3. Pin `baseline-v1` as `"default"` (`store.pin_baseline("baseline-v1")`), verify `get_baseline("default")` and `list_baselines()`.
4. Attempt `store.pin_baseline("candidate-v2")` without `overwrite=True` -> assert `ImmutabilityError` is raised and `"default"` still points to `baseline-v1`.
5. Pin `"default"` with `overwrite=True`, unpin `"default"`, and verify `baseline-v1.json` and `manifest.jsonl` bytes are unchanged (plus POSIX file mode `0o600` on `.evalforge/baselines.json` and directory mode `0o700`).

### Scenario 2 — Pairwise Comparison & Drift Isolation (`US2`, `US3`)
1. Compare a baseline run (`exact_match=1.0`) and candidate run (`exact_match=0.8`, one `PASS -> FAIL` matched case, one added case, one removed case, intentional `model_id` change `m1 -> m2`) via `compare_runs(baseline, candidate)`.
2. Verify exact 6-decimal signed `delta = -0.2`, `direction = ComparisonDirection.REGRESSED`, `added_case_ids`, `removed_case_ids`, `regressed_case_ids`, and `target_changes.model_id_changed is True` with zero measurement-drift flags solely from `model_id` change.
3. Repeat pairwise comparison when `dataset_fingerprint`, shared `metric_version`, or `judge_config_fingerprint` differs -> assert explicit `DriftWarning` entries with exact categories (`DATASET_FINGERPRINT`, `METRIC_VERSION`, `JUDGE_CONFIG`).

### Scenario 3 — Anomaly & Anti-Masking Detection (`US3`)
1. Evaluate a case where `exact_match = 1.0` (`PASS`) and `precision_at_k = 0.0` (`FAIL`) -> verify `AnomalyType.METRIC_DISAGREEMENT` with `spread = 1.0`.
2. Verify boundary precision: scores `0.8` and `0.5` (`spread = 0.3`) yield zero `METRIC_DISAGREEMENT` flags; `0.801` vs `0.5` yields a disagreement anomaly.
3. Evaluate a high aggregate candidate masking a `>= 0.25` single-case drop or mandatory failure -> verify `AGGREGATE_MASKED_DROP` / `MANDATORY_CASE_FAILURE`.

### Scenario 4 — Sliding Window Linear Trend Analysis (`US4`)
1. Persist a chronological sequence of `5` runs (`[0.90, 0.88, 0.86, 0.84, 0.82]`) on `dataset_id="bench"` alongside `1` unrelated run on `dataset_id="other"`.
2. Call `analyze_trend(runs, window=5)` -> confirm automatic scoping locks onto `"bench"` (excluding `"other"`) and computes exact OLS `slope = -0.02` (`TrendDirection.DEGRADING`).
3. Verify `< 2` valid numeric points returns `slope = None` and `TrendDirection.INSUFFICIENT_DATA`, and mid-window `dataset_fingerprint`/`metric_version`/`judge_config_fingerprint` shifts populate `drift_warnings`.

### Scenario 5 — Deterministic `QualityGate` Precedence & 100% Decision Branch Coverage (`US5`, `gate_determinism`)
1. Run `QualityGate(policy).evaluate(run, comparison=comp, trend=trend)` across explicit `PASS`, `FAIL` (mandatory failure, floor breach, >0.05 baseline drop, strict escalations), `INCONCLUSIVE` (>0.10 inconclusive rate, all-`None` metrics, required missing baseline/trend, while proving pure `NOT_APPLICABLE` optional metrics still `PASS`), and `WARNING` (drift warnings, `> 0.3` disagreement anomalies, capped datasets, unmatched cases, degrading trend, `<= 0.10` inconclusive rate).
2. Assert combined-rule precedence (`FAIL > INCONCLUSIVE > WARNING > PASS`) and byte-for-byte canonical JSON identity across repeated invocations (`@pytest.mark.gate_determinism`).

## Verification Gate Commands

```bash
# 1. Static analysis, Bandit security & strict typing
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/ruff check --select S src/
.venv/bin/mypy --strict src tests

# 2. Schema validation for M3 JSON Schema extensions
.venv/bin/python -c "import json, jsonschema; s = json.load(open('specs/003-experiment-regression-engine/contracts/schemas-v1.json')); jsonschema.Draft202012Validator.check_schema(s); print('schemas-v1.json valid')"

# 3. Full suite + branch coverage (overall >=85% and 100% on QualityGate & metrics)
.venv/bin/pytest -W error --cov=src/evalforge_maestro --cov-report=term-missing
.venv/bin/pytest -W error tests/unit/test_quality_gate.py --cov=src/evalforge_maestro/regression/gate --cov-fail-under=100
```
