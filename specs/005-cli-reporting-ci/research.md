# Research: Milestone 5 — CLI, Reporting & CI Integration (`005-cli-reporting-ci`)

**Date**: 2026-11-19 | **Feature**: [spec.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/specs/005-cli-reporting-ci/spec.md)

## Overview

Milestone 5 completes the EvalForge Maestro MVP by exposing a dual-entrypoint CLI (`evalforge-maestro`, `evalforge_maestro`), deterministic configuration resolution, opt-in pre-network PII egress blocking, library-pure JSON and Markdown diagnostic reporting, user-facing GitHub Actions CI workflow templates, and full distribution/release pipeline verification. All technical unknowns from `Technical Context` were evaluated against [constitution.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/.specify/memory/constitution.md), [intent.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/docs/intent.md), and existing M1–M4 subsystem boundaries.

---

## R1. CLI Parser Strategy & Cold-Start Isolation (`--help`)

- **Decision**: Implement the CLI using Python standard-library `argparse` organized into a two-stage entrypoint (`evalforge_maestro.cli.main` -> `cli/parser.py` delegates to `cli/commands.py` only after `--help`, `--version`, and argument parsing pass), with zero new third-party CLI framework dependencies.
- **Rationale**:
  - Zero third-party dependency additions keep the minimal core install footprint clean (`pydantic`, `jsonschema`, and Python `<3.11` `tomli` only) and avoid new supply-chain `pip-audit` surface.
  - Keeping `cli/__init__.py` and `cli/parser.py` free of top-level `tomllib`, `tomli`, `datasets`, `execution`, `judges`, or `adapters` imports ensures `evalforge-maestro --help`, `evalforge_maestro --help`, and subcommand `--help` load zero heavy optional modules (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `jsonschema`, `tomllib`, `dotenv`) into `sys.modules`.
- **Alternatives considered**:
  - `typer` / `click` / `rich`: Rejected because they add unnecessary runtime dependencies, increase cold-start import latency, and risk emitting ANSI banners or formatting onto `stdout` during `--json` output.

---

## R2. Cross-Version TOML & Explicit Opt-In `--env-file` Parsing

- **Decision**: Add `"tomli>=2.0.1; python_version < '3.11'"` as an environment-marker dependency in `pyproject.toml`, resolved lazily inside `evalforge_maestro.cli.config` (`import tomllib` on 3.11+, fallback `import tomli as tomllib` on 3.10). Implement a compact, strict pure-stdlib `.env` parser inside `cli/config.py` invoked **solely** when `--env-file <path>` is explicitly passed.
- **Rationale**:
  - CI runs cross-OS tests across Python `3.10` and `3.13`; `tomllib` exists in stdlib only on `3.11+`, while `tomli` provides identical read-only TOML 1.0 semantics on Python `3.10` with zero dependencies on `3.11+`.
  - Pure stdlib `KEY=VALUE` / `export KEY=VALUE` `.env` parsing inside `cli/config.py` honors Constitution Principle II (no `dotenv` package required, never imported by library modules) and FR-006 (explicit `--env-file` opt-in only, filling variables missing from OS `os.environ` strictly below OS `EVALFORGE_*` and above `evalforge.toml`, failing with exit code `2` on missing or syntactically malformed lines).
  - Preserves existing AST purity checks in `tests/test_library_purity.py` verifying that zero non-`cli` library modules ever import `cli`, `tomllib`, `tomli`, or `dotenv` and never read `evalforge.toml` or `.env`.
- **Alternatives considered**:
  - Requiring Python `3.11+`: Rejected because `pyproject.toml` and CI explicitly target `>=3.10`.
  - Adding `python-dotenv`: Rejected as unnecessary third-party dependency violating minimal footprint and cold-start checks.

---

## R3. Precedence, Non-Recursive Config Discovery & Secret Masking

