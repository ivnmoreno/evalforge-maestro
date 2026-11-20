---

description: "Dependency-ordered implementation tasks for Feature 007: Statistical & Embedding Similarity Metrics"
---

# Tasks: Statistical & Embedding Similarity Metrics

**Input**: Design documents from `/specs/007-statistical-embedding-metrics/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required by [`spec.md`](spec.md) (`SC-001`–`SC-004`) and [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) (`>= 85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`, `@pytest.mark.gate_determinism`, `@pytest.mark.gate_immutability`, AST purity, API stability pinning).

**Organization**: Tasks are grouped by user story (`US1`, `US2`, `US3`) so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story identifier (`US1`, `US2`, `US3`) inside user story phases only
- Every task includes exact repository file path(s)

---

## Phase 1: Setup (Packaging & Subpackage Scaffold)

**Purpose**: Configure the lightweight `[embeddings]` optional extra without adding dependencies to minimal core installs and scaffold the `embeddings` subpackage.

- [ ] T001 Add optional dependency group `embeddings = ["numpy>=1.26,<3", "litellm>=1.84.0"]` to `[project.optional-dependencies]` in `pyproject.toml`
- [ ] T002 Refresh lockfile entries for optional `[embeddings]` dependencies using `uv lock` in `uv.lock`
- [ ] T003 [P] Create package scaffold `src/evalforge_maestro/embeddings/__init__.py` declaring `NullHandler`-safe module docstring and lazy-import docstring conventions

---

## Phase 2: Foundational (Shared Pre-Network Guards & Architecture Boundaries)

**Purpose**: Extract shared pre-network locality/air-gap/PII helpers into a leaf-safe module and enforce AST architectural boundaries before any user story code is added.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Create shared pre-network locality, air-gap cost-map (`LITELLM_LOCAL_MODEL_COST_MAP`), loopback URL validation, and PII egress module in `src/evalforge_maestro/_locality.py` (importing only `_canonical`, `exceptions`, `types`, and stdlib)
- [ ] T005 Refactor `src/evalforge_maestro/judges/security.py` to delegate `is_loopback_host`, `validate_local_only_target`, `ensure_airgap_cost_map`, `is_remote_judge_endpoint`, and `validate_pii_egress` cleanly to `src/evalforge_maestro/_locality.py` while keeping all existing judge security symbols unchanged
- [ ] T006 Verify existing judge security tests pass cleanly after refactor in `tests/unit/test_judge_security.py`
- [ ] T007 Extend AST boundary rules and cold-start checks in `tests/test_library_purity.py` to forbid top-level `numpy`, `litellm`, `scipy`, `docpipe_maestro`, `cli`, `tomllib`, and `dotenv` in `src/evalforge_maestro/embeddings/`, forbid `metrics/`, `regression/`, `types.py`, `exceptions.py`, `_canonical.py`, and `reporting/` from importing `embeddings/`, and forbid `_locality.py` from importing domain subpackages

**Checkpoint**: Foundation ready — user story implementation (`US1` MVP and `US2`) can now proceed cleanly in parallel or sequence.

---

## Phase 3: User Story 1 — Embedding Cosine Similarity Evaluation (`[embeddings]`) (Priority: P1) 🎯 MVP

**Goal**: Deliver `EmbeddingSimilarityMetric` (`embedding_similarity`) and `ContextEmbeddingSimilarityMetric` (`context_embedding_similarity`) behind the lazy `[embeddings]` extra with deterministic SHA-256 `--mock` vectors, clamped `[0.0, 1.0]` cosine similarity, fail-fast `MissingExtraError`, shared pre-network `--local-only`/`--block-pii` checks, `embedding_config_fingerprint` provenance tracking, and decoupled diagnostic classification (`Q4`, `Q5`).

**Independent Test**: Run `pytest tests/unit/test_embedding_metrics.py tests/unit/test_embedding_provider.py tests/contract/test_m7_schemas.py` verifying fail-fast `MissingExtraError` without `[embeddings]`, deterministic `--mock` vector hashing & `[0.0, 1.0]` clamping, edge cases (`NOT_APPLICABLE`, blank output, zero-norm/mismatched/`NaN` -> `INCONCLUSIVE`), pre-network `--local-only`/`--block-pii` blocking, `Orchestrator.arun` end-to-end execution, and `reporting/builder.py` decoupled diagnostics.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T008 [P] [US1] Write unit and `MissingExtraError` tests (covering fail-fast check on `--mock` and missing ground truth, clamped `[0.0, 1.0]` cosine scoring, `max`/`mean` chunk aggregation, blank outputs, zero-norm/`NaN`/dimension-mismatch `INCONCLUSIVE`, and `@pytest.mark.gate_determinism`) in `tests/unit/test_embedding_metrics.py`
- [ ] T009 [P] [US1] Write provider unit tests (covering lazy `numpy` and `litellm` imports, `Mock` vs `embed_fn` vs `litellm.aembedding`, bounded retries, `local_only` loopback enforcement, air-gap cost map env var, and `--block-pii` egress blocking) in `tests/unit/test_embedding_provider.py`
- [ ] T010 [P] [US1] Write embedding schema & backwards-compatibility contract tests (validating `EmbeddingConfig` bounds/redaction/fingerprint, `ResolvedEmbeddingSettings`, `DriftCategory.EMBEDDING_CONFIG`, and historical `1.0` `RunRecord` loading) in `tests/contract/test_m7_schemas.py`

### Implementation for User Story 1

- [ ] T011 [US1] Define `EmbeddingAggregation`, `EmbeddingConfig` (`EmbeddingConfig.schema_version`, `EmbeddingConfig.model`, `EmbeddingConfig.api_base`, `EmbeddingConfig.pass_threshold`, `EmbeddingConfig.aggregation`, `EmbeddingConfig.max_retries`, `EmbeddingConfig.retry_backoff_seconds`, `EmbeddingConfig.timeout_seconds`, `EmbeddingConfig.max_input_chars`, `EmbeddingConfig.local_only`, `EmbeddingConfig.mock_mode`, `EmbeddingConfig.extra_params`, `EmbeddingConfig.redacted_dict()`, `EmbeddingConfig.fingerprint`), `ResolvedEmbeddingSettings` (`ResolvedEmbeddingSettings.model`, `ResolvedEmbeddingSettings.api_base`, `ResolvedEmbeddingSettings.api_key_configured`, `ResolvedEmbeddingSettings.pass_threshold`, `ResolvedEmbeddingSettings.aggregation`, `ResolvedEmbeddingSettings.max_retries`, `ResolvedEmbeddingSettings.retry_backoff_seconds`, `ResolvedEmbeddingSettings.timeout_seconds`, `ResolvedEmbeddingSettings.max_input_chars`, `ResolvedEmbeddingSettings.mock_mode`, `ResolvedEmbeddingSettings.local_only`), `DriftCategory.EMBEDDING_CONFIG`, `RunRecord.embedding_config_fingerprint`, `RunManifestEntry.embedding_config_fingerprint`, `OrchestratorConfig.embedding_config_fingerprint`, and `BaselineEntry.embedding_config_fingerprint` in `src/evalforge_maestro/types.py` per [data-model.md](data-model.md)
- [ ] T012 [P] [US1] Implement deterministic SHA-256 word + character-trigram feature hashing mock vector generator (`generate_mock_embedding`, `embed_texts_mock`, including raw stripped-string fallback for non-blank punctuation-only text so only blank/invalid live vectors hit zero-norm) in `src/evalforge_maestro/embeddings/mock.py` (resolving `numpy` lazily via provider/caller without touching `sys.modules["litellm"]`)
- [ ] T013 [P] [US1] Implement lazy `_resolve_numpy()`, `_resolve_litellm()`, pre-provider `max_input_chars` truncation helper, `clamped_cosine_similarity(...)`, `invoke_embedding_provider(...)` (with pre-network `_locality` validation, retry backoff, non-finite/zero-norm/dimension checks), and `EmbeddingFn` type alias in `src/evalforge_maestro/embeddings/provider.py`
- [ ] T014 [US1] Implement `EmbeddingSimilarityMetric` (`embedding_similarity`, `metric_version="1.0.0"`) and `ContextEmbeddingSimilarityMetric` (`context_embedding_similarity`, `metric_version="1.0.0"`) implementing `Metric`, `AsyncBatchMetric`, `_resolve_numpy()` fail-fast first check (`Q5`), pre-provider `max_input_chars` capping, PII egress guard on remote payloads, deduplicated text batching, and formal `MetricMetadata` in `src/evalforge_maestro/embeddings/metrics.py` (depends on T011, T012, T013)
- [ ] T015 [P] [US1] Export `EmbeddingSimilarityMetric`, `ContextEmbeddingSimilarityMetric`, and `EmbeddingFn` cleanly in `src/evalforge_maestro/embeddings/__init__.py`
- [ ] T016 [US1] Propagate `embedding_config_fingerprint` cleanly from `EmbeddingConfig`-bearing metrics and config through `EvaluationOrchestrator.arun` in `src/evalforge_maestro/execution/orchestrator.py` and `LocalRunStore.pin_baseline` in `src/evalforge_maestro/storage/local.py` (verify `RunManifestEntry.from_run_record` picks up `RunRecord.embedding_config_fingerprint`)
- [ ] T017 [P] [US1] Add `DriftCategory.EMBEDDING_CONFIG` comparison check in `_pair_provenance_drift` (handling `None == None` with zero drift for historical runs) in `src/evalforge_maestro/regression/drift.py`
- [ ] T018 [P] [US1] Register `"embedding_similarity"` in `_ANSWER_SURFACE_METRIC_IDS` and `"context_embedding_similarity"` alongside `"groundedness"` in `_ANSWER_OR_GROUNDING_METRIC_IDS` and `retrieval_or_grounding_fail` inside `detect_decoupled_evidence` per Clarification `Q4` in `src/evalforge_maestro/reporting/builder.py`
- [ ] T019 [US1] Add subprocess cold-start/missing-extra purity tests in `tests/test_library_purity.py` asserting `numpy` and `litellm` remain absent on cold `import evalforge_maestro` and `--help`, unconditionally verifying fail-fast `MissingExtraError` when `importlib.util.find_spec("numpy") is None`, and asserting `litellm` remains absent during offline `--mock` embedding evaluation when `find_spec("numpy") is not None`

**Checkpoint**: User Story 1 MVP complete — run `pytest tests/unit/test_embedding_metrics.py tests/unit/test_embedding_provider.py tests/contract/test_m7_schemas.py tests/test_library_purity.py`.

---

## Phase 4: User Story 2 — Multi-Run & Distributional Regression Comparisons (Priority: P1)

**Goal**: Provide pure-stdlib Student's $t$ statistical inference (`paired_t_case`, `welch_t_run`, `one_sample_t_run`), enrich pairwise `compare_runs` with paired case confidence intervals and significance classifications, implement `compare_run_cohorts` & `build_pooled_cohort_run` (`Q3`), detect intra-/cross-cohort drift (`detect_cohort_drift`), and render statistical CIs and cohorts cleanly in Markdown reports.

**Independent Test**: Run `pytest tests/unit/test_statistical_compare.py tests/unit/test_reporting.py` verifying analytical Student's $t$ accuracy vs exact references (`df=1,2,10,100`), zero-variance equal/non-zero constant shift edge handling, insufficient-sample & unmatched-case handling, multi-run `welch_t_run` + `one_sample_t_run` + secondary `case_statistics` (`paired_t_case`), intra-cohort drift flags, and legacy `1.0` `RunComparisonReport` backward compatibility.

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T020 [P] [US2] Write comprehensive unit tests covering regularized incomplete beta / Student's $t$ quantiles, `paired_t_case`, `welch_t_run`, `one_sample_t_run`, zero-variance (`delta=0` and constant non-zero shift), `insufficient_data` (<`min_statistical_samples`), unmatched/excluded `None` case pairs, `compare_run_cohorts` (`1vM`, `Kv1`, `KvM`), `build_pooled_cohort_run`, and `detect_cohort_drift` in `tests/unit/test_statistical_compare.py`
- [ ] T021 [US2] Extend schema contract tests in `tests/contract/test_m7_schemas.py` (depends on T010) verifying bounded constraints and legacy JSON deserialization for `StatisticalSummary`, `RunCohortSummary`, extended `MetricComparison`, extended `RunComparisonReport`, and `QualityGatePolicy`
- [ ] T022 [P] [US2] Add Three-Way Markdown rendering unit tests verifying `ci_low`/`ci_high`, `baseline_std`/`candidate_std`, `p_value`, `significance`, cohort run summary headers, and pooled repeat metric tables in `tests/unit/test_reporting.py`

### Implementation for User Story 2

- [ ] T023 [US2] Define `SignificanceStatus` (`SIGNIFICANT_IMPROVEMENT`, `SIGNIFICANT_REGRESSION`, `NOT_SIGNIFICANT`, `INSUFFICIENT_DATA`), `StatisticalMethod` (`PAIRED_T_CASE`, `WELCH_T_RUN`, `ONE_SAMPLE_T_RUN`), `StatisticalSummary` (`StatisticalSummary.method`, `StatisticalSummary.confidence_level`, `StatisticalSummary.sample_size`, `StatisticalSummary.baseline_sample_size`, `StatisticalSummary.candidate_sample_size`, `StatisticalSummary.excluded_pair_count`, `StatisticalSummary.mean_delta`, `StatisticalSummary.delta_std`, `StatisticalSummary.standard_error`, `StatisticalSummary.baseline_std`, `StatisticalSummary.candidate_std`, `StatisticalSummary.ci_low`, `StatisticalSummary.ci_high`, `StatisticalSummary.p_value`, `StatisticalSummary.effect_size`, `StatisticalSummary.degrees_of_freedom`, `StatisticalSummary.significance`, `StatisticalSummary.statistically_significant`, `StatisticalSummary.explanation`), `RunCohortSummary` (`RunCohortSummary.baseline_run_ids`, `RunCohortSummary.candidate_run_ids`, `RunCohortSummary.baseline_run_count`, `RunCohortSummary.candidate_run_count`, `RunCohortSummary.baseline_names`), `MetricComparison.statistics`, `MetricComparison.case_statistics`, `RunComparisonReport.cohort`, `QualityGatePolicy.confidence_level`, and `QualityGatePolicy.min_statistical_samples` in `src/evalforge_maestro/types.py` per [data-model.md](data-model.md)
- [ ] T024 [P] [US2] Implement pure-stdlib Student's $t$ CDF/quantile engine (regularized incomplete beta `math.lgamma` + symmetry-guarded Lentz continued fraction + bisection critical value), `compute_paired_case_statistics`, `compute_welch_run_statistics` (`sample_size = min(K, M)` requiring both cohorts `>= min_statistical_samples`), and `compute_one_sample_run_statistics` (`sample_size = repeated_count >= min_statistical_samples`) in `src/evalforge_maestro/regression/stats.py`
- [ ] T025 [P] [US2] Implement `detect_cohort_drift(baseline_runs, candidate_runs)` checking intra-cohort and cross-cohort consistency (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`, `embedding_config_fingerprint`, `dataset_capped`, case set mismatches) in `src/evalforge_maestro/regression/drift.py`
- [ ] T026 [US2] Update `compare_runs` (retaining exact existing signature) to compute `MetricComparison.statistics` (`paired_t_case`), and implement `build_pooled_cohort_run(runs)` (preserving `run_id = runs[-1].run_id`) plus `compare_run_cohorts(baseline_runs, candidate_runs, *, baseline_name=None, policy=None)` (primary `welch_t_run` checking `min(K, M) >= min_statistical_samples` / `one_sample_t_run` / `paired_t_case` fallback + secondary `case_statistics` per Clarification `Q3`) in `src/evalforge_maestro/regression/compare.py` (depends on T023, T024, T025)
- [ ] T027 [P] [US2] Export `compare_run_cohorts` and `build_pooled_cohort_run` in `src/evalforge_maestro/regression/__init__.py`
- [ ] T028 [P] [US2] Update Markdown comparison renderer in `src/evalforge_maestro/reporting/markdown.py` to render cohort metadata (`RunCohortSummary`), confidence intervals (`ci_low`–`ci_high`), sample dispersion (`baseline_std` / `candidate_std`), `p_value`, and `significance` cleanly while staying compatible when `statistics` is `None`

