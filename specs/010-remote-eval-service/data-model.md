# Data Model & HTTP Contracts: Feature 010 (`010-remote-eval-service`)

**Spec**: [spec.md](spec.md) | **Canonical Types Location**: `src/evalforge_maestro/types.py`

## 1. Pydantic v2 Contracts (`src/evalforge_maestro/types.py`)

### 1.1 `ServiceConfig(_StrictModel)`
- `host: str = Field(default="127.0.0.1", min_length=1)`
- `port: int = Field(default=8787, ge=0, le=65535)` (strict int; `0` allows OS-assigned ephemeral loopback port)
- `storage_dir: str = Field(default=".evalforge", min_length=1)`
- `local_only: bool = True`
- `block_pii: bool = False`
- `mock_mode: bool = False`
- `max_request_bytes: int = Field(default=10_485_760, ge=1024, le=104_857_600)` (strict int, 1 KiB–100 MiB)
- `auth_token_configured: bool = False` (metadata boolean only; raw token NEVER persisted/serialized in `ServiceConfig`!)

### 1.2 `ServiceHealthResponse(_StrictModel)`
- `schema_version: Literal["1.0"] = SCHEMA_VERSION`
- `status: Literal["ok"] = "ok"`
- `package_version: str = Field(min_length=1)`
- `storage_dir: str = Field(min_length=1)`
- `local_only: bool`
- `mock_mode: bool`
- `indexed_run_count: int = Field(ge=0)`
- `canonical_run_count: int = Field(ge=0)`

### 1.3 `ServiceErrorResponse(_StrictModel)`
- `schema_version: Literal["1.0"] = SCHEMA_VERSION`
- `status_code: int = Field(ge=400, le=599)`
- `error_type: str = Field(min_length=1)`
- `message: str = Field(min_length=1)` (`scrub_secret_text` applied)
- `hint: str | None = None` (`scrub_secret_text` applied)

### 1.4 `ServiceOtelIngestRequest` & `ServiceOtelIngestResponse`
- **`ServiceOtelIngestRequest(_StrictModel)`**:
  `payload: Any`, `extractors: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)`, `dataset: list[EvaluationCase] | None = None`, `case_id_map: dict[str, str] | None = None`, `system_version: str | None = None`, `model_id: str | None = None`.
- **`ServiceOtelIngestResponse(_StrictModel)`**:
  `schema_version: Literal["1.0"] = SCHEMA_VERSION`, `count: int = Field(ge=0)`, `executions: list[ExecutionResult]`.

### 1.5 `ServiceEvaluateRequest` & `ServiceEvaluateResponse`
- **`ServiceEvaluateRequest(_StrictModel)`**:
  `cases: list[EvaluationCase] = Field(min_length=1)`,
  `executions: list[ExecutionResult] | None = None`,
  `otel_payload: Any = None`,
  `otel_extractors: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)`,
  `case_id_map: dict[str, str] | None = None`,
  `dataset_id: str = Field(default="remote-eval", min_length=1)`,
  `dataset_version: str | None = None`,
  `metrics: list[MetricSpecConfig] = Field(default_factory=list)`,
  `judge: JudgeConfig | None = None`,
  `embedding: EmbeddingConfig | None = None`,
  `gate: QualityGatePolicy = Field(default_factory=QualityGatePolicy)`,
  `max_context_chars: int | None = Field(default=None, ge=1)`,
  `max_concurrency: int = Field(default=4, ge=1, le=64)`,
  `seed: int | None = None`,
  `system_version: str | None = None`,
  `model_id: str | None = None`,
  `run_id: str | None = None`,
  `persist: bool = False`,
  `include_markdown: bool = False`.
  Model validator: requires **exactly one** of `executions` (`is not None`) or `otel_payload` (`is not None`), raising `ValueError` if both or neither are given.
- **`ServiceEvaluateResponse(_StrictModel)`**:
  `schema_version: Literal["1.0"] = SCHEMA_VERSION`,
  `persisted: bool`,
  `evaluation: RunRecord`,
  `gate: QualityGateResult`,
  `report: ReportDocument`,
  `markdown: str | None = None`.

### 1.6 `ServiceCompareRequest`, `ServiceCompareResponse`, `ServiceReportRequest`, `ServiceReportResponse`
- **`ServiceCompareRequest(_StrictModel)`**:
  `candidate_run_id: str | None = None`,
  `candidate_run_ids: list[str] | None = None`,
  `baseline_ref: str = Field(default="default", min_length=1)`,
  `baseline_run_ids: list[str] | None = None`,
  `policy: QualityGatePolicy = Field(default_factory=QualityGatePolicy)`,
  `include_markdown: bool = False`.
  Model validator requires `candidate_run_id` or non-empty `candidate_run_ids`.
- **`ServiceCompareResponse(_StrictModel)`**:
  `schema_version: Literal["1.0"] = SCHEMA_VERSION`,
  `comparison: RunComparisonReport`,
  `gate: QualityGateResult`,
  `report: ReportDocument`,
  `markdown: str | None = None`.
- **`ServiceReportRequest(_StrictModel)`**:
  `run_id: str | None = None`,
  `compare_run_id: str | None = None`,
  `baseline_ref: str | None = None`,
  `trend_window: int | None = Field(default=None, ge=2)`,
  `dataset_id: str | None = None`,
  `model_id: str | None = None`,
  `title: str | None = None`,
  `include_markdown: bool = True`.
  Model validator ensures `run_id`, `compare_run_id`, or `trend_window` is provided (`trend_window` strictly `>= 2`).
- **`ServiceReportResponse(_StrictModel)`**:
  `schema_version: Literal["1.0"] = SCHEMA_VERSION`,
  `report: ReportDocument`,
  `markdown: str | None = None`.
