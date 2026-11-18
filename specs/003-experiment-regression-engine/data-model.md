# Data Model: Milestone 3 — Experiment & Regression Engine

**Feature**: `003-experiment-regression-engine` | **Date**: 2026-11-18 | **Schema Version**: `"1.0"`

All Milestone 3 domain models are strict Pydantic v2 models (`extra="forbid"`, `validate_assignment=True`) defined strictly inside `src/evalforge_maestro/types.py`. Signed deltas and regression slopes normalize values within `1e-9` to `+0.0` (suppressing `-0.0`) and round to 6 decimal places via `_canonical.round_delta`. Existing M1/M2 JSON artifacts remain valid without migration.

---

## 1. Backward-Compatible Additive Extensions to M1 Contracts

### `OrchestratorConfig` (extended)
- `judge_config_fingerprint: str | None = None` — optional redacted hash/identifier of active judge configuration (`_ensure_non_empty_str` when string; default `None`).

### `RunRecord` (extended)
- `judge_config_fingerprint: str | None = None` — optional redacted hash/identifier of judge configuration persisted alongside run provenance (`_ensure_non_empty_str` when string; default `None`).

### `RunManifestEntry` (extended)
- `model_id: str | None = None` — copied from `RunRecord.model_id` by `from_run_record` (defaults to `None` when loading M1/M2 manifest lines).
- `judge_config_fingerprint: str | None = None` — copied from `RunRecord.judge_config_fingerprint` by `from_run_record` (defaults to `None` when loading M1/M2 manifest lines).

---

## 2. Enumerations

| Enum | Values | Notes |
|---|---|---|
| `GateDecision` | `"PASS"`, `"FAIL"`, `"WARNING"`, `"INCONCLUSIVE"` | Exclusive `QualityGate` release acceptance outcomes (strict precedence `FAIL > INCONCLUSIVE > WARNING > PASS`). |
| `ComparisonDirection` | `"IMPROVED"`, `"REGRESSED"`, `"UNCHANGED"`, `"ADDED"`, `"REMOVED"`, `"INCONCLUSIVE"` | Aggregate and per-case metric delta classifications. |
| `TrendDirection` | `"IMPROVING"`, `"STABLE"`, `"DEGRADING"`, `"INSUFFICIENT_DATA"` | Sliding window linear trajectory outcomes. |
| `DriftCategory` | `"DATASET_FINGERPRINT"`, `"METRIC_VERSION"`, `"METRIC_SET"`, `"JUDGE_CONFIG"`, `"DATASET_CAPPED"`, `"CASE_SET_MISMATCH"` | Provenance/measurement comparability drift classes. |
| `AnomalyType` | `"METRIC_DISAGREEMENT"`, `"AGGREGATE_MASKED_DROP"`, `"MANDATORY_CASE_FAILURE"`, `"INCONCLUSIVE_SPIKE"`, `"DATASET_CAPPED"` | Anti-masking & evidence-hygiene anomaly classes. |
| `AnomalySeverity` | `"WARNING"`, `"FAIL"` | Advisory vs. blocking anomaly severity. |
| `AnomalyScope` | `"RUN"`, `"CASE"` | Macro run scope vs. single evaluation case scope. |

---

## 3. Baseline Persistence Entities (`.evalforge/baselines.json`)

