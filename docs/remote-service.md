# Remote Evaluation Service Guide (`evalforge-maestro serve`)

`evalforge-maestro` provides an optional, zero-dependency HTTP service layer (`evalforge_maestro.service` and CLI `evalforge-maestro serve`) that exposes canonical storage queries, SQLite index lifecycle operations, OpenTelemetry trace ingestion, offline/trace evaluation, regression comparisons, and report generation over a typed JSON API.

By architectural design, the HTTP layer sits strictly **outside** the core evaluation engine—library users never pay import-time costs for `http.server` or network transport unless they explicitly invoke `evalforge_maestro.service` or `evalforge-maestro serve`.

---

## 1. Architecture & Library-Purity Boundary

| Component | Module | Responsibility & Isolation Guarantees |
| --- | --- | --- |
| **Transport-Agnostic Router** | `evalforge_maestro.service.app` (`ServiceApplication`) | Validates Bearer credentials (`hmac.compare_digest`), enforces `max_request_bytes`, parses routes/query params, and delegates strictly to core SDK/storage (`LocalRunStore`, `SQLiteRunIndex`, `ReplayAdapter`, `ingest_otel_spans`, `EvaluationOrchestrator`, `compare_runs`, `compare_run_cohorts`, `analyze_trend`, `QualityGate`, `reporting`). Imports **no** `http.server` or live target adapters (`DocpipeAdapter`, `RAGAdapter`, `AgentAdapter`). |
| **Lazy Stdlib HTTP Server** | `evalforge_maestro.service.server` (`create_http_server`, `serve_http`) | Lazily imports Python stdlib `http.server.ThreadingHTTPServer` and `BaseHTTPRequestHandler` (HTTP/1.1) only inside function calls. Enforces `Content-Length` pre-read limits and daemon worker threads. |
| **Core Library Subsystems** | `metrics`, `regression`, `execution`, `storage`, `judges`, `embeddings`, `datasets`, `reporting` | Prohibited by AST tests (`tests/test_library_purity.py`) from importing `evalforge_maestro.service`, `http.server`, or `socketserver`. |
| **Cold-Start CLI (`--help`)** | `evalforge_maestro.cli.parser`, `evalforge_maestro.__init__` | Top-level package exports `ServiceApplication` lazily via `__getattr__`, keeping `http.server`, `socketserver`, and `evalforge_maestro.service` unloaded during `import evalforge_maestro` and `evalforge-maestro --help`. |

> **Scope Boundary**: The service intentionally evaluates pre-captured `ExecutionResult` traces (`executions`) or OpenTelemetry span payloads (`otel_payload`) via `ReplayAdapter` rather than executing arbitrary live Python callables over HTTP. Live target execution stays in local Python/CLI workflows.

---

## 2. Security & Privacy Posture

1. **Loopback Default & Pre-Bind Remote Authentication Guard (`validate_service_bind_policy`)**:
   - Default host is `127.0.0.1` on port `8787` (`ServiceConfig.host`, `ServiceConfig.port`).
   - Binding to any non-loopback host (anything other than `127.0.0.1`, `localhost`, `::1`, or `[::1]`) **without** a non-empty `auth_token` / `EVALFORGE_SERVICE_TOKEN` raises `LocalOnlyPolicyError` **before** opening a listening socket (CLI POSIX exit code `4`).
2. **Constant-Time Bearer Authentication**:
   - When configured with an `auth_token`, every request (including `GET /health`) must supply `Authorization: Bearer <token>`.
   - Tokens are compared in constant time via `hmac.compare_digest`. Missing or invalid headers return `HTTP 401` (`UnauthorizedError`).
3. **Safe-by-Default Locality (`local_only=True`)**:
   - `evalforge-maestro serve` and `ServiceConfig` default to `local_only=True`, blocking outbound non-loopback judge or embedding API calls inside `POST /v1/evaluate` (`HTTP 403` `LocalOnlyPolicyError`).
   - Passing `--allow-remote-judges` (CLI) or constructing `ServiceConfig(local_only=False)` opts into remote provider calls. Note that per-request `ServiceEvaluateRequest.judge.local_only` / `embedding.local_only` cannot downgrade a server configured with `local_only=True`.
