"""Single schema source of truth and core domain protocols for EvalForge Maestro."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from evalforge_maestro._canonical import (
    REDACTED_VALUE,
    canonical_sha256,
    is_sensitive_key,
    redact_secrets,
    round_delta,
    round_percentage,
    round_score,
    scrub_secret_text,
)

SCHEMA_VERSION: Literal["1.0"] = "1.0"
_T = TypeVar("_T")


class MetricStatus(str, Enum):
    """Discrete evaluation status emitted on every MetricResult."""

    PASS = "PASS"  # noqa: S105  # MetricStatus literal, not a credential
    FAIL = "FAIL"
    WARNING = "WARNING"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GateDecision(str, Enum):
    """Exclusive release acceptance decisions emitted by QualityGate."""

    PASS = "PASS"  # noqa: S105  # GateDecision literal, not a credential
    FAIL = "FAIL"
    WARNING = "WARNING"
    INCONCLUSIVE = "INCONCLUSIVE"


class ComparisonDirection(str, Enum):
    """Directional status for aggregate and case-level metric comparisons."""

    IMPROVED = "IMPROVED"
    REGRESSED = "REGRESSED"
    UNCHANGED = "UNCHANGED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    INCONCLUSIVE = "INCONCLUSIVE"


class TrendDirection(str, Enum):
    """Directional classification for sliding window trend trajectories."""

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SignificanceStatus(str, Enum):
    """Statistical hypothesis-test classification for regression comparisons."""

    SIGNIFICANT_IMPROVEMENT = "significant_improvement"
    SIGNIFICANT_REGRESSION = "significant_regression"
    NOT_SIGNIFICANT = "not_significant"
    INSUFFICIENT_DATA = "insufficient_data"


class StatisticalMethod(str, Enum):
    """Statistical inferential method applied to compute intervals and p-values."""

    PAIRED_T_CASE = "paired_t_case"
    WELCH_T_RUN = "welch_t_run"
    ONE_SAMPLE_T_RUN = "one_sample_t_run"


class DriftCategory(str, Enum):
    """Measurement and provenance comparability drift categories."""

    DATASET_FINGERPRINT = "DATASET_FINGERPRINT"
    METRIC_VERSION = "METRIC_VERSION"
    METRIC_SET = "METRIC_SET"
    JUDGE_CONFIG = "JUDGE_CONFIG"
    EMBEDDING_CONFIG = "EMBEDDING_CONFIG"
    DATASET_CAPPED = "DATASET_CAPPED"
    CASE_SET_MISMATCH = "CASE_SET_MISMATCH"


class EmbeddingAggregation(str, Enum):
    """Chunk-similarity aggregation strategy for context embedding evaluation."""

    MAX = "max"
    MEAN = "mean"


class AnomalyType(str, Enum):
    """Anti-masking and evidence-hygiene anomaly classes."""

    METRIC_DISAGREEMENT = "METRIC_DISAGREEMENT"
    AGGREGATE_MASKED_DROP = "AGGREGATE_MASKED_DROP"
    MANDATORY_CASE_FAILURE = "MANDATORY_CASE_FAILURE"
    INCONCLUSIVE_SPIKE = "INCONCLUSIVE_SPIKE"
    DATASET_CAPPED = "DATASET_CAPPED"


class AnomalySeverity(str, Enum):
    """Advisory or blocking severity level assigned to an AnomalyFlag."""

    WARNING = "WARNING"
    FAIL = "FAIL"


class AnomalyScope(str, Enum):
    """Granularity at which an anomaly occurred."""

    RUN = "RUN"
    CASE = "CASE"


class CaseSplit(str, Enum):
    """Dataset partition label preventing train/eval split contamination."""

    EVAL = "eval"
    TRAIN = "train"
    FEW_SHOT = "few_shot"


class CalibrationDisagreementType(str, Enum):
    """Category describing human-versus-judge agreement discrepancies."""

    TOO_GENEROUS = "too_generous"
    TOO_HARSH = "too_harsh"
    SCORE_DIVERGENCE = "score_divergence"
    INCONCLUSIVE = "inconclusive"


class ConfigSourceTier(str, Enum):
    """Precedence tier from which a resolved CLI configuration value originated."""

    CLI = "cli"
    ENV = "env"
    ENV_FILE = "env_file"
    FILE = "file"
    DEFAULT = "default"


class TargetType(str, Enum):
    """Supported target adapter or offline trace-replay execution modes."""

    CALLABLE = "callable"
    RAG = "rag"
    DOCPIPE = "docpipe"
    REPLAY = "replay"
    AGENT = "agent"


class ReportKind(str, Enum):
    """Top-level report workflows emitted by reporting and CLI subcommands."""

    RUN = "run"
    COMPARE = "compare"
    TREND = "trend"
    CALIBRATE = "calibrate"


class EvidenceDecouplingCategory(str, Enum):
    """Category identifying divergence between intermediate evidence and final outcome."""

    ANSWER_PASSED_RETRIEVAL_FAILED = "answer_passed_retrieval_or_grounding_failed"
    RETRIEVAL_PASSED_ANSWER_FAILED = "retrieval_passed_answer_or_grounding_failed"
    ANSWER_PASSED_AGENT_TRACE_FAILED = "answer_passed_agent_trace_failed"
    AGENT_TRACE_PASSED_ANSWER_FAILED = "agent_trace_passed_answer_failed"


class ToolCallStatus(str, Enum):
    """Normalized execution outcome status for an agent tool invocation."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


class TraceStepKind(str, Enum):
    """Canonical category describing a step within an agent execution trace."""

    USER_INPUT = "user_input"
    REASONING = "reasoning"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    FINAL_OUTPUT = "final_output"
    OTHER = "other"


class OtelTimestampUnit(str, Enum):
    """Timestamp unit interpretation hint for OpenTelemetry span timestamps."""

    AUTO = "auto"
    NS = "ns"
    US = "us"
    MS = "ms"
    S = "s"


class RunSortOrder(str, Enum):
    """Ordering modes supported by SQLiteRunIndex.query_runs."""

    TIMESTAMP_DESC = "timestamp_desc"
    TIMESTAMP_ASC = "timestamp_asc"
    RUN_ID_ASC = "run_id_asc"


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


def _reject_strict_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer, not {type(value).__name__}")
    return value


def _ensure_non_empty_str(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


def _validate_http_api_base(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = _ensure_non_empty_str(value, field_name=field_name)
    if any(ch.isspace() for ch in cleaned):
        raise ValueError(f"{field_name} must not contain whitespace")
    if "?" in cleaned or "#" in cleaned or ";" in cleaned:
        raise ValueError(f"{field_name} must not include query parameters or fragments")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field_name} must be an http/https URL with valid hostname")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValueError(f"{field_name} must not include embedded URL credentials")
    return cleaned


def _validate_optional_str(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_non_empty_str(value, field_name=field_name)


def _validate_bounded_score_map(value: Any, *, field_name: str) -> Any:
    if not isinstance(value, dict):
        return value
    validated: dict[str, float] = {}
    for metric_id, score in value.items():
        if not isinstance(metric_id, str):
            raise ValueError(f"{field_name} keys must be non-empty strings")
        cleaned_key = _ensure_non_empty_str(metric_id, field_name=field_name)
        _reject_bool_number(score, field_name=f"{field_name}[{cleaned_key!r}]")
        rounded = round_score(float(score))
        if not (0.0 <= rounded <= 1.0):
            raise ValueError(
                f"{field_name}[{cleaned_key!r}] must be within [0.0, 1.0], got {rounded}"
            )
        validated[cleaned_key] = rounded
    return validated


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
    """Case-level acceptance rules, mandatory flags, and schema/policy constraints."""

    mandatory: bool = False
    json_schema: dict[str, Any] | None = None
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    metric_thresholds: dict[str, float] = Field(default_factory=dict)
    forbidden_tools: list[str] = Field(default_factory=list)
    forbidden_argument_patterns: list[str] = Field(default_factory=list)
    max_steps: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=1)
    allow_redundant_failures: int = Field(default=0, ge=0)

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

    @field_validator("forbidden_tools", "forbidden_argument_patterns")
    @classmethod
    def _validate_policy_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"CaseCriteria.{info.field_name}")
            for item in value
        ]

    @field_validator("max_steps", "max_tool_calls", "allow_redundant_failures", mode="before")
    @classmethod
    def _validate_budget_ints(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"CaseCriteria.{info.field_name}")


class ExpectedContextItem(_StrictModel):
    """Typed ground-truth retrieval item on EvaluationCase.expected_context."""

    id: str = Field(min_length=1)
    text: str | None = None
    relevance: int = Field(default=1, ge=0)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ExpectedContextItem.id")

    @field_validator("relevance", mode="before")
    @classmethod
    def _validate_relevance(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="ExpectedContextItem.relevance")


_TOOL_STATUS_ALIASES: dict[str, ToolCallStatus] = {
    "success": ToolCallStatus.SUCCESS,
    "succeeded": ToolCallStatus.SUCCESS,
    "ok": ToolCallStatus.SUCCESS,
    "completed": ToolCallStatus.SUCCESS,
    "error": ToolCallStatus.ERROR,
    "errored": ToolCallStatus.ERROR,
    "fail": ToolCallStatus.ERROR,
    "failed": ToolCallStatus.ERROR,
    "failure": ToolCallStatus.ERROR,
    "timeout": ToolCallStatus.TIMEOUT,
    "timed_out": ToolCallStatus.TIMEOUT,
    "blocked": ToolCallStatus.BLOCKED,
    "denied": ToolCallStatus.BLOCKED,
    "forbidden": ToolCallStatus.BLOCKED,
}

_TRACE_KIND_ALIASES: dict[str, TraceStepKind] = {
    "user_input": TraceStepKind.USER_INPUT,
    "user": TraceStepKind.USER_INPUT,
    "input": TraceStepKind.USER_INPUT,
    "reasoning": TraceStepKind.REASONING,
    "thought": TraceStepKind.REASONING,
    "thinking": TraceStepKind.REASONING,
    "llm_response": TraceStepKind.LLM_RESPONSE,
    "assistant": TraceStepKind.LLM_RESPONSE,
    "model": TraceStepKind.LLM_RESPONSE,
    "llm": TraceStepKind.LLM_RESPONSE,
    "tool_call": TraceStepKind.TOOL_CALL,
    "tool_use": TraceStepKind.TOOL_CALL,
    "action": TraceStepKind.TOOL_CALL,
    "tool_result": TraceStepKind.TOOL_RESULT,
    "tool": TraceStepKind.TOOL_RESULT,
    "observation": TraceStepKind.TOOL_RESULT,
    "error": TraceStepKind.ERROR,
    "final_output": TraceStepKind.FINAL_OUTPUT,
    "output": TraceStepKind.FINAL_OUTPUT,
    "answer": TraceStepKind.FINAL_OUTPUT,
    "other": TraceStepKind.OTHER,
}


