# Feature Specification: Optional Remote Evaluation Service & Consumer CI Calibration Guides

**Feature Branch**: `010-remote-eval-service`  
**Created**: 2026-11-21  
**Status**: Draft  
**Input**: User description: "Optional HTTP evaluation service wrapper delegating strictly to library-pure SDK and storage layers without leaking server concerns into core packages, paired with downstream hybrid/rerank CI fixtures and small-judge min-agreement calibration workflow guides."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Strict Boundary In-Process & HTTP Service Wrapper Over Library SDK & Storage (Priority: P1)

As a platform engineer integrating EvalForge Maestro into internal developer platforms or remote CI runners, I want an optional HTTP service wrapper (`evalforge_maestro.service` + CLI `evalforge-maestro serve`) that exposes typed JSON endpoints for health inspection, querying indexed runs/cases/baselines, ingesting OTel traces, running offline/trace evaluations, comparing runs, and rendering Three-Way reports—while delegating strictly to library-pure SDK and storage modules so zero HTTP/server concerns ever leak into core packages.

**Why this priority**: Enforcing the Constitution Principle I & II architectural boundary is critical before adding any HTTP server surface: core evaluation, metrics, storage, judges, regression, and reporting must remain 100% pure, minimal-dependency, and cold-start clean.

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/unit/test_remote_service.py tests/test_library_purity.py tests/contract/test_m10_schemas.py` verifying typed Pydantic request/response contracts, all HTTP routes via both in-process request dispatch and live loopback `ThreadingHTTPServer`, strict token auth + loopback binding guardrails, secret masking on error/data responses, zero path-traversal/RCE (`module:fn` blocked over HTTP), and AST checks confirming core packages never import `evalforge_maestro.service` or `http.server`.

**Acceptance Scenarios**:

1. **Given** an `.evalforge/` directory managed by `LocalRunStore` and `SQLiteRunIndex`, **When** calling `GET /health`, `GET /v1/index/status`, `POST /v1/index/rebuild`, `GET /v1/runs`, `GET /v1/runs/{run_id}`, `GET /v1/cases`, `GET /v1/baselines`, or `GET /v1/metrics/{metric_id}/history`, **Then** every response returns a schema-validated Pydantic JSON envelope matching the exact underlying `LocalRunStore` / `SQLiteRunIndex` results cleanly (with HTTP `400` on invalid identifiers like `../secret` and `404` on missing run IDs).
2. **Given** a typed `ServiceEvaluateRequest` carrying inline `cases` (`EvaluationCase`) paired with pre-captured `executions` (`ExecutionResult`) OR `otel_payload` (normalized via `ingest_otel_spans`), plus allowed deterministic/retrieval/agent/statistical/judge metric specs and `QualityGatePolicy`, **When** posted to `POST /v1/evaluate` (optionally with `persist=true` and `run_id`), **Then** the service delegates cleanly through `ReplayAdapter`, `EvaluationOrchestrator`, `QualityGate`, and `build_run_report`, returning a schema-validated `ServiceEvaluateResponse` with exit-equivalent `gate` decision and secret-scrubbed outputs.
3. **Given** `POST /v1/compare` or `POST /v1/reports` or `POST /v1/otel/ingest`, **When** invoked with valid stored run IDs or OTLP trace payloads, **Then** the service delegates cleanly to `compare_runs` / `compare_run_cohorts`, `reporting`, and `ingest_otel_spans`, returning validated JSON/Markdown payloads with zero credentials leaked.

---

### User Story 2 - Remote Service Security Guardrails, Auth & CLI `serve` Lifecycle (Priority: P1)

As a security-conscious platform operator, I want `evalforge-maestro serve` and `EvalForgeService` to fail closed on insecure remote configurations—enforcing loopback-only binding unless explicitly opted in with a Bearer auth token, constant-time token verification (`hmac.compare_digest`), strict request payload size limits, pre-network `local_only` / `block_pii` policy checks, and POSIX exit codes—while keeping `import evalforge_maestro` and `--help` free of HTTP server imports.

**Why this priority**: An HTTP service exposing evaluation storage or judge endpoints must enforce strong defaults out of the box (no unauthenticated `0.0.0.0` exposure, no arbitrary Python entrypoint imports, no oversized JSON DoS, no secret leakage).

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/integration/test_remote_service_pipeline.py tests/unit/test_cli_config.py` covering CLI `evalforge-maestro serve` startup/shutdown on an ephemeral loopback port (`127.0.0.1:0`), live HTTP `urllib.request` roundtrips (`/health`, `/v1/evaluate`, `/v1/runs`, `/v1/compare`, `/v1/reports`), HTTP `401` on missing/bad Bearer token, HTTP `413` on oversized bodies, POSIX exit code `2`/`4` when attempting unauthenticated non-loopback binding, and subprocess `--help` cold-start isolation (`http.server` absent from `sys.modules`).

