# Contract: Command-Line Interface & Configuration (`evalforge-maestro` / `evalforge_maestro`)

**Feature**: `005-cli-reporting-ci` | **Entrypoints**: `evalforge-maestro = "evalforge_maestro.cli:main"`, `evalforge_maestro = "evalforge_maestro.cli:main"`

---

## 1. Global Options, Cold-Start & Stream Hygiene

```text
evalforge-maestro [GLOBAL_OPTS] <subcommand> ...
```

### Global Flags (available before or with subcommands where scoped)
- `--version`: Print packaged `evalforge-maestro <version>` to `stdout` and exit `0`.
- `--help`, `-h`: Print help to `stdout` and exit `0` cleanly with zero heavy optional imports (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `jsonschema`, `tomllib`, `tomli`, `dotenv` MUST remain absent from `sys.modules`).
- `--config <path>`: Explicit path to TOML configuration file (fails with exit `2` if missing or unreadable; when omitted, reads `./evalforge.toml` non-recursively if present).
- `--env-file <path>`: Explicit opt-in `.env` file path (never auto-loaded from CWD; fails with exit `2` if missing or malformed).
- `--storage-dir <path>`: Storage root overriding `.evalforge` (env: `EVALFORGE_STORAGE_DIR`).
- `--log-level {DEBUG,INFO,WARNING,ERROR}`: Minimum stderr diagnostic level (env: `EVALFORGE_LOG_LEVEL`, default `WARNING`).
- `--log-json`: Emit structured JSON log records strictly to `stderr` (env: `EVALFORGE_LOG_JSON`).
- `--json`: Guarantee `stdout` emits solely one schema-validated JSON payload matching Draft 2020-12 contract schemas (`ReportDocument`, `BaselineCommandPayload`, `CLIResolvedConfig`, `ConfigValidationPayload`, or `CLIErrorPayload` on exit `2`/`3`/`4`), with zero banners or stray prints (including CLI syntax/parse errors whenever `--json` is present).
- `--quiet`, `-q`: Suppress non-`--json` primary `stdout` output (useful when exporting cleanly via `--markdown-out` / `--json-out` without duplicating console output; `--json` remains authoritative when both are passed).

### Default Streams When `--json` Is Off
- Primary command output (`Markdown` report for `run`/`compare`/`trend`/`calibrate`/`report`, resolved configuration view for `config show --resolved`, listing/summary for `baseline`) writes strictly to `stdout` (including alongside `--markdown-out` / `--json-out` unless `--quiet` is enabled).
- All logs, warnings, deprecation notices, progress status, unused-trace warnings, and errors write strictly to `stderr`.

---

## 2. Subcommands

### `run`
Execute dataset evaluation, optional baseline/trend gating, and persistence.
- Inputs & Targets:
  - `--dataset <path>` (required via flag, env `EVALFORGE_DATASET`, or `evalforge.toml` -> else exit `2`)
  - `--dataset-id <id>`, `--dataset-version <ver>`
  - Live target mode: `--target-type {callable,rag,docpipe}` + `--target <module:symbol>` (for `callable`/`rag`), `--target-arg-mode {input,case}`, `--system-version`, `--model-id`, `--docpipe-mode {answer_detailed,retrieve}`, `--docpipe-collection`, `--docpipe-top-k`
  - Offline replay mode: `--executions <path>` (mutually exclusive with conflicting live `--target` unless `target_type=replay`; validates 1:1 coverage of all selected dataset cases upfront -> missing case exits `2`, extra trace rows warn on `stderr`)
  - Missing or unresolvable target -> exit `2`
- Metrics & Judges:
  - `--metric <spec>` (repeatable; `<id>` or `<id>:<k=v,...>` or JSON params; fallback env `EVALFORGE_METRICS` or `evalforge.toml` `[metrics]`; zero configured metrics -> exit `2`; unknown metric ID or bad params -> exit `2`)
  - `--mock` (sets `JudgeConfig.mock_mode=True`)
  - `--local-only` (`JudgeConfig.local_only=True` + `[security].local_only=True`)
  - `--block-pii` (`[security].block_pii=True`; pre-network scan before non-mock remote target or remote judge transmission -> exit `4`)
  - `--judge-model`, `--judge-api-base`, `--judge-temperature`, `--judge-pass-threshold`, `--judge-max-retries`, `--judge-timeout`, `--seed`
