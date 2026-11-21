# Contract Specification: Remote Evaluation HTTP Service & Consumer CI Workflows

**Feature**: `010-remote-eval-service`  
**Contract Scope**: Optional HTTP service wrapper (`evalforge_maestro.service`), shared metric factory (`evalforge_maestro._metric_factory`), CLI `serve` subcommand, and consumer CI templates (`examples/ci/`).

## 1. Library & Service Boundaries

### Public Service Module (`evalforge_maestro.service`)
Exported symbols (`evalforge_maestro.service.__all__`):
- `ServiceApplication`
- `create_http_server(config: ServiceConfig, *, auth_token: str | None = None, judge_api_key: str | None = None, embedding_api_key: str | None = None) -> ThreadingHTTPServer`
- `serve_http(config: ServiceConfig, *, auth_token: str | None = None, judge_api_key: str | None = None, embedding_api_key: str | None = None) -> None`
- `validate_service_bind_policy(config: ServiceConfig, *, auth_token: str | None = None) -> None`

Also re-exported cleanly from top-level `evalforge_maestro`:
- `ServiceApplication`, `ServiceConfig`, `ServiceErrorResponse`, `ServiceHealthResponse`, `ServiceOtelIngestRequest`, `ServiceOtelIngestResponse`, `ServiceEvaluateRequest`, `ServiceEvaluateResponse`, `ServiceCompareRequest`, `ServiceCompareResponse`, `ServiceReportRequest`, `ServiceReportResponse`.

### Strict Dependency Invariants (Constitution Principles I & II)
- Core modules (`types`, `datasets`, `execution`, `metrics`, `judges`, `embeddings`, `regression`, `storage`, `reporting`, `adapters`, `_metric_factory`) NEVER import `evalforge_maestro.service`, `http.server`, `socketserver`, `cli`, `tomllib`, or `dotenv`.
- `evalforge_maestro.service` NEVER imports `evalforge_maestro.cli`, `tomllib`, `dotenv`, `langchain`, or `llama_index`.
- `ServiceApplication` and top-level `evalforge_maestro` NEVER import `http.server` at module import time (`http.server` imported lazily inside `create_http_server` / `serve_http`).

---

## 2. HTTP Endpoints & Status Mapping

When `auth_token` is configured (non-empty), **every** route requires `Authorization: Bearer <token>` verified via `hmac.compare_digest`; missing/invalid credentials return `401 Unauthorized` (`ServiceErrorResponse`). When `host` is non-loopback (`host.lower() not in {"127.0.0.1", "localhost", "::1", "[::1]"}`) and no non-empty `auth_token` is provided, `validate_service_bind_policy` raises `LocalOnlyPolicyError` pre-bind (CLI exit code `4`).

| Method & Route | Delegation Target | Success Status & Schema |
| --- | --- | --- |
| `GET /health` | `SQLiteRunIndex.status()` | `200 ServiceHealthResponse` |
| `GET /v1/index/status` | `SQLiteRunIndex.status()` | `200 SQLiteIndexStatus` |
| `POST /v1/index/rebuild` | `SQLiteRunIndex.rebuild()` | `200 SQLiteIndexStatus` |
| `POST /v1/index/sync` | `SQLiteRunIndex.sync()` | `200 SQLiteIndexStatus` |
| `GET /v1/runs` | `SQLiteRunIndex.query_runs(RunQueryFilter(...))` | `200 RunQueryPayload` |
| `GET /v1/runs/{run_id}` | `LocalRunStore.load_run(run_id)` | `200 RunRecord` (`400` bad ID / `404` absent) |
| `GET /v1/cases` | `SQLiteRunIndex.query_cases(CaseQueryFilter(...))` | `200 CaseQueryPayload` |
| `GET /v1/baselines` | `LocalRunStore.load_baselines()` | `200 BaselineRegistry` |
| `GET /v1/metrics/{metric_id}/history` | `SQLiteRunIndex.metric_history(...)` | `200 list[IndexedMetricPoint]` JSON array |
| `POST /v1/otel/ingest` | `ingest_otel_spans(...)` | `200 ServiceOtelIngestResponse` |
| `POST /v1/evaluate` | `_metric_factory` + `ReplayAdapter` + `EvaluationOrchestrator` + `QualityGate` + `build_run_report` | `200 ServiceEvaluateResponse` (`409` on duplicate persistent `run_id`) |
| `POST /v1/compare` | `LocalRunStore` + `compare_runs`/`compare_run_cohorts` + `QualityGate` | `200 ServiceCompareResponse` |
| `POST /v1/reports` | `LocalRunStore` + `compare_runs`/`analyze_trend` + `reporting` | `200 ServiceReportResponse` |

Error code mapping (`ServiceErrorResponse`):
- `400`: `ValidationError`, `ConfigurationError`, `DatasetError`, `AdapterError`, invalid identifier / `StorageError` (except not-found), `MetricError`, invalid query parameter
- `401`: Missing or invalid Bearer token
- `403`: `LocalOnlyPolicyError` (PII egress or non-local judge/embedding blocked pre-network when `local_only=True`)
- `404`: Unknown HTTP route, missing `run_id` / baseline
- `405`: Disallowed HTTP method on known route
- `409`: `ImmutabilityError` (attempting `persist=True` with an already committed `run_id`)
- `413`: Request `Content-Length` or payload exceeds `ServiceConfig.max_request_bytes`
- `503`: `MissingExtraError` (e.g., `[judges]` or `[embeddings]` requested without optional extra installed)

---

## 3. CLI `evalforge-maestro serve` Contract

```text
evalforge-maestro serve
  [--host 127.0.0.1]
  [--port 8787]
  [--storage-dir .evalforge]
  [--auth-token STR]          # or EVALFORGE_SERVICE_TOKEN
  [--max-request-bytes INT]
  [--local-only | --allow-remote-judges]
  [--block-pii] [--mock]
  [--config PATH] [--env-file PATH] [--log-level ...] [--log-json]
```
- `ServiceConfig.local_only` defaults to `True`; passing `--allow-remote-judges` sets `local_only=False` on the service unless overridden by `EVALFORGE_LOCAL_ONLY` / `--local-only`.
- `_args_to_cli_overrides` pops `serve`-only keys (`host`, `port`, `auth_token`, `max_request_bytes`, `allow_remote_judges`) so `CLIResolvedConfig` stays backward-compatible with frozen M5/M6/M8 schemas and raw `auth_token` never enters `CLIResolvedConfig` provenance logs.
- Logs startup URL (`http://<host>:<port>`) strictly to `stderr` (`logger.info(...)`, never `stdout`!).
- Pre-bind security check runs via `validate_service_bind_policy(...)`; exits with `4` if remote host lacks auth token.

---

## 4. Consumer CI Fixtures & Calibration Templates (`examples/ci/`)

- `examples/ci/evalforge-hybrid-rerank.toml`: Offline gating config scoring `normalized_match`, `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k` with `max_context_chars` and strict quality gate.
- `examples/ci/hybrid-rerank-golden.jsonl`: 3 multi-hop / hybrid retrieval + rerank golden cases (2 mandatory, 1 optional).
- `examples/ci/hybrid-rerank-executions.jsonl`: Matching pre-captured `ExecutionResult` traces demonstrating ranked reranked chunks cleanly passing `ndcg_at_k` and `precision_at_k`.
- `examples/ci/calibration-samples.jsonl`: Annotated `HumanCalibrationSample` fixture for `evalforge-maestro calibrate --metric groundedness --min-agreement 0.80 --mock --local-only --json`.
