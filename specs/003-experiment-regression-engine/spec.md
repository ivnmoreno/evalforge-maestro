# Feature Specification: Milestone 3 — Experiment & Regression Engine

**Feature Branch**: `003-experiment-regression-engine`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "start 003" — Milestone 3: Experiment & Regression Engine (`003-experiment-regression-engine`), delivering immutable baseline pinning, pairwise run comparison (aggregate and per-case), sliding window trend slope analysis, automatic anomaly and inter-metric disagreement flagging (`> 0.3` divergence and aggregate masking protection), cross-version provenance drift detection (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`), and a deterministic `QualityGate` (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`) keeping evaluation, regression, and release acceptance strictly separate.

## Clarifications

### Session 2026-11-18

- Q: How much may a metric's average score drop compared to a pinned baseline before failing or warning at the release quality gate by default? → A: Block (`FAIL`) when an average metric score drops by more than `0.05` (`5` percentage points) compared with baseline; smaller drops `<= 0.05` remain `PASS` (recorded diagnostically in comparison deltas) unless stricter thresholds or soft-warning options are configured.
- Q: When an overall evaluation summary looks healthy or improves on average, what exact rule should trigger a "masked critical drop" anomaly warning so hidden regressions are caught deterministically? → A: Flag masked drops deterministically whenever a passing or non-regressing overall summary coincides with any of: (1) an individual metric dropping by strictly more than `max_regression_drop` (default `0.05`) or breaching its configured floor, (2) a matched evaluation case dropping by `>= 0.25` (with `1e-9` tolerance) inside a passing/non-regressing metric, or (3) any mandatory evaluation case failure (`has_mandatory_failures`).
- Q: When analyzing historical trends across a workspace containing runs from different datasets without an explicit filter, how should runs be selected for the sliding window? → A: Scope unfiltered trend queries to the most recent run's `dataset_id` by default, while supporting explicit filter overrides (`dataset_id` filter or cross-dataset inclusion).
- Q: What downward trend slope should classify a metric as degrading across a sliding window, and should a degrading trend warn or fail at the quality gate by default? → A: Classify linear slope `< -0.01 - 1e-9` per sequential run as `DEGRADING` (`> +0.01 + 1e-9` as `IMPROVING`, within `[-0.01, +0.01]` as `STABLE`), and emit `WARNING` in `QualityGate` by default with an explicit escalation option to `FAIL`.
- Q: What share of failed or errored (inconclusive) test cases in an evaluation run should warn reviewers versus making the entire `QualityGate` decision `INCONCLUSIVE` by default? → A: Emit `WARNING` (with an `INCONCLUSIVE_SPIKE` / incomplete-evidence flag) when the inconclusive case rate (`inconclusive_case_count / evaluated_case_count`) is strictly positive and `<= 0.10`, and emit `INCONCLUSIVE` when it exceeds `0.10` (or when zero applicable scores exist across the run), configurable via `max_inconclusive_rate`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pin and Resolve Immutable Reference Baselines (Priority: P1)

An AI/ML engineer or technical lead pins a verified historical evaluation run as a named reference baseline (such as a release branch baseline or default main baseline) so future experiments and pull requests can be compared against a trusted anchor without risking accidental modification of historical evidence.

**Why this priority**: Every regression workflow depends on an unambiguous, tamper-resistant reference point. Without pinned baselines that protect historical artifacts from silent mutation, comparisons across commits or provider updates cannot be trusted.

**Independent Test**: Can be fully tested by committing evaluation runs, pinning named baselines, resolving and listing active baselines, verifying rejection of accidental duplicate overwrites unless explicitly forced, and confirming underlying historical run artifacts remain completely unchanged when baselines are pinned, replaced, or unpinned.

**Acceptance Scenarios**:

1. **Given** a persisted valid historical run record, **When** a user pins that run under a baseline name (defaulting to a standard default baseline identifier if omitted), **Then** the baseline registry records the baseline pointer alongside its timestamp, optional annotation, and provenance identifiers without modifying the underlying run record or run ledger.
2. **Given** a baseline name that is already pinned to a different historical run, **When** a user attempts to pin a new run under the same name without explicit replacement permission, **Then** the system rejects the mutation with a clear immutability/conflict error while keeping the original pinned baseline intact; when explicit replacement permission is provided, the pointer updates atomically while still leaving all historical run records untouched.
3. **Given** a request to pin a nonexistent or corrupted run record, **When** baseline pinning validates the target run, **Then** pinning fails explicitly without writing a broken entry to the baseline registry.
4. **Given** existing named baselines in the registry, **When** a user resolves a baseline by name, lists all pinned baselines, or unpins a baseline name, **Then** lookup returns the exact linked baseline entry and underlying run reference, listing returns baselines in deterministic order, and unpinning removes only the alias pointer without deleting any persisted run records.

