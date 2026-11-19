"""Three-way Markdown report renderer separating Evaluation, Regression, and Quality Gate."""

from __future__ import annotations

from typing import Any

from evalforge_maestro._canonical import redact_secrets, scrub_secret_text
from evalforge_maestro.types import (
    CalibrationReport,
    MetricStatus,
    QualityGateResult,
    ReportDocument,
    RunComparisonReport,
    RunRecord,
    TrendReport,
)


def _cell(value: Any, *, max_len: int | None = None) -> str:
    if value is None:
        return "-"
    text = scrub_secret_text(str(value))
    text = text.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    if max_len is not None and len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text or "-"


def _fmt_num(value: float | None, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:.6g}{suffix}"


def _render_evaluation_section(
    evaluation: RunRecord | None,
    calibration: CalibrationReport | None,
) -> list[str]:
    lines = ["## Evaluation", ""]
    if evaluation is not None:
        cfg_fp = evaluation.config_fingerprint
        judge_fp = evaluation.judge_config_fingerprint
        cfg_fp_short = f"{cfg_fp[:12]}..." if cfg_fp else None
        judge_fp_short = f"{judge_fp[:12]}..." if judge_fp else None
        lines.extend(
            [
                f"- **Run ID**: `{_cell(evaluation.run_id)}`",
                f"- **Timestamp (UTC)**: `{evaluation.timestamp.isoformat()}`",
                f"- **Dataset**: `{_cell(evaluation.dataset_id)}` "
                f"(version=`{_cell(evaluation.dataset_version)}`, "
                f"fingerprint=`{evaluation.dataset_fingerprint[:12]}...`, "
                f"cases=`{evaluation.evaluated_case_count}`, "
                f"capped=`{evaluation.dataset_capped}`)",
                f"- **Target**: system=`{_cell(evaluation.system_version)}`, "
                f"model=`{_cell(evaluation.model_id)}`, "
                f"config_fp=`{_cell(cfg_fp_short)}`, "
                f"judge_fp=`{_cell(judge_fp_short)}`",
                "",
                "| Metric | Version | Mean | Applicable | Pass | Fail | Warn "
                "| Inconclusive | N/A |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for metric_id in sorted(evaluation.aggregates):
            agg = evaluation.aggregates[metric_id]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(metric_id)}`",
                        f"`{_cell(agg.metric_version)}`",
                        _fmt_num(agg.mean_score),
                        str(agg.applicable_count),
                        str(agg.pass_count),
                        str(agg.fail_count),
                        str(agg.warning_count),
                        str(agg.inconclusive_count),
                        str(agg.not_applicable_count),
                    ]
                )
                + " |"
            )
        lines.append("")
    elif calibration is not None:
        sanitized_cfg = redact_secrets(calibration.judge_config.model_dump(mode="json"))
        agr_fmt = _fmt_num(calibration.exact_agreement_rate, suffix="%")
        lines.extend(
            [
                f"- **Metric**: `{_cell(calibration.metric_id)}` "
                f"(v`{_cell(calibration.metric_version)}`)",
                f"- **Judge Config**: model=`{_cell(sanitized_cfg.get('model'))}`, "
                f"mock_mode=`{calibration.judge_config.mock_mode}`, "
                f"local_only=`{calibration.judge_config.local_only}`, "
                f"fingerprint=`{calibration.judge_config_fingerprint[:12]}...`",
                f"- **Samples**: total=`{calibration.total_cases}`, "
                f"valid=`{calibration.valid_cases}`, "
                f"inconclusive=`{calibration.inconclusive_cases}`",
                "",
                "| Metric | Value |",
                "| --- | --- |",
                f"| Exact Agreement Rate | {agr_fmt} |",
                f"| Too Generous Rate | {_fmt_num(calibration.too_generous_rate)} |",
                f"| Too Harsh Rate | {_fmt_num(calibration.too_harsh_rate)} |",
                f"| Mean Human Score | {_fmt_num(calibration.mean_human_score)} |",
                f"| Mean Judge Score | {_fmt_num(calibration.mean_judge_score)} |",
                f"| Mean Score Delta | {_fmt_num(calibration.mean_score_delta)} |",
                f"| Recommended Pass Threshold | `{calibration.recommended_pass_threshold:.6g}` |",
                "",
            ]
        )
        if calibration.disagreements:
            lines.extend(
                [
                    "### Calibration Disagreements",
                    "",
                    "| Case ID | Type | Human Score | Judge Score | Status | Delta | Rationale |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for item in calibration.disagreements:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{_cell(item.case_id)}`",
                            f"`{item.disagreement_type.value}`",
                            _fmt_num(item.human_score),
                            _fmt_num(item.judge_score),
                            f"`{item.judge_status.value}`",
                            _fmt_num(item.score_delta),
                            _cell(item.judge_rationale, max_len=120),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    else:
        lines.extend(["No evaluation run payload attached to this report.", ""])
    return lines


def _render_regression_section(
    comparison: RunComparisonReport | None,
    trend: TrendReport | None,
) -> list[str]:
    lines = ["## Regression", ""]
    if comparison is None and trend is None:
        lines.extend(["No baseline comparison or sliding-window trend analysis configured.", ""])
        return lines

    if comparison is not None:
        lines.extend(
            [
                f"### Pairwise Comparison (`{_cell(comparison.candidate_run_id)}` vs "
                f"`{_cell(comparison.baseline_run_id)}`)",
                "",
                f"- **Baseline Alias**: `{_cell(comparison.baseline_name)}`",
                f"- **Matched Cases**: `{comparison.matched_case_count}` "
                f"(added=`{len(comparison.added_case_ids)}`, "
                f"removed=`{len(comparison.removed_case_ids)}`, "
                f"regressed=`{len(comparison.regressed_case_ids)}`, "
                f"mandatory_regressed=`{len(comparison.mandatory_regressed_case_ids)}`)",
                "",
                "| Metric | Baseline | Candidate | Delta | Direction |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for metric_id in sorted(comparison.metric_comparisons):
            mc = comparison.metric_comparisons[metric_id]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(metric_id)}`",
                        _fmt_num(mc.baseline_score),
                        _fmt_num(mc.candidate_score),
                        _fmt_num(mc.delta),
                        f"`{mc.direction.value}`",
                    ]
                )
                + " |"
            )
        lines.append("")

    if trend is not None:
        lines.extend(
            [
                f"### Sliding Window Trend (window=`{trend.window}`, "
                f"inspected=`{len(trend.inspected_run_ids)}` runs)",
                "",
                f"- **Dataset Filter**: `{_cell(trend.dataset_id_filter)}` | "
                f"**Model Filter**: `{_cell(trend.model_id_filter)}`",
                "",
                "| Metric | Valid Points | Slope / Run | Direction | First | Last | Mean |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for metric_id in sorted(trend.metrics):
            ts = trend.metrics[metric_id]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(metric_id)}`",
                        f"{ts.valid_points}/{ts.window_runs}",
                        _fmt_num(ts.slope),
                        f"`{ts.direction.value}`",
                        _fmt_num(ts.first_score),
                        _fmt_num(ts.last_score),
                        _fmt_num(ts.mean_score),
                    ]
                )
                + " |"
            )
        lines.append("")

    return lines


