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
from evalforge_maestro.types import ExpectedContextItem, RAGExtractorConfig


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
        "DocpipeAdapter",
        "DuplicateCaseIdError",
        "EmptyDatasetError",
        "EvalforgeError",
        "EvaluationCase",
        "EvaluationOrchestrator",
        "ExactMatchMetric",
        "ExecutionError",
        "ExecutionResult",
        "ExpectedContextItem",
        "HitRateAtKMetric",
        "ImmutabilityError",
        "JsonSchemaValidationMetric",
        "LocalRunStore",
        "MRRMetric",
        "MemoryLimitExceededError",
        "Metric",
        "MetricError",
        "MetricMetadata",
        "MetricResult",
        "MetricStatus",
        "MissingExtraError",
        "NDCGAtKMetric",
        "NormalizedMatchMetric",
        "OrchestratorConfig",
        "PrecisionAtKMetric",
        "RAGAdapter",
        "RAGExtractorConfig",
        "RecallAtKMetric",
        "RetrievedChunk",
        "RunManifestEntry",
        "RunRecord",
        "StorageError",
        "TargetAdapter",
        "TokenUsage",
        "__version__",
        "exact_match",
        "hit_rate_at_k",
        "json_schema_validation",
        "load_docpipe_fixture",
        "mrr",
        "ndcg_at_k",
        "normalized_match",
        "precision_at_k",
        "recall_at_k",
    }
    assert set(evalforge_maestro.__all__) == expected_top_all
    assert set(datasets.__all__) == {"DatasetEngine", "DatasetStreamResult", "load_docpipe_fixture"}
    assert set(adapters.__all__) == {"CallableAdapter", "DocpipeAdapter", "RAGAdapter"}
    assert set(metrics.__all__) == {
        "ExactMatchMetric",
        "HitRateAtKMetric",
        "JsonSchemaValidationMetric",
        "MRRMetric",
        "NDCGAtKMetric",
        "NormalizedMatchMetric",
        "PrecisionAtKMetric",
        "RecallAtKMetric",
        "exact_match",
        "hit_rate_at_k",
        "json_schema_validation",
        "mrr",
        "ndcg_at_k",
        "normalized_match",
        "precision_at_k",
        "recall_at_k",
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
    assert _param_spec(datasets.load_docpipe_fixture) == [
        ("source", "POSITIONAL_OR_KEYWORD"),
        ("dataset_id", "KEYWORD_ONLY"),
        ("dataset_version", "KEYWORD_ONLY"),
    ]
    assert _param_spec(datasets.DatasetEngine.from_docpipe_fixture) == [
        ("source", "POSITIONAL_OR_KEYWORD"),
        ("dataset_id", "KEYWORD_ONLY"),
        ("dataset_version", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.RAGAdapter.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("fn", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config", "KEYWORD_ONLY"),
        ("pass_case", "KEYWORD_ONLY"),
        ("input_mapper", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.DocpipeAdapter.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("mode", "KEYWORD_ONLY"),
        ("collection", "KEYWORD_ONLY"),
        ("persist_dir", "KEYWORD_ONLY"),
        ("retrieve_kwargs", "KEYWORD_ONLY"),
        ("answer_kwargs", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("client", "KEYWORD_ONLY"),
    ]
    for k_metric_cls in (
        metrics.PrecisionAtKMetric,
        metrics.RecallAtKMetric,
        metrics.NDCGAtKMetric,
        metrics.HitRateAtKMetric,
    ):
        assert _param_spec(k_metric_cls.__init__) == [
            ("self", "POSITIONAL_OR_KEYWORD"),
            ("k", "POSITIONAL_OR_KEYWORD"),
            ("match_parent_id", "KEYWORD_ONLY"),
            ("threshold", "KEYWORD_ONLY"),
        ]
    assert _param_spec(metrics.MRRMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("match_parent_id", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert list(ExpectedContextItem.model_fields) == ["id", "text", "relevance"]
    assert list(RAGExtractorConfig.model_fields) == [
        "output",
        "chunks",
        "chunk_id",
        "chunk_text",
        "chunk_parent_id",
        "chunk_rank",
        "chunk_score",
        "chunk_metadata",
        "tokens",
    ]