---

### User Story 2 - Compare Candidate Runs Against Baselines at Aggregate and Case Level (Priority: P1)

An engineer compares a candidate evaluation run against a baseline run (selected directly or resolved via a pinned baseline name) to verify whether system performance improved, held steady, or regressed across overall metrics and individual test cases.

**Why this priority**: Aggregate metric averages alone obscure localized failures. Pairwise comparison across both macro metric summaries and aligned individual cases lets engineers pinpoint exactly which capabilities improved or degraded between versions.

**Independent Test**: Can be fully tested by comparing pairs of valid run records covering score improvements, regressions, status transitions (`PASS` to `FAIL`), added/removed cases, and mandatory-case regressions without needing live model execution.

**Acceptance Scenarios**:

1. **Given** a baseline run and a candidate run evaluated on the same dataset and metrics, **When** pairwise comparison executes, **Then** it computes deterministic signed score deltas (`candidate - baseline`, rounded to 6 decimal places with near-zero floating-point noise suppression), metric status count deltas, and clear directional classifications (`IMPROVED`, `REGRESSED`, `UNCHANGED`, `ADDED`, `REMOVED`, `INCONCLUSIVE`) for every metric.
2. **Given** matched evaluation cases appearing in both baseline and candidate runs, **When** pairwise comparison evaluates case-level evidence, **Then** each case comparison captures baseline vs. candidate scores, signed deltas, status transitions (such as `PASS` transitioning to `FAIL` or error state), execution error introductions, and whether the case is marked mandatory.
3. **Given** baseline and candidate runs where some cases were added in the candidate or omitted compared with the baseline, **When** pairwise comparison runs, **Then** matched cases are compared cleanly while added and removed case identifiers are explicitly listed rather than silently dropped or misaligned.
4. **Given** target system metadata changes between runs (such as an updated system version or prompt configuration), **When** comparison reports differences, **Then** target-system changes are reported contextually without falsely marking intended system-under-test changes as invalid measurement drift.

---

### User Story 3 - Detect Inter-Metric Disagreements, Masked Drops, and Cross-Version Drift (Priority: P1)

A QA automation engineer or governance reviewer relies on automatic anomaly detection during run inspection and comparison to surface hidden failure modes—such as strong final answers paired with failing retrieval (`> 0.3` divergence), high macro averages concealing sharp single-metric or per-case drops, mandatory-case failures, or mismatched dataset, metric-version, or judge configurations.

**Why this priority**: High-level averages routinely mask catastrophic localized regressions and invalid cross-version comparisons. Automated anti-masking protection is essential to prevent silent quality degradations from passing unnoticed.

**Independent Test**: Can be fully tested by supplying synthetic or recorded runs and run pairs exhibiting (a) case-level or run-level sub-metric divergence above `0.3`, (b) a positive macro average hiding a severe single-metric drop or mandatory case failure, and (c) mismatches in dataset fingerprint, metric version, or judge configuration fingerprint, verifying distinct structured anomaly and drift warnings are emitted every time.

**Acceptance Scenarios**:

