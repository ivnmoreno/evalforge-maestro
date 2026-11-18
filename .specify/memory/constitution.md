<!--
Sync Impact Report
- Version change: unratified template -> 1.0.0
- Modified principles:
  - PRINCIPLE_1_NAME -> I. One-Sentence Scope Tiebreaker
  - PRINCIPLE_2_NAME -> II. Library Purity & Unidirectional Dependencies
  - PRINCIPLE_3_NAME -> III. Single Schema Source of Truth
  - PRINCIPLE_4_NAME -> IV. Evidence-Aware & Anomaly-Safe Evaluation
  - PRINCIPLE_5_NAME -> V. Immutable Artifacts & Determinism
- Added sections:
  - VI. Stream & Secret Hygiene
  - VII. Automated Quality Gates
  - Technical Constraints & Operational Guardrails
  - Development Workflow & Compliance Verification
- Removed sections:
  - None (all template placeholder slots replaced with ratified project governance)
- Follow-up TODOs:
  - None (remove this Sync Impact Report comment before committing the ratified constitution)
-->

# EvalForge Maestro Constitution

## Core Principles

### I. One-Sentence Scope Tiebreaker

> **"EvalForge Maestro is an independent evaluation and regression verification engine — never an LLM runtime, RAG indexer, or agent framework."**

Every design decision, feature proposal, and module boundary MUST honor this tiebreaker:

- **Independent Verification Role:** `evalforge_maestro` ingests versioned evaluation datasets, invokes or inspects target AI systems solely through standardized external adapters (`CallableAdapter`, protocol-based `RAGAdapter`, lazy `DocpipeAdapter`), evaluates intermediate evidence alongside final outputs, calibrates model-based judges against human ground truth, detects regressions against historical baselines, and enforces release quality gates.
- **Explicit Three-Way Concern Separation:** The data model, execution lifecycle, and reporting MUST keep **Evaluation** (metric performance on a dataset), **Regression** (degradation versus an immutable baseline or sliding run window), and **Acceptance / Quality Gate** (satisfaction of mandatory release policy criteria) strictly distinct.
- **Strict Non-Goals & Exclusions:** `evalforge_maestro` MUST NEVER parse raw documents, chunk text, generate document index embeddings, manage vector databases, execute production retrieval, host an LLM inference runtime, or impose framework lock-in (`langchain`, `llama-index`, `langgraph`, or vendor-locked SDKs) in core orchestration or metrics. Web UI dashboards and HTTP servers are excluded from MVP scope in favor of CLI, schema-validated JSON, and Markdown artifacts.

### II. Library Purity & Unidirectional Dependencies

Architecture MUST maintain strict unidirectional layering across the nine logical subsystems (`types.py`, `datasets`, `adapters`, `execution`, `metrics`, `judges`, `regression`, `storage`, and `reporting`/`cli`):

- **Library Purity (No CLI or Config Side Effects):** Core and domain library modules (`types`, `datasets`, `execution`, `storage`, `metrics`, `judges`, `regression`, and library `reporting`) MUST NEVER import `cli`, `tomllib`, or `dotenv`, and MUST NEVER read `evalforge.toml`, `.env`, or external configuration files. All configuration MUST enter library entrypoints as explicit typed objects; `evalforge.toml` is loaded strictly at the CLI boundary.
- **Unidirectional Dependency Boundary:** `core` (`types`, `datasets`, `execution`, `storage`), `metrics`, `judges`, and `regression` MUST NEVER import `cli`, config loaders, or concrete target adapters (`adapters` implementations such as `CallableAdapter`, `RAGAdapter`, or `DocpipeAdapter`). Specifically, `types`, `datasets`, `metrics`, `judges`, and `regression` MUST have zero imports from `adapters`, and `execution` MUST interact with targets exclusively via abstract protocol contracts rather than concrete adapter modules.
- **Automated AST & Cold-Start Enforcement:** `tests/test_library_purity.py` MUST enforce these import boundaries via AST inspection in CI. Subprocess cold-start tests MUST assert that `import evalforge_maestro` and `evalforge-maestro --help` do not import heavy optional dependencies (`litellm`, `docpipe_maestro`, `numpy`, `scipy`) into `sys.modules`.
- **Public API & Signature Stability:** `tests/test_api_stability.py` MUST pin `__all__`, the `EvalforgeError` exception hierarchy, and `inspect.signature(...)` parameters on public entrypoints so unintentional breaking changes fail CI immediately.

