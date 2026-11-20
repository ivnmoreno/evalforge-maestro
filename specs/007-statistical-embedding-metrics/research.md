# Phase 0 Research: Statistical & Embedding Similarity Metrics

**Feature**: `007-statistical-embedding-metrics`  
**Date**: 2026-11-20  
**Spec**: [`spec.md`](spec.md)

## Research Decisions

### R1 — Packaging & Module Placement for `[embeddings]` (Library Purity & Cold-Start Isolation)

- **Decision**:
  1. Add `embeddings = ["numpy>=1.26,<3", "litellm>=1.84.0"]` to `[project.optional-dependencies]` in `pyproject.toml`, keeping core runtime dependencies untouched (`pydantic`, `jsonschema`, `tomli`).
  2. Implement the embedding subsystem under a dedicated `src/evalforge_maestro/embeddings/` subpackage (`__init__.py`, `mock.py`, `provider.py`, `metrics.py`), mirroring `src/evalforge_maestro/judges/`.
  3. Extract shared pure pre-network URL locality helpers (`is_loopback_host`, `validate_local_only_url`, `is_remote_endpoint`, `ensure_airgap_cost_map`, `validate_pii_egress`) into an internal shared helper `src/evalforge_maestro/_locality.py` imported by both `judges/security.py` and `embeddings/provider.py`.
- **Rationale**:
  - `tests/test_library_purity.py` enforces two critical architectural boundaries: (a) `src/evalforge_maestro/metrics/` must never import `judges/` or other I/O subsystems, and `.github/workflows/ci.yml` enforces a standalone `100%` branch coverage gate specifically on `evalforge_maestro.metrics` via deterministic metric test files (`--extra dev` only, where `numpy` and `litellm` are absent); (b) `_HEAVY_OPTIONAL_MODULES` asserts `numpy`, `scipy`, `litellm`, and `docpipe_maestro` stay absent from `sys.modules` on cold `import evalforge_maestro` and `--help`.
  - Dedicated `embeddings/` keeps `numpy` and `litellm` lazily imported inside functions only at scoring time, shares security/PII preflight logic via `_locality.py` without cross-domain coupling between `judges` and `embeddings` or touching pure `metrics/`, and guarantees clean minimal installs remain ~11 packages.
- **Alternatives Considered**:
  - *Bundling `sentence-transformers` / `torch` in `[embeddings]`*: Rejected due to ~1–2 GB transitive dependencies, slow CI wheels, and the user-confirmed decision to keep `[embeddings]` lightweight with Ollama/remote routing + custom callables + `--mock`.
  - *Putting embedding metrics inside `src/evalforge_maestro/metrics/`*: Rejected because network/provider logic violates `metrics/` purity boundaries and conflicts with the standalone deterministic `100%` coverage gate in `.github/workflows/ci.yml`.

### R2 — Lazy Guard Semantics for `[embeddings]` vs Offline `--mock`

- **Decision**:
  - Importing `evalforge_maestro`, importing `EmbeddingSimilarityMetric` / `ContextEmbeddingSimilarityMetric`, constructing `EmbeddingConfig`, or running `evalforge-maestro --help` NEVER imports `numpy` or `litellm`.
  - Vector normalization and cosine similarity in `embeddings/provider.py` resolve `numpy` lazily via `_resolve_numpy()`, raising `MissingExtraError(extra="embeddings", package="numpy")` (`pip install 'evalforge-maestro[embeddings]'`) if `numpy` is not installed.
  - When `mock_mode=True` and `numpy` IS installed (`[embeddings]`), mock evaluation generates deterministic `np.ndarray` feature vectors offline without importing `litellm` or making network calls.
  - When `mock_mode=False` and `embed_fn is None`, live embedding retrieval validates `--local-only` pre-network and lazily imports `litellm`, raising `MissingExtraError(extra="embeddings", package="litellm")` if `litellm` is absent.
- **Rationale**:
  - Matches `spec.md` (`FR-001`, `SC-001`) and `Constitution Technical Constraints`: vector operations genuinely depend on `[embeddings]`, so executing an embedding metric without `[embeddings]` fails explicitly with installation instructions rather than silently running degraded Python loops, while `--mock` keeps `litellm` unloaded and air-gapped.
  - Under `uv sync --frozen --extra dev` (where `[embeddings]` is omitted), unit tests verify both the `MissingExtraError` branch directly and vector scoring via injected fake `numpy` module / mock provider, while a dedicated `optional-embeddings-compat` CI job runs live `[embeddings]` tests against real `numpy`.
