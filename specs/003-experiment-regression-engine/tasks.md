---

description: "Actionable dependency-ordered task list for Milestone 3 — Experiment & Regression Engine"
---

# Tasks: Milestone 3 — Experiment & Regression Engine

**Input**: Design documents from `/specs/003-experiment-regression-engine/`

**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/public-api.md`, `contracts/schemas-v1.json`, `quickstart.md`

**Tests**: Included per Constitution Principle VII and `spec.md`/`quickstart.md` verification gates (`tests/test_library_purity.py`, `tests/test_api_stability.py`, `tests/contract/test_m3_schemas.py`, `tests/unit/`, `tests/integration/`, `100%` branch coverage on `src/evalforge_maestro/regression/gate.py`, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`).

**Organization**: Tasks are grouped by user story in priority order so each slice can be built, verified, and demonstrated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unresolved dependencies)
- **[Story]**: Maps task to a user story in `spec.md` (`[US1]`..`[US5]`); omitted in Setup, Foundational, and Polish phases
- Exact repository-relative file paths are specified on every task; constrained entity fields cite `data-model.md` canonically.

---

## Phase 1: Setup (Shared Package & AST Guardrail Structure)

**Purpose**: Establish `regression/` package skeleton and update AST architectural import guardrails before domain implementation.

- [X] T001 Create package placeholder `src/evalforge_maestro/regression/__init__.py` declaring module docstring and empty `__all__` list pending feature exports
- [X] T002 [P] Extend AST boundary checks in `tests/test_library_purity.py` so leaf modules (`types.py`, `exceptions.py`, `_canonical.py`) forbid importing `evalforge_maestro.regression`, `regression/` forbids `adapters`, `cli`, `tomllib`, `dotenv`, `docpipe_maestro`, `langchain`, and `llama_index`, and subprocess cold-start keeps optional dependencies absent

---

## Phase 2: Foundational (Blocking Canonical Math, Provenance & Cross-Story Contracts)

**Purpose**: Core numerical helpers, backward-compatible M1 provenance fields, and cross-cutting diagnostic/policy models required before any M3 user story begins.

**⚠️ CRITICAL**: Complete all tasks in Phase 2 before starting Phases 3–7.