### III. Single Schema Source of Truth

All domain, persistence, and interchange contracts MUST be centralized and strictly typed:

- **Canonical Schema Location:** Every contract (`EvaluationCase`, `ExecutionResult`, `MetricResult`, `RunRecord`, `CalibrationReport`, plus regression/gate payloads) MUST reside in `src/evalforge_maestro/types.py` as Pydantic v2 models carrying an explicit `schema_version` field on persisted and interchange contracts.
- **Zero Ad-Hoc Dict Shapes:** Untyped `dict` shapes MUST NOT cross subsystem boundaries, CLI `--json` outputs, judge responses, or `.evalforge/` storage files. Validation errors on schemas or duplicate `EvaluationCase.id` values MUST fail explicitly rather than coercing or overwriting silently.
- **Bounded Metric Semantics:** `MetricResult.score` MUST be typed as `float | None` within `[0.0, 1.0]` (never `NaN` or `Inf`), paired with `metric_version` (coupled to formula logic), explicit `status` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, `NOT_APPLICABLE`), human-readable `explanation`, supporting evidence references, `anomaly_flags`, and the active metric config snapshot.
- **Formal Metric Contracts:** Every metric implementation MUST declare what it measures, required inputs from `EvaluationCase` and `ExecutionResult`, its calculation method, and its known limitations.

### IV. Evidence-Aware & Anomaly-Safe Evaluation

Evaluation MUST verify intermediate evidence independently of surface answers and prevent aggregate score masking:

- **Decoupled Evidence Inspection:** Retrieval quality, answer quality/groundedness, and agent process execution MUST be evaluated independently from captured `ExecutionResult` artifacts:
  - A factually accurate answer backed by irrelevant retrieved chunks MUST pass answer correctness while failing retrieval relevance and/or groundedness.
  - Relevant retrieved context paired with an inaccurate or ungrounded answer MUST pass retrieval metrics while failing answer correctness/groundedness.
  - Agent tool selection, argument validity, execution order, policy adherence, and token/latency cost MUST be scored independently of final answer text.
- **Zero-Divisor & Missing-Reference Safety:** Deterministic IR metrics (`Precision@K`, `Recall@K`, `MRR`, `NDCG@K`, `Hit Rate@K`) and reference-dependent checks MUST return `score = None` with `status = NOT_APPLICABLE` when ground-truth evidence is empty (`|G| == 0`), never dividing by zero or emitting `NaN`.
- **Anti-Masking & Anomaly Flags:** Aggregate scores MUST NEVER conceal a failure on any test case marked mandatory (`criteria.mandatory = True`), a severe single-metric or per-case regression, cross-version drift (`dataset_fingerprint`, `metric_version`, or `judge_config_fingerprint` mismatches), or high inter-metric disagreement (such as sub-metric divergence `> 0.3`). Any such condition MUST surface explicit `anomaly_flags` and trigger at minimum `WARNING` (or `FAIL` for mandatory policy/case breaches).
- **Judge Injection Isolation & Calibration:** Model-based judges MUST wrap untrusted target outputs and retrieved contexts inside randomized XML/nonce delimiters, validate structured JSON responses strictly via Pydantic schemas (recording unparseable outputs as `INCONCLUSIVE`, never defaulting to `0.0` or `1.0`), and support calibration (`calibrate`) against human labels reporting agreement rate, directional bias (`too_generous` vs. `too_harsh`), mean score delta, and recommended pass threshold.
- **Per-Case Fault Isolation:** Single-case or single-metric exceptions or timeouts MUST be captured inside that case's `ExecutionResult` or `MetricResult` (marked error/`INCONCLUSIVE`) without aborting the batch unless `--fail-fast` is enabled.

### V. Immutable Artifacts & Determinism

Historical evidence and offline gate behavior MUST remain tamper-evident, reproducible, and numerically stable:

