"""Contract tests pinning public __all__ exports, exceptions, and entrypoint signatures."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import evalforge_maestro
from evalforge_maestro import adapters, datasets, execution, metrics, storage
from evalforge_maestro.exceptions import (
    AdapterError,
    ConfigurationError,
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
    EvalforgeError,
    ExecutionError,
    ImmutabilityError,
    MemoryLimitExceededError,
    MetricError,
    MissingExtraError,
    StorageError,
)


def _param_spec(fn: Callable[..., Any]) -> list[tuple[str, str]]:
    sig = inspect.signature(fn)
    return [(name, p.kind.name) for name, p in sig.parameters.items()]


def test_public_all_exports_and_exception_hierarchy() -> None:
    expected_top_all = {
        "SCHEMA_VERSION",
        "AdapterError",
        "AggregateMetricSummary",
        "CallableAdapter",
        "CaseCriteria",
        "CaseEvaluationRecord",
        "CaseMetadata",
        "CaseSplit",
        "ConfigurationError",
        "DatasetEngine",
        "DatasetError",
        "DatasetStreamResult",
        "DuplicateCaseIdError",
        "EmptyDatasetError",
        "EvalforgeError",
        "EvaluationCase",
        "EvaluationOrchestrator",
        "ExactMatchMetric",
        "ExecutionError",
        "ExecutionResult",
        "ImmutabilityError",
        "JsonSchemaValidationMetric",
        "LocalRunStore",
        "MemoryLimitExceededError",
        "Metric",
        "MetricError",
        "MetricMetadata",
        "MetricResult",
        "MetricStatus",
        "MissingExtraError",
        "NormalizedMatchMetric",
        "OrchestratorConfig",
        "RetrievedChunk",
        "RunManifestEntry",
        "RunRecord",
        "StorageError",
        "TargetAdapter",
        "TokenUsage",
        "__version__",
        "exact_match",
        "json_schema_validation",
        "normalized_match",
    }
    assert set(evalforge_maestro.__all__) == expected_top_all
    assert set(datasets.__all__) == {"DatasetEngine", "DatasetStreamResult"}
    assert set(adapters.__all__) == {"CallableAdapter"}
    assert set(metrics.__all__) == {
        "ExactMatchMetric",
        "NormalizedMatchMetric",
        "JsonSchemaValidationMetric",
        "exact_match",
        "normalized_match",
        "json_schema_validation",
    }
    assert set(execution.__all__) == {"EvaluationOrchestrator"}
    assert set(storage.__all__) == {"LocalRunStore"}

    subclasses = {
        ConfigurationError: EvalforgeError,
        MissingExtraError: EvalforgeError,
        DatasetError: EvalforgeError,
        EmptyDatasetError: DatasetError,
        DuplicateCaseIdError: DatasetError,
        AdapterError: EvalforgeError,
        MetricError: EvalforgeError,
        ExecutionError: EvalforgeError,
        MemoryLimitExceededError: ExecutionError,
        StorageError: EvalforgeError,
        ImmutabilityError: StorageError,
    }
    for sub, parent in subclasses.items():
        assert issubclass(sub, parent)
        assert issubclass(sub, EvalforgeError)


def test_public_entrypoint_signatures_remain_pinned() -> None:
    assert _param_spec(datasets.DatasetEngine.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("source", "POSITIONAL_OR_KEYWORD"),
        ("dataset_id", "KEYWORD_ONLY"),
        ("dataset_version", "KEYWORD_ONLY"),
    ]
    assert _param_spec(datasets.DatasetEngine.iter_cases) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("max_cases", "KEYWORD_ONLY"),
        ("on_complete", "KEYWORD_ONLY"),
    ]
    assert _param_spec(datasets.DatasetEngine.fingerprint) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("max_cases", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.CallableAdapter.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("fn", "POSITIONAL_OR_KEYWORD"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config", "KEYWORD_ONLY"),
        ("pass_case", "KEYWORD_ONLY"),
        ("input_mapper", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.ExactMatchMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.NormalizedMatchMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("case_sensitive", "KEYWORD_ONLY"),
        ("strip_punctuation", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.JsonSchemaValidationMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("schema", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(execution.EvaluationOrchestrator.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("config", "KEYWORD_ONLY"),
        ("storage_root", "KEYWORD_ONLY"),
    ]
    assert _param_spec(execution.EvaluationOrchestrator.arun) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("dataset", "POSITIONAL_OR_KEYWORD"),
        ("adapter", "POSITIONAL_OR_KEYWORD"),
        ("metrics", "POSITIONAL_OR_KEYWORD"),
        ("run_id", "KEYWORD_ONLY"),
    ]
    assert _param_spec(execution.EvaluationOrchestrator.run) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("dataset", "POSITIONAL_OR_KEYWORD"),
        ("adapter", "POSITIONAL_OR_KEYWORD"),
        ("metrics", "POSITIONAL_OR_KEYWORD"),
        ("run_id", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.LocalRunStore.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("root", "POSITIONAL_OR_KEYWORD"),
    ]
