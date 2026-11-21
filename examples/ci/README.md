# Consumer CI Templates

Drop-in configuration templates, sample datasets, calibration fixtures, and GitHub Actions workflows for integrating automated offline and live quality gates into downstream repositories using `evalforge-maestro`.

## Template Inventory

| File | Purpose | Mode |
| --- | --- | --- |
| [`evalforge-ci.yml`](evalforge-ci.yml) | Pull-request workflow validating config, executing offline gate (`--mock --local-only --strict`), posting Markdown reports to `$GITHUB_STEP_SUMMARY`, and uploading JSON/Markdown artifacts. | Offline CI Gate |
| [`evalforge.toml`](evalforge.toml) | Pre-recorded replay gate (`ReplayAdapter` via `--executions`) scoring `normalized_match`, `precision_at_k`, `recall_at_k`, and deterministic mock `groundedness`. | Mode A: Replay JSONL |
| [`evalforge-docpipe.toml`](evalforge-docpipe.toml) | Direct `docpipe-maestro>=0.4.1` retrieval gate (`docpipe_mode = "retrieve"`, `docpipe_searcher = "fts5_hybrid"`) scoring `precision_at_k`, `recall_at_k`, and `mrr`. | Mode B: Live Docpipe |
| [`evalforge-otel.toml`](evalforge-otel.toml) | OpenTelemetry trace replay gate (`[run].otel_traces` + `[otel]`) scoring `normalized_match`, `precision_at_k`, `recall_at_k`, `tool_selection`, and `policy_compliance`. | Mode C: OTel Export |
| [`evalforge-hybrid-rerank.toml`](evalforge-hybrid-rerank.toml) | Hybrid FTS5 + cross-encoder rerank retrieval & RAG quality gate scoring graded `ndcg_at_k`, `precision_at_k`, `recall_at_k`, `mrr`, `groundedness`, `answer_relevance`, and `context_relevance` (with documented live `[target] docpipe` swap-in). | Mode D: Hybrid + Rerank |
| [`golden-sample.jsonl`](golden-sample.jsonl) | 3-case golden evaluation dataset (`ci-1` mandatory SLA, `ci-2` mandatory refunds, `ci-3` optional security). | Shared Fixture |
| [`executions-sample.jsonl`](executions-sample.jsonl) | Pre-recorded `ExecutionResult` replay records aligned 1:1 with `golden-sample.jsonl`. | Mode A Fixture |
| [`otel-traces-sample.json`](otel-traces-sample.json) | OTLP `ExportTraceServiceRequest` span bundle aligned 1:1 with `golden-sample.jsonl`. | Mode C Fixture |
| [`hybrid-rerank-golden.jsonl`](hybrid-rerank-golden.jsonl) | 4 graded-relevance (`relevance: 1..3`) RAG golden cases testing hybrid fusion and cross-encoder reranking. | Mode D Fixture |
| [`hybrid-rerank-executions.jsonl`](hybrid-rerank-executions.jsonl) | Pre-captured reranked `ExecutionResult` records aligned 1:1 with `hybrid-rerank-golden.jsonl`. | Mode D Fixture |
| [`calibration-samples.jsonl`](calibration-samples.jsonl) | 4 human-labeled `HumanCalibrationSample` cases (`true` + hallucinated `false`) for `calibrate --min-agreement 80.0` verification. | Judge Calibration Fixture |

---

## Adoption Patterns

### Mode A: Offline Replay Gate (`--executions`)

Recommended when your integration test suite or staging job emits `executions.jsonl` (`ExecutionResult` JSONL records) before gating:

1. Copy [`evalforge-ci.yml`](evalforge-ci.yml) into `.github/workflows/evalforge-ci.yml`.
2. Copy [`evalforge.toml`](evalforge.toml), your golden dataset JSONL, and captured `executions.jsonl`.
3. Validate configuration and execute offline:

```bash
evalforge-maestro config validate --config examples/ci/evalforge.toml --json
evalforge-maestro run \
  --config examples/ci/evalforge.toml \
  --mock \
  --local-only \
  --strict \
  --json \
  --json-out evalforge-report.json \
  --markdown-out evalforge-report.md > evalforge-stdout.json
```

### Mode B: Direct `DocpipeAdapter` Gate (`[docpipe-maestro]`)

Recommended when evaluating a live `docpipe-maestro>=0.4.1` checkout or persistent vector index (`pip install "evalforge-maestro[docpipe-maestro]"`):

1. Copy [`evalforge-docpipe.toml`](evalforge-docpipe.toml) into your repository root (or `--config` path).
2. Mount or populate the fixture Chroma/FTS index at `docpipe_persist_dir` for `docpipe_collection`.
3. Run:

