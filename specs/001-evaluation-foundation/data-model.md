# Data Model: Milestone 1 — Evaluation Foundation

**Feature**: `001-evaluation-foundation` | **Date**: 2026-11-18 | **Schema Source**: `src/evalforge_maestro/types.py`

All domain contracts inherit from a strict base model (`extra="forbid"`, `validate_assignment=True`) defined exclusively in `src/evalforge_maestro/types.py`. Zero ad-hoc untyped `dict` payloads are permitted across subsystem boundaries or `.evalforge/` artifacts.

## Enumerations

### `MetricStatus`

| Value | Meaning | Score Constraint |
|---|---|---|
| `PASS` | Metric met pass criteria (`score >= threshold`) | `float` in `[0.0, 1.0]` |
| `FAIL` | Metric violated pass criteria (`score < threshold`) | `float` in `[0.0, 1.0]` |
| `WARNING` | Degraded or anomalous result requiring attention (reserved/threshold-bound) | `float \| None` in `[0.0, 1.0]` |
| `INCONCLUSIVE` | Upstream execution error, timeout, or incompatible runtime state prevented valid scoring | `None` |
| `NOT_APPLICABLE` | Required reference data or schema absent on `EvaluationCase` | `None` |

### `CaseSplit`

- Allowed literals: `"eval"` (default), `"train"`, `"few_shot"`

## Core Contracts

### 1. `CaseMetadata`

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `tags` | `list[str]` | No | `[]` | Non-empty strings |
| `split` | `CaseSplit` | No | `"eval"` | One of `eval`, `train`, `few_shot` |
| `difficulty` | `str \| None` | No | `None` | Free-form difficulty tag |
| `domain` | `str \| None` | No | `None` | Domain label |
| `source` | `str \| None` | No | `None` | Provenance identifier |
| `extra` | `dict[str, Any]` | No | `{}` | JSON-serializable values only |

### 2. `CaseCriteria`

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `mandatory` | `bool` | No | `False` | `True` marks critical release case |
| `json_schema` | `dict[str, Any] \| None` | No | `None` | Valid JSON Schema mapping when present |
| `pass_threshold` | `float \| None` | No | `None` | `[0.0, 1.0]` (overrides metric default when `metric_thresholds[metric_id]` is absent) |
| `metric_thresholds` | `dict[str, float]` | No | `{}` | Values in `[0.0, 1.0]` keyed by `metric_id`; precedence: `metric_thresholds[metric_id]` > `pass_threshold` > metric `threshold` (`1.0`) |

### 3. `EvaluationCase`

Represents one immutable evaluation dataset record.

| Field | Type | Required | Default | Validation Rules |
|---|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | No | `"1.0"` | Supported schema version only |
| `id` | `str` | Yes | — | Non-empty after strip; unique within dataset (`DuplicateCaseIdError` on repeat) |
| `input` | `Any` | Yes | — | Must be JSON-serializable (`pydantic` JSON check) |
| `reference` | `Any` | No | `None` | Text, JSON value, or fallback JSON Schema mapping |
| `expected_context` | `list[Any] \| None` | No | `None` | Reserved for Milestone `002` retrieval metrics |
| `expected_tools` | `list[dict[str, Any]] \| None` | No | `None` | Reserved for post-MVP agent metrics |
| `metadata` | `CaseMetadata` | No | `CaseMetadata()` | Nested metadata contract |
| `criteria` | `CaseCriteria` | No | `CaseCriteria()` | Nested criteria contract |

### 4. `TokenUsage` & `RetrievedChunk` (Reserved Evidence Submodels)

- **`TokenUsage`**: `prompt_tokens: int | None`, `completion_tokens: int | None`, `reasoning_tokens: int | None`, `total_tokens: int | None` (each `>= 0`).
- **`RetrievedChunk`**: `id: str`, `text: str`, `parent_id: str | None = None`, `rank: int | None = None`, `score: float | None = None`, `metadata: dict[str, Any] = {}`.

### 5. `ExecutionResult`

