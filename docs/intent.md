# `intent.md` — EvalForge Maestro: LLM Evaluation & Regression Engine

**Document Status:** Final Baseline Intent & Quality Specification (v1.4)  
**Target Workflow:** GitHub Spec-Kit (`/speckit.constitution` -> `/speckit.specify`)  
**Project Status:** New Project (Greenfield)

---

## 1. Project Identity and Classification

* **Project Name:** EvalForge Maestro
* **Repository Root Directory:** `evalforge-maestro/`
* **PyPI Distribution Name:** `evalforge-maestro` (normalizes identically with `pip install evalforge_maestro` under PEP 503)
* **Python Import Namespace:** `evalforge_maestro` (`src/evalforge_maestro/`)
* **CLI Entrypoints:** `evalforge_maestro` and `evalforge-maestro`
* **CLI Configuration File:** `evalforge.toml` (loaded strictly at CLI entrypoint; never read by library modules)
* **Local Artifact Directory:** `.evalforge/`
* **Tagline:** Evaluate. Compare. Verify.
* **Primary Identity:** Standalone Evaluation and Regression Engine
* **Distribution Interfaces:** Python Library / SDK (`import evalforge_maestro`) and Command-Line Interface (`evalforge-maestro` / `evalforge_maestro`)
* **Integration Surfaces:** Programmatic Python API, RAG/Application Adapter Layer (including first-class `docpipe-maestro` integration), and CI/CD Automated Quality Gates
* **Primary Domain:** LLM System Evaluation, Evidence Verification, and Automated Quality Assurance
* **Operating Model:** Offline/local-first batch evaluation and automated CI/CD regression testing
* **Design Philosophy:** Modular, provider-independent, evidence-aware, and reproducible

### Identity & Scope Tiebreaker
> **"EvalForge Maestro is an independent evaluation and regression verification engine — never an LLM runtime, RAG indexer, or agent framework."**

Its primary responsibility is to ingest versioned evaluation datasets, execute or inspect target AI systems through standardized adapters, evaluate intermediate execution evidence alongside final outputs, calibrate model-based judges against human ground truth, detect regressions against immutable historical baselines, and enforce deterministic release quality gates.

---

## 2. Executive Purpose & Core Promise

### Central Question Addressed
> *"How do we know that an AI system is actually working correctly, and how can we prove that a change has not made it worse?"*

### Core Promise
Turn AI quality from a subjective impression into measurable, reproducible engineering evidence.

### Fundamental Conceptual Distinctions
`evalforge_maestro` explicitly separates three distinct engineering concerns throughout its data model, execution lifecycle, and reporting:
1. **Evaluation:** How well did the system perform on a defined dataset and metric suite?
2. **Regression:** Did the system degrade meaningfully along any critical dimension, test case, or historical run window compared with an established baseline?
3. **Acceptance (Quality Gate):** Does the system satisfy the mandatory policy conditions required for release or merge approval?

---

## 3. Problem Statement

Traditional deterministic software testing assumes that a fixed input yields an identical, predictable output. LLM-powered applications, retrieval-augmented generation (RAG) pipelines, and autonomous agents violate this assumption in ways that standard test runners cannot catch:

* **Non-determinism & Paraphrasing:** Identical prompts can yield different responses across runs, and semantically valid answers may vary substantially in surface wording.
* **Silent Retrieval Failures:** A RAG pipeline may retrieve plausible but irrelevant context, or produce a factually correct answer solely from pretrained model weights despite broken retrieval.
* **Hallucination & Ungrounded Claims:** Generated responses can read fluently while introducing unsupported claims or inaccurate citations.
* **Process vs. Outcome Divergence in Agents:** An agent may arrive at a correct final answer after invoking unsafe tools, passing malformed arguments, violating policies, or consuming excessive tokens and latency.
* **Non-Uniform Regressions & Masked Anomalies:** Updating a prompt, chunking strategy, or foundation model can improve aggregate performance while severely degrading specific critical categories or isolated metrics.
* **Uncalibrated LLM Judges:** Relying blindly on LLM-as-a-judge evaluations without measuring agreement or systematic bias (`too_generous` vs. `too_harsh`) against human ground-truth labels introduces unverified noise into CI gates.
* **Provider & Environment Drift:** Upstream model behavior can shift without any change to application source code, and evaluation runs often lack the cryptographic metadata required for reproduction.