```bash
evalforge-maestro config validate --config examples/ci/evalforge-docpipe.toml --json
evalforge-maestro run \
  --config examples/ci/evalforge-docpipe.toml \
  --strict \
  --json \
  --json-out docpipe-report.json \
  --markdown-out docpipe-report.md > docpipe-stdout.json
```

Use `--docpipe-mode retrieve` for fast zero-LLM retrieval gating, or `--docpipe-mode answer_detailed` with `--docpipe-answer-model` and `--docpipe-api-base` for full RAG generation evaluation.

### Mode C: OpenTelemetry Trace Replay Gate (`--otel-traces` / `ingest-otel`)

Recommended when your agent or RAG service exports OTLP JSON, flat span arrays, or JSONL span streams during CI integration tests (with **zero** runtime OTel dependencies required):

1. Copy [`evalforge-otel.toml`](evalforge-otel.toml) alongside your golden dataset and captured OTel span export (or test immediately against [`otel-traces-sample.json`](otel-traces-sample.json)).
2. Evaluate directly via `run --otel-traces`:

```bash
evalforge-maestro config validate --config examples/ci/evalforge-otel.toml --json
evalforge-maestro run \
  --config examples/ci/evalforge-otel.toml \
  --strict \
  --json \
  --json-out otel-report.json \
  --markdown-out otel-report.md > otel-stdout.json
```

3. Or pre-normalize OTel spans into replayable secret-scrubbed `ExecutionResult` JSONL with `ingest-otel` for downstream archiving or `--executions` reuse:

```bash
evalforge-maestro ingest-otel examples/ci/otel-traces-sample.json \
  --dataset examples/ci/golden-sample.jsonl \
  --output executions-normalized.jsonl \
  --json
```

See [`docs/otel-ingestion.md`](../../docs/otel-ingestion.md) for attribute precedence across GenAI, OpenInference, and Traceloop conventions, tool-call deduplication, and custom `[otel]` extractors.

### Mode D: Hybrid FTS5 + Rerank Retrieval & RAG Gate + Judge Calibration

Recommended when validating `docpipe-maestro` hybrid retrieval (`fts5_hybrid`) with second-stage cross-encoder reranking (`docpipe_rerank = true`) using graded `ndcg_at_k` plus grounding diagnostics, or gating small local judges before CI rollout:

```bash
# 1. Offline hybrid/rerank CI gate (or swap in [target] type="docpipe" for live evaluation)
evalforge-maestro config validate --config examples/ci/evalforge-hybrid-rerank.toml --json
evalforge-maestro run \
  --config examples/ci/evalforge-hybrid-rerank.toml \
  --strict \
  --json \
  --json-out hybrid-report.json \
  --markdown-out hybrid-report.md > hybrid-stdout.json

# 2. Validate judge agreement against human labels (--min-agreement expects [0..100]%)
evalforge-maestro calibrate \
  --samples examples/ci/calibration-samples.jsonl \
  --metric groundedness \
  --min-agreement 80.0 \
  --mock \
  --local-only \
  --strict \
  --json \
  --json-out calibration-report.json \
  --markdown-out calibration-report.md > calibration-stdout.json
```

See [`docs/calibration-and-ci.md`](../../docs/calibration-and-ci.md) for live `docpipe_searcher = "fts5_hybrid"` / `docpipe_rerank = true` swap-in recipes, Student's / Welch's $t$-test cohort flags, and local judge threshold sweeps.

---

## Regression Baselines, Cohorts & Exit Codes

- **Baseline Pinning**: Restore `.evalforge/` via CI cache on `main`, pin trusted runs via `evalforge-maestro baseline set <RUN_ID> --name main --json`, and pass `--baseline main` to enforce `max_regression_drop`.
- **Statistical Cohorts**: For stochastic LLM/agent workflows, pass `--repeats 3 --seed 10 --baseline main --fail-on-significant-regression` to run Student's / Welch's $t$-tests across repeated trials.
- **POSIX Exit Codes**:
  - `0`: Gate `PASS` (or `WARNING` / `INCONCLUSIVE` when `--strict` is disabled).
  - `1`: Gate `FAIL` (threshold breach, mandatory failure, regression violation, `WARNING` / `INCONCLUSIVE` escalated by `--strict`, or `calibrate` agreement below `--min-agreement`).
  - `2`: Invalid CLI flags, TOML / `.env` configuration error, dataset schema fault, replay alignment mismatch, or missing OTel `case_id` correlation.
  - `3`: Runtime adapter/judge failure or missing optional extra (`MissingExtraError`).
  - `4`: Security/locality violation (`--local-only`, `--block-pii` pre-network block, or unauthenticated non-loopback `serve --host ...`).