- [X] T003 Add finite signed 6-decimal rounding helper `round_delta(value: float) -> float` (normalizing `abs(value) <= FLOAT_EPSILON` and `-0.0` to `+0.0`) in `src/evalforge_maestro/_canonical.py`
- [X] T004 Extend `OrchestratorConfig`, `RunRecord`, and `RunManifestEntry` (including `RunManifestEntry.from_run_record`) with backward-compatible nullable provenance fields in `src/evalforge_maestro/types.py`, citing `data-model.md` (`OrchestratorConfig.judge_config_fingerprint`, `RunRecord.judge_config_fingerprint`, `RunManifestEntry.model_id`, `RunManifestEntry.judge_config_fingerprint`), and stamp `judge_config_fingerprint` from `config` in `src/evalforge_maestro/execution/orchestrator.py`
- [X] T005 Implement all Milestone 3 enumerations (`GateDecision`, `ComparisonDirection`, `TrendDirection`, `DriftCategory`, `AnomalyType`, `AnomalySeverity`, `AnomalyScope`) in `src/evalforge_maestro/types.py` per `data-model.md` Section 2
- [X] T006 Implement shared drift, anomaly, and gate policy models (`DriftWarning`, `AnomalyFlag`, `QualityGatePolicy`) with `_StrictModel`, `round_delta`/`round_score`, non-empty string, finite numeric, and scope validators in `src/evalforge_maestro/types.py`, citing `data-model.md` (`DriftWarning.category`, `DriftWarning.metric_id`, `DriftWarning.baseline_run_id`, `DriftWarning.candidate_run_id`, `DriftWarning.baseline_value`, `DriftWarning.candidate_value`, `DriftWarning.explanation`, `AnomalyFlag.anomaly_type`, `AnomalyFlag.severity`, `AnomalyFlag.scope`, `AnomalyFlag.case_id`, `AnomalyFlag.metric_ids`, `AnomalyFlag.spread`, `AnomalyFlag.explanation`, `QualityGatePolicy.schema_version`, `QualityGatePolicy.min_score`, `QualityGatePolicy.min_metric_scores`, `QualityGatePolicy.max_regression_drop`, `QualityGatePolicy.max_metric_regression_drops`, `QualityGatePolicy.max_regressed_cases`, `QualityGatePolicy.disagreement_threshold`, `QualityGatePolicy.case_drop_warning_threshold`, `QualityGatePolicy.trend_slope_threshold`, `QualityGatePolicy.max_inconclusive_rate`, `QualityGatePolicy.require_baseline`, `QualityGatePolicy.require_trend`, `QualityGatePolicy.min_trend_runs`, `QualityGatePolicy.soft_regression_warning`, `QualityGatePolicy.fail_on_drift`, `QualityGatePolicy.fail_on_anomaly`, `QualityGatePolicy.fail_on_degrading_trend`, `QualityGatePolicy.fail_on_mandatory_regression`)
- [X] T007 [P] Add unit tests for `round_delta`, M1/M2 additive `judge_config_fingerprint`/`RunManifestEntry.model_id` backward compatibility (updating M1 schema parity validation in `tests/unit/test_types.py` to overlay M3 `RunRecord`/`RunManifestEntry` extensions), enums, `DriftWarning`, `AnomalyFlag`, and `QualityGatePolicy` bounds in `tests/unit/test_types.py` and extend `tests/unit/test_execution.py` to assert `OrchestratorConfig.judge_config_fingerprint` propagation

**Checkpoint**: Foundational contracts and canonical signed delta math ready — user stories can proceed cleanly without cross-cutting rewrites.

---

## Phase 3: User Story 1 — Pin and Resolve Immutable Reference Baselines (Priority: P1) 🎯 MVP

**Goal**: Enable atomic pinning, resolution, deterministic listing, explicit replacement, and alias-only unpinning of named baselines in `.evalforge/baselines.json` without mutating historical run records or manifests.

**Independent Test**: Commit historical runs to a temporary store, record SHA-256 checksums of `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl`, exercise `pin_baseline`, unforced conflict (`ImmutabilityError`), `overwrite=True`, `get_baseline`, `list_baselines`, and `unpin_baseline`, and verify zero byte changes to historical run files (`@pytest.mark.gate_immutability`).

### Implementation & Tests for User Story 1

- [X] T008 [P] [US1] Implement `BaselineEntry` and `BaselineRegistry` Pydantic models (including registry key `== entry.name` and safe alias regex validation) in `src/evalforge_maestro/types.py`, citing `data-model.md` (`BaselineEntry.schema_version`, `BaselineEntry.name`, `BaselineEntry.run_id`, `BaselineEntry.pinned_at`, `BaselineEntry.note`, `BaselineEntry.tags`, `BaselineEntry.dataset_id`, `BaselineEntry.dataset_version`, `BaselineEntry.dataset_fingerprint`, `BaselineEntry.system_version`, `BaselineEntry.model_id`, `BaselineEntry.config_fingerprint`, `BaselineEntry.judge_config_fingerprint`, `BaselineEntry.metric_versions`, `BaselineEntry.aggregate_scores`, `BaselineRegistry.schema_version`, `BaselineRegistry.baselines`)
- [X] T009 [P] [US1] Create schema contract test file merging M1/M2/M3 `$defs` to validate runtime models and sample JSON payloads against `specs/003-experiment-regression-engine/contracts/schemas-v1.json` for overlaid `RunRecord`/`RunManifestEntry`, `BaselineEntry`, `BaselineRegistry`, `DriftWarning`, `AnomalyFlag`, and `QualityGatePolicy` (plus M1/M2 artifact compatibility) in `tests/contract/test_m3_schemas.py`
- [X] T010 [US1] Extend `LocalRunStore` with `baseline_path`, `load_baselines`, `pin_baseline`, `get_baseline`, `list_baselines`, `unpin_baseline`, `load_baseline_run`, and `load_runs` in `src/evalforge_maestro/storage/local.py` (enforcing `StorageError` on invalid aliases or missing/corrupt runs, `ImmutabilityError` on unforced overwrite, secret redaction, `0o700`/`0o600` permissions, and atomic `os.replace`)
- [X] T011 [US1] Write unit and immutability gate tests for baseline lifecycle, conflict rejection, secret redaction, corrupted registry handling, atomic writes, and historical artifact immutability in `tests/unit/test_baselines.py` (`@pytest.mark.gate_immutability`)

