# Future Features & Post-MVP Roadmap

This backlog tracks capabilities deferred beyond the **v0.1.x MVP** (Milestones **M1–M5**, baseline `v0.1.4`), as referenced in [`docs/intent.md`](intent.md#L129-L133) and governed by [`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

---

## Current Baseline Status (`v0.1.4`)

- **Shipped (M1–M5):** Single Pydantic v2 schema source (`src/evalforge_maestro/types.py`), JSONL streaming `DatasetEngine`, `CallableAdapter` / `RAGAdapter` / lazy `DocpipeAdapter` (`docpipe-maestro>=0.4.1`) / offline `ReplayAdapter`, deterministic text/JSON Schema/IR metrics (`100%` branch coverage), baseline/trend/anomaly/drift gating (`100%` branch coverage on `QualityGate`), LiteLLM + `--mock` judge and human calibration engine, and CLI + Three-Way Markdown/JSON reporting (`evalforge-maestro` / `evalforge_maestro`).
- **Reserved Contract Hooks Ready for M6:**
  - `EvaluationCase.expected_tools: list[dict[str, Any]] | None`
  - `ExecutionResult.trace: list[dict[str, Any]]`
  - `ExecutionResult.tool_calls: list[dict[str, Any]]`

---

## Near-Term Operational & Ergonomic Queue (Pre-M6 / `v0.1.x` Polish)

1. **Consumer Adoption (`evalforge-maestro>=0.1.4` CI Templates):**
   - Adopt [`examples/ci/evalforge-ci.yml`](../examples/ci/evalforge-ci.yml) and `examples/ci/evalforge.toml` inside consumer repositories (starting with `docpipe-maestro`) to gate PRs offline (`--mock --local-only`) and publish `$GITHUB_STEP_SUMMARY` reports.
2. **GitHub Actions Runner Hygiene (Node 24 Transition):**
   - Upgrade workflow actions (`actions/checkout`, `actions/upload-artifact`, `actions/download-artifact`, `astral-sh/setup-uv`, `actions/setup-python`) across `.github/workflows/` and `examples/ci/` to Node 24-native versions, and mute empty-workdir `setup-uv` cache warnings on `verify-testpypi`.
3. **Dogfooding Findings from `v0.1.0`–`v0.1.4` Live Runs:**
   - **Small Local Judge Calibration:** Live calibration against `ollama_chat/qwen2.5:1.5b-instruct` showed contradictory numeric hallucinations are caught reliably, while additive ungrounded clauses can receive false passes (`too_generous`). Promote explicit `calibrate --min-agreement` gating workflows for small local models.
   - **Offline Fixture Alignment:** Extend `examples/ci/` or golden samples when testing downstream Docpipe hybrid/rerank features (`--docpipe-searcher fts5_hybrid --docpipe-rerank`).
   - **Optional Custom Rubric TOML Ergonomics:** Document or simplify multi-rubric parameters under `[metrics.<name>]` in `evalforge.toml`.

---

## Milestone M6 — Agent Trace Evaluation (`006-agent-trace-evaluation`, target `v0.2.0`)

Implements Domain 4 from [`docs/intent.md`](intent.md#L116) while upholding Constitution Principle IV (*process vs. outcome decoupling*):

- **Typed Trace & Tool Contracts (`src/evalforge_maestro/types.py`):**
  - Replace/augment generic `dict[str, Any]` shapes inside `expected_tools`, `tool_calls`, and `trace` with strict Pydantic v2 step/tool models (preserving `schema_version` backward compatibility).
- **Deterministic Agent Metrics (`src/evalforge_maestro/metrics/`):**
  - **Tool Selection Accuracy & Recall:** Expected vs. actual tool names (ordered and unordered matching).
  - **Argument Correctness:** Exact, normalized, and JSON Schema structural matching on tool call arguments.
  - **Execution Sequence & Efficiency:** Prefix/subsequence constraint checks and excessive/redundant tool-loop detection (`max_steps`, repeated identical failing calls).
  - **Policy Compliance & Failure Recovery:** Forbidden-tool / guardrail assertions and recovery-after-tool-error scoring decoupled from final answer text.
  - Maintain `100%` branch coverage and `metric_version` AST/hash contract guards on all new deterministic metrics.
- **Agent Adapters & Trace Importers (`src/evalforge_maestro/adapters/`):**
  - Normalized trace adapters behind optional lazy extras (avoiding core vendor lock-in per Constitution Scope Tiebreaker).
  - Offline JSONL trace replay alignment covering `tool_calls` and `trace`.
- **Diagnostics & Three-Way Reporting Extensions (`src/evalforge_maestro/reporting/`):**
  - Decouple *"right final answer despite unsafe/invalid tool trace"* from *"valid tool trace with failed final synthesis"* cleanly in `ReportDiagnosticsSummary` and Markdown reports.

---

## Post-M6 Deferred Capabilities (Future Minor Releases)

1. **Statistical & Embedding Similarity Metrics (`[embeddings]`):**
   - Local/remote embedding cosine similarity (lazy-loaded behind `[embeddings]` optional extra per Constitution Technical Constraints, keeping cold-start imports free of `numpy`/`scipy`).
   - Multi-run statistical distribution comparisons (confidence intervals / significance flags for comparing non-deterministic runs beyond simple mean deltas).
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