def _decode_json_object_args(raw_args: Any) -> tuple[dict[str, Any], str | None, str | None]:
    if raw_args is None or raw_args == "":
        return {}, None, None
    if isinstance(raw_args, dict):
        checked = _ensure_json_serializable(dict(raw_args), field_name="tool_arguments")
        return checked, None, None
    if isinstance(raw_args, str):
        try:
            decoded = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            return {}, raw_args, f"Invalid JSON tool arguments: {exc.msg}"
        if not isinstance(decoded, dict):
            return (
                {},
                raw_args,
                f"Tool arguments JSON must decode to an object, got {type(decoded).__name__}",
            )
        checked = _ensure_json_serializable(decoded, field_name="tool_arguments")
        return checked, None, None
    raise ValueError(
        f"Tool arguments must be a mapping or JSON string, got {type(raw_args).__name__}"
    )


def _validate_json_schema_mapping(value: dict[str, Any], *, field_name: str) -> dict[str, Any]:
    _ensure_json_serializable(value, field_name=field_name)
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for

    validator_cls = validator_for(value)
    try:
        validator_cls.check_schema(value)
    except SchemaError as exc:
        raise ValueError(f"{field_name} is not a valid JSON Schema: {exc}") from exc
    return value


class ExpectedToolCall(_StrictModel):
    """Typed expectation for an agent tool invocation on EvaluationCase.expected_tools."""

    name: str = Field(min_length=1)
    arguments: dict[str, Any] | None = None
    arguments_schema: dict[str, Any] | None = None
    argument_match_mode: Literal["subset", "exact"] = "subset"
    optional: bool = False
    order: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_input(cls, data: Any) -> Any:
        if isinstance(data, ExpectedToolCall):
            return data
        if isinstance(data, str):
            return {"name": data}
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        fn_block = payload.pop("function", None)
        if isinstance(fn_block, dict):
            if "name" not in payload and "name" in fn_block:
                payload["name"] = fn_block["name"]
            if "arguments" not in payload and "arguments" in fn_block:
                payload["arguments"] = fn_block["arguments"]
            if payload.get("type") == "function":
                payload.pop("type", None)

        if "name" not in payload:
            for alias in ("tool", "tool_name"):
                if alias in payload:
                    payload["name"] = payload.pop(alias)
                    break
        if "arguments" not in payload:
            for alias in ("args", "input", "parameters"):
                if alias in payload:
                    payload["arguments"] = payload.pop(alias)
                    break
        if "arguments_schema" not in payload and "schema" in payload:
            payload["arguments_schema"] = payload.pop("schema")

        if "arguments" in payload and payload["arguments"] is not None:
            decoded, _, parse_err = _decode_json_object_args(payload["arguments"])
            if parse_err is not None:
                raise ValueError(f"ExpectedToolCall.arguments invalid: {parse_err}")
            payload["arguments"] = decoded

        return payload

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ExpectedToolCall.name")

    @field_validator("arguments")
    @classmethod
    def _validate_arguments(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _ensure_json_serializable(value, field_name="ExpectedToolCall.arguments")

    @field_validator("arguments_schema")
    @classmethod
    def _validate_arguments_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return _validate_json_schema_mapping(value, field_name="ExpectedToolCall.arguments_schema")

    @field_validator("order", mode="before")
    @classmethod
    def _validate_order(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="ExpectedToolCall.order")


class EvaluationCase(_StrictModel):
    """Immutable single evaluation case contract."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str = Field(min_length=1)
    input: Any
    reference: Any = None
    expected_context: list[str | ExpectedContextItem] | None = None
    expected_tools: list[ExpectedToolCall] | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)
    criteria: CaseCriteria = Field(default_factory=CaseCriteria)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="EvaluationCase.id")

    @field_validator("expected_context")
    @classmethod
    def _validate_expected_context(
        cls,
        value: list[str | ExpectedContextItem] | None,
    ) -> list[str | ExpectedContextItem] | None:
        if value is None:
            return None
        normalized: list[str | ExpectedContextItem] = []
        seen_ids: set[str] = set()
        for item in value:
            if isinstance(item, str):
                cleaned = _ensure_non_empty_str(item, field_name="EvaluationCase.expected_context")
                item_id = cleaned
                normalized.append(cleaned)
            else:
                item_id = item.id
                normalized.append(item)
            if item_id in seen_ids:
                raise ValueError(
                    f"Duplicate identifier {item_id!r} in EvaluationCase.expected_context"
                )
            seen_ids.add(item_id)
        return normalized

    @field_validator("input", "reference")
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
    """Retrieved chunk submodel for RAG evidence capture."""

    id: str = Field(min_length=1)
    text: str
    parent_id: str | None = None
    rank: int | None = Field(default=None, ge=1)
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="RetrievedChunk.id")

    @field_validator("rank", mode="before")
    @classmethod
    def _validate_rank(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="RetrievedChunk.rank")

    @field_validator("score", mode="before")
    @classmethod
    def _reject_bools(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="RetrievedChunk.score")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _ensure_json_serializable(value, field_name="RetrievedChunk.metadata")


class ToolCallRecord(_StrictModel):
    """Normalized record describing one agent tool invocation."""

    id: str | None = None
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str | None = None
    argument_parse_error: str | None = None
    result: Any = None
    status: ToolCallStatus = ToolCallStatus.SUCCESS
    error: str | None = None
    step_index: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_input(cls, data: Any) -> Any:
        if isinstance(data, ToolCallRecord):
            return data
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        fn_block = payload.pop("function", None)
        if isinstance(fn_block, dict):
            if "name" not in payload and "name" in fn_block:
                payload["name"] = fn_block["name"]
            if "arguments" not in payload and "arguments" in fn_block:
                payload["arguments"] = fn_block["arguments"]
            if payload.get("type") == "function":
                payload.pop("type", None)

        if "id" not in payload:
            for alias in ("tool_call_id", "call_id"):
                if alias in payload:
                    payload["id"] = payload.pop(alias)
                    break
        if "name" not in payload:
            for alias in ("tool", "tool_name"):
                if alias in payload:
                    payload["name"] = payload.pop(alias)
                    break
        if "arguments" not in payload:
            for alias in ("args", "input", "parameters"):
                if alias in payload:
                    payload["arguments"] = payload.pop(alias)
                    break
        if "result" not in payload:
            for alias in ("output", "response"):
                if alias in payload:
                    payload["result"] = payload.pop(alias)
                    break

        if "arguments" in payload:
            decoded, raw_arg, parse_err = _decode_json_object_args(payload["arguments"])
            payload["arguments"] = decoded
            if raw_arg is not None and payload.get("raw_arguments") is None:
                payload["raw_arguments"] = raw_arg
            if parse_err is not None and payload.get("argument_parse_error") is None:
                payload["argument_parse_error"] = parse_err

        raw_err = payload.get("error")
        has_err = (isinstance(raw_err, str) and bool(raw_err.strip())) or bool(
            payload.get("argument_parse_error")
        )
        raw_status = payload.get("status")
        if raw_status is None:
            payload["status"] = ToolCallStatus.ERROR if has_err else ToolCallStatus.SUCCESS
        elif isinstance(raw_status, str):
            mapped = _TOOL_STATUS_ALIASES.get(raw_status.strip().lower())
            if mapped is not None:
                payload["status"] = mapped

        return payload

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="ToolCallRecord.id")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ToolCallRecord.name")

    @field_validator("step_index", mode="before")
    @classmethod
    def _validate_step_index(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="ToolCallRecord.step_index")

    @field_validator("elapsed_seconds", mode="before")
    @classmethod
    def _validate_elapsed(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="ToolCallRecord.elapsed_seconds")

    @field_validator("arguments", "result", "metadata")
    @classmethod
    def _validate_json_fields(cls, value: Any, info: ValidationInfo) -> Any:
        return _ensure_json_serializable(value, field_name=f"ToolCallRecord.{info.field_name}")


class AgentTraceStep(_StrictModel):
    """Canonical ordered execution step inside ExecutionResult.trace."""

    step_index: int | None = Field(default=None, ge=0)
    kind: TraceStepKind = TraceStepKind.OTHER
    name: str | None = None
    content: Any = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_call_id: str | None = None
    status: ToolCallStatus | None = None
    error: str | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0.0)
    tokens: TokenUsage | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_input(cls, data: Any) -> Any:
        if isinstance(data, AgentTraceStep):
            return data
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if "kind" not in payload:
            for alias in ("type", "role"):
                if alias in payload:
                    raw_kind = payload.pop(alias)
                    if isinstance(raw_kind, str):
                        payload["kind"] = _TRACE_KIND_ALIASES.get(
                            raw_kind.strip().lower(), raw_kind
                        )
                    else:
                        payload["kind"] = raw_kind
                    break
        elif isinstance(payload["kind"], str):
            raw_kind = payload["kind"].strip().lower()
            if raw_kind in _TRACE_KIND_ALIASES:
                payload["kind"] = _TRACE_KIND_ALIASES[raw_kind]

        if "status" in payload and isinstance(payload["status"], str):
            mapped = _TOOL_STATUS_ALIASES.get(payload["status"].strip().lower())
            if mapped is not None:
                payload["status"] = mapped

        return payload

    @field_validator("name", "tool_call_id")
    @classmethod
    def _validate_opt_ids(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"AgentTraceStep.{info.field_name}")

    @field_validator("step_index", mode="before")
    @classmethod
    def _validate_step_index(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="AgentTraceStep.step_index")

    @field_validator("elapsed_seconds", mode="before")
    @classmethod
    def _validate_elapsed(cls, value: Any) -> Any:
        if value is None:
            return None
        return _reject_bool_number(value, field_name="AgentTraceStep.elapsed_seconds")

    @field_validator("content", "metadata")
    @classmethod
    def _validate_json_fields(cls, value: Any, info: ValidationInfo) -> Any:
        return _ensure_json_serializable(value, field_name=f"AgentTraceStep.{info.field_name}")


class ExecutionResult(_StrictModel):
    """Captured target output, latency, errors, and evidence for one EvaluationCase."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    input: Any
    output: Any = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
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

    @field_validator("input", "output", "adapter_metadata")
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
    judge_config_fingerprint: str | None = None
    embedding_config_fingerprint: str | None = None
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

    @field_validator("judge_config_fingerprint", "embedding_config_fingerprint")
    @classmethod
    def _validate_config_fingerprints(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"RunRecord.{info.field_name}")

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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
    model_id: str | None = None
    config_fingerprint: str | None = None
    judge_config_fingerprint: str | None = None
    embedding_config_fingerprint: str | None = None
    metric_versions: dict[str, str]
    aggregate_scores: dict[str, float | None]
    status_counts: dict[MetricStatus, int]
    mandatory_failed_case_ids: list[str] = Field(default_factory=list)
    has_mandatory_failures: bool = False

    @field_validator("judge_config_fingerprint", "embedding_config_fingerprint")
    @classmethod
    def _validate_config_fingerprints(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"RunManifestEntry.{info.field_name}")

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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
            model_id=record.model_id,
            config_fingerprint=record.config_fingerprint,
            judge_config_fingerprint=record.judge_config_fingerprint,
            embedding_config_fingerprint=record.embedding_config_fingerprint,
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
    judge_config_fingerprint: str | None = None
    embedding_config_fingerprint: str | None = None

    @field_validator("judge_config_fingerprint", "embedding_config_fingerprint")
    @classmethod
    def _validate_config_fingerprints(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"OrchestratorConfig.{info.field_name}")

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


class RAGExtractorConfig(_StrictModel):
    """Declarative field-extraction rules for protocol-based RAGAdapter."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    output: str | Callable[[Any], Any] | None = None
    chunks: str | Callable[[Any], Any] | None = None
    chunk_id: str | Callable[[Any], Any] | None = None
    chunk_text: str | Callable[[Any], Any] | None = None
    chunk_parent_id: str | Callable[[Any], Any] | None = None
    chunk_rank: str | Callable[[Any], Any] | None = None
    chunk_score: str | Callable[[Any], Any] | None = None
    chunk_metadata: str | Callable[[Any], Any] | None = None
    tokens: str | Callable[[Any], Any] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _validate_extractor_spec(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str):
            return _ensure_non_empty_str(
                value,
                field_name=f"RAGExtractorConfig.{info.field_name}",
            )
        return value


class AgentExtractorConfig(_StrictModel):
    """Declarative field-extraction rules for protocol-based AgentAdapter."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    output: str | Callable[[Any], Any] | None = None
    tool_calls: str | Callable[[Any], Any] | None = None
    trace: str | Callable[[Any], Any] | None = None
    tokens: str | Callable[[Any], Any] | None = None
    errors: str | Callable[[Any], Any] | None = None
    tool_id: str | Callable[[Any], Any] | None = None
    tool_name: str | Callable[[Any], Any] | None = None
    tool_arguments: str | Callable[[Any], Any] | None = None
    tool_result: str | Callable[[Any], Any] | None = None
    tool_status: str | Callable[[Any], Any] | None = None
    tool_error: str | Callable[[Any], Any] | None = None
    step_kind: str | Callable[[Any], Any] | None = None
    step_content: str | Callable[[Any], Any] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _validate_extractor_spec(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str):
            return _ensure_non_empty_str(
                value,
                field_name=f"AgentExtractorConfig.{info.field_name}",
            )
        return value


class OtelExtractorConfig(_StrictModel):
    """Typed OpenTelemetry span attribute extraction and case-correlation rules."""

    case_id_attribute: str | None = None
    input_attribute: str | None = None
    output_attribute: str | None = None
    model_attribute: str | None = None
    service_version_attribute: str | None = None
    step_kind_attribute: str | None = None
    tool_name_attribute: str | None = None
    tool_arguments_attribute: str | None = None
    tool_result_attribute: str | None = None
    retrieval_documents_attribute: str | None = None
    timestamp_unit: OtelTimestampUnit = OtelTimestampUnit.AUTO
    match_dataset_by_input: bool = False

    @field_validator(
        "case_id_attribute",
        "input_attribute",
        "output_attribute",
        "model_attribute",
        "service_version_attribute",
        "step_kind_attribute",
        "tool_name_attribute",
        "tool_arguments_attribute",
        "tool_result_attribute",
        "retrieval_documents_attribute",
    )
    @classmethod
    def _validate_attr_names(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(
            value,
            field_name=f"OtelExtractorConfig.{info.field_name}",
        )


class DriftWarning(_StrictModel):
    """Structured provenance or comparability drift alert."""

    category: DriftCategory
    metric_id: str | None = None
    baseline_run_id: str | None = None
    candidate_run_id: str | None = None
    baseline_value: Any = None
    candidate_value: Any = None
    explanation: str = Field(min_length=1)

    @field_validator("metric_id", "baseline_run_id", "candidate_run_id")
    @classmethod
    def _validate_opt_ids(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"DriftWarning.{info.field_name}")

    @field_validator("baseline_value", "candidate_value")
    @classmethod
    def _validate_values(cls, value: Any, info: ValidationInfo) -> Any:
        return _ensure_json_serializable(value, field_name=f"DriftWarning.{info.field_name}")

    @field_validator("explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="DriftWarning.explanation")


class AnomalyFlag(_StrictModel):
    """Structured anti-masking or evidence-hygiene anomaly finding."""

    anomaly_type: AnomalyType
    severity: AnomalySeverity
    scope: AnomalyScope
    case_id: str | None = None
    metric_ids: list[str] = Field(default_factory=list)
    spread: float | None = None
    explanation: str = Field(min_length=1)

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="AnomalyFlag.case_id")

    @field_validator("metric_ids")
    @classmethod
    def _validate_metric_ids(cls, value: list[str]) -> list[str]:
        return [_ensure_non_empty_str(item, field_name="AnomalyFlag.metric_ids") for item in value]

    @field_validator("spread", mode="before")
    @classmethod
    def _validate_spread(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="AnomalyFlag.spread")
        return round_delta(float(value))

    @field_validator("explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="AnomalyFlag.explanation")

    @model_validator(mode="after")
    def _validate_scope_case_id(self) -> AnomalyFlag:
        if self.scope == AnomalyScope.CASE and self.case_id is None:
            raise ValueError("AnomalyFlag.case_id is required when scope is CASE")
        return self


class QualityGatePolicy(_StrictModel):
    """Declarative acceptance thresholds, drift escalation, and anomaly tolerances."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_metric_scores: dict[str, float] = Field(default_factory=dict)
    max_regression_drop: float = Field(default=0.05, ge=0.0, le=1.0)
    max_metric_regression_drops: dict[str, float] = Field(default_factory=dict)
    max_regressed_cases: int | None = Field(default=None, ge=0)
    disagreement_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    case_drop_warning_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    trend_slope_threshold: float = Field(default=0.01, gt=0.0, le=1.0)
    max_inconclusive_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    require_baseline: bool = False
    require_trend: bool = False
    min_trend_runs: int = Field(default=2, ge=2)
    soft_regression_warning: bool = False
    fail_on_drift: bool = False
    fail_on_anomaly: bool = False
    fail_on_degrading_trend: bool = False
    fail_on_mandatory_regression: bool = True
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    min_statistical_samples: int = Field(default=2, ge=2)
    fail_on_significant_regression: bool = False

    @field_validator(
        "min_score",
        "max_regression_drop",
        "disagreement_threshold",
        "case_drop_warning_threshold",
        "trend_slope_threshold",
        "max_inconclusive_rate",
        "confidence_level",
        mode="before",
    )
    @classmethod
    def _validate_policy_floats(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"QualityGatePolicy.{info.field_name}")
        return round_score(float(value))

    @field_validator(
        "max_regressed_cases",
        "min_trend_runs",
        "min_statistical_samples",
        mode="before",
    )
    @classmethod
    def _validate_policy_ints(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"QualityGatePolicy.{info.field_name}")

    @field_validator("min_metric_scores", "max_metric_regression_drops", mode="before")
    @classmethod
    def _validate_metric_float_maps(cls, value: Any, info: ValidationInfo) -> Any:
        return _validate_bounded_score_map(value, field_name=f"QualityGatePolicy.{info.field_name}")


_SAFE_BASELINE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class BaselineEntry(_StrictModel):
    """Immutable baseline pointer snapshot linking a named alias to one RunRecord."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    name: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    pinned_at: datetime
    note: str | None = None
    tags: list[str] = Field(default_factory=list)
    dataset_id: str = Field(min_length=1)
    dataset_version: str | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_version: str | None = None
    model_id: str | None = None
    config_fingerprint: str | None = None
    judge_config_fingerprint: str | None = None
    embedding_config_fingerprint: str | None = None
    metric_versions: dict[str, str] = Field(default_factory=dict)
    aggregate_scores: dict[str, float | None] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = _ensure_non_empty_str(value, field_name="BaselineEntry.name")
        if not _SAFE_BASELINE_NAME_RE.match(cleaned) or ".." in cleaned:
            raise ValueError(
                f"Invalid BaselineEntry.name {value!r}: must match "
                "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ without '..'"
            )
        return cleaned

    @field_validator("run_id", "dataset_id")
    @classmethod
    def _validate_ids(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"BaselineEntry.{info.field_name}")

    @field_validator("pinned_at")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator(
        "note",
        "dataset_version",
        "judge_config_fingerprint",
        "embedding_config_fingerprint",
    )
    @classmethod
    def _validate_opt_strings(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"BaselineEntry.{info.field_name}")

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return [_ensure_non_empty_str(item, field_name="BaselineEntry.tags") for item in value]

    @field_validator("metric_versions")
    @classmethod
    def _validate_metric_versions(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            _ensure_non_empty_str(k, field_name="BaselineEntry.metric_versions"): (
                _ensure_non_empty_str(v, field_name="BaselineEntry.metric_versions")
            )
            for k, v in value.items()
        }

    @field_validator("aggregate_scores", mode="before")
    @classmethod
    def _validate_aggregate_scores(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        validated: dict[str, float | None] = {}
        for metric_id, score in value.items():
            if not isinstance(metric_id, str):
                raise ValueError("BaselineEntry.aggregate_scores keys must be non-empty strings")
            cleaned_key = _ensure_non_empty_str(
                metric_id, field_name="BaselineEntry.aggregate_scores"
            )
            if score is None:
                validated[cleaned_key] = None
                continue
            _reject_bool_number(
                score, field_name=f"BaselineEntry.aggregate_scores[{cleaned_key!r}]"
            )
            rounded = round_score(float(score))
            if not (0.0 <= rounded <= 1.0):
                raise ValueError(
                    f"BaselineEntry.aggregate_scores[{cleaned_key!r}] must be in [0.0, 1.0]"
                )
            validated[cleaned_key] = rounded
        return validated


class BaselineRegistry(_StrictModel):
    """Schema-versioned persisted mapping of baseline names to BaselineEntry snapshots."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    baselines: dict[str, BaselineEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_key_alignment(self) -> BaselineRegistry:
        for key, entry in self.baselines.items():
            if key != entry.name:
                raise ValueError(
                    f"BaselineRegistry key {key!r} must match BaselineEntry.name {entry.name!r}"
                )
        return self


def _validate_optional_bounded_score(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    _reject_bool_number(value, field_name=field_name)
    rounded = round_score(float(value))
    if not (0.0 <= rounded <= 1.0):
        raise ValueError(f"{field_name} must be within [0.0, 1.0], got {rounded}")
    return rounded


def _validate_optional_delta(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    _reject_bool_number(value, field_name=field_name)
    rounded = round_delta(float(value))
    if not (-1.0 <= rounded <= 1.0):
        raise ValueError(f"{field_name} must be within [-1.0, 1.0], got {rounded}")
    return rounded


def _validate_optional_finite_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    _reject_bool_number(value, field_name=field_name)
    return round_delta(float(value))


class StatisticalSummary(_StrictModel):
    """Immutable distributional dispersion, CI, and hypothesis-test evidence."""

    method: StatisticalMethod
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    sample_size: int = Field(ge=0)
    baseline_sample_size: int = Field(ge=0)
    candidate_sample_size: int = Field(ge=0)
    excluded_pair_count: int = Field(default=0, ge=0)
    mean_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    delta_std: float | None = Field(default=None, ge=0.0)
    standard_error: float | None = Field(default=None, ge=0.0)
    baseline_std: float | None = Field(default=None, ge=0.0)
    candidate_std: float | None = Field(default=None, ge=0.0)
    ci_low: float | None = Field(default=None, ge=-1.0, le=1.0)
    ci_high: float | None = Field(default=None, ge=-1.0, le=1.0)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    effect_size: float | None = None
    degrees_of_freedom: float | None = Field(default=None, ge=0.0)
    significance: SignificanceStatus
    statistically_significant: bool = False
    explanation: str = Field(min_length=1)

    @field_validator("confidence_level", mode="before")
    @classmethod
    def _validate_conf(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="StatisticalSummary.confidence_level")
        return round_score(float(value))

    @field_validator(
        "sample_size",
        "baseline_sample_size",
        "candidate_sample_size",
        "excluded_pair_count",
        mode="before",
    )
    @classmethod
    def _validate_counts(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"StatisticalSummary.{info.field_name}")

    @field_validator("mean_delta", "ci_low", "ci_high", mode="before")
    @classmethod
    def _validate_deltas(cls, value: Any, info: ValidationInfo) -> float | None:
        return _validate_optional_delta(value, field_name=f"StatisticalSummary.{info.field_name}")

    @field_validator("p_value", mode="before")
    @classmethod
    def _validate_p_value(cls, value: Any) -> float | None:
        return _validate_optional_bounded_score(value, field_name="StatisticalSummary.p_value")

    @field_validator(
        "delta_std",
        "standard_error",
        "baseline_std",
        "candidate_std",
        "effect_size",
        "degrees_of_freedom",
        mode="before",
    )
    @classmethod
    def _validate_finite_stats(cls, value: Any, info: ValidationInfo) -> float | None:
        return _validate_optional_finite_float(
            value, field_name=f"StatisticalSummary.{info.field_name}"
        )

    @field_validator("explanation")
    @classmethod
    def _validate_explanation(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="StatisticalSummary.explanation")


class RunCohortSummary(_StrictModel):
    """Provenance record for multi-run baseline/candidate cohorts."""

    baseline_run_ids: list[str] = Field(min_length=1)
    candidate_run_ids: list[str] = Field(min_length=1)
    baseline_run_count: int = Field(ge=1)
    candidate_run_count: int = Field(ge=1)
    baseline_names: list[str] = Field(default_factory=list)

    @field_validator("baseline_run_ids", "candidate_run_ids", "baseline_names")
    @classmethod
    def _validate_str_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"RunCohortSummary.{info.field_name}")
            for item in value
        ]

    @field_validator("baseline_run_count", "candidate_run_count", mode="before")
    @classmethod
    def _validate_run_counts(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"RunCohortSummary.{info.field_name}")


class MetricComparison(_StrictModel):
    """Aggregate metric comparison between baseline and candidate runs."""

    metric_id: str = Field(min_length=1)
    baseline_version: str | None = None
    candidate_version: str | None = None
    baseline_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    direction: ComparisonDirection
    status_count_deltas: dict[MetricStatus, int] = Field(default_factory=dict)
    statistics: StatisticalSummary | None = None
    case_statistics: StatisticalSummary | None = None

    @field_validator("metric_id")
    @classmethod
    def _validate_metric_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="MetricComparison.metric_id")

    @field_validator("baseline_version", "candidate_version")
    @classmethod
    def _validate_versions(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"MetricComparison.{info.field_name}")

    @field_validator("baseline_score", "candidate_score", mode="before")
    @classmethod
    def _validate_scores(cls, value: Any, info: ValidationInfo) -> float | None:
        return _validate_optional_bounded_score(
            value, field_name=f"MetricComparison.{info.field_name}"
        )

    @field_validator("delta", mode="before")
    @classmethod
    def _validate_delta(cls, value: Any) -> float | None:
        return _validate_optional_delta(value, field_name="MetricComparison.delta")

    @field_validator("status_count_deltas", mode="before")
    @classmethod
    def _validate_status_deltas(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        for k, v in value.items():
            _reject_strict_int(v, field_name=f"MetricComparison.status_count_deltas[{k!r}]")
        return value


class CaseMetricDelta(_StrictModel):
    """Single-metric baseline-versus-candidate delta on one aligned evaluation case."""

    metric_id: str = Field(min_length=1)
    baseline_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    baseline_status: MetricStatus | None = None
    candidate_status: MetricStatus | None = None
    regressed: bool = False
    direction: ComparisonDirection

    @field_validator("metric_id")
    @classmethod
    def _validate_metric_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="CaseMetricDelta.metric_id")

    @field_validator("baseline_score", "candidate_score", mode="before")
    @classmethod
    def _validate_scores(cls, value: Any, info: ValidationInfo) -> float | None:
        return _validate_optional_bounded_score(
            value, field_name=f"CaseMetricDelta.{info.field_name}"
        )

    @field_validator("delta", mode="before")
    @classmethod
    def _validate_delta(cls, value: Any) -> float | None:
        return _validate_optional_delta(value, field_name="CaseMetricDelta.delta")


class CaseComparison(_StrictModel):
    """Aligned case-level regression and transition summary across baseline and candidate."""

    case_id: str = Field(min_length=1)
    mandatory: bool = False
    regressed: bool = False
    mandatory_regressed: bool = False
    error_introduced: bool = False
    error_resolved: bool = False
    metrics: dict[str, CaseMetricDelta]

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="CaseComparison.case_id")


class TargetChangeSummary(_StrictModel):
    """Contextual summary of target system changes isolated from measurement drift."""

    system_version_changed: bool = False
    baseline_system_version: str | None = None
    candidate_system_version: str | None = None
    model_id_changed: bool = False
    baseline_model_id: str | None = None
    candidate_model_id: str | None = None
    config_fingerprint_changed: bool = False
    baseline_config_fingerprint: str | None = None
    candidate_config_fingerprint: str | None = None


class RunComparisonReport(_StrictModel):
    """Schema-versioned pairwise regression report between baseline and candidate runs."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    baseline_run_id: str = Field(min_length=1)
    candidate_run_id: str = Field(min_length=1)
    baseline_name: str | None = None
    target_changes: TargetChangeSummary
    metric_comparisons: dict[str, MetricComparison]
    case_comparisons: list[CaseComparison]
    matched_case_count: int = Field(ge=0)
    added_case_ids: list[str] = Field(default_factory=list)
    removed_case_ids: list[str] = Field(default_factory=list)
    regressed_case_ids: list[str] = Field(default_factory=list)
    mandatory_regressed_case_ids: list[str] = Field(default_factory=list)
    drift_warnings: list[DriftWarning] = Field(default_factory=list)
    anomalies: list[AnomalyFlag] = Field(default_factory=list)
    cohort: RunCohortSummary | None = None

    @field_validator("baseline_run_id", "candidate_run_id")
    @classmethod
    def _validate_run_ids(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"RunComparisonReport.{info.field_name}")

    @field_validator("baseline_name")
    @classmethod
    def _validate_baseline_name(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="RunComparisonReport.baseline_name")

    @field_validator("matched_case_count", mode="before")
    @classmethod
    def _validate_matched_count(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="RunComparisonReport.matched_case_count")

    @field_validator(
        "added_case_ids",
        "removed_case_ids",
        "regressed_case_ids",
        "mandatory_regressed_case_ids",
    )
    @classmethod
    def _validate_id_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"RunComparisonReport.{info.field_name}")
            for item in value
        ]


class TrendDataPoint(_StrictModel):
    """Single chronological observation within a sliding window trend series."""

    run_id: str = Field(min_length=1)
    timestamp: datetime
    index: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    metric_version: str | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_config_fingerprint: str | None = None

    @field_validator("run_id")
    @classmethod
    def _validate_run_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="TrendDataPoint.run_id")

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("index", mode="before")
    @classmethod
    def _validate_index(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="TrendDataPoint.index")

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: Any) -> float | None:
        return _validate_optional_bounded_score(value, field_name="TrendDataPoint.score")

    @field_validator("metric_version", "judge_config_fingerprint")
    @classmethod
    def _validate_opt_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"TrendDataPoint.{info.field_name}")


