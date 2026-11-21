# Contract Specification: CLI Subcommands, TOML Config & Security Precedence

**Feature**: `007-statistical-embedding-metrics`  
**Contract Scope**: CLI parser (`evalforge-maestro`), `evalforge.toml`, `EVALFORGE_*` environment variables, and POSIX exit codes.

## 1. Precedence, Isolation & Secret Hygiene
- Precedence remains strictly:
  `CLI flags > OS environment (EVALFORGE_*) > --env-file > local evalforge.toml > Built-in defaults`.
- `[embedding]` settings (`--embedding-*`, `EVALFORGE_EMBEDDING_*`, `[embedding]` TOML) remain strictly independent from `[judge]` settings (`--judge-*`, `EVALFORGE_JUDGE_*`, `[judge]` TOML) and never inherit judge models, `api_base`, or `api_key`. Under `--mock` without an explicit model, embedding model defaults to `"mock-embedding"`.
- Secrets (`[embedding].api_key`, `EVALFORGE_EMBEDDING_API_KEY`) are stripped into `raw_embedding_api_key` strictly inside CLI config loading, replaced by `api_key_configured: bool` in `CLIResolvedConfig.embedding`, and never serialized into logs, JSON stdout, Markdown reports, or `RunRecord`.
- Plaintext `[embedding].api_key` in `evalforge.toml` emits a config validation warning matching `[judge].api_key`.

---

## 2. CLI Surface Extensions (`cli/parser.py`, `cli/commands.py`)

### 2.1 `evalforge-maestro run`
New flags:
- `--metric embedding_similarity[:pass_threshold=0.7]` / `context_embedding_similarity[:aggregation=mean,pass_threshold=0.6]`
- `--embedding-model MODEL` (`EVALFORGE_EMBEDDING_MODEL`, `[embedding].model`)
- `--embedding-api-base URL` (`EVALFORGE_EMBEDDING_API_BASE`, `[embedding].api_base`)
- `--embedding-pass-threshold FLOAT` (`EVALFORGE_EMBEDDING_PASS_THRESHOLD`, `[embedding].pass_threshold`)
- `--embedding-aggregation {max,mean}` (`EVALFORGE_EMBEDDING_AGGREGATION`, `[embedding].aggregation`)
- `--embedding-max-retries INT` (`EVALFORGE_EMBEDDING_MAX_RETRIES`, `[embedding].max_retries`)
- `--embedding-timeout FLOAT` (`EVALFORGE_EMBEDDING_TIMEOUT`, `[embedding].timeout_seconds`)
- `--embedding-max-input-chars INT` (`EVALFORGE_EMBEDDING_MAX_INPUT_CHARS`, `[embedding].max_input_chars`, defaults cleanly to `execution.max_context_chars` if omitted or `None`)
- `--repeats INT` (`EVALFORGE_REPEATS`, `[run].repeats`, `>= 1`, default `1`):
  - When `--repeats == 1`: single run, byte-identical to existing behavior.
  - When `--repeats N` (`N >= 2`):
    - Names repeats `<X>-r01` .. `<X>-rNN` when `--run-id X` is provided (or auto-generates unique immutable `run_id` values), persisting all `N` immutable `RunRecord` artifacts cleanly.
    - If `--seed S` is set, repeat `i` (`0`-based) executes with `seed = S + i` for reproducible stochastic trial variation.
    - Evaluates `QualityGate.evaluate_cohort(runs, ...)` (failing immediately if *any* repeat fails a mandatory case, and evaluating metric score floors and rates against pooled cohort averages across all `N` repeats).
    - If `--baseline` / `--baseline-run` is present, compares the `N` candidate runs against baseline(s) via `compare_run_cohorts`; attaches `cohort_run_ids` and `cohort_aggregates` cleanly on `ReportDocument` alongside representative `evaluation = runs[-1]`.
- `--baseline-run REF` (repeatable on `run` and `compare`, additive alongside singular `--baseline`)
- `--confidence-level FLOAT` (`EVALFORGE_CONFIDENCE_LEVEL`, `[gate].confidence_level`, `0 < x < 1`, default `0.95`)
- `--min-statistical-samples INT` (`EVALFORGE_MIN_STATISTICAL_SAMPLES`, `[gate].min_statistical_samples`, `>= 2`, default `2`)
- `--fail-on-significant-regression` (`EVALFORGE_FAIL_ON_SIGNIFICANT_REGRESSION`, `[gate].fail_on_significant_regression`, default `false`)

### 2.2 `evalforge-maestro compare`
- Backward-compatible positional signature updated safely:
  `evalforge-maestro compare <CANDIDATE_RUN_ID> [<CANDIDATE_RUN_ID> ...] (--baseline <REF> | --baseline-run <REF> ...)`
- Resolves `baseline_refs = ([resolved.baseline] if resolved.baseline else []) + list(resolved.baseline_runs)` (requiring `>= 1` baseline reference, so `--baseline-run` works cleanly even without singular `--baseline`).
- Single candidate + single baseline: calls `compare_runs(...)` directly (identically preserving existing output structure + populated `MetricComparison.statistics`).
- Multiple candidates and/or multiple baselines: resolves every run ID or pinned baseline alias and calls `compare_run_cohorts(...)` + `QualityGate.evaluate_cohort(...)`.
- Accepts `--confidence-level`, `--min-statistical-samples`, `--fail-on-significant-regression`, `--strict`, `--min-score`, `--max-regression-drop`.

### 2.3 POSIX Exit Codes (`0`–`4`)
Unchanged guarantees:
- `0`: `PASS` (or `WARNING` / `INCONCLUSIVE` without `--strict`).
- `1`: `FAIL`, mandatory failure, `--fail-on-significant-regression` triggered, or `--strict` on `WARNING`/`INCONCLUSIVE` (including advisory significant regression `WARNING`).
- `2`: Invalid CLI/TOML config (e.g., `confidence_level=1.5`, `repeats=0`, invalid aggregation).
- `3`: `MissingExtraError` (`evalforge-maestro[embeddings]` absent when executing embedding metrics) or execution failure.
- `4`: `LocalOnlyPolicyError` (`--local-only` blocking non-loopback embedding endpoint or `--block-pii` blocking PII/secret egress on remote embedding call).

---

## 3. TOML Configuration Schema (`evalforge.toml`)

```toml
[run]
repeats = 1

[embedding]
model = "ollama/nomic-embed-text"
api_base = "http://localhost:11434"
pass_threshold = 0.65
aggregation = "max"
max_retries = 2
retry_backoff_seconds = 0.5
timeout_seconds = 30.0
mock_mode = false
local_only = true

[gate]
confidence_level = 0.95
min_statistical_samples = 2
fail_on_significant_regression = false
```
