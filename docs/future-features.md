# Future Features & Post-MVP Roadmap

This backlog tracks capabilities beyond the **v0.1.x MVP** (Milestones **M1–M5**, baseline `v0.1.4`), as referenced in [`docs/intent.md`](intent.md#L129-L133) and governed by [`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

---

## Current Baseline Status (M1–M6 + Features `007`–`010` Shipped)

- **Shipped in `evalforge-maestro` (M1–M6 + Features `007`–`010`):**
  - **M1–M5**: Single Pydantic v2 schema source (`src/evalforge_maestro/types.py`), JSONL streaming `DatasetEngine`, `CallableAdapter` / `RAGAdapter` / lazy `DocpipeAdapter` (`docpipe-maestro>=0.4.1`) / offline `ReplayAdapter`, deterministic text/JSON Schema/IR metrics (`100%` branch coverage), baseline/trend/anomaly/drift gating (`100%` branch coverage on `QualityGate`), LiteLLM + `--mock` judge and human calibration engine, and CLI + Three-Way Markdown/JSON reporting (`evalforge-maestro` / `evalforge_maestro`).
  - **M6 (`006-agent-trace-evaluation`):** Typed trace/tool contracts (`ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`), six `100%`-branch-covered deterministic agent metrics (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`), `AgentAdapter` with OpenAI/Anthropic trace normalization, CLI `--target-type agent`, post-scoring `max_context_chars` truncation, and trace-vs-answer decoupling diagnostics.
  - **Feature `007` (`007-statistical-embedding-metrics`):** Lazy `[embeddings]` extra (`numpy` + `litellm`) powering `EmbeddingSimilarityMetric` and `ContextEmbeddingSimilarityMetric`, pure-stdlib Student's $t$ / Welch's $t$ / one-sample $t$ significance & confidence intervals (`compare_runs`, `compare_run_cohorts`, `build_pooled_cohort_run`), `--repeats` immutable cohorts, and `QualityGate.evaluate_cohort` (`100%` branch coverage).
  - **Feature `008` (`008-otel-trace-ingestion`):** Zero-dependency OpenTelemetry ingestion (`ingest_otel_spans`, `load_otel_executions`, `ReplayAdapter.from_otel_file`, `OtelExtractorConfig`), normalizing OTLP JSON, flat span arrays, JSONL spans, and duck-typed SDK `ReadableSpan` objects across GenAI/OpenInference/Traceloop conventions into secret-scrubbed canonical `ExecutionResult` traces, plus `[otel]` / `[run].otel_traces` config precedence, `evalforge-maestro run --otel-traces`, and `evalforge-maestro ingest-otel`.
  - **Feature `009` (`009-sqlite-query-index`):** Rebuildable local `SQLiteRunIndex` (`evalforge_maestro.storage`) derived strictly from immutable canonical `.evalforge/runs/<run_id>.json`, `manifest.jsonl`, and `baselines.json` with atomic `os.replace` builds, deletion/corruption auto-recovery, parameterized `query_runs` / `query_cases` / `metric_history`, and CLI `evalforge-maestro index` / `query` subcommands.
  - **Feature `010` (`010-remote-eval-service`):**
    - **Optional Remote Evaluation Service**: Library-pure `ServiceApplication` (`evalforge_maestro.service.app`) + lazy stdlib `ThreadingHTTPServer` (`create_http_server`, `serve_http`) and CLI `evalforge-maestro serve` enforcing pre-bind remote auth guards (`validate_service_bind_policy`), constant-time Bearer auth, `local_only=True` defaults, `max_request_bytes` (`HTTP 413`), secret scrubbing, and zero `http.server` leakage into core packages.
    - **Hybrid/Rerank CI Fixtures & Small-Judge Calibration Guides**: Added `examples/ci/evalforge-hybrid-rerank.toml`, `hybrid-rerank-golden.jsonl`, `hybrid-rerank-executions.jsonl`, and `calibration-samples.jsonl` verified end-to-end, documented across [`docs/calibration-and-ci.md`](calibration-and-ci.md) and [`docs/remote-service.md`](remote-service.md).

---

## Remaining External Repository Follow-Up (Outside `evalforge-maestro`)

- **Downstream `docpipe-maestro` Repository Integration**: External repositories such as `docpipe-maestro` can directly adopt [`examples/ci/evalforge-ci.yml`](../examples/ci/evalforge-ci.yml), [`examples/ci/evalforge-hybrid-rerank.toml`](../examples/ci/evalforge-hybrid-rerank.toml), and `calibrate --min-agreement` workflows following [`docs/calibration-and-ci.md`](calibration-and-ci.md) without changes to `evalforge-maestro` core packages.

---

## Explicitly Excluded (Permanent Boundaries per Constitution Principle I)

- Document parsing, text chunking, embedding index management, or production RAG execution (`docpipe-maestro` owns runtime RAG).
- Agent orchestration loops, production prompt routing, or hard coupling to LangChain/LlamaIndex/vendor SDKs.
- Hosting model weights or running a primary system-of-record database.