1. **Given** a run containing a case (or run-level metric summary) where two or more applicable metrics emit numeric scores that diverge by strictly more than `0.3` (e.g., answer correctness `1.0` alongside retrieval precision `0.0`), **When** anomaly detection evaluates the run, **Then** it raises an explicit inter-metric disagreement anomaly identifying the affected scope, diverging metrics, and observed score spread.
2. **Given** a candidate run where overall average performance remains high or improves relative to a baseline, yet an individual metric suffers a sharp regression drop, falls below critical expectations, or a mandatory test case fails, **When** comparison and anomaly detection evaluate the pair, **Then** a high-aggregate masking anomaly and/or mandatory-failure anomaly is surfaced explicitly so the aggregate cannot conceal the underlying regression.
3. **Given** a baseline run and candidate run (or historical window) where the dataset content fingerprint, any shared metric version, or judge configuration fingerprint differs, **When** cross-version drift detection runs, **Then** distinct provenance drift warnings identify every mismatched dimension (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`) and explain why scores may not be strictly comparable.
4. **Given** a run where dataset sampling was capped before full dataset completion or where high execution-error / inconclusive rates threaten summary validity, **When** anomaly detection runs, **Then** explicit coverage/inconclusive anomalies alert reviewers to partial or degraded evidence.

---

### User Story 4 - Analyze Linear Quality Trends Across a Sliding Window of Runs (Priority: P2)

A technical lead inspects quality trajectories across the latest sliding window of `N` historical runs (e.g., the last 5 or 10 scheduled evaluations) to catch gradual performance decay or upstream provider drift before any single commit exceeds a sharp pairwise threshold.

**Why this priority**: Gradual model or data drift frequently slips past single-commit pairwise checks because each individual delta looks small. Multi-run sliding window slope analysis exposes slow erosion over time while surfacing within-window version changes that would invalidate naive trend lines.

**Independent Test**: Can be fully tested by seeding historical run ledgers/records showing declining, stable, and improving trajectories across windows of size `N`, plus windows containing missing/inconclusive points or mid-window version drift, and verifying exact linear slope values and directional classifications.

**Acceptance Scenarios**:

1. **Given** an ordered chronological history containing at least `2` valid evaluation runs up to window size `N` (`N >= 2`), **When** sliding window trend analysis evaluates a metric over those runs, **Then** it orders runs chronologically from oldest to newest within the window, computes the ordinary least-squares linear regression slope (change per sequential run step, rounded to 6 decimal places), reports start/end/min/max/mean statistics, and classifies the trajectory (`IMPROVING`, `STABLE`, `DEGRADING`, or `INSUFFICIENT_DATA`).
2. **Given** a metric series whose computed linear downward slope is steeper than the configured negative slope tolerance, **When** trend analysis finishes, **Then** that metric is flagged as `DEGRADING` with the exact negative slope and ordered data points preserved in the report.
3. **Given** a sliding window containing runs with changing dataset fingerprints, metric versions, or judge configuration fingerprints, **When** trend analysis inspects provenance across the window, **Then** cross-version drift warnings identify every version transition inside the window so reviewers do not mistake an evaluation configuration change for system drift.
4. **Given** a metric having fewer than `2` valid numeric aggregate points inside the selected window (due to empty history, short history, or `INCONCLUSIVE`/`NOT_APPLICABLE` runs), **When** trend analysis runs, **Then** it avoids division-by-zero and emits a null slope with an `INSUFFICIENT_DATA` status and clear explanation.

---

### User Story 5 - Enforce Deterministic Quality Gate Acceptance Decisions (Priority: P1)

A DevOps engineer or CI/CD pipeline evaluates a candidate evaluation run—optionally alongside a baseline comparison, sliding window trend report, and anomaly findings—against an explicit acceptance policy to receive an unambiguous deterministic release decision (`PASS`, `FAIL`, `WARNING`, or `INCONCLUSIVE`).

**Why this priority**: Separating evaluation and regression analysis from release acceptance allows teams to encode enforceable CI/CD release rules with reproducible outcomes, zero non-determinism, and complete auditability of every triggered rule.

**Independent Test**: Can be fully tested by passing runs, comparisons, trends, anomalies, and gate policy configurations through the quality gate decision engine and asserting deterministic `PASS`, `FAIL`, `WARNING`, and `INCONCLUSIVE` outcomes across identical repeated runs, precedence combinations, drift conditions, and anomaly triggers.

**Acceptance Scenarios**:

1. **Given** a candidate run with all monitored metrics meeting minimum policy thresholds, zero mandatory failures, regression deltas within policy bounds, and no drift, trend, or anomaly warnings, **When** the quality gate evaluates acceptance, **Then** it deterministically returns `PASS` with structured rule checks explaining each satisfied criterion.
2. **Given** a candidate run that achieves high non-mandatory aggregate scores yet fails a mandatory test case, breaches a configured minimum metric score floor, or exceeds maximum allowed aggregate or mandatory-case regression against its baseline, **When** the quality gate evaluates acceptance, **Then** it deterministically returns `FAIL` regardless of high aggregate averages elsewhere.
3. **Given** a candidate run with no hard `FAIL` breaches, yet exhibiting inconclusive evidence conditions (such as zero applicable metric scores, inconclusive rates above allowed threshold, or missing required baseline/trend evidence), **When** the quality gate evaluates acceptance, **Then** it returns `INCONCLUSIVE` rather than silently downgrading incomplete evidence to `PASS` or `WARNING`.
4. **Given** a candidate run with valid applicable evidence and no hard `FAIL` or `INCONCLUSIVE` blockers, yet exhibiting cross-version drift (`dataset_fingerprint`, `metric_version`, or `judge_config_fingerprint` mismatch), inter-metric disagreement (`> 0.3`), aggregate masking warnings, capped datasets, unmatched cases, or non-blocking trend/soft-regression warnings, **When** the quality gate evaluates acceptance, **Then** it returns `WARNING` (or escalates to `FAIL` when explicit strict escalation policy options are enabled), preserving full diagnostic reasons.
5. **Given** identical evaluation inputs, baseline/trend artifacts, and gate policy configuration, **When** the quality gate runs repeatedly across separate invocations, **Then** it produces bit-for-bit identical scores, deltas, flags, triggered rule reasons, and gate decisions.

---

### Edge Cases

- What happens when comparing two runs whose metric sets only partially overlap (a metric exists in the candidate but not the baseline, or vice versa)? Shared metrics compute paired deltas and drift checks, baseline-only metrics are reported as `REMOVED` (and trigger drift/missing warnings), and candidate-only metrics are reported as `ADDED` (and trigger drift notices) without crashing or fabricating zero baseline scores.
- What happens when either baseline or candidate metric aggregate `mean_score` is missing (`NOT_APPLICABLE` or `INCONCLUSIVE`, so no numeric mean exists)? Pairwise delta MUST be absent (`null`) with classification `INCONCLUSIVE` rather than coalescing missing scores to `0.0`.
- What happens when sub-metric divergence is evaluated at the `0.3` boundary (e.g., `0.8 - 0.5 = 0.30000000000000004` in IEEE 754 floating point)? Both canonical 6-decimal rounding and `1e-9` epsilon tolerance MUST apply so exact `0.3` divergence does not trigger a false-positive anomaly, whereas strictly greater divergence (e.g., `0.301`) deterministically triggers it.
- What happens when a regression delta equals `-0.0` in floating-point arithmetic or sits within `[-1e-9, +1e-9]`? Signed delta rounding MUST normalize tiny numerical noise to exact `0.0` (never `-0.0`) so identical runs always yield deterministic unchanged deltas (`0.0`).
- What happens when sliding window analysis receives `window < 2` or zero historical runs? Passing `window < 2` MUST raise an explicit configuration/validation error; querying a store with `0` or `1` runs MUST return a clean valid trend report containing empty/insufficient-data metric states (absent/null slope) rather than failing with division by zero.
- What happens when a quality gate receives both a hard `FAIL` condition (e.g., mandatory case failure) AND `INCONCLUSIVE` / `WARNING` signals simultaneously? Precedence MUST strictly follow `FAIL` > `INCONCLUSIVE` > `WARNING` > `PASS` so severe failures can never be masked by lower-severity warnings or partial inconclusive metrics.
- What happens when `QualityGate` evaluates a run where one metric is entirely `NOT_APPLICABLE` (e.g., a retrieval metric on an answer-only dataset with zero errors) while all other applicable metrics pass cleanly? Pure `NOT_APPLICABLE` counts on unrequired metrics MUST NOT falsely trigger `INCONCLUSIVE`; `INCONCLUSIVE` MUST trigger only when no metrics produce valid applicable scores across the run, a policy-required metric lacks valid numeric evidence, inconclusive execution error rates exceed tolerance, or required baseline/trend evidence is incomplete.
- What happens when historical run records persisted under Milestone 1 or Milestone 2 (which did not record an explicit judge configuration fingerprint) are inspected or compared in Milestone 3? Cross-version comparison and run loading MUST treat an absent judge configuration fingerprint as backward-compatible unset/null, flagging drift only when one run carries a non-null judge configuration fingerprint while the other differs or omits it.
- What happens when two runs have the exact same timestamp inside trend history? Chronological sorting MUST break timestamp ties deterministically (using ledger insertion order or unique run identifier) so window selection and linear regression slopes are 100% reproducible.

## Requirements *(mandatory)*

### Scope Boundaries

- **In Scope (`003-experiment-regression-engine`)**:
  - Separation between **Evaluation** (run records), **Regression & Anomaly Analysis** (baseline registry, pairwise comparison, sliding window trend analysis, inter-metric disagreement & masked drop flagging, cross-version provenance drift), and **Acceptance** (deterministic `QualityGate` policy and decision engine).
  - Immutable local baseline registry supporting create/pin, resolve/get, list, unpin, and explicit overwrite-protected replace using atomic persistence and restricted file/directory permissions without modifying persisted run records.
  - Pairwise run comparison covering signed aggregate deltas, status-count shifts, matched case comparisons, added/removed case tracking, mandatory-case regression detection, and provenance drift checks.
  - Sliding window linear regression trend analysis (`window >= 2`) over chronological historical runs, including per-metric slopes, summary bounds, missing-point accounting, and within-window drift detection.
  - Automatic anti-masking and anomaly engine detecting case-level and run-level metric disagreement (`> 0.3` divergence), high-aggregate-masked individual drops, mandatory case failures, inconclusive spikes, and partial/capped dataset coverage.
  - Deterministic `QualityGate` policy engine emitting schema-validated decisions (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`) following strict precedence (`FAIL` > `INCONCLUSIVE` > `WARNING` > `PASS`), plus optional backward-compatible extension of run/ledger records for `judge_config_fingerprint`.
