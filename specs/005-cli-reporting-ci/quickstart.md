# Quickstart Validation Guide: Milestone 5 — CLI, Reporting & CI Integration

**Feature**: `005-cli-reporting-ci` | **Contracts**: [cli.md](contracts/cli.md), [public-api.md](contracts/public-api.md)

## 1. Cold-Start & Console Entrypoint Verification

```bash
evalforge-maestro --version
evalforge-maestro --help
evalforge_maestro --help
```

Verify in a clean minimal install (`--no-dev`) that `evalforge-maestro --help` loads zero heavy optional packages (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `jsonschema`, `tomllib`, `tomli`, `dotenv`) into `sys.modules`.

---

## 2. Offline End-to-End CI Smoke Evaluation (`run --mock --local-only`)

Using the bundled sample CI workflow assets (`examples/ci/`):

```bash
evalforge-maestro run \
  --dataset examples/ci/golden-sample.jsonl \
  --executions examples/ci/executions-sample.jsonl \
  --metric normalized_match \
  --metric precision_at_k:k=2 \
  --metric groundedness \
  --mock \
  --local-only \
  --strict \
  --json \
  --markdown-out report.md
```

Expected outcomes:
- Exit code `0` (`PASS`), immutable `.evalforge/runs/<run_id>.json` + `.evalforge/manifest.jsonl` persisted with `0o700`/`0o600` permissions.
- `stdout` contains solely one schema-valid `ReportDocument` JSON object; all progress telemetry and warnings appear solely on `stderr`.
- `report.md` renders clearly separated **Evaluation**, **Regression**, and **Acceptance / Quality Gate** headings.
- Repeating the `--mock --local-only` invocation produces identical metric scores, `judge_config_fingerprint`, anomaly/drift flags, gate verdicts, and POSIX exit codes (`run_id` / wall-clock `timestamp` / `generated_at` normalized unless `--run-id` is pinned).

---

## 3. Baseline Pinning, Comparison, Trends, Calibration & Report Export

```bash
# Pin baseline without mutating RunRecord
evalforge-maestro baseline set <RUN_ID> --name release-v1 --json
evalforge-maestro baseline list --json

# Compare a candidate run against pinned baseline
evalforge-maestro compare <CANDIDATE_RUN_ID> --baseline release-v1 --strict --json --markdown-out compare.md

# Track multi-run sliding window slope
evalforge-maestro trend --window 3 --json --markdown-out trend.md

# Calibrate mock judge against human samples
evalforge-maestro calibrate --samples cal-samples.jsonl --metric groundedness --mock --local-only --min-agreement 50 --json

# Render Markdown directly from stored run artifact
evalforge-maestro report --run <RUN_ID> --baseline release-v1 > diagnostic-report.md
```

---

## 4. Configuration Precedence, Secret Redaction & Security Exit Codes

```bash
# Inspect resolved configuration precedence with secrets masked
EVALFORGE_JUDGE_API_KEY=sk-secret123456 \
EVALFORGE_MAX_CONCURRENCY=8 \
  evalforge-maestro config show --resolved --json
```

Verify:
- `"judge.api_key"` shows `"[REDACTED]"` (`"masked": true`) across `stdout`, `stderr`, Markdown, and `.evalforge/`.
- Opt-in `--env-file .env.local` fills unset env variables strictly below OS env vars and above `evalforge.toml`, returning exit code `2` if missing or malformed.
- Running live non-mock remote model (`openai/gpt-4o-mini`) under `--local-only` or sending PII under `--block-pii` aborts pre-network with **exit code `4`**.
- Triggering `--fail-fast` or missing optional extras (`MissingExtraError`) returns **exit code `3`**.

---

## 5. Full CI & Quality Gate Verification

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/ruff check --select S src/
.venv/bin/mypy --strict src tests
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro.metrics --cov-branch --cov-fail-under=100 tests/unit/test_metrics.py tests/unit/test_ir_metrics.py tests/contract/test_metric_formulas.py
.venv/bin/pytest --strict-markers -W error --cov=evalforge_maestro.regression.gate --cov-branch --cov-fail-under=100 tests/unit/test_quality_gate.py
.venv/bin/pytest --strict-markers -W error -m "gate_determinism or gate_immutability"
uv build && .venv/bin/twine check --strict dist/*
```
