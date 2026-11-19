# Data Model: Milestone 5 — CLI, Reporting & CI Integration (`005-cli-reporting-ci`)

**Date**: 2026-11-19 | **Feature**: [spec.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/specs/005-cli-reporting-ci/spec.md)

All Milestone 5 data contracts live exclusively in `src/evalforge_maestro/types.py` as strict Pydantic v2 models (`extra="forbid"`, immutable/validated) extending M1–M4 schemas without breaking existing persisted `.evalforge/` artifacts or M4 `JudgeConfig` fingerprints.

---

## 1. Enumerations

### `ConfigSourceTier(str, Enum)`
Resolution provenance tier for every effective setting:
- `CLI = "cli"` (highest precedence — CLI flags)
- `ENV = "env"` (`EVALFORGE_*` or provider API key from OS environment)
- `ENV_FILE = "env_file"` (explicit `--env-file <path>` filling env vars absent from OS env)
- `FILE = "file"` (`evalforge.toml` discovered non-recursively in CWD or explicit `--config`)
- `DEFAULT = "default"` (built-in default)

### `TargetType(str, Enum)`
Supported target execution/replay modes configured in CLI or `evalforge.toml`:
- `CALLABLE = "callable"`
- `RAG = "rag"`
- `DOCPIPE = "docpipe"`
- `REPLAY = "replay"`

### `ReportKind(str, Enum)`
Distinguishes top-level reporting workflows:
- `RUN = "run"`
- `COMPARE = "compare"`
- `TREND = "trend"`
- `CALIBRATE = "calibrate"`

### `EvidenceDecouplingCategory(str, Enum)`
Classifies intermediate retrieval vs. final answer decoupling issues surfaced per case:
- `ANSWER_PASSED_RETRIEVAL_FAILED = "answer_passed_retrieval_or_grounding_failed"`
- `RETRIEVAL_PASSED_ANSWER_FAILED = "retrieval_passed_answer_or_grounding_failed"`

---

## 2. Configuration Contracts (CLI Boundary & `CLIResolvedConfig`)

### `MetricSpecConfig(_StrictModel)`
Declarative single metric specification parsed from `--metric`, `EVALFORGE_METRICS`, or `[metrics]` in `evalforge.toml`:
- `metric_id: str` (non-empty stripped identifier)
- `params: dict[str, Any] = Field(default_factory=dict)` (validated JSON-safe dict; e.g., `k`, `match_parent_id`, `threshold`, `case_sensitive`, `strip_punctuation`, `schema`, `rubric`, `metric_id`, `metric_version`, `what_it_measures`, `require_reference`, `require_context`)

### `ResolvedSecurityConfig(_StrictModel)`
- `local_only: bool = False`
- `block_pii: bool = False`

### `ResolvedTargetConfig(_StrictModel)`
- `target_type: TargetType | None = None`
- `entrypoint: str | None = None` (`module.path:attribute`, secret-scrubbed if URL-like)
- `system_version: str | None = None`
- `model_id: str | None = None`
- `arg_mode: Literal["input", "case"] = "input"`
- `rag_extractors: dict[str, str] = Field(default_factory=dict)` (dotted extraction paths)
- `docpipe_mode: Literal["answer_detailed", "retrieve"] = "answer_detailed"`
- `docpipe_collection: str | None = None`
- `docpipe_top_k: int | None = Field(default=None, ge=1)`

### `ResolvedJudgeSettings(_StrictModel)`
Redacted snapshot of judge configuration resolved for display/reporting (inherits M4 `JudgeConfig` bounds while keeping `api_key` strictly masked to `"[REDACTED]"` or `None`):
- `model: str = "mock-judge"`
- `api_base: str | None = None` (validated/scrubbed HTTP/HTTPS URL with no userinfo/query/fragment)
- `api_key: str | None = None` (always `"[REDACTED]"` if configured, never plaintext)
- `temperature: float = Field(default=0.0, ge=0.0, le=2.0)`
- `pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)`
- `max_retries: int = Field(default=2, ge=0, le=10)`
- `retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)`
- `timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)`
- `prompt_version: str = "1.0"`
- `mock_mode: bool = False`
- `local_only: bool = False`
- `seed: int | None = None`
- `min_agreement: float | None = Field(default=None, ge=0.0, le=100.0)` (used by `calibrate`)