class MetricTrendSummary(_StrictModel):
    """OLS slope, statistics, and chronological trajectory for one metric."""

    metric_id: str = Field(min_length=1)
    window_runs: int = Field(ge=0)
    valid_points: int = Field(ge=0)
    missing_points: int = Field(ge=0)
    slope: float | None = None
    direction: TrendDirection
    first_score: float | None = Field(default=None, ge=0.0, le=1.0)
    last_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    points: list[TrendDataPoint] = Field(default_factory=list)
    explanation: str = Field(min_length=1)

    @field_validator("metric_id", "explanation")
    @classmethod
    def _validate_non_empty(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"MetricTrendSummary.{info.field_name}")

    @field_validator("window_runs", "valid_points", "missing_points", mode="before")
    @classmethod
    def _validate_counts(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"MetricTrendSummary.{info.field_name}")

    @field_validator("slope", mode="before")
    @classmethod
    def _validate_slope(cls, value: Any) -> float | None:
        return _validate_optional_delta(value, field_name="MetricTrendSummary.slope")

    @field_validator(
        "first_score",
        "last_score",
        "min_score",
        "max_score",
        "mean_score",
        mode="before",
    )
    @classmethod
    def _validate_bounds(cls, value: Any, info: ValidationInfo) -> float | None:
        return _validate_optional_bounded_score(
            value, field_name=f"MetricTrendSummary.{info.field_name}"
        )

    @model_validator(mode="after")
    def _validate_insufficient_data_consistency(self) -> MetricTrendSummary:
        if self.valid_points < 2:
            if self.slope is not None:
                raise ValueError("MetricTrendSummary.slope must be None when valid_points < 2")
            if self.direction != TrendDirection.INSUFFICIENT_DATA:
                raise ValueError(
                    "MetricTrendSummary.direction must be INSUFFICIENT_DATA when valid_points < 2"
                )
        return self