---

## 4. Requirements Discovery (5W3H)

### WHO — Stakeholders and Users
* **Primary Users:** AI/ML Engineers, Backend Software Engineers, and RAG/Agent System Developers who need programmatic and CLI tools to verify system quality before deployment.
* **Secondary Users:**
  * **QA Automation Engineers & DevOps/Platform Engineers:** Integrating AI quality gates, PR diff summaries, and exit-code policies into CI/CD pipelines.
  * **Technical Leads:** Reviewing release readiness and version-over-version regression reports.
  * **AI Governance, Risk & Compliance (GRC) Auditors / Legal Reviewers:** Inspecting immutable `RunRecord` fingerprints, groundedness/citation evidence, and judge calibration reports to verify auditability and regulatory compliance (such as EU AI Act transparency and accuracy documentation).
  * **Domain Subject-Matter Experts (SMEs) / Dataset Curators:** Non-developer reviewers who author golden evaluation cases, review flagged metric disagreements (`> 0.3` delta), and supply human ground-truth labels for `evalforge_maestro calibrate`.
* **External Systems (Actors):** Target Python callables, external RAG pipelines (specifically `docpipe-maestro`), LLM API providers (via LiteLLM routing for model-based judges), and CI/CD runners (e.g., GitHub Actions).

### WHAT — Purpose and Capabilities
`evalforge_maestro` provides an end-to-end framework for defining evaluation datasets, capturing rich execution traces and intermediate evidence, running deterministic/statistical/model-based metrics, calibrating LLM judges against human labels, tracking immutable experimental runs, comparing versions and multi-run trends for regressions, and generating both human-readable and machine-readable diagnostics.

### WHEN — Usage and Lifecycle
* **Local Development (Iterative):** Run via Python SDK (`import evalforge_maestro`) or CLI (`evalforge-maestro run`) during prompt engineering, retrieval tuning, or adapter refactoring to get immediate feedback against golden datasets.
* **CI Smoke Testing (`--mock` Mode):** Executed in CI pipelines without external API keys using deterministic mock judge responses to validate pipeline wiring, schema contracts, and exit-code gate logic.
* **Pre-Merge / CI Pipeline (Event-Driven):** Triggered automatically on pull requests or release branches to verify that candidate changes do not violate baseline regression policies.
* **Post-Release / Periodic Monitoring (Scheduled):** Executed periodically against fixed baselines and sliding run windows to detect upstream model provider drift.

### WHERE — Operating Context
* **Execution Environment:** Runs as a single installable local Python package (`Python 3.10+`) within developer workstations, Linux environments, and containerized CI/CD runners.
* **Architectural Boundary:** Operates strictly outside the target AI application's core runtime logic, communicating via explicit adapter contracts without requiring target systems to adopt specific frameworks (no forced dependency on LangChain, LlamaIndex, or LangGraph).

### WHY — Engineering and Portfolio Value
* **Operational Value:** Prevents silent quality degradations, ungrounded hallucinations, and broken retrieval pipelines from reaching production.
* **Architectural Value:** Demonstrates strict separation of concerns alongside `docpipe-maestro`—proving the ability to engineer both an AI runtime system and the independent verification infrastructure required to trust it.