### `ResolvedLoggingConfig(_StrictModel)`
- `log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"`
- `log_json: bool = False`

### `ConfigSettingProvenance(_StrictModel)`
Records effective value and exact origin tier per configuration key:
- `key: str` (non-empty dotted path, e.g., `"execution.max_concurrency"`, `"judge.api_key"`)
- `value: Any` (redacted via `redact_secrets` / `scrub_secret_text`; secret keys always `"[REDACTED]"` when set)
- `source: ConfigSourceTier`
- `masked: bool = False`

### `CLIResolvedConfig(_StrictModel)`
Schema-versioned configuration resolution artifact (`config show --resolved` `--json` and internal CLI dispatch):
- `schema_version: Literal["1.0"] = "1.0"`
- `config_path: str | None = None` (resolved file path if `evalforge.toml` or `--config` loaded)
- `env_file_path: str | None = None` (explicit `--env-file` path if loaded)
- `storage_dir: str = ".evalforge"`
- `dataset: str | None = None`
- `dataset_id: str | None = None`
- `dataset_version: str | None = None`
- `executions_path: str | None = None`
- `run_id: str | None = None`
- `baseline: str | None = None`
- `trend_window: int | None = Field(default=None, ge=2)`
- `strict: bool = False`
- `target: ResolvedTargetConfig = Field(default_factory=ResolvedTargetConfig)`
- `metrics: list[MetricSpecConfig] = Field(default_factory=list)`
- `execution: OrchestratorConfig = Field(default_factory=OrchestratorConfig)`
- `judge: ResolvedJudgeSettings = Field(default_factory=ResolvedJudgeSettings)`
- `security: ResolvedSecurityConfig = Field(default_factory=ResolvedSecurityConfig)`
- `gate: QualityGatePolicy = Field(default_factory=QualityGatePolicy)`
- `logging: ResolvedLoggingConfig = Field(default_factory=ResolvedLoggingConfig)`
- `provenance: list[ConfigSettingProvenance] = Field(default_factory=list)`
- **Validation invariants**:
  - Model validator scrubs/masks `judge.api_key` and any provenance entry whose key denotes a credential (`api_key`, `token`, `secret`, `password`, `authorization`) so plaintext credentials can NEVER exist inside `CLIResolvedConfig`.

---

## 3. Reporting & CLI Output Contracts (`types.py` -> `reporting/` -> `cli/`)

### `DecoupledEvidenceDiagnostic(_StrictModel)`
Captures one test case exhibiting retrieval-vs-answer/groundedness decoupling:
- `case_id: str`
- `mandatory: bool = False`
- `category: EvidenceDecouplingCategory`
- `passed_metrics: list[str]`
- `failed_metrics: list[str]`
- `retrieved_chunk_ids: list[str] = Field(default_factory=list)`
- `explanation: str`

### `ReportDiagnosticsSummary(_StrictModel)`
Aggregated high-visibility diagnostics derived cleanly from run/comparison/trend/calibration artifacts:
- `mandatory_failed_case_ids: list[str] = Field(default_factory=list)`
- `decoupled_evidence_cases: list[DecoupledEvidenceDiagnostic] = Field(default_factory=list)`
- `anomaly_highlights: list[AnomalyFlag] = Field(default_factory=list)`
- `drift_highlights: list[DriftWarning] = Field(default_factory=list)`

