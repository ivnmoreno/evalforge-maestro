"""Pure library report builders and decoupled-evidence diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from evalforge_maestro._canonical import canonical_json_str, redact_secrets, scrub_secret_text
from evalforge_maestro.types import (
    CalibrationGateSummary,
    CalibrationReport,
    DecoupledEvidenceDiagnostic,
    DriftWarning,
    EvidenceDecouplingCategory,
    MetricStatus,
    QualityGateResult,
    ReportDiagnosticsSummary,
    ReportDocument,
    ReportKind,
    RunComparisonReport,
    RunRecord,
    TrendReport,
)

_RETRIEVAL_METRIC_IDS = frozenset(
    {
        "precision_at_k",
        "recall_at_k",
        "mrr",
        "ndcg_at_k",
        "hit_rate_at_k",
        "context_relevance",
    }
)
_ANSWER_SURFACE_METRIC_IDS = frozenset(
    {
        "exact_match",
        "normalized_match",
        "json_schema_validation",
        "answer_correctness",
        "answer_relevance",
    }
)
_ANSWER_OR_GROUNDING_METRIC_IDS = _ANSWER_SURFACE_METRIC_IDS | frozenset({"groundedness"})


def _scrub_json_tree(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_secret_text(value)
    if isinstance(value, Mapping):
        return {str(k): _scrub_json_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_json_tree(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_json_tree(item) for item in value]
    return value


def _deduplicate_drift(warnings: list[DriftWarning]) -> list[DriftWarning]:
    seen: set[tuple[str, str | None, str | None, str | None, str]] = set()
    unique: list[DriftWarning] = []
    for item in warnings:
        sig = (
            item.category.value,
            item.metric_id,
            item.baseline_run_id,
            item.candidate_run_id,
            item.explanation,
        )
        if sig not in seen:
            seen.add(sig)
            unique.append(item)
    return unique


def detect_decoupled_evidence(run: RunRecord) -> list[DecoupledEvidenceDiagnostic]:
    """Identify cases where retrieval evidence quality diverges from final answer or grounding."""
    diagnostics: list[DecoupledEvidenceDiagnostic] = []
    for case in run.case_results:
        retrieval_pass = [
            m_id
            for m_id, res in case.metrics.items()
            if m_id in _RETRIEVAL_METRIC_IDS and res.status == MetricStatus.PASS
        ]
        retrieval_or_grounding_fail = [
            m_id
            for m_id, res in case.metrics.items()
            if (m_id in _RETRIEVAL_METRIC_IDS or m_id == "groundedness")
            and res.status == MetricStatus.FAIL
        ]
        answer_pass = [
            m_id
            for m_id, res in case.metrics.items()
            if m_id in _ANSWER_SURFACE_METRIC_IDS and res.status == MetricStatus.PASS
        ]
        answer_or_grounding_fail = [
            m_id
            for m_id, res in case.metrics.items()
            if m_id in _ANSWER_OR_GROUNDING_METRIC_IDS and res.status == MetricStatus.FAIL
        ]
        retrieval_fail = [
            m_id
            for m_id, res in case.metrics.items()
            if m_id in _RETRIEVAL_METRIC_IDS and res.status == MetricStatus.FAIL
        ]
        chunk_ids = [chunk.id for chunk in case.execution.retrieved_chunks]

        if answer_pass and retrieval_or_grounding_fail:
            passed_list = ", ".join(sorted(answer_pass))
            failed_list = ", ".join(sorted(retrieval_or_grounding_fail))
            diagnostics.append(
                DecoupledEvidenceDiagnostic(
                    case_id=case.case_id,
                    mandatory=case.mandatory,
                    category=EvidenceDecouplingCategory.ANSWER_PASSED_RETRIEVAL_FAILED,
                    passed_metrics=sorted(answer_pass),
                    failed_metrics=sorted(retrieval_or_grounding_fail),
                    retrieved_chunk_ids=chunk_ids,
                    explanation=(
                        f"Case {case.case_id!r} passed answer metrics ({passed_list}) "
                        f"while retrieval/grounding failed ({failed_list})."
                    ),
                )
            )
        elif retrieval_pass and not retrieval_fail and answer_or_grounding_fail:
            passed_list = ", ".join(sorted(retrieval_pass))
            failed_list = ", ".join(sorted(answer_or_grounding_fail))
            diagnostics.append(
                DecoupledEvidenceDiagnostic(
                    case_id=case.case_id,
                    mandatory=case.mandatory,
                    category=EvidenceDecouplingCategory.RETRIEVAL_PASSED_ANSWER_FAILED,
                    passed_metrics=sorted(retrieval_pass),
                    failed_metrics=sorted(answer_or_grounding_fail),
                    retrieved_chunk_ids=chunk_ids,
                    explanation=(
                        f"Case {case.case_id!r} retrieved relevant context ({passed_list}) "
                        f"while answer/grounding failed ({failed_list})."
                    ),
                )
            )
    return diagnostics


def build_run_report(
    run: RunRecord,
    *,
    comparison: RunComparisonReport | None = None,
    trend: TrendReport | None = None,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a three-way-separated, secret-scrubbed ReportDocument for an evaluation RunRecord."""
    anomalies = (
        list(gate.anomalies)
        if gate is not None
        else (list(comparison.anomalies) if comparison is not None else [])
    )
    drift_pool: list[DriftWarning] = []
    if gate is not None:
        drift_pool.extend(gate.drift_warnings)
    if comparison is not None:
        drift_pool.extend(comparison.drift_warnings)
    if trend is not None:
        drift_pool.extend(trend.drift_warnings)

    diagnostics = ReportDiagnosticsSummary(
        mandatory_failed_case_ids=list(run.mandatory_failed_case_ids),
        decoupled_evidence_cases=detect_decoupled_evidence(run),
        anomaly_highlights=anomalies,
        drift_highlights=_deduplicate_drift(drift_pool),
    )
    resolved_title = title or f"Evaluation Report: {run.dataset_id} ({run.run_id})"
    return ReportDocument(
        report_kind=ReportKind.RUN,
        title=resolved_title,
        generated_at=datetime.now(timezone.utc),
        evaluation=run,
        comparison=comparison,
        trend=trend,
        gate=gate,
        diagnostics=diagnostics,
    )


