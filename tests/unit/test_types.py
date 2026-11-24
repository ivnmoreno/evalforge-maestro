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
    AggregateMetricSummary,
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    CalibrationDisagreement,
    CalibrationDisagreementType,
    CalibrationReport,
    CaseCriteria,
    CaseEvaluationRecord,
    CaseMetadata,
    CaseSplit,
    ComparisonDirection,
    DriftCategory,
    DriftWarning,
    EvaluationCase,
    EvidenceDecouplingCategory,
    ExecutionResult,
    ExpectedContextItem,
    ExpectedToolCall,
    GateDecision,
    HumanCalibrationSample,
    JudgeConfig,
    JudgeResponse,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    QualityGatePolicy,
    RAGExtractorConfig,
    RetrievedChunk,
    RunManifestEntry,
    RunRecord,
    TargetType,
    TokenUsage,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
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
    assert issubclass(JudgeError, EvalforgeError)
    assert issubclass(LocalOnlyPolicyError, EvalforgeError)

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

    # Parity check against M1 schemas overlaid with additive M3 and M6 fields
    schemas_dir = Path(__file__).resolve().parents[1] / "contract" / "schemas"
    schema_path = schemas_dir / "m1-schemas-v1.json"
    contract_schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    m3_path = schemas_dir / "m3-schemas-v1.json"
    m3_schema: dict[str, Any] = json.loads(m3_path.read_text(encoding="utf-8"))
    m6_path = schemas_dir / "m6-schemas-v1.json"
    m6_schema: dict[str, Any] = json.loads(m6_path.read_text(encoding="utf-8"))
    defs = {**contract_schema["$defs"], **m3_schema["$defs"], **m6_schema["$defs"]}

    def _validate_def(def_name: str, payload: dict[str, Any]) -> None:
        sub_schema = {"$schema": contract_schema["$schema"], "$defs": defs, **defs[def_name]}
        jsonschema.validate(instance=payload, schema=sub_schema)

    case = EvaluationCase(id="c1", input="q", reference="a")
    _validate_def("EvaluationCase", case.model_dump(mode="json"))
    _validate_def("ExecutionResult", exec_res.model_dump(mode="json"))
    _validate_def("MetricResult", metric_res.model_dump(mode="json"))
    _validate_def("CaseEvaluationRecord", case_rec.model_dump(mode="json"))
    run_payload = run.model_dump(mode="json")
    run_payload.pop("embedding_config_fingerprint", None)
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload.pop("embedding_config_fingerprint", None)
    _validate_def("RunRecord", run_payload)
    _validate_def("RunManifestEntry", manifest_payload)

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

    # Parity check against M2 retrieval schema contract
    m2_schema_path = (
        Path(__file__).resolve().parents[1] / "contract" / "schemas" / "m2-schemas-v1.json"
    )
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
    assert len(DriftCategory) == 7
    assert DriftCategory.EMBEDDING_CONFIG.value == "EMBEDDING_CONFIG"
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


