# Phase 1 Data Model: Statistical & Embedding Similarity Metrics

**Feature**: `007-statistical-embedding-metrics`  
**Canonical Location**: `src/evalforge_maestro/types.py` (Single Schema Source of Truth, `schema_version = "1.0"`)

## 1. Embedding Domain Models (`types.py`)

### 1.1 `EmbeddingAggregation` (`str, Enum`)
- Values:
  - `MAX = "max"` (default: highest clamped cosine similarity between output and any non-blank retrieved chunk)
  - `MEAN = "mean"` (arithmetic mean of clamped cosine similarities across all non-blank retrieved chunks)

### 1.2 `EmbeddingConfig` (`_StrictModel`)
Secret-free, canonical configuration matching `JudgeConfig` conventions:
- `schema_version: Literal["1.0"] = SCHEMA_VERSION`
- `model: str = Field(default="mock-embedding", min_length=1)`
- `api_base: str | None = None` (validated HTTP/HTTPS URL via `_validate_http_api_base`)
- `pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)` (6-decimal rounded via `round_score`)
- `aggregation: EmbeddingAggregation = EmbeddingAggregation.MAX`
- `max_retries: int = Field(default=2, ge=0, le=10)`
- `retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)`
- `timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)`
- `local_only: bool = False`
- `mock_mode: bool = False`
- `extra_params: dict[str, Any] = Field(default_factory=dict)` (JSON-serializable, scrubbed via `redact_secrets`)
- Methods/Properties:
  - `redacted_dict() -> dict[str, Any]`
  - `@property def fingerprint(self) -> str` (`canonical_sha256(self.redacted_dict())`)

### 1.3 `ResolvedEmbeddingSettings` (`_StrictModel`, for `CLIResolvedConfig.embedding`)
Matches `ResolvedJudgeSettings` pattern (never holds raw `api_key`):
- `model: str = "mock-embedding"`
- `api_base: str | None = None`
- `api_key_configured: bool = False`
- `pass_threshold: float = 0.5`
- `aggregation: EmbeddingAggregation = EmbeddingAggregation.MAX`
- `max_retries: int = 2`
- `retry_backoff_seconds: float = 0.5`
- `timeout_seconds: float = 30.0`
- `mock_mode: bool = False`
- `local_only: bool = False`

---

## 2. Statistical Distribution Models (`types.py`)

### 2.1 `SignificanceStatus` (`str, Enum`)
- `SIGNIFICANT_IMPROVEMENT = "significant_improvement"`
- `SIGNIFICANT_REGRESSION = "significant_regression"`
- `NOT_SIGNIFICANT = "not_significant"`
- `INSUFFICIENT_DATA = "insufficient_data"`

### 2.2 `StatisticalMethod` (`str, Enum`)
- `PAIRED_T_CASE = "paired_t_case"`
- `WELCH_T_RUN = "welch_t_run"`
- `ONE_SAMPLE_T_RUN = "one_sample_t_run"`

### 2.3 `StatisticalSummary` (`_StrictModel`)
Immutable inferential statistics payload attached to `MetricComparison`:
- `method: StatisticalMethod`
- `confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)`
- `sample_size: int = Field(ge=0)` (number of paired observations for `paired_t_case`, or `min(K, M)` / repeated `N` summary count, documented clearly)
- `baseline_sample_size: int = Field(ge=0)`
- `candidate_sample_size: int = Field(ge=0)`
- `excluded_pair_count: int = Field(default=0, ge=0)`
- `mean_delta: float | None = Field(default=None, ge=-1.0, le=1.0)` (`round_delta`)
- `delta_std: float | None = Field(default=None, ge=0.0)` (`round_score`)
- `standard_error: float | None = Field(default=None, ge=0.0)` (`round_score`)
- `baseline_std: float | None = Field(default=None, ge=0.0)` (`round_score`)
- `candidate_std: float | None = Field(default=None, ge=0.0)` (`round_score`)
- `ci_low: float | None = Field(default=None, ge=-1.0, le=1.0)` (`round_delta`, clamped to `[-1.0, 1.0]`)
- `ci_high: float | None = Field(default=None, ge=-1.0, le=1.0)` (`round_delta`, clamped to `[-1.0, 1.0]`)
- `p_value: float | None = Field(default=None, ge=0.0, le=1.0)` (`round_score`)
- `effect_size: float | None = None` (`round_delta`-like 6-decimal float, finite check rejecting `NaN`/`Inf` & `bool`)
- `degrees_of_freedom: float | None = Field(default=None, ge=0.0)`
- `significance: SignificanceStatus`
- `statistically_significant: bool = False`
- `explanation: str = Field(min_length=1)`

