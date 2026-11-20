# Feature Specification: Statistical & Embedding Similarity Metrics

**Feature Branch**: `007-statistical-embedding-metrics`

**Created**: 2026-11-20

**Status**: Draft

**Input**: Post-M6 Capability 1 (`docs/future-features.md`) — Statistical & Embedding Similarity Metrics: lazy-loaded embedding similarity metrics behind an optional `[embeddings]` extra (preserving clean core cold-start behavior) plus multi-run statistical distribution comparisons (confidence intervals and significance flags for comparing non-deterministic runs beyond simple mean deltas).

## Clarifications

### Session 2026-11-20

- Q: When a metric shows a statistically significant score drop that is still smaller than the Quality Gate's allowed regression drop tolerance, should the gate always warn/fail or require exceeding a minimum practical drop threshold first? → A: Flag any statistically significant drop (`ci_high < 0`, regardless of drop size) as `WARNING`, escalating to `FAIL` under `--strict` or `fail_on_significant_regression`.
- Q: When running repeated trials in a single command (`run --repeats N`), how should the Quality Gate evaluate mandatory test case failures and metric score floors across those N repeats? → A: Persist all `N` immutable runs; fail mandatory checks if any repeat fails a mandatory case, and evaluate metric score floors and baseline comparisons against the candidate cohort's pooled means across all `N` repeats.
- Q: When comparing cohorts of multiple baseline runs against multiple candidate runs, should the primary statistical significance test measure run-to-run score spread across repeated runs or only per-case score differences after averaging across trials? → A: Primary significance tests run-to-run spread across repeated run averages (Welch's unequal-variance t-test for >=2 runs per side, or one-sample t-test when comparing 1 reference run against >=2 repeats; default `min_statistical_samples = 2`), plus secondary per-case paired intervals.
- Q: How should the two new embedding metrics participate in decoupled evidence diagnostics when an answer's surface quality diverges from retrieval or context alignment? → A: Classify `embedding_similarity` as an answer-quality metric and `context_embedding_similarity` as a context-alignment/grounding metric (analogous to `groundedness`) inside decoupled evidence diagnostics.
- Q: Should embedding configuration stay independent from judge configuration, and should invoking an embedding metric without `[embeddings]` installed fail immediately even under `--mock` or missing case references? → A: Keep `[embedding]` configuration strictly separate from `[judge]` (defaulting to `mock-embedding` in `--mock` mode or requiring explicit embedding model/endpoint), and fail immediately with missing-extra guidance whenever an embedding metric is invoked without `[embeddings]` installed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Embedding Cosine Similarity Evaluation (`[embeddings]`) (Priority: P1)

As an AI engineer evaluating open-ended LLM answers where surface phrasing varies legitimately from the reference answer, I want optional semantic similarity metrics backed by text embeddings so I can catch semantic drift quickly and deterministically in offline tests without triggering heavy model dependencies when the feature is not installed or invoked.

**Why this priority**: Exact and normalized string matching unfairly penalize valid paraphrases, while LLM-as-a-judge checks add cost and latency. Optional embedding similarity provides a fast semantic signal between deterministic string metrics and full LLM judges while preserving minimal core installation footprint.

**Independent Test**: Run evaluation with the optional embeddings capability installed against reference/output pairs (identical paraphrases, unrelated text, and missing references), both in live/custom provider mode and deterministic offline `--mock` mode; also import the core package in a clean environment without the optional embeddings extra installed and confirm cold-start speed and actionable missing-extra guidance when invoked.

**Acceptance Scenarios**:

1. **Given** an evaluation case with a target answer and reference output (or retrieved context, depending on selected metric scope) and the `[embeddings]` capability installed, **When** embedding similarity evaluates a semantically equivalent paraphrase under `--mock` or configured embedding provider, **Then** it produces a bounded score in `[0.0, 1.0]`, explicit status (`PASS` / `FAIL`), supporting explanation, and metric version provenance.
2. **Given** an evaluation case missing a required reference text or retrieved chunks (or receiving empty output), **When** embedding similarity evaluates the case, **Then** it handles empty/missing ground truth safely without dividing by zero or producing invalid floating-point numbers (returning `NOT_APPLICABLE` when ground truth is absent, or failing safely on zero-magnitude/invalid vectors).
3. **Given** a clean core installation without `[embeddings]` installed, **When** a user imports the package or runs `--help` or any deterministic/judge command, **Then** no optional embedding dependencies are loaded or required; attempting to execute an embedding similarity metric raises an actionable missing-extra error naming `evalforge-maestro[embeddings]`.
4. **Given** `--local-only` or `--block-pii` security flags paired with an embedding similarity metric, **When** pre-network policy checks execute before any external embedding request, **Then** non-loopback endpoints or PII-bearing payloads are blocked prior to outbound network transmission with deterministic exit codes.

---

### User Story 2 - Multi-Run & Distributional Regression Comparisons (Priority: P1)

As a reliability engineer evaluating non-deterministic LLM or agent pipelines, I want regression comparisons to calculate score dispersion, confidence intervals around mean deltas, and statistical significance indicators across repeated runs and case distributions so flaky run-to-run variance is clearly separated from genuine quality changes.

**Why this priority**: Comparing single-run averages on stochastic LLM outputs frequently produces false regression alarms or masks real degradations behind noisy variance. Statistical distribution comparisons turn `compare` into rigorous release evidence beyond simple mean differences.

**Independent Test**: Compare baseline and candidate evaluation results whose mean delta is small relative to high variance vs. results with consistent shift across cases or repeated runs; verify deterministic confidence intervals, dispersion metrics, significance classifications, and insufficient-sample guards across identical inputs.

**Acceptance Scenarios**:

1. **Given** a baseline-vs-candidate regression comparison with case-level and/or multi-run sample distributions, **When** statistical comparison executes, **Then** the comparison report includes dispersion summary metrics, bounded confidence intervals for the score delta, an explicit significance status (for example: significant improvement, significant regression, not significant, or insufficient sample size), and human-readable interpretation in JSON and Markdown reports.
2. **Given** repeated evaluation runs executed under the same configuration or explicit candidate/baseline run cohorts, **When** the user invokes multi-run comparison, **Then** the system aggregates across-run and across-case variation cleanly without mutating immutable run artifacts.
3. **Given** a tiny dataset or single-point sample where statistical inference is unreliable (such as fewer than the minimum required paired observations or zero variance across all pairs), **When** statistical comparison runs, **Then** it avoids unstable estimates or divisions by zero and explicitly reports `insufficient_data` / non-significant uncertainty status alongside the raw mean delta.

---

### User Story 3 - Repeatable Evaluation Runs & Quality Gate Statistical Awareness (Priority: P2)

As a CI operator releasing prompt or model changes, I want ergonomic CLI and configuration support for running repeated trials on non-deterministic targets, configuring embedding similarity metrics in TOML/CLI, and surfacing statistically significant regressions cleanly inside the Quality Gate so release decisions distinguish real regressions from noise.

**Why this priority**: Operationalizing statistical rigor requires first-class CLI/config ergonomics (`evalforge.toml`, `run`, `compare`, and `report`) and transparent Three-Way Quality Gate separation so operators do not manually stitch multiple runs together.

**Independent Test**: Run `config validate`, multi-repeat offline `--mock` evaluation runs, multi-run comparison, and Markdown/JSON report rendering end-to-end; verify repeatable exit codes, gate status transitions, secret masking, and backward compatibility when comparing historical runs lacking statistical metadata.

**Acceptance Scenarios**:

1. **Given** CLI or TOML configuration specifying embedding metrics, embedding model/locality settings, confidence level, or repeat count, **When** `config validate` and `run` execute, **Then** settings validate strictly under standard precedence (`CLI > ENV > file > defaults`), secrets are masked in configuration output, and repeated trials persist immutable run artifacts.
2. **Given** a regression check where a metric regresses with high statistical confidence vs. one with noisy non-significant variance, **When** the Quality Gate evaluates release readiness, **Then** it applies explicit statistical significance policy rules without concealing mandatory case failures, anomalies, or cross-version drift warnings.
3. **Given** legacy historical run artifacts created before this feature existed, **When** loaded into `compare` or `report`, **Then** historical runs deserialize cleanly without schema breakage and degrade gracefully on unsupported fields.

---

### Edge Cases

- What happens when embedding texts exceed context or token limits or contain only whitespace/punctuation? Empty target outputs or empty references follow deterministic zero-division/missing-reference safety (`NOT_APPLICABLE` for missing ground truth, bounded `0.0` or explicit status on blank output); provider truncation or oversize inputs are bounded by configured resource limits without crashing the batch.
- What happens when an embedding provider returns vectors with zero norm (`[0, 0, ...]`), mismatched dimensions between reference and candidate vectors, or `NaN`/`Inf` values? The metric catches invalid vector math explicitly and marks the case `INCONCLUSIVE` with diagnostic error context rather than leaking `NaN`/`Inf` or crashing other cases.
- What happens when two runs compared statistically do not share identical case IDs (added/removed dataset cases) or have mixed `NOT_APPLICABLE` / `INCONCLUSIVE` scores on some cases? Paired statistical tests compute solely over valid aligned case pairs while clearly reporting excluded/missing pair counts and falling back cleanly when unpaired or under-powered.
- What happens when baseline runs and candidate runs inside a multi-run comparison differ in `dataset_fingerprint` or `metric_version`? Cross-version provenance drift detection surfaces explicit drift warnings so incomparable distributions are never silently pooled together.
- What happens when all paired deltas are identically zero (`std = 0`, `delta = 0`)? Zero variance produces deterministic zero-width confidence interval `[0.0, 0.0]` classified as not significant (`no_change`), never dividing by zero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide optional embedding similarity evaluation behind a dedicated `[embeddings]` installation extra so cold-start imports and non-embedding workflows remain lightweight and free of optional vector dependencies; invoking an embedding metric without `[embeddings]` installed MUST fail immediately with a clear `MissingExtraError` referencing `evalforge-maestro[embeddings]` regardless of `--mock` mode or missing case ground truth, and `[embedding]` configuration MUST remain strictly separate from `[judge]` configuration (defaulting to `mock-embedding` in `--mock` mode or requiring explicit embedding settings).
- **FR-002**: System MUST keep the optional `[embeddings]` dependency footprint lightweight (vector normalization and cosine similarity computation paired with a provider-independent embedding interface supporting local or remote model-serving endpoints, caller-supplied embedding callables, and deterministic offline `--mock` vector generation, without bundling multi-gigabyte in-process model weights).
- **FR-003**: System MUST expose two built-in embedding similarity metrics — `embedding_similarity` (comparing target output against `EvaluationCase.reference`) and `context_embedding_similarity` (comparing target output against retrieved context chunks via configurable `max` or `mean` aggregation, defaulting to `max`) — mapping cosine similarity to strictly bounded `[0.0, 1.0]` scores via zero-clamping (`max(0.0, cosine)`), never emitting `NaN` or `Inf`, declaring explicit `metric_version` and formal capability/limitation metadata, and returning `NOT_APPLICABLE` (`score = None`) when required reference text or retrieved chunks are empty/absent.
- **FR-004**: System MUST provide deterministic offline `--mock` vector generation for embedding metrics alongside pre-network `--local-only` endpoint validation, `--block-pii` egress checks, bounded async execution, and single-case fault isolation (`INCONCLUSIVE` on invalid vectors, zero norms, or dimension mismatches).
- **FR-005**: System MUST support statistical distribution comparisons across both (a) single-run pairwise `compare` (computing paired case-level score differences, dispersion, confidence interval bounds, and significance classifications automatically across aligned valid case pairs) and (b) multi-run cohort comparison (comparing $N \ge 1$ baseline runs against $M \ge 1$ candidate runs plus ergonomic repeated trial execution via `--repeats` on `run`, where primary statistical significance evaluates run-to-run spread across repeated run averages via unequal-variance / one-sample tests with default `min_statistical_samples = 2` while also attaching secondary per-case paired intervals over trial-averaged scores); the Quality Gate MUST surface **any** statistically significant negative shift (`ci_high < 0`, `p < alpha`, regardless of drop size relative to `max_regression_drop`) as an advisory `WARNING` by default, escalating to `FAIL` under `--strict` or explicit `fail_on_significant_regression` policy configuration while never hiding mandatory failures, anomalies, or provenance drift warnings.
- **FR-006**: Statistical distribution calculations MUST compute reproducible confidence intervals, dispersion statistics (such as standard deviation / standard error), effect size or sample counts, and clear significance classifications (`significant_improvement`, `significant_regression`, `not_significant`, `insufficient_data`) using deterministic numerical rounding (`6` decimal places with epsilon guards) and zero external heavy dependencies required for core statistical comparisons.
- **FR-007**: System MUST preserve immutable canonical run storage, backward-compatible `1.0` schema deserialization across `.evalforge/runs/*.json` and `manifest.jsonl`, strict separation of Evaluation / Regression / Quality Gate in JSON and Markdown reports, CLI secret masking, and unidirectional architectural import boundaries (zero `cli`/`adapters` leaks into core/metrics/regression); decoupled evidence diagnostics MUST classify `embedding_similarity` as an answer-quality metric and `context_embedding_similarity` as a context-alignment/grounding metric (analogous to `groundedness`).
- **FR-008**: System MUST extend CLI commands and `evalforge.toml` / `EVALFORGE_*` configuration precedence cleanly to configure embedding metrics, locality/provider options, repeat execution counts (`--repeats N`), statistical confidence level (`alpha` / confidence %), and minimum sample requirements without breaking existing `--strict`, `--mock`, `--local-only`, or exit codes (`0`–`4`); for `--repeats N` (`N >= 2`), all `N` immutable runs MUST persist cleanly, any mandatory case failure across any repeat MUST fail the Quality Gate, and metric score floors and baseline comparisons MUST evaluate against the candidate cohort's pooled means across all `N` repeats.

### Key Entities

- **Embedding Configuration**: Typed settings governing embedding model identifier, optional API base, similarity normalization/threshold, aggregation mode (when multiple context chunks exist), timeout, locality policy (`local_only`), and deterministic `--mock` behavior.
- **Statistical Comparison Summary**: Immutable statistical evidence attached per metric in comparison results containing sample size, mean delta, baseline/candidate dispersion, confidence level, lower/upper confidence interval bounds, significance label, and explanatory summary.
- **Run Cohort / Trial Group**: Collection of immutable run records executed under comparable dataset/configuration conditions used to measure stochastic run-to-run variability alongside per-case variation.
- **Statistical Gate Policy Rule**: Configurable policy rule defining minimum required sample size, confidence level, and whether statistically significant regression emits `WARNING` or blocks as `FAIL`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a minimal core installation without `[embeddings]`, cold-start package import and `--help` load zero optional vector or judge dependencies and complete without import side effects; executing an embedding metric without `[embeddings]` fails deterministically with clear installation instructions.
- **SC-002**: All built-in embedding similarity metrics execute deterministically offline under `--mock` (`100%` identical scores and gate results across repeated identical runs) and enforce pre-network `--local-only` and `--block-pii` protections before any remote call.
- **SC-003**: Statistical confidence interval and significance computations produce identical bounds and classifications across repeated executions on identical run inputs, never fail with `NaN`/`Inf` or zero-division errors on constant or tiny samples, and report `100%` branch test coverage on new metric and Quality Gate decision logic alongside `>= 85%` global branch coverage.
- **SC-004**: Existing saved run artifacts, datasets, CLI commands, and non-statistical workflows remain `100%` backward-compatible with zero broken deserializations or regressions across existing unit, contract, purity, and integration checks.

## Assumptions

- Statistical inference (confidence intervals and significance testing) relies on deterministic paired-sample and/or deterministic seeded resampling methods that require no external heavy scientific runtime dependencies in core installation.
- Target systems remain outside evaluation control: embedding similarity compares already-captured target outputs, references, and retrieved contexts rather than building document retrieval indexes or chunk stores.
- Historical run records without statistical summary fields remain readable as valid runs and participate in pairwise comparisons cleanly.
