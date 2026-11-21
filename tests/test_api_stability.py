"""Contract tests pinning public __all__ exports, exceptions, and entrypoint signatures."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import evalforge_maestro
from evalforge_maestro import (
    adapters,
    datasets,
    execution,
    judges,
    metrics,
    regression,
    reporting,
    service,
    storage,
)
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
    AgentExtractorConfig,
    AgentTraceStep,
    BaselineCommandPayload,
    BaselineEntry,
    BaselineRegistry,
    CalibrationDisagreement,
    CalibrationGateSummary,
    CalibrationReport,
    CLIErrorPayload,
    CLIResolvedConfig,
    ConfigValidationPayload,
    DecoupledEvidenceDiagnostic,
    EmbeddingConfig,
    ExpectedContextItem,
    ExpectedToolCall,
    HumanCalibrationSample,
    JudgeConfig,
    JudgeResponse,
    MetricComparison,
    OtelExtractorConfig,
    QualityGatePolicy,
    QualityGateResult,
    RAGExtractorConfig,
    ReportDiagnosticsSummary,
    ReportDocument,
    ResolvedEmbeddingSettings,
    RunCohortSummary,
    RunComparisonReport,
    StatisticalSummary,
    ToolCallRecord,
    TrendReport,
)


def _param_spec(fn: Callable[..., Any]) -> list[tuple[str, str]]:
    sig = inspect.signature(fn)
    return [(name, p.kind.name) for name, p in sig.parameters.items()]


def test_public_all_exports_and_exception_hierarchy() -> None:
    expected_top_all = {
        "SCHEMA_VERSION",
        "AdapterError",
        "AgentAdapter",
        "AgentExtractorConfig",
        "AgentTraceStep",
        "AggregateMetricSummary",
        "AnomalyFlag",
        "AnomalyScope",
        "AnomalySeverity",
        "AnomalyType",
        "AnswerCorrectnessMetric",
        "AnswerRelevanceMetric",
        "ArgumentCorrectnessMetric",
        "AsyncBatchMetric",
        "BaseJudgeMetric",
        "BaselineCommandPayload",
        "BaselineEntry",
        "BaselineRegistry",
        "CLIErrorPayload",
        "CLIResolvedConfig",
        "CalibrationDisagreement",
        "CalibrationDisagreementType",
        "CalibrationGateSummary",
        "CalibrationReport",
        "CallableAdapter",
        "CaseComparison",
        "CaseCriteria",
        "CaseEvaluationRecord",
        "CaseMetadata",
        "CaseMetricDelta",
        "CaseQueryFilter",
        "CaseQueryPayload",
        "CaseSplit",
        "ComparisonDirection",
        "ConfigSettingProvenance",
        "ConfigSourceTier",
        "ConfigValidationPayload",
        "ConfigurationError",
        "ContextEmbeddingSimilarityMetric",
        "ContextRelevanceMetric",
        "CustomRubricJudgeMetric",
        "DatasetEngine",
        "DatasetError",
        "DatasetStreamResult",
        "DecoupledEvidenceDiagnostic",
        "DocpipeAdapter",
        "DriftCategory",
        "DriftWarning",
        "DuplicateCaseIdError",
        "EmbeddingAggregation",
        "EmbeddingConfig",
        "EmbeddingSimilarityMetric",
        "EmptyDatasetError",
        "EvalforgeError",
        "EvaluationCase",
        "EvaluationOrchestrator",
        "EvidenceDecouplingCategory",
        "ExactMatchMetric",
        "ExecutionError",
        "ExecutionResult",
        "ExecutionSequenceMetric",
        "ExpectedContextItem",
        "ExpectedToolCall",
        "FailureRecoveryMetric",
        "GateDecision",
        "GateRuleCheck",
        "GroundednessMetric",
        "HitRateAtKMetric",
        "HumanCalibrationSample",
        "ImmutabilityError",
        "IndexedCaseMetricRow",
        "IndexedMetricPoint",
        "IndexedRunSummary",
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
        "MetricSpecConfig",
        "MetricStatus",
        "MetricTrendSummary",
        "MissingExtraError",
        "NDCGAtKMetric",
        "NormalizedMatchMetric",
        "OrchestratorConfig",
        "OtelExtractorConfig",
        "OtelTimestampUnit",
        "PolicyComplianceMetric",
        "PrecisionAtKMetric",
        "QualityGate",
        "QualityGatePolicy",
        "QualityGateResult",
        "RAGAdapter",
        "RAGExtractorConfig",
        "RecallAtKMetric",
        "ReplayAdapter",
        "ReportDiagnosticsSummary",
        "ReportDocument",
        "ReportKind",
        "ResolvedEmbeddingSettings",
        "ResolvedJudgeSettings",
        "ResolvedLoggingConfig",
        "ResolvedSecurityConfig",
        "ResolvedTargetConfig",
        "RetrievedChunk",
        "RunCohortSummary",
        "RunComparisonReport",
        "RunManifestEntry",
        "RunQueryFilter",
        "RunQueryPayload",
        "RunRecord",
        "RunSortOrder",
        "SQLiteIndexStatus",
        "SQLiteRunIndex",
        "ServiceApplication",
        "ServiceCompareRequest",
        "ServiceCompareResponse",
        "ServiceConfig",
        "ServiceErrorResponse",
        "ServiceEvaluateRequest",
        "ServiceEvaluateResponse",
        "ServiceHealthResponse",
        "ServiceOtelIngestRequest",
        "ServiceOtelIngestResponse",
        "ServiceReportRequest",
        "ServiceReportResponse",
        "SignificanceStatus",
        "StatisticalMethod",
        "StatisticalSummary",
        "StorageError",
        "TargetAdapter",
        "TargetChangeSummary",
        "TargetType",
        "TokenUsage",
        "ToolCallRecord",
        "ToolCallStatus",
        "ToolEfficiencyMetric",
        "ToolSelectionMetric",
        "TraceStepKind",
        "TrendDataPoint",
        "TrendDirection",
        "TrendReport",
        "__version__",
        "acalibrate_judge",
        "analyze_trend",
        "answer_correctness",
        "answer_relevance",
        "argument_correctness",
        "build_calibration_report",
        "build_comparison_report",
        "build_pooled_cohort_run",
        "build_run_report",
        "build_trend_report",
        "calibrate_judge",
        "compare_run_cohorts",
        "compare_runs",
        "context_relevance",
        "custom_rubric_judge",
        "detect_anomalies",
        "detect_cohort_drift",
        "detect_decoupled_evidence",
        "detect_drift",
        "detect_pii_categories",
        "exact_match",
        "execution_sequence",
        "failure_recovery",
        "groundedness",
        "hit_rate_at_k",
        "ingest_otel_spans",
        "json_schema_validation",
        "load_docpipe_fixture",
        "load_otel_executions",
        "mrr",
        "ndcg_at_k",
        "normalize_agent_trace",
        "normalize_tool_calls",
        "normalized_match",
        "policy_compliance",
        "precision_at_k",
        "recall_at_k",
        "render_markdown",
        "render_report_json",
        "tool_efficiency",
        "tool_selection",
        "validate_pii_egress",
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
        "build_pooled_cohort_run",
        "compare_run_cohorts",
        "compare_runs",
        "detect_anomalies",
        "detect_cohort_drift",
        "detect_drift",
    }
    assert set(datasets.__all__) == {"DatasetEngine", "DatasetStreamResult", "load_docpipe_fixture"}
    assert set(adapters.__all__) == {
        "AgentAdapter",
        "CallableAdapter",
        "DocpipeAdapter",
        "RAGAdapter",
        "ReplayAdapter",
        "ingest_otel_spans",
        "load_otel_executions",
        "normalize_agent_trace",
        "normalize_tool_calls",
    }
    assert set(reporting.__all__) == {
        "build_calibration_report",
        "build_comparison_report",
        "build_run_report",
        "build_trend_report",
        "detect_decoupled_evidence",
        "render_markdown",
        "render_report_json",
    }
    assert set(metrics.__all__) == {
        "ArgumentCorrectnessMetric",
        "ExactMatchMetric",
        "ExecutionSequenceMetric",
        "FailureRecoveryMetric",
        "HitRateAtKMetric",
        "JsonSchemaValidationMetric",
        "MRRMetric",
        "NDCGAtKMetric",
        "NormalizedMatchMetric",
        "PolicyComplianceMetric",
        "PrecisionAtKMetric",
        "RecallAtKMetric",
        "ToolEfficiencyMetric",
        "ToolSelectionMetric",
        "argument_correctness",
        "exact_match",
        "execution_sequence",
        "failure_recovery",
        "hit_rate_at_k",
        "json_schema_validation",
        "mrr",
        "ndcg_at_k",
        "normalized_match",
        "policy_compliance",
        "precision_at_k",
        "recall_at_k",
        "tool_efficiency",
        "tool_selection",
    }
    assert set(execution.__all__) == {"EvaluationOrchestrator"}
    assert set(storage.__all__) == {"LocalRunStore", "SQLiteRunIndex"}

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
    assert _param_spec(regression.QualityGate.evaluate_cohort) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("runs", "POSITIONAL_OR_KEYWORD"),
        ("comparison", "KEYWORD_ONLY"),
        ("trend", "KEYWORD_ONLY"),
    ]
    assert _param_spec(regression.build_pooled_cohort_run) == [
        ("runs", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(regression.compare_run_cohorts) == [
        ("baseline_runs", "POSITIONAL_OR_KEYWORD"),
        ("candidate_runs", "POSITIONAL_OR_KEYWORD"),
        ("baseline_name", "KEYWORD_ONLY"),
        ("policy", "KEYWORD_ONLY"),
    ]
    assert _param_spec(regression.detect_cohort_drift) == [
        ("baseline_runs", "POSITIONAL_OR_KEYWORD"),
        ("candidate_runs", "POSITIONAL_OR_KEYWORD"),
    ]
    for emb_cls in (
        evalforge_maestro.EmbeddingSimilarityMetric,
        evalforge_maestro.ContextEmbeddingSimilarityMetric,
    ):
        assert _param_spec(emb_cls.__init__) == [
            ("self", "POSITIONAL_OR_KEYWORD"),
            ("config", "KEYWORD_ONLY"),
            ("api_key", "KEYWORD_ONLY"),
            ("embed_fn", "KEYWORD_ONLY"),
        ]
    assert set(EmbeddingConfig.model_fields) >= {
        "schema_version",
        "model",
        "api_base",
        "pass_threshold",
        "aggregation",
        "max_input_chars",
        "local_only",
        "mock_mode",
    }
    assert set(ResolvedEmbeddingSettings.model_fields) >= {
        "model",
        "api_base",
        "api_key_configured",
        "pass_threshold",
        "aggregation",
        "max_input_chars",
        "mock_mode",
        "local_only",
    }
    assert set(StatisticalSummary.model_fields) >= {
        "method",
        "confidence_level",
        "sample_size",
        "mean_delta",
        "ci_low",
        "ci_high",
        "p_value",
        "significance",
        "statistically_significant",
    }
    assert set(RunCohortSummary.model_fields) >= {
        "baseline_run_ids",
        "candidate_run_ids",
        "baseline_run_count",
        "candidate_run_count",
    }
    assert set(MetricComparison.model_fields) >= {"statistics", "case_statistics"}
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
        "cohort",
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
        "confidence_level",
        "min_statistical_samples",
        "fail_on_significant_regression",
    }
    assert set(QualityGateResult.model_fields) >= {
        "schema_version",
        "decision",
        "passed",
        "blocking",
        "checks",
        "drift_warnings",
        "anomalies",
        "cohort",
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
    assert _param_spec(evalforge_maestro.detect_pii_categories) == [
        ("value", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(evalforge_maestro.validate_pii_egress) == [
        ("value", "POSITIONAL_OR_KEYWORD"),
        ("enabled", "KEYWORD_ONLY"),
        ("context_label", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.ReplayAdapter.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("executions", "POSITIONAL_OR_KEYWORD"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config_fingerprint", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.ReplayAdapter.from_file) == [
        ("path", "POSITIONAL_OR_KEYWORD"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config_fingerprint", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.ReplayAdapter.from_otel_file) == [
        ("path", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
        ("dataset", "KEYWORD_ONLY"),
        ("case_id_map", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config_fingerprint", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.ingest_otel_spans) == [
        ("payload", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
        ("dataset", "KEYWORD_ONLY"),
        ("case_id_map", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.load_otel_executions) == [
        ("path", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
        ("dataset", "KEYWORD_ONLY"),
        ("case_id_map", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.detect_decoupled_evidence) == [
        ("run", "POSITIONAL_OR_KEYWORD"),
    ]
    assert _param_spec(reporting.build_run_report) == [
        ("run", "POSITIONAL_OR_KEYWORD"),
        ("comparison", "KEYWORD_ONLY"),
        ("trend", "KEYWORD_ONLY"),
        ("gate", "KEYWORD_ONLY"),
        ("title", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.build_comparison_report) == [
        ("comparison", "POSITIONAL_OR_KEYWORD"),
        ("candidate_run", "KEYWORD_ONLY"),
        ("gate", "KEYWORD_ONLY"),
        ("title", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.build_trend_report) == [
        ("trend", "POSITIONAL_OR_KEYWORD"),
        ("gate", "KEYWORD_ONLY"),
        ("title", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.build_calibration_report) == [
        ("calibration", "POSITIONAL_OR_KEYWORD"),
        ("min_agreement", "KEYWORD_ONLY"),
        ("strict", "KEYWORD_ONLY"),
        ("title", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.render_report_json) == [
        ("document", "POSITIONAL_OR_KEYWORD"),
        ("pretty", "KEYWORD_ONLY"),
    ]
    assert _param_spec(reporting.render_markdown) == [
        ("document", "POSITIONAL_OR_KEYWORD"),
    ]
    assert set(CLIResolvedConfig.model_fields) >= {
        "schema_version",
        "config_path",
        "env_file_path",
        "storage_dir",
        "dataset",
        "dataset_id",
        "dataset_version",
        "executions_path",
        "otel_traces",
        "otel",
        "run_id",
        "repeats",
        "baseline",
        "baseline_runs",
        "trend_window",
        "strict",
        "target",
        "metrics",
        "execution",
        "judge",
        "embedding",
        "security",
        "gate",
        "logging",
        "provenance",
    }
    assert set(DecoupledEvidenceDiagnostic.model_fields) >= {
        "case_id",
        "mandatory",
        "category",
        "passed_metrics",
        "failed_metrics",
        "retrieved_chunk_ids",
        "explanation",
    }
    assert set(ReportDiagnosticsSummary.model_fields) >= {
        "mandatory_failed_case_ids",
        "decoupled_evidence_cases",
        "anomaly_highlights",
        "drift_highlights",
    }
    assert set(CalibrationGateSummary.model_fields) >= {
        "min_agreement",
        "observed_agreement",
        "strict",
        "valid_cases",
        "inconclusive_cases",
        "passed",
        "reason",
    }
    assert set(ReportDocument.model_fields) >= {
        "schema_version",
        "report_kind",
        "title",
        "generated_at",
        "evaluation",
        "comparison",
        "trend",
        "calibration",
        "gate",
        "calibration_gate",
        "diagnostics",
        "cohort_run_ids",
        "cohort_aggregates",
    }
    assert set(BaselineCommandPayload.model_fields) >= {
        "schema_version",
        "action",
        "entry",
        "baselines",
    }
    assert set(ConfigValidationPayload.model_fields) >= {
        "schema_version",
        "valid",
        "config_path",
        "env_file_path",
        "warnings",
    }
    assert set(CLIErrorPayload.model_fields) >= {
        "schema_version",
        "exit_code",
        "error_type",
        "message",
        "hint",
    }
    assert _param_spec(adapters.AgentAdapter.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("fn", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("config", "KEYWORD_ONLY"),
        ("pass_case", "KEYWORD_ONLY"),
        ("input_mapper", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.normalize_agent_trace) == [
        ("raw", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
    ]
    assert _param_spec(adapters.normalize_tool_calls) == [
        ("raw", "POSITIONAL_OR_KEYWORD"),
        ("extractors", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.ToolSelectionMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("mode", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.ArgumentCorrectnessMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("strict_mode", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.ExecutionSequenceMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("mode", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.ToolEfficiencyMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("default_max_steps", "KEYWORD_ONLY"),
        ("default_max_tool_calls", "KEYWORD_ONLY"),
        ("allow_redundant_failures", "KEYWORD_ONLY"),
        ("loop_penalty", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.PolicyComplianceMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("forbidden_tools", "KEYWORD_ONLY"),
        ("forbidden_argument_patterns", "KEYWORD_ONLY"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert _param_spec(metrics.FailureRecoveryMetric.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("threshold", "KEYWORD_ONLY"),
    ]
    assert set(ExpectedToolCall.model_fields) >= {
        "name",
        "arguments",
        "arguments_schema",
        "argument_match_mode",
        "optional",
        "order",
    }
    assert set(ToolCallRecord.model_fields) >= {
        "id",
        "name",
        "arguments",
        "raw_arguments",
        "argument_parse_error",
        "result",
        "status",
        "error",
        "step_index",
        "elapsed_seconds",
        "metadata",
    }
    assert set(AgentTraceStep.model_fields) >= {
        "step_index",
        "kind",
        "name",
        "content",
        "tool_calls",
        "tool_call_id",
        "status",
        "error",
        "elapsed_seconds",
        "tokens",
        "metadata",
    }
    assert set(AgentExtractorConfig.model_fields) >= {
        "output",
        "tool_calls",
        "trace",
        "tokens",
        "errors",
    }
    assert set(OtelExtractorConfig.model_fields) >= {
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
        "timestamp_unit",
        "match_dataset_by_input",
    }
    assert _param_spec(storage.SQLiteRunIndex.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("store", "POSITIONAL_OR_KEYWORD"),
        ("db_path", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.SQLiteRunIndex.rebuild) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("force", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.SQLiteRunIndex.query_runs) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("filters", "POSITIONAL_OR_KEYWORD"),
        ("auto_sync", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.SQLiteRunIndex.query_cases) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("filters", "POSITIONAL_OR_KEYWORD"),
        ("auto_sync", "KEYWORD_ONLY"),
    ]
    assert _param_spec(storage.SQLiteRunIndex.metric_history) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("metric_id", "POSITIONAL_OR_KEYWORD"),
        ("dataset_id", "KEYWORD_ONLY"),
        ("model_id", "KEYWORD_ONLY"),
        ("system_version", "KEYWORD_ONLY"),
        ("limit", "KEYWORD_ONLY"),
        ("auto_sync", "KEYWORD_ONLY"),
    ]


def test_m10_service_api_stability() -> None:
    from evalforge_maestro.types import (
        ServiceCompareRequest,
        ServiceCompareResponse,
        ServiceConfig,
        ServiceErrorResponse,
        ServiceEvaluateRequest,
        ServiceEvaluateResponse,
        ServiceHealthResponse,
        ServiceOtelIngestRequest,
        ServiceOtelIngestResponse,
        ServiceReportRequest,
        ServiceReportResponse,
    )

    assert set(service.__all__) == {
        "ServiceApplication",
        "create_http_server",
        "serve_http",
        "validate_service_bind_policy",
    }
    assert evalforge_maestro.ServiceApplication is service.ServiceApplication
    try:
        evalforge_maestro.__getattr__("__nonexistent_symbol__")
    except AttributeError:
        pass
    else:  # pragma: no cover - assertion safeguard
        raise AssertionError("Expected AttributeError for unknown top-level symbol")
    assert _param_spec(service.validate_service_bind_policy) == [
        ("config", "POSITIONAL_OR_KEYWORD"),
        ("auth_token", "KEYWORD_ONLY"),
    ]
    assert _param_spec(service.ServiceApplication.__init__) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("config", "POSITIONAL_OR_KEYWORD"),
        ("auth_token", "KEYWORD_ONLY"),
        ("judge_api_key", "KEYWORD_ONLY"),
        ("embedding_api_key", "KEYWORD_ONLY"),
    ]
    assert _param_spec(service.ServiceApplication.handle_request) == [
        ("self", "POSITIONAL_OR_KEYWORD"),
        ("method", "POSITIONAL_OR_KEYWORD"),
        ("raw_path", "POSITIONAL_OR_KEYWORD"),
        ("body", "KEYWORD_ONLY"),
        ("headers", "KEYWORD_ONLY"),
    ]
    assert _param_spec(service.create_http_server) == [
        ("config", "POSITIONAL_OR_KEYWORD"),
        ("auth_token", "KEYWORD_ONLY"),
        ("judge_api_key", "KEYWORD_ONLY"),
        ("embedding_api_key", "KEYWORD_ONLY"),
    ]
    assert _param_spec(service.serve_http) == [
        ("config", "POSITIONAL_OR_KEYWORD"),
        ("auth_token", "KEYWORD_ONLY"),
        ("judge_api_key", "KEYWORD_ONLY"),
        ("embedding_api_key", "KEYWORD_ONLY"),
    ]

    assert set(ServiceConfig.model_fields) >= {
        "host",
        "port",
        "storage_dir",
        "local_only",
        "block_pii",
        "mock_mode",
        "max_request_bytes",
        "auth_token_configured",
    }
    assert set(ServiceHealthResponse.model_fields) >= {
        "schema_version",
        "status",
        "package_version",
        "storage_dir",
        "local_only",
        "mock_mode",
        "indexed_run_count",
        "canonical_run_count",
    }
    assert set(ServiceErrorResponse.model_fields) >= {
        "schema_version",
        "status_code",
        "error_type",
        "message",
        "hint",
    }
    assert set(ServiceOtelIngestRequest.model_fields) >= {
        "payload",
        "extractors",
        "dataset",
        "case_id_map",
        "system_version",
        "model_id",
    }
    assert set(ServiceOtelIngestResponse.model_fields) >= {
        "schema_version",
        "count",
        "executions",
    }
    assert set(ServiceEvaluateRequest.model_fields) >= {
        "cases",
        "executions",
        "otel_payload",
        "otel_extractors",
        "case_id_map",
        "dataset_id",
        "dataset_version",
        "metrics",
        "judge",
        "embedding",
        "gate",
        "max_context_chars",
        "max_concurrency",
        "seed",
        "system_version",
        "model_id",
        "run_id",
        "persist",
        "include_markdown",
    }
    assert set(ServiceEvaluateResponse.model_fields) >= {
        "schema_version",
        "persisted",
        "evaluation",
        "gate",
        "report",
        "markdown",
    }
    assert set(ServiceCompareRequest.model_fields) >= {
        "candidate_run_id",
        "candidate_run_ids",
        "baseline_ref",
        "baseline_run_ids",
        "policy",
        "include_markdown",
    }
    assert set(ServiceCompareResponse.model_fields) >= {
        "schema_version",
        "comparison",
        "gate",
        "report",
        "markdown",
    }
    assert set(ServiceReportRequest.model_fields) >= {
        "run_id",
        "compare_run_id",
        "baseline_ref",
        "trend_window",
        "dataset_id",
        "model_id",
        "title",
        "include_markdown",
    }
    assert set(ServiceReportResponse.model_fields) >= {
        "schema_version",
        "report",
        "markdown",
    }