### `BaselineEntry`
| Field | Type & Constraints | Description |
|---|---|---|
| `schema_version` | `Literal["1.0"] = "1.0"` | Contract version. |
| `name` | `str` (`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, no `".."`) | Safe baseline alias (e.g., `"default"`, `"v1.0-release"`). |
| `run_id` | `str` (`min_length=1`, trimmed non-empty) | Immutable referenced `RunRecord.run_id`. |
| `pinned_at` | `datetime` (UTC normalized) | Timestamp when baseline was pinned. |
| `note` | `str | None = None` | Optional annotation (trimmed if string; secret-redacted on persist). |
| `tags` | `list[str] = []` | Non-empty trimmed metadata labels. |
| `dataset_id` | `str` (`min_length=1`, trimmed non-empty) | Snapshot dataset identifier. |
| `dataset_version` | `str | None = None` | Snapshot dataset version. |
| `dataset_fingerprint` | `str` (`^[0-9a-f]{64}$`) | Canonical SHA-256 dataset digest from `RunRecord`. |
| `system_version` | `str | None = None` | Snapshot target `system_version`. |
| `model_id` | `str | None = None` | Snapshot target `model_id`. |
| `config_fingerprint` | `str | None = None` | Snapshot target `config_fingerprint`. |
| `judge_config_fingerprint` | `str | None = None` | Snapshot `judge_config_fingerprint`. |
| `metric_versions` | `dict[str, str] = {}` | Snapshot `metric_id -> metric_version`. |
| `aggregate_scores` | `dict[str, float | None] = {}` | Snapshot rounded `[0.0, 1.0]` aggregate mean scores (`_reject_bool_number`, `round_score`). |

### `BaselineRegistry`
| Field | Type & Constraints | Description |
|---|---|---|
| `schema_version` | `Literal["1.0"] = "1.0"` | Registry file format version. |
| `baselines` | `dict[str, BaselineEntry] = {}` | Mapping `name -> BaselineEntry`; validator enforces `key == entry.name` for every item. |

---

## 4. Drift & Anomaly Entities

### `DriftWarning`
| Field | Type & Constraints | Description |
|---|---|---|
| `category` | `DriftCategory` | Classification of provenance drift. |
| `metric_id` | `str | None = None` | Affected metric identifier (if metric-specific). |
| `baseline_run_id` | `str | None = None` | Baseline or earlier run identifier in transition. |
| `candidate_run_id` | `str | None = None` | Candidate or newer run identifier in transition. |
| `baseline_value` | `Any = None` | Strict JSON-serializable observed prior value. |
| `candidate_value` | `Any = None` | Strict JSON-serializable observed new value. |
| `explanation` | `str` (`min_length=1`, trimmed non-empty) | Clear description of comparability drift. |

### `AnomalyFlag`
| Field | Type & Constraints | Description |
|---|---|---|
| `anomaly_type` | `AnomalyType` | Specific anti-masking/hygiene category. |
| `severity` | `AnomalySeverity` | `WARNING` or `FAIL`. |
| `scope` | `AnomalyScope` | `RUN` or `CASE`. |
| `case_id` | `str | None = None` | Required non-empty string when `scope == CASE`. |
| `metric_ids` | `list[str] = []` | Non-empty metric identifiers involved. |
| `spread` | `float | None = None` | Finite magnitude (`round_delta`, rejecting `bool`/`NaN`/`Inf`). |
| `explanation` | `str` (`min_length=1`, trimmed non-empty) | Human-readable diagnostic reason. |

---

## 5. Pairwise Comparison Entities

### `MetricComparison`
| Field | Type & Constraints | Description |
|---|---|---|
| `metric_id` | `str` (`min_length=1`) | Evaluated metric identifier. |
| `baseline_version` | `str | None = None` | Metric version in baseline run (`None` if `ADDED`). |
| `candidate_version` | `str | None = None` | Metric version in candidate run (`None` if `REMOVED`). |
| `baseline_score` | `float | None` (`0.0 <= s <= 1.0`, `round_score`) | Baseline aggregate mean score. |
| `candidate_score` | `float | None` (`0.0 <= s <= 1.0`, `round_score`) | Candidate aggregate mean score. |
| `delta` | `float | None` (`-1.0 <= d <= 1.0`, `round_delta`) | Signed `candidate_score - baseline_score`; `None` if either score absent. |
| `direction` | `ComparisonDirection` | Directional outcome (`IMPROVED`, `REGRESSED`, `UNCHANGED`, `ADDED`, `REMOVED`, `INCONCLUSIVE`). |
| `status_count_deltas` | `dict[MetricStatus, int] = {}` | Strict integer deltas (`candidate - baseline`) per `MetricStatus`. |

### `CaseMetricDelta`
| Field | Type & Constraints | Description |
|---|---|---|
| `metric_id` | `str` (`min_length=1`) | Evaluated metric identifier. |
| `baseline_score` | `float | None` (`0.0..1.0`, `round_score`) | Baseline case score. |
| `candidate_score` | `float | None` (`0.0..1.0`, `round_score`) | Candidate case score. |
| `delta` | `float | None` (`-1.0..1.0`, `round_delta`) | Signed case delta when both numeric scores exist. |
| `baseline_status` | `MetricStatus | None = None` | Baseline case status. |
| `candidate_status` | `MetricStatus | None = None` | Candidate case status. |
| `regressed` | `bool = False` | `True` on `PASS -> FAIL` transition or `delta < -1e-9`. |
| `direction` | `ComparisonDirection` | Case-metric directional classification. |

### `CaseComparison`
| Field | Type & Constraints | Description |
|---|---|---|
| `case_id` | `str` (`min_length=1`) | Matched case identifier. |
| `mandatory` | `bool = False` | `True` if marked mandatory in baseline or candidate case. |
| `regressed` | `bool = False` | `True` if any metric regressed or execution errors introduced. |
| `mandatory_regressed` | `bool = False` | `True` if `mandatory` and either any candidate metric is `FAIL` or any metric regressed. |
| `error_introduced` | `bool = False` | `True` if baseline had zero execution errors and candidate has errors. |
| `error_resolved` | `bool = False` | `True` if baseline had execution errors and candidate has none. |
| `metrics` | `dict[str, CaseMetricDelta]` | Per-metric case comparisons keyed by `metric_id`. |

### `TargetChangeSummary` & `RunComparisonReport`
- `TargetChangeSummary`: captures non-drift contextual deltas across `system_version`, `model_id`, and adapter `config_fingerprint` (`*_changed: bool`, `baseline_*`, `candidate_*`).
- `RunComparisonReport`: `schema_version="1.0"`, `baseline_run_id`, `candidate_run_id`, `baseline_name`, `target_changes: TargetChangeSummary`, `metric_comparisons: dict[str, MetricComparison]`, `case_comparisons: list[CaseComparison]`, `matched_case_count: int >= 0`, `added_case_ids: list[str]`, `removed_case_ids: list[str]`, `regressed_case_ids: list[str]`, `mandatory_regressed_case_ids: list[str]`, `drift_warnings: list[DriftWarning]`, `anomalies: list[AnomalyFlag]`.

---

## 6. Sliding Window Trend Entities

### `TrendDataPoint`
- `run_id: str`, `timestamp: datetime` (UTC), `index: int >= 0` (strict int), `score: float | None` (`0.0..1.0`), `metric_version: str | None = None`, `dataset_fingerprint: str` (`^[0-9a-f]{64}$`), `judge_config_fingerprint: str | None = None`.

### `MetricTrendSummary`
- `metric_id: str`, `window_runs: int >= 0`, `valid_points: int >= 0`, `missing_points: int >= 0`, `slope: float | None = None` (`round_delta`), `direction: TrendDirection`, `first_score: float | None`, `last_score: float | None`, `min_score: float | None`, `max_score: float | None`, `mean_score: float | None` (all `0.0..1.0` rounded), `points: list[TrendDataPoint]`, `explanation: str` (`min_length=1`).
- **Consistency Invariant**: if `valid_points < 2`, then `slope is None` and `direction == TrendDirection.INSUFFICIENT_DATA`.

### `TrendReport`
- `schema_version: Literal["1.0"] = "1.0"`, `window: int >= 2` (strict int), `dataset_id_filter: str | None = None`, `model_id_filter: str | None = None`, `inspected_run_ids: list[str]`, `slope_threshold: float` (`0.0 < t <= 1.0`), `metrics: dict[str, MetricTrendSummary]`, `drift_warnings: list[DriftWarning]`.

---

## 7. Quality Gate Entities

### `QualityGatePolicy`
| Field | Default | Bounds & Semantics |
|---|---|---|
| `schema_version` | `"1.0"` | Strict `"1.0"`. |
| `min_score` | `None` | Optional global minimum mean score floor (`0.0..1.0`). |
| `min_metric_scores` | `{}` | Per-metric minimum mean score floors (`0.0..1.0`; requires metric valid score). |
| `max_regression_drop` | `0.05` | Blocking drop tolerance vs. baseline (`0.0..1.0`). |
| `max_metric_regression_drops` | `{}` | Per-metric blocking regression drop overrides (`0.0..1.0`). |
| `max_regressed_cases` | `None` | Optional cap on regressed cases vs. baseline (`>= 0`, strict int). |
| `disagreement_threshold` | `0.3` | Inter-metric spread threshold triggering `METRIC_DISAGREEMENT` (`0.0..1.0`). |
| `case_drop_warning_threshold` | `0.25` | Single-case masked drop threshold (`0.0..1.0`). |
| `trend_slope_threshold` | `0.01` | Magnitude dividing `STABLE` from `DEGRADING`/`IMPROVING` (`0.0 < t <= 1.0`). |
| `max_inconclusive_rate` | `0.10` | Inconclusive case rate cutoff between `WARNING` and `INCONCLUSIVE` (`0.0..1.0`). |
| `require_baseline` | `False` | Emit `INCONCLUSIVE` when baseline comparison is absent or uncomparable. |
| `require_trend` | `False` | Emit `INCONCLUSIVE` when trend report is absent or below `min_trend_runs`. |
| `min_trend_runs` | `2` | Minimum runs inspected when `require_trend=True` (`>= 2`, strict int). |
| `soft_regression_warning` | `False` | Emit `WARNING` for drops inside `(1e-9, max_regression_drop]`. |
| `fail_on_drift` | `False` | Escalate any `DriftWarning` from `WARNING` to `FAIL`. |
| `fail_on_anomaly` | `False` | Escalate any non-mandatory `WARNING` anomaly from `WARNING` to `FAIL`. |
| `fail_on_degrading_trend` | `False` | Escalate any `DEGRADING` trend metric from `WARNING` to `FAIL`. |
| `fail_on_mandatory_regression` | `True` | Escalate `mandatory_regressed_case_ids` in pairwise comparisons to `FAIL`. |

### `GateRuleCheck` & `QualityGateResult`
- `GateRuleCheck`: `rule_id: str`, `status: GateDecision`, `message: str`, `metric_id: str | None = None`, `observed: float | int | str | None = None`, `threshold: float | int | str | None = None`. (Rejects `bool` and non-finite floats on `observed`/`threshold`.)
- `QualityGateResult`: `schema_version="1.0"`, `decision: GateDecision`, `candidate_run_id: str`, `baseline_run_id: str | None = None`, `passed: bool`, `blocking: bool`, `inconclusive_rate: float` (`0.0..1.0`, `round_score`), `checks: list[GateRuleCheck]`, `failure_reasons: list[str]`, `inconclusive_reasons: list[str]`, `warning_reasons: list[str]`, `drift_warnings: list[DriftWarning]`, `anomalies: list[AnomalyFlag]`, `summary: str`.
- **Consistency Invariant**: `passed == (decision == GateDecision.PASS)` and `blocking == (decision == GateDecision.FAIL)`.