class TrendReport(_StrictModel):
    """Schema-versioned sliding window trajectory and drift summary across historical runs."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    window: int = Field(ge=2)
    dataset_id_filter: str | None = None
    model_id_filter: str | None = None
    inspected_run_ids: list[str] = Field(default_factory=list)
    slope_threshold: float = Field(default=0.01, gt=0.0, le=1.0)
    metrics: dict[str, MetricTrendSummary] = Field(default_factory=dict)
    drift_warnings: list[DriftWarning] = Field(default_factory=list)

    @field_validator("window", mode="before")
    @classmethod
    def _validate_window(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="TrendReport.window")

    @field_validator("dataset_id_filter", "model_id_filter")
    @classmethod
    def _validate_filters(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"TrendReport.{info.field_name}")

    @field_validator("inspected_run_ids")
    @classmethod
    def _validate_run_ids(cls, value: list[str]) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name="TrendReport.inspected_run_ids")
            for item in value
        ]

    @field_validator("slope_threshold", mode="before")
    @classmethod
    def _validate_threshold(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="TrendReport.slope_threshold")
        rounded = round_score(float(value))
        if not (0.0 < rounded <= 1.0):
            raise ValueError(
                f"TrendReport.slope_threshold must be within (0.0, 1.0], got {rounded}"
            )
        return rounded


class GateRuleCheck(_StrictModel):
    """Single policy check evaluation trace emitted by QualityGate."""

    rule_id: str = Field(min_length=1)
    status: GateDecision
    message: str = Field(min_length=1)
    metric_id: str | None = None
    observed: float | int | str | None = None
    threshold: float | int | str | None = None

    @field_validator("rule_id", "message")
    @classmethod
    def _validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"GateRuleCheck.{info.field_name}")

    @field_validator("metric_id")
    @classmethod
    def _validate_metric_id(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="GateRuleCheck.metric_id")

    @field_validator("observed", "threshold", mode="before")
    @classmethod
    def _validate_scalar(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"GateRuleCheck.{info.field_name}")
        if isinstance(value, float):
            return round_delta(value)
        return value


class QualityGateResult(_StrictModel):
    """Schema-versioned deterministic acceptance outcome emitted by QualityGate."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    decision: GateDecision
    candidate_run_id: str = Field(min_length=1)
    baseline_run_id: str | None = None
    passed: bool
    blocking: bool
    inconclusive_rate: float = Field(ge=0.0, le=1.0)
    checks: list[GateRuleCheck]
    failure_reasons: list[str] = Field(default_factory=list)
    inconclusive_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    drift_warnings: list[DriftWarning] = Field(default_factory=list)
    anomalies: list[AnomalyFlag] = Field(default_factory=list)
    cohort: RunCohortSummary | None = None
    summary: str = Field(min_length=1)

    @field_validator("candidate_run_id", "summary")
    @classmethod
    def _validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"QualityGateResult.{info.field_name}")

    @field_validator("baseline_run_id")
    @classmethod
    def _validate_baseline_run_id(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="QualityGateResult.baseline_run_id")

    @field_validator("inconclusive_rate", mode="before")
    @classmethod
    def _validate_inconclusive_rate(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="QualityGateResult.inconclusive_rate")
        rounded = round_score(float(value))
        if not (0.0 <= rounded <= 1.0):
            raise ValueError(
                f"QualityGateResult.inconclusive_rate must be within [0.0, 1.0], got {rounded}"
            )
        return rounded

    @field_validator("failure_reasons", "inconclusive_reasons", "warning_reasons")
    @classmethod
    def _validate_reason_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"QualityGateResult.{info.field_name}")
            for item in value
        ]

    @model_validator(mode="after")
    def _validate_decision_flags(self) -> QualityGateResult:
        expected_passed = self.decision == GateDecision.PASS
        expected_blocking = self.decision == GateDecision.FAIL
        if self.passed != expected_passed or self.blocking != expected_blocking:
            raise ValueError(
                f"QualityGateResult.passed/blocking flags must match decision {self.decision.value}"
            )
        return self


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