- **Decision**: Resolve CLI settings inside `cli/config.py` using explicit 5-layer precedence (preserving the 4 constitutional tiers when `--env-file` is omitted):
  `CLI flags > OS environment variables (EVALFORGE_*) > explicit --env-file (opt-in) > evalforge.toml (non-recursive CWD or --config) > Built-in defaults`.
  Record per-setting origin (`cli`, `env`, `env_file`, `file`, `default`) and redact every secret field (`api_key`, `OPENAI_API_KEY`, etc.) inside `CLIResolvedConfig`, passing any raw runtime credential exclusively in-memory to `BaseJudgeMetric(..., api_key=raw_key)`.
- **Rationale**:
  - Non-recursive discovery checks strictly `Path.cwd() / "evalforge.toml"` when `--config` is omitted, preventing silent inheritance from parent folders.
  - Strict Pydantic schema validation (`extra="forbid"`) over TOML tables rejects typos, unknown keys, conflicting target modes, missing metric suites on `run`, or invalid numeric bounds immediately with `ConfigurationError` (exit code `2`).
  - Keeping raw secrets out of `CLIResolvedConfig` guarantees `--json`, `config show --resolved`, Markdown reports, persisted `RunRecord`s, and `stderr` logs cannot leak credentials.
- **Alternatives considered**:
  - Recursive upward `evalforge.toml` search (like git/ruff): Rejected by Constitution Principle VI (`non-recursive CWD`).

---

## R4. Replay Target Binding (`--executions`) & Zero-Case Exit Code Mapping

- **Decision**: Add `ReplayAdapter` under `evalforge_maestro.adapters.replay` implementing `TargetAdapter` (`execute(case) -> ExecutionResult` plus `system_version`, `model_id`, `config_fingerprint`) backed by pre-captured `ExecutionResult` JSONL/JSON records. Before dispatching `EvaluationOrchestrator`, CLI validates 1:1 coverage over every selected `EvaluationCase` (capped by `--max-dataset-cases`), raising `ConfigurationError`/`DatasetError` (`exit 2`) if any selected case lacks a matching record and logging unused extra `case_id`s to `stderr`.
- **Rationale**:
  - Reuses the exact M1–M4 orchestrator pipeline (`EvaluationOrchestrator.arun` -> checkpointing, `max_context_chars` truncation, `AsyncBatchMetric` context-grouped batching, canonical storage) with zero code duplication.
  - Preserves deterministic replay behavior across identical invocations (`@pytest.mark.gate_determinism`).
  - Handles zero-case-completed runtime failures cleanly: after `EvaluationOrchestrator` completes (`fail_fast=False`), if `run.evaluated_case_count == 0` OR every evaluated case failed execution (`all(case.execution.errors for case in run.case_results)`) OR all evaluated cases suffered unrecovered runtime judge failures (`ExecutionError` / `AdapterError` / `JudgeError`), CLI exits deterministically with code `3`. Missing extras (`MissingExtraError`) likewise map to `3` with actionable install hint on `stderr`.
- **Alternatives considered**:
  - Bypassing `EvaluationOrchestrator` for `--executions`: Rejected because checkpointing, truncation, aggregate summaries, and `judge_config_fingerprint` calculation would have to be duplicated.

---

## R5. Opt-In PII Egress Guard (`--block-pii` -> Exit Code `4`)

- **Decision**: Implement `detect_pii_categories(value)` and `validate_pii_egress(value, *, context_label)` in `src/evalforge_maestro/_canonical.py` / `src/evalforge_maestro/judges/security.py`, scanning for five sensitive classes: `email_address`, `phone_number`, `us_ssn`, `payment_card` (Luhn-validated 13–19 digit candidates to prevent false-positive ID blocks), and `secret_token` (API keys / Bearer tokens). Enforce pre-network interception raising `LocalOnlyPolicyError` (`exit 4`) without printing matched raw PII strings whenever `--block-pii` (`[security].block_pii`) is enabled alongside non-mock remote judges (`not mock_mode` and non-loopback endpoint) or non-mock remote-capable pipeline targets (`docpipe` in `answer_detailed` mode or configured remote endpoints). Keep M4 `JudgeConfig` fields/fingerprint unchanged by wrapping non-mock remote judges at the orchestration security boundary.
- **Rationale**:
  - Preserves 100% M4 `JudgeConfig.fingerprint` backward compatibility and `schemas-v1.json` strict `additionalProperties: false` invariants.
  - Prevents false-positive exit `4` blocks in offline `--mock`, loopback `localhost` Ollama, or default non-regulated benchmarks while delivering strict pre-network protection for regulated cloud workloads.
  - Never includes raw matched emails/SSNs/cards/secrets in exception messages or logs.