### HOW — User-Observable Behavior
1. **Define:** The user supplies a versioned JSONL/JSON dataset (or imports an existing `docpipe-maestro` evaluation fixture) containing inputs, reference outcomes, expected retrieval context, expected tool calls, metadata, and evaluation criteria.
2. **Adapt:** The user wraps their target Python function or RAG pipeline in an `evalforge_maestro` adapter (`CallableAdapter`, protocol-based `RAGAdapter`, or `DocpipeAdapter`) that translates execution outputs and intermediate artifacts into a standard `ExecutionResult` contract.
3. **Execute:** The user runs the evaluation via CLI or SDK (with optional `--mock` mode for deterministic offline testing and `--local-only` pre-network enforcement). The Evaluation Orchestrator streams dataset cases, enforces resource/concurrency caps, captures evidence (retrieved chunks, citations, latency, tokens, truncation flags, errors), checkpoints progress incrementally, and invokes configured metrics.
4. **Calibrate:** When using LLM judges, the user runs `evalforge-maestro calibrate` against human-labeled subsets to quantify agreement rate, directional bias (`too_generous` vs. `too_harsh`), score delta, and recommended pass thresholds.
5. **Compare, Trend & Gate:** The Regression Engine compares the new run record against a designated baseline run (or analyzes linear slope across a sliding window of $N$ historical runs), surfaces metric disagreement/anomaly flags, evaluates configurable acceptance policies, emits `PASS`, `FAIL`, `WARNING`, or `INCONCLUSIVE` determinations, writes JSON/Markdown artifacts, and exits with a deterministic POSIX status code (`0`–`4`).

### HOW MUCH — Scale, Memory & Workstation Protection
* **Package Footprint:** Single installable Python package (`evalforge-maestro`) with minimal core dependencies (`pydantic` v2); heavy or optional capabilities (`[judges]`, `[docpipe]`, `[embeddings]`, `[dev]`) are isolated behind lazy imports and optional extras.
* **Workstation Memory Protection:**
  * **Streaming Execution Pipeline:** Stream `EvaluationCase` records lazily from JSONL via iterators/generators and flush case-level `ExecutionResult` and `MetricResult` entries incrementally to an append-only temporary journal (`.evalforge/tmp/<run_id>.jsonl`) rather than holding thousands of full traces and retrieved context chunks in RAM simultaneously.
  * **Configurable Resource & Memory Guardrails:** Support explicit limits in `evalforge.toml` and CLI flags (`--max-concurrency` defaulting to `4`, `--max-dataset-cases`, `--max-context-chars` trace truncation, and an optional resident memory soft-cap / `resource.getrusage` warning or clean abort threshold) so oversized payloads or runaway adapters fail gracefully instead of hanging a developer workstation.
* **Cost & Latency Control:** Deterministic metrics form the foundational layer; model-based judges support bounded async concurrency grouped by shared context and explicit `--mock` execution for zero-cost CI smoke tests.

### HOW LONG — Retention and Reproducibility Horizon
* **Artifact Immutability:** Historical run records (`.evalforge/runs/<run_id>.json`), dataset fingerprints, and configuration snapshots remain immutable across the lifecycle of a project so that past baselines are never silently altered by subsequent code or dataset edits.

---

## 5. Scope and Phased Delivery Boundaries

