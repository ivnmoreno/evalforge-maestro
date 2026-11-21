# Future Features & Post-MVP Roadmap

This backlog tracks capabilities deferred beyond the **v0.1.x MVP** (Milestones **M1–M5**, baseline `v0.1.4`), as referenced in [`docs/intent.md`](intent.md#L129-L133) and governed by [`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

---

## Current Baseline Status (Post-M6 / Feature `007-statistical-embedding-metrics`)

- **Shipped (M1–M6 + Feature `007`):**
  - **M1–M5**: Single Pydantic v2 schema source (`src/evalforge_maestro/types.py`), JSONL streaming `DatasetEngine`, `CallableAdapter` / `RAGAdapter` / lazy `DocpipeAdapter` (`docpipe-maestro>=0.4.1`) / offline `ReplayAdapter`, deterministic text/JSON Schema/IR metrics (`100%` branch coverage), baseline/trend/anomaly/drift gating (`100%` branch coverage on `QualityGate`), LiteLLM + `--mock` judge and human calibration engine, and CLI + Three-Way Markdown/JSON reporting (`evalforge-maestro` / `evalforge_maestro`).
  - **M6 (`006-agent-trace-evaluation`):** Typed trace/tool contracts (`ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`), six `100%`-branch-covered deterministic agent metrics (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`), `AgentAdapter` with OpenAI/Anthropic trace normalization, CLI `--target-type agent`, post-scoring `max_context_chars` truncation, and trace-vs-answer decoupling diagnostics.
  - **Feature `007` (`007-statistical-embedding-metrics`):** Lazy `[embeddings]` extra (`numpy` + `litellm`) powering `EmbeddingSimilarityMetric` and `ContextEmbeddingSimilarityMetric`, pure-stdlib Student's $t$ / Welch's $t$ / one-sample $t$ significance & confidence intervals (`compare_runs`, `compare_run_cohorts`, `build_pooled_cohort_run`), `--repeats` immutable cohorts, and `QualityGate.evaluate_cohort` (`100%` branch coverage).

---

## Remaining Operational & Post-M6 Deferred Capabilities

1. **Downstream `docpipe-maestro` CI Adoption & Small-Judge Calibration Workflow Guidance:**
   - Adopt [`examples/ci/evalforge-ci.yml`](../examples/ci/evalforge-ci.yml) inside `docpipe-maestro`, add hybrid/rerank offline fixtures, and promote `calibrate --min-agreement` gating workflows for small local models.
2. **OpenTelemetry Execution Trace Ingestion:**
   - Normalized span/event importers mapping OTel LLM/tool spans into canonical `ExecutionResult.trace` and `tool_calls` records without coupling core orchestration to an OTel backend.
3. **Rebuildable Local SQLite Query Index:**
   - Optional local SQLite read/query index built strictly from immutable canonical `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` artifacts (retaining canonical JSON as the single source of truth).
4. **Remote Evaluation Service (Strict Scope Boundary):**
   - Optional HTTP API wrapper delegating strictly to the library-pure SDK and storage layers (excluded until local/CI batch workflows settle, never leaking server concerns into core library packages).

---

## Explicitly Excluded (Permanent Boundaries per Constitution Principle I)

- Document parsing, text chunking, embedding index management, or production RAG execution (`docpipe-maestro` owns runtime RAG).
- Agent orchestration loops, production prompt routing, or hard coupling to LangChain/LlamaIndex/vendor SDKs.
- Hosting model weights or running a primary system-of-record database.