class JudgeConfig(_StrictModel):
    """Secret-free, canonical configuration for a model-based judge."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    model: str = Field(default="mock-judge", min_length=1)
    api_base: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    local_only: bool = False
    mock_mode: bool = False
    seed: int | None = None
    prompt_version: str = Field(default="1.0", min_length=1)
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model", "prompt_version")
    @classmethod
    def _validate_non_empty(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"JudgeConfig.{info.field_name}")

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, value: str | None) -> str | None:
        return _validate_http_api_base(value, field_name="JudgeConfig.api_base")

    @field_validator("temperature", "retry_backoff_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _validate_float_params(cls, value: Any, info: ValidationInfo) -> Any:
        _reject_bool_number(value, field_name=f"JudgeConfig.{info.field_name}")
        return value

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _validate_pass_threshold(cls, value: Any) -> Any:
        _reject_bool_number(value, field_name="JudgeConfig.pass_threshold")
        return round_score(float(value))

    @field_validator("max_retries", mode="before")
    @classmethod
    def _validate_max_retries(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="JudgeConfig.max_retries")

    @field_validator("seed", mode="before")
    @classmethod
    def _validate_seed(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="JudgeConfig.seed")

    @field_validator("extra_params")
    @classmethod
    def _validate_extra_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _ensure_json_serializable(value, field_name="JudgeConfig.extra_params")
        sanitized = redact_secrets(checked)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("JudgeConfig.extra_params must be a JSON object")
        return sanitized

    def redacted_dict(self) -> dict[str, Any]:
        """Return redacted canonical dictionary representation safe for persistence."""
        payload = self.model_dump(mode="json")
        sanitized = redact_secrets(payload)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("JudgeConfig redacted payload must be a dict")
        return sanitized

    @property
    def fingerprint(self) -> str:
        """Compute deterministic canonical SHA-256 over redacted judge configuration."""
        return canonical_sha256(self.redacted_dict())


class EmbeddingConfig(_StrictModel):
    """Secret-free, canonical configuration for embedding similarity metrics."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    model: str = Field(default="mock-embedding", min_length=1)
    api_base: str | None = None
    pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    aggregation: EmbeddingAggregation = EmbeddingAggregation.MAX
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    max_input_chars: int | None = Field(default=None, gt=0)
    local_only: bool = False
    mock_mode: bool = False
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="EmbeddingConfig.model")

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, value: str | None) -> str | None:
        return _validate_http_api_base(value, field_name="EmbeddingConfig.api_base")

    @field_validator("retry_backoff_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _validate_float_params(cls, value: Any, info: ValidationInfo) -> Any:
        _reject_bool_number(value, field_name=f"EmbeddingConfig.{info.field_name}")
        return value

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _validate_pass_threshold(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="EmbeddingConfig.pass_threshold")
        return round_score(float(value))

    @field_validator("max_retries", "max_input_chars", mode="before")
    @classmethod
    def _validate_int_params(cls, value: Any, info: ValidationInfo) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"EmbeddingConfig.{info.field_name}")

    @field_validator("extra_params")
    @classmethod
    def _validate_extra_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _ensure_json_serializable(value, field_name="EmbeddingConfig.extra_params")
        sanitized = redact_secrets(checked)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("EmbeddingConfig.extra_params must be a JSON object")
        return sanitized

    def redacted_dict(self) -> dict[str, Any]:
        """Return redacted canonical dictionary representation safe for persistence."""
        payload = self.model_dump(mode="json")
        sanitized = redact_secrets(payload)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("EmbeddingConfig redacted payload must be a dict")
        return sanitized

    @property
    def fingerprint(self) -> str:
        """Compute deterministic canonical SHA-256 over redacted embedding configuration."""
        return canonical_sha256(self.redacted_dict())


class JudgeResponse(_StrictModel):
    """Strict structured response contract required from model-based judges."""

    score: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    verdict: str | None = None
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _validate_score(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="JudgeResponse.score")
        return round_score(float(value))

    @field_validator("rationale")
    @classmethod
    def _validate_rationale(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="JudgeResponse.rationale")

    @field_validator("verdict")
    @classmethod
    def _validate_verdict(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="JudgeResponse.verdict")

    @field_validator("supported_claims", "unsupported_claims")
    @classmethod
    def _validate_claims(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"JudgeResponse.{info.field_name}")
            for item in value
        ]


class HumanCalibrationSample(_StrictModel):
    """Human ground-truth labeled sample used to calibrate a judge metric."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    input: Any
    output: Any
    reference: Any = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    human_score: float | None = Field(default=None, ge=0.0, le=1.0)
    human_passed: bool | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="HumanCalibrationSample.case_id")

    @field_validator("input", "output", "reference")
    @classmethod
    def _validate_payloads(cls, value: Any, info: ValidationInfo) -> Any:
        return _ensure_json_serializable(
            value, field_name=f"HumanCalibrationSample.{info.field_name}"
        )

    @field_validator("human_score", mode="before")
    @classmethod
    def _validate_human_score(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="HumanCalibrationSample.human_score")
        return round_score(float(value))

    @field_validator("notes")
    @classmethod
    def _validate_notes(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="HumanCalibrationSample.notes")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _ensure_json_serializable(value, field_name="HumanCalibrationSample.metadata")
        sanitized = redact_secrets(checked)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("HumanCalibrationSample.metadata must be a JSON object")
        return sanitized

    @model_validator(mode="after")
    def _validate_human_label_present(self) -> HumanCalibrationSample:
        if self.human_score is None and self.human_passed is None:
            raise ValueError(
                "HumanCalibrationSample requires at least one of human_score or human_passed"
            )
        return self


class CalibrationDisagreement(_StrictModel):
    """Per-case human-versus-judge disagreement or inconclusive inspection record."""

    case_id: str = Field(min_length=1)
    disagreement_type: CalibrationDisagreementType
    human_score: float | None = Field(default=None, ge=0.0, le=1.0)
    human_passed: bool
    judge_score: float | None = Field(default=None, ge=0.0, le=1.0)
    judge_status: MetricStatus
    judge_passed: bool | None = None
    score_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    judge_rationale: str = Field(min_length=1)
    human_notes: str | None = None

    @field_validator("case_id", "judge_rationale")
    @classmethod
    def _validate_required_str(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"CalibrationDisagreement.{info.field_name}")

    @field_validator("human_score", "judge_score", mode="before")
    @classmethod
    def _validate_opt_scores(cls, value: Any, info: ValidationInfo) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"CalibrationDisagreement.{info.field_name}")
        return round_score(float(value))

    @field_validator("score_delta", mode="before")
    @classmethod
    def _validate_score_delta(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="CalibrationDisagreement.score_delta")
        return round_delta(float(value))

    @field_validator("human_notes")
    @classmethod
    def _validate_human_notes(cls, value: str | None) -> str | None:
        return _validate_optional_str(value, field_name="CalibrationDisagreement.human_notes")


class CalibrationReport(_StrictModel):
    """Schema-versioned human ground-truth calibration summary and threshold recommendation."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    metric_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    judge_config: JudgeConfig
    judge_config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_cases: int = Field(ge=1)
    valid_cases: int = Field(ge=0)
    inconclusive_cases: int = Field(ge=0)
    pass_threshold_evaluated: float = Field(ge=0.0, le=1.0)
    human_threshold_evaluated: float = Field(ge=0.0, le=1.0)
    score_divergence_threshold: float = Field(default=0.25, gt=0.0, le=1.0)
    exact_agreement_rate: float | None = Field(default=None, ge=0.0, le=100.0)
    too_generous_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    too_harsh_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_human_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_judge_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_score_delta: float | None = Field(default=None, ge=-1.0, le=1.0)
    disagreements: list[CalibrationDisagreement] = Field(default_factory=list)
    recommended_pass_threshold: float = Field(ge=0.0, le=1.0)

    @field_validator("metric_id", "metric_version")
    @classmethod
    def _validate_metric_ids(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"CalibrationReport.{info.field_name}")

    @field_validator("total_cases", "valid_cases", "inconclusive_cases", mode="before")
    @classmethod
    def _validate_case_counts(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"CalibrationReport.{info.field_name}")

    @field_validator(
        "pass_threshold_evaluated",
        "human_threshold_evaluated",
        "score_divergence_threshold",
        "recommended_pass_threshold",
        mode="before",
    )
    @classmethod
    def _validate_thresholds(cls, value: Any, info: ValidationInfo) -> float:
        _reject_bool_number(value, field_name=f"CalibrationReport.{info.field_name}")
        return round_score(float(value))

    @field_validator("exact_agreement_rate", mode="before")
    @classmethod
    def _validate_agreement_pct(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="CalibrationReport.exact_agreement_rate")
        return round_percentage(float(value))

    @field_validator(
        "too_generous_rate",
        "too_harsh_rate",
        "mean_human_score",
        "mean_judge_score",
        mode="before",
    )
    @classmethod
    def _validate_opt_unit_metrics(cls, value: Any, info: ValidationInfo) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"CalibrationReport.{info.field_name}")
        return round_score(float(value))

    @field_validator("mean_score_delta", mode="before")
    @classmethod
    def _validate_mean_score_delta(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="CalibrationReport.mean_score_delta")
        return round_delta(float(value))

    @model_validator(mode="after")
    def _validate_report_consistency(self) -> CalibrationReport:
        if self.valid_cases + self.inconclusive_cases != self.total_cases:
            raise ValueError(
                "CalibrationReport requires valid_cases + inconclusive_cases == total_cases"
            )
        summary_values = (
            self.exact_agreement_rate,
            self.too_generous_rate,
            self.too_harsh_rate,
            self.mean_human_score,
            self.mean_judge_score,
            self.mean_score_delta,
        )
        if self.valid_cases == 0:
            if any(v is not None for v in summary_values):
                raise ValueError(
                    "CalibrationReport summary metrics must be None when valid_cases == 0"
                )
        elif any(v is None for v in summary_values):
            raise ValueError(
                "CalibrationReport summary metrics must not be None when valid_cases > 0"
            )
        return self


