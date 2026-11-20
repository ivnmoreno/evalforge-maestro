# EvalForge Maestro

**Evaluate. Compare. Verify.**

> *"EvalForge Maestro is an independent evaluation and regression verification engine — never an LLM runtime, RAG indexer, or agent framework."*

## Installation

```bash
pip install evalforge-maestro
# With optional docpipe-maestro integration:
pip install "evalforge-maestro[docpipe]"
# With optional LiteLLM model-based judges:
pip install "evalforge-maestro[judges]"
```

For contributor development using [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
```

## Quickstart (CLI)

Both `evalforge-maestro` and `evalforge_maestro` console commands are installed:

```bash
# Run offline deterministic + mock judge evaluation cleanly in CI or locally
evalforge-maestro run \
  --config examples/ci/evalforge.toml \
  --mock \
  --local-only \
  --strict \
  --json \
  --json-out report.json \
  --markdown-out report.md

# Pin a trusted baseline without mutating immutable run records
evalforge-maestro baseline set <RUN_ID> --name release-v1 --json

# Compare a candidate run against a pinned baseline
evalforge-maestro compare <CANDIDATE_RUN_ID> --baseline release-v1 --strict --json

# Inspect multi-run sliding OLS trends
evalforge-maestro trend --window 5 --json

# Calibrate a judge against human ground-truth samples
evalforge-maestro calibrate --samples cal-samples.jsonl --metric groundedness --mock --local-only --json

# Export Markdown/JSON diagnostic reports from stored artifacts
evalforge-maestro report --run <RUN_ID> --baseline release-v1 > diagnostic-report.md

# Audit effective resolved config across precedence tiers (secrets always masked)
evalforge-maestro config show --resolved
```

### Configuration Precedence & Streams

- **Precedence**: `CLI flags > OS environment (EVALFORGE_*) > opt-in --env-file <path> > non-recursive CWD evalforge.toml > Built-in defaults`.
- **Streams**: `--json` emits strictly one schema-validated JSON document on `stdout`; diagnostics, warnings, and `--log-json` / `--log-level` logs write strictly to `stderr`. Default non-`--json` runs write Markdown summaries to `stdout` (suppressible via `--quiet`).
- **POSIX Exit Codes**:
  - `0`: Gate `PASS` (or `WARNING`/`INCONCLUSIVE` when `--strict` is disabled), diagnostic `calibrate`, or management commands.
  - `1`: Gate `FAIL` (mandatory failure, threshold breach, excessive regression, or `--strict` escalating `WARNING`/`INCONCLUSIVE`).
  - `2`: CLI argument, `evalforge.toml` / `--env-file` configuration, replay alignment, missing run/baseline, or dataset/schema validation error.
  - `3`: Adapter, judge, or missing-extra runtime failure (`--fail-fast`, `MissingExtraError`, or zero cases completed).
  - `4`: Security or locality policy violation (`--local-only` endpoint block or `--block-pii` pre-network egress block).

## Quickstart (Python SDK)

```python
from evalforge_maestro import (
    DatasetEngine,
    EvaluationOrchestrator,
    PrecisionAtKMetric,
    RAGAdapter,
    RecallAtKMetric,
    exact_match,
)

dataset = DatasetEngine(
    [
        {
            "id": "q1",
            "input": "What is the capital of France?",
            "reference": "Paris",
            "expected_context": ["doc-paris"],
        }
    ]
)

adapter = RAGAdapter(
    lambda q: {
        "answer": "Paris",
        "chunks": [{"id": "doc-paris", "text": "Paris is the capital of France."}],
    }
)

run = EvaluationOrchestrator().run(
    dataset,
    adapter,
    [exact_match, PrecisionAtKMetric(k=1), RecallAtKMetric(k=1)],
)
print(run.aggregates["recall_at_k"].mean_score)
```

## GitHub Actions CI Template

Copy [`examples/ci/evalforge-ci.yml`](examples/ci/evalforge-ci.yml) and [`examples/ci/evalforge.toml`](examples/ci/evalforge.toml) (for offline `--executions` replay) or [`examples/ci/evalforge-docpipe.toml`](examples/ci/evalforge-docpipe.toml) (for `[docpipe]` retrieval gating) into your project to gate pull requests offline (`--mock --local-only`) and publish Markdown summaries directly to `$GITHUB_STEP_SUMMARY`. See [`examples/ci/README.md`](examples/ci/README.md) for consumer setup details.

## Implemented Milestones (M1–M6)

- **M1 — Evaluation Foundation (`001-evaluation-foundation`)**: Single Pydantic v2 schema source (`evalforge_maestro.types`), lazy JSONL streaming `DatasetEngine`, `CallableAdapter`, deterministic text/JSON Schema metrics (`exact_match`, `normalized_match`, `json_schema_validation`), bounded async `EvaluationOrchestrator`, and atomic `0o700`/`0o600` `.evalforge/` storage.
- **M2 — Retrieval & RAG Evaluation (`002-retrieval-rag-evaluation`)**: Protocol-based `RAGAdapter`, lazy `DocpipeAdapter` (`[docpipe]`), dependency-free fixture importer, and versioned IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`) with AST formula verification.
- **M3 — Experiment & Regression Engine (`003-experiment-regression-engine`)**: Pinned baseline aliases, pairwise aggregate/per-case comparisons, sliding-window OLS trend slopes (`analyze_trend`), anti-masking/disagreement anomalies (`> 0.3` divergence), provenance drift alerts, and deterministic `QualityGate`.
- **M4 — Model-Based Judge & Calibration Engine (`004-judge-calibration-engine`)**: Lazy LiteLLM gateway (`[judges]`), pre-network `--local-only` & `LITELLM_LOCAL_MODEL_COST_MAP` air-gap safety, randomized XML/nonce prompt-injection delimiting, offline `--mock` scoring, context-grouped bounded async batching, and human calibration (`calibrate_judge` / `CalibrationReport`).
- **M5 — CLI, Reporting & CI Integration (`005-cli-reporting-ci`)**: Dual CLI entrypoints (`evalforge-maestro` / `evalforge_maestro`) with seven subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`), offline `ReplayAdapter`, opt-in `--block-pii` egress guard, library-pure `evalforge_maestro.reporting` (`ReportDocument` JSON & Three-Way Markdown separating Evaluation, Regression, and Quality Gate + retrieval-vs-answer decoupling diagnostics), and copy-ready CI workflow templates.
- **M6 — Agent Trace Evaluation (`006-agent-trace-evaluation`)**: Backward-compatible typed trace/tool contracts (`ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`), six `100%`-branch-covered deterministic agent metrics (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`), dependency-free `AgentAdapter` + structural OpenAI/Anthropic trace normalizers, CLI `--target-type agent` support, field-level post-scoring `max_context_chars` trace truncation, and decoupled trace-vs-answer diagnostics.

## CI/CD & PyPI Trusted Publishing Setup

- **CI Pipeline (`.github/workflows/ci.yml`)**: Enforces `uv lock --check`, `ruff format --check`, `ruff check`, Bandit `S` checks, `mypy --strict`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`, `@pytest.mark.gate_determinism` / `@pytest.mark.gate_immutability`, `pip-audit`, `cz check`, cross-OS testing (`ubuntu-latest`, `macos-latest`, `windows-latest`), `uv build` + `twine check --strict`, clean-venv wheel/sdist installs + CLI cold-start smoke checks, and `--no-dev` `MissingExtraError` isolation.
- **Release Pipeline (`.github/workflows/release.yml`)**: Triggered on `v*` tags; re-runs all verification gates, verifies `hatch-vcs` wheel version matches the Git tag, publishes via OIDC Trusted Publishing (`id-token: write`) to `TestPyPI`, validates clean wheel + CLI entrypoint installation from `TestPyPI`, promotes to `PyPI`, and creates the GitHub Release.
  - One-time repository prerequisite before pushing the first `v*` tag: configure GitHub environments named `testpypi` and `pypi` and register matching OIDC Trusted Publishers on `test.pypi.org` and `pypi.org` targeting `.github/workflows/release.yml`.