- **Immutable Canonical Run Storage:** Persisted `RunRecord` artifacts in `.evalforge/runs/<run_id>.json`, run ledger entries in `.evalforge/manifest.jsonl`, pinned baselines in `.evalforge/baselines.json`, and canonical SHA-256 dataset fingerprints MUST NEVER be mutated in place. Re-runs or dataset modifications MUST generate a new `run_id` and fingerprint.
- **Atomic Persistence & Permissions:** In-progress runs MUST checkpoint incrementally to `.evalforge/tmp/<run_id>.jsonl`, and final `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` writes MUST commit atomically via temporary file rename (`os.replace`) under `0o700` directory and `0o600` file permissions.
- **Canonical Hashing & Numerical Stability:** SHA-256 fingerprints MUST hash canonical JSON (sorted keys, UTF-8 encoding, `\n` LF line endings). Scores and regression deltas MUST round to 6 decimal places with explicit `1e-9` epsilon tolerance to avoid IEEE 754 drift. Built-in deterministic metric formulas MUST be protected by normalized AST/source-hash contract tests so formula edits without bumping `metric_version` fail CI.
- **Deterministic Offline `--mock` & `--local-only` Execution:** `--mock` mode MUST run deterministically without API keys or network calls, yielding identical scores, gate determinations, and exit codes across identical runs. `--local-only` MUST block outbound remote endpoints pre-network and enforce air-gap safety (including `LITELLM_LOCAL_MODEL_COST_MAP=true`).
- **Deterministic POSIX Exit Codes (`0`–`4`):**
  - `0`: `PASS` (or `WARNING` / `INCONCLUSIVE` when `--strict` is disabled).
  - `1`: `FAIL` (quality gate threshold violated, mandatory case failed, or `--strict` active on `WARNING`/`INCONCLUSIVE`).
  - `2`: Configuration, CLI argument, or dataset/schema validation error.
  - `3`: Target adapter or external judge runtime/network failure (when `--fail-fast` is active or zero cases completed).
  - `4`: Security or locality policy violation (e.g., remote endpoint blocked under `--local-only` or PII egress block).

### VI. Stream & Secret Hygiene

CLI streams, library logging, configuration resolution, and credentials MUST adhere to strict UNIX and security boundaries:

- **Strict `stdout` / `stderr` Separation:** When `--json` is enabled, `stdout` MUST emit strictly schema-validated machine-readable JSON with zero banners, warnings, or stray prints. Human diagnostics, progress telemetry, and `--log-json` / `--log-level` logs MUST emit strictly to `stderr`.
- **NullHandler-Only Library Logging:** Library modules under `src/evalforge_maestro/` MUST attach only `logging.NullHandler()` and MUST NEVER configure the root logger, add stream handlers, or write directly to `stdout`.
- **Zero Leaked Credentials:** Provider API keys, tokens, and secrets MUST NEVER appear in `RunRecord`, `manifest.jsonl`, `--json` output, Markdown reports, `stderr` logs, or `evalforge-maestro config show --resolved` (all secrets MUST be masked/redacted).
- **Deterministic Configuration Precedence:** CLI settings MUST resolve strictly in order: `CLI flags` > `Environment variables (EVALFORGE_*)` > `Project config file (evalforge.toml, non-recursive CWD)` > `Built-in defaults`.
- **Hermetic Test Isolation:** A global `autouse` test fixture MUST clear all `EVALFORGE_*` and provider API key environment variables and block outbound network sockets unless explicitly enabled, guaranteeing zero `.env` leakage and zero accidental external calls during tests.

### VII. Automated Quality Gates

Code quality, static security, coverage, and release invariants MUST be mechanically verified on every change:

- **Static Analysis & Security Linting:** Every commit and PR MUST pass `ruff format --check .`, `ruff check .` (rules `E, W, F, I, UP, B, SIM, RUF`), `ruff check --select S src/` (Bandit security checks), and `mypy --strict src tests`.
- **Strict Test Execution & Branch Coverage:** `pytest` MUST execute with `--strict-markers` and `filterwarnings = ["error"]` (allowing only narrowly scoped ignore rules for third-party library deprecations). `--cov` MUST enforce a minimum **85% branch coverage** floor across `src/evalforge_maestro/`, with **100% coverage** required on deterministic metric formulas and quality gate decision logic.
- **Named Mandatory Release Gates:** CI and release pipelines MUST run and pass:
  - `@pytest.mark.gate_determinism`: Verifies identical inputs, policies, and `--mock` judge runs produce identical scores, gate statuses, and POSIX exit codes across runs.
  - `@pytest.mark.gate_immutability`: Verifies persisted `RunRecord` artifacts and canonical dataset fingerprints cannot be silently overwritten or corrupted.
