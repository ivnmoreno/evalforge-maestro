# Quickstart Validation Guide: Statistical & Embedding Similarity Metrics

**Feature**: `007-statistical-embedding-metrics`  
**References**: [`spec.md`](spec.md) | [`data-model.md`](data-model.md) | [`contracts/public-api-and-metrics.md`](contracts/public-api-and-metrics.md) | [`contracts/cli-and-config.md`](contracts/cli-and-config.md)

## Scenario 1 — Minimal Core Purity & `MissingExtraError`

1. Install only core package dependencies (`uv sync --frozen --no-dev` or isolated wheel install).
2. Verify cold-start `import evalforge_maestro` and `evalforge-maestro --help` leave `numpy`, `scipy`, `litellm`, and `docpipe_maestro` absent from `sys.modules`.
3. Evaluate `EmbeddingSimilarityMetric` in that environment and confirm `MissingExtraError` reports `evalforge-maestro[embeddings]`.

## Scenario 2 — Offline Deterministic `--mock` Embedding Metrics (`[embeddings]`)

```bash
uv sync --frozen --extra dev --extra embeddings
evalforge-maestro run --dataset examples/ci/golden-sample.jsonl --executions examples/ci/executions-sample.jsonl --metric embedding_similarity --metric context_embedding_similarity --mock --local-only --json
```

**Expected**:
- Runs offline with zero API keys and zero `litellm` import in `sys.modules`.
- Produces identical bounded scores (`[0.0, 1.0]`), `NOT_APPLICABLE` when ground truth is absent, and deterministic gate exit codes across repeated invocations.
- Also test `--local-only` with remote `--embedding-api-base` (expects POSIX exit code `4`).

## Scenario 3 — Paired & Multi-Run Statistical Cohort Comparison

```bash
# Execute 3 repeated baseline trials and 3 candidate trials, then compare cohorts
evalforge-maestro run --config examples/ci/evalforge.toml --repeats 3 --seed 10 --run-id base-trial --mock --local-only --json
evalforge-maestro run --config examples/ci/evalforge.toml --repeats 3 --seed 20 --run-id cand-trial --mock --local-only --json
evalforge-maestro compare cand-trial-r01 cand-trial-r02 cand-trial-r03 --baseline base-trial-r01 --baseline-run base-trial-r02 --baseline-run base-trial-r03 --confidence-level 0.95 --json
```

**Expected**:
- All 6 immutable `RunRecord` files persist cleanly without mutation.
- `compare` emits `MetricComparison.statistics` (with `welch_t_run`, `ci_low`, `ci_high`, `p_value`, `baseline_std`, `candidate_std`, `significance`) alongside per-case `case_statistics` (`paired_t_case`), rendered in both JSON and Three-Way Markdown output.
- Statistically significant regressions emit an advisory `WARNING` by default (escalating to exit code `1` under `--strict` or `--fail-on-significant-regression`).

## Scenario 4 — Repository Quality & Coverage Verification

```bash
uv run ruff format --check . && uv run ruff check . && uv run ruff check --select S src/ && uv run mypy --strict src tests
uv run pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85
uv run pytest --strict-markers -W error --cov=evalforge_maestro.regression.gate --cov-branch --cov-fail-under=100 tests/unit/test_quality_gate.py
uv run pytest --strict-markers -W error -m "gate_determinism or gate_immutability"
```