@runtime_checkable
class AsyncBatchMetric(Protocol):
    """Protocol for async batch-capable metrics preserving context-grouped dispatch."""

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metric metadata declaration."""

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Evaluate one case synchronously."""

    async def aevaluate_batch(
        self,
        items: Sequence[tuple[EvaluationCase, ExecutionResult]],
        *,
        max_concurrency: int = 4,
    ) -> list[MetricResult]:
        """Evaluate a sequence of case/execution pairs concurrently under max_concurrency."""


class MetricSpecConfig(_StrictModel):
    """Declarative single metric identifier and optional parameter snapshot."""

    metric_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metric_id")
    @classmethod
    def _validate_metric_id(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="MetricSpecConfig.metric_id")

    @field_validator("params")
    @classmethod
    def _validate_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        checked = _ensure_json_serializable(value, field_name="MetricSpecConfig.params")
        sanitized = redact_secrets(checked)
        if not isinstance(sanitized, dict):  # pragma: no cover - defensive guard
            raise ValueError("MetricSpecConfig.params must be a JSON object")
        return sanitized


class ResolvedSecurityConfig(_StrictModel):
    """Resolved locality and pre-network PII egress blocking policy."""

    local_only: bool = False
    block_pii: bool = False


class ResolvedTargetConfig(_StrictModel):
    """Resolved CLI target adapter or offline replay binding configuration."""

    target_type: TargetType | None = None
    entrypoint: str | None = None
    system_version: str | None = None
    model_id: str | None = None
    arg_mode: Literal["input", "case"] = "input"
    rag_extractors: dict[str, str] = Field(default_factory=dict)
    agent_extractors: dict[str, str] = Field(default_factory=dict)
    docpipe_mode: Literal["answer_detailed", "retrieve"] = "answer_detailed"
    docpipe_collection: str | None = None
    docpipe_persist_dir: str | None = None
    docpipe_top_k: int | None = Field(default=None, ge=1)
    docpipe_embed_model: str | None = None
    docpipe_answer_model: str | None = None
    docpipe_api_base: str | None = None
    docpipe_searcher: str | None = None
    docpipe_rerank: bool = False

    @field_validator(
        "entrypoint",
        "system_version",
        "model_id",
        "docpipe_collection",
        "docpipe_persist_dir",
        "docpipe_embed_model",
        "docpipe_answer_model",
        "docpipe_searcher",
    )
    @classmethod
    def _validate_opt_strings(cls, value: str | None, info: ValidationInfo) -> str | None:
        cleaned = _validate_optional_str(
            value, field_name=f"ResolvedTargetConfig.{info.field_name}"
        )
        return scrub_secret_text(cleaned) if cleaned is not None else None

    @field_validator("docpipe_api_base")
    @classmethod
    def _validate_docpipe_api_base(cls, value: str | None) -> str | None:
        return _validate_http_api_base(value, field_name="ResolvedTargetConfig.docpipe_api_base")

    @field_validator("rag_extractors", "agent_extractors")
    @classmethod
    def _validate_extractors(cls, value: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        return {
            _ensure_non_empty_str(k, field_name=f"ResolvedTargetConfig.{info.field_name}"): (
                _ensure_non_empty_str(v, field_name=f"ResolvedTargetConfig.{info.field_name}")
            )
            for k, v in value.items()
        }

    @field_validator("docpipe_top_k", mode="before")
    @classmethod
    def _validate_top_k(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="ResolvedTargetConfig.docpipe_top_k")


class ResolvedJudgeSettings(_StrictModel):
    """Redacted judge runtime and calibration settings resolved across CLI config tiers."""

    model: str = Field(default="mock-judge", min_length=1)
    api_base: str | None = None
    api_key: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    prompt_version: str = Field(default="1.0", min_length=1)
    mock_mode: bool = False
    local_only: bool = False
    seed: int | None = None
    min_agreement: float | None = Field(default=None, ge=0.0, le=100.0)

    @field_validator("model", "prompt_version")
    @classmethod
    def _validate_non_empty(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"ResolvedJudgeSettings.{info.field_name}")

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, value: str | None) -> str | None:
        return _validate_http_api_base(value, field_name="ResolvedJudgeSettings.api_base")

    @field_validator("api_key")
    @classmethod
    def _mask_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return REDACTED_VALUE

    @field_validator("temperature", "retry_backoff_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _validate_float_params(cls, value: Any, info: ValidationInfo) -> Any:
        _reject_bool_number(value, field_name=f"ResolvedJudgeSettings.{info.field_name}")
        return value

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _validate_pass_threshold(cls, value: Any) -> Any:
        _reject_bool_number(value, field_name="ResolvedJudgeSettings.pass_threshold")
        return round_score(float(value))

    @field_validator("min_agreement", mode="before")
    @classmethod
    def _validate_min_agreement(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="ResolvedJudgeSettings.min_agreement")
        return round_percentage(float(value))

    @field_validator("max_retries", "seed", mode="before")
    @classmethod
    def _validate_ints(cls, value: Any, info: ValidationInfo) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"ResolvedJudgeSettings.{info.field_name}")


class ResolvedEmbeddingSettings(_StrictModel):
    """Secret-free embedding runtime settings resolved across CLI configuration tiers."""

    model: str = Field(default="mock-embedding", min_length=1)
    api_base: str | None = None
    api_key_configured: bool = False
    pass_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    aggregation: EmbeddingAggregation = EmbeddingAggregation.MAX
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    max_input_chars: int | None = Field(default=None, gt=0)
    mock_mode: bool = False
    local_only: bool = False

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ResolvedEmbeddingSettings.model")

    @field_validator("api_base")
    @classmethod
    def _validate_api_base(cls, value: str | None) -> str | None:
        return _validate_http_api_base(value, field_name="ResolvedEmbeddingSettings.api_base")

    @field_validator("retry_backoff_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _validate_float_params(cls, value: Any, info: ValidationInfo) -> Any:
        _reject_bool_number(value, field_name=f"ResolvedEmbeddingSettings.{info.field_name}")
        return value

    @field_validator("pass_threshold", mode="before")
    @classmethod
    def _validate_pass_threshold(cls, value: Any) -> float:
        _reject_bool_number(value, field_name="ResolvedEmbeddingSettings.pass_threshold")
        return round_score(float(value))

    @field_validator("max_retries", "max_input_chars", mode="before")
    @classmethod
    def _validate_int_params(cls, value: Any, info: ValidationInfo) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"ResolvedEmbeddingSettings.{info.field_name}")


class ResolvedLoggingConfig(_StrictModel):
    """Resolved CLI stderr diagnostic verbosity and structured logging mode."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"
    log_json: bool = False


class ConfigSettingProvenance(_StrictModel):
    """Provenance record attributing one effective config value to its resolution tier."""

    key: str = Field(min_length=1)
    value: Any = None
    source: ConfigSourceTier
    masked: bool = False

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="ConfigSettingProvenance.key")

    @model_validator(mode="after")
    def _enforce_secret_masking(self) -> ConfigSettingProvenance:
        leaf = self.key.rsplit(".", 1)[-1]
        raw_json = _ensure_json_serializable(self.value, field_name="provenance")
        sanitized_val = redact_secrets(raw_json)
        if isinstance(sanitized_val, str):
            sanitized_val = scrub_secret_text(sanitized_val)
        if is_sensitive_key(leaf) or self.masked:
            object.__setattr__(self, "masked", self.masked or (sanitized_val is not None))
            if sanitized_val is not None:
                object.__setattr__(self, "value", REDACTED_VALUE)
        else:
            object.__setattr__(self, "value", sanitized_val)
        return self


class CLIResolvedConfig(_StrictModel):
    """Schema-versioned effective CLI configuration with credential masking and provenance."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    config_path: str | None = None
    env_file_path: str | None = None
    storage_dir: str = Field(default=".evalforge", min_length=1)
    dataset: str | None = None
    dataset_id: str | None = None
    dataset_version: str | None = None
    executions_path: str | None = None
    otel_traces: str | None = None
    run_id: str | None = None
    repeats: int = Field(default=1, ge=1, le=100)
    baseline: str | None = None
    baseline_runs: list[str] = Field(default_factory=list)
    trend_window: int | None = Field(default=None, ge=2)
    strict: bool = False
    target: ResolvedTargetConfig = Field(default_factory=ResolvedTargetConfig)
    otel: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)
    metrics: list[MetricSpecConfig] = Field(default_factory=list)
    execution: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    judge: ResolvedJudgeSettings = Field(default_factory=ResolvedJudgeSettings)
    embedding: ResolvedEmbeddingSettings = Field(default_factory=ResolvedEmbeddingSettings)
    security: ResolvedSecurityConfig = Field(default_factory=ResolvedSecurityConfig)
    gate: QualityGatePolicy = Field(default_factory=QualityGatePolicy)
    logging: ResolvedLoggingConfig = Field(default_factory=ResolvedLoggingConfig)
    provenance: list[ConfigSettingProvenance] = Field(default_factory=list)

    @field_validator("storage_dir")
    @classmethod
    def _validate_storage_dir(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="CLIResolvedConfig.storage_dir")

    @field_validator(
        "config_path",
        "env_file_path",
        "dataset",
        "dataset_id",
        "dataset_version",
        "executions_path",
        "otel_traces",
        "run_id",
        "baseline",
    )
    @classmethod
    def _validate_opt_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"CLIResolvedConfig.{info.field_name}")

    @field_validator("baseline_runs")
    @classmethod
    def _validate_baseline_runs(cls, value: list[str]) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name="CLIResolvedConfig.baseline_runs")
            for item in value
        ]

    @field_validator("trend_window", mode="before")
    @classmethod
    def _validate_trend_window(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="CLIResolvedConfig.trend_window")

    @field_validator("repeats", mode="before")
    @classmethod
    def _validate_repeats(cls, value: Any) -> int:
        return _reject_strict_int(value, field_name="CLIResolvedConfig.repeats")