**Checkpoint**: User Stories 1 and 2 are both functional and independently testable.

---

## Phase 5: User Story 3 — Repeatable Runs, CLI/Config Ergonomics & Quality Gate Statistical Awareness (Priority: P2)

**Goal**: Wire `[embedding]`, `--embedding-*`, `--repeats N`, multi-run `compare`, and statistical Quality Gate flags/policy cleanly through `cli/config.py`, `cli/parser.py`, `cli/targets.py`, `cli/commands.py`, and `regression/gate.py` (`Q1` any-size significant drop warning / strict FAIL + `Q2` any-repeat mandatory failure + pooled cohort floor gating at `100%` branch coverage), and pin all public SDK exports/signatures.

**Independent Test**: Run `pytest tests/unit/test_quality_gate.py tests/unit/test_cli_config.py tests/integration/test_cli_workflow.py tests/integration/test_statistical_embedding_pipeline.py tests/test_api_stability.py` verifying 100% branch coverage on `regression/gate.py`, CLI config precedence & secret masking (`embedding.api_key`), offline `--mock` embedding evaluation via CLI, `--repeats 3` mandatory/pooled gate evaluation, multi-run cohort `compare`, exit codes `0`–`4`, and backward compatibility of all existing M1–M6 workflows.

### Tests for User Story 3 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T029 [P] [US3] Extend `tests/unit/test_quality_gate.py` with tests covering **all** branches of `statistical_regression:<metric_id>` (`WARNING` on tiny significant drops `ci_high < 0` below `max_regression_drop` per `Q1`, `FAIL` when `fail_on_significant_regression=True`, `"statistical_significance"` `PASS` when none regress significantly) and `QualityGate.evaluate_cohort` (empty cohort validation error, any-repeat mandatory failure across `[run_1..run_N]`, pooled metric floor pass/fail across repeats per `Q2`)
- [ ] T030 [P] [US3] Add CLI configuration precedence, unknown-key validation, plaintext `[embedding].api_key` warning/secret-masking, `[embedding]`/`[judge]` config isolation (`Q5`), `--repeats`, and `[gate]` statistical settings tests in `tests/unit/test_cli_config.py`
- [ ] T031 [P] [US3] Write end-to-end integration tests covering CLI `run --metric embedding_similarity --mock --local-only`, `--local-only` exit code `4` on remote `--embedding-api-base`, `--block-pii` exit code `4`, `--repeats 3 --seed 10` immutable run cohort creation + any-repeat mandatory fail, multi-run `compare c1 c2 --baseline b1 --baseline-run b2`, and Markdown/JSON report validation in `tests/integration/test_statistical_embedding_pipeline.py`

