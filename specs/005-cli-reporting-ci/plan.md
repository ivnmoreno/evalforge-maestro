# Implementation Plan: Milestone 5 — CLI, Reporting & CI Integration

**Branch**: `005-cli-reporting-ci` | **Date**: 2026-11-19 | **Spec**: [spec.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/specs/005-cli-reporting-ci/spec.md)

**Input**: Feature specification from `/specs/005-cli-reporting-ci/spec.md`

## Summary

Milestone 5 completes the EvalForge Maestro MVP by delivering: (1) dual CLI entrypoints (`evalforge-maestro` and `evalforge_maestro`) exposing seven subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`) built cleanly on Python stdlib `argparse` for instant cold-start `--help` isolation; (2) deterministic configuration loading (`CLI flags > OS env > opt-in --env-file > non-recursive CWD evalforge.toml > defaults`) strictly isolated at the CLI boundary (`cli/config.py`) with `CLIResolvedConfig` credential masking; (3) offline trace replay (`ReplayAdapter`) plus live `callable`/`rag`/`docpipe` target resolution and explicit metric requirement enforcement; (4) opt-in pre-network PII egress blocking (`--block-pii` -> `LocalOnlyPolicyError` / exit `4`) alongside `--local-only` enforcement and full POSIX `0`–`4` exit-code mapping; (5) a pure, CLI-independent `reporting` subsystem rendering three-way separated, schema-validated `ReportDocument` JSON and Markdown diagnostic reports highlighting mandatory failures, `> 0.3` disagreements, drift, and retrieval-vs-answer evidence decoupling; and (6) verified user GitHub Actions CI templates (`examples/ci/`), packaging checks, and release pipeline validation.

## Technical Context

**Language/Version**: Python `>=3.10` (validated across `3.10`–`3.13`, `mypy --strict`)

**Primary Dependencies**: Minimal core (`pydantic>=2.7,<3`, `jsonschema>=4.23,<5`, plus `"tomli>=2.0.1; python_version < '3.11'"` loaded lazily only inside `cli/config.py`); stdlib `argparse` and `logging` for CLI/stderr telemetry (zero external `.env`, `click`, `typer`, or `rich` dependencies); optional extras `[docpipe]` and `[judges]` remain strictly lazy.

**Storage**: Immutable canonical JSON/JSONL persistence under `.evalforge/` via `LocalRunStore` (`runs/<run_id>.json`, `manifest.jsonl`, `baselines.json`, `tmp/<run_id>.jsonl`, `0o700`/`0o600` permissions); user-requested file exports (`--json-out`, `--markdown-out`, `--output`) created safely on disk without mutating `.evalforge/`.

**Testing**: `pytest` with `--strict-markers`, `filterwarnings = ["error"]`, `>=85%` total branch coverage (`100%` preserved on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`), `tests/test_library_purity.py` AST boundary & CLI `--help` cold-start subprocess verification, `tests/test_api_stability.py` signature/`__all__` pinning, `tests/contract/test_m5_schemas.py`, hermetic socket/env isolation, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, and CI template integration verification.

**Target Platform**: Cross-platform (`linux` / `ubuntu-latest`, `macos-latest`, `windows-latest`) CLI & Python SDK package.

**Project Type**: Python library + packaged dual-alias CLI tool + CI workflow templates.

**Performance Goals**: Cold-start `evalforge-maestro --help` / `--version` avoids parsing TOML/datasets or importing optional extras; `--executions` and `--dataset` stream cleanly with `max_concurrency=4` default and workstation memory/truncation guardrails intact.

**Constraints**: Strict library purity (`types`, `datasets`, `execution`, `storage`, `metrics`, `judges`, `regression`, and library `reporting` NEVER import `cli`, `tomllib`, `tomli`, or `dotenv` and NEVER read `evalforge.toml`/`.env`); zero plaintext credentials in any output or file; strict single-JSON `stdout` separation under `--json`; zero M4 `JudgeConfig` schema/fingerprint breakage.

