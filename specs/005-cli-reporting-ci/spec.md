# Feature Specification: Milestone 5 — CLI, Reporting & CI Integration

**Feature Branch**: `005-cli-reporting-ci`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "start 005" — Milestone 5: CLI, Reporting & CI Integration (`005-cli-reporting-ci`), completing the EvalForge Maestro MVP by delivering the command-line workflow (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`), strict layered configuration resolution (`CLI flags > EVALFORGE_* > evalforge.toml > defaults`) with secret masking, strict `stdout`/`stderr` stream separation, deterministic POSIX exit codes (`0`–`4`), library-pure Markdown and schema-validated JSON reporting, CLI cold-start isolation, user-facing GitHub Actions CI integration templates, and full MVP TestPyPI/PyPI release validation readiness.

## Clarifications

### Session 2026-11-19

- Q: Which target input modes should `evalforge-maestro run` support directly from CLI flags and `evalforge.toml`? (`FR-003`) -> A: **Option A** — Support both live target adapter bindings (`callable` / `rag` import references and `docpipe` target configuration) AND optional offline replay from pre-captured execution-trace files (`--executions`).
- Q: How should CLI entrypoints treat `.env` files relative to the constitutional 4-tier precedence (`CLI flags > EVALFORGE_* > evalforge.toml > defaults`)? (`FR-006`) -> A: **Option A** — Support explicit opt-in `.env` loading only when `--env-file <path>` is passed (never auto-reading implicit CWD `.env` files); values from `--env-file` fill missing process environment variables strictly below OS-exported `EVALFORGE_*` variables and above `evalforge.toml`, and missing/unparseable `--env-file` paths fail cleanly with exit code `2`.
- Q: What outbound security inspection should trigger exit code `4` alongside `--local-only` remote endpoint checks? (`FR-011`) -> A: **Option B** — Keep heuristic PII egress blocking opt-in via `--block-pii` (or equivalent `[security].block_pii` config policy); when enabled, scan outbound payloads before non-mock remote target/judge transmission (email, phone, SSN, payment card, and secret/token patterns) and abort pre-network with exit code `4`, while `--local-only` remote-endpoint blocking and credential redaction remain active independently.
- Q: When running `evalforge-maestro run` without an explicit baseline option, should regression comparison run automatically against a stored default baseline or only when explicitly configured? (`FR-002`) → A: Compare against a baseline only when specified via CLI option (`--baseline`) or configuration (`evalforge.toml` / env); otherwise run evaluation and threshold/mandatory quality gates standalone.
- Q: How should `evalforge-maestro calibrate` determine whether to exit with code `0` or code `1`? (`FR-012`) → A: Diagnostic by default (`exit 0`), returning `exit 1` only when an explicitly configured minimum agreement threshold (`--min-agreement` or config) is breached or `--strict` is active alongside zero valid/inconclusive calibration outcomes.
- Q: When `--json` is not enabled, what should CLI commands write to `stdout` versus `stderr`? (`FR-009`, `FR-016`) → A: Primary command output (Markdown report/summary for `run`/`compare`/`trend`/`calibrate`/`report`, resolved config for `config show --resolved`, listing/info for `baseline`) writes to `stdout` by default; logs, warnings, progress telemetry, and errors always write strictly to `stderr` (and `--json` guarantees `stdout` emits solely the schema-validated JSON payload).
- Q: When replaying pre-captured execution traces via `evalforge-maestro run --executions`, how should missing matches for dataset cases be handled? (`FR-003`) → A: Fail upfront with validation error (`exit 2`) before scoring if any selected dataset case lacks a matching execution record (ignoring unreferenced extra execution records while warning cleanly on `stderr`).
- Q: What should `evalforge-maestro run` do when no metrics are specified via CLI options, environment variables, or `evalforge.toml`? (`FR-002`, `FR-005`) → A: Require at least one configured metric (`--metric`, `EVALFORGE_*`, or `evalforge.toml`) and fail immediately with configuration error code `2` when zero metrics are configured.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run End-to-End Evaluations and Enforce Release Gates from the Command Line (Priority: P1)

An AI/ML engineer or CI automation job invokes `evalforge-maestro run` (or `evalforge_maestro run`) to evaluate a versioned dataset against a target AI system and selected metrics (optionally in zero-network offline `--mock --local-only` mode), persist an immutable run artifact and ledger entry, check acceptance thresholds against a designated baseline or quality policy, emit machine-readable JSON or human-readable Markdown diagnostics, and receive a deterministic POSIX exit code suitable for gating merges or builds.

**Why this priority**: Command-line execution with deterministic exit codes and offline `--mock --local-only` support is the primary day-to-day interface for local iteration and automated CI/CD regression checks; without it, teams must write custom runner scripts for every project.

**Independent Test**: Can be fully tested by invoking the CLI `run` command in an isolated workspace against golden JSONL datasets, mock and live-simulated targets, failing mandatory cases, threshold breaches, and `--local-only` blocked endpoints, then verifying persisted immutable artifacts, `stdout`/`stderr` isolation, and exact exit codes `0` through `4`.

**Acceptance Scenarios**:

1. **Given** a valid evaluation dataset, configured deterministic/judge metrics, and passing target outputs in offline `--mock --local-only` mode, **When** the user invokes `evalforge-maestro run --mock --local-only --json`, **Then** the command completes with zero external network calls or API keys, persists an immutable run record and manifest ledger entry, writes strictly schema-validated JSON only to `stdout` (all diagnostics on `stderr`), and exits with code `0`.
2. **Given** an evaluation run where a mandatory test case fails, a quality gate threshold is breached, or `--strict` is active alongside a `WARNING` or `INCONCLUSIVE` outcome, **When** `evalforge-maestro run` evaluates the quality gate policy, **Then** it records the persisted evidence, reports the exact gate failure or escalation reasons, and exits with code `1`.
3. **Given** repeated `evalforge-maestro run --mock --local-only` invocations with identical datasets, target responses, policies, and random seeds, **When** comparing results across invocations, **Then** metric scores, anomaly flags, gate determinations, and exit codes are identical across runs.
4. **Given** an evaluation target or judge configuration that attempts outbound access to a remote non-loopback endpoint while `--local-only` is active, **When** `evalforge-maestro run --local-only` executes pre-network checks, **Then** execution aborts before transmitting any evaluation data and exits with code `4`.
5. **Given** a single evaluation case encounters an isolated runtime error during execution while other cases succeed and `--fail-fast` is not enabled, **When** the run finishes, **Then** the error is recorded cleanly inside that case's captured result without crashing the remaining batch; if `--fail-fast` is enabled or zero cases complete, the command exits with code `3`.

---

### User Story 2 - Compare Runs, Track Sliding Trends, Calibrate Judges, and Manage Pinned Baselines via CLI (Priority: P1)

A technical lead, QA engineer, or domain reviewer uses dedicated CLI subcommands (`compare`, `trend`, `calibrate`, and `baseline`) to pin trusted runs as named baselines, perform pairwise comparisons between candidate runs and baselines, inspect performance trajectories across sliding windows of historical runs, and calibrate model-based judges against human ground-truth samples without ever mutating historical run records.

**Why this priority**: Continuous quality verification requires comparing candidate releases against trusted baselines, detecting gradual multi-run degradation, pinning/inspecting baselines cleanly, and verifying judge alignment with human reviewers directly from CLI workflows.

**Independent Test**: Can be fully tested by running `baseline`, `compare`, `trend`, and `calibrate` subcommands across pre-seeded immutable run histories and human calibration sample datasets, verifying baseline pinning/listing/inspection/removal, delta/slope/drift/anomaly outputs, calibration metrics, JSON/Markdown exports, and deterministic exit codes.

**Acceptance Scenarios**:

1. **Given** stored immutable runs in the local artifact store, **When** a user runs `evalforge-maestro baseline` actions to pin a specific run under a baseline name, list saved baselines, inspect a baseline, or delete a baseline alias, **Then** the baseline registry updates accurately while every underlying historical run record remains bit-for-bit unmodified.
2. **Given** a candidate run and a reference baseline (specified by run ID or pinned baseline name), **When** the user executes `evalforge-maestro compare`, **Then** the system reports aggregate deltas, per-case regressions, cross-version configuration/dataset drift warnings, and quality gate outcomes in schema-validated JSON and/or Markdown, exiting with `0` or `1` according to policy and `--strict`.
3. **Given** a sequence of historical runs in the local store, **When** the user runs `evalforge-maestro trend --window N`, **Then** the command computes linear trend slopes and anomalies across the most recent `N` runs (or reports `INSUFFICIENT_DATA` cleanly when fewer than two runs exist, while failing with exit code `2` if `N < 2`) and enforces any configured trend gate rules.
4. **Given** a dataset of human-labeled calibration samples and judge configuration, **When** the user runs `evalforge-maestro calibrate` (supporting `--mock` and `--local-only`), **Then** the command outputs exact agreement rate (%), `too_generous_rate`, `too_harsh_rate`, mean score delta, detailed disagreement items, and a recommended calibrated pass threshold in JSON and/or Markdown format.

---

### User Story 3 - Resolve Configuration Deterministically, Mask Secrets, and Inspect Effective Settings (Priority: P1)

A developer or DevOps engineer manages shared evaluation defaults in a project-level `evalforge.toml` file, overrides settings with `EVALFORGE_*` environment variables in CI, applies per-command CLI flags, and runs `evalforge-maestro config show --resolved` to audit active settings without risking accidental credential exposure in terminal logs or saved artifacts.

**Why this priority**: Misconfigured precedence rules or leaked API keys in CI logs and persisted run artifacts are critical operational and security hazards; teams must be able to inspect effective settings confidently across local and CI environments.

**Independent Test**: Can be fully tested by combining `evalforge.toml` files in CWD, `EVALFORGE_*` variables, explicit CLI flags, invalid TOML/schema inputs, and sensitive secret tokens, then asserting exact precedence order, masked secret output in `config show --resolved`, and exit code `2` on invalid configuration.

**Acceptance Scenarios**:

1. **Given** overlapping settings defined in built-in defaults, `evalforge.toml` in the current working directory, `EVALFORGE_*` environment variables, and explicit CLI flags, **When** any CLI command or `evalforge-maestro config show --resolved` evaluates configuration, **Then** values resolve strictly in order: `CLI flags > Environment variables > evalforge.toml > Built-in defaults`, and `config show --resolved` indicates effective values without leaking raw credentials.
2. **Given** an `evalforge.toml` file placed in a parent directory above the current working directory (without an explicit config file override), **When** CLI configuration discovery runs, **Then** discovery stays strictly non-recursive in the current working directory so unexpected parent settings are never inherited silently.
3. **Given** malformed TOML syntax, unknown configuration keys, out-of-bounds parameter values, or an explicit config path that does not exist, **When** any CLI command initializes configuration, **Then** it emits a clear diagnostic error on `stderr` and exits with code `2`.
4. **Given** API keys, bearer tokens, or credentialed URLs passed via environment settings or provider configuration, **When** `config show --resolved`, `RunRecord`, ledger entries, Markdown reports, `--json` payloads, or `stderr` logs are generated, **Then** all secrets remain masked/redacted and never appear in plaintext.

---

### User Story 4 - Export Schema-Validated JSON and Human-Readable Markdown Diagnostic Reports (Priority: P2)

A technical lead, QA reviewer, or compliance auditor runs `evalforge-maestro report` (or requests dual output during `run`, `compare`, `trend`, or `calibrate`) to export both machine-parseable JSON and clear Markdown reports that separate evaluation performance, regression comparison, and gate acceptance while exposing mandatory failures, evidence decoupling issues, and anomalies.

**Why this priority**: Machine-validated JSON enables downstream automation while structured Markdown summaries make CI pull request reviews and human audits fast and transparent without building a web dashboard.

**Independent Test**: Can be fully tested by generating reports from persisted run, comparison, trend, and calibration artifacts (including cases with high average scores masking a mandatory failure, retrieval-vs-answer decoupling failures, and `> 0.3` inter-metric disagreements) and verifying separation of Evaluation/Regression/Gate sections, secret redaction, schema validity, and pure library rendering without CLI imports.

**Acceptance Scenarios**:

1. **Given** a persisted run, comparison, trend, or calibration artifact containing a passing aggregate score that masks a mandatory case failure or high sub-metric disagreement (`> 0.3`), **When** generating a Markdown report, **Then** the report visibly separates **Evaluation**, **Regression** (when present), and **Acceptance / Quality Gate** sections and surfaces flagged cases, anomaly reasons, and intermediate retrieval-vs-answer evidence details.
2. **Given** any valid artifact for `run`, `compare`, `trend`, `calibrate`, or `report`, **When** exporting with `--json` to `stdout` or a JSON output path alongside a Markdown output path, **Then** the JSON output conforms strictly to versioned schemas with zero untyped ad-hoc wrapper fields, zero stray text on `stdout`, and both files write cleanly without altering underlying immutable run artifacts.
3. **Given** programmatic callers importing the library's report rendering capabilities directly in Python, **When** formatting Markdown or report models from stored artifacts, **Then** report generation executes independently of CLI parsing, configuration files, and environment variable readers.

---

### User Story 5 - Adopt User-Facing CI/CD Workflows and Validate Full MVP Distribution Readiness (Priority: P2)

An external project team adopts `evalforge-maestro` in GitHub Actions using ready-to-use CI workflow templates for PR regression gating and Markdown summary reporting, while project maintainers validate the complete MVP packaging, CLI cold-start isolation, multi-OS smoke matrix, and `TestPyPI` -> `PyPI` tag release readiness.

**Why this priority**: Turning `evalforge-maestro` into an adoptable open-source tool and closing out the MVP requires verified packaging, minimal cold-start overhead, reproducible user CI templates, and validated release automation before public distribution.

**Independent Test**: Can be fully tested by installing built wheel and sdist artifacts into clean environments without dev/optional extras, asserting `evalforge-maestro --help` loads zero heavy optional dependencies, executing the user CI workflow pattern against a sample project fixture in offline `--mock --local-only` mode, and running automated validation checks over the release workflow and packaged templates.

**Acceptance Scenarios**:

1. **Given** a clean minimal installation (without optional judge, docpipe, or dev dependencies), **When** executing `evalforge-maestro --help` (and subcommand `--help`), **Then** help renders quickly and process module inspection confirms zero heavy optional packages (such as `litellm`, `docpipe_maestro`, `numpy`, `scipy`) were imported during startup.
2. **Given** the repository's user-facing GitHub Actions CI integration templates and example configuration, **When** an engineer copies the template workflow into a target repository and runs the offline `--mock --local-only` gate step, **Then** the workflow installs the package cleanly, runs `evalforge-maestro run` / `compare`, publishes Markdown/JSON artifacts, and fails the PR step accurately when exit code is non-zero.
3. **Given** the complete MVP distribution built from the repository, **When** maintainers execute automated packaging and release-gate validation checks, **Then** distribution metadata, dual CLI scripts (`evalforge-maestro` and `evalforge_maestro`), version alignment rules, lockfile verification, vulnerability audits, and `TestPyPI` -> `PyPI` workflow definitions pass end-to-end verification checks.

---

### Edge Cases

- **Missing Optional Extras at CLI Boundary**: What happens when a user runs `evalforge-maestro run` configured with a live non-mock LLM judge or `docpipe` target without installing those optional extras? The CLI must catch the missing-extra condition cleanly, emit an actionable install instruction (`evalforge-maestro[judges]` or `evalforge-maestro[docpipe-maestro]`) on `stderr`, avoid noisy stack traces by default, and return deterministic exit code `2` or `3` consistent with runtime vs configuration policy (specifically, missing runtime dependency blocks execution cleanly with a clear error message rather than an unhandled traceback; see exit code rules).
- **Unknown Run ID, Baseline Alias, or Corrupted Artifact**: What happens when `compare`, `report`, or `baseline` references a non-existent run ID, unknown baseline name, or unreadable/tampered JSON artifact in `.evalforge/`? The CLI must report a clear diagnostic on `stderr` (and structured error info if appropriate) without creating empty/corrupted files and exit with code `2`.
- **Empty Store on `trend` or `baseline list`**: What happens when `trend --window N` (`N >= 2`) or `baseline list` runs in a clean directory with zero or one stored runs? `baseline list` cleanly reports an empty baseline set (exit `0`), and `trend --window N` cleanly emits an `INSUFFICIENT_DATA` trend report (or fails only if policy requires minimum runs, returning `1` when `--strict` escalates `INCONCLUSIVE` or insufficient trend evidence).
- **Strict Stream Isolation on Warnings and Log JSON**: What happens when `--json` and `--log-json --log-level DEBUG` are combined during a run that emits deprecation/drift/truncation warnings? `stdout` must contain solely the valid JSON document, while all structured JSON log lines and warnings emit strictly to `stderr`.
- **Concurrent File Writes & Permission Errors**: What happens if output directories for `--output` / `--markdown` or `.evalforge/` do not yet exist or lack write permissions? Safe parent directory creation (preserving `0o700`/`0o600` rules inside `.evalforge/`) succeeds automatically, while unwriteable paths fail clearly on `stderr` with exit code `2` without corrupting existing files.
- **Interrupted stdin / `--version` / Invalid Subcommand Flags**: What happens when an unknown flag, invalid choice, or mutually conflicting option is passed? CLI argument parsing exits cleanly with code `2` and prints usage guidance on `stderr` without modifying `.evalforge/`.

## Requirements *(mandatory)*

### Functional Requirements

#### CLI Entrypoints & Subcommand Surface

- **FR-001**: System MUST expose dual CLI console entrypoints (`evalforge-maestro` and `evalforge_maestro`) executing a unified command-line interface with top-level `--version`, `--help`, global configuration path override (`--config`), stream logging options (`--log-level`, `--log-json`), and deterministic POSIX exit codes `0`–`4`.
- **FR-002**: System MUST provide the seven primary CLI subcommands matching project governance:
  - `run`: Execute dataset evaluation against configured target, at least one explicitly configured metric (failing with exit code `2` if zero metrics are specified), optional explicitly referenced baseline comparison (`--baseline` or configured baseline; omitted unless explicitly set) / sliding trend policy, and quality gate; persist immutable run + ledger updates; emit JSON and/or Markdown output.
  - `compare`: Perform pairwise regression comparison between a candidate run and a specified baseline run ID or named pinned baseline, apply acceptance gate policy, and emit JSON and/or Markdown diagnostics.
  - `trend`: Perform chronological sliding-window linear trend analysis (`--window N`, validating `N >= 2`), evaluate optional trend gate policy, and emit JSON and/or Markdown diagnostics.
  - `calibrate`: Run judge calibration diagnostics against human ground-truth samples (`--mock`, `--local-only`, optional `--min-agreement` threshold supported) producing exact agreement rate (%), directional bias metrics, mean score delta, disagreements, and recommended pass threshold in JSON and/or Markdown formats.
  - `baseline`: Manage pinned baseline aliases cleanly (`set` / pin, `list`, `show`, `delete` / remove) without mutating historical run files.
  - `report`: Render or export schema-validated JSON and human-readable Markdown diagnostic reports directly from stored run, comparison, trend, or calibration artifacts.
  - `config`: Inspect effective resolved settings (`config show --resolved`) with masked/redacted credentials and verify configuration validity (`config validate`).
- **FR-003**: System MUST support binding target systems in `evalforge-maestro run` via both live target adapters (`callable` and `rag` module references with optional field extractors, plus `docpipe` pipeline targets) and offline replay from pre-captured execution-trace files (`--executions`), failing with exit code `2` when target binding configuration is missing, ambiguous (e.g., conflicting live target and replay file), unresolvable, or (in replay mode) missing a matching execution trace for any active selected dataset case (while logging unused extra trace records as a `stderr` warning).
- **FR-004**: `evalforge-maestro run` MUST support resource and execution controls via CLI flags and configuration defaults: `--mock`, `--local-only`, `--strict`, `--fail-fast`, `--max-concurrency` (defaulting to `4`), `--max-dataset-cases`, `--max-context-chars`, and optional workstation resident-memory soft-cap.

#### Configuration Precedence, Purity & Cold-Start Isolation

- **FR-005**: CLI configuration MUST resolve settings strictly in deterministic precedence order: `CLI flags > Environment variables (EVALFORGE_*) > Project configuration file (evalforge.toml, discovered non-recursively in CWD unless --config is passed) > Built-in defaults`. Explicit validation failures (syntax errors, unknown keys, type mismatches, missing explicit `--config` paths, or invoking `run` with zero configured metrics) MUST fail immediately with exit code `2`.
- **FR-006**: CLI `.env` loading MUST occur strictly on explicit opt-in via `--env-file <path>` at the CLI entrypoint boundary without ever auto-loading implicit `.env` files in the working directory; variables loaded from `--env-file` MUST rank strictly below OS-exported environment variables and above `evalforge.toml`, require zero external third-party `.env` runtime libraries, and fail immediately with exit code `2` if the specified `--env-file` path is missing or malformed.
- **FR-007**: System MUST preserve strict library purity and unidirectional dependency boundaries: core, domain, and library reporting modules MUST NEVER import CLI modules, configuration/TOML parsers, or `.env` loaders, and MUST NEVER read `evalforge.toml` or `.env` files directly; configuration MUST cross into library code exclusively as validated typed objects.
- **FR-008**: Importing the core library or invoking `evalforge-maestro --help` (and subcommand `--help`) MUST maintain cold-start isolation, loading zero heavy optional integrations (model judge routing providers, external RAG runtime integrations, or scientific array libraries) and deferring heavy parser imports where unused during bare startup/help.

#### Stream Hygiene, Secret Redaction & Security Policy

- **FR-009**: CLI stream separation MUST guarantee that when `--json` is enabled, `stdout` contains solely the single valid schema-validated JSON payload with zero banners, warnings, progress bars, or extraneous text; when `--json` is disabled, primary human-readable command output (Markdown report/summary, `config show --resolved`, or `baseline` output) MUST write to `stdout` (unless superseded by silent file-only export when requested), while all diagnostics, warnings, progress telemetry, error details, and `--log-json` / `--log-level` logs MUST write strictly to `stderr`.
- **FR-010**: System MUST mask/redact all API keys, provider tokens, authorization headers, and secret configuration fields across `config show --resolved`, `--json` output, Markdown reports, persisted artifacts, and `stderr` logs so raw credentials never appear in any output surface.
- **FR-011**: System MUST provide opt-in outbound PII egress protection (`--block-pii` CLI flag / `[security].block_pii` configuration policy): when enabled for non-mock remote target or remote judge calls, payloads MUST be scanned pre-network for sensitive PII/credential patterns (email addresses, phone numbers, Social Security numbers, payment card sequences, and raw API tokens/credentials) and block execution before network transmission with exit code `4` (without writing raw matched PII values to diagnostics); when disabled, `--local-only` endpoint blocking and credential scrubbing/masking still remain enforced.
- **FR-012**: CLI commands MUST deterministically map outcomes to documented POSIX exit codes `0`–`4`:
  - `0`: `PASS`, `WARNING`/`INCONCLUSIVE` when `--strict` is disabled, successful read/management operations (`baseline`, `report`, `config`), or `calibrate` when no `--min-agreement` threshold is breached and `--strict` inconclusive conditions are not triggered.
  - `1`: `FAIL` (gate policy breach, mandatory case failure, excessive regression, or `calibrate` failing an explicitly configured `--min-agreement` floor), or `--strict` active when outcome is `WARNING` or `INCONCLUSIVE` (including inconclusive/zero-valid calibration under `--strict`).
  - `2`: Configuration error, invalid CLI arguments, invalid or missing dataset/artifact/baseline/`--env-file`, unknown metrics/adapters, or schema validation failure.
  - `3`: Target adapter or external judge runtime/network failure when `--fail-fast` is enabled or zero evaluation cases completed successfully.
  - `4`: Security or locality policy violation (remote endpoint blocked under `--local-only`, or PII/credential egress blocked under `--block-pii`).

#### Reporting Engine (JSON & Markdown)

- **FR-013**: System MUST provide a pure, CLI-independent reporting capability capable of rendering both schema-validated JSON outputs (carrying `schema_version`) and structured human-readable Markdown diagnostic reports for evaluation runs, pairwise comparisons, multi-run sliding trends, and judge calibration reports.
- **FR-014**: Markdown and JSON reports MUST preserve explicit three-way conceptual separation across **Evaluation** (metric results and case breakdowns), **Regression** (baseline deltas, trend slopes, and drift/case regressions when applicable), and **Acceptance / Quality Gate** (final gate verdict and rule-by-rule rationale).
- **FR-015**: Diagnostic reports MUST expose and highlight mandatory case failures, aggregate-masking anomalies, inter-metric disagreements (`> 0.3` sub-metric divergence), retrieval-vs-answer decoupling failures (e.g., accurate answer with failed retrieval, or relevant retrieval with hallucinated/inaccurate answer), and cross-version drift warnings (dataset fingerprint, metric version, or judge configuration mismatches), while omitting/masking all secrets.
- **FR-016**: Reports MUST support exporting both to streams (`stdout` for `--json` or default human Markdown/summary output) and to user-specified files on disk (including `--markdown-out` / `--json-out` / `--output`) cleanly without mutating immutable stored run records.

#### CI/CD Integration Templates & Release Readiness

- **FR-017**: Repository MUST provide user-facing CI/CD integration templates and example configuration demonstrating offline `--mock --local-only` PR smoke gating, baseline regression comparison, Markdown job summary / report artifact upload, and POSIX exit-code enforcement.
- **FR-018**: Complete MVP packaging and CI/release pipelines MUST validate clean minimal installs, package distributions, dual CLI commands (`evalforge-maestro` & `evalforge_maestro`), `--help` cold-start isolation, multi-OS smoke verification, lockfile and vulnerability checks, mandatory determinism and immutability verification gates, and tag-triggered staging-to-production registry release workflow correctness.

### Key Entities *(include if feature involves data)*

- **CLIResolvedConfig**: Represents the unified effective configuration resolved strictly across CLI arguments, `EVALFORGE_*` environment variables, non-recursive CWD `evalforge.toml`, and defaults, paired with per-setting resolution provenance (`cli`, `env`, `file`, `default`) and credential-safe redacted rendering.
- **ReportDocument / CLIOutputEnvelope**: Represents the schema-versioned (`schema_version`) machine-readable JSON interchange payload emitted by CLI subcommands (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`) separating evaluation, regression, and gate sections cleanly with zero untyped dicts.
- **MarkdownReport**: Represents a deterministic, human-readable formatted diagnostic document summarizing gate decisions, metric performance, regression/trend tables, calibration diagnostics, flagged anomalies, and redacted evidence excerpts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete an end-to-end offline evaluation (`run --mock --local-only`), pin a baseline (`baseline`), compare a candidate run (`compare`), analyze multi-run trends (`trend`), calibrate judges (`calibrate`), inspect masked configuration (`config show --resolved`), and export Markdown + JSON reports (`report`) solely via `evalforge-maestro` CLI commands without writing custom Python scripts.
- **SC-002**: Repeated identical CLI invocations under `--mock --local-only` produce 100% identical metric scores, gate verdicts (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`), and POSIX exit codes (`0`–`4`) across runs, and all error/policy scenarios map to exact exit codes `0`–`4` in 100% of verified test cases.
- **SC-003**: Across all `--json` invocations (including warnings and verbose `--log-json` diagnostics), 100% of `stdout` output parses as a single schema-validated JSON payload matching documented contracts with zero leaked raw secrets anywhere in `stdout`, `stderr`, Markdown files, or persisted artifacts.
- **SC-004**: Cold-start execution of `evalforge-maestro --help` in a clean minimal environment loads zero heavy optional integrations (model judge routing, document pipeline adapters, or scientific computing packages) and maintains complete library purity (zero CLI or configuration-file dependencies inside core, domain, or reporting library modules).
- **SC-005**: Clean distribution builds pass strict metadata validation, clean minimal-environment installs expose working `evalforge-maestro` / `evalforge_maestro` commands, user CI integration templates execute cleanly in offline mode, and the full verification suite maintains at least 85% overall branch coverage (with 100% preserved on deterministic metrics and quality gate decision logic) alongside clean static type and security checks.

## Assumptions

- Persisted run storage layout (immutable run records, append-only ledger, named baselines, and incremental temporary journals) and atomic restrictive directory/file permissions from Milestones 1–4 remain unchanged and backward-compatible with earlier records.
- Core package footprint remains minimal across all supported runtime versions; any configuration parsing compatibility required on older supported runtimes respects automated supply-chain vulnerability auditing without introducing heavy third-party frameworks.
- Actual external `TestPyPI` and `PyPI` tag publication requires repository owner trusted-publisher configuration and pushing a release version tag after Milestone 5 merges to `main`; pre-merge CI verifies the complete build, metadata, version-tag alignment logic, clean-environment install, and release workflow definition deterministically.
- Markdown diagnostic reports and CLI JSON outputs remain offline, static artifacts; web UI dashboards and HTTP API servers remain explicitly out of MVP scope per governance.