### 5.1 Eight Target Functional Domains (Full Vision)
1. **Dataset Management:** Golden datasets, JSON/JSONL import/export, `docpipe-maestro` fixture import, schema validation, versioning, canonical SHA-256 content fingerprinting, split leakage checks, tagging, and provenance.
2. **Retrieval Evaluation:** Deterministic IR metrics (`Precision@K`, `Recall@K`, `MRR`, `NDCG@K`, `Hit Rate@K`), context relevance, context coverage, and duplicate/redundant retrieval analysis.
3. **Answer Quality Evaluation:** Exact/normalized match, JSON Schema / structured output validation, citation existence/verification, semantic similarity, factual consistency, relevance, completeness, groundedness, and unsupported claim detection.
4. **Agent Evaluation:** Task completion, tool selection accuracy, argument correctness, execution sequence, excessive tool usage, policy compliance, failure recovery, and cost/duration tracking.
5. **Regression Detection:** Pairwise baseline comparison, multi-run sliding window trend slope analysis, aggregate and per-case regression detection, metric disagreement/anomaly flagging, cross-version drift warnings, configurable thresholds, and release acceptance decisions.
6. **Experiment Management:** Unique run IDs, model/provider metadata, prompt/config fingerprints, dataset version tracking, timestamps, and cross-run comparison.
7. **CI/CD Integration:** CLI execution (`evalforge-maestro` / `evalforge_maestro`), deterministic `--mock` mode, machine-readable JSON on `stdout`, structured telemetry on `stderr`, deterministic POSIX exit codes (`0`–`4`), configurable quality gates, and GitHub Actions workflow integration.
8. **Reporting and Diagnostics:** Overall summaries, metric breakdowns, failed-case diagnostics, anomaly/disagreement flags, regression explanations, per-example evidence inspection, and JSON/Markdown artifact export.

