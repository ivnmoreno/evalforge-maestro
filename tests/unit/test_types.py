"""Unit tests for exception hierarchy, core contracts, and JSON Schema parity."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

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
from evalforge_maestro.types import (
    AggregateMetricSummary,
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    CaseCriteria,
    CaseEvaluationRecord,
    CaseMetadata,
    CaseSplit,
    ComparisonDirection,
    DriftCategory,
    DriftWarning,
    EvaluationCase,
    ExecutionResult,
    ExpectedContextItem,
    GateDecision,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    QualityGatePolicy,
    RAGExtractorConfig,
    RetrievedChunk,
    RunManifestEntry,
    RunRecord,
    TokenUsage,
    TrendDirection,
)


def test_exception_hierarchy_and_missing_extra_messages() -> None:
    assert issubclass(ConfigurationError, EvalforgeError)
    assert issubclass(MissingExtraError, EvalforgeError)
    assert issubclass(EmptyDatasetError, DatasetError)
    assert issubclass(DuplicateCaseIdError, DatasetError)
    assert issubclass(DatasetError, EvalforgeError)
    assert issubclass(AdapterError, EvalforgeError)
    assert issubclass(MetricError, EvalforgeError)
    assert issubclass(MemoryLimitExceededError, ExecutionError)
    assert issubclass(ExecutionError, EvalforgeError)
    assert issubclass(ImmutabilityError, StorageError)
    assert issubclass(StorageError, EvalforgeError)

    err_extra = MissingExtraError(extra="judges", package="litellm")
    assert "evalforge-maestro[judges]" in str(err_extra)
    assert err_extra.extra == "judges"
    assert err_extra.package == "litellm"

    err_plain = MissingExtraError()
    assert "not installed" in str(err_plain)

    ds_err = DatasetError("bad row", line_number=3, case_id="c3", field="input")
    assert ds_err.line_number == 3
    assert ds_err.case_id == "c3"
    assert ds_err.field == "input"


def test_evaluation_case_strict_validation() -> None:
    case = EvaluationCase(
        id="  case-1 ",
        input={"q": "hi"},
        reference="hello",
        metadata=CaseMetadata(tags=["smoke"], split=CaseSplit.EVAL, extra={"k": 1}),
        criteria=CaseCriteria(
            mandatory=True,
            json_schema={"type": "string"},
            pass_threshold=0.8,
            metric_thresholds={"exact_match": 1.0},
        ),
    )
    assert case.id == "case-1"
    assert case.schema_version == "1.0"

    with pytest.raises(ValidationError):
        EvaluationCase(id="   ", input="ok")

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({"id": "c1", "input": "ok", "unknown": 1})

    with pytest.raises(ValidationError):
        EvaluationCase(id="c1", input=float("nan"))

    with pytest.raises(ValidationError):
        CaseMetadata(tags=["   "])

    with pytest.raises(ValidationError):
        CaseCriteria(json_schema={"type": 123})

    with pytest.raises(ValidationError):
        CaseCriteria(pass_threshold=True)

    with pytest.raises(ValidationError):
        CaseCriteria(metric_thresholds={"": 0.5})


def test_execution_and_metric_result_constraints() -> None:
    res = ExecutionResult(
        case_id="c1",
        input="hi",
        output="ok",
        elapsed_seconds=0.05,
        tokens=TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        retrieved_chunks=[RetrievedChunk(id="ch1", text="ctx", rank=1, score=0.9)],
    )
    assert res.elapsed_seconds == 0.05

    with pytest.raises(ValidationError):
        ExecutionResult(case_id="c1", input="hi", elapsed_seconds=-0.1)

    with pytest.raises(ValidationError):
        ExecutionResult(case_id="c1", input="hi", elapsed_seconds=True)

    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=True)

    metric = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=0.1234567,
        status=MetricStatus.PASS,
        explanation="Matched.",
    )
    assert metric.score == 0.123457

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=float("nan"),
            status=MetricStatus.PASS,
            explanation="Invalid",
        )

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=None,
            status=MetricStatus.PASS,
            explanation="Missing score",
        )

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=0.5,
            status=MetricStatus.NOT_APPLICABLE,
            explanation="Unexpected score",
        )


def test_run_record_manifest_orchestrator_config_and_schema_parity() -> None:
    tz_plus2 = timezone(timedelta(hours=2))
    ts = datetime(2026, 11, 18, 12, 0, 0, tzinfo=tz_plus2)
    exec_res = ExecutionResult(case_id="c1", input="q", output="a", elapsed_seconds=0.1)
    metric_res = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=1.0,
        status=MetricStatus.PASS,
        explanation="Exact match.",
    )
    case_rec = CaseEvaluationRecord(
        case_id="c1",
        mandatory=True,
        execution=exec_res,
        metrics={"exact_match": metric_res},
    )
    run = RunRecord(
        run_id="run-001",
        timestamp=ts,
        package_version="0.1.0",
        dataset_id="ds-1",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=1,
        metric_versions={"exact_match": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=1.0,
                applicable_count=1,
                pass_count=1,
            )
        },
        status_counts={
            status: (1 if status == MetricStatus.PASS else 0) for status in MetricStatus
        },
        case_results=[case_rec],
    )
    assert run.timestamp.utcoffset() == timedelta(0)
    manifest = RunManifestEntry.from_run_record(run)
    assert manifest.aggregate_scores == {"exact_match": 1.0}

    cfg = OrchestratorConfig()
    assert cfg.max_concurrency == 4
    with pytest.raises(ValidationError):
        OrchestratorConfig(max_concurrency=True)

    meta = MetricMetadata(
        metric_id="exact_match",
        metric_version="1.0.0",
        what_it_measures="exact",
        required_case_fields=("reference",),
        required_execution_fields=("output",),
        calculation_method="eq",
        known_limitations="lexical",
    )
    assert meta.metric_id == "exact_match"

    # Parity check against M1 schemas overlaid with additive M3 RunRecord / RunManifestEntry fields
    schema_path = Path("specs/001-evaluation-foundation/contracts/schemas-v1.json")
    contract_schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    m3_path = Path("specs/003-experiment-regression-engine/contracts/schemas-v1.json")
    m3_schema: dict[str, Any] = json.loads(m3_path.read_text(encoding="utf-8"))
    defs = {**contract_schema["$defs"], **m3_schema["$defs"]}

    def _validate_def(def_name: str, payload: dict[str, Any]) -> None:
        sub_schema = {"$schema": contract_schema["$schema"], "$defs": defs, **defs[def_name]}
        jsonschema.validate(instance=payload, schema=sub_schema)

    case = EvaluationCase(id="c1", input="q", reference="a")
    _validate_def("EvaluationCase", case.model_dump(mode="json"))
    _validate_def("ExecutionResult", exec_res.model_dump(mode="json"))
    _validate_def("MetricResult", metric_res.model_dump(mode="json"))
    _validate_def("CaseEvaluationRecord", case_rec.model_dump(mode="json"))
    _validate_def("RunRecord", run.model_dump(mode="json"))
    _validate_def("RunManifestEntry", manifest.model_dump(mode="json"))

    # Legacy M1 serialized payloads omitting M3 optional fields remain readable
    legacy_run_json = run.model_dump(mode="json")
    legacy_run_json.pop("judge_config_fingerprint")
    assert RunRecord.model_validate(legacy_run_json).judge_config_fingerprint is None

    legacy_manifest_json = manifest.model_dump(mode="json")
    legacy_manifest_json.pop("model_id")
    legacy_manifest_json.pop("judge_config_fingerprint")
    loaded_legacy_manifest = RunManifestEntry.model_validate(legacy_manifest_json)
    assert loaded_legacy_manifest.model_id is None
    assert loaded_legacy_manifest.judge_config_fingerprint is None


def test_m2_expected_context_retrieved_chunk_rag_extractor_and_schema_parity() -> None:
    item = ExpectedContextItem(id="  chunk-2  ", text="passage", relevance=3)
    assert item.id == "chunk-2"
    assert item.relevance == 3

    case = EvaluationCase(
        id="c-rag",
        input="What is M2?",
        expected_context=["  chunk-1 ", {"id": "chunk-3", "relevance": 2}, item],  # type: ignore[list-item]
    )
    assert case.expected_context is not None
    assert len(case.expected_context) == 3
    assert case.expected_context[0] == "chunk-1"
    assert isinstance(case.expected_context[1], ExpectedContextItem)
    assert case.expected_context[1].id == "chunk-3"

    # Duplicate effective IDs (string vs ExpectedContextItem) must fail
    with pytest.raises(ValidationError):
        EvaluationCase(
            id="c-dup",
            input="q",
            expected_context=["chunk-1", ExpectedContextItem(id="chunk-1", relevance=2)],
        )

    with pytest.raises(ValidationError):
        EvaluationCase(id="c-dup-str", input="q", expected_context=["chunk-1", " chunk-1 "])

    with pytest.raises(ValidationError):
        EvaluationCase(id="c-blank-ctx", input="q", expected_context=["   "])

    for bad_rel in (-1, True, 1.5, 1.0, float("nan")):
        with pytest.raises(ValidationError):
            ExpectedContextItem(id="c1", relevance=bad_rel)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ExpectedContextItem(id="   ")

    # RetrievedChunk bounds: rank >= 1 (int, not bool/float) and finite non-bool score
    chunk = RetrievedChunk(id=" ch-1 ", text="", parent_id="doc-1", rank=1, score=0.75)
    assert chunk.id == "ch-1"
    for bad_rank in (0, -2, True, 1.0, 1.5):
        with pytest.raises(ValidationError):
            RetrievedChunk(id="ch-1", text="t", rank=bad_rank)  # type: ignore[arg-type]

    for bad_score in (True, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError):
            RetrievedChunk(id="ch-1", text="t", score=bad_score)

    # RAGExtractorConfig strict config + whitespace path rejection
    def _extract(payload: Any) -> Any:
        return payload

    ext_cfg = RAGExtractorConfig(
        output="answer.text",
        chunks=_extract,
        chunk_id="id",
        chunk_text="content",
        chunk_parent_id="metadata.parent_id",
        chunk_rank="rank",
        chunk_score="score",
        chunk_metadata="metadata",
        tokens="usage",
    )
    assert ext_cfg.output == "answer.text"
    with pytest.raises(ValidationError):
        RAGExtractorConfig(output="   ")
    with pytest.raises(ValidationError):
        RAGExtractorConfig.model_validate({"unknown_field": "x"})

    # Parity check against specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json
    m2_schema_path = Path("specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json")
    m2_schema: dict[str, Any] = json.loads(m2_schema_path.read_text(encoding="utf-8"))
    m2_defs = m2_schema["$defs"]

    def _validate_m2(def_name: str, payload: Any) -> None:
        sub_schema = {"$schema": m2_schema["$schema"], "$defs": m2_defs, **m2_defs[def_name]}
        jsonschema.validate(instance=payload, schema=sub_schema)

    _validate_m2("ExpectedContextItem", item.model_dump(mode="json"))
    _validate_m2(
        "EvaluationCaseExpectedContext",
        case.model_dump(mode="json")["expected_context"],
    )
    _validate_m2("RetrievedChunk", chunk.model_dump(mode="json"))


def test_m3_enums_drift_anomaly_and_quality_gate_policy_contracts() -> None:
    assert {d.value for d in GateDecision} == {"PASS", "FAIL", "WARNING", "INCONCLUSIVE"}
    assert {d.value for d in ComparisonDirection} == {
        "IMPROVED",
        "REGRESSED",
        "UNCHANGED",
        "ADDED",
        "REMOVED",
        "INCONCLUSIVE",
    }
    assert {d.value for d in TrendDirection} == {
        "IMPROVING",
        "STABLE",
        "DEGRADING",
        "INSUFFICIENT_DATA",
    }
    assert len(DriftCategory) == 6
    assert len(AnomalyType) == 5

    dw = DriftWarning(
        category=DriftCategory.JUDGE_CONFIG,
        baseline_run_id="r1",
        candidate_run_id="r2",
        baseline_value="fp1",
        candidate_value="fp2",
        explanation="Judge config fingerprint changed",
    )
    assert dw.category == DriftCategory.JUDGE_CONFIG
    with pytest.raises(ValidationError):
        DriftWarning(category=DriftCategory.METRIC_VERSION, explanation="   ")
    with pytest.raises(ValidationError):
        DriftWarning(
            category=DriftCategory.METRIC_VERSION,
            baseline_value=float("nan"),
            explanation="bad",
        )

    af = AnomalyFlag(
        anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
        severity=AnomalySeverity.WARNING,
        scope=AnomalyScope.CASE,
        case_id=" c1 ",
        metric_ids=["exact_match", "precision_at_k"],
        spread=0.8000001,
        explanation="Case metric spread > 0.3",
    )
    assert af.case_id == "c1"
    assert af.spread == 0.8
    with pytest.raises(ValidationError):
        AnomalyFlag(
            anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
            severity=AnomalySeverity.WARNING,
            scope=AnomalyScope.CASE,
            explanation="Missing case_id",
        )
    with pytest.raises(ValidationError):
        AnomalyFlag(
            anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
            severity=AnomalySeverity.WARNING,
            scope=AnomalyScope.RUN,
            spread=True,
            explanation="Bool rejected",
        )

    policy = QualityGatePolicy(
        min_score=0.75,
        min_metric_scores={"exact_match": 0.9},
        max_metric_regression_drops={"recall_at_k": 0.02},
        max_regressed_cases=1,
    )
    assert policy.max_regression_drop == 0.05
    assert policy.disagreement_threshold == 0.3
    assert policy.case_drop_warning_threshold == 0.25
    assert policy.trend_slope_threshold == 0.01
    assert policy.max_inconclusive_rate == 0.1
    assert policy.fail_on_mandatory_regression is True

    with pytest.raises(ValidationError):
        QualityGatePolicy(max_regression_drop=True)
    with pytest.raises(ValidationError):
        QualityGatePolicy(max_regressed_cases=True)
    with pytest.raises(ValidationError):
        QualityGatePolicy(trend_slope_threshold=0.0)
    with pytest.raises(ValidationError):
        QualityGatePolicy(min_metric_scores={" ": 0.5})
    with pytest.raises(ValidationError):
        QualityGatePolicy(min_metric_scores={"m": 1.2})
