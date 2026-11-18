"""Contract tests pinning public __all__ exports, exceptions, and entrypoint signatures."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import evalforge_maestro
from evalforge_maestro import adapters, datasets, execution, judges, metrics, regression, storage
from evalforge_maestro.exceptions import (
    AdapterError,
    ConfigurationError,
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
    EvalforgeError,
    ExecutionError,
    ImmutabilityError,
    JudgeError,
    LocalOnlyPolicyError,
    MemoryLimitExceededError,
    MetricError,
    MissingExtraError,
    StorageError,
)
from evalforge_maestro.types import (
    BaselineEntry,
    BaselineRegistry,
    CalibrationDisagreement,
    CalibrationReport,
    ExpectedContextItem,
    HumanCalibrationSample,
    JudgeConfig,
    JudgeResponse,
    QualityGatePolicy,
    QualityGateResult,
    RAGExtractorConfig,
    RunComparisonReport,
    TrendReport,
)


def _param_spec(fn: Callable[..., Any]) -> list[tuple[str, str]]:
    sig = inspect.signature(fn)
    return [(name, p.kind.name) for name, p in sig.parameters.items()]


def test_public_all_exports_and_exception_hierarchy() -> None:
    expected_top_all = {
        "SCHEMA_VERSION",
        "AdapterError",
        "AggregateMetricSummary",
        "AnomalyFlag",
        "AnomalyScope",
        "AnomalySeverity",
        "AnomalyType",
        "AnswerCorrectnessMetric",
        "AnswerRelevanceMetric",
        "AsyncBatchMetric",
        "BaseJudgeMetric",
        "BaselineEntry",
        "BaselineRegistry",
        "CalibrationDisagreement",
        "CalibrationDisagreementType",
        "CalibrationReport",
        "CallableAdapter",
        "CaseComparison",
        "CaseCriteria",
        "CaseEvaluationRecord",
        "CaseMetadata",
        "CaseMetricDelta",
        "CaseSplit",
        "ComparisonDirection",
        "ConfigurationError",
        "ContextRelevanceMetric",
        "CustomRubricJudgeMetric",
        "DatasetEngine",
        "DatasetError",
        "DatasetStreamResult",
        "DocpipeAdapter",
        "DriftCategory",
        "DriftWarning",
        "DuplicateCaseIdError",
        "EmptyDatasetError",
        "EvalforgeError",
        "EvaluationCase",
        "EvaluationOrchestrator",
        "ExactMatchMetric",
        "ExecutionError",
        "ExecutionResult",
        "ExpectedContextItem",
        "GateDecision",
        "GateRuleCheck",
        "GroundednessMetric",
        "HitRateAtKMetric",
        "HumanCalibrationSample",
        "ImmutabilityError",
        "JsonSchemaValidationMetric",
        "JudgeConfig",
        "JudgeError",
        "JudgeResponse",
        "LocalOnlyPolicyError",
        "LocalRunStore",
        "MRRMetric",
        "MemoryLimitExceededError",
        "Metric",
        "MetricComparison",
        "MetricError",
        "MetricMetadata",
        "MetricResult",
        "MetricStatus",
        "MetricTrendSummary",
        "MissingExtraError",
        "NDCGAtKMetric",
        "NormalizedMatchMetric",
        "OrchestratorConfig",
        "PrecisionAtKMetric",
        "QualityGate",
        "QualityGatePolicy",
        "QualityGateResult",
        "RAGAdapter",
        "RAGExtractorConfig",
        "RecallAtKMetric",
        "RetrievedChunk",
        "RunComparisonReport",
        "RunManifestEntry",
        "RunRecord",
        "StorageError",
        "TargetAdapter",
        "TargetChangeSummary",
        "TokenUsage",
        "TrendDataPoint",
        "TrendDirection",
        "TrendReport",
        "__version__",
        "acalibrate_judge",
        "analyze_trend",
        "answer_correctness",
        "answer_relevance",
        "calibrate_judge",
        "compare_runs",
        "context_relevance",
        "custom_rubric_judge",
        "detect_anomalies",
        "detect_drift",
        "exact_match",
        "groundedness",
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
    assert set(judges.__all__) == {
        "AnswerCorrectnessMetric",
        "AnswerRelevanceMetric",
        "BaseJudgeMetric",
        "ContextRelevanceMetric",
        "CustomRubricJudgeMetric",
        "GroundednessMetric",
        "acalibrate_judge",
        "answer_correctness",
        "answer_relevance",
        "calibrate_judge",
        "context_relevance",
        "custom_rubric_judge",
        "groundedness",
    }
    assert set(regression.__all__) == {
        "QualityGate",
        "analyze_trend",
        "compare_runs",
        "detect_anomalies",
        "detect_drift",
    }
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
        JudgeError: EvalforgeError,
        LocalOnlyPolicyError: EvalforgeError,
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
    assert _param_spec(storage.LocalRunStore.pin_baseline) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("run_id", "POSITIONAL_OR_KEYWORD"),
        ("name", "KEYWORD_ONLY"),
        ("note", "KEYWORD_ONLY"),
        ("tags", "KEYWORD_ONLY"),
        ("overwrite", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.LocalRunStore.get_baseline) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("name", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(storage.LocalRunStore.list_baselines) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(storage.LocalRunStore.unpin_baseline) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("name", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(storage.LocalRunStore.load_baseline_run) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("name", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(storage.LocalRunStore.load_runs) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("run_ids", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(regression.detect_drift) == [
        ("baseline", "POSITIONAL_OR_KEYWORD"),
        ("candidate", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(regression.detect_anomalies) == [
        ("run", "POSITIONAL_OR_KEYWORD"),
        ("comparison", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
    ]
    assert _param_spec(regression.compare_runs) == [
        ("baseline", "POSITIONAL_OR_KEYWORD"),
        ("candidate", "POSITIONAL_OR_KEYWORD"),
        ("baseline_name", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
    ]
    assert _param_spec(regression.analyze_trend) == [
        ("runs", "POSITIONAL_OR_KEYWORD"),
        ("window", "KEYWORD_ONLY"),
        ("dataset_id", "KEYWORD_ONLY"),
        ("all_datasets", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("metric_ids", "KEYWORD_ONLY"),
        ("slope_threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(regression.QualityGate.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("policy", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(regression.QualityGate.evaluate) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("run", "POSITIONAL_OR_KEYWORD"),
        ("comparison", "KEYWORD_ONLY"),
        ("trend", "KEYWORD_ONLY"),
    ]
    assert set(BaselineEntry.model_fields) >= {
        "schema_version",
        "name",
        "run_id",
        "pinned_at",
        "dataset_fingerprint",
        "judge_config_fingerprint",
    }
    assert list(BaselineRegistry.model_fields) == ["schema_version", "baselines"]
    assert set(RunComparisonReport.model_fields) >= {
        "schema_version",
        "baseline_run_id",
        "candidate_run_id",
        "target_changes",
        "metric_comparisons",
        "case_comparisons",
        "drift_warnings",
        "anomalies",
    }
    assert set(TrendReport.model_fields) >= {
        "schema_version",
        "window",
        "dataset_id_filter",
        "inspected_run_ids",
        "metrics",
        "drift_warnings",
    }
    assert set(QualityGatePolicy.model_fields) >= {
        "max_regression_drop",
        "disagreement_threshold",
        "case_drop_warning_threshold",
        "trend_slope_threshold",
        "max_inconclusive_rate",
    }
    assert set(QualityGateResult.model_fields) >= {
        "schema_version",
        "decision",
        "passed",
        "blocking",
        "checks",
        "drift_warnings",
        "anomalies",
    }
    for judge_cls in (
        judges.GroundednessMetric,
        judges.AnswerRelevanceMetric,
        judges.ContextRelevanceMetric,
        judges.AnswerCorrectnessMetric,
    ):
        assert _param_spec(judge_cls.__init__) == [
            ("self", "POSITIONAL_OR_KEYWORD"),
            ("config", "KEYWORD_ONLY"),
            ("api_key", "KEYWORD_ONLY"),
            ("mock_responses", "KEYWORD_ONLY"),
            ("completion_fn", "KEYWORD_ONLY"),
        ]
    for judge_factory in (
        judges.groundedness,
        judges.answer_relevance,
        judges.context_relevance,
        judges.answer_correctness,
    ):
        assert _param_spec(judge_factory) == [
            ("config", "KEYWORD_ONLY"),
            ("api_key", "KEYWORD_ONLY"),
            ("mock_responses", "KEYWORD_ONLY"),
            ("completion_fn", "KEYWORD_ONLY"),
        ]
    assert _param_spec(judges.CustomRubricJudgeMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("rubric", "POSITIONAL_OR_KEYWORD"),
        ("metric_id", "KEYWORD_ONLY"),
        ("metric_version", "KEYWORD_ONLY"),
        ("what_it_measures", "KEYWORD_ONLY"),
        ("require_reference", "KEYWORD_ONLY"),
        ("require_context", "KEYWORD_ONLY"),
        ("config", "KEYWORD_ONLY"),
        ("api_key", "KEYWORD_ONLY"),
        ("mock_responses", "KEYWORD_ONLY"),
        ("completion_fn", "KEYWORD_ONLY"),
    ]
    assert _param_spec(judges.custom_rubric_judge) == [
        ("rubric", "POSITIONAL_OR_KEYWORD"),
        ("metric_id", "KEYWORD_ONLY"),
        ("metric_version", "KEYWORD_ONLY"),
        ("what_it_measures", "KEYWORD_ONLY"),
        ("require_reference", "KEYWORD_ONLY"),
        ("require_context", "KEYWORD_ONLY"),
        ("config", "KEYWORD_ONLY"),
        ("api_key", "KEYWORD_ONLY"),
        ("mock_responses", "KEYWORD_ONLY"),
        ("completion_fn", "KEYWORD_ONLY"),
    ]
    for cal_fn in (judges.calibrate_judge, judges.acalibrate_judge):
        assert _param_spec(cal_fn) == [
            ("judge", "POSITIONAL_OR_KEYWORD"),
            ("samples", "POSITIONAL_OR_KEYWORD"),
            ("human_threshold", "KEYWORD_ONLY"),
            ("score_divergence_threshold", "KEYWORD_ONLY"),
            ("max_concurrency", "KEYWORD_ONLY"),
        ]
    assert set(JudgeConfig.model_fields) >= {
        "schema_version",
        "model",
        "api_base",
        "temperature",
        "pass_threshold",
        "max_retries",
        "retry_backoff_seconds",
        "timeout_seconds",
        "local_only",
        "mock_mode",
        "seed",
        "prompt_version",
        "extra_params",
    }
    assert set(JudgeResponse.model_fields) >= {
        "score",
        "rationale",
        "verdict",
        "supported_claims",
        "unsupported_claims",
    }
    assert set(HumanCalibrationSample.model_fields) >= {
        "schema_version",
        "case_id",
        "input",
        "output",
        "reference",
        "retrieved_chunks",
        "human_score",
        "human_passed",
        "notes",
        "metadata",
    }
    assert set(CalibrationDisagreement.model_fields) >= {
        "case_id",
        "disagreement_type",
        "human_score",
        "human_passed",
        "judge_score",
        "judge_status",
        "judge_passed",
        "score_delta",
        "judge_rationale",
        "human_notes",
    }
    assert set(CalibrationReport.model_fields) >= {
        "schema_version",
        "metric_id",
        "metric_version",
        "judge_config",
        "judge_config_fingerprint",
        "total_cases",
        "valid_cases",
        "inconclusive_cases",
        "exact_agreement_rate",
        "too_generous_rate",
        "too_harsh_rate",
        "mean_human_score",
        "mean_judge_score",
        "mean_score_delta",
        "disagreements",
        "recommended_pass_threshold",
    }
