"""Single schema source of truth and core domain protocols for EvalForge Maestro."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalforge_maestro._canonical import round_score

SCHEMA_VERSION: Literal["1.0"] = "1.0"
_T = TypeVar("_T")


class MetricStatus(str, Enum):
    """Discrete evaluation status emitted on every MetricResult."""

    PASS = "PASS"  # noqa: S105  # MetricStatus literal, not a credential
    FAIL = "FAIL"
    WARNING = "WARNING"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CaseSplit(str, Enum):
    """Dataset partition label preventing train/eval split contamination."""

    EVAL = "eval"
    TRAIN = "train"
    FEW_SHOT = "few_shot"


def _ensure_json_serializable(value: _T, *, field_name: str) -> _T:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be strictly JSON-serializable (no NaN/Inf)") from exc
    return value


def _reject_bool_number(value: Any, *, field_name: str) -> Any:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric, not bool")
    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite")
    return value


def _ensure_non_empty_str(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


class _StrictModel(BaseModel):
    """Base schema rejecting unknown fields and validating reassignments."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CaseMetadata(_StrictModel):
    """Descriptive provenance and categorization metadata for an EvaluationCase."""

    tags: list[str] = Field(default_factory=list)
    split: CaseSplit = CaseSplit.EVAL
    difficulty: str | None = None
    domain: str | None = None
    source: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return [_ensure_non_empty_str(tag, field_name="CaseMetadata.tags") for tag in value]

    @field_validator("extra")
    @classmethod
    def _validate_extra(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_serializable(value, field_name="CaseMetadata.extra")


class CaseCriteria(_StrictModel):
    """Case-level acceptance rules, mandatory flags, and schema/threshold overrides."""

    mandatory: bool = False
    json_schema: dict[str, Any] | None = None
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    metric_thresholds: dict[str, float] = Field(default_factory=dict)

    @field_validator("json_schema")
    @classmethod
    def _validate_json_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        _ensure_json_serializable(value, field_name="CaseCriteria.json_schema")
        from jsonschema.exceptions import SchemaError
        from jsonschema.validators import validator_for

        validator_cls = validator_for(value)
        try:
            validator_cls.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"CaseCriteria.json_schema is not a valid JSON Schema: {exc}") from exc
        return value

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _validate_pass_threshold(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="CaseCriteria.pass_threshold")

    @field_validator("metric_thresholds", mode="before")
    @classmethod
    def _validate_metric_thresholds(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        for metric_id, threshold in value.items():
            if not isinstance(metric_id, str) or not metric_id.strip():
                raise ValueError("CaseCriteria.metric_thresholds keys must be non-empty strings")
            _reject_bool_number(threshold, field_name=f"metric_thresholds[{metric_id!r}]")
        return value


class EvaluationCase(_StrictModel):
    """Immutable single evaluation case contract."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str = Field(min_length=1)
    input: Any
    reference: Any = None
    expected_context: list[Any] | None = None
    expected_tools: list[dict[str, Any]] | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)
    criteria: CaseCriteria = Field(default_factory=CaseCriteria)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="EvaluationCase.id")

    @field_validator("input", "reference", "expected_context", "expected_tools")
    @classmethod
    def _validate_json_fields(cls, value: Any) -> Any:
        return _ensure_json_serializable(value, field_name="EvaluationCase")


class TokenUsage(_StrictModel):
    """Reserved token accounting submodel on ExecutionResult."""

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    @field_validator(
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
        mode="before",
    )
    @classmethod
    def _reject_bools(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="TokenUsage")


class RetrievedChunk(_StrictModel):
    """Reserved retrieved chunk submodel for RAG evidence capture (M2+)."""

    id: str = Field(min_length=1)
    text: str
    parent_id: str | None = None
    rank: int | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="RetrievedChunk.id")

    @field_validator("rank", "score", mode="before")
    @classmethod
    def _reject_bools(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="RetrievedChunk")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_serializable(value, field_name="RetrievedChunk.metadata")


class ExecutionResult(_StrictModel):
    """Captured target output, latency, errors, and evidence for one EvaluationCase."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    input: Any
    output: Any = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tokens: TokenUsage | None = None
    elapsed_seconds: float = Field(ge=0.0)
    truncated: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    system_version: str | None = None
    model_id: str | None = None
    config_fingerprint: str | None = None
    adapter_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ExecutionResult.case_id")

    @field_validator("elapsed_seconds", mode="before")
    @classmethod
    def _validate_elapsed(cls, value: Any) -> Any:
        return _reject_bool_number(value, field_name="ExecutionResult.elapsed_seconds")

    @field_validator("input", "output", "trace", "tool_calls", "adapter_metadata")
    @classmethod
    def _validate_json_fields(cls, value: Any) -> Any:
        return _ensure_json_serializable(value, field_name="ExecutionResult")


class MetricMetadata(_StrictModel):
    """Formal capability, input, formula, and limitation declaration for a metric."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    what_it_measures: str = Field(min_length=1)
    required_case_fields: tuple[str, ...]
    required_execution_fields: tuple[str, ...]
    calculation_method: str = Field(min_length=1)
    known_limitations: str = Field(min_length=1)


class MetricResult(_StrictModel):
    """Single metric outcome for one ExecutionResult."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    metric_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: MetricStatus
    label: str | None = None
    explanation: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    anomaly_flags: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metric_id", "metric_version", "explanation")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="MetricResult")

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score_before(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="MetricResult.score")
        return round_score(float(value))

    @field_validator("config_snapshot")
    @classmethod
    def _validate_snapshot(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_serializable(value, field_name="MetricResult.config_snapshot")

    @model_validator(mode="after")
    def _validate_score_status_consistency(self) -> MetricResult:
        if self.status in (MetricStatus.INCONCLUSIVE, MetricStatus.NOT_APPLICABLE):
            if self.score is not None:
                raise ValueError(
                    f"MetricResult.score must be None when status is {self.status.value}"
                )
        elif self.status in (MetricStatus.PASS, MetricStatus.FAIL) and self.score is None:
            raise ValueError(
                f"MetricResult.score must not be None when status is {self.status.value}"
            )
        return self


class CaseEvaluationRecord(_StrictModel):
    """Combined per-case execution evidence and metric outcomes stored in checkpoints and runs."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    mandatory: bool = False
    execution: ExecutionResult
    metrics: dict[str, MetricResult]

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="CaseEvaluationRecord.case_id")


class AggregateMetricSummary(_StrictModel):
    """Per-metric aggregate statistics across an evaluation run."""

    metric_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    applicable_count: int = Field(default=0, ge=0)
    pass_count: int = Field(default=0, ge=0)
    fail_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    inconclusive_count: int = Field(default=0, ge=0)
    not_applicable_count: int = Field(default=0, ge=0)

    @field_validator("mean_score", mode="before")
    @classmethod
    def _validate_mean(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="AggregateMetricSummary.mean_score")
        return round_score(float(value))


class RunRecord(_StrictModel):
    """Complete immutable audit artifact persisted per evaluation run."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    timestamp: datetime
    package_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_case_count: int = Field(ge=1)
    dataset_capped: bool = False
    max_dataset_cases: int | None = Field(default=None, ge=1)
    system_version: str | None = None
    model_id: str | None = None
    config_fingerprint: str | None = None
    metric_versions: dict[str, str]
    seed: int | None = None
    aggregates: dict[str, AggregateMetricSummary]
    status_counts: dict[MetricStatus, int]
    mandatory_failed_case_ids: list[str] = Field(default_factory=list)
    has_mandatory_failures: bool = False
    case_results: list[CaseEvaluationRecord]

    @field_validator("run_id", "package_version", "dataset_id")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="RunRecord")

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("evaluated_case_count", "max_dataset_cases", "seed", mode="before")
    @classmethod
    def _reject_bool_ints(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="RunRecord")


class RunManifestEntry(_StrictModel):
    """Lightweight run index line appended to .evalforge/manifest.jsonl."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    timestamp: datetime
    package_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_case_count: int = Field(ge=1)
    dataset_capped: bool = False
    system_version: str | None = None
    config_fingerprint: str | None = None
    metric_versions: dict[str, str]
    aggregate_scores: dict[str, float | None]
    status_counts: dict[MetricStatus, int]
    mandatory_failed_case_ids: list[str] = Field(default_factory=list)
    has_mandatory_failures: bool = False

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def from_run_record(cls, record: RunRecord) -> RunManifestEntry:
        """Project an immutable RunRecord onto a compact RunManifestEntry."""
        return cls(
            schema_version=record.schema_version,
            run_id=record.run_id,
            timestamp=record.timestamp,
            package_version=record.package_version,
            dataset_id=record.dataset_id,
            dataset_version=record.dataset_version,
            dataset_fingerprint=record.dataset_fingerprint,
            evaluated_case_count=record.evaluated_case_count,
            dataset_capped=record.dataset_capped,
            system_version=record.system_version,
            config_fingerprint=record.config_fingerprint,
            metric_versions=dict(record.metric_versions),
            aggregate_scores={
                metric_id: summary.mean_score for metric_id, summary in record.aggregates.items()
            },
            status_counts=dict(record.status_counts),
            mandatory_failed_case_ids=list(record.mandatory_failed_case_ids),
            has_mandatory_failures=record.has_mandatory_failures,
        )


class OrchestratorConfig(_StrictModel):
    """Runtime concurrency, truncation, timeout, and workstation guardrail configuration."""

    max_concurrency: int = Field(default=4, ge=1)
    max_dataset_cases: int | None = Field(default=None, ge=1)
    max_context_chars: int | None = Field(default=None, ge=1)
    case_timeout_seconds: float | None = Field(default=None, gt=0.0)
    max_memory_mb: float | None = Field(default=None, gt=0.0)
    memory_limit_action: Literal["warn", "abort"] = "warn"
    fail_fast: bool = False
    retain_checkpoints: bool = False
    seed: int | None = None

    @field_validator(
        "max_concurrency",
        "max_dataset_cases",
        "max_context_chars",
        "case_timeout_seconds",
        "max_memory_mb",
        "seed",
        mode="before",
    )
    @classmethod
    def _reject_bool_fields(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="OrchestratorConfig")


@runtime_checkable
class TargetAdapter(Protocol):
    """Abstract target adapter interface decoupled from concrete adapter implementations."""

    @property
    def system_version(self) -> str | None:
        """Return target system version identifier."""

    @property
    def model_id(self) -> str | None:
        """Return optional target model identifier."""

    @property
    def config_fingerprint(self) -> str | None:
        """Return canonical SHA-256 fingerprint of redacted adapter configuration."""

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Execute target system on one EvaluationCase and return ExecutionResult."""


@runtime_checkable
class Metric(Protocol):
    """Deterministic or model-based evaluation metric interface."""

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata describing inputs, calculation method, and limitations."""

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Evaluate one ExecutionResult against its EvaluationCase contract."""