def build_comparison_report(
    comparison: RunComparisonReport,
    *,
    candidate_run: RunRecord | None = None,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed pairwise comparison ReportDocument."""
    anomalies = list(gate.anomalies) if gate is not None else list(comparison.anomalies)
    drift_pool = list(gate.drift_warnings) if gate is not None else list(comparison.drift_warnings)
    mandatory_failed = list(candidate_run.mandatory_failed_case_ids) if candidate_run else []
    decoupled = detect_decoupled_evidence(candidate_run) if candidate_run else []

    diagnostics = ReportDiagnosticsSummary(
        mandatory_failed_case_ids=mandatory_failed,
        decoupled_evidence_cases=decoupled,
        anomaly_highlights=anomalies,
        drift_highlights=_deduplicate_drift(drift_pool),
    )
    resolved_title = (
        title or f"Comparison Report: {comparison.candidate_run_id} vs {comparison.baseline_run_id}"
    )
    return ReportDocument(
        report_kind=ReportKind.COMPARE,
        title=resolved_title,
        generated_at=datetime.now(timezone.utc),
        evaluation=candidate_run,
        comparison=comparison,
        gate=gate,
        diagnostics=diagnostics,
    )


def build_trend_report(
    trend: TrendReport,
    *,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed sliding-window trend ReportDocument."""
    anomalies = list(gate.anomalies) if gate is not None else []
    drift_pool = list(gate.drift_warnings) if gate is not None else list(trend.drift_warnings)
    diagnostics = ReportDiagnosticsSummary(
        anomaly_highlights=anomalies,
        drift_highlights=_deduplicate_drift(drift_pool),
    )
    resolved_title = title or f"Trend Report (window={trend.window})"
    return ReportDocument(
        report_kind=ReportKind.TREND,
        title=resolved_title,
        generated_at=datetime.now(timezone.utc),
        trend=trend,
        gate=gate,
        diagnostics=diagnostics,
    )


def build_calibration_report(
    calibration: CalibrationReport,
    *,
    min_agreement: float | None = None,
    strict: bool = False,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed judge calibration ReportDocument with optional threshold gate."""
    observed = calibration.exact_agreement_rate
    if calibration.valid_cases == 0:
        passed = not (strict or min_agreement is not None)
        reason = (
            "Calibration yielded 0 valid human-judge pairs; inconclusive."
            if not passed
            else "Calibration yielded 0 valid pairs in diagnostic mode (--strict disabled)."
        )
    elif min_agreement is not None and (observed is None or observed < min_agreement - 1e-9):
        passed = False
        reason = (
            f"Observed exact agreement {observed}% is below configured minimum {min_agreement}%."
        )
    elif strict and calibration.inconclusive_cases > 0:
        passed = False
        reason = (
            f"Calibration encountered {calibration.inconclusive_cases} inconclusive sample(s) "
            "under --strict mode."
        )
    else:
        passed = True
        reason = (
            f"Calibration passed with {observed}% exact agreement (min_agreement={min_agreement}%)."
            if min_agreement is not None
            else f"Diagnostic calibration completed ({observed}% exact agreement)."
        )

    cal_gate = CalibrationGateSummary(
        min_agreement=min_agreement,
        observed_agreement=observed,
        strict=strict,
        valid_cases=calibration.valid_cases,
        inconclusive_cases=calibration.inconclusive_cases,
        passed=passed,
        reason=reason,
    )
    resolved_title = title or f"Judge Calibration Report: {calibration.metric_id}"
    return ReportDocument(
        report_kind=ReportKind.CALIBRATE,
        title=resolved_title,
        generated_at=datetime.now(timezone.utc),
        calibration=calibration,
        calibration_gate=cal_gate,
    )


def render_report_json(document: ReportDocument, *, pretty: bool = False) -> str:
    """Serialize a secret-redacted, schema-validated ReportDocument to canonical JSON."""
    payload = redact_secrets(document.model_dump(mode="json"))
    scrubbed = _scrub_json_tree(payload)
    return canonical_json_str(scrubbed, pretty=pretty)