**Scale/Scope**: Milestone 5 delivers `ReplayAdapter`, opt-in PII egress guard helpers, library-pure `evalforge_maestro.reporting`, `evalforge_maestro.cli`, M5 models in `types.py`, console script entrypoints in `pyproject.toml`, `examples/ci/` templates, README documentation, and `.github/workflows/{ci,release}.yml` CLI checks.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Research | Post-Design | Justification / Enforcement Mechanism |
| --- | --- | --- | --- |
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | CLI orchestrates evaluation, calibration, regression comparison/trends, quality gating, and JSON/Markdown artifacts via adapters without adding RAG indexing, LLM runtimes, frameworks, or web UI servers. Three-way separation (**Evaluation**, **Regression**, **Quality Gate**) is enforced cleanly inside `ReportDocument` and Markdown section structure. |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | Library modules (`types`, `datasets`, `execution`, `storage`, `metrics`, `judges`, `regression`, `reporting`) NEVER import `cli`, `tomllib`, `tomli`, `dotenv`, or read `evalforge.toml`/`.env`. `reporting/` imports only `types`, `_canonical`, `exceptions`, and stdlib. `cli/` sits cleanly at the outermost boundary. Enforced via `tests/test_library_purity.py` AST + `--help` subprocess cold-start tests. |
| **III. Single Schema Source of Truth** | PASS | PASS | Every M5 contract (`CLIResolvedConfig`, `ReportDocument`, `DecoupledEvidenceDiagnostic`, `ReportDiagnosticsSummary`, `CalibrationGateSummary`, `BaselineCommandPayload`, `ConfigValidationPayload`, `CLIErrorPayload`) resides in `src/evalforge_maestro/types.py` carrying `schema_version="1.0"`, `extra="forbid"`, and Draft 2020-12 JSON schemas validated by `tests/contract/test_m5_schemas.py`. |
| **IV. Evidence-Aware & Anomaly-Safe Eval** | PASS | PASS | `reporting/` derives `DecoupledEvidenceDiagnostic` directly from captured intermediate chunks & metric outcomes without modifying raw scores, surfaces mandatory case failures, `> 0.3` inter-metric disagreements, aggregate-masked drops, and drift warnings clearly in both JSON and Markdown. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | `baseline`, `report`, `compare`, and `trend` never mutate persisted `RunRecord` files; `--mock --local-only` CLI invocations yield identical scores, gate decisions, and POSIX exit codes `0`–`4` (`@pytest.mark.gate_determinism`); replay mismatches fail cleanly (`exit 2`); runtime/judge zero-case faults map deterministically to `exit 3`; `--local-only` / `--block-pii` map to `exit 4`. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | `--json` prints exclusively schema-validated JSON on `stdout` (`CLIErrorPayload` on error); diagnostics, warnings, progress telemetry, and `--log-json` / `--log-level` write strictly to `stderr`; library `reporting` uses `NullHandler()` only; `CLIResolvedConfig`, `config show --resolved`, logs, and reports strictly mask credentials (`[REDACTED]`); precedence enforces `CLI flags > OS env > opt-in --env-file > evalforge.toml (non-recursive CWD) > defaults`. |
| **VII. Automated Quality Gates** | PASS | PASS | Preserves `ruff format/check`, Bandit `S`, `mypy --strict`, `>=85%` total branch coverage (`100%` kept on `metrics/` & `regression/gate.py`), `pip-audit` (`tomli` env-marker only for `3.10`), `cz check`, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, cross-OS minimal wheel/sdist CLI checks, and `verify-testpypi` CLI checks. |

## Project Structure

### Documentation (this feature)

```text
specs/005-cli-reporting-ci/
├── spec.md                     # Feature specification & 8 clarified design decisions
├── plan.md                     # This file
├── research.md                 # Phase 0 decisions (cold-start CLI, config, replay, PII, reporting)
├── data-model.md               # Phase 1 M5 schemas & validation invariants
├── quickstart.md               # Phase 1 end-to-end validation guide
├── checklists/
│   └── requirements.md         # Spec quality checklist (16/16)
└── contracts/
    ├── cli.md                  # CLI subcommands, flags, streams, env vars & exit codes 0–4
    ├── public-api.md           # Public Python SDK additions (reporting, ReplayAdapter, PII helpers)
    └── schemas-v1.json         # Draft 2020-12 M5 schema definitions
```