def _render_gate_section(
    gate: QualityGateResult | None,
    document: ReportDocument,
) -> list[str]:
    lines = ["## Acceptance / Quality Gate", ""]
    if gate is not None:
        lines.extend(
            [
                f"- **Decision**: **`{gate.decision.value}`** (`passed={gate.passed}`, "
                f"`blocking={gate.blocking}`, `inconclusive_rate={gate.inconclusive_rate:.6g}`)",
                f"- **Summary**: {_cell(gate.summary)}",
                "",
            ]
        )
        if gate.checks:
            lines.extend(
                [
                    "| Rule | Status | Metric | Observed | Threshold | Details |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for chk in gate.checks:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{_cell(chk.rule_id)}`",
                            f"`{chk.status.value}`",
                            f"`{_cell(chk.metric_id)}`",
                            _cell(chk.observed),
                            _cell(chk.threshold),
                            _cell(chk.message, max_len=140),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        return lines

    if document.calibration_gate is not None:
        cg = document.calibration_gate
        verdict = "PASS" if cg.passed else "FAIL"
        lines.extend(
            [
                f"- **Calibration Gate Decision**: **`{verdict}`** (`strict={cg.strict}`, "
                f"`min_agreement={_fmt_num(cg.min_agreement, suffix='%')}`, "
                f"`observed={_fmt_num(cg.observed_agreement, suffix='%')}`)",
                f"- **Reason**: {_cell(cg.reason)}",
                "",
            ]
        )
        return lines

    lines.extend(["No quality gate policy evaluated for this report.", ""])
    return lines


def _render_diagnostics_section(document: ReportDocument) -> list[str]:
    diag = document.diagnostics
    lines = ["## Diagnostics & Anomalies", ""]
    has_findings = bool(
        diag.mandatory_failed_case_ids
        or diag.decoupled_evidence_cases
        or diag.anomaly_highlights
        or diag.drift_highlights
    )

    if diag.mandatory_failed_case_ids:
        joined = ", ".join(f"`{_cell(cid)}`" for cid in diag.mandatory_failed_case_ids)
        lines.append(f"- **Mandatory Failed Cases**: {joined}")

    if diag.decoupled_evidence_cases:
        lines.extend(
            [
                "",
                "### Evidence Decoupling Findings",
                "",
                "| Case ID | Mandatory | Category | Passed | Failed | Chunks | Explanation |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in diag.decoupled_evidence_cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(item.case_id)}`",
                        str(item.mandatory),
                        f"`{item.category.value}`",
                        _cell(", ".join(item.passed_metrics)),
                        _cell(", ".join(item.failed_metrics)),
                        _cell(", ".join(item.retrieved_chunk_ids)),
                        _cell(item.explanation, max_len=140),
                    ]
                )
                + " |"
            )

    if diag.anomaly_highlights:
        lines.extend(
            [
                "",
                "### Anti-Masking & Disagreement Anomalies",
                "",
                "| Type | Severity | Scope | Case ID | Metrics | Explanation |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for flag in diag.anomaly_highlights:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{flag.anomaly_type.value}`",
                        f"`{flag.severity.value}`",
                        f"`{flag.scope.value}`",
                        f"`{_cell(flag.case_id)}`",
                        _cell(", ".join(flag.metric_ids)),
                        _cell(flag.explanation, max_len=140),
                    ]
                )
                + " |"
            )

    if diag.drift_highlights:
        lines.extend(
            [
                "",
                "### Cross-Version Provenance Drift Warnings",
                "",
                "| Category | Metric ID | Baseline | Candidate | Explanation |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for dw in diag.drift_highlights:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{dw.category.value}`",
                        f"`{_cell(dw.metric_id)}`",
                        _cell(dw.baseline_value, max_len=40),
                        _cell(dw.candidate_value, max_len=40),
                        _cell(dw.explanation, max_len=140),
                    ]
                )
                + " |"
            )

    if document.evaluation is not None:
        failing_cases = [
            rec
            for rec in document.evaluation.case_results
            if rec.execution.errors
            or any(
                m.status in {MetricStatus.FAIL, MetricStatus.INCONCLUSIVE}
                for m in rec.metrics.values()
            )
        ]
        if failing_cases:
            has_findings = True
            lines.extend(
                [
                    "",
                    "### Failed / Errored Case Highlights",
                    "",
                    "| Case ID | Mandatory | Failed/Inconclusive Metrics | "
                    "Errors | Output Preview |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for rec in failing_cases[:25]:
                bad_metrics = [
                    f"{mid}={m.status.value}"
                    for mid, m in sorted(rec.metrics.items())
                    if m.status in {MetricStatus.FAIL, MetricStatus.INCONCLUSIVE}
                ]
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{_cell(rec.case_id)}`",
                            str(rec.mandatory),
                            _cell(", ".join(bad_metrics)),
                            _cell("; ".join(rec.execution.errors), max_len=100),
                            _cell(rec.execution.output, max_len=100),
                        ]
                    )
                    + " |"
                )

    if not has_findings:
        lines.extend(
            ["Zero mandatory failures, anomalies, decoupling issues, or drift warnings.", ""]
        )
    else:
        lines.append("")
    return lines


def render_markdown(document: ReportDocument) -> str:
    """Render deterministic, secret-scrubbed Markdown with Three-Way Concern Separation."""
    header = [
        f"# {_cell(document.title)}",
        "",
        f"- **Schema Version**: `{document.schema_version}` | "
        f"**Kind**: `{document.report_kind.value}` | "
        f"**Generated (UTC)**: `{document.generated_at.isoformat()}`",
        "",
    ]
    sections = [
        *header,
        *_render_evaluation_section(document.evaluation, document.calibration),
        *_render_regression_section(document.comparison, document.trend),
        *_render_gate_section(document.gate, document),
        *_render_diagnostics_section(document),
    ]
    return "\n".join(sections).rstrip() + "\n"