### 5.2 Minimum Viable Product (MVP) In-Scope (Milestones M1–M5)
* **M1 — Evaluation Foundation:** Core data contracts (`types.py` with `schema_version`), streaming `DatasetEngine` with canonical SHA-256 fingerprinting, `CallableAdapter`, deterministic text/schema metrics (`exact_match`, `normalized_match`, `json_schema_validation`), bounded `EvaluationOrchestrator` with incremental `.evalforge/tmp/` checkpointing and workstation memory guardrails, and immutable canonical JSON storage (`.evalforge/runs/<run_id>.json` + `.evalforge/manifest.jsonl`).
* **M2 — Retrieval & RAG Evaluation:** Protocol-based `RAGAdapter` (supporting configurable dict/object field extractors), optional lazy-imported `DocpipeAdapter` (wrapping `docpipe_maestro.retrieve()` and `docpipe_maestro.answer_detailed()`), dependency-free `docpipe` fixture import, deterministic IR metrics (`precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`), and core GitHub Actions CI + OIDC release pipeline baselines (`.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pip-audit`, `cz check`, and PyPI metadata).
* **M3 — Experiment & Regression Engine:** Baseline pinning (`.evalforge/baselines.json`), pairwise run comparison (aggregate and per-case), sliding window trend slope analysis (`trend --window N`), automatic anomaly/disagreement flagging (when sub-metrics diverge by `> 0.3` or a high aggregate score masks a critical metric drop), cross-version drift warnings (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`), deterministic `QualityGate` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`) with `100%` branch coverage on gate decision logic, and mandatory gate tests covering cross-version drift and anomaly flagging.
* **M4 — Model-Based Judge & Calibration Engine:** Configurable, provider-agnostic LLM judge interface (via LiteLLM with `--local-only` pre-network enforcement and `LITELLM_LOCAL_MODEL_COST_MAP=true` air-gap safety verified in tests), prompt-injection boundary framing for untrusted target outputs, structured JSON judge response validation, context-grouped bounded async execution, deterministic `--mock` judge mode tested under `@pytest.mark.gate_determinism`, and `calibrate` diagnostics against human ground-truth labels.
* **M5 — CLI, Reporting & CI Integration:** Full CLI workflow (`run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, `config`) via `[project.scripts]` entrypoints (`evalforge-maestro`) exporting schema-validated JSON and human-readable Markdown reports with deterministic POSIX exit codes (`0`–`4`), CLI `--help` cold-start `sys.modules` verification, user-facing GitHub Actions CI integration templates, and full `TestPyPI` → `PyPI` release validation of the complete MVP.

### 5.3 Deferred to Post-MVP (Milestone M6 & Future — Tracked in `docs/future-features.md`)
* **Agent Trace Evaluation (M6):** Multi-step tool execution sequence verification, recovery analysis, and framework-specific agent adapters.
* **Statistical & Embedding Similarity Metrics:** Local/remote embedding cosine similarity and multi-run statistical distribution comparisons.
* **OpenTelemetry Ingestion:** Importing distributed execution traces from external observability pipelines.
* **Optional SQLite Index & Remote Evaluation Service:** Rebuildable local SQLite query index and centralized HTTP API server.

### 5.4 Strictly Out of Scope (Exclusions)
* **No Duplication of RAG Runtime Operations:** `evalforge_maestro` must **not** parse documents, chunk text, generate document index embeddings, manage vector databases, or execute production retrieval.
* **No Framework Lock-In:** Core orchestration and metric engines must **not** depend on LangChain, LlamaIndex, LangGraph, or any single LLM vendor SDK.
* **No Web UI Dashboard in MVP:** Web-based frontend dashboards and HTTP servers are excluded from the initial package scope in favor of CLI, Markdown, and JSON artifacts.

---

## 6. Core Domain Contracts & Mathematical Invariants

### 6.1 Evidence-Aware & Anomaly-Safe Evaluation Invariants
`evalforge_maestro` must evaluate intermediate execution evidence independently of final output text and prevent score masking:
* **Retrieval vs. Answer Decoupling:** A factually correct final answer paired with irrelevant retrieved context must pass answer correctness but **fail** retrieval relevance and/or groundedness.
* **Groundedness Decoupling:** Relevant retrieved context paired with an inaccurate or hallucinated answer must pass retrieval metrics but **fail** answer correctness/groundedness.
* **Mandatory Case & Anomaly Protection:** High aggregate metric scores must **never** mask a failure on a test case designated as mandatory/critical (`criteria.mandatory = True`), nor conceal a severe drop in an individual metric or a high inter-metric disagreement (which must trigger at minimum a `WARNING` or human-review anomaly flag).

### 6.2 Deterministic IR Metric Definitions
All built-in retrieval metrics operate over ordered retrieved chunk IDs $R = [r_1, r_2, \dots, r_n]$ and ground-truth relevant chunk IDs $G$ (where $|G| > 0$; if $|G| = 0$, the metric returns `score = None` with status `NOT_APPLICABLE` rather than dividing by zero or emitting `NaN`):
* **$\text{Precision@K}$:** $\frac{|R_{1..K} \cap G|}{K}$
* **$\text{Recall@K}$:** $\frac{|R_{1..K} \cap G|}{|G|}$
* **$\text{Hit Rate@K}$:** $1.0$ if $|R_{1..K} \cap G| > 0$ else $0.0$
* **$\text{MRR}$ (Mean Reciprocal Rank):** $\frac{1}{\text{rank}_1}$ where $\text{rank}_1$ is the 1-based index of the first item in $R$ belonging to $G$, or $0.0$ if none match.
* **$\text{NDCG@K}$:** $\frac{\text{DCG@K}}{\text{IDCG@K}}$ where $\text{DCG@K} = \sum_{i=1}^{\min(K, |R|)} \frac{2^{\text{rel}_i} - 1}{\log_2(i + 1)}$ (supporting both binary relevance $\text{rel}_i \in \{0, 1\}$ and graded integer relevance labels).

### 6.3 Core Data Contracts (Single Source in `src/evalforge_maestro/types.py`)
1. **`EvaluationCase` Contract:**
   * `schema_version`: Semantic schema version string (e.g., `"1.0"`).
   * `id`: Unique immutable identifier within the dataset (duplicate IDs raise a dataset validation error).
   * `input`: User query, prompt, or structured task payload.
   * `reference`: Expected answer, reference text, or target structured output (optional per metric).
   * `expected_context`: Identifiers or text snippets of ground-truth evidence documents/chunks (with optional graded relevance weights).
   * `expected_tools`: Expected tool invocations and argument constraints (reserved/optional for agent cases).
   * `metadata`: Categorization tags, split (`eval` vs. `train`/`few_shot`), difficulty level, domain, and provenance source.
   * `criteria`: Case-specific evaluation rules, mandatory pass flags, or threshold overrides.

2. **`ExecutionResult` Contract:**
   * Captures `case_id`, original `input`, actual `output`, retrieved context chunks (`id`, `text`, `parent_id`, `rank`, `score`, `metadata`), execution trace/steps, tool calls and arguments, token consumption (`prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `total_tokens`), `elapsed_seconds`, `truncated` flag, runtime errors/warnings, and target system/model/configuration fingerprints.