### Implementation for User Story 3

- [ ] T032 [US3] Define `QualityGatePolicy.fail_on_significant_regression`, `CLIResolvedConfig.repeats`, `CLIResolvedConfig.baseline_runs`, `CLIResolvedConfig.embedding`, `ReportDocument.cohort_run_ids`, and `ReportDocument.cohort_aggregates` in `src/evalforge_maestro/types.py` per [data-model.md](data-model.md)
- [ ] T033 [US3] Implement statistical regression significance gate check (`Q1`: `WARNING` by default or `FAIL` when `fail_on_significant_regression=True` on any `mc.statistics.significance == SignificanceStatus.SIGNIFICANT_REGRESSION`, plus `PASS` on `"statistical_significance"`) and `QualityGate.evaluate_cohort(runs, *, comparison=None, trend=None)` (`Q2`: validating non-empty `runs` and matching `comparison.cohort.candidate_run_ids` / `runs[-1].run_id`, failing `"mandatory_cases"` if *any* repeat failed a mandatory case, and evaluating pooled cohort metric floors/rates via `build_pooled_cohort_run`) in `src/evalforge_maestro/regression/gate.py` preserving `100%` branch coverage and `QualityGate.evaluate`'s exact pinned signature (depends on T026, T032)
- [ ] T034 [P] [US3] Extend Markdown run evaluation renderer in `src/evalforge_maestro/reporting/markdown.py` to display `ReportDocument.cohort_run_ids` and `ReportDocument.cohort_aggregates` clearly when repeated trials (`repeats >= 2`) ran
- [ ] T035 [US3] Extend CLI configuration resolution, TOML schemas (`_TomlRunSection.repeats`, `_TomlEmbeddingSection` including `max_input_chars`, `_TomlGateSection` statistical fields), env vars (`EVALFORGE_EMBEDDING_*`, `EVALFORGE_REPEATS`, `EVALFORGE_CONFIDENCE_LEVEL`, `EVALFORGE_MIN_STATISTICAL_SAMPLES`, `EVALFORGE_FAIL_ON_SIGNIFICANT_REGRESSION`), and secret masking (`embedding.api_key` -> `raw_embedding_api_key` / `api_key_configured`) with strict isolation from `[judge]` in `src/evalforge_maestro/cli/config.py`
- [ ] T036 [P] [US3] Extend CLI parser (`run`: `--embedding-*`, `--embedding-max-input-chars`, `--repeats`, `--baseline-run`, `--confidence-level`, `--min-statistical-samples`, `--fail-on-significant-regression`; `compare`: multi-positional `candidate_run_ids` with `nargs="+"`, `--baseline-run`, `--confidence-level`, `--min-statistical-samples`, `--fail-on-significant-regression`) keeping `evalforge-maestro --help` cold-start pure in `src/evalforge_maestro/cli/parser.py`
- [ ] T037 [US3] Extend metric builder (`_DIRECT` / `_EMBEDDING` factory for `embedding_similarity` and `context_embedding_similarity`, parameter validation, defaulting `max_input_chars` cleanly) and `preflight_run_security` (early `[embeddings]` / `--local-only` / `--block-pii` remote embedding checks + fail-fast exit codes `3` / `4`) in `src/evalforge_maestro/cli/targets.py` (depends on T014, T035)
- [ ] T038 [US3] Update CLI command handlers `_handle_run` (`--repeats N` immutable run suffixing `<run_id>-r01..rNN`, deterministic `seed + i` progression, merging `resolved.baseline` + `resolved.baseline_runs`, `compare_run_cohorts`, `QualityGate.evaluate_cohort`, setting `ReportDocument.evaluation`, `ReportDocument.comparison`, `ReportDocument.cohort_run_ids`, and `ReportDocument.cohort_aggregates` per [data-model.md](data-model.md)) and `_handle_compare` (merging `resolved.baseline` + `resolved.baseline_runs` allowing `--baseline-run` without singular `--baseline`, backward-compatible 1v1 `compare_runs` vs multi-run `compare_run_cohorts` + `evaluate_cohort`) in `src/evalforge_maestro/cli/commands.py` (depends on T033, T034, T035, T036, T037)
- [ ] T039 [US3] Export all new Feature `007` public classes, models, enums, and functions (`EmbeddingAggregation`, `EmbeddingConfig`, `ResolvedEmbeddingSettings`, `SignificanceStatus`, `StatisticalMethod`, `StatisticalSummary`, `RunCohortSummary`, `EmbeddingSimilarityMetric`, `ContextEmbeddingSimilarityMetric`, `compare_run_cohorts`, `build_pooled_cohort_run`) in `src/evalforge_maestro/__init__.py`
- [ ] T040 [US3] Update `tests/test_api_stability.py` to pin every new Feature `007` export, constructor signature (`EmbeddingSimilarityMetric`, `ContextEmbeddingSimilarityMetric`, `compare_run_cohorts`, `build_pooled_cohort_run`, `QualityGate.evaluate_cohort`), and extended model field set while confirming zero breaking changes on prior M1–M6 APIs (depends on T039)

