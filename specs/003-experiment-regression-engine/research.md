# Phase 0 Research: Milestone 3 — Experiment & Regression Engine

**Feature**: `003-experiment-regression-engine` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## Research Decisions

### 1. Subsystem Purity vs. Local Baseline Persistence Boundary

- **Decision**: Keep all `.evalforge/` disk I/O and atomic locking inside `src/evalforge_maestro/storage/local.py` (`LocalRunStore` extended with `.evalforge/baselines.json` methods and multi-run loading helpers), while keeping `src/evalforge_maestro/regression/` 100% pure in-memory computation over canonical `types.py` models (`compare_runs`, `detect_drift`, `detect_anomalies`, `analyze_trend`, `QualityGate`). Optional convenience loaders may live on `LocalRunStore` or thin orchestrating helpers that accept already-loaded artifacts or `LocalRunStore` without importing target adapters, `cli`, `tomllib`, or `dotenv`.
- **Rationale**:
  - Satisfies Constitution Principle II (unidirectional dependencies, zero CLI/config file leakage, AST boundary verification in `tests/test_library_purity.py`).
  - Satisfies `FR-019` and `@pytest.mark.gate_determinism`: pure functions over `RunRecord`/`RunManifestEntry`/`BaselineRegistry` make zero wall-clock (`datetime.now()`), UUID, or filesystem calls inside comparison, anomaly, trend, and `QualityGate` evaluations, yielding canonical JSON that is byte-for-byte identical across repeated calls.
  - Keeps POSIX `0o700` directory / `0o600` file permission hardening, `redact_secrets`, `os.fsync`, and atomic `os.replace` swaps isolated in one battle-tested storage module.
- **Alternatives Considered**:
  - Placing filesystem reads/writes directly inside `regression/` (`baselines.py`, `trend.py`): rejected because duplicating atomic file/locking helpers across subsystems risks drift and tangles disk state with pure gate testing.

### 2. Backward-Compatible `judge_config_fingerprint` Support Across M1–M4

