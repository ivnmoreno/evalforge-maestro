# Consumer CI Templates

Drop-in templates for adding automated offline evaluation quality gates to downstream repositories with `evalforge-maestro>=0.1.4`.

## Files

- [`evalforge-ci.yml`](evalforge-ci.yml): GitHub Actions pull-request workflow validating `evalforge.toml`, running offline evaluation (`--mock --local-only --strict`), posting Markdown reports to `$GITHUB_STEP_SUMMARY`, and uploading `evalforge-report.json` / `evalforge-report.md`.
- [`evalforge.toml`](evalforge.toml): Offline replay configuration (`ReplayAdapter` via `--executions`) scoring `normalized_match`, `precision_at_k`, `recall_at_k`, and deterministic mock `groundedness`.
- [`evalforge-docpipe.toml`](evalforge-docpipe.toml): Direct `docpipe-maestro>=0.4.1` retrieval configuration (`[target] type = "docpipe"`, `docpipe_mode = "retrieve"`, `docpipe_searcher = "fts5_hybrid"`) scoring deterministic `precision_at_k`, `recall_at_k`, and `mrr`.
- [`golden-sample.jsonl`](golden-sample.jsonl) & [`executions-sample.jsonl`](executions-sample.jsonl): Minimal golden dataset and pre-recorded execution trace fixtures for smoke-testing Mode A offline.

## Adoption Patterns

### Mode A: Offline Replay Gate (`--executions`)

Best when your repository generates `executions.jsonl` in an earlier CI step or stores pre-captured traces alongside a golden dataset (`pip install "evalforge-maestro>=0.1.4"`):

1. Copy `evalforge-ci.yml` into `.github/workflows/evalforge-ci.yml`.
2. Copy and customize `evalforge.toml`, `golden.jsonl`, and `executions.jsonl` (adjust `--config`, `--dataset`, and `--executions` paths inside the workflow).
3. Keep `--mock --local-only --strict` so CI runs offline with zero external LLM calls and escalates `WARNING` / `INCONCLUSIVE` outcomes to exit code `1`.

### Mode B: Direct `DocpipeAdapter` Gate (`[docpipe]`)

Best when evaluating a live `docpipe-maestro>=0.4.1` checkout or persistent Chroma store (`pip install "evalforge-maestro[docpipe]>=0.1.4"`):

1. Copy [`evalforge-docpipe.toml`](evalforge-docpipe.toml) into your repository (for example `evalforge.toml`).
2. Populate or mount a deterministic fixture index at `docpipe_persist_dir` for `docpipe_collection` during CI setup, then run:

```bash
evalforge-maestro config validate --config evalforge.toml --json
evalforge-maestro run --config evalforge.toml --strict --json --json-out evalforge-report.json --markdown-out evalforge-report.md > evalforge-stdout.json
```

3. Use `--target-type docpipe` / `--docpipe-mode retrieve` (or `answer_detailed` with `--mock --local-only` or a local Ollama endpoint via `--docpipe-answer-model` and `--docpipe-api-base`) to override TOML settings from CLI flags or `EVALFORGE_DOCPIPE_*` environment variables.

## Regression Baselines & Exit Codes

- Cache or restore `.evalforge/` across runs and pin trusted runs with `evalforge-maestro baseline set <RUN_ID> --name main --json`, then pass `--baseline main` to `run` or `compare` to enforce `max_regression_drop`.
- Standard POSIX exit codes in CI: `0` (`PASS`), `1` (`FAIL`, or `WARNING` / `INCONCLUSIVE` under `--strict`), `2` (config/dataset/replay alignment error), `3` (runtime or missing optional extra), `4` (`--local-only` or `--block-pii` policy violation).
