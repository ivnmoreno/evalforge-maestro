# Tasks: Optional Remote Evaluation Service & Consumer CI Guides (`010-remote-eval-service`)

**Input**: Design documents from `/specs/010-remote-eval-service/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/service-and-ci.md`

---

## Phase 1: Setup & Library Purity Guards

**Purpose**: Lock cold-start & unidirectional boundary tests before adding service modules.

- [X] T001 [P] Add `"http.server"` to `_HEAVY_OPTIONAL_MODULES` and add explicit AST rules in `tests/test_library_purity.py` asserting core packages (`types`, `datasets`, `adapters`, `execution`, `metrics`, `judges`, `embeddings`, `regression`, `storage`, `reporting`, `_metric_factory`) NEVER import `evalforge_maestro.service`, `http.server`, or `socketserver`, and `service/` NEVER imports `evalforge_maestro.cli`, `tomllib`, `dotenv`, `langchain`, or `llama_index`

---

## Phase 2: Foundational Schemas & Shared Metric Builder — Blocking Prerequisites

**Purpose**: Establish M10 Pydantic v2 contracts (`types.py`) and extract library-pure `_metric_factory.py` before implementing service endpoints or CLI handlers.

- [X] T002 [P] Write strict schema contract tests in `tests/contract/test_m10_schemas.py` covering `ServiceConfig` (`port` `0..65535`, `max_request_bytes` `1024..104857600`, bool rejection), `ServiceHealthResponse`, `ServiceErrorResponse` (`status_code` `400..599`, secret scrubbing), `ServiceOtelIngestRequest` / `Response`, `ServiceEvaluateRequest` (XOR `executions` vs `otel_payload`, `cases` non-empty, `max_concurrency` `1..64`) / `Response`, `ServiceCompareRequest` (`candidate_run_id` or non-empty `candidate_run_ids`) / `Response`, and `ServiceReportRequest` (`run_id`, `compare_run_id`, or `trend_window >= 2`) / `Response`
- [X] T003 Implement `ServiceConfig`, `ServiceHealthResponse`, `ServiceErrorResponse`, `ServiceOtelIngestRequest`, `ServiceOtelIngestResponse`, `ServiceEvaluateRequest` (with optional non-secret `judge: JudgeConfig | None` and `embedding: EmbeddingConfig | None`), `ServiceEvaluateResponse`, `ServiceCompareRequest`, `ServiceCompareResponse`, `ServiceReportRequest`, and `ServiceReportResponse` in `src/evalforge_maestro/types.py` citing constraints in `specs/010-remote-eval-service/data-model.md` (`ServiceConfig.{host,port,storage_dir,max_request_bytes,auth_token_configured}`, `ServiceEvaluateRequest.{cases,executions,otel_payload,dataset_id,metrics,judge,embedding,max_context_chars,max_concurrency}`, `ServiceCompareRequest.{candidate_run_id,candidate_run_ids,baseline_ref}`, `ServiceReportRequest.trend_window`) (depends on T002)
- [X] T004 Extract shared library-pure metric builder and security preflight helper (`build_metrics_from_specs`, `preflight_metric_security`, reusing `_DIRECT_DETERMINISTIC_FACTORIES`, `_TOPK_RETRIEVAL_FACTORIES`, `_SIMPLE_JUDGE_FACTORIES`, `_EMBEDDING_METRIC_IDS`, `CustomRubricJudgeMetric`) into `src/evalforge_maestro/_metric_factory.py` and delegate `build_metrics_from_config` & metric portion of `preflight_run_security` in `src/evalforge_maestro/cli/targets.py` cleanly with zero duplication (depends on T001)

**Checkpoint**: Schemas, purity guards, and shared metric factory pass (`test_m10_schemas.py`, `test_library_purity.py`, existing CLI/metric tests).

---

## Phase 3: User Story 1 — Strict Boundary In-Process & HTTP Service Wrapper (Priority: P1) 🎯 MVP