4. **Opt-In Pre-Network PII & Secret Scanning (`block_pii=True`)**:
   - Enabling `--block-pii` (or `ServiceConfig(block_pii=True)`) scans non-mock dataset/execution payloads before calling remote non-loopback judges or embedding endpoints, returning `HTTP 403` on detection.
5. **Request Payload Bounds (`HTTP 413`)**:
   - `ServiceConfig.max_request_bytes` defaults to `10_485_760` (10 MiB; valid range `1024`–`104_857_600` bytes).
   - Both `evalforge.service.server` (`Content-Length` pre-check with `Connection: close`) and `ServiceApplication.handle_request` (buffered body length check) reject oversized requests with `HTTP 413` (`PayloadTooLargeError`).
6. **Path-Traversal Hardening & Secret Scrubbing**:
   - Path parameters (`/v1/runs/{run_id}`) reject `..`, slashes, whitespace, and invalid characters via `_validate_safe_identifier` (`HTTP 400`).
   - All JSON responses set `Cache-Control: no-store` and scrub secret/token strings via `redact_secrets` and `scrub_secret_text`. Access logs emitted by `_EvalRequestHandler` scrub URLs/messages via Python `logging` (`NullHandler` by default in library code; `stderr` only in CLI).

### 2.1 Deployment Boundary & External Exposure

`evalforge-maestro serve` (`ThreadingHTTPServer`) is intentionally scoped for **local development, internal CI runners, and trusted loopback/internal integration**—not as a standalone public edge server. Specifically, the built-in stdlib server provides **no TLS termination, no rate limiting, no bounded worker thread pool, and no per-connection socket timeouts**.

```text
External Client
   │  HTTPS (TLS), rate limiting, edge auth, request timeouts
   ▼
Reverse Proxy / API Gateway (Nginx, Caddy, Envoy, Cloud ALB)
   │  Internal HTTP + Bearer token + max_request_bytes
   ▼
EvalForge HTTP Service (`evalforge-maestro serve`)
   │  OR embed `ServiceApplication` directly inside FastAPI / Starlette / Gunicorn+Uvicorn
   ▼
Evaluation Engine & Canonical Storage (`.evalforge/`)
```

