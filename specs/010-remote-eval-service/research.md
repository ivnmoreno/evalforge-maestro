# Research & Architectural Decisions: Feature 010 (`010-remote-eval-service`)

**Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

## Decisions Resolved

1. **Decoupled Transport-Agnostic Kernel + Lazy Stdlib `ThreadingHTTPServer`**
   - **Decision**: Separate request routing/validation (`ServiceApplication` in `service/app.py`) from socket transport (`create_http_server`, `serve_http` in `service/server.py`). Import `http.server` lazily inside `service/server.py` functions and enforce `"http.server"` absence during cold-start tests in `tests/test_library_purity.py`.
   - **Rationale**: Preserves core package minimalism (zero FastAPI/Starlette/Uvicorn dependency bloat or PyPI CVE surface), passes AST/cold-start checks even with top-level imports, and enables deterministic in-process unit tests alongside real multi-threaded loopback HTTP integration tests.

2. **Fail-Closed Remote Security Posture (`LocalOnlyPolicyError`, `hmac.compare_digest`, Body Caps, Safe IDs)**
   - **Decision**:
     - Treat `host` outside loopback (`127.0.0.1`, `localhost`, `::1`, `[::1]`) as remote; reject pre-socket-bind with `LocalOnlyPolicyError` (CLI exit code `4`) unless an explicit non-empty `auth_token` is supplied.
     - Verify `Authorization: Bearer <token>` using `hmac.compare_digest` cleanly on every endpoint (returning `401 Unauthorized` when missing/invalid whenever `auth_token` is configured; or opt-in health exempt? Keep `/health` consistent or authenticated when `auth_token` is set—simplest, safest, least surprising rule: when `auth_token` is configured, **all** HTTP routes including `/health` require `Authorization: Bearer <token>` so zero internal metadata leaks to unauthenticated callers!).
     - Enforce `max_request_bytes` (`1..50_000_000`, default `10_485_760` = 10 MiB) before parsing JSON bodies (`413 Payload Too Large`).
     - Restrict `ServiceEvaluateRequest` strictly to inline `cases` + `executions` / `otel_payload` (no arbitrary Python `module:symbol` loading or server-side filesystem paths over HTTP).
     - Validate all URL path identifiers (`run_id`, `metric_id`, `baseline_name`) cleanly (`400 Bad Request` on `..` or disallowed chars).

3. **Zero-Duplication Metric & Security Preflight Layer (`_metric_factory.py`)**
   - **Decision**: Extract `_construct_single_metric`, `_build_judge_config`, `_build_embedding_config`, `build_metrics_for_settings`, and `preflight_metric_security` into library-pure `src/evalforge_maestro/_metric_factory.py` (no imports of `cli`, `adapters`, `service`, `tomllib`, or `dotenv`), and have both `cli/targets.py` and `service/app.py` call it.
   - **Rationale**: Eliminates duplicated metric-factory logic across CLI and HTTP while strictly honoring Constitution Principle II unidirectional dependencies (`metrics`/`judges`/`embeddings` stay untouched; core packages never import `service` or `cli`).

4. **Hybrid/Rerank CI Templates & `calibrate --min-agreement` Small-Judge Workflows**
   - **Decision**: Add `examples/ci/evalforge-hybrid-rerank.toml`, `examples/ci/hybrid-rerank-golden.jsonl`, `examples/ci/hybrid-rerank-executions.jsonl`, and `examples/ci/calibration-samples.jsonl` alongside dedicated documentation (`docs/remote-service.md`, `docs/calibration-and-ci.md`, expanded `examples/ci/README.md`).
   - **Rationale**: Satisfies item 1 of `docs/future-features.md` completely inside `evalforge-maestro` with verifiable end-to-end tests while leaving the external `docpipe-maestro` checkout clean.