3. **`MetricResult` Contract:**
   * Captures `metric_id`, `metric_version` (coupled to calculation logic), `score` (`float | None` in `[0.0, 1.0]`, never `NaN` or `Inf`), categorical label, explicit `status` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, `NOT_APPLICABLE`), human-readable `explanation`, specific supporting evidence references, `anomaly_flags`, and the metric configuration snapshot.
   * Every metric implementation must formally declare what it measures, its required inputs from `EvaluationCase` and `ExecutionResult`, its calculation method, and its known limitations.

4. **`RunRecord` & Reproducibility Contract:**
   * Captures `schema_version`, unique `run_id`, ISO-8601 UTC `timestamp`, `package_version`, `dataset_id`, `dataset_version`, canonical `dataset_fingerprint` (SHA-256), `system_version`, model/provider identifiers, prompt/config fingerprints, `metric_versions`, judge model/prompt configuration (including `mock_mode: bool`), controllable random seeds, rounded aggregate scores, and all case-level `ExecutionResult` and `MetricResult` payloads.
   * **Immutability Rule:** Once persisted to `.evalforge/runs/<run_id>.json`, a `RunRecord` cannot be mutated in place; any re-evaluation or dataset modification must generate a new `run_id` and version fingerprint.

5. **`CalibrationReport` Contract:**
   * Captures `schema_version`, `metric_id`, judge configuration, total human-labeled cases evaluated, exact agreement rate (%), directional bias breakdown (`too_generous_rate`, `too_harsh_rate`), mean human score vs. mean judge score delta, per-case disagreement details, and a recommended calibrated pass threshold.

---

## 7. Engineering Standards and Quality Baseline

### 7.1 Architectural Integrity, Packaging & AST Purity
* **Standardized Package Layout:** Repository root `evalforge-maestro/`, package source at `src/evalforge_maestro/` with `py.typed` (PEP 561), dual CLI entrypoints (`evalforge-maestro` and `evalforge_maestro`), and dynamic Git-tag versioning via `hatch-vcs`.
* **Modular Decoupling:** Strict boundary separation across nine logical subsystems: `types.py` (single schema source), `datasets`, `adapters` (including `CallableAdapter`, `RAGAdapter`, and lazy `DocpipeAdapter`), `execution` (orchestrator & checkpointing), `metrics`, `judges` (LiteLLM wrapper, prompt-injection delimiter framing, calibration & `--mock` provider), `regression` (baselines, trends, anomaly flags, quality gates), `storage` (canonical JSON/JSONL + `manifest.jsonl`), and `reporting`/`cli`.
* **Library Purity & AST Enforcement (`tests/test_library_purity.py`):** Automated AST boundary tests verify that library modules (`types`, `datasets`, `metrics`, `judges`, `regression`, `execution`) never import `cli`, `tomllib`, `dotenv`, or read external configuration files, and that `metrics`, `judges`, and `regression` never import `adapters`.
* **Subprocess Cold-Start & Lazy-Import Verification:** Automated subprocess tests assert that `import evalforge_maestro` and `evalforge-maestro --help` do not load heavy optional dependencies (`litellm`, `docpipe_maestro`, `numpy`, `scipy`) into `sys.modules`.
* **Public API & Signature Pinning (`tests/test_api_stability.py`):** Pin `__all__`, public exception inheritance (`EvalforgeError` hierarchy), and `inspect.signature(...)` parameters across public entrypoints so breaking changes fail CI immediately.

