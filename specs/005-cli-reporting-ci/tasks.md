# Tasks: Milestone 5 — CLI, Reporting & CI Integration (`005-cli-reporting-ci`)

**Input**: Design documents from `/specs/005-cli-reporting-ci/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [cli.md](contracts/cli.md), [public-api.md](contracts/public-api.md), [schemas-v1.json](contracts/schemas-v1.json), [quickstart.md](quickstart.md)

**Organization**: Tasks are grouped by user story (`US1`–`US5`) following Phase 1 Setup and Phase 2 Foundational prerequisites, preserving strict library purity (`types`, `datasets`, `execution`, `storage`, `metrics`, `judges`, `regression`, and `reporting` never import `cli`, `tomllib`, `tomli`, or `dotenv`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (`US1`, `US2`, `US3`, `US4`, `US5`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Packaging & Package Skeleton)

**Purpose**: Configure console script entrypoints, Python 3.10 conditional TOML parsing dependency, package skeletons, and test module structure.

- [X] T001 Configure `[project.scripts]` (`evalforge-maestro` and `evalforge_maestro` -> `evalforge_maestro.cli:main`) and conditional `"tomli>=2.0.1; python_version < '3.11'"` in [pyproject.toml](../../pyproject.toml), then update lockfile [uv.lock](../../uv.lock) via `uv lock`
- [X] T002 [P] Create cold-start-safe package skeleton [src/evalforge_maestro/reporting/__init__.py](../../src/evalforge_maestro/reporting/__init__.py) (`logging.NullHandler()` only) and thin [src/evalforge_maestro/cli/__init__.py](../../src/evalforge_maestro/cli/__init__.py) + [src/evalforge_maestro/cli/parser.py](../../src/evalforge_maestro/cli/parser.py) stub keeping heavy optional and config modules out of top-level imports
- [X] T003 [P] Create Milestone 5 test suite scaffolding in [tests/contract/test_m5_schemas.py](../../tests/contract/test_m5_schemas.py), [tests/unit/test_pii_security.py](../../tests/unit/test_pii_security.py), [tests/unit/test_replay_adapter.py](../../tests/unit/test_replay_adapter.py), [tests/unit/test_cli_config.py](../../tests/unit/test_cli_config.py), [tests/unit/test_reporting.py](../../tests/unit/test_reporting.py), [tests/integration/test_cli_workflow.py](../../tests/integration/test_cli_workflow.py), and [tests/integration/test_ci_templates.py](../../tests/integration/test_ci_templates.py)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core PII security guards, centralized M5 Pydantic schemas in `types.py`, offline replay adapter, stdlib `stderr` telemetry logger, configuration precedence resolver (`cli/config.py`), and pure reporting core (`reporting/`).

**⚠️ CRITICAL**: No User Story CLI implementation should begin until these shared contracts and boundaries are complete.

- [X] T004 [P] Implement `detect_pii_categories(value)` (email, phone, US SSN, Luhn-checked payment card, API/Bearer tokens returning category names only) in [src/evalforge_maestro/_canonical.py](../../src/evalforge_maestro/_canonical.py) and `validate_pii_egress` / `wrap_pii_guarded_metric` raising `LocalOnlyPolicyError` without echoing raw PII in [src/evalforge_maestro/judges/security.py](../../src/evalforge_maestro/judges/security.py)
- [X] T005 [P] Add Milestone 5 configuration enums and models in [src/evalforge_maestro/types.py](../../src/evalforge_maestro/types.py) implementing all constrained definitions in [data-model.md](data-model.md): `ConfigSourceTier`, `TargetType`, `MetricSpecConfig` (`MetricSpecConfig.metric_id`, `MetricSpecConfig.params`), `ResolvedSecurityConfig` (`ResolvedSecurityConfig.local_only`, `ResolvedSecurityConfig.block_pii`), `ResolvedTargetConfig` (`ResolvedTargetConfig.target_type`, `ResolvedTargetConfig.entrypoint`, `ResolvedTargetConfig.system_version`, `ResolvedTargetConfig.model_id`, `ResolvedTargetConfig.arg_mode`, `ResolvedTargetConfig.rag_extractors`, `ResolvedTargetConfig.docpipe_mode`, `ResolvedTargetConfig.docpipe_collection`, `ResolvedTargetConfig.docpipe_top_k`), `ResolvedJudgeSettings` (`ResolvedJudgeSettings.model`, `ResolvedJudgeSettings.api_base`, `ResolvedJudgeSettings.api_key`, `ResolvedJudgeSettings.temperature`, `ResolvedJudgeSettings.pass_threshold`, `ResolvedJudgeSettings.max_retries`, `ResolvedJudgeSettings.retry_backoff_seconds`, `ResolvedJudgeSettings.timeout_seconds`, `ResolvedJudgeSettings.prompt_version`, `ResolvedJudgeSettings.mock_mode`, `ResolvedJudgeSettings.local_only`, `ResolvedJudgeSettings.seed`, `ResolvedJudgeSettings.min_agreement`), `ResolvedLoggingConfig` (`ResolvedLoggingConfig.log_level`, `ResolvedLoggingConfig.log_json`), `ConfigSettingProvenance` (`ConfigSettingProvenance.key`, `ConfigSettingProvenance.value`, `ConfigSettingProvenance.source`, `ConfigSettingProvenance.masked`), and `CLIResolvedConfig` (`CLIResolvedConfig.schema_version`, `CLIResolvedConfig.config_path`, `CLIResolvedConfig.env_file_path`, `CLIResolvedConfig.storage_dir`, `CLIResolvedConfig.dataset`, `CLIResolvedConfig.dataset_id`, `CLIResolvedConfig.dataset_version`, `CLIResolvedConfig.executions_path`, `CLIResolvedConfig.run_id`, `CLIResolvedConfig.baseline`, `CLIResolvedConfig.trend_window`, `CLIResolvedConfig.strict`, `CLIResolvedConfig.target`, `CLIResolvedConfig.metrics`, `CLIResolvedConfig.execution`, `CLIResolvedConfig.judge`, `CLIResolvedConfig.security`, `CLIResolvedConfig.gate`, `CLIResolvedConfig.logging`, `CLIResolvedConfig.provenance`) with unconditional secret redaction on `CLIResolvedConfig`
- [X] T006 Add Milestone 5 reporting and CLI payload models in [src/evalforge_maestro/types.py](../../src/evalforge_maestro/types.py) implementing all constrained definitions in [data-model.md](data-model.md): `ReportKind`, `EvidenceDecouplingCategory`, `DecoupledEvidenceDiagnostic` (`DecoupledEvidenceDiagnostic.case_id`, `DecoupledEvidenceDiagnostic.mandatory`, `DecoupledEvidenceDiagnostic.category`, `DecoupledEvidenceDiagnostic.passed_metrics`, `DecoupledEvidenceDiagnostic.failed_metrics`, `DecoupledEvidenceDiagnostic.retrieved_chunk_ids`, `DecoupledEvidenceDiagnostic.explanation`), `ReportDiagnosticsSummary` (`ReportDiagnosticsSummary.mandatory_failed_case_ids`, `ReportDiagnosticsSummary.decoupled_evidence_cases`, `ReportDiagnosticsSummary.anomaly_highlights`, `ReportDiagnosticsSummary.drift_highlights`), `CalibrationGateSummary` (`CalibrationGateSummary.min_agreement`, `CalibrationGateSummary.observed_agreement`, `CalibrationGateSummary.strict`, `CalibrationGateSummary.valid_cases`, `CalibrationGateSummary.inconclusive_cases`, `CalibrationGateSummary.passed`, `CalibrationGateSummary.reason`), `ReportDocument` (`ReportDocument.schema_version`, `ReportDocument.report_kind`, `ReportDocument.title`, `ReportDocument.generated_at`, `ReportDocument.evaluation`, `ReportDocument.comparison`, `ReportDocument.trend`, `ReportDocument.calibration`, `ReportDocument.gate`, `ReportDocument.calibration_gate`, `ReportDocument.diagnostics`), `BaselineCommandPayload` (`BaselineCommandPayload.schema_version`, `BaselineCommandPayload.action`, `BaselineCommandPayload.entry`, `BaselineCommandPayload.baselines`), `ConfigValidationPayload` (`ConfigValidationPayload.schema_version`, `ConfigValidationPayload.valid`, `ConfigValidationPayload.config_path`, `ConfigValidationPayload.env_file_path`, `ConfigValidationPayload.warnings`), and `CLIErrorPayload` (`CLIErrorPayload.schema_version`, `CLIErrorPayload.exit_code`, `CLIErrorPayload.error_type`, `CLIErrorPayload.message`, `CLIErrorPayload.hint`)
- [X] T007 [P] Implement `stderr`-only logger and `--log-json` / `--log-level` secret-scrubbed formatter in [src/evalforge_maestro/cli/logging_utils.py](../../src/evalforge_maestro/cli/logging_utils.py)
- [X] T008 [P] Implement offline `ReplayAdapter` (`from_file` supporting JSONL `ExecutionResult`, JSON list, or `RunRecord`, duplicate `case_id` rejection, and `TargetAdapter` contract) in [src/evalforge_maestro/adapters/replay.py](../../src/evalforge_maestro/adapters/replay.py) and export in [src/evalforge_maestro/adapters/__init__.py](../../src/evalforge_maestro/adapters/__init__.py)
- [X] T009 Implement 5-tier configuration precedence resolver (`CLI flags > OS env > opt-in --env-file > non-recursive CWD evalforge.toml > defaults`), lazy `tomllib`/`tomli` import, strict pure-stdlib `.env` parser, TOML validation (`extra="forbid"` -> `ConfigurationError`), non-fatal hygiene warning detection (e.g., plaintext secret key present in `evalforge.toml`, never echoing raw secret values), and secret masking returning `(CLIResolvedConfig, raw_runtime_api_key, warnings)` in [src/evalforge_maestro/cli/config.py](../../src/evalforge_maestro/cli/config.py)
- [X] T010 Implement library-pure reporting engine (`detect_decoupled_evidence`, `build_run_report`, `build_comparison_report`, `build_trend_report`, `build_calibration_report`, `render_report_json`) in [src/evalforge_maestro/reporting/builder.py](../../src/evalforge_maestro/reporting/builder.py) and three-way Markdown formatter (`render_markdown` preserving **Evaluation**, **Regression**, **Acceptance / Quality Gate** sections and `scrub_secret_text` redaction) in [src/evalforge_maestro/reporting/markdown.py](../../src/evalforge_maestro/reporting/markdown.py), exported via [src/evalforge_maestro/reporting/__init__.py](../../src/evalforge_maestro/reporting/__init__.py)

**Checkpoint**: Shared schemas, security helpers, `ReplayAdapter`, config resolver, and pure reporting engine ready for all CLI user stories.

---

## Phase 3: User Story 1 — `evalforge-maestro run` & POSIX Exit Codes `0`–`4` (Priority: P1) 🎯 MVP

**Goal**: Deliver end-to-end CLI evaluation execution (`run`) supporting `--mock --local-only`, live `callable`/`rag`/`docpipe` targets, `--executions` replay, explicit baseline/trend gating, JSON/Markdown exports, and deterministic POSIX exit codes `0`–`4`.

**Independent Test**: Invoke `evalforge-maestro run` in isolated subprocess/CLI tests across passing offline `--mock --local-only` datasets, mandatory case failures, `--strict` escalations, replay alignment errors (`exit 2`), `--fail-fast` / zero-case runtime faults / missing extras (`exit 3`), and `--local-only` / `--block-pii` pre-network blocks (`exit 4`), asserting deterministic outputs (`@pytest.mark.gate_determinism`) and clean `stdout` vs `stderr` streams.

### Tests for User Story 1

- [X] T011 [P] [US1] Write unit tests covering `detect_pii_categories`, Luhn payment-card precision, pre-network `--block-pii` `LocalOnlyPolicyError` interception without raw PII leakage, and remote-only scope in [tests/unit/test_pii_security.py](../../tests/unit/test_pii_security.py)
- [X] T012 [P] [US1] Write unit tests covering `ReplayAdapter` JSONL/JSON/`RunRecord` loading, duplicate `case_id` errors, missing case errors, and empty/malformed traces in [tests/unit/test_replay_adapter.py](../../tests/unit/test_replay_adapter.py)
- [X] T013 [P] [US1] Write integration and `@pytest.mark.gate_determinism` tests for `run` covering `--mock --local-only` (asserting identical scores, `judge_config_fingerprint`, anomaly/drift flags, gate verdicts, and exit codes across runs when normalizing volatile wall-clock `run_id`/`timestamp`/`generated_at`), `callable`/`rag`/`docpipe`/`--executions` targets, replay missing-case `exit 2`, zero-metric `exit 2`, `--strict`, `--fail-fast` & zero-case `exit 3`, `MissingExtraError` `exit 3`, `--local-only` & `--block-pii` `exit 4`, `--quiet` file-only mode, and `--json` (including parse-error `CLIErrorPayload`) + `--log-json` stream separation in [tests/integration/test_cli_workflow.py](../../tests/integration/test_cli_workflow.py)

### Implementation for User Story 1

- [X] T014 [US1] Implement target adapter resolution (`callable` / `rag` `module:symbol` loading, `DocpipeAdapter`, `ReplayAdapter` with upfront 1:1 selected-case coverage check logging unused extra trace IDs to `stderr`), metric spec construction (rejecting empty/unknown metrics with `ConfigurationError`), and pre-network `--block-pii` checks (`validate_pii_egress` / `wrap_pii_guarded_metric`) in [src/evalforge_maestro/cli/targets.py](../../src/evalforge_maestro/cli/targets.py)
- [X] T015 [US1] Implement complete `evalforge-maestro run` argument parser options (`--dataset`, `--dataset-id`, `--dataset-version`, `--executions`, `--target`, `--target-type`, `--target-arg-mode`, `--system-version`, `--model-id`, `--docpipe-mode`, `--docpipe-collection`, `--docpipe-top-k`, `--metric`, `--mock`, `--local-only`, `--block-pii`, `--judge-model`, `--judge-api-base`, `--judge-temperature`, `--judge-pass-threshold`, `--judge-max-retries`, `--judge-timeout`, `--seed`, `--baseline`, `--trend-window`, `--strict`, `--fail-fast`, `--max-concurrency`, `--max-dataset-cases`, `--max-context-chars`, `--case-timeout`, `--max-memory-mb`, `--memory-limit-action`, `--run-id`, `--json`, `--json-out`, `--markdown-out`, `--output`) and global flags (`--version`, `--config`, `--env-file`, `--storage-dir`, `--log-level`, `--log-json`, `--json`, `--quiet`/`-q`), including custom parser error handling so syntax/usage errors under `--json` emit `CLIErrorPayload(exit_code=2)` on `stdout` + usage on `stderr`, in [src/evalforge_maestro/cli/parser.py](../../src/evalforge_maestro/cli/parser.py)
- [X] T016 [US1] Implement `run` command execution, optional explicit baseline/trend gate evaluation (omitting implicit `"default"` baseline unless explicitly configured), zero-case-completed runtime fault detection (`exit 3`), centralized exception-to-POSIX exit code (`0`–`4`) mapping with `CLIErrorPayload` support, dual file/stream writers (respecting `--quiet` on non-`--json` `stdout`), and `main()` dispatcher in [src/evalforge_maestro/cli/commands.py](../../src/evalforge_maestro/cli/commands.py) and [src/evalforge_maestro/cli/__init__.py](../../src/evalforge_maestro/cli/__init__.py)

**Checkpoint**: User Story 1 (`evalforge-maestro run`) is independently complete, testable offline, and delivers deterministic MVP CLI gating.

---

## Phase 4: User Story 2 — `compare`, `trend`, `calibrate` & `baseline` Subcommands (Priority: P1)

**Goal**: Enable pairwise baseline comparison, sliding-window OLS trend analysis, judge calibration diagnostics against human ground-truth samples, and immutable-safe baseline alias management directly via CLI.

**Independent Test**: Run `baseline set|list|show|delete`, `compare`, `trend --window N`, and `calibrate --mock --local-only` across seeded immutable `.evalforge/` stores and calibration JSONL fixtures, asserting zero run mutation (`@pytest.mark.gate_immutability`), accurate deltas/slopes/drift/agreement outputs, `--min-agreement` / `--strict` `0` vs `1` gating, and JSON/Markdown exports.

### Tests for User Story 2

- [X] T017 [P] [US2] Write integration and `@pytest.mark.gate_immutability` tests for `baseline` (`set`, `list`, `show`, `delete`, duplicate-without-`--overwrite` `exit 2`, unknown alias `exit 2`), `compare`, `trend` (`window < 2` -> `exit 2`, `0`/`1`-run `INSUFFICIENT_DATA`, `--strict`), and `calibrate` (`--mock --local-only`, `--min-agreement` pass/fail -> `0`/`1`, `--strict` on inconclusive/zero valid cases -> `1`, `--block-pii` remote -> `4`) in [tests/integration/test_cli_workflow.py](../../tests/integration/test_cli_workflow.py)

### Implementation for User Story 2

- [X] T018 [US2] Add subcommand parsers for `compare` (`--baseline`, `--strict`, `--min-score`, `--max-regression-drop`, `--json`, `--json-out`, `--markdown-out`, `--output`), `trend` (`--window`, `--dataset-id`, `--all-datasets`, `--model-id`, `--metric`, `--slope-threshold`, `--strict`, `--json`, `--json-out`, `--markdown-out`, `--output`), `calibrate` (`--samples`, `--metric`, `--mock`, `--local-only`, `--block-pii`, `--judge-model`, `--judge-api-base`, `--judge-pass-threshold`, `--human-threshold`, `--score-divergence-threshold`, `--min-agreement`, `--strict`, `--max-concurrency`, `--json`, `--json-out`, `--markdown-out`, `--output`), and `baseline` (`set`, `list`, `show`, `delete`/`remove`) matching [contracts/cli.md](contracts/cli.md) in [src/evalforge_maestro/cli/parser.py](../../src/evalforge_maestro/cli/parser.py)
- [X] T019 [US2] Implement `compare` (applying `--min-score`/`--max-regression-drop`/`--strict` gate overrides), `trend` (including clean `0`-run `INSUFFICIENT_DATA` policy evaluation without crashing), `calibrate` (strict `HumanCalibrationSample` JSONL/JSON ingestion, judge target instantiation, `acalibrate_judge`, `min_agreement`/`strict` exit logic), and `baseline` (`BaselineCommandPayload` `--json` and table rendering) handlers in [src/evalforge_maestro/cli/commands.py](../../src/evalforge_maestro/cli/commands.py)

**Checkpoint**: Full lifecycle CLI operations (`run`, `baseline`, `compare`, `trend`, `calibrate`) work seamlessly together.

---

## Phase 5: User Story 3 — Configuration Precedence, `--env-file`, `config` Subcommands & Secret Masking (Priority: P1)

**Goal**: Provide `config show --resolved` and `config validate`, proving strict 5-layer precedence, non-recursive CWD `evalforge.toml` discovery, explicit `--env-file` opt-in semantics, fail-fast TOML validation (`exit 2`), and zero plaintext credential leaks across every output surface.

**Independent Test**: Combine CWD `evalforge.toml`, parent-directory `evalforge.toml`, explicit `--env-file`, OS `EVALFORGE_*` vars, CLI overrides, invalid TOML/unknown keys, malformed `--env-file`, and mock API keys/tokens, asserting exact provenance attribution, exit code `2` on invalid inputs, and complete credential masking across `config show --resolved`, `--json`, Markdown, logs, and `.evalforge/`.

### Tests for User Story 3

- [X] T020 [P] [US3] Write comprehensive unit tests covering 5-tier precedence (`cli > env > env_file > file > default`), non-recursive CWD `evalforge.toml`, explicit `--config` / `--env-file` missing or malformed errors (`ConfigurationError`), unknown key rejection, and secret masking across `CLIResolvedConfig` and provenance in [tests/unit/test_cli_config.py](../../tests/unit/test_cli_config.py)
- [X] T021 [P] [US3] Write CLI integration tests verifying `config show --resolved` (text & `--json` provenance), `config validate`, bad TOML `exit 2`, and end-to-end zero plaintext secrets across `stdout`, `stderr`, Markdown files, and `.evalforge/` in [tests/integration/test_cli_workflow.py](../../tests/integration/test_cli_workflow.py)

### Implementation for User Story 3

- [X] T022 [US3] Add `config` subcommand parser (`show --resolved`, `validate`) in [src/evalforge_maestro/cli/parser.py](../../src/evalforge_maestro/cli/parser.py)
- [X] T023 [US3] Implement human-readable secret-masked resolved configuration formatter and `config show` / `config validate` handlers (surfacing non-fatal config hygiene `warnings` on `stderr` and inside `ConfigValidationPayload.warnings` alongside `CLIResolvedConfig` `--json`) in [src/evalforge_maestro/cli/config.py](../../src/evalforge_maestro/cli/config.py) and [src/evalforge_maestro/cli/commands.py](../../src/evalforge_maestro/cli/commands.py)

**Checkpoint**: Configuration resolution, opt-in env-file support, validation, and secret redaction are fully verified.

---

## Phase 6: User Story 4 — `report` Subcommand & Diagnostic Reporting Verification (Priority: P2)

**Goal**: Expose the `evalforge-maestro report` subcommand and verify library-pure JSON and Markdown reporting clearly distinguishes Evaluation, Regression, and Quality Gate outcomes while surfacing mandatory failures, `> 0.3` inter-metric disagreements, retrieval-vs-answer decoupling failures, and drift alerts with secret redaction.

**Independent Test**: Execute `reporting/` unit tests and Draft 2020-12 contract tests directly in Python (with zero CLI involvement) plus `evalforge-maestro report` across stored run IDs, comparisons, trends, and JSON artifact files (`RunRecord`, `RunComparisonReport`, `TrendReport`, `CalibrationReport`, `ReportDocument`), verifying schema validity, immutable run safety, and Markdown diagnostic sections.

### Tests for User Story 4

- [X] T024 [P] [US4] Write unit tests verifying `detect_decoupled_evidence` (both answer-pass/retrieval-fail and retrieval-pass/answer-fail cases), mandatory case failure surfacing, `> 0.3` disagreement & aggregate-masked-drop highlights, Three-Way Markdown section ordering (`Evaluation`, `Regression`, `Acceptance / Quality Gate`), and secret scrubbing inside [tests/unit/test_reporting.py](../../tests/unit/test_reporting.py)
- [X] T025 [P] [US4] Write Draft 2020-12 JSON schema contract tests validating merged M1–M5 `schemas-v1.json` and runtime serialized `CLIResolvedConfig`, `ReportDocument`, `BaselineCommandPayload`, `ConfigValidationPayload`, and `CLIErrorPayload` instances in [tests/contract/test_m5_schemas.py](../../tests/contract/test_m5_schemas.py)

### Implementation for User Story 4

- [X] T026 [US4] Add `report` subcommand parser (`--run`, `--compare`, `--trend`, `--artifact`, `--baseline`, `--window`, `--json`, `--json-out`, `--markdown-out`, `--output`) in [src/evalforge_maestro/cli/parser.py](../../src/evalforge_maestro/cli/parser.py)
- [X] T027 [US4] Implement `report` artifact loader & subcommand handler (supporting stored runs, comparisons, trends, and disk JSON artifacts `ReportDocument` / `RunRecord` / `RunComparisonReport` / `TrendReport` / `CalibrationReport`, read-only with `StorageError`/`DatasetError` -> `exit 2`) in [src/evalforge_maestro/cli/commands.py](../../src/evalforge_maestro/cli/commands.py), and finalize edge-case Markdown formatting/redaction in [src/evalforge_maestro/reporting/markdown.py](../../src/evalforge_maestro/reporting/markdown.py)

**Checkpoint**: Both SDK reporting APIs and CLI `report` produce schema-validated JSON and Three-Way Markdown reports cleanly.

---

## Phase 7: User Story 5 — User CI Integration Templates, Cold-Start & Release Readiness (Priority: P2)

**Goal**: Provide ready-to-use GitHub Actions CI workflow templates and sample assets, enforce CLI `--help` cold-start & `reporting/` AST purity in CI, extend cross-OS minimal wheel/sdist & TestPyPI pipeline checks to cover CLI entrypoints, and complete MVP README documentation.

**Independent Test**: Execute clean-subprocess cold-start `evalforge-maestro --help` checks verifying zero optional imports (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `jsonschema`, `tomllib`, `tomli`, `dotenv`), run the `examples/ci/` offline `--mock --local-only` evaluation & comparison workflow end-to-end inside `tests/integration/test_ci_templates.py`, and validate packaging workflows (`uv build`, `twine check --strict`, `--no-dev` minimal install).

### Tests & Templates for User Story 5

- [X] T028 [P] [US5] Extend [tests/test_library_purity.py](../../tests/test_library_purity.py) with AST checks forbidding `reporting/` from importing `cli`, `tomllib`, `tomli`, `dotenv`, `adapters`, `datasets`, or `execution`, enforcing lazy `tomllib`/`tomli` inside `cli/`, and adding subprocess cold-start probes verifying `evalforge-maestro --help`, `evalforge_maestro --help`, and `evalforge-maestro run --help` load zero heavy optional modules
- [X] T029 [P] [US5] Author copy-ready user GitHub Actions workflow template [examples/ci/evalforge-ci.yml](../../examples/ci/evalforge-ci.yml), starter [examples/ci/evalforge.toml](../../examples/ci/evalforge.toml), [examples/ci/golden-sample.jsonl](../../examples/ci/golden-sample.jsonl), and [examples/ci/executions-sample.jsonl](../../examples/ci/executions-sample.jsonl)
- [X] T030 [US5] Implement end-to-end template validation executing the offline `--mock --local-only` workflow commands from `examples/ci/evalforge-ci.yml` against `examples/ci/` fixtures and verifying JSON + Markdown PR summary artifacts in [tests/integration/test_ci_templates.py](../../tests/integration/test_ci_templates.py)

### CI/CD Pipeline & Documentation for User Story 5

- [X] T031 [P] [US5] Extend [.github/workflows/ci.yml](../../.github/workflows/ci.yml) (`cross-os-and-packaging` minimal `--no-dev` wheel/sdist checks resolving POSIX `bin/` and Windows `Scripts/` console scripts cleanly) and [.github/workflows/release.yml](../../.github/workflows/release.yml) (`verify-testpypi`) to execute CLI `--help`, `--version`, cold-start `sys.modules`, and clean-venv offline `evalforge-maestro run --mock --local-only` smoke tests
- [X] T032 [P] [US5] Update [README.md](../../README.md) with complete MVP documentation covering CLI installation, subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`), `evalforge.toml` configuration precedence, POSIX exit codes `0`–`4`, Milestones 3–5 summaries, and GitHub Actions adoption via `examples/ci/`