class DecoupledEvidenceDiagnostic(_StrictModel):
    """Diagnostic record flagging retrieval-vs-answer or groundedness decoupling on a case."""

    case_id: str = Field(min_length=1)
    mandatory: bool = False
    category: EvidenceDecouplingCategory
    passed_metrics: list[str] = Field(min_length=1)
    failed_metrics: list[str] = Field(min_length=1)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)

    @field_validator("case_id", "explanation")
    @classmethod
    def _validate_non_empty(cls, value: str, info: ValidationInfo) -> str:
        cleaned = _ensure_non_empty_str(
            value, field_name=f"DecoupledEvidenceDiagnostic.{info.field_name}"
        )
        return scrub_secret_text(cleaned)

    @field_validator("passed_metrics", "failed_metrics", "retrieved_chunk_ids")
    @classmethod
    def _validate_id_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name=f"DecoupledEvidenceDiagnostic.{info.field_name}")
            for item in value
        ]


class ReportDiagnosticsSummary(_StrictModel):
    """High-visibility diagnostic summary surfaced across JSON and Markdown reports."""

    mandatory_failed_case_ids: list[str] = Field(default_factory=list)
    decoupled_evidence_cases: list[DecoupledEvidenceDiagnostic] = Field(default_factory=list)
    anomaly_highlights: list[AnomalyFlag] = Field(default_factory=list)
    drift_highlights: list[DriftWarning] = Field(default_factory=list)

    @field_validator("mandatory_failed_case_ids")
    @classmethod
    def _validate_failed_ids(cls, value: list[str]) -> list[str]:
        return [
            _ensure_non_empty_str(
                item, field_name="ReportDiagnosticsSummary.mandatory_failed_case_ids"
            )
            for item in value
        ]


class CalibrationGateSummary(_StrictModel):
    """Calibration pass/fail assessment applying optional --min-agreement and --strict checks."""

    min_agreement: float | None = Field(default=None, ge=0.0, le=100.0)
    observed_agreement: float | None = Field(default=None, ge=0.0, le=100.0)
    strict: bool = False
    valid_cases: int = Field(ge=0)
    inconclusive_cases: int = Field(ge=0)
    passed: bool
    reason: str = Field(min_length=1)

    @field_validator("min_agreement", "observed_agreement", mode="before")
    @classmethod
    def _validate_percentages(cls, value: Any, info: ValidationInfo) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"CalibrationGateSummary.{info.field_name}")
        return round_percentage(float(value))

    @field_validator("valid_cases", "inconclusive_cases", mode="before")
    @classmethod
    def _validate_counts(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"CalibrationGateSummary.{info.field_name}")

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        return _ensure_non_empty_str(value, field_name="CalibrationGateSummary.reason")


class ReportDocument(_StrictModel):
    """Canonical schema-validated JSON payload splitting evaluation, regression, and gate."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    report_kind: ReportKind
    title: str = Field(min_length=1)
    generated_at: datetime
    evaluation: RunRecord | None = None
    comparison: RunComparisonReport | None = None
    trend: TrendReport | None = None
    calibration: CalibrationReport | None = None
    gate: QualityGateResult | None = None
    calibration_gate: CalibrationGateSummary | None = None
    diagnostics: ReportDiagnosticsSummary = Field(default_factory=ReportDiagnosticsSummary)
    cohort_run_ids: list[str] = Field(default_factory=list)
    cohort_aggregates: dict[str, AggregateMetricSummary] = Field(default_factory=dict)

    @field_validator("cohort_run_ids")
    @classmethod
    def _validate_cohort_run_ids(cls, value: list[str]) -> list[str]:
        return [
            _ensure_non_empty_str(item, field_name="ReportDocument.cohort_run_ids")
            for item in value
        ]

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return scrub_secret_text(_ensure_non_empty_str(value, field_name="ReportDocument.title"))

    @field_validator("generated_at")
    @classmethod
    def _normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_kind_alignment(self) -> ReportDocument:
        if self.report_kind == ReportKind.RUN:
            if self.evaluation is None:
                raise ValueError("ReportDocument.evaluation is required when report_kind == 'run'")
            if self.calibration is not None:
                raise ValueError(
                    "ReportDocument.calibration must be None when report_kind == 'run'"
                )
        elif self.report_kind == ReportKind.COMPARE:
            if self.comparison is None:
                raise ValueError(
                    "ReportDocument.comparison is required when report_kind == 'compare'"
                )
        elif self.report_kind == ReportKind.TREND:
            if self.trend is None:
                raise ValueError("ReportDocument.trend is required when report_kind == 'trend'")
        elif self.report_kind == ReportKind.CALIBRATE:
            if self.calibration is None:
                raise ValueError(
                    "ReportDocument.calibration is required when report_kind == 'calibrate'"
                )
            if self.evaluation is not None or self.comparison is not None or self.trend is not None:
                raise ValueError(
                    "ReportDocument evaluation/comparison/trend must be None when "
                    "report_kind == 'calibrate'"
                )
        return self


class BaselineCommandPayload(_StrictModel):
    """Typed CLI --json payload emitted by `evalforge-maestro baseline` actions."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    action: Literal["set", "list", "show", "delete"]
    entry: BaselineEntry | None = None
    baselines: list[BaselineEntry] = Field(default_factory=list)


class ConfigValidationPayload(_StrictModel):
    """Typed CLI --json payload emitted by `evalforge-maestro config validate`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    valid: bool
    config_path: str | None = None
    env_file_path: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("warnings")
    @classmethod
    def _validate_warnings(cls, value: list[str]) -> list[str]:
        return [
            scrub_secret_text(
                _ensure_non_empty_str(w, field_name="ConfigValidationPayload.warnings")
            )
            for w in value
        ]


class CLIErrorPayload(_StrictModel):
    """Typed CLI --json error payload emitted on exit codes 2, 3, or 4."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    exit_code: Literal[2, 3, 4]
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    hint: str | None = None

    @field_validator("error_type", "message")
    @classmethod
    def _validate_required(cls, value: str, info: ValidationInfo) -> str:
        return scrub_secret_text(
            _ensure_non_empty_str(value, field_name=f"CLIErrorPayload.{info.field_name}")
        )

    @field_validator("hint")
    @classmethod
    def _validate_hint(cls, value: str | None) -> str | None:
        cleaned = _validate_optional_str(value, field_name="CLIErrorPayload.hint")
        return scrub_secret_text(cleaned) if cleaned is not None else None


class RunQueryFilter(_StrictModel):
    """Typed filter contract for querying indexed runs in SQLiteRunIndex."""

    dataset_id: str | None = None
    dataset_version: str | None = None
    run_ids: list[str] | None = None
    model_id: str | None = None
    system_version: str | None = None
    baseline_name: str | None = None
    metric_id: str | None = None
    min_mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    has_mandatory_failures: bool | None = None
    since: datetime | None = None
    until: datetime | None = None
    order_by: RunSortOrder = RunSortOrder.TIMESTAMP_DESC
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @field_validator(
        "dataset_id",
        "dataset_version",
        "model_id",
        "system_version",
        "baseline_name",
        "metric_id",
    )
    @classmethod
    def _validate_opt_strs(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"RunQueryFilter.{info.field_name}")

    @field_validator("run_ids")
    @classmethod
    def _validate_run_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [_ensure_non_empty_str(item, field_name="RunQueryFilter.run_ids") for item in value]

    @field_validator("min_mean_score", "max_mean_score", mode="before")
    @classmethod
    def _validate_score_bounds(cls, value: Any, info: ValidationInfo) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"RunQueryFilter.{info.field_name}")
        return float(value)

    @field_validator("limit", "offset", mode="before")
    @classmethod
    def _validate_pagination(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"RunQueryFilter.{info.field_name}")

    @field_validator("since", "until")
    @classmethod
    def _normalize_dates(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> RunQueryFilter:
        if (
            self.min_mean_score is not None or self.max_mean_score is not None
        ) and self.metric_id is None:
            raise ValueError(
                "RunQueryFilter.metric_id is required when filtering by min_mean_score "
                "or max_mean_score"
            )
        if (
            self.min_mean_score is not None
            and self.max_mean_score is not None
            and self.min_mean_score > self.max_mean_score
        ):
            raise ValueError("RunQueryFilter.min_mean_score must not exceed max_mean_score")
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("RunQueryFilter.since must not exceed until")
        return self


class CaseQueryFilter(_StrictModel):
    """Typed filter contract for querying per-case metric rows in SQLiteRunIndex."""

    run_id: str | None = None
    dataset_id: str | None = None
    case_id: str | None = None
    metric_id: str | None = None
    status: MetricStatus | None = None
    mandatory_only: bool = False
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_score: float | None = Field(default=None, ge=0.0, le=1.0)
    has_errors: bool | None = None
    has_anomaly_flags: bool | None = None
    limit: int = Field(default=100, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)

    @field_validator("run_id", "dataset_id", "case_id", "metric_id")
    @classmethod
    def _validate_opt_strs(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"CaseQueryFilter.{info.field_name}")

    @field_validator("min_score", "max_score", mode="before")
    @classmethod
    def _validate_score_bounds(cls, value: Any, info: ValidationInfo) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name=f"CaseQueryFilter.{info.field_name}")
        return float(value)

    @field_validator("limit", "offset", mode="before")
    @classmethod
    def _validate_pagination(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"CaseQueryFilter.{info.field_name}")

    @model_validator(mode="after")
    def _validate_bounds(self) -> CaseQueryFilter:
        if (
            self.min_score is not None
            and self.max_score is not None
            and self.min_score > self.max_score
        ):
            raise ValueError("CaseQueryFilter.min_score must not exceed max_score")
        return self


