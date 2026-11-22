# Statistical Methodology & Interpretation Guide

EvalForge Maestro computes pure-stdlib inferential statistics alongside magnitude deltas inside [`evalforge_maestro.regression.stats`](../src/evalforge_maestro/regression/stats.py), attaching `StatisticalSummary` metadata to `MetricComparison` records during pairwise (`compare_runs`) and multi-run cohort (`compare_run_cohorts`) comparisons.

This guide documents the exact statistical formulas, underlying assumptions, edge-case semantics, and quality-gate interactions so engineers can interpret `$p$`-values and confidence intervals accurately.

---

## 1. Methods Selected Automatically (`StatisticalMethod`)

| Method (`StatisticalMethod`) | Trigger Context | Sampling Unit & Degrees of Freedom (`df`) | Dispersion Input |
| --- | --- | --- | --- |
| **`paired_t_case`** | `compare_runs(baseline, candidate)` and cohort `case_statistics` ([`compare.py`](../src/evalforge_maestro/regression/compare.py#L140-L146), [`L454-L460`](../src/evalforge_maestro/regression/compare.py#L454-L460)) | Matched applicable `case_id` score differences $d_i = c_i - b_i$; $\text{df} = n - 1$ | Sample standard deviation `delta_std` of paired per-case differences; unmatched or non-applicable pairs tracked in `excluded_pair_count`. |
| **`welch_t_run`** | `compare_run_cohorts` when baseline has $k \ge 2$ runs and candidate has $m \ge 2$ runs ([`compare.py#L474-L480`](../src/evalforge_maestro/regression/compare.py#L474-L480)) | Per-run aggregate `mean_score` across $k$ baseline and $m$ candidate trials; Welch–Satterthwaite `df` | Unequal-variance `baseline_std` and `candidate_std` across repeated runs; reported `sample_size = min(k, m)` with full counts in `baseline_sample_size` / `candidate_sample_size`. |
| **`one_sample_t_run`** | `compare_run_cohorts` when one side is a single scalar run (`1`) and the other has $N \ge 2$ runs ([`compare.py#L481-L487`](../src/evalforge_maestro/regression/compare.py#L481-L487)) | Multi-run trial `mean_score` cohort tested against the fixed scalar single-run mean; $\text{df} = N - 1$ | Sample SD of whichever cohort side has $N \ge 2$ runs. |

All cumulative probabilities use continued-fraction regularized incomplete beta evaluation (`student_t_two_tailed_p`, `student_t_critical`) without `scipy` or `numpy`. Confidence intervals (`ci_low`, `ci_high`) are clamped to `[-1.0, 1.0]` to reflect valid metric-delta bounds.

---

## 2. Distributional Assumptions & Small-$n$ Caveats

1. **Bounded `[0.0, 1.0]` & Binary Metric Non-Normality**:
   - EvalForge metric scores live strictly in `[0.0, 1.0]`. Binary pass/fail metrics (`exact_match`, `normalized_match`, `json_schema_validation`, strict policy metrics) follow Bernoulli/binomial distributions and frequently cluster near `0.0` or `1.0`.
   - Student's $t$ / Welch's $t$ rely on approximate normality of sample means (Central Limit Theorem) or differences. When score distributions are heavily skewed or bimodal at small sample sizes, nominal `95%` coverage (`confidence_level = 0.95`) can over- or under-cover.
2. **Small Sample Counts (`min_statistical_samples = 2`)**:
   - [`QualityGatePolicy.min_statistical_samples`](../src/evalforge_maestro/types.py#L1315) defaults to `2` (enforced `>= 2`). At $n = 2$ ($\text{df} = 1$), two-sided $t^*_{0.975} \approx 12.71$, producing extremely wide confidence intervals and low statistical power.
   - For stochastic runs (`--repeats`) or noisy LLM-as-a-judge cohorts, prefer `n >= 5` trials or larger golden datasets before relying on significance tests for automated merge blocking. If `sample_size < max(2, min_statistical_samples)`, inference stops safely and emits `SignificanceStatus.INSUFFICIENT_DATA` (`p_value = None`).
3. **Observation Independence**:
   - `welch_t_run` treats each `RunRecord` (`--repeats`) as an independent stochastic trial. If repeated runs share fixed deterministic outputs, cached judge responses, or identical random seeds (`--seed`), trial-to-trial variance vanishes and reflects determinism rather than population uncertainty.
   - `paired_t_case` treats evaluation cases as independent sampling units; correlated case clusters (e.g., multiple paraphrases from the same document) can underestimate standard errors.

---

## 3. Zero-Variance (`p = 0.0`) Semantics

In [`_finalize_inference`](../src/evalforge_maestro/regression/stats.py#L170-L193), if `standard_error <= FLOAT_EPSILON` (`1e-9`):

- **Zero mean delta** (`abs(mean_delta) <= FLOAT_EPSILON`):
  - `p_value = 1.0`, `ci_low = ci_high = mean_delta`, `significance = NOT_SIGNIFICANT`, `statistically_significant = False`.
- **Non-zero constant delta** (`abs(mean_delta) > FLOAT_EPSILON`):
  - `p_value = 0.0`, `ci_low = ci_high = mean_delta`, `effect_size = None` (division by zero SD avoided), `statistically_significant = True`, and `significance` becomes `SIGNIFICANT_IMPROVEMENT` or `SIGNIFICANT_REGRESSION` (explanation notes `"zero variance"`).

**Why & Caution**: Deterministic systems and `--mock` judges frequently shift by an identical constant across every trial (`SE = 0`). Returning `p_value = 0.0` prevents zero-division errors and faithfully records zero within-group variance. However, at tiny $n$ (e.g., `2` binary trials that both fail `0.0` vs. baseline `1.0`), `SE = 0` triggers `p_value = 0.0` immediately—never equate `p = 0.0` at `n = 2` with broad empirical generalization.

---

## 4. Multiple-Comparison Risk Across Metrics

[`compare_runs`](../src/evalforge_maestro/regression/compare.py#L115-L158) and [`compare_run_cohorts`](../src/evalforge_maestro/regression/compare.py#L430-L509) evaluate each metric independently at significance threshold $\alpha = 1 - \text{confidence\_level}$ (`0.05` by default when `confidence_level = 0.95`), **without** Bonferroni or Benjamini–Hochberg FDR correction across simultaneous metrics.

- When tracking $K$ metrics together (e.g., `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `groundedness`, `answer_relevance`), testing $K = 6$ metrics independently at $\alpha = 0.05$ raises the family-wise chance of at least one spurious `p < 0.05` hit to $1 - (1 - 0.05)^6 \approx 26.5\%$ under the global null.
- Raise `confidence_level` (e.g., `0.99`) or require practical magnitude drops alongside `p`-values when gating multi-metric suites.

---

## 5. Practical Effect Magnitude vs. Statistical Significance in `QualityGatePolicy`

Statistical significance (`p < alpha`) only measures compatibility with zero difference—it does **not** measure whether a change matters operationally:
- With `n = 2,000` cases, a negligible `-0.002` drop can yield `p < 0.01` (`SIGNIFICANT_REGRESSION`).
- With `n = 3` trials, a genuine `-0.08` regression can yield `p = 0.12` (`NOT_SIGNIFICANT`).

Inspect **`StatisticalSummary.mean_delta`**, the **`[ci_low, ci_high]`** interval, and standardized **`StatisticalSummary.effect_size`** (paired Cohen's $d_z = \bar{d} / s_d$, or cohort $d = (\bar{c} - \bar{b}) / s_{\text{pooled}}$ when SD $> 10^{-9}$) alongside [`QualityGatePolicy`](../src/evalforge_maestro/types.py#L1293-L1317) thresholds in [`gate.py`](../src/evalforge_maestro/regression/gate.py#L207-L292):

| `QualityGatePolicy` Field / CLI Flag | Default | Role in Gate Decision |
| --- | --- | --- |
| `max_regression_drop` (`--max-regression-drop`) | `0.05` | **Practical magnitude threshold**: fails (`GateDecision.FAIL` on `baseline_regression:<metric_id>`) whenever `drop > max_regression_drop`. |
| `max_metric_regression_drops` | `{}` | Per-metric practical drop overrides keyed by `metric_id`. |
| `soft_regression_warning` | `False` | Emits `GateDecision.WARNING` (`soft_regression:<metric_id>`) for small drops (`> 1e-9`) within `max_regression_drop`. |
| `confidence_level` (`--confidence-level`) | `0.95` | Sets two-tailed CI width and hypothesis threshold $\alpha = 1 - \text{confidence\_level}$. |
| `min_statistical_samples` (`--min-statistical-samples`) | `2` | Minimum sample count before emitting significance rather than `INSUFFICIENT_DATA`. |
| `fail_on_significant_regression` (`--fail-on-significant-regression`) | `False` | When `False`, `statistical_regression:<metric_id>` emits non-blocking `WARNING`; set `True` to escalate statistically significant regressions to `FAIL` (note: there is no separate `min_effect_size` filter—pair this flag with `max_regression_drop` and adequate `--repeats`). |