Captures raw target behavior and intermediate evidence for one `EvaluationCase`.

| Field | Type | Required | Default | Validation Rules |
|---|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | No | `"1.0"` | Explicit schema tag |
| `case_id` | `str` | Yes | — | Matches source `EvaluationCase.id` |
| `input` | `Any` | Yes | — | Echoed input payload |
| `output` | `Any` | No | `None` | Target output (truncated post-scoring only if `max_context_chars` exceeded) |
| `retrieved_chunks` | `list[RetrievedChunk]` | No | `[]` | Reserved for M2 |
| `trace` | `list[dict[str, Any]]` | No | `[]` | Reserved for M6 |
| `tool_calls` | `list[dict[str, Any]]` | No | `[]` | Reserved for M6 |
| `tokens` | `TokenUsage \| None` | No | `None` | Reserved for token tracking |
| `elapsed_seconds` | `float` | Yes | — | `>= 0.0`, finite |
| `truncated` | `bool` | No | `False` | `True` when persisted fields truncated by `max_context_chars` |
| `errors` | `list[str]` | No | `[]` | Non-empty on target exception or timeout |
| `warnings` | `list[str]` | No | `[]` | Runtime warnings |
| `system_version` | `str \| None` | No | `None` | Target version identifier |
| `model_id` | `str \| None` | No | `None` | Optional model identifier |
| `config_fingerprint` | `str \| None` | No | `None` | SHA-256 of redacted adapter config |
| `adapter_metadata` | `dict[str, Any]` | No | `{}` | Redacted key-value metadata |

### 6. `MetricMetadata` & `MetricResult`

- **`MetricMetadata`** (frozen/immutable descriptor exposed by every metric):
  - `metric_id: str`, `metric_version: str`, `what_it_measures: str`, `required_case_fields: tuple[str, ...]`, `required_execution_fields: tuple[str, ...]`, `calculation_method: str`, `known_limitations: str`.
- **`MetricResult`**:
  - `schema_version: Literal["1.0"] = "1.0"`
  - `metric_id: str`
  - `metric_version: str`
  - `score: float | None = None` — validated not `NaN` / `Inf`, within `[0.0, 1.0]`, rounded to 6 decimal places (`round(v, 6)`)
  - `status: MetricStatus`
  - `label: str | None = None`
  - `explanation: str` (non-empty)
  - `evidence: list[str] = []`
  - `anomaly_flags: list[str] = []`
  - `config_snapshot: dict[str, Any] = {}`

### 7. `CaseEvaluationRecord` & `CheckpointEntry`

- **`CaseEvaluationRecord`**:
  - `schema_version: Literal["1.0"] = "1.0"`
  - `case_id: str`
  - `mandatory: bool = False`
  - `execution: ExecutionResult` (stored after post-scoring `max_context_chars` truncation)
  - `metrics: dict[str, MetricResult]` (keyed by `metric_id`)
- Used both as each line serialized to `.evalforge/tmp/<run_id>.jsonl` and as entries inside `RunRecord.case_results`.

### 8. `AggregateMetricSummary`

- `metric_id: str`
- `metric_version: str`
- `mean_score: float | None = None` (rounded to 6 decimal places over applicable numeric scores only; `None` if `applicable_count == 0`)
- `applicable_count: int = 0` (`PASS` + `FAIL` + `WARNING` with numeric scores)
- `pass_count: int = 0`
- `fail_count: int = 0`
- `warning_count: int = 0`
- `inconclusive_count: int = 0`
- `not_applicable_count: int = 0`

### 9. `RunRecord`

