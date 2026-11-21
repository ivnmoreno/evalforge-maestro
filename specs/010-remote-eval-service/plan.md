# Implementation Plan: Optional Remote Evaluation Service & Consumer CI Guides

**Branch**: `010-remote-eval-service` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/010-remote-eval-service/spec.md`

## Summary

Deliver the optional `evalforge_maestro.service` HTTP wrapper (`ServiceApplication` in `service/app.py` + lazy stdlib `ThreadingHTTPServer` in `service/server.py`) plus CLI `evalforge-maestro serve`, extracting metric & security construction cleanly into a shared library-pure helper (`evalforge_maestro._metric_factory`) so core packages stay 100% free of server/HTTP concerns. Pair this with hybrid/rerank CI templates, small-judge `calibrate --min-agreement` fixtures (`examples/ci/`), and comprehensive documentation (`docs/remote-service.md`, `docs/calibration-and-ci.md`, `examples/ci/README.md`, `README.md`, `docs/future-features.md`) without altering the external `docpipe-maestro` repository.

## Technical Context

**Language/Version**: Python 3.10+ (`3.13` local runtime, `mypy --strict`, `from __future__ import annotations`)  
**Primary Dependencies**: Stdlib `http.server` / `hmac` / `urllib.parse` (lazy import on server start), `pydantic>=2.7`  
**Storage**: Delegates read/write strictly to `LocalRunStore` & `SQLiteRunIndex`; `persist=False` executes inside isolated temp dir  
**Testing**: `pytest --strict-markers -W error --cov-branch`, `tests/contract/test_m10_schemas.py`, `tests/unit/test_remote_service.py`, `tests/integration/test_remote_service_pipeline.py`, `tests/integration/test_ci_templates.py`, `tests/test_library_purity.py`, `tests/test_api_stability.py`  
**Target Platform**: Cross-OS (`ThreadingHTTPServer` loopback/authenticated TCP socket)  
**Project Type**: Library + CLI + Optional HTTP Service Wrapper + Consumer CI Examples  
**Performance Goals**: Zero server imports on `import evalforge_maestro` and `--help`; bounded request body cap (`max_request_bytes`); multi-threaded HTTP handling cleanly supporting concurrent requests  
**Constraints**: Zero external HTTP/ASGI runtime deps; zero `evalforge_maestro.service` or `http.server` imports in core subsystems; zero RCE (`module:symbol` forbidden over HTTP); pre-bind remote auth guard (`LocalOnlyPolicyError`); external `docpipe-maestro` repo untouched; `>=85%` global branch coverage (`100%` preserved on `metrics` and `regression.gate`)

## Constitution Check

*GATE: Passed pre-research and post-design against `.specify/memory/constitution.md` Principles I–VII.*

- **Principle I (Scope Tiebreaker)**: Passes. Service is an optional wrapper delegating strictly to library SDK and storage layers; zero server code leaks into core packages, no primary DB runtime, no document indexing/agent framework coupling, external `docpipe-maestro` untouched.
- **Principle II (Library Purity & Unidirectional Dependencies)**: Passes. Core packages (`types`, `datasets`, `adapters`, `execution`, `metrics`, `judges`, `embeddings`, `regression`, `storage`, `reporting`, `_metric_factory`) have zero imports from `service`, `http.server`, `cli`, `tomllib`, or `dotenv`. `service` never imports `cli`, `tomllib`, or `dotenv`. `"http.server"` added to `_HEAVY_OPTIONAL_MODULES` (cold-start purity list) in `tests/test_library_purity.py` + explicit AST assertions guarding against `evalforge_maestro.service` imports from core packages!
- **Principle III (Single Schema Source of Truth)**: Passes. All service config/request/response/error schemas live in `src/evalforge_maestro/types.py` with `SCHEMA_VERSION` and strict validation.
- **Principle IV (Evidence-Aware & Anomaly-Safe)**: Passes. `/v1/evaluate` and `/v1/compare` run full `QualityGate`, decoupled diagnostics, anomaly flags, and drift checks identically to CLI/SDK.
- **Principle V (Immutable Artifacts & Determinism)**: Passes. `persist=False` isolates scratch writes to `TemporaryDirectory`; `persist=True` uses `LocalRunStore.save_run` and maps `ImmutabilityError` cleanly to HTTP `409`.
- **Principle VI (Stream & Secret Hygiene)**: Passes. `ServiceConfig` stores only `auth_token_configured: bool` (never raw token); HTTP errors & logs run `scrub_secret_text` / `redact_secrets`; `serve` logs to `stderr`, never `stdout` (`NullHandler` in library).
- **Principle VII (Automated Quality Gates)**: Passes cleanly across all static, coverage (`>=85%`, `100%` on `metrics`/`regression.gate`), security, determinism/immutability, and packaging gates.

## Project Structure

### Documentation (this feature)

```text
specs/010-remote-eval-service/
├── spec.md                              # Feature specification (US1-US3 + Clarifications)
├── checklists/requirements.md           # Spec quality checklist
├── plan.md                              # This implementation plan
├── research.md                          # Architecture, security, & dependency decisions
├── data-model.md                        # Service Pydantic v2 contracts
├── quickstart.md                        # Live HTTP server, in-process & CI template quickstarts
└── contracts/
    └── service-and-ci.md                # HTTP routes, status codes, serve CLI, & CI fixtures