**Checkpoint**: All 3 user stories are complete, CLI/SDK wired, and release contracts pinned.

---

## Phase 6: Polish, CI Matrix & Cross-Cutting Verification

**Purpose**: Ensure CI tests both minimal-core `--no-dev` `MissingExtraError` guards and live `[embeddings]` compatibility across OSes, document user-facing usage cleanly, and verify all release quality gates.

- [ ] T041 [P] Add `optional-embeddings-compat` CI job (running `uv sync --frozen --extra dev --extra embeddings`, `tests/test_library_purity.py`, `tests/unit/test_embedding_*.py`, and lazy-import checks) and extend the `cross-os-and-packaging` minimal clean-wheel check (`--no-dev`) to verify `EmbeddingSimilarityMetric` raises `MissingExtraError` referencing `embeddings` in `.github/workflows/ci.yml`
- [ ] T042 [P] Update installation, quickstart examples, and Feature `007` milestone notes (`pip install "evalforge-maestro[embeddings]"`, `--repeats`, statistical `compare`) in `README.md`
- [ ] T043 [P] Mark completed pre-M6 / M6 items and reflect Feature `007` implementation status accurately in `docs/future-features.md`
- [ ] T044 Validate `uv run pytest --strict-markers -W error --cov=evalforge_maestro --cov-branch --cov-fail-under=85`, `uv run pytest --strict-markers -W error --cov=evalforge_maestro.metrics --cov-branch --cov-fail-under=100 tests/unit/test_metrics.py tests/unit/test_ir_metrics.py tests/unit/test_agent_metrics.py tests/contract/test_metric_formulas.py`, `uv run pytest --strict-markers -W error --cov=evalforge_maestro.regression.gate --cov-branch --cov-fail-under=100 tests/unit/test_quality_gate.py`, and `-m "gate_determinism or gate_immutability"` across the suite
- [ ] T045 Validate static analysis, security lint, dependency audit, lockfile, and packaging (`uv lock --check && uv run ruff format --check . && uv run ruff check . && uv run ruff check --select S src/ && uv run mypy --strict src tests && uv run pip-audit --skip-editable && uv build && uv run twine check --strict dist/*`) plus runnable validation scenarios from [quickstart.md](quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001–T003)**: Starts immediately on branch `007-statistical-embedding-metrics`.
- **Foundational (Phase 2, T004–T007)**: Depends on Phase 1; BLOCKS all user stories (`_locality.py` refactor & AST boundary checks).
- **User Story 1 (Phase 3, T008–T019 — P1 🎯 MVP)**: Depends on Foundational (Phase 2) only; completely independent of US2.
- **User Story 2 (Phase 4, T020–T028 — P1)**: Depends on Foundational (Phase 2) (`types.py` updates should run sequentially with US1's `T011` or immediately after if single developer, while `regression/stats.py`, `regression/drift.py`, and tests parallelize freely).
- **User Story 3 (Phase 5, T029–T040 — P2)**: Depends on US1 (`embeddings/`) and US2 (`regression/stats.py`, `compare_run_cohorts`, `build_pooled_cohort_run`).
- **Polish & CI Verification (Phase 6, T041–T045)**: Depends on US1, US2, and US3 completion.

### Within Each User Story

1. Write tests (`T008`–`T010`, `T020`–`T022`, `T029`–`T031`) FIRST and observe failing red state before writing implementation.
2. Add canonical schemas in `src/evalforge_maestro/types.py` referencing `data-model.md`.
3. Implement core library logic (`embeddings/`, `regression/`) before orchestrator/storage/reporting/CLI integration.
4. Keep `src/evalforge_maestro/metrics/` completely untouched by optional `numpy`/`litellm` imports so its standalone `100%` CI gate never breaks.

### Parallel Opportunities

- **Within Phase 1 & 2**: `T003` can run parallel to `T001`–`T002`; `T007` aligns AST checks cleanly once `T004`–`T005` land.
- **Within US1**: All test tasks `T008`, `T009`, `T010` run in parallel; `T012` (`mock.py`) and `T013` (`provider.py`) run in parallel; `T017` (`drift.py`) and `T018` (`reporting/builder.py`) run in parallel once `T011` schemas exist.
- **Within US2**: `T020` and `T022` tests run in parallel (`T021` extends `tests/contract/test_m7_schemas.py` after `T010`); `T024` (`regression/stats.py`) and `T025` (`regression/drift.py`) run in parallel once `T023` schemas exist; `T027` and `T028` run in parallel after `T026`.
- **Within US3**: `T029`, `T030`, `T031` tests run in parallel; `T034` (`reporting/markdown.py`) and `T036` (`cli/parser.py`) can progress cleanly alongside `T035` (`cli/config.py`) before final `T038` command wiring.
- **Within Phase 6**: `T041`, `T042`, `T043` run in parallel prior to final gate suite `T044`–`T045`.

---

## Parallel Example: User Story 1 (MVP)

```bash
# Write all US1 tests in parallel (TDD red phase):
Task: "T008 [P] [US1] Write unit and MissingExtraError tests in tests/unit/test_embedding_metrics.py"
Task: "T009 [P] [US1] Write provider unit tests in tests/unit/test_embedding_provider.py"
Task: "T010 [P] [US1] Write embedding schema tests in tests/contract/test_m7_schemas.py"

# After T011 schemas land, implement mock + provider in parallel:
Task: "T012 [P] [US1] Implement SHA-256 mock vector generator in src/evalforge_maestro/embeddings/mock.py"
Task: "T013 [P] [US1] Implement lazy numpy/litellm provider and clamped cosine math in src/evalforge_maestro/embeddings/provider.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup: `[embeddings]` extra & lockfile) and Phase 2 (Foundational: `_locality.py` + AST purity guards).
2. Complete Phase 3 (US1: `EmbeddingSimilarityMetric`, `ContextEmbeddingSimilarityMetric`, fail-fast `MissingExtraError`, deterministic `--mock`, decoupled diagnostics, `embedding_config_fingerprint`).
3. **STOP and VALIDATE**: Confirm US1 passes all unit, contract, purity, cold-start, and determinism tests independently before merging into statistical inference & CLI enhancements.

### Incremental Delivery

1. Phase 1 + Phase 2 -> Shared security/purity baseline green.
2. Phase 3 (`US1`) -> Semantic embedding similarity SDK & orchestrator integration tested independently (**MVP**).
3. Phase 4 (`US2`) -> Pure-stdlib statistical CIs, Welch/one-sample cohorts, drift & Markdown tables tested independently.
4. Phase 5 (`US3`) -> `QualityGate` 100%-branch significance/cohort gating, `--repeats N`, TOML/ENV/CLI parity, API stability pinned.
5. Phase 6 (`Polish`) -> CI minimal-core + `[embeddings]` matrix, docs, quickstart smoke validation, full security/coverage/audit pass.