- **Alternatives Considered**:
  - *Bypassing `numpy` completely in `--mock`*: Rejected because executing an embedding metric in a minimal core install without `[embeddings]` would mask missing-extra errors during offline smoke runs (`SC-001`).

### R3 — Deterministic `--mock` Vector Construction & Cosine Clamping

- **Decision**:
  - `generate_mock_embedding(text: str, *, dim: int = 64)` produces a deterministic `float64` unit vector using normalized word tokens (weight `1.0`) and lowercase alphanumeric character trigrams (weight `0.5`) mapped via signed `hashlib.sha256` bucket hashing (`idx = digest % dim`, sign `±1`) into a `dim=64` array followed by L2 normalization.
  - Whitespace-only or empty text produces an explicit zero-vector handled predictably: empty/absent `reference` (`embedding_similarity`) or empty `retrieved_chunks` (`context_embedding_similarity`) returns `MetricStatus.NOT_APPLICABLE` (`score=None`); blank target `output` returns `score=0.0` (`FAIL` when threshold `> 0`), matching deterministic RAG/text semantics.
  - Similarity score for vector pair $(u, v)$ is $\max(0.0, \text{round\_score}(\cos(u, v)))$ clamped strictly to $[0.0, 1.0]$. Non-finite elements (`NaN`/`Inf`), zero norms from a live/custom provider, or mismatched dimensions yield `MetricStatus.INCONCLUSIVE` (`score=None`) cleanly per case.
- **Rationale**:
  - Never relies on Python's per-process randomized `hash()`, preserving `@pytest.mark.gate_determinism` bit-for-bit across runs, OSes, and Python versions.
  - Word + character trigram projections give realistic semantic separation in `--mock` mode (paraphrases/shared vocabulary score high, orthogonal text scores low/zero) without hardcoded lookup tables.
  - Zero-clamping (`max(0.0, cos)`) matches user decision A2 and retrieval/judge intuition where unrelated text scores `0.0` instead of `0.5`.
- **Alternatives Considered**:
  - *Linear rescaling `(cos + 1) / 2`*: Rejected per user selection; maps orthogonal uncorrelated vectors to `0.5` rather than `0.0`.
  - *Single fixed constant mock score*: Rejected because tests need paraphrases and unrelated answers to rank meaningfully in `--mock` mode.

### R4 — Pure Stdlib Statistical Distribution Inference (`regression/stats.py`)

- **Decision**:
  - Implement Student's $t$ distribution math strictly using Python stdlib `math` (no `scipy` or `numpy` dependency in `regression/`):
    - Compute regularized incomplete beta $I_x(a, b)$ via `math.lgamma` and symmetry-guarded Lentz continued fraction (`max_iter=200`, `tol=1e-13`).
    - Compute exact two-tailed Student's $t$ $p$-value $p = I_{\nu / (\nu + t^2)}(\nu / 2, 1 / 2)$ for any real degrees of freedom $\nu > 0$.
    - Invert $I_x(\nu / 2, 1 / 2) = 1 - \text{confidence\_level}$ via 64-iteration monotonic bisection over $x \in (0, 1)$ to obtain exact critical value $t^* = \sqrt{\nu(1 - x) / x}$ accurate to `< 1e-11` for any `confidence_level` in `(0, 1)`.
  - Apply two principled inferential methods cleanly:
    1. **`paired_t_case`** (pairwise single-run `compare_runs`, and secondary per-case inference inside multi-run cohorts): over aligned valid case pairs $(b_i, c_i)$ ($n \ge \text{min\_statistical\_samples}$, minimum `2`), computes paired differences $d_i = c_i - b_i$, sample SD $s_d$, $\text{SE} = s_d / \sqrt{n}$, $df = n - 1$, $t = \bar{d} / \text{SE}$, two-tailed $p$-value, Cohen's $d_z = \bar{d} / s_d$, and delta CI $[\max(-1.0, \bar{d} - t^* \text{SE}), \min(1.0, \bar{d} + t^* \text{SE})]$.
    2. **`welch_t_run` / `one_sample_t_run`** (primary run-level inference inside multi-run cohort comparison `compare_run_cohorts` when $\max(K, M) \ge 2$):
       - When $K \ge 2$ and $M \ge 2$: Welch's two-sample $t$-test over baseline run metric scores $[b_1, \dots, b_K]$ and candidate run metric scores $[c_1, \dots, c_M]$ using Welch-Satterthwaite $df$ (clamped cleanly if one side has zero variance and the other is positive: $df = n_{\text{nonzero}} - 1$).
       - When $K = 1, M \ge 2$ (or $K \ge 2, M = 1$): one-sample $t$-test of the repeated side against the single fixed reference score (`df = M - 1` or `K - 1`).
  - Handle degenerate zero-variance edges explicitly without division by zero or `NaN`:
    - When `SE <= FLOAT_EPSILON`: if $|\bar{d}| \le \text{FLOAT\_EPSILON}$, emit `[0.0, 0.0]`, `p_value = 1.0`, `NOT_SIGNIFICANT`; otherwise emit `[d_bar, d_bar]` (clamped), `p_value = 0.0`, `SIGNIFICANT_IMPROVEMENT` or `SIGNIFICANT_REGRESSION`.