Immutable audit artifact written atomically to `.evalforge/runs/<run_id>.json`.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `Literal["1.0"]` | `"1.0"` |
| `run_id` | `str` | Unique non-empty identifier (collision raises `ImmutabilityError`) |
| `timestamp` | `datetime` | UTC ISO-8601 (`Z` / `+00:00`) |
| `package_version` | `str` | Resolved package version |
| `dataset_id` | `str` | Logical dataset identifier (defaults to `Path.stem` for files or `"in-memory"` for iterables when omitted) |
| `dataset_version` | `str \| None` | Optional dataset version label |
| `dataset_fingerprint` | `str` | 64-hex canonical SHA-256 over **evaluated cases only** |
| `evaluated_case_count` | `int` | Count of evaluated cases (`>= 1`) |
| `dataset_capped` | `bool` | `True` if `max_dataset_cases` capped intake before EOF (1-line non-blank lookahead without full tail scan) |
| `max_dataset_cases` | `int \| None` | Applied case limit if configured |
| `system_version` | `str \| None` | Target system version from adapter |
| `model_id` | `str \| None` | Target model ID from adapter |
| `config_fingerprint` | `str \| None` | Redacted config SHA-256 |
| `metric_versions` | `dict[str, str]` | Mapping `metric_id -> metric_version` |
| `seed` | `int \| None` | Optional reproducibility seed |
| `aggregates` | `dict[str, AggregateMetricSummary]` | Per-metric aggregates & status counts |
| `status_counts` | `dict[MetricStatus, int]` | Global counts across all evaluated `MetricResult` entries (all 5 `MetricStatus` keys pre-initialized to `0`) |
| `mandatory_failed_case_ids` | `list[str]` | Sorted case IDs with `criteria.mandatory=True` that hit `FAIL`, `INCONCLUSIVE`, or `ExecutionResult.errors` |
| `has_mandatory_failures` | `bool` | `len(mandatory_failed_case_ids) > 0` |
| `case_results` | `list[CaseEvaluationRecord]` | Ordered per-case evidence & scores |

### 10. `RunManifestEntry`

Lightweight line-delimited index record appended to `.evalforge/manifest.jsonl`:

- `schema_version`, `run_id`, `timestamp`, `package_version`, `dataset_id`, `dataset_version`, `dataset_fingerprint`, `evaluated_case_count`, `dataset_capped`, `system_version`, `config_fingerprint`, `metric_versions`, `aggregate_scores: dict[str, float | None]`, `status_counts: dict[MetricStatus, int]`, `has_mandatory_failures`, `mandatory_failed_case_ids`.

### 11. `OrchestratorConfig`

- `max_concurrency: int = 4` (`>= 1`)
- `max_dataset_cases: int | None = None` (`>= 1` when set)
- `max_context_chars: int | None = None` (`>= 1` when set)
- `case_timeout_seconds: float | None = None` (`> 0.0` when set)
- `max_memory_mb: float | None = None` (`> 0.0` when set)
- `memory_limit_action: Literal["warn", "abort"] = "warn"`
- `fail_fast: bool = False`
- `retain_checkpoints: bool = False`
- `seed: int | None = None`

## State Transitions & Lifecycle Invariants

```text
JSONL line
  └─[DatasetEngine validate]──▶ Invalid/Duplicate/Empty ─▶ DatasetError / DuplicateCaseIdError / EmptyDatasetError
  └─▶ Valid EvaluationCase (updates streaming SHA-256)
        └─[Orchestrator + TargetAdapter]──▶ Exception / Timeout ─▶ ExecutionResult(errors=[...]) ─▶ MetricResult(score=None, status=INCONCLUSIVE)
        └─▶ Success ─▶ ExecutionResult(output=full)
              └─[Metric evaluation on full output]─▶ MetricResult(PASS | FAIL | NOT_APPLICABLE)
                    └─[Post-scoring max_context_chars truncation]─▶ ExecutionResult(truncated=True if trimmed)
                          └─▶ Append CaseEvaluationRecord to .evalforge/tmp/<run_id>.jsonl
                                ├─[Run aborted / fail_fast]─▶ Keep .evalforge/tmp/<run_id>.jsonl; no RunRecord committed
                                └─[Run completed]─▶ Atomic commit .evalforge/runs/<run_id>.json + append manifest.jsonl ─▶ Delete tmp journal (unless retain_checkpoints=True)
```
