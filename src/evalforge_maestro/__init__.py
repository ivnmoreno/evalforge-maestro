"""EvalForge Maestro: independent LLM evaluation and regression verification engine."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from evalforge_maestro.adapters import CallableAdapter, DocpipeAdapter, RAGAdapter
from evalforge_maestro.datasets import DatasetEngine, DatasetStreamResult, load_docpipe_fixture
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
    HitRateAtKMetric,
    JsonSchemaValidationMetric,
    MRRMetric,
    NDCGAtKMetric,
    NormalizedMatchMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
    exact_match,
    hit_rate_at_k,
    json_schema_validation,
    mrr,
    ndcg_at_k,
    normalized_match,
    precision_at_k,
    recall_at_k,
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
    ExpectedContextItem,
    Metric,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    RAGExtractorConfig,
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
]