**Goal**: Implement transport-agnostic `ServiceApplication` in `src/evalforge_maestro/service/app.py` delegating strictly to `LocalRunStore`, `SQLiteRunIndex`, `ingest_otel_spans`, `ReplayAdapter`, `EvaluationOrchestrator`, `compare_runs`/`compare_run_cohorts`, `analyze_trend`, `QualityGate`, and `reporting`.

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/unit/test_remote_service.py -k us1 tests/test_library_purity.py` verifying all HTTP routes (`GET /health`, `/v1/index/status`, `POST /v1/index/{rebuild,sync}`, `GET /v1/runs`, `/v1/runs/{run_id}`, `/v1/cases`, `/v1/baselines`, `/v1/metrics/{metric_id}/history`, `POST /v1/otel/ingest`, `/v1/evaluate` stateless + persistent, `/v1/compare`, `/v1/reports`), error mappings (`400`, `403`, `404`, `405`, `409`), and secret masking.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [P] [US1] Write US1 unit tests in `tests/unit/test_remote_service.py` covering `ServiceApplication.handle_request` across all `GET`/`POST` routes, stateless (`persist=False`) vs persistent (`persist=True`) `/v1/evaluate` over both inline `executions` and `otel_payload`, `409 Conflict` on duplicate persistent `run_id`, `400 Bad Request` on invalid path identifiers (`..`), `403 Forbidden` on `local_only` / `block_pii` blocks, `404` on unknown routes or missing runs, `405` on disallowed methods, and secret redaction across responses

### Implementation for User Story 1

- [X] T006 [US1] Implement `validate_service_bind_policy` and `ServiceApplication` (`handle_request(method, raw_path, body=b"", headers=None)`) in `src/evalforge_maestro/service/app.py` routing all 13 endpoints via library SDK/storage/reporting layers cleanly with parameterized identifier validation and exception-to-HTTP-status mapping (depends on T003, T004, T005)

**Checkpoint**: User Story 1 (`ServiceApplication` in-process delegation, routes, & error/security mapping) passes independently (**MVP complete**).

---

## Phase 4: User Story 2 — Live Loopback ThreadingHTTPServer, Auth & CLI `serve` (Priority: P1)

**Goal**: Implement lazy `ThreadingHTTPServer` wrapper in `src/evalforge_maestro/service/server.py`, export service symbols via `service/__init__.py` & `evalforge_maestro/__init__.py`, wire CLI `evalforge-maestro serve`, and pin API contracts in `tests/test_api_stability.py`.

**Independent Test**: Run `uv run pytest --strict-markers -W error tests/unit/test_remote_service.py tests/integration/test_remote_service_pipeline.py tests/test_api_stability.py tests/test_library_purity.py` verifying Bearer `401` checks via `hmac.compare_digest`, pre-bind exit code `4` on unauthenticated remote bind, HTTP `413` body-size enforcement, live ephemeral loopback HTTP requests over TCP sockets, CLI `serve` startup/logging to `stderr` only, and cold-start `--help` isolation (zero `http.server` import).

### Tests for User Story 2 ⚠️

- [X] T007 [P] [US2] Extend `tests/unit/test_remote_service.py` covering Bearer token auth (`401`), `hmac.compare_digest`, `413` oversized body enforcement, `validate_service_bind_policy` (`LocalOnlyPolicyError` on `0.0.0.0` without token vs allowed with token), and in-process `socket.socketpair()` verification of `EvalRequestHandler` in `service/server.py` without relaxing `tests/conftest.py`
- [X] T008 [P] [US2] Write live HTTP & CLI integration tests in `tests/integration/test_remote_service_pipeline.py` (including `@pytest.mark.gate_determinism`) launching `create_http_server` on `127.0.0.1:0` in an isolated subprocess (preserving `tests/conftest.py` hermeticity) and invoking live HTTP GET/POST `/health`, `/v1/evaluate`, `/v1/runs`, `/v1/compare`, `/v1/reports` via `urllib.request`, verifying unauthenticated `401`, testing CLI `evalforge-maestro serve --host 0.0.0.0` exit code `4`, and running subprocess `--help` cold-start check confirming `http.server` absent from `sys.modules`

### Implementation for User Story 2

- [X] T009 [US2] Implement lazy `create_http_server` and `serve_http` using stdlib `http.server.ThreadingHTTPServer` in `src/evalforge_maestro/service/server.py` (enforcing `validate_service_bind_policy`, `max_request_bytes`, header Content-Length checks, and NullHandler/logger telemetry without stdout prints) and export package API in `src/evalforge_maestro/service/__init__.py` (depends on T006, T007, T008)
- [X] T010 [P] [US2] Add `serve` subcommand (`--host`, `--port`, `--auth-token`, `--max-request-bytes`, `--local-only`, `--allow-remote-judges`, `--block-pii`, `--mock`, `--storage-dir`) in `src/evalforge_maestro/cli/parser.py` keeping `http.server` / `service` absent from module top level (depends on T008)
- [X] T011 [US2] Implement `_handle_serve` (`EVALFORGE_SERVICE_TOKEN` fallback, `validate_service_bind_policy` -> exit code `4`, stderr startup log, clean delegation to `serve_http`), update `_args_to_cli_overrides` (popping `serve`-only keys cleanly), and route `cmd == "serve"` cleanly in `src/evalforge_maestro/cli/commands.py` (depends on T009, T010)
- [X] T012 [P] [US2] Export `ServiceApplication`, `ServiceConfig`, `ServiceErrorResponse`, `ServiceHealthResponse`, `ServiceOtelIngestRequest`, `ServiceOtelIngestResponse`, `ServiceEvaluateRequest`, `ServiceEvaluateResponse`, `ServiceCompareRequest`, `ServiceCompareResponse`, `ServiceReportRequest`, and `ServiceReportResponse` in `src/evalforge_maestro/__init__.py` (depends on T003, T009)
- [X] T013 [US2] Update `tests/test_api_stability.py` cleanly to pin M10 exports, `service.__all__`, `ServiceApplication` / `create_http_server` / `serve_http` / `validate_service_bind_policy` signatures, and `Service*` schema fields (depends on T012)

**Checkpoint**: User Stories 1 and 2 deliver secure, library-pure HTTP service + CLI `serve`.

---

## Phase 5: User Story 3 — Hybrid/Rerank CI Fixtures, Small-Judge Calibration & Docs (Priority: P2)

**Goal**: Add ready-to-run hybrid+rerank CI fixtures and small-judge `calibrate --min-agreement` workflows inside `examples/ci/` (leaving external `docpipe-maestro` untouched), verify end-to-end execution via `tests/integration/test_ci_templates.py`, and author comprehensive user documentation across `docs/` and `README.md`.

### Tests for User Story 3 ⚠️

- [X] T014 [P] [US3] Extend `tests/integration/test_ci_templates.py` verifying `examples/ci/evalforge-hybrid-rerank.toml`, `hybrid-rerank-golden.jsonl`, `hybrid-rerank-executions.jsonl`, and `calibration-samples.jsonl` validate and execute end-to-end cleanly via CLI `config validate`, `run --strict --json`, and `calibrate --min-agreement 80.0 --mock --local-only --json`

### Implementation for User Story 3 & Final Verification

- [X] T015 [P] [US3] Create `examples/ci/hybrid-rerank-golden.jsonl`, `examples/ci/hybrid-rerank-executions.jsonl`, `examples/ci/evalforge-hybrid-rerank.toml`, and `examples/ci/calibration-samples.jsonl` (aligned with `examples/ci/README.md`, zero secrets, zero edits to external `docpipe-maestro`) (depends on T014)
- [X] T016 [P] [US3] Author comprehensive user documentation: `docs/remote-service.md` (architecture boundary, security posture, complete HTTP route/schema reference, curl & Python examples, CLI `serve`), `docs/calibration-and-ci.md` (`docpipe-maestro` hybrid/rerank CI guide, small-judge `calibrate --min-agreement` workflow, GitHub Actions snippets), update `examples/ci/README.md`, `README.md`, and `docs/future-features.md` (marking all in-repo post-MVP roadmap items shipped) (depends on T011, T015)
- [X] T017 Run full Constitution & CI release verification (`uv lock --check`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ruff check --select S src/`, `uv run mypy --strict src tests`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` & `regression.gate`, `-m "gate_determinism or gate_immutability"`, `uv run pip-audit --skip-editable`, `uv build && uv run twine check --strict dist/*`, isolated `--no-dev` wheel install & CLI/service/CI-template smoke check) and clean temporary artifacts

---

## Dependencies & Execution Order

- **Phase 1–2 (`T001`–`T004`)**: Purity guards, M10 schemas (`types.py`), and shared `_metric_factory.py` refactoring (`cli/targets.py`).
- **Phase 3 (`US1`, `T005`–`T006`)**: Transport-agnostic `ServiceApplication`.
- **Phase 4 (`US2`, `T007`–`T013`)**: Live loopback `ThreadingHTTPServer`, Bearer auth, CLI `serve`, top-level exports, & API stability pins.
- **Phase 5 (`US3`, `T014`–`T017`)**: Hybrid/rerank & calibration CI templates, comprehensive user documentation, and full CI verification.