```

### Source Code, CI Templates & Documentation Targets

```text
src/evalforge_maestro/
├── types.py                             # ServiceConfig, ServiceHealthResponse, ServiceErrorResponse, ServiceOtelIngest*, ServiceEvaluate*, ServiceCompare*, ServiceReport*
├── _metric_factory.py                   # Shared library-pure metric instantiation & preflight checks
├── service/
│   ├── __init__.py                      # Export ServiceApplication, create_http_server, serve_http, validate_service_bind_policy
│   ├── app.py                           # Transport-agnostic ServiceApplication HTTP router & JSON envelopes
│   └── server.py                        # Lazy ThreadingHTTPServer wrapper & signal-safe serve_http
├── cli/
│   ├── targets.py                       # Delegate build_metrics_from_config & preflight to _metric_factory cleanly
│   ├── parser.py                        # `serve` subcommand (`--host`, `--port`, `--auth-token`, `--max-request-bytes`, etc.)
│   └── commands.py                      # `_handle_serve`, `_args_to_cli_overrides` key popping (`EVALFORGE_SERVICE_TOKEN` reading cleanly)
└── __init__.py                          # Export ServiceApplication and M10 types (zero http.server import)

examples/ci/
├── evalforge-hybrid-rerank.toml         # Hybrid + rerank offline retrieval/answer CI template
├── hybrid-rerank-golden.jsonl           # 3-case golden fixture (2 mandatory, 1 optional)
├── hybrid-rerank-executions.jsonl       # Aligned pre-captured executions with ranked chunks
├── calibration-samples.jsonl            # Small-judge human calibration sample fixture
└── README.md                            # Comprehensive CI adoption guide (Modes A–E + calibrate --min-agreement)

docs/
├── remote-service.md                    # Complete HTTP API reference, security model, & integration guide
├── calibration-and-ci.md                # Detailed small-judge calibrate --min-agreement & hybrid/rerank CI handbook
└── future-features.md                   # Update final post-MVP roadmap completion status
README.md                                # Document `serve`, HTTP API, calibration/hybrid templates, docs links, & M10 summary

tests/
├── contract/test_m10_schemas.py         # Strict contract tests for all Service* models
├── test_library_purity.py               # Guard zero service/http.server imports in core & cold-start
├── test_api_stability.py                # Pin M10 exports & signatures cleanly
├── unit/test_remote_service.py          # US1+US2 ServiceApplication routes, auth, 400/401/403/404/405/409/413, security & parity
├── integration/test_remote_service_pipeline.py # US2 live ThreadingHTTPServer + CLI `serve` + cold-start tests
└── integration/test_ci_templates.py     # US3 E2E execution of hybrid-rerank & calibrate --min-agreement templates
```

## Complexity Tracking

No Constitution violations or structural exceptions required.