**Checkpoint**: User CI integration templates, cold-start isolation, cross-OS packaging CLI smoke checks, and release pipeline updates are complete.

---

## Phase 8: Polish & Cross-Cutting Verification

**Purpose**: Wire public SDK exports cleanly, lock API stability tests, and execute every Constitution Principle VII static, security, coverage, determinism/immutability, and packaging verification gate.

- [X] T033 Export M5 reporting, `ReplayAdapter`, PII helpers, and M5 Pydantic contracts cleanly in [src/evalforge_maestro/__init__.py](../../src/evalforge_maestro/__init__.py) (keeping `cli` unimported on SDK cold start) and update pinned public API assertions in [tests/test_api_stability.py](../../tests/test_api_stability.py)
- [X] T034 Code review cleanup, zero duplication check across CLI subcommands/reporting modules, and docstring consistency across modified source files under [src/evalforge_maestro/](../../src/evalforge_maestro)
- [X] T035 Execute full Constitution Principle VII verification & [quickstart.md](quickstart.md) validation suite: `uv lock --check`, `ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`, `pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85`, `100%` branch coverage on `evalforge_maestro.metrics` & `evalforge_maestro.regression.gate`, `-m "gate_determinism or gate_immutability"`, `pip-audit`, `uv build`, `twine check --strict dist/*`, and isolated `--no-dev` clean-venv wheel + CLI `--help`/smoke install verification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — starts immediately (`T001` updates `pyproject.toml`/`uv.lock` first or alongside `[P]` `T002`, `T003`).
- **Foundational (Phase 2)**: Depends on Setup completion (`T002`, `T003` — and `T001` for editable/installed script entrypoints). **BLOCKS all User Stories**.
  - Inside Phase 2: `T004`, `T005`, `T006`, `T007`, `T008` run in parallel on separate modules (`_canonical.py`/`judges/security.py`, `types.py` config section vs report section sequentially/cleanly, `cli/logging_utils.py`, `adapters/replay.py`), followed by `T009` (`cli/config.py`) and `T010` (`reporting/`). Note: `T005` and `T006` both edit `src/evalforge_maestro/types.py`, so `T006` runs right after `T005` during execution.