For any deployment exposed beyond localhost or trusted internal networks, either **terminate TLS, enforce rate limits, and apply connection timeouts at an upstream reverse proxy / API gateway**, or **mount the transport-agnostic `ServiceApplication` directly inside a production ASGI/WSGI server** (see [Section 5.2](#52-embedding-serviceapplication-in-process-zero-extra-web-frameworks-needed--or-mountable-in-asgiwsgi)).

---

## 3. CLI Usage (`evalforge-maestro serve`)

```bash
# 1. Start local loopback service with deterministic mock judges (default local_only=True)
evalforge-maestro serve --storage-dir .evalforge --mock --log-level INFO

# 2. Bind to all interfaces with Bearer auth + SQLite/JSON storage + PII protection
export EVALFORGE_SERVICE_TOKEN="replace-with-strong-random-token"
export EVALFORGE_JUDGE_API_KEY="sk-..."
evalforge-maestro serve \
  --host 0.0.0.0 \
  --port 8787 \
  --storage-dir /var/lib/evalforge \
  --allow-remote-judges \
  --block-pii \
  --log-level INFO \
  --log-json
```

### `serve` Flags

| Flag | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address. Non-loopback hosts require `--auth-token` or `EVALFORGE_SERVICE_TOKEN` (else exit code `4`). |
| `--port` | `8787` | TCP listen port (`0..65535`). |
| `--auth-token` | `None` (env: `EVALFORGE_SERVICE_TOKEN`) | Bearer secret required on every HTTP request when configured. |
| `--max-request-bytes` | `10485760` (10 MiB) | Maximum request size in bytes (`1024..104857600`). |
| `--local-only` | `True` (default for `serve`) | Enforce loopback-only judge/embedding endpoints pre-network. Cannot be combined with `--allow-remote-judges` (exit code `2`). |
| `--allow-remote-judges` | `False` | Permit outbound non-loopback judge/embedding endpoints when requested by `/v1/evaluate`. |
| `--block-pii` | `False` (or config/env) | Reject outbound non-mock remote judge/embedding payloads containing PII or secrets. |
| `--mock` | `False` (or config/env) | Score judge and embedding metrics deterministically offline without API keys or network calls. |
| `--storage-dir`, `--config`, `--env-file`, `--log-level`, `--log-json`, `--json`, `--quiet` | Global defaults | Standard 5-tier config flags. Diagnostic startup/request logs go strictly to `stderr`. |

> **Credential Env Vars**: Server-held `EVALFORGE_JUDGE_API_KEY` and `EVALFORGE_EMBEDDING_API_KEY` are supplied to the server process at startup and never transmitted in JSON responses, error payloads, or `ServiceConfig` (which exposes only boolean `auth_token_configured`).

---

## 4. Complete HTTP API Reference

All endpoints accept and emit UTF-8 JSON (`Content-Type: application/json; charset=utf-8`).

| Method | Path | Response Model / Type | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | `ServiceHealthResponse` | Service liveness, package version, security flags (`local_only`, `mock_mode`), `indexed_run_count`, and `canonical_run_count`. |
| `GET` | `/v1/index/status` | `SQLiteIndexStatus` | Non-mutating parity check comparing `.evalforge/index.sqlite3` against canonical JSON runs & baselines. |
| `POST` | `/v1/index/rebuild` | `SQLiteIndexStatus` | Atomically reconstructs `.evalforge/index.sqlite3` strictly from `.evalforge/runs/*.json`, `manifest.jsonl`, and `baselines.json`. |
| `POST` | `/v1/index/sync` | `SQLiteIndexStatus` | Incrementally indexes newly committed runs and baseline changes (auto-rebuilds if DB missing/corrupt). |
| `GET` | `/v1/runs` | `RunQueryPayload` | Filterable indexed run listing (`SQLiteRunIndex.query_runs`). |
| `GET` | `/v1/runs/{run_id}` | `RunRecord` | Load full canonical immutable run record (including per-case trace/retrieved chunks) directly from JSON store. |
| `GET` | `/v1/cases` | `CaseQueryPayload` | Filterable per-case metric row search (`SQLiteRunIndex.query_cases`). |
| `GET` | `/v1/baselines` | `BaselineRegistry` | List pinned baseline aliases (`main`, `default`, etc.) from `.evalforge/baselines.json`. |
| `GET` | `/v1/metrics/{metric_id}/history` | `list[IndexedMetricPoint]` | Chronological aggregate mean-score series for one metric (`SQLiteRunIndex.metric_history`). |
| `POST` | `/v1/otel/ingest` | `ServiceOtelIngestResponse` | Normalize OTLP JSON, flat span arrays, or JSONL span exports into secret-scrubbed `ExecutionResult` records. |
| `POST` | `/v1/evaluate` | `ServiceEvaluateResponse` | Score `cases` against `executions` **or** `otel_payload`, evaluate `QualityGate`, build `ReportDocument`, and optionally render Markdown. |
| `POST` | `/v1/compare` | `ServiceCompareResponse` | Run pairwise (`compare_runs`) or statistical cohort (`compare_run_cohorts`) regression comparison against a baseline alias or run ID cohort. |
| `POST` | `/v1/reports` | `ServiceReportResponse` | Render Three-Way JSON/Markdown reports for a stored `run_id`, pairwise `compare_run_id`, or `trend_window >= 2`. |

### 4.1 Query Parameters on Read Endpoints

- **`GET /v1/runs`**:
  - `dataset_id`, `dataset_version`, `model_id`, `system_version`, `baseline`, `metric_id`: exact string filters.
  - `run_id` (repeatable): restrict to matching run IDs (`?run_id=r1&run_id=r2`).
  - `min_score`, `max_score` (`float`): inclusive mean-score bounds when `metric_id` is supplied.
  - `has_mandatory_failures` (`true`/`false`), `since`, `until` (UTC ISO-8601).
  - `order_by` (`timestamp_desc` | `timestamp_asc` | `run_id_asc`, default `timestamp_desc`), `limit` (default `50`), `offset` (default `0`), `auto_sync` (default `true`).
- **`GET /v1/cases`**:
  - `run_id`, `dataset_id`, `case_id`, `metric_id`.
  - `status` (`PASS` | `FAIL` | `WARNING` | `INCONCLUSIVE` | `NOT_APPLICABLE`).
  - `mandatory_only`, `has_errors`, `has_anomaly_flags` (`true`/`false`), `min_score`, `max_score`, `limit` (default `100`), `offset` (default `0`), `auto_sync` (default `true`).
- **`GET /v1/metrics/{metric_id}/history`**:
  - `dataset_id`, `model_id`, `system_version`, `limit` (default `50`).

### 4.2 Request Contract Highlights (`POST` Payloads)

- **`POST /v1/evaluate` (`ServiceEvaluateRequest`)**:
  - `cases` (non-empty `list[EvaluationCase]`) and **exactly one** of `executions` (`list[ExecutionResult]`) or `otel_payload` (any OTLP dict, list of spans, or NDJSON span structure; optionally paired with `otel_extractors` and `case_id_map`).
  - `metrics`: `list[MetricSpecConfig]` (defaults to `[{"metric_id": "exact_match"}]`).
  - Optional non-secret `judge: JudgeConfig` (`model`, `api_base`, `temperature`, `pass_threshold`, `mock_mode`, `local_only`, `max_retries`, `timeout_seconds`) and `embedding: EmbeddingConfig` (strictly isolated from judge settings; secrets remain server-side).
  - `persist` (`bool`, default `false`):
    - When `persist=False`, orchestrator runs inside an ephemeral `TemporaryDirectory` so `.evalforge/runs/` and `manifest.jsonl` remain untouched.
    - When `persist=True`, `LocalRunStore` atomically writes `.evalforge/runs/<run_id>.json` + appends `manifest.jsonl` (`0o700`/`0o600`), syncs `.evalforge/index.sqlite3` if the index already exists on disk, and rejects an already-existing `run_id` with `HTTP 409 Conflict` (`ImmutabilityError`).
  - `include_markdown` (`bool`, default `false`): includes rendered Three-Way Markdown string on `ServiceEvaluateResponse.markdown`.
- **`POST /v1/compare` (`ServiceCompareRequest`)**:
  - Requires `candidate_run_id` or non-empty `candidate_run_ids`, paired with `baseline_ref` (alias or run ID, default `"default"`) and/or `baseline_run_ids`, plus optional `policy: QualityGatePolicy` and `include_markdown`.
- **`POST /v1/reports` (`ServiceReportRequest`)**:
  - Supply `run_id` (with optional `baseline_ref`), `compare_run_id` (with optional `baseline_ref`), or `trend_window >= 2` (with optional `dataset_id`, `model_id`, `title`, and `include_markdown` defaulting to `true`).

### 4.3 HTTP Error Mapping (`ServiceErrorResponse`)

All non-2xx responses validate against `ServiceErrorResponse` (`schema_version`, `status_code`, `error_type`, scrubbed `message`, optional `hint`):

| HTTP Status | Triggering Conditions / Exceptions |
| --- | --- |
| `400 Bad Request` | Malformed JSON, `ValidationError`, invalid query types/timestamps, `ConfigurationError`, `DatasetError`, `AdapterError`, `MetricError`, invalid identifier (`..` / `/`), non-404 `StorageError`. |
| `401 Unauthorized` | Missing or non-matching `Authorization: Bearer <token>` header when `auth_token` is configured. |
| `403 Forbidden` | `LocalOnlyPolicyError` (blocked remote judge/embedding endpoint or outbound PII/secret detection under `--block-pii`). |
| `404 Not Found` | Unknown URL route or `StorageError` indicating missing run/baseline (`"not found"`). |
| `405 Method Not Allowed` | Unsupported HTTP verb (`PUT`/`DELETE`, or `GET` on `POST` route / `POST` on `GET` route). |
| `409 Conflict` | `ImmutabilityError` (attempting `POST /v1/evaluate` with `persist=True` and an existing `run_id`). |
| `413 Payload Too Large` | Request body or `Content-Length` header exceeds `ServiceConfig.max_request_bytes`. |
| `500 Internal Server Error` | Unhandled `ExecutionError`, `JudgeError`, or unexpected runtime fault (never leaks secrets or raw stack traces). |
| `503 Service Unavailable` | `MissingExtraError` (e.g., request requires `[judges]` or `[embeddings]` optional extra without `mock_mode=True`). |

---

## 5. End-to-End Examples

### 5.1 `curl` Workflow (Health -> Persist Evaluate -> Query Runs)

```bash
export TOKEN="demo-local-token"
evalforge-maestro serve --storage-dir /tmp/ef-svc --auth-token "$TOKEN" --mock --log-level INFO &
SVC_PID=$!

# 1. Health check
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/health | python -m json.tool

# 2. Persistent evaluation over inline cases & executions
curl -sS -X POST http://127.0.0.1:8787/v1/evaluate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "svc-demo-1",
    "dataset_id": "support-qa",
    "persist": true,
    "include_markdown": true,
    "cases": [
      {"id": "c1", "input": "Uptime SLA?", "reference": "99.9%", "expected_context": ["doc-sla"], "criteria": {"mandatory": true}}
    ],
    "executions": [
      {"case_id": "c1", "input": "Uptime SLA?", "output": "99.9%", "retrieved_chunks": [{"id": "doc-sla", "text": "99.9% monthly uptime SLA", "rank": 1}], "elapsed_seconds": 0.02}
    ],
    "metrics": [{"metric_id": "exact_match"}, {"metric_id": "precision_at_k", "params": {"k": 1}}, {"metric_id": "groundedness"}]
  }' | python -m json.tool

# 3. Query indexed runs via SQLite-backed endpoint
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8787/v1/runs?dataset_id=support-qa&metric_id=exact_match" | python -m json.tool

kill "$SVC_PID"
```

### 5.2 Embedding `ServiceApplication` In-Process (Zero Extra Web Frameworks Needed — or Mountable in ASGI/WSGI)

Because `ServiceApplication` only consumes `(method, raw_path, *, body=b"", headers=None)` and returns `(status_code, response_headers, json_bytes)`, you can run it inside hermetic tests or wrap it in any production WSGI/ASGI framework (FastAPI, Starlette, Flask, AWS Lambda) without binding extra sockets:

```python
import json

from evalforge_maestro import ServiceApplication, ServiceConfig, ServiceEvaluateResponse

app = ServiceApplication(
    ServiceConfig(
        storage_dir=".evalforge",
        local_only=True,
        mock_mode=True,
    ),
    auth_token="internal-service-secret",
)

payload = {
    "cases": [{"id": "c1", "input": "Capital of France?", "reference": "Paris"}],
    "executions": [
        {"case_id": "c1", "input": "Capital of France?", "output": "Paris", "elapsed_seconds": 0.01}
    ],
    "metrics": [{"metric_id": "exact_match"}],
    "persist": False,
}
status, headers, raw_body = app.handle_request(
    "POST",
    "/v1/evaluate",
    body=json.dumps(payload).encode("utf-8"),
    headers={"Authorization": "Bearer internal-service-secret"},
)
assert status == 200
result = ServiceEvaluateResponse.model_validate_json(raw_body)
assert result.gate.passed is True
```