- **Explicitly Out of Scope (Deferred to Milestones 004–005 / Post-MVP)**:
  - Model-based LLM judges, provider routing, prompt-injection delimiter framing, `--mock`/`--local-only` judge execution, and human judge calibration (`004`).
  - CLI subcommands (`compare`, `trend`, `baseline`), TOML configuration loading, POSIX process exit code mapping, and Markdown diagnostic report formatting (`005`).
  - Multi-step agent execution trace recovery analysis, semantic embedding similarity metrics, OpenTelemetry ingestion, and web UI dashboards (post-MVP / permanently excluded).

### Functional Requirements

#### Baseline Management & Artifact Immutability

- **FR-001**: System MUST provide a versioned local baseline registry allowing users to pin persisted valid run identifiers under human-readable baseline names (defaulting to a standard `"default"` name), inspect/resolve pinned baselines, list all pinned baselines deterministically, and unpin baseline names.
- **FR-002**: Baseline pinning MUST validate that the referenced run record exists and conforms to canonical run schema contracts before recording the baseline pointer alongside creation timestamp, optional annotation/tags, and provenance summary (`dataset_fingerprint`, `metric_versions`, `judge_config_fingerprint`, `system_version`, `model_id`).
- **FR-003**: System MUST uphold historical immutability across baseline operations: pinning, updating, or unpinning baselines MUST NEVER alter historical run record files or run ledger entries, and attempting to repin an existing baseline name to a different run MUST fail explicitly unless explicit overwrite/replace authorization is provided.
- **FR-004**: System MUST persist baseline registry updates atomically under restricted file/directory permissions and redact any sensitive key/credential patterns from baseline metadata prior to storage.