**Checkpoint**: User Story 1 complete — immutable baseline registry works and passes independent validation.

---

## Phase 4: User Story 2 — Compare Candidate Runs Against Baselines at Aggregate and Case Level (Priority: P1)

**Goal**: Compare any baseline and candidate `RunRecord` across signed aggregate metric deltas, status count deltas, matched case comparisons (`PASS -> FAIL`, execution error changes, mandatory regressions), unmatched cases, and contextual target changes.

**Independent Test**: Compare synthetic/recorded `RunRecord` pairs exercising score improvements, regressions, `PASS -> FAIL` transitions, added/removed cases, missing `None` metric means, `-0.0`/`1e-9` epsilon normalization, and target `model_id`/`system_version` changes without calling target adapters.

### Implementation & Tests for User Story 2

- [X] T012 [P] [US2] Implement `MetricComparison`, `CaseMetricDelta`, `CaseComparison`, `TargetChangeSummary`, and `RunComparisonReport` in `src/evalforge_maestro/types.py`, citing `data-model.md` (`MetricComparison.metric_id`, `MetricComparison.baseline_version`, `MetricComparison.candidate_version`, `MetricComparison.baseline_score`, `MetricComparison.candidate_score`, `MetricComparison.delta`, `MetricComparison.direction`, `MetricComparison.status_count_deltas`, `CaseMetricDelta.metric_id`, `CaseMetricDelta.baseline_score`, `CaseMetricDelta.candidate_score`, `CaseMetricDelta.delta`, `CaseMetricDelta.baseline_status`, `CaseMetricDelta.candidate_status`, `CaseMetricDelta.regressed`, `CaseMetricDelta.direction`, `CaseComparison.case_id`, `CaseComparison.mandatory`, `CaseComparison.regressed`, `CaseComparison.mandatory_regressed`, `CaseComparison.error_introduced`, `CaseComparison.error_resolved`, `CaseComparison.metrics`, `TargetChangeSummary.system_version_changed`, `TargetChangeSummary.baseline_system_version`, `TargetChangeSummary.candidate_system_version`, `TargetChangeSummary.model_id_changed`, `TargetChangeSummary.baseline_model_id`, `TargetChangeSummary.candidate_model_id`, `TargetChangeSummary.config_fingerprint_changed`, `TargetChangeSummary.baseline_config_fingerprint`, `TargetChangeSummary.candidate_config_fingerprint`, `RunComparisonReport.schema_version`, `RunComparisonReport.baseline_run_id`, `RunComparisonReport.candidate_run_id`, `RunComparisonReport.baseline_name`, `RunComparisonReport.target_changes`, `RunComparisonReport.metric_comparisons`, `RunComparisonReport.case_comparisons`, `RunComparisonReport.matched_case_count`, `RunComparisonReport.added_case_ids`, `RunComparisonReport.removed_case_ids`, `RunComparisonReport.regressed_case_ids`, `RunComparisonReport.mandatory_regressed_case_ids`, `RunComparisonReport.drift_warnings`, `RunComparisonReport.anomalies`)
- [X] T013 [US2] Implement `compare_runs` (aggregate deltas with `round_delta`, status count deltas, directional classifications, matched `case_id` comparisons, `added_case_ids`/`removed_case_ids`/`regressed_case_ids`/`mandatory_regressed_case_ids`, and `TargetChangeSummary`) in `src/evalforge_maestro/regression/compare.py` per `contracts/public-api.md`
- [X] T014 [P] [US2] Add pairwise comparison unit tests covering `IMPROVED`/`REGRESSED`/`UNCHANGED`/`ADDED`/`REMOVED`/`INCONCLUSIVE` directions, `PASS -> FAIL` transitions, added/removed/mandatory cases, `-0.0`/`1e-9` stability, and target change isolation in `tests/unit/test_compare_and_drift.py`