**Acceptance Scenarios**:

1. **Given** an operator invoking `evalforge-maestro serve --host 0.0.0.0` without supplying an auth token (`--auth-token` / `EVALFORGE_SERVICE_TOKEN` / `--env-file`), **When** validating service configuration prior to binding a socket, **Then** startup aborts cleanly with exit code `4` (`LocalOnlyPolicyError`) rather than opening an unauthenticated public listener.
2. **Given** a running loopback service configured with `auth_token="secret-tok-123"` and `max_request_bytes`, **When** a client sends an unauthenticated request, wrong Bearer token, malformed JSON, unknown route, or payload exceeding `max_request_bytes`, **Then** the service responds with structured `CLIErrorPayload`-compatible JSON error envelopes (`401`, `400`, `404`, `413`), never echoing raw tokens or stack traces.

---

### User Story 3 - Downstream Hybrid/Rerank CI Fixtures & Small-Judge `calibrate --min-agreement` Guides (Priority: P2)

As an engineering team adopting EvalForge Maestro across RAG repositories (such as `docpipe-maestro` consumers), I want ready-to-run hybrid/rerank offline CI configuration templates and small-judge `calibrate --min-agreement` gating fixtures and workflows inside `examples/ci/` plus comprehensive documentation (`docs/service-and-ci.md`, `docs/calibration-and-ci.md`, updated `examples/ci/README.md`, `README.md`, and `docs/future-features.md`), without modifying any external repository.

**Why this priority**: Completes the remaining adoption workflows from `docs/future-features.md` while keeping the `docpipe-maestro` repository completely untouched.

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/integration/test_ci_templates.py tests/test_api_stability.py` validating `examples/ci/evalforge-hybrid-rerank.toml`, `examples/ci/hybrid-rerank-golden.jsonl`, `examples/ci/hybrid-rerank-executions.jsonl`, `examples/ci/calibration-samples.jsonl`, and end-to-end CLI execution of `calibrate --min-agreement` and `run --config examples/ci/evalforge-hybrid-rerank.toml --strict --json`.

**Acceptance Scenarios**:

1. **Given** the new `examples/ci/evalforge-hybrid-rerank.toml`, `hybrid-rerank-golden.jsonl`, and `hybrid-rerank-executions.jsonl` templates, **When** validated and executed in offline CI mode (`--mock --local-only --strict`), **Then** retrieval (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`), text (`normalized_match`), and `--max-context-chars` truncation evaluate cleanly to `PASS` (exit code `0`) and render Three-Way reports.
2. **Given** `examples/ci/calibration-samples.jsonl` paired with `evalforge-maestro calibrate --metric groundedness --min-agreement 0.80 --mock --local-only --json`, **When** run in CI pre-flight gating, **Then** agreement rate, directional bias (`CalibrationReport`), and exit code `0`/`1` enforcement on `--min-agreement` work deterministically and match the documented CI workflow.

---

### Edge Cases

- What happens when `POST /v1/evaluate` attempts to run `EvaluationOrchestrator` over dynamic arbitrary target imports or remote judge URLs while `local_only=True`?
  - Remote arbitrary code execution (`target` module strings) is never exposed on the service API (`ServiceEvaluateRequest` accepts strictly `executions` or `otel_payload` alongside `cases`), and pre-network `validate_local_only_target` / `validate_pii_egress` block disallowed remote endpoints (`403` / `LocalOnlyPolicyError`).
- What happens when `POST /v1/evaluate` is invoked with `persist=True` and a `run_id` that already exists on disk?
  - `LocalRunStore.save_run` raises `ImmutabilityError`, translated cleanly to HTTP `409 Conflict` without overwriting historical canonical artifacts.
- What happens when `GET /v1/runs/../secret` or an invalid `run_id` containing slashes or `..` is requested?
  - `_validate_safe_identifier` rejects it immediately cleanly with HTTP `400 Bad Request` (`StorageError`).
- What happens when `evalforge-maestro serve --allow-remote` binds non-loopback without `EVALFORGE_SERVICE_TOKEN` or `auth_token`?
  - Blocked pre-socket-bind with `LocalOnlyPolicyError` (CLI exit code `4`).