- **Rationale**:
  - Satisfies `tests/test_library_purity.py` (`scipy`/`numpy` absent from `regression/` and core package), works identically across Python 3.10–3.13 and all OS platforms, handles arbitrary confidence levels (`0.90`, `0.95`, `0.99`, etc.), and handles small repeats (`--repeats 3`) as well as large case counts (`100+`).
  - Clamping reported `ci_low`/`ci_high` to `[-1.0, 1.0]` respects the domain invariant that metric deltas lie in `[-1.0, 1.0]` while significance remains driven strictly by the exact $t$-test $p$-value $< (1 - \text{confidence\_level})$.
- **Alternatives Considered**:
  - *Hardcoded $z = 1.96$ normal approximation*: Rejected because small sample counts ($K=3$–$5$ runs or $5$–$15$ cases) require Student's $t$ heavy tails to avoid false significance.
  - *Monte Carlo permutation/bootstrap sampling*: Rejected as primary default because small $n=2..4$ yields too few discrete permutations for 95% intervals without fragile tie-breaking, though Student's $t$ works cleanly down to $n=2$.

### R5 — Multi-Run `compare`, `--repeats`, Quality Gate & Backward Compatibility

- **Decision**:
  - Extend `MetricComparison` with optional backward-compatible fields `statistics: StatisticalSummary | None = None` and `case_statistics: StatisticalSummary | None = None`.
  - Extend `RunComparisonReport` with optional `cohort: RunCohortSummary | None = None`, leaving `baseline_run_id`, `candidate_run_id`, and all existing fields intact (`representative` run IDs when comparing cohorts so `QualityGate.evaluate(...)` validates without breaking existing assertions).
  - Add pure `compare_run_cohorts(baseline_runs, candidate_runs, *, baseline_name=None, policy=None)` alongside `compare_runs(baseline, candidate, ...)` (`tests/test_api_stability.py` preserves `compare_runs` signature and checks `compare_run_cohorts` explicitly).
  - Add statistical Quality Gate rule in `regression/gate.py` (`100%` branch coverage maintained via `tests/unit/test_quality_gate.py`):
    - Checks `mc.statistics.significance == SignificanceStatus.SIGNIFICANT_REGRESSION` across comparable metrics (with `fail_on_significant_regression: bool = False`, emitting `WARNING` by default or `FAIL` when enabled, and `PASS` on rule `"statistical_significance"` when no significant regressions occur among statistically evaluated metrics).
  - Extend `cli` (`run --repeats N`, `compare cand1 [cand2 ...] --baseline ... [--baseline-run ...]`, `[embedding]` TOML/ENV/CLI precedence) without breaking any existing single-run `compare <id> --baseline <ref>` invocation.
- **Rationale**:
  - Guarantees `100%` deserialization compatibility with all existing M1–M6 `.evalforge/runs/*.json`, `RunComparisonReport`, and CLI scripts while providing seamless upgrade to statistical & cohort evaluation.
- **Alternatives Considered**:
  - *Creating an incompatible `2.0` comparison schema or separate `compare-cohorts` subcommand*: Rejected to keep `compare` cohesive and preserve existing workflow familiarity.
