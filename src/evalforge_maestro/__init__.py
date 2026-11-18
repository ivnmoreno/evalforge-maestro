"""EvalForge Maestro: independent LLM evaluation and regression verification engine."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine, DatasetStreamResult
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
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import (
    ExactMatchMetric,
    JsonSchemaValidationMetric,
    NormalizedMatchMetric,
    exact_match,
    json_schema_validation,
    normalized_match,
)
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    SCHEMA_VERSION,
    AggregateMetricSummary,
    CaseCriteria,
    CaseEvaluationRecord,
    CaseMetadata,
    CaseSplit,
    EvaluationCase,
    ExecutionResult,
    Metric,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    RetrievedChunk,
    RunManifestEntry,
    RunRecord,
    TargetAdapter,
    TokenUsage,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    __version__ = version("evalforge-maestro")
except PackageNotFoundError:  # pragma: no cover - uninstalled source tree fallback
    __version__ = "0.1.0.dev0"

__all__ = [
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
]