class IndexedRunSummary(_StrictModel):
    """Projected canonical run summary returned by SQLiteRunIndex.query_runs."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    timestamp: datetime
    dataset_id: str = Field(min_length=1)
    dataset_version: str | None = None
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_case_count: int = Field(ge=1)
    dataset_capped: bool = False
    system_version: str | None = None
    model_id: str | None = None
    config_fingerprint: str | None = None
    has_mandatory_failures: bool = False
    mandatory_failed_case_ids: list[str] = Field(default_factory=list)
    baseline_names: list[str] = Field(default_factory=list)
    aggregate_scores: dict[str, float | None] = Field(default_factory=dict)
    status_counts: dict[MetricStatus, int] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("aggregate_scores", mode="before")
    @classmethod
    def _round_scores(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        out: dict[str, float | None] = {}
        for k, v in value.items():
            if v is None:
                out[str(k)] = None
            else:
                _reject_bool_number(v, field_name="IndexedRunSummary.aggregate_scores")
                out[str(k)] = round_score(float(v))
        return out


class IndexedCaseMetricRow(_StrictModel):
    """Projected per-case metric evaluation row returned by SQLiteRunIndex.query_cases."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    timestamp: datetime
    dataset_id: str = Field(min_length=1)
    model_id: str | None = None
    system_version: str | None = None
    case_id: str = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    status: MetricStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    mandatory: bool = False
    elapsed_seconds: float = Field(ge=0.0)
    has_errors: bool = False
    anomaly_count: int = Field(default=0, ge=0)
    explanation: str = ""

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("score", mode="before")
    @classmethod
    def _round_score(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="IndexedCaseMetricRow.score")
        return round_score(float(value))

    @field_validator("explanation")
    @classmethod
    def _scrub_explanation(cls, value: str) -> str:
        return scrub_secret_text(value)


class IndexedMetricPoint(_StrictModel):
    """Chronological run-level metric summary returned by SQLiteRunIndex.metric_history."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    metric_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    timestamp: datetime
    dataset_id: str = Field(min_length=1)
    model_id: str | None = None
    system_version: str | None = None
    mean_score: float | None = Field(default=None, ge=0.0, le=1.0)
    applicable_count: int = Field(default=0, ge=0)
    pass_count: int = Field(default=0, ge=0)
    fail_count: int = Field(default=0, ge=0)

    @field_validator("timestamp")
    @classmethod
    def _normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("mean_score", mode="before")
    @classmethod
    def _round_mean(cls, value: Any) -> float | None:
        if value is None:
            return None
        _reject_bool_number(value, field_name="IndexedMetricPoint.mean_score")
        return round_score(float(value))


class SQLiteIndexStatus(_StrictModel):
    """Diagnostic health and sync parity snapshot for SQLiteRunIndex."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    db_path: str = Field(min_length=1)
    exists: bool
    corrupt: bool = False
    in_sync: bool
    index_schema_version: str = "1"
    db_size_bytes: int = Field(default=0, ge=0)
    canonical_run_count: int = Field(default=0, ge=0)
    indexed_run_count: int = Field(default=0, ge=0)
    baseline_count: int = Field(default=0, ge=0)
    pending_run_ids: list[str] = Field(default_factory=list)
    extra_indexed_run_ids: list[str] = Field(default_factory=list)
    stale_reason: str | None = None


class RunQueryPayload(_StrictModel):
    """Typed CLI --json payload emitted by `evalforge-maestro query runs`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    storage_dir: str = Field(min_length=1)
    total_returned: int = Field(ge=0)
    runs: list[IndexedRunSummary] = Field(default_factory=list)


class CaseQueryPayload(_StrictModel):
    """Typed CLI --json payload emitted by `evalforge-maestro query cases`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    storage_dir: str = Field(min_length=1)
    total_returned: int = Field(ge=0)
    cases: list[IndexedCaseMetricRow] = Field(default_factory=list)


class ServiceConfig(_StrictModel):
    """Configuration for the optional EvalForge Maestro HTTP evaluation service wrapper."""

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8787, ge=0, le=65535)
    storage_dir: str = Field(default=".evalforge", min_length=1)
    local_only: bool = True
    block_pii: bool = False
    mock_mode: bool = False
    max_request_bytes: int = Field(default=10_485_760, ge=1024, le=104_857_600)
    auth_token_configured: bool = False

    @field_validator("host", "storage_dir")
    @classmethod
    def _validate_non_empty_strs(cls, value: str, info: ValidationInfo) -> str:
        return _ensure_non_empty_str(value, field_name=f"ServiceConfig.{info.field_name}")

    @field_validator("port", "max_request_bytes", mode="before")
    @classmethod
    def _validate_strict_ints(cls, value: Any, info: ValidationInfo) -> int:
        return _reject_strict_int(value, field_name=f"ServiceConfig.{info.field_name}")


class ServiceHealthResponse(_StrictModel):
    """Typed health and index readiness response emitted by `GET /health`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status: Literal["ok"] = "ok"
    package_version: str = Field(min_length=1)
    storage_dir: str = Field(min_length=1)
    local_only: bool
    mock_mode: bool
    indexed_run_count: int = Field(ge=0)
    canonical_run_count: int = Field(ge=0)


class ServiceErrorResponse(_StrictModel):
    """Typed secret-redacted JSON error response emitted by EvalForge HTTP endpoints."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status_code: int = Field(ge=400, le=599)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    hint: str | None = None

    @field_validator("error_type", "message")
    @classmethod
    def _validate_required(cls, value: str, info: ValidationInfo) -> str:
        return scrub_secret_text(
            _ensure_non_empty_str(value, field_name=f"ServiceErrorResponse.{info.field_name}")
        )

    @field_validator("hint")
    @classmethod
    def _validate_hint(cls, value: str | None) -> str | None:
        cleaned = _validate_optional_str(value, field_name="ServiceErrorResponse.hint")
        return scrub_secret_text(cleaned) if cleaned is not None else None


class ServiceOtelIngestRequest(_StrictModel):
    """Typed request payload for `POST /v1/otel/ingest`."""

    payload: Any
    extractors: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)
    dataset: list[EvaluationCase] | None = None
    case_id_map: dict[str, str] | None = None
    system_version: str | None = None
    model_id: str | None = None

    @field_validator("system_version", "model_id")
    @classmethod
    def _validate_opt_strs(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(
            value, field_name=f"ServiceOtelIngestRequest.{info.field_name}"
        )


class ServiceOtelIngestResponse(_StrictModel):
    """Typed normalized OTel response emitted by `POST /v1/otel/ingest`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    count: int = Field(ge=0)
    executions: list[ExecutionResult] = Field(default_factory=list)


class ServiceEvaluateRequest(_StrictModel):
    """Typed offline/trace evaluation request accepted by `POST /v1/evaluate`."""

    cases: list[EvaluationCase] = Field(min_length=1)
    executions: list[ExecutionResult] | None = None
    otel_payload: Any = None
    otel_extractors: OtelExtractorConfig = Field(default_factory=OtelExtractorConfig)
    case_id_map: dict[str, str] | None = None
    dataset_id: str = Field(default="remote-eval", min_length=1)
    dataset_version: str | None = None
    metrics: list[MetricSpecConfig] = Field(default_factory=list)
    judge: JudgeConfig | None = None
    embedding: EmbeddingConfig | None = None
    gate: QualityGatePolicy = Field(default_factory=QualityGatePolicy)
    max_context_chars: int | None = Field(default=None, ge=1)
    max_concurrency: int = Field(default=4, ge=1, le=64)
    seed: int | None = None
    system_version: str | None = None
    model_id: str | None = None
    run_id: str | None = None
    persist: bool = False
    include_markdown: bool = False

    @field_validator("max_context_chars", "max_concurrency", "seed", mode="before")
    @classmethod
    def _validate_ints(cls, value: Any, info: ValidationInfo) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name=f"ServiceEvaluateRequest.{info.field_name}")

    @field_validator("dataset_version", "system_version", "model_id", "run_id")
    @classmethod
    def _validate_opt_strs(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _validate_optional_str(value, field_name=f"ServiceEvaluateRequest.{info.field_name}")

    @model_validator(mode="after")
    def _validate_trace_source(self) -> ServiceEvaluateRequest:
        has_exec = self.executions is not None
        has_otel = self.otel_payload is not None
        if has_exec == has_otel:
            raise ValueError(
                "ServiceEvaluateRequest must specify exactly one of 'executions' or 'otel_payload'"
            )
        return self


class ServiceEvaluateResponse(_StrictModel):
    """Typed Three-Way response emitted by `POST /v1/evaluate`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    persisted: bool
    evaluation: RunRecord
    gate: QualityGateResult
    report: ReportDocument
    markdown: str | None = None


class ServiceCompareRequest(_StrictModel):
    """Typed pairwise or cohort regression request for `POST /v1/compare`."""

    candidate_run_id: str | None = None
    candidate_run_ids: list[str] | None = None
    baseline_ref: str = Field(default="default", min_length=1)
    baseline_run_ids: list[str] | None = None
    policy: QualityGatePolicy = Field(default_factory=QualityGatePolicy)
    include_markdown: bool = False

    @model_validator(mode="after")
    def _validate_candidates(self) -> ServiceCompareRequest:
        has_single = bool(self.candidate_run_id and self.candidate_run_id.strip())
        has_cohort = bool(self.candidate_run_ids)
        if not has_single and not has_cohort:
            raise ValueError(
                "ServiceCompareRequest requires candidate_run_id or non-empty candidate_run_ids"
            )
        return self


class ServiceCompareResponse(_StrictModel):
    """Typed comparison and gate verdict response emitted by `POST /v1/compare`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    comparison: RunComparisonReport
    gate: QualityGateResult
    report: ReportDocument
    markdown: str | None = None


class ServiceReportRequest(_StrictModel):
    """Typed report rendering request accepted by `POST /v1/reports`."""

    run_id: str | None = None
    compare_run_id: str | None = None
    baseline_ref: str | None = None
    trend_window: int | None = Field(default=None, ge=2)
    dataset_id: str | None = None
    model_id: str | None = None
    title: str | None = None
    include_markdown: bool = True

    @field_validator("trend_window", mode="before")
    @classmethod
    def _validate_window(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _reject_strict_int(value, field_name="ServiceReportRequest.trend_window")

    @model_validator(mode="after")
    def _validate_source(self) -> ServiceReportRequest:
        if self.run_id is None and self.compare_run_id is None and self.trend_window is None:
            raise ValueError(
                "ServiceReportRequest requires at least one of run_id, compare_run_id, "
                "or trend_window"
            )
        return self


class ServiceReportResponse(_StrictModel):
    """Typed report document + optional Markdown response emitted by `POST /v1/reports`."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    report: ReportDocument
    markdown: str | None = None
