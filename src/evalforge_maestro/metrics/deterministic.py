"""Deterministic baseline evaluation metrics with pinned formula versions."""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Mapping
from typing import Any

from evalforge_maestro._canonical import round_score
from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)

_JSON_SCHEMA_INDICATOR_KEYS = frozenset(
    {
        "$schema",
        "$defs",
        "definitions",
        "type",
        "properties",
        "items",
        "required",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "enum",
        "const",
        "additionalProperties",
    }
)


def _validate_threshold(threshold: float) -> float:
    if isinstance(threshold, bool) or not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise MetricError(
            f"Metric threshold must be a finite float in [0.0, 1.0], got {threshold!r}"
        )
    return float(threshold)


def _resolve_threshold(case: EvaluationCase, metric_id: str, default_threshold: float) -> float:
    if metric_id in case.criteria.metric_thresholds:
        return case.criteria.metric_thresholds[metric_id]
    if case.criteria.pass_threshold is not None:
        return case.criteria.pass_threshold
    return default_threshold


def _normalize_text(text: str, *, case_sensitive: bool, strip_punctuation: bool) -> str:
    normalized = unicodedata.normalize("NFC", text)
    if strip_punctuation:
        normalized = "".join(
            ch for ch in normalized if not unicodedata.category(ch).startswith("P")
        )
    collapsed = " ".join(normalized.split())
    return collapsed if case_sensitive else collapsed.casefold()


def _inconclusive_result(
    metadata: MetricMetadata,
    execution: ExecutionResult,
    config_snapshot: dict[str, Any],
) -> MetricResult:
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=None,
        status=MetricStatus.INCONCLUSIVE,
        explanation=f"Upstream execution failed: {execution.errors[0]}",
        evidence=list(execution.errors),
        config_snapshot=config_snapshot,
    )


def _score_exact_match(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for exact_match v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"threshold": threshold}

    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)
    if case.reference is None:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation="EvaluationCase.reference is absent; exact_match is not applicable.",
            config_snapshot=snapshot,
        )

    if isinstance(case.reference, str):
        if not isinstance(execution.output, str):
            return MetricResult(
                metric_id=metadata.metric_id,
                metric_version=metadata.metric_version,
                score=0.0,
                status=MetricStatus.FAIL,
                label="type_mismatch",
                explanation=(
                    f"Type mismatch: expected str output, got {type(execution.output).__name__}."
                ),
                config_snapshot=snapshot,
            )
        matched = execution.output == case.reference
    else:
        matched = type(execution.output) is type(case.reference) and (
            execution.output == case.reference
        )

    score = round_score(1.0 if matched else 0.0)
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="match" if matched else "mismatch",
        explanation="Output exactly matches reference."
        if matched
        else "Output differs from reference.",
        config_snapshot=snapshot,
    )


def _score_normalized_match(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    case_sensitive: bool,
    strip_punctuation: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for normalized_match v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "case_sensitive": case_sensitive,
        "strip_punctuation": strip_punctuation,
        "threshold": threshold,
    }

    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)
    if case.reference is None or not isinstance(case.reference, str):
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                "EvaluationCase.reference is absent or non-string; "
                "normalized_match is not applicable."
            ),
            config_snapshot=snapshot,
        )
    if not isinstance(execution.output, str):
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=0.0,
            status=MetricStatus.FAIL,
            label="type_mismatch",
            explanation=(
                f"Type mismatch: expected str output, got {type(execution.output).__name__}."
            ),
            config_snapshot=snapshot,
        )

    norm_out = _normalize_text(
        execution.output,
        case_sensitive=case_sensitive,
        strip_punctuation=strip_punctuation,
    )
    norm_ref = _normalize_text(
        case.reference,
        case_sensitive=case_sensitive,
        strip_punctuation=strip_punctuation,
    )
    matched = norm_out == norm_ref
    score = round_score(1.0 if matched else 0.0)
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="match" if matched else "mismatch",
        explanation=(
            "Normalized output matches reference."
            if matched
            else "Normalized output differs from reference."
        ),
        config_snapshot=snapshot,
    )