- **User Stories (Phases 3–7)**: All depend on Phase 2 completion.
  - **US1 (`P1`)** delivers `run` (`cli/targets.py`, `cli/parser.py`, `cli/commands.py` + `exit 0`–`4` infrastructure) -> **US2 (`P1`)** extends `parser.py` & `commands.py` with `compare`, `trend`, `calibrate`, `baseline` -> **US3 (`P1`)** extends `parser.py`, `config.py`, & `commands.py` with `config show --resolved` / `config validate` -> **US4 (`P2`)** extends `parser.py` & `commands.py` with `report` -> **US5 (`P2`)** packages/tests `examples/ci/`, purity cold-start probes, CI/release workflows, and `README.md`.
- **Polish (Phase 8)**: Depends on completion of US1–US5 (`T033` -> `T034` -> `T035`).

### Parallel Opportunities

- Setup: `T002` and `T003` run cleanly in parallel after `T001`.
- Foundational: `T004`, `T005`->`T006`, `T007`, and `T008` target separate subsystems and run concurrently.
- Within each User Story: `[P]` test authoring tasks (`T011`, `T012`, `T013` for US1; `T020`, `T021` for US3; `T024`, `T025` for US4; `T028`, `T029`, `T031`, `T032` for US5) can execute in parallel on distinct files before integrating shared `parser.py`/`commands.py` edits sequentially.