## Clarifications

### Session 2026-11-21

- **Zero-Duplication Metric & Security Builder (`_metric_factory.py`)**: Metric instantiation and PII/locality preflight guards are shared via a library-pure internal helper (`evalforge_maestro._metric_factory`) consumed by both `cli/targets.py` and `service/app.py`, keeping `evalforge_maestro.service` completely decoupled from `cli` while guaranteeing identical metric parameters, secret masking, and security enforcement across CLI and HTTP.
- **Stateless vs. Persistent Evaluation (`persist: bool = False`)**: `POST /v1/evaluate` defaults to `persist=False` (executing inside an isolated temporary directory so stateless requests never pollute `.evalforge/`), while `persist=True` writes atomically to the configured `LocalRunStore` (returning HTTP `409 Conflict` cleanly on duplicate `run_id` via `ImmutabilityError` and auto-syncing `SQLiteRunIndex` when present).
- **HTTP Transport & WSGI/ASGI-Free Dependency Profile**: `evalforge_maestro.service` uses stdlib `http.server.ThreadingHTTPServer` lazily imported only in `service/server.py` (`serve_http` / `create_http_server`), while `ServiceApplication` in `service/app.py` stays completely transport-agnostic (`handle_request(method, path, ...)`), preserving the minimal core dependency footprint (`pydantic`, `jsonschema`, `tomli` on `<3.11`) and cold-start purity (`import evalforge_maestro` and `--help` leave `http.server` unloaded).
- **RCE & SSRF Prevention on Remote Service**: `ServiceEvaluateRequest` accepts strictly `cases` (`list[EvaluationCase]`) paired with either inline `executions` (`list[ExecutionResult]`) or inline `otel_payload` (ingested via `ingest_otel_spans`); arbitrary Python module import targets (`module:symbol`) and local filesystem path reads are disallowed over HTTP payloads. Non-loopback host binding (`0.0.0.0` / LAN IP) is rejected pre-bind with `LocalOnlyPolicyError` (exit code `4`) unless a non-empty `auth_token` (`EVALFORGE_SERVICE_TOKEN` / `--auth-token`) is provided.
- **Consumer Hybrid/Rerank & Small-Judge Calibration Adoption**: All downstream `docpipe-maestro` CI guidance, hybrid/rerank offline templates, and small-judge `calibrate --min-agreement` workflows are added cleanly inside `examples/ci/` and `docs/` within `evalforge-maestro`, keeping the external `docpipe-maestro` checkout completely untouched.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define strict Pydantic v2 contracts in `src/evalforge_maestro/types.py` for service configuration (`ServiceConfig`), error responses (`ServiceErrorResponse`), health/capabilities (`ServiceHealthResponse`), evaluation requests & responses (`ServiceEvaluateRequest`, `ServiceEvaluateResponse`), comparison requests (`ServiceCompareRequest`, `ServiceCompareResponse`), OTel ingestion requests & responses (`ServiceOtelIngestRequest`, `ServiceOtelIngestResponse`), and report rendering requests & responses (`ServiceReportRequest`, `ServiceReportResponse`).
- **FR-002**: System MUST implement the optional HTTP service wrapper under `src/evalforge_maestro/service/` (`ServiceApplication` in `service/app.py` and stdlib `ThreadingHTTPServer` runner `create_http_server` / `serve_http` in `service/server.py`, zero new external dependencies, lazy `http.server` import).
- **FR-003**: Core packages (`types`, `datasets`, `adapters`, `execution`, `metrics`, `judges`, `embeddings`, `regression`, `storage`, `reporting`) MUST have zero imports from `evalforge_maestro.service`, `http.server`, or `cli`. `evalforge_maestro.service` MUST delegate strictly to public library/storage/reporting entrypoints without duplicating evaluation, metric, regression, or SQL logic, and MUST NEVER import `evalforge_maestro.cli`, `tomllib`, or `dotenv`.
- **FR-004**: `ServiceApplication` MUST expose a deterministic, strongly-typed dispatcher supporting:
  - `GET /health`
  - `GET /v1/index/status`, `POST /v1/index/rebuild`, `POST /v1/index/sync`
  - `GET /v1/runs`, `GET /v1/runs/{run_id}`, `GET /v1/cases`, `GET /v1/baselines`, `GET /v1/metrics/{metric_id}/history`
  - `POST /v1/otel/ingest`
  - `POST /v1/evaluate`
  - `POST /v1/compare`
  - `POST /v1/reports`