- Gate & Execution Guardrails:
  - `--baseline <run_id_or_alias>` (explicit only; never auto-loads `"default"` unless set via CLI/env/config)
  - `--trend-window <N>` (`N >= 2`, else exit `2`)
  - `--strict` (escalates `WARNING` and `INCONCLUSIVE` gate decisions to exit `1`)
  - `--fail-fast` (aborts immediately on case/judge failure -> exit `3`)
  - `--max-concurrency <N>` (default `4`), `--max-dataset-cases <N>`, `--max-context-chars <N>`, `--case-timeout <sec>`, `--max-memory-mb <MiB>`, `--memory-limit-action {warn,abort}`
  - `--run-id <id>` (if already exists -> `ImmutabilityError` -> exit `2`)
- Output Export:
  - `--json`, `--json-out <path>`, `--markdown-out <path>` / `--output <path>`

### `compare`
Compare candidate run against explicit baseline (`<candidate_run_id>` + `--baseline <run_id_or_alias>`).
- Optional `--baseline` from env/config allowed; missing candidate or baseline -> exit `2`.
- Supports `--strict`, `--min-score`, `--max-regression-drop`, `--json`, `--json-out <path>`, `--markdown-out <path>` / `--output <path>`.

### `trend`
Sliding-window OLS trend analysis (`--window <N>`, default from config/`5`; `< 2` -> exit `2`).
- Supports `--dataset-id <id>`, `--all-datasets`, `--model-id <id>`, `--metric <id>` (repeatable), `--slope-threshold <float>`, `--strict`, `--json`, `--json-out <path>`, `--markdown-out <path>` / `--output <path>`.
- Handles `0` or `1` runs gracefully as `INSUFFICIENT_DATA` without division-by-zero (`--strict` or `require_trend` / `min_trend_runs` controls escalation to `1`).

### `calibrate`
Judge calibration against human ground-truth samples (`--samples <jsonl_or_json_path>`, `--metric <judge_metric_id>`).
- Supports `--mock`, `--local-only`, `--block-pii`, `--judge-model`, `--judge-api-base`, `--judge-pass-threshold`, `--human-threshold`, `--score-divergence-threshold`, `--min-agreement <0..100>`, `--strict`, `--max-concurrency`, `--json`, `--json-out <path>`, `--markdown-out <path>` / `--output <path>`.
- Exit `0` by default; `1` if `min_agreement` breached or `--strict` triggered on inconclusive/zero valid cases; `2` on invalid input/unknown judge metric; `3` on missing `[judges]` extra / runtime judge failure; `4` on `local_only` / `block_pii` violation.

### `baseline`
Manage pinned named baselines in `.evalforge/baselines.json` without modifying runs:
- `baseline set <run_id> [--name default] [--note ...] [--tag ...] [--overwrite]`
- `baseline list`
- `baseline show [name]` (default `"default"`)
- `baseline delete <name>` (alias `remove`)
- Supports `--json`, `--storage-dir`. Missing run/alias or overwrite-without-flag (`ImmutabilityError`) -> exit `2`.

### `report`
Render/export `ReportDocument` JSON and/or Markdown directly from existing stored runs/comparisons/trends or JSON artifacts on disk:
- Exactly one source selector required:
  - `--run <run_id>` (optionally paired with `--baseline <run_id_or_alias>` / `--trend-window <N>`)
  - `--compare <candidate_run_id>` (`--baseline <run_id_or_alias>` required)
  - `--trend` (`--window <N>`, `--dataset-id`, `--all-datasets`, `--model-id`)
  - `--artifact <path>` (validates `ReportDocument`, `RunRecord`, `RunComparisonReport`, `TrendReport`, or `CalibrationReport` JSON file)
- Supports `--json`, `--json-out <path>`, `--markdown-out <path>` / `--output <path>`. Never mutates historical `.evalforge/runs/<id>.json`.

### `config`
- `config show --resolved` (`--resolved` accepted/recommended explicitly; prints resolved configuration + provenance table with all secret values masked to `"[REDACTED]"` on `stdout`, or `CLIResolvedConfig` when `--json` is passed)
- `config validate` (validates TOML, `--env-file`, env vars, and schema constraints -> exit `0` or `2`; emits `ConfigValidationPayload` under `--json`)

---

## 3. Configuration Precedence & `EVALFORGE_*` Mapping

1. **CLI flags** (`cli`)
2. **Process OS environment variables** (`env`)
3. **Explicit `--env-file <path>` variables** (`env_file` — ONLY if `--env-file` is passed, never implicitly loaded; fills keys absent from `os.environ`)
4. **TOML file** (`file` — `--config <path>` or non-recursive `./evalforge.toml`)
5. **Built-in defaults** (`default`)