#### Pairwise Run Comparison

- **FR-005**: System MUST support pairwise comparison between any two valid run records (or between a candidate run and a named pinned baseline), producing a single schema-validated comparison artifact strictly separated from target runtime adapters.
- **FR-006**: For every metric present in either baseline or candidate run, pairwise comparison MUST calculate rounded 6-decimal signed deltas (`candidate - baseline` normalized within `1e-9` epsilon, suppressing negative zero `-0.0`), status count deltas, and directional metric outcomes (`IMPROVED`, `REGRESSED`, `UNCHANGED`, `ADDED`, `REMOVED`, `INCONCLUSIVE`), keeping missing scores distinct rather than coalescing them to `0.0`.
- **FR-007**: Pairwise comparison MUST align evaluation cases by unique case identifier (`case_id`), recording matched case comparisons (per-metric score deltas, status transitions such as `PASS` to `FAIL`, execution error transitions, and mandatory-case regression indicators) alongside explicit lists of added and removed case identifiers.

#### Cross-Version Provenance Drift Detection

- **FR-008**: System MUST inspect measurement provenance during both pairwise comparison and sliding window trend analysis, emitting structured drift warnings whenever runs differ in dataset fingerprint (`dataset_fingerprint`), shared metric version values (or metric sets), or judge configuration fingerprint (`judge_config_fingerprint`).
- **FR-009**: Run records and run ledger summaries MUST support an optional judge configuration fingerprint field defaulting to unset/null so Milestone 1 and Milestone 2 persisted artifacts load without migration breaks while enabling forward-compatible drift verification immediately.
- **FR-010**: Cross-version drift detection MUST distinguish measurement-configuration drift (dataset content, metrics, judge configuration, dataset capping/mismatch) from target system changes (system version, target model identifier, adapter configuration fingerprint) so intentional model or prompt comparisons report target changes contextually without triggering false measurement-drift alarms.