### 2.4 `RunCohortSummary` (`_StrictModel`)
Captures provenance when `compare_run_cohorts` evaluates multiple baseline and/or candidate runs:
- `baseline_run_ids: list[str] = Field(min_length=1)`
- `candidate_run_ids: list[str] = Field(min_length=1)`
- `baseline_run_count: int = Field(ge=1)`
- `candidate_run_count: int = Field(ge=1)`
- `baseline_names: list[str] = Field(default_factory=list)`

---

## 3. Backward-Compatible Extensions to Existing Contracts (`types.py`)

All new fields carry defaults so existing persisted `1.0` JSON artifacts continue validating untouched:

### 3.1 `RunRecord`, `RunManifestEntry`, `BaselineEntry` & `DriftCategory`
- Existing fields preserved unchanged (`schema_version="1.0"`, `judge_config_fingerprint`, etc.).
- Added backward-compatible optional provenance tracking for embedding configurations:
  - `RunRecord.embedding_config_fingerprint: str | None = None`
  - `RunManifestEntry.embedding_config_fingerprint: str | None = None`
  - `OrchestratorConfig.embedding_config_fingerprint: str | None = None`
  - `BaselineEntry.embedding_config_fingerprint: str | None = None`
  - `DriftCategory.EMBEDDING_CONFIG = "embedding_config"` (triggers drift warning only when non-matching embedding config fingerprints differ between compared runs; historical `None == None` emits zero drift)

### 3.2 `MetricComparison`
- Existing fields preserved unchanged (`metric_id`, `baseline_version`, `candidate_version`, `baseline_score`, `candidate_score`, `delta`, `direction`, `status_count_deltas`).
- Added:
  - `statistics: StatisticalSummary | None = None`
  - `case_statistics: StatisticalSummary | None = None` (populated in multi-run cohorts with aligned case-level paired inference over trial-averaged case scores; `None` when single-run 1v1 already uses `statistics` for `paired_t_case`)

### 3.3 `RunComparisonReport`
- Existing fields preserved unchanged (`schema_version="1.0"`, `baseline_run_id`, `candidate_run_id`, ...).
- Added:
  - `cohort: RunCohortSummary | None = None` (present for multi-run cohort comparisons, `None` for single-run pairwise `compare_runs`).

### 3.4 `QualityGatePolicy`
- Existing fields preserved unchanged.
- Added:
  - `confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)` (strict finite bool-rejected float)
  - `min_statistical_samples: int = Field(default=2, ge=2)` (strict non-bool `int >= 2`)
  - `fail_on_significant_regression: bool = False`

### 3.5 `CLIResolvedConfig`
- Existing fields preserved unchanged.
- Added:
  - `repeats: int = Field(default=1, ge=1, le=100)`
  - `baseline_runs: list[str] = Field(default_factory=list)`
  - `embedding: ResolvedEmbeddingSettings = Field(default_factory=ResolvedEmbeddingSettings)`

### 3.6 `ReportDocument`
- When `run --repeats N` (`N >= 2`) executes, `ReportDocument.evaluation` holds the representative canonical `RunRecord` (latest repeat, preserving `report_kind == ReportKind.RUN` invariance), `ReportDocument.cohort_run_ids: list[str] = Field(default_factory=list)` lists all `N` persisted run IDs, and `ReportDocument.cohort_aggregates: dict[str, AggregateMetricSummary] = Field(default_factory=dict)` captures the pooled cohort summaries evaluated by `QualityGate.evaluate_cohort(...)` (while `ReportDocument.comparison` captures the cohort regression comparison when `--baseline` is provided). When `--repeats == 1`, both new fields default to empty (`[]` and `{}`), zero breaking change!