Canonical environment variables:
- `EVALFORGE_CONFIG`, `EVALFORGE_ENV_FILE`, `EVALFORGE_STORAGE_DIR`
- `EVALFORGE_DATASET`, `EVALFORGE_DATASET_ID`, `EVALFORGE_DATASET_VERSION`, `EVALFORGE_EXECUTIONS`
- `EVALFORGE_RUN_ID`, `EVALFORGE_BASELINE`, `EVALFORGE_TREND_WINDOW`
- `EVALFORGE_TARGET_TYPE`, `EVALFORGE_TARGET`, `EVALFORGE_TARGET_ARG_MODE`, `EVALFORGE_SYSTEM_VERSION`, `EVALFORGE_MODEL_ID`
- `EVALFORGE_DOCPIPE_MODE`, `EVALFORGE_DOCPIPE_COLLECTION`, `EVALFORGE_DOCPIPE_TOP_K`
- `EVALFORGE_METRICS` (comma-separated metric specs or JSON array)
- `EVALFORGE_MOCK`, `EVALFORGE_LOCAL_ONLY`, `EVALFORGE_BLOCK_PII`, `EVALFORGE_STRICT`, `EVALFORGE_FAIL_FAST`
- `EVALFORGE_MAX_CONCURRENCY`, `EVALFORGE_MAX_DATASET_CASES`, `EVALFORGE_MAX_CONTEXT_CHARS`, `EVALFORGE_CASE_TIMEOUT_SECONDS`, `EVALFORGE_MAX_MEMORY_MB`, `EVALFORGE_MEMORY_LIMIT_ACTION`, `EVALFORGE_SEED`
- `EVALFORGE_JUDGE_MODEL`, `EVALFORGE_JUDGE_API_BASE`, `EVALFORGE_JUDGE_API_KEY`, `EVALFORGE_JUDGE_TEMPERATURE`, `EVALFORGE_JUDGE_PASS_THRESHOLD`, `EVALFORGE_JUDGE_MAX_RETRIES`, `EVALFORGE_JUDGE_TIMEOUT_SECONDS`, `EVALFORGE_CALIBRATE_MIN_AGREEMENT`
- `EVALFORGE_GATE_MIN_SCORE`, `EVALFORGE_GATE_MAX_REGRESSION_DROP`, `EVALFORGE_GATE_MAX_REGRESSED_CASES`, `EVALFORGE_GATE_MAX_INCONCLUSIVE_RATE`, `EVALFORGE_GATE_FAIL_ON_DRIFT`, `EVALFORGE_GATE_FAIL_ON_ANOMALY`, `EVALFORGE_GATE_FAIL_ON_DEGRADING_TREND`
- `EVALFORGE_LOG_LEVEL`, `EVALFORGE_LOG_JSON`

---

## 4. Deterministic POSIX Exit Code Mapping

| Exit Code | Meaning & Exhaustive Trigger Conditions |
| --- | --- |
| `0` | Quality gate `PASS`; `WARNING` or `INCONCLUSIVE` when `--strict` is disabled; diagnostic `calibrate` without `--min-agreement` breach; successful `baseline`, `report`, or `config` commands. |
| `1` | Quality gate `FAIL` (mandatory failure, metric floor breach, excessive regression); `--strict` active with `WARNING` or `INCONCLUSIVE` gate result; `calibrate` failing `--min-agreement` or `--strict` on inconclusive/zero-valid samples. |
| `2` | CLI syntax/usage error; invalid TOML syntax or unknown TOML key; missing explicit `--config` or `--env-file`; invalid `--env-file` line; `ConfigurationError`; `DatasetError` / `EmptyDatasetError` / `DuplicateCaseIdError`; `MetricError`; `StorageError` / `ImmutabilityError` (unknown run/baseline, duplicate `run_id`, baseline overwrite without `--overwrite`); replay `--executions` missing dataset `case_id` match; zero metrics on `run`. |
| `3` | Target adapter or judge runtime/network failure: `AdapterError`, `ExecutionError` (including `--fail-fast`), `MemoryLimitExceededError` (`abort`), `JudgeError`, `MissingExtraError`, OR `--fail-fast=False` completing with zero successful non-error cases (`evaluated_case_count == 0`, or all cases failed execution / unrecovered judge errors). |
| `4` | Security or locality policy violation: `LocalOnlyPolicyError` (`--local-only` blocking cloud/non-loopback endpoint, or `--block-pii` blocking outbound sensitive PII/secret pattern pre-network). |