def test_m4_judge_and_calibration_contracts_enforce_strict_validation() -> None:
    cfg = JudgeConfig(
        model=" ollama_chat/llama3.2 ",
        api_base=" http://localhost:11434 ",
        temperature=0.0,
        pass_threshold=0.6666666,
        max_retries=1,
        retry_backoff_seconds=0.1,
        timeout_seconds=15.0,
        local_only=True,
        mock_mode=False,
        seed=42,
        prompt_version=" 2.0 ",
        extra_params={"api_key": "sk-secret", "custom": "ok"},
    )
    assert cfg.model == "ollama_chat/llama3.2"
    assert cfg.api_base == "http://localhost:11434"
    assert cfg.pass_threshold == 0.666667
    assert cfg.prompt_version == "2.0"
    assert cfg.extra_params["api_key"] == "[REDACTED]"
    assert len(cfg.fingerprint) == 64

    # Equal configs excluding redacted secret values emit identical fingerprints
    cfg2 = cfg.model_copy(update={"extra_params": {"api_key": "different", "custom": "ok"}})
    assert cfg.fingerprint == cfg2.fingerprint

    for bad_url in (
        "   ",
        "http://localhost:8000 /v1",
        "ftp://localhost:8000",
        "http://",
        "http://user:pass@localhost:8000",
        "http://localhost:8000?api_key=secret",
        "http://localhost:8000#frag",
        "http://localhost:8000;params",
    ):
        with pytest.raises(ValidationError):
            JudgeConfig(api_base=bad_url)

    for bad_kwargs in (
        {"model": "   "},
        {"prompt_version": ""},
        {"temperature": True},
        {"temperature": float("nan")},
        {"pass_threshold": True},
        {"pass_threshold": 1.2},
        {"max_retries": True},
        {"max_retries": -1},
        {"retry_backoff_seconds": True},
        {"timeout_seconds": 0.0},
        {"timeout_seconds": False},
        {"seed": True},
        {"extra_params": {"nan": float("inf")}},
    ):
        with pytest.raises(ValidationError):
            JudgeConfig.model_validate(bad_kwargs)

    resp = JudgeResponse(
        score=0.75,
        rationale=" Supported well. ",
        verdict=" pass ",
        supported_claims=[" claim a "],
        unsupported_claims=[],
    )
    assert resp.rationale == "Supported well."
    assert resp.verdict == "pass"
    assert resp.supported_claims == ["claim a"]

    for bad_resp in (
        {"score": True, "rationale": "ok"},
        {"score": float("nan"), "rationale": "ok"},
        {"score": 1.05, "rationale": "ok"},
        {"score": -0.1, "rationale": "ok"},
        {"score": 0.5, "rationale": "   "},
        {"score": 0.5, "rationale": "ok", "unsupported_claims": ["  "]},
    ):
        with pytest.raises(ValidationError):
            JudgeResponse.model_validate(bad_resp)

    sample = HumanCalibrationSample(
        case_id=" c-1 ",
        input="Q",
        output="A",
        human_score=0.8,
        notes=" good ",
        metadata={"token": "secret"},
    )
    assert sample.case_id == "c-1"
    assert sample.notes == "good"
    assert sample.metadata["token"] == "[REDACTED]"

    with pytest.raises(ValidationError):
        HumanCalibrationSample(case_id="c-x", input="Q", output="A")
    with pytest.raises(ValidationError):
        HumanCalibrationSample(case_id="c-x", input="Q", output="A", human_score=True)

    dis = CalibrationDisagreement(
        case_id="c-1",
        disagreement_type=CalibrationDisagreementType.SCORE_DIVERGENCE,
        human_score=0.9,
        human_passed=True,
        judge_score=0.55,
        judge_status=MetricStatus.PASS,
        judge_passed=True,
        score_delta=-0.0,
        judge_rationale="Minor delta.",
    )
    assert dis.score_delta == 0.0

    with pytest.raises(ValidationError):
        CalibrationReport(
            metric_id="groundedness",
            metric_version="1.0.0",
            judge_config=cfg,
            judge_config_fingerprint=cfg.fingerprint,
            total_cases=2,
            valid_cases=1,
            inconclusive_cases=0,
            pass_threshold_evaluated=0.5,
            human_threshold_evaluated=0.5,
            recommended_pass_threshold=0.5,
        )
    with pytest.raises(ValidationError):
        CalibrationReport(
            metric_id="groundedness",
            metric_version="1.0.0",
            judge_config=cfg,
            judge_config_fingerprint=cfg.fingerprint,
            total_cases=1,
            valid_cases=0,
            inconclusive_cases=1,
            pass_threshold_evaluated=0.5,
            human_threshold_evaluated=0.5,
            exact_agreement_rate=100.0,
            recommended_pass_threshold=0.5,
        )
    with pytest.raises(ValidationError):
        CalibrationReport(
            metric_id="groundedness",
            metric_version="1.0.0",
            judge_config=cfg,
            judge_config_fingerprint=cfg.fingerprint,
            total_cases=1,
            valid_cases=1,
            inconclusive_cases=0,
            pass_threshold_evaluated=0.5,
            human_threshold_evaluated=0.5,
            recommended_pass_threshold=0.5,
        )