### Source Code (repository root)

```text
pyproject.toml                                # Add [project.scripts] entrypoints & Python <3.11 tomli dep
uv.lock                                       # Updated lockfile including tomli conditional marker
README.md                                     # Complete MVP CLI, evalforge.toml & CI adoption docs
.github/workflows/
├── ci.yml                                    # Extend minimal-wheel/sdist checks with CLI --help/--version/smoke checks
└── release.yml                               # Extend verify-testpypi job with installed CLI entrypoint check
examples/ci/
├── evalforge-ci.yml                          # User-facing GitHub Actions PR quality-gate & summary template
├── evalforge.toml                            # Sample project configuration matching template
├── golden-sample.jsonl                       # Sample golden dataset for CI template verification
└── executions-sample.jsonl                   # Sample pre-captured execution traces for offline smoke runs
src/evalforge_maestro/
├── __init__.py                               # Re-export M5 reporting/replay/security/types APIs cleanly (lazy CLI)
├── _canonical.py                             # Add detect_pii_categories (Luhn card, SSN, email, phone, secrets)
├── types.py                                  # Add M5 Pydantic contracts (CLIResolvedConfig, ReportDocument, etc.)
├── adapters/
│   ├── __init__.py                           # Export ReplayAdapter alongside CallableAdapter, RAGAdapter, DocpipeAdapter
│   └── replay.py                             # Offline ReplayAdapter reading pre-captured ExecutionResult traces
├── judges/
│   └── security.py                           # Add validate_pii_egress / wrap_pii_guarded_metric helpers
├── reporting/
│   ├── __init__.py                           # NullHandler logger + public reporting exports
│   ├── builder.py                            # Pure build_*_report, detect_decoupled_evidence, render_report_json
│   └── markdown.py                           # Pure three-way Markdown formatter (Evaluation / Regression / Gate)
└── cli/
    ├── __init__.py                           # Thin cold-start-safe CLI entrypoint exporting main()
    ├── parser.py                             # Pure stdlib argparse tree with zero heavy/config imports
    ├── config.py                             # Lazy TOML/env-file/env/CLI precedence resolution & secret masking
    ├── logging_utils.py                      # Strictly stderr plain & --log-json formatter
    ├── targets.py                            # Target/metric resolution, Replay alignment, --block-pii guards
    └── commands.py                           # Subcommand handlers + exit code 0–4 mapping
tests/
├── test_library_purity.py                    # Add reporting/ boundaries + CLI --help cold-start sys.modules probe
├── test_api_stability.py                     # Pin M5 __all__ exports, reporting/ReplayAdapter/PII signatures & models
├── contract/
│   └── test_m5_schemas.py                    # Draft 2020-12 schema validation over merged M1–M5 contracts & CLI --json
├── unit/
│   ├── test_cli_config.py                    # 5-tier precedence, non-recursive CWD, --env-file, masking, bad TOML -> 2
│   ├── test_pii_security.py                  # detect_pii_categories (Luhn card/SSN/email/phone/secret) & pre-network 4
│   ├── test_replay_adapter.py                # ReplayAdapter validation, duplicates, missing ID alignment
│   └── test_reporting.py                     # Evaluation/Regression/Gate separation, decoupling, redaction, Markdown
└── integration/
    ├── test_cli_workflow.py                  # Full end-to-end CLI run/compare/trend/calibrate/baseline/report/config + exit 0–4
    └── test_ci_templates.py                  # Execute examples/ci/ template commands cleanly in offline mode
```

**Structure Decision**: Single Python package layout extending `src/evalforge_maestro/` with two cleanly isolated boundary modules: pure `reporting/` (usable standalone by SDK consumers without touching CLI/TOML/env) and outermost `cli/` (strictly isolated for parsing configuration files, `--env-file`, logging to `stderr`, emitting JSON/Markdown to `stdout`, and mapping domain exceptions/outcomes to POSIX exit codes `0`–`4`).

## Complexity Tracking

No constitution violations — all design choices satisfy Principles I–VII without exceptions.