def _resolve_target_schema(
    case: EvaluationCase,
    default_schema: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if case.criteria.json_schema is not None:
        return case.criteria.json_schema
    if isinstance(case.reference, dict) and (
        set(case.reference.keys()) & _JSON_SCHEMA_INDICATOR_KEYS
    ):
        return case.reference
    return default_schema


def _score_json_schema_validation(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    default_schema: dict[str, Any] | None,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for json_schema_validation v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {"threshold": threshold}

    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    target_schema = _resolve_target_schema(case, default_schema)
    if target_schema is None:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                "No JSON Schema specified on case criteria, schema-like reference, or metric."
            ),
            config_snapshot=snapshot,
        )

    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for

    validator_cls = validator_for(target_schema)
    try:
        validator_cls.check_schema(target_schema)
    except SchemaError as exc:
        raise MetricError(f"Invalid JSON Schema for case {case.id!r}: {exc.message}") from exc

    if execution.output is None:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=0.0,
            status=MetricStatus.FAIL,
            label="missing_output",
            explanation="Target produced None; valid JSON payload expected.",
            config_snapshot=snapshot,
        )

    if isinstance(execution.output, str):
        try:
            parsed: Any = json.loads(execution.output)
        except json.JSONDecodeError as exc:
            return MetricResult(
                metric_id=metadata.metric_id,
                metric_version=metadata.metric_version,
                score=0.0,
                status=MetricStatus.FAIL,
                label="invalid_json",
                explanation=f"Invalid JSON syntax at line {exc.lineno}, col {exc.colno}: {exc.msg}",
                config_snapshot=snapshot,
            )
    else:
        parsed = execution.output

    errors = sorted(
        validator_cls(target_schema).iter_errors(parsed),
        key=lambda err: (str(list(err.path)), err.message),
    )
    if errors:
        first = errors[0]
        path_display = ".".join(str(p) for p in first.path) or "<root>"
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=0.0,
            status=MetricStatus.FAIL,
            label="schema_violation",
            explanation=f"Schema validation failed at {path_display}: {first.message}",
            evidence=[
                f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
                for err in errors[:5]
            ],
            config_snapshot=snapshot,
        )

    score = round_score(1.0)
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=MetricStatus.PASS,
        label="valid",
        explanation="Output conforms to declared JSON Schema.",
        config_snapshot=snapshot,
    )


class ExactMatchMetric:
    """Strict equality metric comparing target output against expected reference."""

    _METADATA = MetricMetadata(
        metric_id="exact_match",
        metric_version="1.0.0",
        what_it_measures="Strict equality between target output and expected reference.",
        required_case_fields=("reference",),
        required_execution_fields=("output", "errors"),
        calculation_method=(
            "1.0 if string output == string reference (or identical non-string type and value); "
            "else 0.0."
        ),
        known_limitations=(
            "Sensitive to whitespace, casing, punctuation, and valid paraphrasing; "
            "non-string outputs fail against string references rather than coercing."
        ),
    )

    def __init__(self, *, threshold: float = 1.0) -> None:
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for exact_match."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate exact match between execution output and case reference."""
        return _score_exact_match(
            case,
            execution,
            metadata=self._METADATA,
            default_threshold=self._threshold,
        )


class NormalizedMatchMetric:
    """Canonical text-equivalence metric applying NFC, whitespace, and case normalization."""

    _METADATA = MetricMetadata(
        metric_id="normalized_match",
        metric_version="1.0.0",
        what_it_measures=(
            "Normalized lexical equality after Unicode NFC and whitespace normalization."
        ),
        required_case_fields=("reference",),
        required_execution_fields=("output", "errors"),
        calculation_method=(
            "Normalize Unicode NFC, optionally strip Unicode punctuation, collapse whitespace, "
            "optionally casefold, then score 1.0 on equality else 0.0."
        ),
        known_limitations=(
            "Lexical comparison only; cannot recognize semantically equivalent paraphrases "
            "with differing words."
        ),
    )

    def __init__(
        self,
        *,
        case_sensitive: bool = False,
        strip_punctuation: bool = False,
        threshold: float = 1.0,
    ) -> None:
        self._case_sensitive = case_sensitive
        self._strip_punctuation = strip_punctuation
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for normalized_match."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate normalized lexical equivalence between execution output and case reference."""
        return _score_normalized_match(
            case,
            execution,
            metadata=self._METADATA,
            case_sensitive=self._case_sensitive,
            strip_punctuation=self._strip_punctuation,
            default_threshold=self._threshold,
        )


class JsonSchemaValidationMetric:
    """Structural JSON Schema validator over serialized JSON or structured outputs."""

    _METADATA = MetricMetadata(
        metric_id="json_schema_validation",
        metric_version="1.0.0",
        what_it_measures="Syntactic JSON validity and structural conformance to a JSON Schema.",
        required_case_fields=("criteria.json_schema", "reference"),
        required_execution_fields=("output", "errors"),
        calculation_method=(
            "Resolve schema (criteria.json_schema > schema-like reference > metric default), "
            "parse string output via json.loads if needed, validate via jsonschema (1.0 vs 0.0)."
        ),
        known_limitations=(
            "Verifies structure and types only; does not validate factual accuracy or groundedness."
        ),
    )

    def __init__(
        self,
        *,
        schema: Mapping[str, Any] | None = None,
        threshold: float = 1.0,
    ) -> None:
        self._threshold = _validate_threshold(threshold)
        if schema is not None:
            from jsonschema.exceptions import SchemaError
            from jsonschema.validators import validator_for

            copied = dict(schema)
            try:
                validator_for(copied).check_schema(copied)
            except SchemaError as exc:
                raise MetricError(f"Invalid metric JSON Schema: {exc.message}") from exc
            self._default_schema: dict[str, Any] | None = copied
        else:
            self._default_schema = None

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for json_schema_validation."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate JSON syntax and schema conformance for execution output."""
        return _score_json_schema_validation(
            case,
            execution,
            metadata=self._METADATA,
            default_schema=self._default_schema,
            default_threshold=self._threshold,
        )


exact_match = ExactMatchMetric()
normalized_match = NormalizedMatchMetric()
json_schema_validation = JsonSchemaValidationMetric()