def test_m6_typed_agent_trace_tool_calls_and_legacy_compatibility() -> None:
    assert TargetType.AGENT.value == "agent"
    assert EvidenceDecouplingCategory.ANSWER_PASSED_AGENT_TRACE_FAILED.value == (
        "answer_passed_agent_trace_failed"
    )
    assert EvidenceDecouplingCategory.AGENT_TRACE_PASSED_ANSWER_FAILED.value == (
        "agent_trace_passed_answer_failed"
    )
    assert {s.value for s in ToolCallStatus} == {"success", "error", "timeout", "blocked"}
    assert {k.value for k in TraceStepKind} == {
        "user_input",
        "reasoning",
        "llm_response",
        "tool_call",
        "tool_result",
        "error",
        "final_output",
        "other",
    }

    # ExpectedToolCall handles string shorthand, legacy dicts, and nested OpenAI function dicts
    case = EvaluationCase.model_validate(
        {
            "id": "agent-legacy-1",
            "input": "Check weather and order status",
            "expected_tools": [
                "  search_docs  ",
                {"tool": "get_order", "args": '{"id": "42"}', "order": 1},
                {
                    "function": {"name": "calc_tax", "arguments": {"rate": 0.1}},
                    "optional": True,
                },
            ],
            "criteria": {
                "mandatory": True,
                "forbidden_tools": ["  drop_db  "],
                "forbidden_argument_patterns": ["--force"],
                "max_steps": 8,
                "max_tool_calls": 5,
                "allow_redundant_failures": 1,
            },
        }
    )
    assert case.expected_tools is not None
    assert [t.name for t in case.expected_tools] == ["search_docs", "get_order", "calc_tax"]
    assert case.expected_tools[1].arguments == {"id": "42"}
    assert case.expected_tools[1].order == 1
    assert case.expected_tools[2].optional is True
    assert case.criteria.forbidden_tools == ["drop_db"]
    assert case.criteria.max_steps == 8

    for bad_exp in (
        {"name": "   "},
        {"name": "t", "arguments_schema": {"type": 123}},
        {"name": "t", "order": True},
        {"name": "t", "order": -1},
        {"name": "t", "unknown": 1},
    ):
        with pytest.raises(ValidationError):
            ExpectedToolCall.model_validate(bad_exp)

    for bad_crit in (
        {"forbidden_tools": ["   "]},
        {"forbidden_argument_patterns": ["  "]},
        {"max_steps": 0},
        {"max_steps": True},
        {"max_tool_calls": 0},
        {"allow_redundant_failures": -1},
        {"allow_redundant_failures": True},
    ):
        with pytest.raises(ValidationError):
            CaseCriteria.model_validate(bad_crit)

    # ToolCallRecord parses OpenAI/legacy dict forms and flags invalid JSON arguments safely
    good_tc = ToolCallRecord.model_validate(
        {
            "tool_call_id": "call-1",
            "type": "function",
            "function": {"name": "get_order", "arguments": '{"id": "42"}'},
            "output": {"status": "ok"},
            "step_index": 1,
            "elapsed_seconds": 0.05,
        }
    )
    assert good_tc.id == "call-1"
    assert good_tc.name == "get_order"
    assert good_tc.arguments == {"id": "42"}
    assert good_tc.result == {"status": "ok"}
    assert good_tc.status == ToolCallStatus.SUCCESS

    bad_json_tc = ToolCallRecord.model_validate(
        {
            "name": "get_order",
            "arguments": "{not-valid-json",
        }
    )
    assert bad_json_tc.arguments == {}
    assert bad_json_tc.raw_arguments == "{not-valid-json"
    assert bad_json_tc.argument_parse_error is not None
    assert bad_json_tc.status == ToolCallStatus.ERROR

    non_obj_tc = ToolCallRecord.model_validate({"name": "x", "arguments": "[1, 2]"})
    assert non_obj_tc.status == ToolCallStatus.ERROR
    assert non_obj_tc.argument_parse_error is not None

    failed_tc = ToolCallRecord.model_validate({"tool": "x", "status": "failed", "error": "boom"})
    assert failed_tc.status == ToolCallStatus.ERROR
    assert failed_tc.error == "boom"

    # AgentTraceStep maps legacy role/type strings and preserves nested ToolCallRecord models
    exec_res = ExecutionResult.model_validate(
        {
            "case_id": "agent-legacy-1",
            "input": "Check order",
            "output": "Done",
            "elapsed_seconds": 0.1,
            "tool_calls": [{"tool": "get_order", "args": {"id": "42"}}],
            "trace": [
                {"step_index": 0, "role": "user", "content": "Check order"},
                {"step_index": 1, "role": "assistant", "tool_calls": [{"name": "get_order"}]},
                {"step_index": 2, "role": "tool", "tool_call_id": "c1", "content": "ok"},
            ],
        }
    )
    assert isinstance(exec_res.tool_calls[0], ToolCallRecord)
    assert [s.kind for s in exec_res.trace] == [
        TraceStepKind.USER_INPUT,
        TraceStepKind.LLM_RESPONSE,
        TraceStepKind.TOOL_RESULT,
    ]
    assert isinstance(exec_res.trace[1], AgentTraceStep)
    assert isinstance(exec_res.trace[1].tool_calls[0], ToolCallRecord)

    for bad_tc in (
        {"name": "   "},
        {"name": "t", "step_index": True},
        {"name": "t", "elapsed_seconds": float("nan")},
        {"name": "t", "unknown_extra": 1},
    ):
        with pytest.raises(ValidationError):
            ToolCallRecord.model_validate(bad_tc)

    ext = AgentExtractorConfig(tool_calls="steps.calls", step_kind="kind")
    assert ext.tool_calls == "steps.calls"
    with pytest.raises(ValidationError):
        AgentExtractorConfig(tool_calls="   ")
    with pytest.raises(ValidationError):
        AgentExtractorConfig.model_validate({"bad_key": "x"})