### 7.2 Deterministic CLI, Exit Codes & Stream Separation
* **CLI Subcommands:** `run`, `compare`, `trend`, `calibrate`, `baseline`, `report`, and `config` (`config show --resolved` prints active configuration with secrets masked).
* **Configuration Precedence:** Strictly enforced and tested order: `CLI flags` > `Environment variables (EVALFORGE_*)` > `Project config file (evalforge.toml, non-recursive CWD)` > `Built-in defaults`.
* **Deterministic POSIX Exit Codes:**
  * `0`: `PASS` (or `WARNING` / `INCONCLUSIVE` when `--strict` is not enabled).
  * `1`: `FAIL` (mandatory quality gate threshold violated, critical case failed, or `--strict` triggered on `WARNING`/`INCONCLUSIVE`).
  * `2`: Configuration, CLI argument, or dataset/schema validation error.
  * `3`: Target adapter or external judge runtime/network failure (when `--fail-fast` is active or zero cases completed).
  * `4`: Security or locality policy violation (e.g., remote endpoint blocked under `--local-only` or PII egress block).
* **Stream Hygiene:** `--json` machine-readable output belongs strictly on `stdout`; human diagnostics, warnings, and `--log-json` / `--log-level` telemetry belong strictly on `stderr`. Library modules attach only `logging.NullHandler()` and never touch the root logger or `stdout`.

### 7.3 Numerical Determinism, Judge Safety & Fault Isolation
* **Canonical Hashing & Float Rounding:** Compute SHA-256 fingerprints over canonicalized JSON (sorted keys, UTF-8, `\n` line endings). Round all metric scores and regression deltas to 6 decimal places with explicit epsilon tolerance (`1e-9`) to prevent IEEE 754 drift.
* **Metric Formula Versioning Guard:** Pin normalized AST/source hashes of built-in deterministic metrics in contract tests so altering a formula without bumping `metric_version` fails CI.
* **Judge Prompt-Injection Isolation & Schema Enforcement:** Wrap untrusted target outputs and retrieved contexts inside randomized XML/nonce delimiters in judge prompts; validate judge JSON responses strictly via Pydantic schemas (`0.0 <= score <= 1.0`, non-empty rationale), retrying transient failures and marking unparseable responses `INCONCLUSIVE` rather than defaulting to `0.0` or `1.0`.
* **Atomic Writes & Crash Recovery:** Stage incremental run results to `.evalforge/tmp/<run_id>.jsonl` and commit final `.evalforge/runs/<run_id>.json` and `.evalforge/manifest.jsonl` updates atomically via temp-file rename (`os.replace`) under `0o700`/`0o600` directory/file permissions.
* **Per-Case Fault Isolation:** A runtime exception or timeout in a single evaluation case or metric is captured cleanly within that case's `ExecutionResult` / `MetricResult` (marked error/`INCONCLUSIVE`) without crashing the batch run, unless `--fail-fast` is passed.

### 7.4 Testing Strategy & Mandatory Release Gates
* **Strict Warnings & Coverage:** `pytest` configured with `filterwarnings = ["error"]` (scoped ignore rules only for third-party library deprecations) and `--cov` enforcing a minimum **85% branch coverage** floor across `src/evalforge_maestro/`, with **100% coverage** on deterministic metric formulas and quality gate decision logic.
* **Hermetic Test Isolation:** Global `autouse` pytest fixture clears all `EVALFORGE_*` and provider API key environment variables and blocks outbound network sockets unless explicitly enabled, ensuring zero network calls and zero `.env` leakage during test runs.
* **Named Mandatory Release Gates (`--strict-markers`):**
  * `@pytest.mark.gate_determinism`: Verifies identical inputs, policies, and `--mock` judge runs produce identical scores, gate statuses, and CLI exit codes across runs.
  * `@pytest.mark.gate_immutability`: Verifies persisted `RunRecord` artifacts and canonical dataset fingerprints cannot be silently overwritten or corrupted.

