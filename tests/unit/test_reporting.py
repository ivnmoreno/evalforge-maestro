"""Unit tests for pure reporting diagnostics, Three-Way Markdown, and redaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from evalforge_maestro.reporting import (
    build_calibration_report,
    build_comparison_report,
    build_run_report,
    build_trend_report,
    detect_decoupled_evidence,
    render_markdown,
    render_report_json,
)
from evalforge_maestro.types import (
    AggregateMetricSummary,
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    CalibrationDisagreement,
    CalibrationDisagreementType,
    CalibrationReport,
    CaseEvaluationRecord,
    ComparisonDirection,
    DriftCategory,
    DriftWarning,
    ExecutionResult,
    GateDecision,
    GateRuleCheck,
    JudgeConfig,
    MetricComparison,
    MetricResult,
    MetricStatus,
    MetricTrendSummary,
    QualityGateResult,
    RetrievedChunk,
    RunCohortSummary,
    RunComparisonReport,
    RunRecord,
    SignificanceStatus,
    StatisticalMethod,
    StatisticalSummary,
    TargetChangeSummary,
    ToolCallRecord,
    ToolCallStatus,
    TrendDirection,
    TrendReport,
)


def _sample_run(*, include_secret: bool = False) -> RunRecord:
    out_b = "Paris Authorization: Bearer secret_leak_abc" if include_secret else "Wrong City"
    return RunRecord(
        run_id="run-m5-001",
        timestamp=datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc),
        package_version="0.5.0",
        dataset_id="rag-bench",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=2,
        system_version="v1.0",
        model_id="mock-app",
        config_fingerprint="b" * 64,
        judge_config_fingerprint="c" * 64,
        metric_versions={"exact_match": "1.0.0", "precision_at_k": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=0.5,
                applicable_count=2,
                pass_count=1,
                fail_count=1,
            ),
            "precision_at_k": AggregateMetricSummary(
                metric_id="precision_at_k",
                metric_version="1.0.0",
                mean_score=0.5,
                applicable_count=2,
                pass_count=1,
                fail_count=1,
            ),
        },
        status_counts={MetricStatus.PASS: 2, MetricStatus.FAIL: 2},
        mandatory_failed_case_ids=["c2"],
        has_mandatory_failures=True,
        case_results=[
            CaseEvaluationRecord(
                case_id="c1",
                mandatory=False,
                execution=ExecutionResult(
                    case_id="c1",
                    input="Capital of France?",
                    output="Paris",
                    retrieved_chunks=[RetrievedChunk(id="off-topic", text="Noise")],
                    elapsed_seconds=0.01,
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="Exact match.",
                    ),
                    "precision_at_k": MetricResult(
                        metric_id="precision_at_k",
                        metric_version="1.0.0",
                        score=0.0,
                        status=MetricStatus.FAIL,
                        explanation="Off-topic chunk retrieved.",
                    ),
                },
            ),
            CaseEvaluationRecord(
                case_id="c2",
                mandatory=True,
                execution=ExecutionResult(
                    case_id="c2",
                    input="Capital of Germany?",
                    output=out_b,
                    retrieved_chunks=[RetrievedChunk(id="doc-berlin", text="Berlin is capital.")],
                    elapsed_seconds=0.01,
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=0.0,
                        status=MetricStatus.FAIL,
                        explanation="Missed answer | pipe\nline.",
                    ),
                    "precision_at_k": MetricResult(
                        metric_id="precision_at_k",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="Relevant chunk retrieved.",
                    ),
                },
            ),
        ],
    )


def test_detect_decoupled_evidence_and_three_way_markdown_with_redaction() -> None:
    run = _sample_run(include_secret=True)
    decoupled = detect_decoupled_evidence(run)
    assert len(decoupled) == 2
    assert decoupled[0].case_id == "c1"
    assert decoupled[0].category.value == "answer_passed_retrieval_or_grounding_failed"
    assert decoupled[1].case_id == "c2"
    assert decoupled[1].category.value == "retrieval_passed_answer_or_grounding_failed"

    gate = QualityGateResult(
        decision=GateDecision.FAIL,
        candidate_run_id=run.run_id,
        passed=False,
        blocking=True,
        inconclusive_rate=0.0,
        checks=[
            GateRuleCheck(
                rule_id="mandatory_cases",
                status=GateDecision.FAIL,
                message="Mandatory case c2 failed.",
                observed=1,
                threshold=0,
            )
        ],
        failure_reasons=["Mandatory case c2 failed."],
        anomalies=[
            AnomalyFlag(
                anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
                severity=AnomalySeverity.WARNING,
                scope=AnomalyScope.CASE,
                case_id="c1",
                metric_ids=["exact_match", "precision_at_k"],
                spread=1.0,
                explanation="Sub-metrics diverged by 1.0.",
            )
        ],
        drift_warnings=[
            DriftWarning(
                category=DriftCategory.METRIC_VERSION,
                metric_id="exact_match",
                baseline_value="0.9.0",
                candidate_value="1.0.0",
                explanation="Metric version bumped.",
            )
        ],
        summary="QualityGate=FAIL",
    )

    doc = build_run_report(run, gate=gate)
    md = render_markdown(doc)
    assert "## Evaluation" in md
    assert "## Regression" in md
    assert "## Acceptance / Quality Gate" in md
    assert "## Diagnostics & Anomalies" in md
    assert (
        md.index("## Evaluation")
        < md.index("## Regression")
        < md.index("## Acceptance / Quality Gate")
    )
    assert "### Evidence Decoupling Findings" in md
    assert "### Anti-Masking & Disagreement Anomalies" in md
    assert "### Cross-Version Provenance Drift Warnings" in md
    assert "secret_leak_abc" not in md
    assert "[REDACTED]" in md

    raw_json = render_report_json(doc)
    assert "secret_leak_abc" not in raw_json
    parsed = json.loads(raw_json)
    assert parsed["schema_version"] == "1.0"
    assert parsed["report_kind"] == "run"


def test_compare_trend_and_calibration_report_builders() -> None:
    cmp_rep = RunComparisonReport(
        baseline_run_id="base-1",
        candidate_run_id="cand-2",
        baseline_name="prod",
        target_changes=TargetChangeSummary(),
        metric_comparisons={
            "exact_match": MetricComparison(
                metric_id="exact_match",
                baseline_version="1.0.0",
                candidate_version="1.0.0",
                baseline_score=0.9,
                candidate_score=0.8,
                delta=-0.1,
                direction=ComparisonDirection.REGRESSED,
            )
        },
        case_comparisons=[],
        matched_case_count=1,
        regressed_case_ids=["c2"],
    )
    cmp_doc = build_comparison_report(cmp_rep)
    cmp_md = render_markdown(cmp_doc)
    assert "Pairwise Comparison" in cmp_md
    assert "-0.1" in cmp_md

    trend_rep = TrendReport(
        window=3,
        inspected_run_ids=["r1", "r2"],
        slope_threshold=0.01,
        metrics={
            "exact_match": MetricTrendSummary(
                metric_id="exact_match",
                window_runs=2,
                valid_points=2,
                missing_points=0,
                slope=-0.05,
                direction=TrendDirection.DEGRADING,
                first_score=0.9,
                last_score=0.85,
                min_score=0.85,
                max_score=0.9,
                mean_score=0.875,
                explanation="Degrading slope.",
            )
        },
    )
    trend_doc = build_trend_report(trend_rep)
    trend_md = render_markdown(trend_doc)
    assert "Sliding Window Trend" in trend_md
    assert "DEGRADING" in trend_md

    cfg = JudgeConfig(mock_mode=True, local_only=True)
    cal_rep = CalibrationReport(
        metric_id="groundedness",
        metric_version="1.0.0",
        judge_config=cfg,
        judge_config_fingerprint=cfg.fingerprint,
        total_cases=2,
        valid_cases=2,
        inconclusive_cases=0,
        pass_threshold_evaluated=0.5,
        human_threshold_evaluated=0.5,
        exact_agreement_rate=50.0,
        too_generous_rate=0.5,
        too_harsh_rate=0.0,
        mean_human_score=0.4,
        mean_judge_score=0.75,
        mean_score_delta=0.35,
        disagreements=[
            CalibrationDisagreement(
                case_id="cal-2",
                disagreement_type=CalibrationDisagreementType.TOO_GENEROUS,
                human_score=0.1,
                human_passed=False,
                judge_score=0.9,
                judge_status=MetricStatus.PASS,
                judge_passed=True,
                score_delta=0.8,
                judge_rationale="Token sk-calibration-secret-key999 leaked",
            )
        ],
        recommended_pass_threshold=0.7,
    )
    cal_doc = build_calibration_report(cal_rep, min_agreement=80.0, strict=True)
    assert cal_doc.calibration_gate is not None
    assert cal_doc.calibration_gate.passed is False
    cal_md = render_markdown(cal_doc)
    assert "Calibration Disagreements" in cal_md
    assert "sk-calibration-secret-key999" not in cal_md


def test_detect_decoupled_agent_trace_vs_answer_diagnostics_and_markdown() -> None:
    run = RunRecord(
        run_id="run-agent-decoupled",
        timestamp=datetime(2026, 11, 20, tzinfo=timezone.utc),
        package_version="0.2.0",
        dataset_id="agent-ds",
        dataset_fingerprint="d" * 64,
        evaluated_case_count=2,
        metric_versions={
            "exact_match": "1.0.0",
            "policy_compliance": "1.0.0",
            "tool_selection": "1.0.0",
        },
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=0.5,
                applicable_count=2,
                pass_count=1,
                fail_count=1,
            ),
            "policy_compliance": AggregateMetricSummary(
                metric_id="policy_compliance",
                metric_version="1.0.0",
                mean_score=0.5,
                applicable_count=2,
                pass_count=1,
                fail_count=1,
            ),
            "tool_selection": AggregateMetricSummary(
                metric_id="tool_selection",
                metric_version="1.0.0",
                mean_score=1.0,
                applicable_count=2,
                pass_count=2,
            ),
        },
        status_counts={MetricStatus.PASS: 4, MetricStatus.FAIL: 2},
        case_results=[
            CaseEvaluationRecord(
                case_id="ag-bad-trace",
                mandatory=True,
                execution=ExecutionResult(
                    case_id="ag-bad-trace",
                    input="Refund user",
                    output="Refund issued.",
                    tool_calls=[
                        ToolCallRecord(
                            name="delete_user",
                            arguments={"token": "sk-topsecret-agent-token99"},
                            status=ToolCallStatus.BLOCKED,
                        )
                    ],
                    elapsed_seconds=0.05,
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="Answer matched.",
                    ),
                    "policy_compliance": MetricResult(
                        metric_id="policy_compliance",
                        metric_version="1.0.0",
                        score=0.0,
                        status=MetricStatus.FAIL,
                        explanation="Forbidden tool invoked.",
                    ),
                },
            ),
            CaseEvaluationRecord(
                case_id="ag-bad-answer",
                mandatory=False,
                execution=ExecutionResult(
                    case_id="ag-bad-answer",
                    input="Check policy",
                    output="Wrong text",
                    tool_calls=[ToolCallRecord(name="read_policy", status=ToolCallStatus.SUCCESS)],
                    elapsed_seconds=0.05,
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=0.0,
                        status=MetricStatus.FAIL,
                        explanation="Wrong synthesis.",
                    ),
                    "tool_selection": MetricResult(
                        metric_id="tool_selection",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="Selected read_policy cleanly.",
                    ),
                    "policy_compliance": MetricResult(
                        metric_id="policy_compliance",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="Policy ok.",
                    ),
                },
            ),
        ],
    )
    doc = build_run_report(run)
    decs = doc.diagnostics.decoupled_evidence_cases
    assert len(decs) == 2
    assert decs[0].case_id == "ag-bad-trace"
    assert decs[0].category.value == "answer_passed_agent_trace_failed"
    assert "delete_user" in decs[0].explanation
    assert decs[1].case_id == "ag-bad-answer"
    assert decs[1].category.value == "agent_trace_passed_answer_failed"
    assert "read_policy" in decs[1].explanation

    md = render_markdown(doc)
    assert "answer_passed_agent_trace_failed" in md
    assert "agent_trace_passed_answer_failed" in md
    assert "delete_user" in md
    assert "sk-topsecret-agent-token99" not in md


def test_markdown_renders_statistical_ci_dispersion_and_cohort_summary() -> None:
    stat = StatisticalSummary(
        method=StatisticalMethod.WELCH_T_RUN,
        confidence_level=0.95,
        sample_size=3,
        baseline_sample_size=3,
        candidate_sample_size=3,
        mean_delta=-0.15,
        delta_std=0.04,
        standard_error=0.023094,
        baseline_std=0.02,
        candidate_std=0.03,
        ci_low=-0.214,
        ci_high=-0.086,
        p_value=0.0021,
        effect_size=-5.883484,
        degrees_of_freedom=3.4,
        significance=SignificanceStatus.SIGNIFICANT_REGRESSION,
        statistically_significant=True,
        explanation="Significant regression across 3v3 runs.",
    )
    comparison = RunComparisonReport(
        baseline_run_id="base-r03",
        candidate_run_id="cand-r03",
        baseline_name="v1-cohort",
        target_changes=TargetChangeSummary(),
        metric_comparisons={
            "exact_match": MetricComparison(
                metric_id="exact_match",
                baseline_score=0.9,
                candidate_score=0.75,
                delta=-0.15,
                direction=ComparisonDirection.REGRESSED,
                statistics=stat,
            )
        },
        case_comparisons=[],
        matched_case_count=10,
        cohort=RunCohortSummary(
            baseline_run_ids=["base-r01", "base-r02", "base-r03"],
            candidate_run_ids=["cand-r01", "cand-r02", "cand-r03"],
            baseline_run_count=3,
            candidate_run_count=3,
            baseline_names=["v1-cohort"],
        ),
    )
    doc = build_comparison_report(comparison)
    md = render_markdown(doc)
    assert "Cohort" in md
    assert "3 baseline" in md or "baseline=3" in md
    assert "significant_regression" in md
    assert "-0.214" in md and "-0.086" in md
    assert "0.0021" in md
    assert "0.02" in md and "0.03" in md
    assert "welch_t_run" in md
