# Data Model & SQLite Schema: Feature 009 (`009-sqlite-query-index`)

**Spec**: [spec.md](spec.md) | **Canonical Types Location**: `src/evalforge_maestro/types.py`

## 1. Pydantic v2 Contracts (`src/evalforge_maestro/types.py`)

### 1.1 `RunSortOrder(str, Enum)`
- `TIMESTAMP_DESC = "timestamp_desc"`
- `TIMESTAMP_ASC = "timestamp_asc"`
- `RUN_ID_ASC = "run_id_asc"`

### 1.2 `RunQueryFilter(_StrictModel)`
Typed filter parameters for `SQLiteRunIndex.query_runs`:
- `dataset_id: str | None = None`
- `dataset_version: str | None = None`
- `run_ids: list[str] | None = None`
- `model_id: str | None = None`
- `system_version: str | None = None`
- `baseline_name: str | None = None`
- `metric_id: str | None = None`
- `min_mean_score: float | None = Field(default=None, ge=0.0, le=1.0)` (rejects bool/NaN/Inf; requires `metric_id` when set!)
- `max_mean_score: float | None = Field(default=None, ge=0.0, le=1.0)` (rejects bool/NaN/Inf; requires `metric_id` when set!)
- `has_mandatory_failures: bool | None = None`
- `since: datetime | None = None` (UTC normalized)
- `until: datetime | None = None` (UTC normalized)
- `order_by: RunSortOrder = RunSortOrder.TIMESTAMP_DESC`
- `limit: int = Field(default=50, ge=1, le=1000)` (strict int)
- `offset: int = Field(default=0, ge=0)` (strict int)
- Model validator ensures: `min_mean_score <= max_mean_score` if both set; `since <= until` if both set; `metric_id` is required when `min_mean_score` or `max_mean_score` is specified.

### 1.3 `CaseQueryFilter(_StrictModel)`
Typed filter parameters for `SQLiteRunIndex.query_cases`:
- `run_id: str | None = None`
- `dataset_id: str | None = None`
- `case_id: str | None = None`
- `metric_id: str | None = None`
- `status: MetricStatus | None = None`
- `mandatory_only: bool = False`
- `min_score: float | None = Field(default=None, ge=0.0, le=1.0)`
- `max_score: float | None = Field(default=None, ge=0.0, le=1.0)`
- `has_errors: bool | None = None`
- `has_anomaly_flags: bool | None = None`
- `limit: int = Field(default=100, ge=1, le=5000)`
- `offset: int = Field(default=0, ge=0)`
- Model validator ensures `min_score <= max_score` if both set.

### 1.4 Query Output Models (`_StrictModel` + `SCHEMA_VERSION`)
- **`IndexedRunSummary`**:
  `schema_version: Literal["1.0"]`, `run_id: str`, `timestamp: datetime`, `dataset_id: str`, `dataset_version: str | None`, `dataset_fingerprint: str`, `evaluated_case_count: int`, `dataset_capped: bool`, `system_version: str | None`, `model_id: str | None`, `config_fingerprint: str | None`, `has_mandatory_failures: bool`, `mandatory_failed_case_ids: list[str]`, `baseline_names: list[str]`, `aggregate_scores: dict[str, float | None]`, `status_counts: dict[MetricStatus, int]`.
- **`IndexedCaseMetricRow`**:
  `schema_version: Literal["1.0"]`, `run_id: str`, `timestamp: datetime`, `dataset_id: str`, `model_id: str | None`, `system_version: str | None`, `case_id: str`, `metric_id: str`, `metric_version: str`, `status: MetricStatus`, `score: float | None`, `mandatory: bool`, `elapsed_seconds: float`, `has_errors: bool`, `anomaly_count: int`, `explanation: str`.
- **`IndexedMetricPoint`**:
  `schema_version: Literal["1.0"]`, `metric_id: str`, `run_id: str`, `timestamp: datetime`, `dataset_id: str`, `model_id: str | None`, `system_version: str | None`, `mean_score: float | None`, `applicable_count: int`, `pass_count: int`, `fail_count: int`.
- **`SQLiteIndexStatus`**:
  `schema_version: Literal["1.0"]`, `db_path: str`, `exists: bool`, `corrupt: bool`, `in_sync: bool`, `index_schema_version: str`, `db_size_bytes: int`, `canonical_run_count: int`, `indexed_run_count: int`, `baseline_count: int`, `pending_run_ids: list[str]`, `extra_indexed_run_ids: list[str]`, `stale_reason: str | None = None`.
- **CLI Response Envelopes (`RunQueryPayload`, `CaseQueryPayload`)**:
  `schema_version: Literal["1.0"]`, `storage_dir: str`, `total_returned: int`, `runs: list[IndexedRunSummary]` / `cases: list[IndexedCaseMetricRow]`.

---

## 2. Derived SQLite DDL Schema (`index_schema_version = "1"`)

```sql
CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    timestamp_iso TEXT NOT NULL,
    timestamp_epoch REAL NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version TEXT,
    dataset_fingerprint TEXT NOT NULL,
    evaluated_case_count INTEGER NOT NULL,
    dataset_capped INTEGER NOT NULL,
    system_version TEXT,
    model_id TEXT,
    config_fingerprint TEXT,
    has_mandatory_failures INTEGER NOT NULL,
    mandatory_failed_case_ids_json TEXT NOT NULL,
    status_counts_json TEXT NOT NULL,
    package_version TEXT NOT NULL,
    run_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    metric_id TEXT NOT NULL,
    metric_version TEXT NOT NULL,
    mean_score REAL,
    applicable_count INTEGER NOT NULL,
    pass_count INTEGER NOT NULL,
    fail_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    inconclusive_count INTEGER NOT NULL,
    not_applicable_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, metric_id)
);

CREATE TABLE IF NOT EXISTS case_results (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    metric_version TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL,
    mandatory INTEGER NOT NULL,
    elapsed_seconds REAL NOT NULL,
    has_errors INTEGER NOT NULL,
    anomaly_count INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id, metric_id)
);

CREATE TABLE IF NOT EXISTS baselines (
    baseline_name TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    pinned_at TEXT NOT NULL
);
```

- **Ordering & Pagination**:
  - `query_runs` uses `order_by` (`timestamp_desc` ties broken by `run_id ASC`, `timestamp_asc` ties broken by `run_id ASC`, or `run_id_asc`) and populates sorted `IndexedRunSummary.baseline_names` without duplicating rows when filtering by `baseline_name`.
  - `query_cases` orders rows deterministically by `(runs.timestamp_epoch DESC, case_results.run_id ASC, case_results.case_id ASC, case_results.metric_id ASC)`.
  - `metric_history` selects the most recent `limit` (`>= 1`) matching runs and returns `IndexedMetricPoint` entries ordered chronologically ascending `(timestamp_epoch ASC, run_id ASC)`.

Indexes (`idx_runs_dataset_ts`, `idx_runs_model`, `idx_run_metrics_metric_score`, `idx_case_results_metric_status`, `idx_case_results_case`, `idx_baselines_run_id`) support millisecond filtering without full table scans. `index_meta` tracks `index_schema_version = "1"`, `baselines_sha256`, and `last_synced_at`.