#### Anti-Masking & Anomaly Detection

- **FR-011**: System MUST detect inter-metric disagreements both per evaluated case and across run aggregate metric means whenever two or more applicable numeric metrics diverge by strictly more than the configured disagreement threshold (default `0.3`, evaluated with 6-decimal rounding and `1e-9` tolerance).
- **FR-012**: System MUST detect and flag aggregate score masking conditions whenever a passing or non-regressing overall summary (macro mean across metrics `>= 0.5` or non-negative macro delta vs. baseline) coincides with any of: (a) a single metric dropping strictly beyond `max_regression_drop` (default `0.05`) or breaching its configured floor, (b) any matched evaluation case suffering a score drop `>= case_drop_warning_threshold` (default `0.25`, evaluated within `1e-9` tolerance) inside a passing or non-regressing metric, or (c) any mandatory evaluation case failing (`has_mandatory_failures` is active).
- **FR-013**: Anomaly detection MUST also emit structured warning flags for partial/capped datasets (`dataset_capped`) and any run containing inconclusive or execution-errored cases (computing `inconclusive_rate = inconclusive_case_count / evaluated_case_count`, where rates `> 0.0` trigger an `INCONCLUSIVE_SPIKE` warning and rates exceeding `max_inconclusive_rate` trigger gate escalation) so compromised evidence is never silently treated as healthy.

#### Sliding Window Trend Analysis

- **FR-014**: System MUST compute sliding window trend reports over up to the latest `N` (`window >= 2`) chronologically ordered valid runs (with deterministic tie-breaking on equal timestamps), defaulting unfiltered queries to runs matching the most recent run's dataset identifier (`dataset_id`) while supporting explicit filtering by `dataset_id` (or explicit cross-dataset mode), metric set, or model identifier.
- **FR-015**: For each metric inside the sliding window with at least `2` valid numeric aggregate points, system MUST compute the exact ordinary least-squares linear regression slope (change per sequential run position in the window, rounded to 6 decimal places with `1e-9` near-zero stabilization), window score bounds (`min`, `max`, `mean`, `first`, `last`), point count, and directional trend classification using configurable slope threshold `trend_slope_threshold` defaulting to `0.01` (`DEGRADING` when `slope < -threshold - 1e-9`, `IMPROVING` when `slope > threshold + 1e-9`, `STABLE` otherwise, and `INSUFFICIENT_DATA` when `< 2` valid points).
- **FR-016**: Sliding window trend analysis MUST handle missing runs, short histories (`< 2` valid numeric points), and mid-window `INCONCLUSIVE`/`NOT_APPLICABLE` scores cleanly (reporting an absent/null slope and `INSUFFICIENT_DATA` rather than dividing by zero) and MUST surface cross-version provenance transitions across adjacent chronological run pairs inside the window (plus capped-dataset runs).

#### Deterministic Quality Gate Decision Engine

