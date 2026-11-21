# Downstream Consumer CI & Small-Judge Calibration Guide

This guide covers two critical production workflows for downstream RAG and agent repositories (such as `docpipe-maestro>=0.4.1`):

1. **Hybrid Retrieval (`fts5_hybrid`) & Cross-Encoder Reranking Quality Gates** using offline CI replay fixtures (`examples/ci/evalforge-hybrid-rerank.toml`) or live `DocpipeAdapter` targets.
2. **Small & Local Judge Calibration (`evalforge-maestro calibrate --min-agreement`)** validating that fast/low-cost judge models agree with human labels before gating pull requests.

---

## Part 1: Evaluating Hybrid FTS5 + Cross-Encoder Reranking (`docpipe-maestro`)

### 1.1 Dual-Stage CI Strategy (PR Offline vs. Nightly Live)

| Stage | Target Mode | Dependencies & Network | Recommended Cadence |
| --- | --- | --- | --- |
| **PR Gate (Fast & Deterministic)** | `ReplayAdapter` (`--executions` or `--otel-traces`) | Base `evalforge-maestro` only (`--mock --local-only`). Zero external APIs or Chroma/torch startup. | Every pull request via [`examples/ci/evalforge-ci.yml`](../examples/ci/evalforge-ci.yml). |
| **Release / Nightly Gate (Live Stack)** | `DocpipeAdapter` (`--target-type docpipe` / `[target] type = "docpipe"`) | `pip install "evalforge-maestro[docpipe-maestro]"` against versioned Chroma + FTS5 test corpus. | Nightly, release tags, or manual workflow dispatch when retriever/reranker weights change. |

### 1.2 Drop-In Hybrid + Rerank Configuration (`examples/ci/evalforge-hybrid-rerank.toml`)

The shipped template [`examples/ci/evalforge-hybrid-rerank.toml`](../examples/ci/evalforge-hybrid-rerank.toml) paired with [`examples/ci/hybrid-rerank-golden.jsonl`](../examples/ci/hybrid-rerank-golden.jsonl) and [`examples/ci/hybrid-rerank-executions.jsonl`](../examples/ci/hybrid-rerank-executions.jsonl) evaluates seven orthogonal quality dimensions simultaneously:

- **Retrieval Ranking (Deterministic, `100%` Branch Coverage)**:
  - `precision_at_k` (`k = 2`), `recall_at_k` (`k = 3`), `mrr`, and `ndcg_at_k` (`k = 3`).
  - Notice [`hybrid-rerank-golden.jsonl`](../examples/ci/hybrid-rerank-golden.jsonl) uses typed **graded relevance** labels (`{"id": "doc-hybrid-rrf", "relevance": 3}` vs `{"id": "doc-misc-bm25", ...}`), verifying that second-stage cross-encoder reranking orders high-relevance passages ahead of partial matches (`ndcg_at_k`) rather than relying purely on binary hit/miss checks.
- **Evidence Grounding & Answer Relevance**:
  - `groundedness`, `answer_relevance`, and `context_relevance` evaluate both evidence fidelity and query alignment.
- **Anti-Masking & Evidence Decoupling Diagnostics**:
  - `QualityGate` checks per-metric floors (`[gate].min_score = 0.75`) individually so high `ndcg_at_k` can never mask poor `groundedness` (`AGGREGATE_MASKED_DROP`), flags cross-metric spreads `> 0.3` (`METRIC_DISAGREEMENT`), and emits `DecoupledEvidenceDiagnostic` warnings if retrieval succeeds while generation hallucinates (`RETRIEVAL_OK_GENERATION_FAILED`) or vice versa (`GENERATION_OK_RETRIEVAL_WEAK`).

Run the hybrid/rerank CI template immediately in offline mode:

```bash
evalforge-maestro config validate --config examples/ci/evalforge-hybrid-rerank.toml --json
evalforge-maestro run \
  --config examples/ci/evalforge-hybrid-rerank.toml \
  --strict \
  --json \
  --json-out hybrid-report.json \
  --markdown-out hybrid-report.md > hybrid-stdout.json
```

### 1.3 Switching to Live `docpipe-maestro>=0.4.1` Hybrid + Rerank Evaluation

In a `docpipe-maestro` checkout with an indexed test corpus (e.g., `./.docpipe/chroma`), replace `[run].executions` with live `[target]` configuration or override directly via CLI flags:

```toml
[target]
type = "docpipe"
docpipe_mode = "answer_detailed"     # Use "retrieve" for zero-LLM retrieval-only CI gating
docpipe_collection = "docs"
docpipe_persist_dir = "./.docpipe/chroma"
docpipe_top_k = 4
docpipe_searcher = "fts5_hybrid"     # Enable BM25 FTS5 + dense vector reciprocal rank fusion
docpipe_rerank = true                # Enable second-stage cross-encoder reranking
# docpipe_embed_model = "text-embedding-3-small"
# docpipe_answer_model = "openai/glm-5.3"
# docpipe_api_base = "https://..."
```

Equivalent CLI flags allow rapid A/B comparison in CI without editing `evalforge.toml`:

```bash
# Baseline run: dense-only without rerank
evalforge-maestro run \
  --config evalforge-hybrid-rerank.toml \
  --target-type docpipe \
  --docpipe-mode retrieve \
  --docpipe-searcher default \
  --model-id docpipe-dense \
  --json > dense.json

# Pin trusted baseline alias
evalforge-maestro baseline set <DENSE_RUN_ID> --name main --json

# Candidate run: fts5_hybrid + cross-encoder reranker gated against main baseline
evalforge-maestro run \
  --config evalforge-hybrid-rerank.toml \
  --target-type docpipe \
  --docpipe-mode retrieve \
  --docpipe-searcher fts5_hybrid \
  --docpipe-rerank \
  --model-id docpipe-hybrid-rerank \
  --baseline main \
  --strict \
  --json
```

When generation is stochastic (`docpipe_mode = "answer_detailed"`), add `--repeats 3 --seed 10 --fail-on-significant-regression` so regressions fail only when statistically significant under Student's / Welch's $t$-tests rather than random single-run jitter.

> **Environment Credentials Note**: `evalforge-maestro --env-file` loads only `EVALFORGE_*` settings into CLI config; when invoking live remote `docpipe-maestro` generation models (such as `together_ai/zai-org/GLM-5.3-Flash`), export the provider key (e.g., `TOGETHERAI_API_KEY`) directly in the shell or CI environment alongside `EVALFORGE_JUDGE_API_KEY`.

---

## Part 2: Calibrating Small & Local Judges (`calibrate --min-agreement`)

Small local models (`ollama_chat/llama3.2`, `qwen2.5:1.5b-instruct`, etc.) run zero-cost inside private CI runners (`--local-only` allows loopback `http://127.0.0.1:11434`), but uncalibrated small judges frequently drift toward excessive leniency (`too_generous`) or harshness (`too_harsh`). Never promote an uncalibrated judge directly into a blocking PR gate.

### 2.1 Preparing Human Calibration Samples (`HumanCalibrationSample`)

Author a small labeled JSONL dataset containing both **clear passes** (`human_passed: true`) and **realistic failures** (subtle hallucinations, unsupported numbers, wrong citations, `human_passed: false`). See [`examples/ci/calibration-samples.jsonl`](../examples/ci/calibration-samples.jsonl):

```json
{"case_id": "cal-1", "input": "What monthly uptime SLA does EvalForge Pro guarantee?", "output": "EvalForge Pro guarantees a 99.9% monthly uptime SLA for production clusters.", "reference": "99.9% monthly uptime SLA", "retrieved_chunks": [{"id": "ctx-1", "text": "EvalForge Pro provides a 99.9% monthly uptime SLA for all production clusters.", "rank": 1}], "human_score": 0.95, "human_passed": true, "notes": "Accurate and directly grounded in retrieved SLA clause."}
{"case_id": "cal-4", "input": "Does EvalForge transmit API keys to third-party analytics endpoints?", "output": "Yes, API keys are uploaded weekly to external telemetry dashboards for debugging.", "reference": "No, secrets are scrubbed before logging, reporting, or persistence.", "retrieved_chunks": [{"id": "ctx-4", "text": "EvalForge scrubs API keys and tokens before stderr logging, report rendering, and persistence.", "rank": 1}], "human_score": 0.0, "human_passed": false, "notes": "Direct contradiction/hallucination unsupported by evidence."}
```

Schema notes for `HumanCalibrationSample`:
- Required: non-empty `case_id`, `input`, `output`, and at least one of `human_score` (`0.0..1.0`) or `human_passed` (`bool`).
- Recommended: `retrieved_chunks` (critical for calibrating `groundedness` or `context_relevance`), `reference` (for `answer_correctness`), and `notes` for triage auditing.