### 7.5 CI/CD & Open-Source Release Guardrails
* **Static Analysis & Security:** Enforced via `ruff format --check .`, `ruff check .` (`E, W, F, I, UP, B, SIM, RUF`), `ruff check --select S src/` (Bandit security checks), and `mypy --strict src tests`.
* **GitHub Actions Matrix (`.github/workflows/ci.yml`):**
  * `uv lock --check` lockfile verification.
  * Cross-OS smoke matrix (`ubuntu-latest`, `macos-latest`, `windows-latest`) paired with `.gitattributes` enforcing LF on text files.
  * Isolated `--no-dev` minimal-core installation check verifying zero hidden dev-dependency leakage and clear `MissingExtraError` hints.
  * Packaging smoke job running `uv build`, `twine check --strict dist/*`, and clean wheel/sdist installation in fresh virtual environments.
  * `pip-audit` dependency vulnerability scan and `cz check` Conventional Commits enforcement.
* **Tag-Driven OIDC Trusted Publishing (`.github/workflows/release.yml`):** On `v*` tag push, re-run all gates, verify built wheel version matches tag, publish to `TestPyPI` via OIDC, verify clean install, publish to `PyPI`, and create the GitHub Release.

---

## 8. Objective Acceptance Criteria (MVP Verification)

The MVP implementation of `evalforge_maestro` is verified as complete if and only if all of the following conditions are demonstrated:

1. **Zero-Intrusion Dataset Definition:** A user can define, validate, fingerprint, and version a multi-case JSONL evaluation dataset (or import a `docpipe-maestro` eval fixture) without modifying target application code.
2. **Adaptability (`Callable`, `RAG`, and `Docpipe`):** A user can evaluate a standalone Python callable, a protocol-mapped RAG pipeline, and a `docpipe-maestro` collection via public adapters under `evalforge_maestro.adapters`.
3. **Multi-Metric Evidence Inspection:** A single evaluation run executes both retrieval metrics (against retrieved context) and answer metrics (against generated output) from the same `ExecutionResult`, correctly flagging cases where the answer is right but retrieval failed (and vice versa).
4. **Workstation-Safe Streaming Execution:** Running a multi-hundred-case dataset streams inputs, bounds concurrency, checkpoints incrementally, and completes within configured memory/resource guardrails without exhausting RAM.
5. **Deterministic `--mock` & `--local-only` Execution:** Running `evalforge-maestro run --mock --local-only` executes the full evaluation and quality gate pipeline offline with zero external API keys or network calls.
6. **Judge Calibration Diagnostics:** Running `evalforge-maestro calibrate` against a fixture human-label dataset outputs agreement percentage, directional bias (`too_generous` vs. `too_harsh`), score delta, and a recommended pass threshold.
7. **Immutable Canonical Persistence:** Completing a run atomically writes an immutable `RunRecord` to `.evalforge/runs/<run_id>.json` and appends summary metrics to `.evalforge/manifest.jsonl`.
8. **Granular Regression, Trend & Anomaly Detection:** Comparing a candidate run against a saved baseline (or window of historical runs) accurately identifies aggregate regressions, per-case regressions, linear trend degradation, cross-version config/dataset drift warnings, and inter-metric disagreement anomalies.
9. **Deterministic Quality Gates & Exit Codes:** Evaluating a run against a policy threshold configuration deterministically yields `PASS`, `FAIL`, `WARNING`, or `INCONCLUSIVE` and maps to documented POSIX exit codes (`0`–`4`).
10. **Dual Artifact Export & CI Reproducibility:** Any evaluation, calibration, or comparison run exports both schema-validated JSON (`stdout`/file) and human-readable Markdown diagnostic reports, and passes the full multi-OS/packaging CI pipeline on a clean clone.