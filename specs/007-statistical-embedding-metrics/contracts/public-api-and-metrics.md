# Contract Specification: Public Python SDK, Embedding Metrics & Statistical Engine

**Feature**: `007-statistical-embedding-metrics`  
**Contract Scope**: Top-level exports (`evalforge_maestro`), metric contracts, statistical inference contracts, and backward-compatible API stability.

## 1. Public Exports Added to `evalforge_maestro.__all__`

All existing exports and signatures in `tests/test_api_stability.py` remain unchanged. Feature `007` adds:

- Models / Enums (`evalforge_maestro.types`):
  - `EmbeddingAggregation`
  - `EmbeddingConfig`
  - `ResolvedEmbeddingSettings`
  - `SignificanceStatus`
  - `StatisticalMethod`
  - `StatisticalSummary`
  - `RunCohortSummary`
- Embedding Metrics (`evalforge_maestro.embeddings`):
  - `EmbeddingSimilarityMetric`
  - `ContextEmbeddingSimilarityMetric`
- Statistical Comparison Function (`evalforge_maestro.regression`):
  - `compare_run_cohorts`

---

## 2. Embedding Metric Contracts (`evalforge_maestro.embeddings`)

Both classes satisfy `Metric` (`evaluate(case, execution)`) and `AsyncBatchMetric` (`aevaluate`, `aevaluate_batch(items, max_concurrency=...)`).

### 2.1 `EmbeddingSimilarityMetric`
- **`metric_id`**: `"embedding_similarity"`
- **`metric_version`**: `"1.0.0"`
- **What it measures**: Cosine similarity between dense embedding vectors of `ExecutionResult.output` and `EvaluationCase.reference`, clamped to `[0.0, 1.0]` via `max(0.0, cos(u, v))`.
- **Required fields**:
  - `EvaluationCase`: `reference`
  - `ExecutionResult`: `output`
- **Known limitations**: Dense embedding cosine similarity captures topical/paraphrase overlap but does not verify discrete numerical facts, strict JSON schemas, or temporal/negation nuances reliably.
- **Constructor**:
  ```python
  EmbeddingSimilarityMetric(
      *,
      config: EmbeddingConfig | None = None,
      api_key: str | None = None,
      embed_fn: EmbeddingFn | None = None,
  )
  ```
- **Edge & Error Rules**:
  1. Lazy `[embeddings]` check (`_resolve_numpy()`): raises `MissingExtraError(extra="embeddings", package="numpy")` when `numpy` is not installed (unless upstream error? Check BEFORE computing vectors; raises immediately on invocation if `numpy` is missing!).
  2. `execution.errors` non-empty -> `status = INCONCLUSIVE`, `score = None`, `explanation = scrub_secret_text(...)`.
  3. `case.reference is None` or blank (`not case.reference.strip()`) -> `status = NOT_APPLICABLE`, `score = None`.
  4. `execution.output is None` or blank (`not execution.output.strip()`) -> `status = FAIL` (`score = 0.0` if `threshold > 0`, else `PASS`), without unnecessary remote embedding call.
  5. Zero-norm / `NaN` / `Inf` / mismatched vector dimension / failed retries -> `status = INCONCLUSIVE`, `score = None`.
  6. Clamped score: `score = round_score(max(0.0, min(1.0, cos_sim)))`. `status = PASS` iff `score + FLOAT_EPSILON >= threshold`, else `FAIL`. Threshold resolves as `case.criteria.metric_thresholds.get(metric_id, case.criteria.pass_threshold or config.pass_threshold)`.

### 2.2 `ContextEmbeddingSimilarityMetric`
- **`metric_id`**: `"context_embedding_similarity"`
- **`metric_version`**: `"1.0.0"`
- **What it measures**: Clamped cosine similarity (`max(0.0, cos(u, v))`) between `ExecutionResult.output` and non-blank `ExecutionResult.retrieved_chunks`, aggregated via `EmbeddingConfig.aggregation` (`"max"` default or `"mean"`).
- **Required fields**:
  - `EvaluationCase`: *(none)*
  - `ExecutionResult`: `output`, `retrieved_chunks`
- **Known limitations**: Embedding similarity between answer and retrieved context measures topical overlap rather than fine-grained logical entailment or factual attribution; pair with `groundedness` for high-assurance citation checking.
- **Edge & Error Rules**: Same lazy `[embeddings]`, error, blank-output, zero-norm, and batching contracts as `EmbeddingSimilarityMetric`; returns `NOT_APPLICABLE` (`score = None`) when `retrieved_chunks` contains no non-blank chunk text.

### 2.3 Reporting Decoupling Diagnostic Classification
- `reporting/builder.py` recognizes:
  - `embedding_similarity` in `_ANSWER_SURFACE_METRIC_IDS`
  - `context_embedding_similarity` as a grounding/context-alignment metric alongside `groundedness` inside `_ANSWER_OR_GROUNDING_METRIC_IDS` and `retrieval_or_grounding_fail`.

---

## 3. Statistical Comparison Contracts (`evalforge_maestro.regression`)

### 3.1 `compare_runs(baseline, candidate, *, baseline_name=None, policy=None) -> RunComparisonReport`
- Signature remains 100% compatible with M3 (`tests/test_api_stability.py`).
- Populates `MetricComparison.statistics` with `StatisticalSummary(method="paired_t_case", ...)`:
  - Uses aligned valid `(base_score, cand_score)` case pairs present in both runs where neither is `None`.
  - Records `excluded_pair_count` for unmatched or `None`-scored aligned cases.
  - Applies `policy.confidence_level` and `policy.min_statistical_samples` (`>= 2`).

### 3.2 `compare_run_cohorts(baseline_runs, candidate_runs, *, baseline_name=None, policy=None) -> RunComparisonReport`
- Validates `baseline_runs` and `candidate_runs` are non-empty (`ConfigurationError` on empty sequence).
- Delegates to `compare_runs` when `len(baseline_runs) == 1 and len(candidate_runs) == 1`, setting `cohort = None`.
- When `max(len(baseline_runs), len(candidate_runs)) >= 2`:
  - Sets `RunComparisonReport.cohort = RunCohortSummary(...)`.
  - Uses `baseline_runs[-1]` and `candidate_runs[-1]` as representative `baseline_run_id` and `candidate_run_id`.
  - Computes pooled run-level mean scores, baseline/candidate SDs, and `MetricComparison.statistics`:
    - `welch_t_run` if both cohorts have `>= 2` valid run means for the metric (`insufficient_data` if total runs below `policy.min_statistical_samples`).
    - `one_sample_t_run` if one side has `1` run and the other has `>= 2` valid run means.
    - `paired_t_case` fallback if neither side has `>= 2` run means for that metric.
  - Populates `MetricComparison.case_statistics` with `paired_t_case` computed over aligned per-case cohort means across trials!
  - Runs `detect_cohort_drift` verifying intra-cohort and cross-cohort consistency (`dataset_fingerprint`, `metric_version`, `judge_config_fingerprint`).

### 3.3 `QualityGate.evaluate(...)`
- Evaluates `mc.statistics.significance == SignificanceStatus.SIGNIFICANT_REGRESSION` across `comparison.metric_comparisons`:
  - When found -> emits rule `"statistical_regression:<metric_id>"` with `GateDecision.FAIL` if `policy.fail_on_significant_regression` else `GateDecision.WARNING`.
  - When none found among metrics having `mc.statistics` (`!= insufficient_data`) or when `comparison` has statistical summaries -> emits `"statistical_significance"` (`GateDecision.PASS`).
  - Must maintain **100%** branch coverage in `tests/unit/test_quality_gate.py`.