---

## Parallel Example: Foundational & User Story 1

```bash
# Phase 2 parallel foundation slices:
Task: "PII egress helpers in _canonical.py and judges/security.py" (T004)
Task: "M5 Pydantic schemas in types.py" (T005 -> T006)
Task: "Stderr logging formatter in cli/logging_utils.py" (T007)
Task: "ReplayAdapter in adapters/replay.py" (T008)

# Phase 3 (US1) parallel test suite creation:
Task: "PII security unit tests in tests/unit/test_pii_security.py" (T011)
Task: "ReplayAdapter unit tests in tests/unit/test_replay_adapter.py" (T012)
Task: "CLI run integration & determinism gate tests in tests/integration/test_cli_workflow.py" (T013)
```

---

## Implementation Strategy

### MVP First (Phase 1 + Phase 2 + User Story 1)

1. Complete Phase 1 Setup (`pyproject.toml` `[project.scripts]` + `tomli` marker + skeleton).
2. Complete Phase 2 Foundational contracts, PII helpers, `ReplayAdapter`, `cli/config.py`, and pure `reporting/`.
3. Complete Phase 3 (US1 — `evalforge-maestro run` + exit codes `0`–`4`) -> verify `evalforge-maestro run --mock --local-only` end-to-end immediately.

### Incremental Delivery

1. Add US2 (`compare`, `trend`, `calibrate`, `baseline`) -> test full regression/calibration CLI loop.
2. Add US3 (`config show --resolved`, `config validate`) -> verify 5-tier config precedence & secret redaction.
3. Add US4 (`report` subcommand + decoupled-evidence/three-way report tests) -> verify standalone reporting + JSON schemas.
4. Add US5 (`examples/ci/` templates, `--help` cold-start purity, workflow & README updates) -> run full Phase 8 release verification (`T033`–`T035`).