- **Supply-Chain & Cross-OS Verification:** CI MUST enforce `uv lock --check`, cross-OS smoke matrices (`ubuntu-latest`, `macos-latest`, `windows-latest` with `.gitattributes` enforcing LF text files), isolated `--no-dev` minimal-core install checks (verifying zero dev-dependency leakage and clear `MissingExtraError` hints), `uv build` + `twine check --strict dist/*` clean-venv installs, `pip-audit` vulnerability scanning, and `cz check` Conventional Commits validation.

## Technical Constraints & Operational Guardrails

- **Packaging & Minimal Footprint:** Target runtime is `Python 3.10+` packaged as `evalforge-maestro` (`src/evalforge_maestro/` with `py.typed` and `hatch-vcs` Git-tag versioning), exposing `evalforge_maestro` and `evalforge-maestro`. Core installation MUST depend minimally on `pydantic` v2; optional capabilities (`[judges]`, `[docpipe]`, `[embeddings]`, `[dev]`) MUST remain behind lazy imports raising clear `MissingExtraError` instructions when uninstalled.
- **Workstation Memory & Streaming Protection:** `DatasetEngine` MUST stream `EvaluationCase` records via iterators/generators and flush `ExecutionResult` / `MetricResult` entries incrementally to `.evalforge/tmp/<run_id>.jsonl` rather than buffering full multi-thousand-case traces in RAM. Execution MUST support `--max-concurrency` (defaulting to `4`), `--max-dataset-cases`, `--max-context-chars` truncation (recorded in `ExecutionResult.truncated`), and optional resident memory soft-caps (`resource.getrusage`) so runaway adapters fail cleanly without hanging workstations.
- **Bounded Context-Grouped Judge Execution:** LLM-as-a-judge calls MUST execute under bounded async concurrency grouped by shared retrieval context to control latency, cost, and provider rate limits.
- **Phased Scope Discipline:** MVP milestones (M1–M5) cover dataset management, deterministic IR/text/schema metrics, `CallableAdapter`/`RAGAdapter`/`DocpipeAdapter`, baseline/trend regression & anomaly gating, LiteLLM judge & calibration, and CLI (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`). Post-MVP extensions (multi-step agent recovery traces, embedding similarity metrics, OpenTelemetry ingestion, rebuildable SQLite index / HTTP server) MUST NOT enter MVP scope without explicit spec authorization.

## Development Workflow & Compliance Verification

- **Spec-Kit Constitution Check:** Every feature specification, implementation plan, and task breakdown MUST pass a Constitution Check against Principles I–VII before Phase 0 research and again after Phase 1 design. Any temporary or structural deviation MUST be documented and justified in the plan's Complexity Tracking table before implementation begins.
- **Contract & Version Guardrails:** Modifying any built-in deterministic metric calculation MUST be accompanied by a `metric_version` bump (enforced by AST/source-hash tests). Public `__all__`, exception class, or signature modifications MUST deliberately update `tests/test_api_stability.py` in accordance with semantic versioning.
- **Tag-Driven Release Gate:** On `v*` tag pushes (`.github/workflows/release.yml`), CI MUST re-run all static, coverage, purity, determinism, and immutability gates, confirm the built wheel version matches the Git tag, publish via OIDC Trusted Publishing to `TestPyPI` and verify a clean-environment install before publishing to `PyPI` and creating the GitHub Release.

## Governance

This constitution supersedes all conflicting ad-hoc engineering practices, backlog shortcuts, or unverified assumptions in `evalforge-maestro`, operating alongside `docs/intent.md` as the project's binding governance baseline.

- **Amendment Procedure:** Any change to this constitution MUST be submitted as an explicit pull request amending `.specify/memory/constitution.md`, including an updated Sync Impact Report detailing modified principles, version bump rationale, downstream spec/template alignment checks, and a migration plan for any affected contracts or gates.
- **Semantic Versioning Policy:** Constitution versions follow `MAJOR.MINOR.PATCH`:
  - `MAJOR`: Backward-incompatible removal, relaxation, or redefinition of a core principle or non-negotiable gate.
  - `MINOR`: Addition of a new principle or governance section, or material expansion of enforceable constraints.
  - `PATCH`: Clarifications, wording improvements, typo corrections, or non-semantic refinements.
- **Compliance Verification:** Every pull request, architectural plan, and release artifact MUST verify conformance with Principles I–VII through automated CI checks (`ruff`, `mypy --strict`, `pytest`, AST purity tests, API signature pinning, and release gate markers) and human code review.

**Version**: 1.0.0 | **Ratified**: 2026-11-18 | **Last Amended**: 2026-11-18