### 2.2 Running Calibration & Threshold Gating

```bash
# Step A: Deterministic dry-run verifying fixture pipeline in CI (mock mode)
evalforge-maestro calibrate \
  --samples examples/ci/calibration-samples.jsonl \
  --metric groundedness \
  --min-agreement 80.0 \
  --mock \
  --local-only \
  --strict \
  --json \
  --json-out calibration-report.json \
  --markdown-out calibration-report.md

# Step B: Live calibration against a local Ollama/vLLM endpoint (`[judges]` extra installed)
evalforge-maestro calibrate \
  --samples examples/ci/calibration-samples.jsonl \
  --metric groundedness \
  --judge-model ollama_chat/llama3.2:latest \
  --judge-api-base http://127.0.0.1:11434 \
  --judge-pass-threshold 0.70 \
  --human-threshold 0.50 \
  --score-divergence-threshold 0.25 \
  --min-agreement 80.0 \
  --local-only \
  --strict \
  --json \
  --markdown-out local-judge-calibration.md
```

### 2.3 Interpreting Calibration Diagnostics

| Metric / Field (`CalibrationReport`) | Meaning & Actionable Decision |
| --- | --- |
| `exact_agreement_rate` (`0.0..100.0%`) | Percentage of valid pairs where human verdict and judge pass/fail match. Fails with exit code `1` when below `--min-agreement` (in `[0..100]` scale, e.g. `80.0` for `80%`). |
| `too_generous_rate` / `too_harsh_rate` (`0.0..1.0`) | Directional bias rates: fraction of human-failing cases wrongly passed by the judge (`too_generous_rate`) vs. human-passing cases wrongly failed (`too_harsh_rate`). |
| `mean_human_score`, `mean_judge_score`, `mean_score_delta` | Mean score averages and signed delta (`mean_judge_score - mean_human_score` in `-1.0..1.0`) surfacing systemic calibration shift. |
| `recommended_pass_threshold` (`0.0..1.0`) | Deterministic candidate threshold optimizing exact verdict agreement across evaluated scores (breaking ties closest to `pass_threshold_evaluated`). Copy into `[judge].pass_threshold` or `--judge-pass-threshold` if needed. |
| `disagreements` (`too_generous`, `too_harsh`, `score_divergence`, `inconclusive`) | Per-case `CalibrationDisagreement` list recording `human_score`, `judge_score`, `score_delta`, `judge_rationale`, and `human_notes` for rubric tuning. |

### 2.4 Python SDK Calibration Loop

```python
from evalforge_maestro import (
    GroundednessMetric,
    HumanCalibrationSample,
    JudgeConfig,
    RetrievedChunk,
    build_calibration_report,
    calibrate_judge,
    render_markdown,
)

cfg = JudgeConfig(model="mock-judge", mock_mode=True, local_only=True, pass_threshold=0.7)
metric = GroundednessMetric(config=cfg)
samples = [
    HumanCalibrationSample(
        case_id="cal-ok",
        input="Uptime SLA?",
        output="EvalForge Pro guarantees 99.9% monthly uptime SLA.",
        retrieved_chunks=[RetrievedChunk(id="d1", text="99.9% monthly uptime SLA guaranteed.")],
        human_score=0.95,
        human_passed=True,
    ),
]
report = calibrate_judge(metric, samples, human_threshold=0.5)
doc = build_calibration_report(report, min_agreement=80.0, strict=True)
assert doc.calibration_gate is not None and doc.calibration_gate.passed is True
print(render_markdown(doc))
```

### 2.5 Adding Periodic Calibration to GitHub Actions

```yaml
- name: Gate judge alignment before running model-based evaluation
  run: |
    evalforge-maestro calibrate \
      --samples examples/ci/calibration-samples.jsonl \
      --metric groundedness \
      --min-agreement 80.0 \
      --mock \
      --local-only \
      --strict \
      --json \
      --markdown-out calibration-report.md > calibration-stdout.json
```

Pair `calibrate --min-agreement 80.0` ahead of judge-backed `run` steps whenever upgrading judge prompts, `custom_rubric` definitions, or local Ollama/vLLM model tags so regressions in the evaluator never silently approve failing releases.