**Checkpoint**: User Story 2 core pairwise comparison works cleanly and is independently tested.

---

## Phase 5: User Story 3 — Detect Inter-Metric Disagreements, Masked Drops, and Cross-Version Drift (Priority: P1)

**Goal**: Automatically detect case/run-level inter-metric disagreements (`> 0.3`), aggregate-masked single-metric and per-case drops (`>= 0.25`), mandatory case failures, dataset capping, inconclusive error spikes, and cross-version provenance drift (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`), and wire them cleanly into `compare_runs`.

**Independent Test**: Pass runs and comparisons exhibiting `0.8 - 0.5` (exact `0.3` non-trigger) vs `0.801 - 0.5` (`> 0.3` trigger), high macro averages hiding metric/case drops or mandatory failures, and provenance mismatches across `dataset_fingerprint`, shared `metric_version`, metric sets, and `judge_config_fingerprint`.

### Implementation & Tests for User Story 3

- [X] T015 [P] [US3] Implement pure provenance drift helpers (`detect_drift` for pairwise `RunRecord`s plus adjacent chronological pair checking over `RunRecord | RunManifestEntry` windows across `DriftCategory.DATASET_FINGERPRINT`, `METRIC_VERSION`, `METRIC_SET`, `JUDGE_CONFIG`, `DATASET_CAPPED`, `CASE_SET_MISMATCH`) in `src/evalforge_maestro/regression/drift.py`
- [X] T016 [P] [US3] Implement `detect_anomalies` covering case-level and run-level `METRIC_DISAGREEMENT` (`spread > policy.disagreement_threshold + FLOAT_EPSILON`), `AGGREGATE_MASKED_DROP` (passing/non-regressing summary masking metric drops `> policy.max_regression_drop`, floor breaches, or single-case drops `>= policy.case_drop_warning_threshold - FLOAT_EPSILON`), `MANDATORY_CASE_FAILURE`, `DATASET_CAPPED`, and `INCONCLUSIVE_SPIKE` (`> 0.0` rate) in `src/evalforge_maestro/regression/anomaly.py`
- [X] T017 [US3] Wire `detect_drift` and `detect_anomalies` into `compare_runs` in `src/evalforge_maestro/regression/compare.py` so `RunComparisonReport.drift_warnings` and `RunComparisonReport.anomalies` populate deterministically in one pass
- [X] T018 [P] [US3] Complete pairwise provenance drift tests (including backward-compatible `judge_config_fingerprint = None` M1/M2 checks) in `tests/unit/test_compare_and_drift.py` and write comprehensive anti-masking anomaly tests in `tests/unit/test_anomalies.py`

**Checkpoint**: User Stories 2 and 3 integrate cleanly — comparisons automatically surface drift and anti-masking anomalies.

---

## Phase 6: User Story 4 — Analyze Linear Quality Trends Across a Sliding Window of Runs (Priority: P2)

*(Implemented prior to User Story 5 `QualityGate` so `QualityGate` can verify all trend rules cleanly in a single complete pass without double-editing `gate.py`.)*

**Goal**: Compute exact closed-form ordinary least-squares slopes, bounds, valid/missing point counts, default latest `dataset_id` filtering, deterministic equal-timestamp tie-breaking, `< 2`-point `INSUFFICIENT_DATA` safety, and within-window provenance drift across chronological sliding windows (`window >= 2`).

**Independent Test**: Pass chronological `RunRecord` and compact `RunManifestEntry` sequences covering improving/stable/degrading slopes (`0.01` cutoff with `1e-9` tolerance), multi-dataset default scoping, equal timestamps, `None`/`INCONCLUSIVE` gaps, empty/1-run histories, and mid-window version shifts.

### Implementation & Tests for User Story 4

- [X] T019 [P] [US4] Implement `TrendDataPoint`, `MetricTrendSummary`, and `TrendReport` Pydantic models (enforcing `valid_points < 2 -> slope is None and direction == INSUFFICIENT_DATA`, `window >= 2`, `slope_threshold > 0.0`) in `src/evalforge_maestro/types.py`, citing `data-model.md` (`TrendDataPoint.run_id`, `TrendDataPoint.timestamp`, `TrendDataPoint.index`, `TrendDataPoint.score`, `TrendDataPoint.metric_version`, `TrendDataPoint.dataset_fingerprint`, `TrendDataPoint.judge_config_fingerprint`, `MetricTrendSummary.metric_id`, `MetricTrendSummary.window_runs`, `MetricTrendSummary.valid_points`, `MetricTrendSummary.missing_points`, `MetricTrendSummary.slope`, `MetricTrendSummary.direction`, `MetricTrendSummary.first_score`, `MetricTrendSummary.last_score`, `MetricTrendSummary.min_score`, `MetricTrendSummary.max_score`, `MetricTrendSummary.mean_score`, `MetricTrendSummary.points`, `MetricTrendSummary.explanation`, `TrendReport.schema_version`, `TrendReport.window`, `TrendReport.dataset_id_filter`, `TrendReport.model_id_filter`, `TrendReport.inspected_run_ids`, `TrendReport.slope_threshold`, `TrendReport.metrics`, `TrendReport.drift_warnings`)
- [X] T020 [US4] Implement `analyze_trend` in `src/evalforge_maestro/regression/trend.py` (supporting `RunRecord | RunManifestEntry`, `ConfigurationError` on `window < 2` or `slope_threshold <= 0.0`, default latest `dataset_id` scoping unless overridden, chronological `(timestamp, run_id)` sorting, sequential OLS regression `round_delta(num / denom)`, `INSUFFICIENT_DATA` safety, and within-window adjacent chronological pair `DriftWarning` transitions + `dataset_capped` checks via `drift.py`)
- [X] T021 [P] [US4] Add unit tests covering OLS math, multi-dataset auto-scoping and `all_datasets=True` override, `model_id`/`metric_ids` filters, equal-timestamp tie-breaking, `< 2` valid point safety, within-window drift transitions, and manifest-only runs in `tests/unit/test_trend.py`

**Checkpoint**: User Story 4 complete — chronological sliding window trends and within-window drift work across both full runs and lightweight manifests.

---

## Phase 7: User Story 5 — Enforce Deterministic Quality Gate Acceptance Decisions (Priority: P1)

**Goal**: Provide the pure deterministic `QualityGate` evaluator resolving `PASS`, `FAIL`, `WARNING`, and `INCONCLUSIVE` under strict `FAIL > INCONCLUSIVE > WARNING > PASS` precedence with full rule transparency and verified `100%` branch coverage.

**Independent Test**: Run `QualityGate.evaluate` over `RunRecord`s + optional `RunComparisonReport` + optional `TrendReport` across every policy rule, precedence permutation, `NOT_APPLICABLE` optional-metric safety, cross-version drift, anomaly flagging, repeated identical calls (`@pytest.mark.gate_determinism`), and enforce `--cov=src/evalforge_maestro/regression/gate --cov-fail-under=100`.

### Implementation & Tests for User Story 5

- [X] T022 [P] [US5] Implement `GateRuleCheck` and `QualityGateResult` models (enforcing `bool`/`NaN`/`Inf` rejection on `observed`/`threshold` and `passed`/`blocking` alignment with `decision`) in `src/evalforge_maestro/types.py`, citing `data-model.md` (`GateRuleCheck.rule_id`, `GateRuleCheck.status`, `GateRuleCheck.message`, `GateRuleCheck.metric_id`, `GateRuleCheck.observed`, `GateRuleCheck.threshold`, `QualityGateResult.schema_version`, `QualityGateResult.decision`, `QualityGateResult.candidate_run_id`, `QualityGateResult.baseline_run_id`, `QualityGateResult.passed`, `QualityGateResult.blocking`, `QualityGateResult.inconclusive_rate`, `QualityGateResult.checks`, `QualityGateResult.failure_reasons`, `QualityGateResult.inconclusive_reasons`, `QualityGateResult.warning_reasons`, `QualityGateResult.drift_warnings`, `QualityGateResult.anomalies`, `QualityGateResult.summary`)
- [X] T023 [US5] Implement `QualityGate` in `src/evalforge_maestro/regression/gate.py` with clean single-purpose helpers, `ConfigurationError` on mismatched `comparison.candidate_run_id != run.run_id`, active-policy evaluation via `detect_anomalies(run, comparison=comparison, policy=self._policy)` (avoiding stale precomputed comparison thresholds), strict `FAIL > INCONCLUSIVE > WARNING > PASS` precedence, `NOT_APPLICABLE` vs. `INCONCLUSIVE` distinction, drift & anomaly enforcement, and zero wall-clock/randomness/disk side effects
- [X] T024 [US5] Wire public exports in `src/evalforge_maestro/regression/__init__.py` (`QualityGate`, `analyze_trend`, `compare_runs`, `detect_anomalies`, `detect_drift`) and top-level re-exports in `src/evalforge_maestro/__init__.py` matching `contracts/public-api.md`
- [X] T025 [US5] Write 100%-branch unit test suite covering every decision branch, precedence matrix (`FAIL > INCONCLUSIVE > WARNING > PASS`), `NOT_APPLICABLE` safety, mandatory cross-version drift gate checks, mandatory anomaly gate checks, trend gate rules, invalid `candidate_run_id` guard, and canonical JSON determinism (`@pytest.mark.gate_determinism`) in `tests/unit/test_quality_gate.py`

**Checkpoint**: All five M3 user stories are complete, exported cleanly, and 100%-branch verified on `QualityGate`.

---

## Phase 8: Polish, Schema/API Contract Pinning & Release Gate Verification

**Purpose**: Finalize contract pins, run end-to-end M1+M2+M3 integration pipeline, verify `quickstart.md` scenarios, and pass every constitutional quality gate.

- [X] T026 [P] Expand `tests/contract/test_m3_schemas.py` to validate runtime JSON payloads for `MetricComparison`, `CaseComparison`, `RunComparisonReport`, `TrendDataPoint`, `MetricTrendSummary`, `TrendReport`, `GateRuleCheck`, and `QualityGateResult` against `specs/003-experiment-regression-engine/contracts/schemas-v1.json`
- [X] T027 [P] Pin all M3 `__all__` exports, regression entrypoint `inspect.signature` shapes, `LocalRunStore` baseline method signatures, and new Pydantic model field lists in `tests/test_api_stability.py`
- [X] T028 Write end-to-end integration test (`DatasetEngine` -> `EvaluationOrchestrator` -> `LocalRunStore` baseline pinning -> `compare_runs` -> `analyze_trend` -> `QualityGate` with `@pytest.mark.gate_determinism` and `@pytest.mark.gate_immutability`) in `tests/integration/test_regression_pipeline.py`
- [X] T029 Run complete M3 validation suite and confirm all gates pass: `ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`, `schemas-v1.json` validation, full `pytest -W error --cov=src/evalforge_maestro` (`>=85%` branch coverage overall and `100%` branch coverage on `src/evalforge_maestro/metrics/` and `src/evalforge_maestro/regression/gate.py`), `pip-audit`, and `uv lock --check`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately (`T001` then `T002`).
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — BLOCKS all user stories (`T003`–`T007`).
- **Phase 3 (US1 Baselines — P1)**: Depends on Phase 2 — independent of `US2`/`US3`/`US4`/`US5`.
- **Phase 4 (US2 Pairwise Compare — P1)**: Depends on Phase 2 (`T012`–`T014`).
- **Phase 5 (US3 Anomalies & Drift — P1)**: Depends on Phase 2 (`T015`–`T016` independent of US2) + Phase 4 (`T017` integrates `drift.py` and `anomaly.py` into `compare.py`).
- **Phase 6 (US4 Sliding Trend — P2)**: Depends on Phase 2 + `drift.py` (`T015`) for within-window provenance drift checks; independent of `US1`/`US2`/`US5`.
- **Phase 7 (US5 QualityGate — P1)**: Depends on Phases 4, 5, and 6 outputs (`RunComparisonReport`, `detect_anomalies`, `TrendReport`).
- **Phase 8 (Polish & Full Verification)**: Depends on Phases 1–7 completion.

### Parallel Opportunities

- Within Phase 1: `T002` can run after or alongside `T001`.
- Within Phase 2: `T003`, `T004`, `T005`, `T006` touch `_canonical.py`, `execution/orchestrator.py`, and `types.py` (keep `types.py` edits serialized or consolidated cleanly, then `T007` validates all of them).
- After Phase 2: **US1 (`T008`–`T011`)** is completely parallel with **`US3` pure engines (`T015`, `T016`)** and **`US2` schemas/compare (`T012`, `T013`)**!
- Within Phase 6 (`US4`): `T019` and `T021` setup/contract fixtures can prepare cleanly alongside `T020`.
- Within Phase 8: `T026`, `T027`, and `T028` operate on separate test files and can run concurrently before `T029`.

### Parallel Example: Post-Foundational Wave (US1 + US2 + US3)

```text
Worker A (Baselines — US1):     T008 (BaselineEntry/Registry in types.py) -> T010 (storage/local.py) -> T011 (test_baselines.py)
Worker B (Compare/Drift — US2): T012 (Comparison types) -> T013 (compare.py)
Worker C (Anomalies/Drift — US3): T015 (drift.py) + T016 (anomaly.py) -> T017 (wire into compare.py) + T018 (test_anomalies.py)
```

---

## Implementation Strategy

### MVP First (Through User Story 1 -> Pairwise + Gate Core)

1. Complete Phase 1 (Setup & AST purity update) + Phase 2 (Foundational signed math & M3 schemas).
2. Complete Phase 3 (**US1 Baselines**) and validate immutability independently (`pytest tests/unit/test_baselines.py`).
3. Complete Phase 4 & Phase 5 (**US2 Compare + US3 Anomalies & Drift**).
4. Complete Phase 6 (**US4 Trend**) and Phase 7 (**US5 QualityGate** with 100% branch coverage).
5. Run Phase 8 full integration, schema contracts, API stability, and CI security/audit verification (`T029`).

### Incremental Verification Rule

- Run `.venv/bin/pytest -W error` on the targeted story unit test file after each phase checkpoint, ensuring `tests/test_library_purity.py` stays green whenever modules or imports are added.
- Run `QualityGate` coverage specifically (`.venv/bin/pytest -W error tests/unit/test_quality_gate.py --cov=src/evalforge_maestro/regression/gate --cov-fail-under=100`) before declaring Phase 7 complete.