- **Decision**: Add `judge_config_fingerprint: str | None = None` as an optional nullable field to `RunRecord`, `RunManifestEntry` (populated automatically by `RunManifestEntry.from_run_record`), and `OrchestratorConfig` in `src/evalforge_maestro/types.py`.
- **Rationale**:
  - Preserves 100% backward compatibility with all persisted Milestone 1 and Milestone 2 `.evalforge/runs/*.json` and `.evalforge/manifest.jsonl` files (`extra="forbid"` validates cleanly because missing keys fall back to default `None`).
  - Enables Milestone 3 drift detection and tests to exercise all three required provenance drift dimensions (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`) end-to-end without waiting for Milestone 4's LiteLLM judge subsystem.
  - Preserves pinned signatures on `EvaluationOrchestrator.arun` and `EvaluationOrchestrator.run` in `tests/test_api_stability.py` because judge fingerprint configuration enters through `OrchestratorConfig` (already passed as `config`).
- **Alternatives Considered**:
  - Deferring `judge_config_fingerprint` schema support until M4: rejected because `docs/intent.md` Section 5.2 (M3) and `spec.md` `FR-008`/`FR-009` require M3 drift detection and gate tests to verify `judge_config_fingerprint` mismatches now.
  - Adding a new keyword parameter to `EvaluationOrchestrator.arun`: avoided to minimize churn on pinned M1 entrypoints, while M4 can optionally inspect judge metric metadata in addition to `OrchestratorConfig.judge_config_fingerprint`.

### 3. Signed Regression Math, IEEE-754 Epsilon Tolerance, and Determinism

- **Decision**: Introduce `round_delta(value: float) -> float` in `src/evalforge_maestro/_canonical.py` alongside `round_score` (`SCORE_ROUND_DECIMALS = 6`, `FLOAT_EPSILON = 1e-9`). Unlike `round_score` (which clamps values to `[0.0, 1.0]`), `round_delta` permits finite signed values across arbitrary numeric deltas/slopes while snapping values with `abs(value) <= FLOAT_EPSILON` (including IEEE-754 `-0.0` or `0.8 - 0.8 + noise`) strictly to positive `+0.0`. All threshold comparisons use `FLOAT_EPSILON` consistently:
  - Inter-metric divergence: `(max_score - min_score) > disagreement_threshold + FLOAT_EPSILON` (`0.8 - 0.5 = 0.30000000000000004` does NOT falsely exceed `0.3`).
  - Baseline drop breach: `(baseline - candidate) > max_regression_drop + FLOAT_EPSILON`.
  - Masked single-case drop: `(baseline - candidate) >= case_drop_warning_threshold - FLOAT_EPSILON`.
  - Minimum metric floor breach: `mean_score < floor - FLOAT_EPSILON`.
  - Trend slope classification: `slope < -threshold - FLOAT_EPSILON` (`DEGRADING`), `slope > threshold + FLOAT_EPSILON` (`IMPROVING`), else `STABLE`.
  - Inconclusive rate check: `inconclusive_rate > max_inconclusive_rate + FLOAT_EPSILON`.
- **Rationale**: Eliminates binary floating-point representation boundary bugs (e.g., `0.8 - 0.5 == 0.30000000000000004`, `0.85 - 0.80 == 0.050000000000000044`, `-0.0` JSON serialization diffs) and matches Constitution Principle V.
- **Alternatives Considered**:
  - Reusing `round_score` for deltas/slopes: rejected because `round_score` clamps `[0.0, 1.0]` boundaries designed specifically for bounded scores.

### 4. Sliding Window History Resolution & OLS Trend Calculation

- **Decision**:
  - Accept runs via pure `analyze_trend(runs: Sequence[RunRecord | RunManifestEntry], *, window: int = 5, dataset_id: str | None = None, all_datasets: bool = False, model_id: str | None = None, metric_ids: Sequence[str] | None = None, slope_threshold: float = 0.01) -> TrendReport`. Extending `RunManifestEntry` with nullable `model_id` and `judge_config_fingerprint` enables manifest-only filtering and within-window drift inspection without loading heavy `RunRecord` traces from disk.
  - Validate `window >= 2` (raising `ConfigurationError` otherwise) and `slope_threshold > 0.0`.
  - Sort candidate runs deterministically by `(entry.timestamp, entry.run_id)` ascending (oldest -> newest).
  - Default dataset scoping when `dataset_id is None and not all_datasets`: if at least one run exists, lock onto the most recent run's `dataset_id` (`ordered_runs[-1].dataset_id`) before taking the trailing `[-window:]` slice!
  - Within-window provenance drift checks adjacent chronological run pairs `(ordered_window[i], ordered_window[i + 1])` across `dataset_fingerprint`, `metric_versions` / metric sets, and `judge_config_fingerprint` (capturing step transitions and rollbacks) plus per-run `dataset_capped`.
  - Ordinary least-squares regression over valid non-null numeric aggregate points `(0, y_0), (1, y_1), ..., (m-1, y_{m-1})`: for `m >= 2`, denominator `m * (m * m - 1) / 12.0` is strictly positive, eliminating division-by-zero; for `m < 2`, set `slope = None` and `direction = TrendDirection.INSUFFICIENT_DATA`.
- **Rationale**:
  - Sequential index `0..m-1` matches `spec.md` Assumptions ("invariant to pauses between runs").
  - Extending `RunManifestEntry` with optional backward-compatible `model_id: str | None = None` and `judge_config_fingerprint: str | None = None` enables trend analysis and within-window drift detection directly from compact `.evalforge/manifest.jsonl` or full `RunRecord` objects without loading massive trace arrays into RAM.
- **Alternatives Considered**:
  - Wall-clock delta OLS slopes (`days` or `seconds` on x-axis): rejected because burst runs milliseconds apart would cause near-zero denominators and non-deterministic slopes.

### 5. `QualityGate` 100%-Branch Decision Architecture & `NOT_APPLICABLE` Safety

- **Decision**: Structure `QualityGate.evaluate(...)` in `src/evalforge_maestro/regression/gate.py` around explicit, discrete helper evaluations with strict precedence `FAIL > INCONCLUSIVE > WARNING > PASS`:
  - `failure_reasons` non-empty -> `GateDecision.FAIL`
  - elif `inconclusive_reasons` non-empty -> `GateDecision.INCONCLUSIVE`
  - elif `warning_reasons` non-empty -> `GateDecision.WARNING`
  - else -> `GateDecision.PASS`
  Distinguish `NOT_APPLICABLE` (`applicable_count == 0 and inconclusive_count == 0`) from `INCONCLUSIVE` (`inconclusive_count > 0`, or zero applicable scores across the entire run, or a metric explicitly listed in `policy.min_metric_scores` / `policy.max_metric_regression_drops` having `mean_score is None`).
- **Rationale**:
  - Prevents clean answer-only runs carrying an optional unpopulated retrieval metric from spuriously tripping `INCONCLUSIVE`.
  - Avoids unreachable branches and ensures `pytest --cov=src/evalforge_maestro/regression/gate` achieves verified **100% branch coverage** alongside `metrics/`.
- **Alternatives Considered**:
  - Mapping `MetricStatus` directly onto gate decisions: rejected because `MetricStatus` includes `NOT_APPLICABLE`, which is invalid as a release `QualityGate` outcome (`spec.md` `FR-017` specifies exactly `PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`).