### `CalibrationGateSummary(_StrictModel)`
Optional gate/threshold check outcome on `calibrate`:
- `min_agreement: float | None = Field(default=None, ge=0.0, le=100.0)`
- `observed_agreement: float | None = Field(default=None, ge=0.0, le=100.0)`
- `strict: bool = False`
- `valid_cases: int = Field(ge=0)`
- `inconclusive_cases: int = Field(ge=0)`
- `passed: bool`
- `reason: str`

### `ReportDocument(_StrictModel)`
Canonical top-level JSON report and CLI interchange payload (`run`, `compare`, `trend`, `calibrate`, `report`) enforcing **Three-Way Concern Separation**:
- `schema_version: Literal["1.0"] = "1.0"`
- `report_kind: ReportKind`
- `title: str`
- `generated_at: datetime` (UTC normalized)
- `evaluation: RunRecord | None = None` *(Concern 1: Evaluation)*
- `comparison: RunComparisonReport | None = None` *(Concern 2a: Pairwise Regression)*
- `trend: TrendReport | None = None` *(Concern 2b: Sliding Trend Regression)*
- `calibration: CalibrationReport | None = None` *(Judge Calibration Diagnostics)*
- `gate: QualityGateResult | None = None` *(Concern 3: Acceptance / Quality Gate)*
- `calibration_gate: CalibrationGateSummary | None = None` *(Calibrate threshold verdict)*
- `diagnostics: ReportDiagnosticsSummary = Field(default_factory=ReportDiagnosticsSummary)`
- **Validation invariants**:
  - When `report_kind == RUN`: `evaluation` MUST NOT be `None`, `calibration` MUST be `None`.
  - When `report_kind == COMPARE`: `comparison` MUST NOT be `None`.
  - When `report_kind == TREND`: `trend` MUST NOT be `None`.
  - When `report_kind == CALIBRATE`: `calibration` MUST NOT be `None`, `evaluation`/`comparison`/`trend` MUST be `None`.

### `BaselineCommandPayload(_StrictModel)`
Typed JSON payload emitted by `evalforge-maestro baseline --json`:
- `schema_version: Literal["1.0"] = "1.0"`
- `action: Literal["set", "list", "show", "delete"]`
- `entry: BaselineEntry | None = None`
- `baselines: list[BaselineEntry] = Field(default_factory=list)`

### `ConfigValidationPayload(_StrictModel)`
Typed JSON payload emitted by `evalforge-maestro config validate --json`:
- `schema_version: Literal["1.0"] = "1.0"`
- `valid: bool`
- `config_path: str | None = None`
- `env_file_path: str | None = None`
- `warnings: list[str] = Field(default_factory=list)`

### `CLIErrorPayload(_StrictModel)`
Typed JSON error payload emitted on `stdout` ONLY when `--json` was requested and execution terminated with POSIX exit `2`, `3`, or `4`:
- `schema_version: Literal["1.0"] = "1.0"`
- `exit_code: Literal[2, 3, 4]`
- `error_type: str`
- `message: str` (scrubbed via `scrub_secret_text`, never contains plaintext secrets or raw blocked PII)
- `hint: str | None = None`

---

## 4. State & Ownership Boundaries

1. **Configuration (`cli/config.py`)** resolves raw files (`evalforge.toml`, explicit `--env-file`) -> `CLIResolvedConfig` (+ raw ephemeral `api_key` in memory only) -> passed down to library execution/judges.
2. **Reporting (`reporting/`)** operates purely on immutable in-memory Pydantic artifacts (`RunRecord`, `RunComparisonReport`, `TrendReport`, `CalibrationReport`, `QualityGateResult`, `ReportDocument`) with zero filesystem config/env reading and zero artifact mutation.
3. **Storage (`storage/local.py`)** remains strictly append-only / atomic-non-overwrite for `RunRecord` and `manifest.jsonl`; `report` and `baseline` never rewrite `.evalforge/runs/<run_id>.json`.