- **FR-005**: HTTP transport & handler MUST enforce loopback-only binding (`127.0.0.1` / `localhost` / `::1`) unless an explicit non-empty `auth_token` (`--auth-token` / `EVALFORGE_SERVICE_TOKEN`) is configured, constant-time Bearer token comparison (`hmac.compare_digest`), configurable `max_request_bytes` limit (HTTP `413`), identifier path-traversal protection (`400`), immutability conflict mapping (`409`), and secret scrubbing on all outputs/errors.
- **FR-006**: CLI MUST expose `evalforge-maestro serve` (`--host`, `--port`, `--storage-dir`, `--auth-token`, `--allow-unauthenticated-loopback` default safe, `--local-only`, `--block-pii`, `--mock`, `--max-request-bytes`, `--workers` / threaded server) preserving sub-second `--help` cold-start isolation and POSIX exit codes (`0`, `2`, `4`).
- **FR-007**: `ServiceEvaluateRequest` MUST enforce safe offline/trace execution (accepting `cases` + `executions` or `otel_payload`, never dynamic Python `module:fn` import strings) and apply pre-network `local_only` / `block_pii` security checks cleanly before external calls.
- **FR-008**: System MUST add consumer CI templates and fixtures under `examples/ci/` (`evalforge-hybrid-rerank.toml`, `hybrid-rerank-golden.jsonl`, `hybrid-rerank-executions.jsonl`, `calibration-samples.jsonl`) plus updated CI documentation covering `docpipe-maestro` hybrid+rerank and small-judge `calibrate --min-agreement` workflows without modifying `/home/maestro/LifeFolder/10_PUBLIC/projects/docpipe-maestro`.
- **FR-009**: System MUST provide comprehensive, professional documentation (`docs/remote-service.md`, `docs/calibration-and-ci.md`, `examples/ci/README.md`, `README.md`, `docs/future-features.md`).

### Key Entities

- **`ServiceConfig`**: Service host, port, `storage_dir`, `local_only`, `block_pii`, `mock_mode`, `max_request_bytes`, `auth_token_configured` (never storing raw secret token!).
- **`ServiceEvaluateRequest` / `ServiceEvaluateResponse`**: Typed remote evaluation contract wrapping `EvaluationCase` items, pre-captured `ExecutionResult`s or OTLP payload, `metric_specs`, `QualityGatePolicy`, `persist`, optional `run_id`, and returning `RunRecord`, `QualityGateResult`, and optional `ReportDocument`.
- **`ServiceApplication`**: In-process testable request router/dispatcher translating typed HTTP requests (`method`, `path`, `query_params`, `body`, `headers`) into library calls and strict HTTP status + JSON payloads.

## Success Criteria *(mandatory)*

- **SC-001**: AST & subprocess cold-start tests confirm zero imports of `evalforge_maestro.service` or `http.server` anywhere in core modules, `import evalforge_maestro`, or `evalforge-maestro --help`.
- **SC-002**: Live loopback HTTP integration tests verify `GET`/`POST` roundtrips (`health`, `index`, `runs`, `cases`, `otel/ingest`, `evaluate`, `compare`, `reports`), Bearer auth `401`, oversized payload `413`, duplicate `run_id` `409`, invalid `run_id` `400`, and pre-bind `4` block on unauthenticated remote bind.
- **SC-003**: Downstream CI templates (`evalforge-hybrid-rerank.toml`, `calibration-samples.jsonl`) execute end-to-end cleanly via CLI (`run` and `calibrate --min-agreement`) with exit code `0`.
- **SC-004**: All repository gates pass (`uv lock --check`, `ruff format --check`, `ruff check`, Bandit `S`, `mypy --strict src tests`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` and `regression.gate`, determinism/immutability markers, `pip-audit`, `uv build && twine check --strict`, isolated `--no-dev` wheel test).

## Assumptions

- Using Python's built-in `http.server.ThreadingHTTPServer` keeps zero external HTTP server dependencies while offering real multi-threaded HTTP/1.1 serving; if an operator mounts inside FastAPI/Starlette externally, `ServiceApplication.handle_request(...)` acts as a framework-agnostic adapter kernel.
- Raw `auth_token` never enters serialized `ServiceConfig` (mirroring `ResolvedJudgeSettings.api_key = REDACTED_VALUE` and passing raw secret separately into `ServiceApplication` / server startup).