- **FR-017**: System MUST provide a deterministic `QualityGate` evaluator accepting a candidate run, optional pairwise baseline comparison, optional sliding window trend report, and an explicit versioned acceptance policy, producing a schema-validated gate decision record containing one of four outcomes: `PASS`, `FAIL`, `WARNING`, or `INCONCLUSIVE`.
- **FR-018**: `QualityGate` MUST evaluate policy checks under strict precedence `FAIL` > `INCONCLUSIVE` > `WARNING` > `PASS`:
  - Emit `FAIL` when any mandatory case failed, any monitored metric aggregate falls below configured minimum score thresholds, any average metric score drops by strictly more than `max_regression_drop` (default `0.05`) vs. baseline, mandatory-case regression or failed-case limits are breached, or an explicit strict policy setting escalates drift, anomalies, or degrading trends to blocking failures.
  - Emit `INCONCLUSIVE` (when no `FAIL` rule triggered) when zero metrics across the run have applicable numeric evidence, inconclusive case rate (`inconclusive_case_count / evaluated_case_count`) strictly exceeds `max_inconclusive_rate` (default `0.10`, with `1e-9` tolerance), a policy-required metric has no numeric score, required baseline comparison lacks comparable metrics, or required trend gating lacks sufficient historical data—while never marking cleanly passing runs `INCONCLUSIVE` solely because an unrequired metric is `NOT_APPLICABLE`.
  - Emit `WARNING` (when neither `FAIL` nor `INCONCLUSIVE` triggered) when cross-version provenance drift, inter-metric disagreement anomalies (`> 0.3`), masked drop warnings, dataset capping, partial inconclusive case rates (`0.0 < inconclusive_rate <= max_inconclusive_rate`), unmatched baseline/candidate cases, non-blocking trend degradation, or explicitly enabled soft-regression notices (when a policy chooses to warn on drops within `max_regression_drop`) are present.
  - Emit `PASS` when all evaluated criteria pass with zero blocking failures, inconclusive blockers, or active warnings (including when baseline drops remain within `max_regression_drop` and no soft-warning policy is enabled).
- **FR-019**: `QualityGate` decision logic MUST remain strictly pure and deterministic—independent of wall-clock time, randomness, external files, target runtime systems, or command-line interface state—and record every checked rule with its individual status, observed values, thresholds, and human-readable explanation.

### Key Entities *(include if feature involves data)*