- **Alternatives considered**:
  - Adding `block_pii` directly to `JudgeConfig`: Rejected because M4's JSON Schema specifies `"additionalProperties": false` and changing `JudgeConfig` would shift historical M4 `judge_config_fingerprint` hashes.

---

## R6. Library-Pure Reporting (`reporting/`) vs CLI Stream Separation

- **Decision**: Introduce `src/evalforge_maestro/reporting/` (`__init__.py`, `builder.py`, `markdown.py`) exporting pure, side-effect-free builders (`build_run_report`, `build_comparison_report`, `build_trend_report`, `build_calibration_report`, `render_markdown`, `render_report_json`) over centralized M5 Pydantic models in `src/evalforge_maestro/types.py` (`ReportDocument`, `ReportDiagnosticsSummary`, `DecoupledEvidenceDiagnostic`, `CalibrationGateSummary`, `CLIResolvedConfig`, `BaselineCommandPayload`, `CLIErrorPayload`).
- **Rationale**:
  - Strictly honors Constitution Principle II: `reporting/` imports only `types`, `_canonical`, `exceptions`, and stdlib (zero imports of `cli`, `tomllib`, `tomli`, `dotenv`, `adapters`, `datasets`, `execution`).
  - Preserves Three-Way Concern Separation in both `ReportDocument` JSON schemas and Markdown headings (`## Evaluation`, `## Regression`, `## Acceptance / Quality Gate`), plus dedicated **Diagnostics & Anomalies** highlighting mandatory failures, `> 0.3` inter-metric disagreements, retrieval-vs-answer decoupling (`answer_passed_retrieval_or_grounding_failed` and `retrieval_passed_answer_or_grounding_failed`), and drift warnings with `scrub_secret_text` redaction applied across every rendered snippet.
  - Enforces strict `stdout` vs `stderr` rules: `--json` emits only single schema-validated JSON on `stdout` (`CLIErrorPayload` if pre-report error occurs), default mode emits deterministic Markdown/table output on `stdout`, and `--log-level` / `--log-json` / progress / warnings always write strictly to `stderr`.
- **Alternatives considered**:
  - Putting Markdown formatting logic directly inside `cli/`: Rejected because Constitution Principle II requires library `reporting` to be independently reusable without CLI or config side effects.

---

## R7. User CI Templates & MVP Release Pipeline Validation

- **Decision**: Provide self-contained, copy-ready CI adoption assets in `examples/ci/` (`evalforge-ci.yml`, `evalforge.toml`, `golden-sample.jsonl`, `executions-sample.jsonl`) and verify them end-to-end inside `tests/integration/test_ci_templates.py`. Update `.github/workflows/ci.yml` (`cross-os-and-packaging`) and `.github/workflows/release.yml` (`verify-testpypi`) to execute minimal clean-venv CLI checks (`evalforge-maestro --help`, `evalforge_maestro --version`, `--no-dev` offline smoke checks, and `sys.modules` cold-start assertions).
- **Rationale**:
  - Directly fulfills `docs/intent.md` Section `5.2 (M5)` and Acceptance Criterion `#10` without inventing unratified top-level CLI subcommands (`init` is omitted to stay aligned with the 7 governed subcommands: `run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`).
  - Shipping runnable example fixtures alongside `examples/ci/evalforge-ci.yml` lets external adopters verify their GitHub Actions PR gate workflow within minutes.
- **Alternatives considered**:
  - Documentation-only YAML snippets in `README.md`: Rejected because untested snippets easily rot when flags evolve; backed by integration tests, `examples/ci/` stays continuously verified.
