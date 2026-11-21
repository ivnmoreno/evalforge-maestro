"""Unit tests for EvalForgeService application routing, auth, limits, bind policy, and HTTP."""

from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.exceptions import LocalOnlyPolicyError
from evalforge_maestro.service import (
    ServiceApplication,
    create_http_server,
    validate_service_bind_policy,
)
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    CaseQueryPayload,
    EvaluationCase,
    ExecutionResult,
    IndexedMetricPoint,
    JudgeConfig,
    MetricSpecConfig,
    MetricStatus,
    RunQueryPayload,
    RunRecord,
    ServiceCompareResponse,
    ServiceConfig,
    ServiceErrorResponse,
    ServiceEvaluateRequest,
    ServiceEvaluateResponse,
    ServiceHealthResponse,
    ServiceOtelIngestResponse,
    ServiceReportResponse,
    SQLiteIndexStatus,
)


def _json_req(
    app: ServiceApplication,
    method: str,
    path: str,
    payload: dict[str, Any] | list[Any] | None = None,
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    status, _, body = app.handle_request(method, path, body=raw, headers=headers)
    return status, json.loads(body.decode("utf-8"))


def test_us1_service_application_routes_delegation_and_security(tmp_path: Path) -> None:
    root = tmp_path / ".evalforge"
    cfg = ServiceConfig(
        storage_dir=str(root),
        mock_mode=True,
        local_only=True,
        block_pii=False,
    )
    app = ServiceApplication(cfg)

    # 1) Health & index lifecycle on empty store
    st, health_raw = _json_req(app, "GET", "/health")
    assert st == 200
    health = ServiceHealthResponse.model_validate(health_raw)
    assert health.status == "ok" and health.canonical_run_count == 0

    st, idx_raw = _json_req(app, "GET", "/v1/index/status")
    assert st == 200
    assert SQLiteIndexStatus.model_validate(idx_raw).in_sync is True

    # 2) Stateless evaluation (persist=False) -> nothing written to store
    c1 = EvaluationCase(id="c1", input="SLA?", reference="99.9%")
    ex1 = ExecutionResult(case_id="c1", input="SLA?", output="99.9%", elapsed_seconds=0.05)
    st, eval_stateless_raw = _json_req(
        app,
        "POST",
        "/v1/evaluate",
        {
            "cases": [c1.model_dump(mode="json")],
            "executions": [ex1.model_dump(mode="json")],
            "metrics": [{"metric_id": "exact_match"}],
            "include_markdown": True,
            "persist": False,
        },
    )
    assert st == 200
    eval_stateless = ServiceEvaluateResponse.model_validate(eval_stateless_raw)
    assert eval_stateless.persisted is False
    assert eval_stateless.evaluation.aggregates["exact_match"].mean_score == 1.0
    assert eval_stateless.markdown is not None and "## Evaluation" in eval_stateless.markdown
    assert not (root / "runs").exists()

    # 3) Persistent evaluation (persist=True) over OTel spans + duplicate run_id -> 409
    otlp = {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [
                    {
                        "scope": {"name": "svc.test"},
                        "spans": [
                            {
                                "traceId": "01" * 16,
                                "spanId": "02" * 8,
                                "name": "agent",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000000200000000",
                                "attributes": [
                                    {"key": "evalforge.case_id", "value": {"stringValue": "c1"}},
                                    {"key": "input.value", "value": {"stringValue": "SLA?"}},
                                    {"key": "output.value", "value": {"stringValue": "99.9%"}},
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    st, ingest_raw = _json_req(app, "POST", "/v1/otel/ingest", {"payload": otlp})
    assert st == 200
    assert ServiceOtelIngestResponse.model_validate(ingest_raw).count == 1

    st, run1_raw = _json_req(
        app,
        "POST",
        "/v1/evaluate",
        {
            "cases": [c1.model_dump(mode="json")],
            "otel_payload": otlp,
            "metrics": [{"metric_id": "exact_match"}, {"metric_id": "groundedness"}],
            "dataset_id": "svc-ds",
            "run_id": "svc-run-1",
            "persist": True,
        },
    )
    assert st == 200
    r1 = ServiceEvaluateResponse.model_validate(run1_raw)
    assert r1.persisted is True and r1.evaluation.run_id == "svc-run-1"

    st, dup_raw = _json_req(
        app,
        "POST",
        "/v1/evaluate",
        {
            "cases": [c1.model_dump(mode="json")],
            "executions": [ex1.model_dump(mode="json")],
            "metrics": [{"metric_id": "exact_match"}],
            "dataset_id": "svc-ds",
            "run_id": "svc-run-1",
            "persist": True,
        },
    )
    assert st == 409
    assert ServiceErrorResponse.model_validate(dup_raw).status_code == 409

    # Pin baseline and create candidate run for /v1/compare, /v1/runs, /v1/cases, /v1/reports
    LocalRunStore(root).pin_baseline("svc-run-1", name="main")
    st, _ = _json_req(
        app,
        "POST",
        "/v1/evaluate",
        {
            "cases": [c1.model_dump(mode="json")],
            "executions": [
                ExecutionResult(
                    case_id="c1", input="SLA?", output="99.9%", elapsed_seconds=0.05
                ).model_dump(mode="json")
            ],
            "metrics": [{"metric_id": "exact_match"}, {"metric_id": "groundedness"}],
            "dataset_id": "svc-ds",
            "run_id": "svc-run-2",
            "persist": True,
        },
    )
    assert st == 200

    st, runs_raw = _json_req(app, "GET", "/v1/runs?dataset_id=svc-ds&metric_id=exact_match")
    assert st == 200
    assert RunQueryPayload.model_validate(runs_raw).total_returned == 2

    st, single_raw = _json_req(app, "GET", "/v1/runs/svc-run-1")
    assert st == 200
    assert RunRecord.model_validate(single_raw).run_id == "svc-run-1"

    st, cases_raw = _json_req(app, "GET", "/v1/cases?run_id=svc-run-1&status=PASS")
    assert st == 200
    cq = CaseQueryPayload.model_validate(cases_raw)
    assert cq.total_returned >= 1 and cq.cases[0].status == MetricStatus.PASS

    st, bases_raw = _json_req(app, "GET", "/v1/baselines")
    assert st == 200 and "main" in bases_raw["baselines"]

    st, hist_raw = _json_req(app, "GET", "/v1/metrics/exact_match/history?dataset_id=svc-ds")
    assert st == 200
    assert len([IndexedMetricPoint.model_validate(p) for p in hist_raw]) == 2

    st, rebuild_raw = _json_req(app, "POST", "/v1/index/rebuild", {})
    assert st == 200 and SQLiteIndexStatus.model_validate(rebuild_raw).in_sync is True

    st, sync_raw = _json_req(app, "POST", "/v1/index/sync", {})
    assert st == 200 and SQLiteIndexStatus.model_validate(sync_raw).in_sync is True

    st, cmp_raw = _json_req(
        app,
        "POST",
        "/v1/compare",
        {
            "candidate_run_id": "svc-run-2",
            "baseline_ref": "main",
            "include_markdown": True,
        },
    )
    assert st == 200
    cmp_resp = ServiceCompareResponse.model_validate(cmp_raw)
    assert cmp_resp.comparison.candidate_run_id == "svc-run-2"
    assert cmp_resp.markdown is not None

    for rep_body in (
        {"run_id": "svc-run-2", "baseline_ref": "main"},
        {"compare_run_id": "svc-run-2", "baseline_ref": "main"},
        {"trend_window": 2, "dataset_id": "svc-ds"},
    ):
        st, rep_raw = _json_req(app, "POST", "/v1/reports", rep_body)
        assert st == 200
        assert ServiceReportResponse.model_validate(rep_raw).markdown

    # Security & error mapping checks: path traversal, local-only violation, 404, 405
    st, bad_id_raw = _json_req(app, "GET", "/v1/runs/..%2Fsecret")
    assert st == 400 and ServiceErrorResponse.model_validate(bad_id_raw).status_code == 400

    st, not_found_raw = _json_req(app, "GET", "/v1/runs/nonexistent-run")
    assert st == 404 and ServiceErrorResponse.model_validate(not_found_raw).status_code == 404

    st, unk_raw = _json_req(app, "GET", "/v1/does-not-exist")
    assert st == 404 and ServiceErrorResponse.model_validate(unk_raw).status_code == 404

    st, mna_raw = _json_req(app, "POST", "/health", {})
    assert st == 405 and ServiceErrorResponse.model_validate(mna_raw).status_code == 405

    req_remote_judge = ServiceEvaluateRequest(
        cases=[c1],
        executions=[ex1],
        metrics=[MetricSpecConfig(metric_id="groundedness")],
        judge=JudgeConfig(
            model="openai/gpt-4o",
            api_base="https://api.openai.com/v1",
            local_only=True,
            mock_mode=False,
        ),
    )
    st, blocked_raw = _json_req(
        ServiceApplication(ServiceConfig(storage_dir=str(root), local_only=True, mock_mode=False)),
        "POST",
        "/v1/evaluate",
        req_remote_judge.model_dump(mode="json"),
    )
    assert st == 403
    assert ServiceErrorResponse.model_validate(blocked_raw).error_type == "LocalOnlyPolicyError"


def test_us2_service_auth_limits_bind_policy_and_socketpair_handler(tmp_path: Path) -> None:
    root = tmp_path / ".evalforge"
    cfg_loop = ServiceConfig(host="127.0.0.1", port=0, storage_dir=str(root), mock_mode=True)
    validate_service_bind_policy(cfg_loop, auth_token=None)

    cfg_remote = ServiceConfig(host="0.0.0.0", port=8787, storage_dir=str(root))
    with pytest.raises(LocalOnlyPolicyError, match="auth_token"):
        validate_service_bind_policy(cfg_remote, auth_token=None)
    validate_service_bind_policy(cfg_remote, auth_token="strong-secret-token")

    secret = "tok-svc-auth-123"
    limited_cfg = ServiceConfig(
        host="127.0.0.1",
        port=0,
        storage_dir=str(root),
        mock_mode=True,
        max_request_bytes=1024,
        auth_token_configured=True,
    )
    app = ServiceApplication(limited_cfg, auth_token=secret)

    # Auth enforcement
    st, err = _json_req(app, "GET", "/health")
    assert st == 401 and ServiceErrorResponse.model_validate(err).status_code == 401
    st, _ = _json_req(app, "GET", "/health", token="wrong-secret")
    assert st == 401
    st, ok_health = _json_req(app, "GET", "/health", token=secret)
    assert st == 200 and ok_health["status"] == "ok"

    # Body size limit 413
    st_big, _, body_big = app.handle_request(
        "POST",
        "/v1/otel/ingest",
        body=b"{" + b" " * 2048 + b"}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert st_big == 413 and json.loads(body_big.decode("utf-8"))["status_code"] == 413

    # Exercise live EvalRequestHandler over hermetic socket.socketpair() without relaxing conftest
    server = create_http_server(limited_cfg, auth_token=secret)
    handler_cls = server.RequestHandlerClass
    try:
        server_sock, client_sock = socket.socketpair()
        with client_sock:
            client_sock.settimeout(2.0)
            with server_sock:
                client_sock.sendall(
                    (
                        f"GET /health HTTP/1.1\r\n"
                        f"Host: localhost\r\n"
                        f"Authorization: Bearer {secret}\r\n"
                        f"Connection: close\r\n\r\n"
                    ).encode("ascii")
                )
                client_sock.shutdown(socket.SHUT_WR)
                handler_cls(server_sock, ("127.0.0.1", 0), server)
            resp_bytes = b""
            while chunk := client_sock.recv(4096):
                resp_bytes += chunk
            raw_head, raw_body = resp_bytes.split(b"\r\n\r\n", 1)
            assert b"200 OK" in raw_head
            parsed = json.loads(raw_body.decode("utf-8"))
            assert ServiceHealthResponse.model_validate(parsed).status == "ok"

        # Verify POST Content-Length > max_request_bytes returns HTTP 413 cleanly over HTTP handler
        server_sock2, client_sock2 = socket.socketpair()
        with client_sock2:
            client_sock2.settimeout(2.0)
            with server_sock2:
                oversize_body = json.dumps({"pad": "x" * 1500}).encode("utf-8")
                client_sock2.sendall(
                    (
                        f"POST /v1/otel/ingest HTTP/1.1\r\n"
                        f"Host: localhost\r\n"
                        f"Authorization: Bearer {secret}\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(oversize_body)}\r\n"
                        f"Connection: close\r\n\r\n"
                    ).encode("ascii")
                    + oversize_body
                )
                client_sock2.shutdown(socket.SHUT_WR)
                handler_cls(server_sock2, ("127.0.0.1", 0), server)
            resp2 = b""
            while chunk := client_sock2.recv(4096):
                resp2 += chunk
            assert b"413" in resp2.split(b"\r\n", 1)[0]
    finally:
        server.server_close()

    # Clean unused import check for http.client (or use http.client.HTTPStatus check)
    assert http.client.OK == 200