- **BaselineEntry**: Immutable snapshot metadata pointing a named baseline alias to a persisted `run_id`, recording `pinned_at` timestamp, optional notes/tags, provenance summary (`dataset_id`, `dataset_fingerprint`, `metric_versions`, `judge_config_fingerprint`, `system_version`, `model_id`).
- **BaselineRegistry**: Schema-versioned collection of named `BaselineEntry` mappings persisted locally in the project artifact store.
- **DriftWarning**: Structured provenance mismatch record identifying drift category (`DATASET_FINGERPRINT`, `METRIC_VERSION`, `METRIC_SET`, `JUDGE_CONFIG`, `DATASET_CAPPED`, `CASE_SET_MISMATCH`), affected metric or provenance field, expected/baseline value, observed/candidate value, and explanatory message.
- **AnomalyFlag**: Structured anti-masking diagnostic record identifying anomaly type (`METRIC_DISAGREEMENT`, `AGGREGATE_MASKED_DROP`, `MANDATORY_CASE_FAILURE`, `INCONCLUSIVE_SPIKE`, `DATASET_CAPPED`), severity (`WARNING` or `FAIL`), scope (`RUN` or `CASE`), affected `case_id` / `metric_id`s, measured numeric spread or drop, and explanation.
- **MetricComparison & CaseComparison**: Aligned baseline-versus-candidate delta records capturing paired scores, signed deltas, status counts or transitions, added/removed cases, and mandatory-case regression markers.
- **RunComparisonReport**: Schema-versioned pairwise regression report combining baseline/candidate provenance, aggregate `MetricComparison` summaries, `CaseComparison` details (`added_case_ids`, `removed_case_ids`, `regressed_case_ids`), `DriftWarning` records, and `AnomalyFlag` findings.
- **MetricTrendSummary & TrendReport**: Schema-versioned sliding window trajectory report capturing ordered `window` size, inspected run sequence, per-metric `slope`, window summary metrics (`mean`, `min`, `max`, `first`, `last`, valid/missing point counts), trend classification, and within-window `DriftWarning` list.
- **QualityGatePolicy**: Declarative, schema-validated threshold and policy rule specification governing minimum metric floors, baseline regression tolerances (`max_regression_drop`, `max_regressed_cases`), anomaly thresholds (`disagreement_threshold = 0.3` default, `case_drop_warning_threshold = 0.25` default), drift escalation behavior, trend slope limits (`trend_slope_threshold = 0.01` default), inconclusive rate limit (`max_inconclusive_rate = 0.10` default), and strict enforcement options.
- **QualityGateResult & GateRuleCheck**: Schema-versioned release acceptance decision (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`) summarizing individual `GateRuleCheck` evaluations, blocking failures, warnings, inconclusive blockers, surfaced `DriftWarning` and `AnomalyFlag` findings, and deterministic outcome rationale.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pinning, updating with explicit confirmation, resolving, listing, and unpinning baselines leaves historical evaluation run records and run ledger entries 100% unmodified, and rejects conflicting unforced baseline overwrites 100% of the time.
- **SC-002**: Pairwise comparison detects 100% of aggregate metric regressions, per-case score drops, `PASS`-to-`FAIL` transitions, added/removed case mismatches, and mandatory-case regressions with 6-decimal score deltas matching reference arithmetic within `1e-9`.
- **SC-003**: Anomaly detection triggers structured alerts on 100% of test cases and run aggregates exhibiting inter-metric divergence exceeding `0.3`, mandatory failures hidden behind passing aggregates, and critical individual drops masked by passing macro averages, with zero false positives at or below the `0.3` boundary.
- **SC-004**: Cross-version provenance inspection surfaces explicit drift warnings on 100% of comparisons and trend windows involving differing `dataset_fingerprint`, shared `metric_version` / metric-set changes, or `judge_config_fingerprint` changes, while leaving intentional target system/model changes unpenalized by measurement-drift warnings.
- **SC-005**: Sliding window trend analysis computes exact linear regression slopes across chronological multi-run windows matching reference least-squares calculations to 6 decimal places in 100% of valid multi-run sequences and safely reports `INSUFFICIENT_DATA` (absent numeric slope) in 100% of `< 2`-point series without errors or invalid numeric values.
- **SC-006**: `QualityGate` yields 100% deterministic, identical outcomes across repeated invocations on identical artifacts and policies, enforces `FAIL` > `INCONCLUSIVE` > `WARNING` > `PASS` precedence across all tested rule combinations, and achieves 100% deterministic verification across every policy decision rule path, including dedicated cross-version drift and anomaly scenarios.

## Assumptions

- **M1 & M2 Artifact Compatibility**: All existing Milestone 1 and Milestone 2 run records and dataset artifacts (`schema_version = "1.0"`) remain readable without requiring retroactive schema migration; newly introduced `judge_config_fingerprint` defaults to unset/null when omitted.
- **Default Anti-Masking & Regression Policy Thresholds**: Unless overridden in `QualityGatePolicy`:
  - Inter-metric disagreement anomaly threshold defaults to `0.3` (strictly greater divergence triggers an anomaly flag).
  - Single-case masked drop anomaly threshold (`case_drop_warning_threshold`) defaults to `0.25` (`baseline - candidate >= 0.25 - 1e-9` inside a passing/non-regressing metric triggers an `AGGREGATE_MASKED_DROP` anomaly).
  - Baseline aggregate `max_regression_drop` defaults to `0.05` (`5` percentage points) for blocking `FAIL`; drops `<= 0.05` remain `PASS` under default settings (still recorded as deltas in comparison reports) unless a stricter `max_regression_drop` (such as `0.0`) or optional soft-regression warning is explicitly enabled.
  - Minimum metric score floors (`min_score` / `min_metric_scores`) default to unset (honoring case-level mandatory failures unless an explicit aggregate floor is configured).
  - Cross-version provenance drift (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`) and non-mandatory inter-metric anomalies default to `WARNING` severity, with explicit policy options to escalate either or both to `FAIL`.
  - Default sliding window size for trend inspection defaults to `5` runs (`window >= 2`), with default trend slope threshold `0.01` per run (`DEGRADING` emits `WARNING` in `QualityGate` by default unless escalated to `FAIL` by policy).
  - Default `max_inconclusive_rate` defaults to `0.10` (`10%` of evaluated cases having execution errors or any `INCONCLUSIVE` metric): rates in `(0.0, 0.10]` trigger `WARNING`, while rates strictly exceeding `0.10 + 1e-9` (or zero valid scores across the run) trigger `INCONCLUSIVE` unless a `FAIL` condition applies first.
- **Linear Trend Indexing Convention**: Sliding window linear regression fits score against normalized sequential index (`0, 1, ..., m - 1`) across valid runs in chronological order rather than uneven wall-clock intervals, ensuring deterministic `slope` magnitude (`score delta per run`) invariant to pauses between runs.
- **Subsystem Purity**: Baseline persistence extends historical storage cleanly without altering run immutability, while regression analysis, anomaly detection, trend slope calculation, and `QualityGate` remain pure over canonical run and comparison records without touching external configuration files or target execution pipelines.
