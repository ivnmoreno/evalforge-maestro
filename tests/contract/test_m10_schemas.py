"""Contract tests pinning Feature 010 Remote Evaluation Service Pydantic v2 schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evalforge_maestro.types import (
    SCHEMA_VERSION,
    EvaluationCase,
    ExecutionResult,
    GateDecision,
    MetricSpecConfig,
    QualityGateResult,
    ReportDocument,
    ReportKind,
    RunRecord,
    ServiceCompareRequest,
    ServiceConfig,
    ServiceErrorResponse,
    ServiceEvaluateRequest,
    ServiceHealthResponse,
    ServiceOtelIngestRequest,
    ServiceOtelIngestResponse,
    ServiceReportRequest,
    ServiceReportResponse,
)


def test_m10_service_config_and_error_contracts() -> None:
    cfg = ServiceConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8787
    assert cfg.local_only is True
    assert cfg.auth_token_configured is False
    assert cfg.max_request_bytes == 10_485_760

    with pytest.raises(ValidationError):
        ServiceConfig(port=True)

    with pytest.raises(ValidationError):
        ServiceConfig(port=70000)

    with pytest.raises(ValidationError):
        ServiceConfig(max_request_bytes=128)

    err = ServiceErrorResponse(
        status_code=401,
        error_type="UnauthorizedError",
        message="Invalid token sk-secret-99999999",
        hint="Supply Bearer tok-secret sk-another-99999999",
    )
    assert err.schema_version == SCHEMA_VERSION
    assert "sk-secret-99999999" not in err.message
    assert "sk-another-99999999" not in (err.hint or "")

    health = ServiceHealthResponse(
        package_version="0.2.1",
        storage_dir=".evalforge",
        local_only=True,
        mock_mode=True,
        indexed_run_count=2,
        canonical_run_count=2,
    )
    assert health.status == "ok"


def test_m10_service_request_and_response_contracts() -> None:
    c1 = EvaluationCase(id="c-1", input="Hi", reference="Hello")
    ex1 = ExecutionResult(case_id="c-1", input="Hi", output="Hello", elapsed_seconds=0.1)

    req = ServiceEvaluateRequest(
        cases=[c1],
        executions=[ex1],
        metrics=[MetricSpecConfig(metric_id="exact_match")],
    )
    assert req.persist is False
    assert req.max_concurrency == 4

    with pytest.raises(ValidationError):
        ServiceEvaluateRequest(cases=[], executions=[ex1])

    with pytest.raises(ValidationError):
        ServiceEvaluateRequest(cases=[c1])  # neither executions nor otel_payload

    with pytest.raises(ValidationError):
        ServiceEvaluateRequest(cases=[c1], executions=[ex1], otel_payload=[])  # both set

    with pytest.raises(ValidationError):
        ServiceEvaluateRequest(cases=[c1], executions=[ex1], max_concurrency=True)

    ingest_req = ServiceOtelIngestRequest(payload=[{"trace_id": "t1", "span_id": "s1"}])
    ingest_resp = ServiceOtelIngestResponse(count=1, executions=[ex1])
    assert ingest_req.payload
    assert ingest_resp.schema_version == SCHEMA_VERSION

    cmp_req = ServiceCompareRequest(candidate_run_id="r2", baseline_ref="main")
    assert cmp_req.baseline_ref == "main"
    with pytest.raises(ValidationError):
        ServiceCompareRequest(baseline_ref="main")

    rep_req = ServiceReportRequest(run_id="r2")
    assert rep_req.include_markdown is True
    with pytest.raises(ValidationError):
        ServiceReportRequest()  # needs run_id, compare_run_id, or trend_window

    with pytest.raises(ValidationError):
        ServiceReportRequest(trend_window=1)

    # Unused imports smoke check cleanly
    assert RunRecord is not None
    assert QualityGateResult is not None
    assert ReportDocument is not None
    assert ReportKind.RUN.value == "run"
    assert ServiceReportResponse is not None
    assert GateDecision is not None
