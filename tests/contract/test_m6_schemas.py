"""Contract tests validating Milestone 6 agent trace payloads against Draft 2020-12 schemas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from evalforge_maestro.reporting import build_run_report
from evalforge_maestro.types import (
    AgentExtractorConfig,
    AgentTraceStep,
    AggregateMetricSummary,
    CaseCriteria,
    CaseEvaluationRecord,
    CLIResolvedConfig,
    DecoupledEvidenceDiagnostic,
    EvaluationCase,
    EvidenceDecouplingCategory,
    ExecutionResult,
    ExpectedToolCall,
    MetricResult,
    MetricSpecConfig,
    MetricStatus,
    ResolvedTargetConfig,
    RunRecord,
    TargetType,
    ToolCallRecord,
    ToolCallStatus,
    TraceStepKind,
)


def _merged_m6_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    defs: dict[str, Any] = {}
    m6: dict[str, Any] = {}
    for rel_path in (
        "specs/001-evaluation-foundation/contracts/schemas-v1.json",
        "specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json",
        "specs/003-experiment-regression-engine/contracts/schemas-v1.json",
        "specs/004-judge-calibration-engine/contracts/schemas-v1.json",
        "specs/005-cli-reporting-ci/contracts/schemas-v1.json",
        "specs/006-agent-trace-evaluation/contracts/schemas-v1.json",
    ):
        doc = json.loads(Path(rel_path).read_text(encoding="utf-8"))
        defs.update(doc["$defs"])
        m6 = doc
    merged = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs}
    jsonschema.Draft202012Validator.check_schema(merged)
    return merged, m6


def _validate_def(schema_root: dict[str, Any], def_name: str, instance: Any) -> None:
    validator = jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": schema_root["$defs"]}
    )
    validator.validate(instance)


def test_m6_schema_contract_is_valid_draft_2020_12() -> None:
    merged, m6 = _merged_m6_schema()
    assert {
        "ToolCallStatus",
        "TraceStepKind",
        "TargetType",
        "EvidenceDecouplingCategory",
        "ExpectedToolCall",
        "ToolCallRecord",
        "AgentTraceStep",
        "CaseCriteria",
        "EvaluationCase",
        "ExecutionResult",
        "ResolvedTargetConfig",
    } <= set(m6["$defs"])
    assert len(merged["$defs"]) >= 66


def test_m6_runtime_models_validate_against_contract_schemas() -> None:
    merged, _ = _merged_m6_schema()

    case = EvaluationCase(
        id="agent-case-1",
        input="Look up order and summarize",
        reference="Shipped",
        expected_tools=[
            ExpectedToolCall(
                name="get_order",
                arguments={"order_id": "123"},
                arguments_schema={"type": "object", "required": ["order_id"]},
                argument_match_mode="subset",
                order=0,
            )
        ],
        criteria=CaseCriteria(
            mandatory=True,
            forbidden_tools=["delete_order"],
            forbidden_argument_patterns=["--force"],
            max_steps=6,
            max_tool_calls=4,
            allow_redundant_failures=0,
        ),
    )
    _validate_def(merged, "EvaluationCase", case.model_dump(mode="json"))

    call = ToolCallRecord(
        id="tc-1",
        name="get_order",
        arguments={"order_id": "123"},
        result={"status": "shipped"},
        status=ToolCallStatus.SUCCESS,
        step_index=1,
        elapsed_seconds=0.05,
    )
    step = AgentTraceStep(
        step_index=0,
        kind=TraceStepKind.TOOL_CALL,
        name="assistant",
        tool_calls=[call],
    )
    exec_res = ExecutionResult(
        case_id="agent-case-1",
        input="Look up order and summarize",
        output="Shipped",
        tool_calls=[call],
        trace=[step],
        elapsed_seconds=0.1,
    )
    _validate_def(merged, "ToolCallRecord", call.model_dump(mode="json"))
    _validate_def(merged, "AgentTraceStep", step.model_dump(mode="json"))
    _validate_def(merged, "ExecutionResult", exec_res.model_dump(mode="json"))

    cfg = CLIResolvedConfig(
        dataset="agent.jsonl",
        target=ResolvedTargetConfig(
            target_type=TargetType.AGENT,
            entrypoint="my_agent:run",
            agent_extractors={"tool_calls": "steps"},
        ),
        metrics=[MetricSpecConfig(metric_id="tool_selection")],
    )
    cfg_m6 = cfg.model_dump(mode="json")
    for k in ("repeats", "baseline_runs", "embedding", "otel_traces", "otel"):
        cfg_m6.pop(k, None)
    cfg_m6["execution"].pop("embedding_config_fingerprint", None)
    for k in ("confidence_level", "min_statistical_samples", "fail_on_significant_regression"):
        cfg_m6["gate"].pop(k, None)
    _validate_def(merged, "CLIResolvedConfig", cfg_m6)

    ext = AgentExtractorConfig(tool_calls="messages", output="answer")
    assert ext.tool_calls == "messages"

    run = RunRecord(
        run_id="run-m6-1",
        timestamp=datetime(2026, 11, 20, tzinfo=timezone.utc),
        package_version="0.2.0",
        dataset_id="agent-ds",
        dataset_fingerprint="b" * 64,
        evaluated_case_count=1,
        metric_versions={"exact_match": "1.0.0", "policy_compliance": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=1.0,
                applicable_count=1,
                pass_count=1,
            ),
            "policy_compliance": AggregateMetricSummary(
                metric_id="policy_compliance",
                metric_version="1.0.0",
                mean_score=0.0,
                applicable_count=1,
                fail_count=1,
            ),
        },
        status_counts={MetricStatus.PASS: 1, MetricStatus.FAIL: 1},
        case_results=[
            CaseEvaluationRecord(
                case_id="agent-case-1",
                execution=exec_res,
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="ok",
                    ),
                    "policy_compliance": MetricResult(
                        metric_id="policy_compliance",
                        metric_version="1.0.0",
                        score=0.0,
                        status=MetricStatus.FAIL,
                        explanation="blocked tool",
                    ),
                },
            )
        ],
    )
    report_doc = build_run_report(run)
    report_m6 = report_doc.model_dump(mode="json")
    for k in ("cohort_run_ids", "cohort_aggregates"):
        report_m6.pop(k, None)
    report_m6["evaluation"].pop("embedding_config_fingerprint", None)
    _validate_def(merged, "ReportDocument", report_m6)

    diag = DecoupledEvidenceDiagnostic(
        case_id="agent-case-1",
        category=EvidenceDecouplingCategory.ANSWER_PASSED_AGENT_TRACE_FAILED,
        passed_metrics=["exact_match"],
        failed_metrics=["policy_compliance"],
        explanation="Answer passed while agent trace failed.",
    )
    _validate_def(merged, "DecoupledEvidenceDiagnostic", diag.model_dump(mode="json"))
