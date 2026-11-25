# Formal Assurance Layer Guide (`Lean 4` — Quality Gate & Retrieval IR Metrics)

EvalForge Maestro includes an independent, development-time and CI-time **Formal Assurance Layer** written in **Lean 4** (`formal/`), implementing Increment 1 (**Quality Gate Decision Semantics**) and Increment 2 (**Retrieval IR Metric Invariants & Bounds**) of the architectural charter in [`docs/formal-assurance-intent.md`](formal-assurance-intent.md). It formally specifies and proves core mathematical invariants over EvalForge's release-acceptance gate (`src/evalforge_maestro/regression/gate.py`, `src/evalforge_maestro/types.py`) and deterministic Information Retrieval metrics (`src/evalforge_maestro/metrics/retrieval.py`), paired with dual-mode empirical Python-to-Lean conformance testing.

Python remains the sole production implementation and runtime language of `evalforge-maestro`. End users installing `evalforge-maestro` from PyPI or running the SDK/CLI **never require Lean, Lake, or Elan**.

---

## 1. Scope & Architectural Position

- **Standalone Lean 4 project**: `formal/` (pinned to `leanprover/lean4:v4.36.0` in [`formal/lean-toolchain`](../formal/lean-toolchain), pure Lean 4 core standard library `Init` with zero external Lean package dependencies in [`formal/lakefile.toml`](../formal/lakefile.toml)).
- **Excluded from Python distributions**: `pyproject.toml` excludes `/formal` and `/agy-logs` from both built wheels (`[tool.hatch.build.targets.wheel]`) and PyPI source distributions (`[tool.hatch.build.targets.sdist]`), enforced in CI and release pipelines.
- **Authoritative Python runtime**: `src/evalforge_maestro/` is strictly unmodified (including AST-pinned `src/evalforge_maestro/metrics/retrieval.py`) and contains zero Lean imports, FFI bindings, Lean RPC/service processes, or subprocess calls.
- **Modeled Increment 1 — Quality Gate Decision Semantics (`EvalForgeFormal.QualityGate`)**:
  1. **`GateDecision` domain & total precedence** (`formal/EvalForgeFormal/QualityGate/Decision.lean`): four-state inductive type (`pass`, `warning`, `inconclusive`, `fail`) ordered strictly by `pass < warning < inconclusive < fail` (`FAIL > INCONCLUSIVE > WARNING > PASS`), mirroring `evalforge_maestro.types.GateDecision`.
  2. **`_RuleRecorder` check partitioning** (`formal/EvalForgeFormal/QualityGate/RuleRecorder.lean`): models `RuleCheck`, `ReasonState`, `recordCheck`, and `recordChecks`, mirroring `_RuleRecorder.add` in `src/evalforge_maestro/regression/gate.py`.
  3. **Reason-collection decision aggregation & derived flags** (`formal/EvalForgeFormal/QualityGate/Aggregation.lean`): models `selectDecision`, `GateOutcome` (`decision`, `passed`, `blocking`), `evaluateReasonState`, and `evaluateChecks`.
- **Modeled Increment 2 — Retrieval IR Metric Invariants & Bounds (`EvalForgeFormal.Retrieval`)**:
  1. **Exact non-negative rationals (`NNRat`)** (`formal/EvalForgeFormal/Retrieval/ExactRat.lean`): pure-`Init` rational pair `(num, den)` with proof `0 < den`, exact cross-multiplication order/equivalence, arithmetic, positive-divisor division, rearrangement swap lemma, and `Nat.gcd` canonical reduction.
  2. **Retrieval domain & discount schedules** (`formal/EvalForgeFormal/Retrieval/Types.lean`): `ExpectedItem`, `RetrievedItem`, `RelevanceMap`, `PreparedRetrieval`, `IRStatus`, `GuardOutcome`, `MetricOutcome`, and `DiscountSchedule` (strictly positive non-increasing rational discount weights generalizing `1 / log2(i + 1)`, plus concrete executable `harmonicDiscount` `1 / (i + 1)`).
  3. **Input preparation, sorting, deduplication & guard precedence** (`formal/EvalForgeFormal/Retrieval/Preparation.lean`): mirrors `_prepare_retrieval_inputs` (`buildRelevanceMap` with last-positive overwrite and `relevance = 0` no-op, stable `(rank ?? idx+1, idx)` `List.mergeSort`, `effectiveId` fallback on `None`/`""`, first-seen `dedupPreserveFirst`) and `_prepare_ir_evaluation` (`INCONCLUSIVE > NOT_APPLICABLE > numeric`).
  4. **Deterministic IR scoring & finalization** (`formal/EvalForgeFormal/Retrieval/Metrics.lean`): exact rational `precisionAtK`, `recallAtK`, `hitRateAtK`, `mrr`, abstract-discount `dcgAtK` / `idcgAtK` / `ndcgAtK` with exponential gain `2^rel - 1`, `finalizeOutcome`, and end-to-end evaluators for all 5 IR metrics.

---

## 2. Machine-Checked Theorem Inventory (`58` Audited Theorems)

All **58** mandatory theorems (`22` Quality Gate + `36` Retrieval) are audited at compile time by [`formal/EvalForgeAudit.lean`](../formal/EvalForgeAudit.lean) using `Lean.collectAxioms` to depend **only** on Lean's standard core axioms `{propext, Classical.choice, Quot.sound}` (strictly rejecting `sorryAx`, `Lean.ofReduceBool`, `Lean.trustCompiler`, and any user-declared `axiom`).

### 2.1 Quality Gate Theorems (`22` — [`formal/EvalForgeFormal/QualityGate/Properties.lean`](../formal/EvalForgeFormal/QualityGate/Properties.lean))

| Group | Lean Theorem (`EvalForgeFormal.QualityGate.*`) | Machine-Checked Property |
| --- | --- | --- |
| **Precedence Order** | `precedence_strict_chain` | `pass < warning ∧ warning < inconclusive ∧ inconclusive < fail` |
| **Precedence Order** | `precedence_total` | `≤` on `GateDecision` is total (`a ≤ b ∨ b ≤ a`) and antisymmetric (`a ≤ b → b ≤ a → a = b`) |
| **Dominance** | `fail_dominates` | `s.failureReasons ≠ [] → selectDecision s = .fail` |
| **Dominance** | `inconclusive_dominates_warning_and_pass` | `s.failureReasons = [] → s.inconclusiveReasons ≠ [] → selectDecision s = .inconclusive` |
| **Dominance** | `warning_dominates_pass` | `s.failureReasons = [] → s.inconclusiveReasons = [] → s.warningReasons ≠ [] → selectDecision s = .warning` |
| **Biconditionals** | `selectDecision_eq_fail_iff` | `selectDecision s = .fail ↔ s.failureReasons ≠ []` |
| **Biconditionals** | `selectDecision_eq_inconclusive_iff` | `selectDecision s = .inconclusive ↔ s.failureReasons = [] ∧ s.inconclusiveReasons ≠ []` |
| **Biconditionals** | `selectDecision_eq_warning_iff` | `selectDecision s = .warning ↔ s.failureReasons = [] ∧ s.inconclusiveReasons = [] ∧ s.warningReasons ≠ []` |
| **Biconditionals** | `selectDecision_eq_pass_iff` | `selectDecision s = .pass ↔ s.failureReasons = [] ∧ s.inconclusiveReasons = [] ∧ s.warningReasons = []` |
| **Determinism** | `selectDecision_deterministic` | Equal `ReasonState` inputs always produce equal `GateDecision` outputs |
| **Determinism** | `selectDecision_depends_only_on_nonempty` | Decision depends solely on `(isEmpty, isEmpty, isEmpty)` across the three reason lists |
| **Exhaustive 8-State** | `selectDecision_exhaustive_eight_states` | Every one of the `2^3 = 8` boolean `(hasFail, hasInc, hasWarn)` states maps uniquely to its expected `GateDecision` |
| **Derived Flags** | `evaluateReasonState_passed_iff` | `(evaluateReasonState s).passed = true ↔ (evaluateReasonState s).decision = .pass` |
| **Derived Flags** | `evaluateReasonState_blocking_iff` | `(evaluateReasonState s).blocking = true ↔ (evaluateReasonState s).decision = .fail` |
| **Derived Flags** | `evaluateReasonState_passed_blocking_mutex` | `¬ ((evaluateReasonState s).passed = true ∧ (evaluateReasonState s).blocking = true)` |
| **Derived Flags** | `evaluateReasonState_warning_and_inconclusive_neither` | Both `WARNING` and `INCONCLUSIVE` yield `passed = false ∧ blocking = false` |
| **Rule Recorder** | `recordChecks_failure_nonempty_iff` | `(recordChecks checks).failureReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .fail` |
| **Rule Recorder** | `recordChecks_inconclusive_nonempty_iff` | `(recordChecks checks).inconclusiveReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .inconclusive` |
| **Rule Recorder** | `recordChecks_warning_nonempty_iff` | `(recordChecks checks).warningReasons ≠ [] ↔ ∃ c ∈ checks, c.status = .warning` |
| **Rule Recorder** | `evaluateChecks_eq_fail_iff` | `(evaluateChecks checks).decision = .fail ↔ ∃ c ∈ checks, c.status = .fail` |
| **Rule Recorder** | `evaluateChecks_eq_pass_iff` | `(evaluateChecks checks).decision = .pass ↔ ∀ c ∈ checks, c.status = .pass` |
| **Rule Recorder** | `evaluateChecks_status_set_invariance` | Any reordering, duplication, or rewriting of `RuleCheck` sequences preserving the set of present statuses produces the identical `GateOutcome` |

### 2.2 Retrieval IR Metric Theorems (`36` — [`formal/EvalForgeFormal/Retrieval/Properties.lean`](../formal/EvalForgeFormal/Retrieval/Properties.lean))

| Group | Lean Theorem (`EvalForgeFormal.Retrieval.*`) | Machine-Checked Property |
| --- | --- | --- |
| **Guard Precedence & Safety** | `prepareIREvaluation_errors_precedence` | `errors ≠ [] → prepareIREvaluation ... = .inconclusive errors` (supersedes empty/all-zero ground truth) |
| **Guard Precedence & Safety** | `prepareIREvaluation_empty_gpos_notApplicable` | `errors = [] → (∀ e ∈ expected, e.relevance = 0) → prepareIREvaluation ... = .notApplicable` |
| **Guard Precedence & Safety** | `prepareIREvaluation_ready_guarantees` | `.ready gPos rankedIds` guarantees `errors = []`, `0 < gPos.length`, positive weights, `keys.Nodup`, and `rankedIds.Nodup` |
| **Guard Precedence & Safety** | `evaluate_guards_match_all_metrics` | All 5 evaluators return `.inconclusive` (`score = none`) on errors and `.notApplicable` (`score = none`) on empty `G_pos` |
| **Preparation & Deduplication** | `buildRelevanceMap_keys_nodup` | `G_pos` key list is strictly duplicate-free (`Nodup`) |
| **Preparation & Deduplication** | `buildRelevanceMap_all_pos` | Every retained entry in `G_pos` has strictly positive relevance (`0 < rel`) |
| **Preparation & Deduplication** | `buildRelevanceMap_mem_iff` | `id` is in `G_pos` iff `expected` contains an entry for `id` with `relevance > 0` |
| **Preparation & Deduplication** | `sortRetrieved_perm_and_sorted` | Indexed `(rank ?? idx+1, idx)` `mergeSort` preserves chunk multiset (`Perm`) and pairwise `sortKeyLe` order |
| **Preparation & Deduplication** | `dedupPreserveFirst_nodup` | First-seen deduplication always yields `Nodup` |
| **Preparation & Deduplication** | `dedupPreserveFirst_mem_iff` | First-seen deduplication preserves exact set membership |
| **Preparation & Deduplication** | `prepareRetrievalInputs_rankedIds_mem_iff` | `cid ∈ rankedIds ↔ ∃ c ∈ retrieved, effectiveId matchParentId c = cid` |
| **Preparation & Deduplication** | `extractHits_length_le_min` | Deduplicated hit count never exceeds `min k |G_pos|` (anti-inflation cap) |
| **Universal `[0, 1]` Bounds** | `precisionAtK_bounds` | `0 ≤ Precision@K ≤ 1` for all `k ≥ 1` and `Nodup rankedIds` |
| **Universal `[0, 1]` Bounds** | `recallAtK_bounds` | `0 ≤ Recall@K ≤ 1` for all `|G_pos| ≥ 1` and `Nodup rankedIds` |
| **Universal `[0, 1]` Bounds** | `hitRateAtK_binary` | `Hit Rate@K ∈ {0, 1}` |
| **Universal `[0, 1]` Bounds** | `mrr_bounds` | `0 ≤ MRR ≤ 1` universally |
| **Universal `[0, 1]` Bounds** | `idcgAtK_pos` | `IDCG@K > 0` for `k ≥ 1`, `G_pos ≠ []`, positive weights, and any `DiscountSchedule` |
| **Universal `[0, 1]` Bounds** | `dcgAtK_le_idcgAtK` | `DCG@K ≤ IDCG@K` for `Nodup rankedIds` under any positive non-increasing `DiscountSchedule` |
| **Universal `[0, 1]` Bounds** | `ndcgAtK_bounds` | `0 ≤ NDCG@K ≤ 1` universally over any `DiscountSchedule` |
| **Cutoff Monotonicity** | `extractHits_length_mono` | `k₁ ≤ k₂ → |hits(k₁)| ≤ |hits(k₂)|` |
| **Cutoff Monotonicity** | `recallAtK_mono` | `k₁ ≤ k₂ → Recall@k₁ ≤ Recall@k₂` |
| **Cutoff Monotonicity** | `hitRateAtK_mono` | `k₁ ≤ k₂ → Hit Rate@k₁ ≤ Hit Rate@k₂` |
| **Cutoff Monotonicity** | `dcgAtK_mono` | `k₁ ≤ k₂ → DCG@k₁ ≤ DCG@k₂` |
| **Cutoff Monotonicity** | `idcgAtK_mono` | `k₁ ≤ k₂ → IDCG@k₁ ≤ IDCG@k₂` |
| **Identities & Boundaries** | `precision_recall_exact_identity` | `Precision@K · K ≈ Recall@K · |G_pos|` |
| **Identities & Boundaries** | `hitRate_one_iff_precision_pos` | `Hit Rate@K = 1 ↔ Precision@K > 0` |
| **Identities & Boundaries** | `hitRate_one_iff_recall_pos` | `Hit Rate@K = 1 ↔ Recall@K > 0` |
| **Identities & Boundaries** | `hitRate_zero_iff_no_hits` | `Hit Rate@K = 0 ↔ hits = [] ↔ Precision@K ≈ 0 ↔ Recall@K ≈ 0` |
| **Identities & Boundaries** | `mrr_eq_one_iff_rank_one_relevant` | `MRR ≈ 1 ↔` rank-1 deduplicated chunk is in `G_pos` |
| **Identities & Boundaries** | `mrr_eq_zero_iff_no_relevant` | `MRR ≈ 0 ↔` no deduplicated chunk is in `G_pos` |
| **Identities & Boundaries** | `hitRate_one_implies_mrr_ge_inv_k` | `Hit Rate@K = 1 → MRR ≥ 1 / K` |
| **Identities & Boundaries** | `empty_retrieval_scores_zero` | Empty retrieval (`rankedIds = []`) yields exact `0` across all 5 IR metrics |
| **Identities & Boundaries** | `ndcgAtK_optimal_order_eq_one` | Retrieving `G_pos` keys sorted descending by relevance yields `NDCG@K ≈ 1` |
| **Threshold Finalization** | `finalizeOutcome_pass_iff` | Numeric `status = PASS ↔ threshold ≤ score` |
| **Threshold Finalization** | `finalizeOutcome_fail_iff` | Numeric `status = FAIL ↔ score < threshold` |
| **Threshold Finalization** | `finalizeOutcome_pass_fail_mutex` | Numeric `PASS` and `FAIL` are exhaustive and mutually exclusive |

---

## 3. Building & Verifying the Lean 4 Project Locally

Install [`elan`](https://lean-lang.org/install/) (which automatically reads `formal/lean-toolchain` pinned to `leanprover/lean4:v4.36.0`), then run:

```bash
# 1. Compile EvalForgeFormal, compile-time EvalForgeAudit (58 theorems), and both oracle binaries
cd formal
lake build

# 2. Independently kernel-check compiled .olean artifacts via bundled leanchecker
lake env leanchecker EvalForgeFormal

# 3. Run automated negative fault-detection probes confirming sorry & custom axiom rejection
cd ..
bash formal/scripts/verify_negative_probes.sh
```

Expected result: zero compilation errors, zero `sorry` warnings, `leanchecker` exits `0`, and `verify_negative_probes.sh` exits `0` after confirming that both temporary probes (`sorryAx` and a custom `axiom`) are rejected with non-zero exit codes.

---

## 4. Dual-Mode Python-to-Lean Conformance Testing

Python conformance tests live in:
- [`tests/conformance/test_quality_gate_formal_conformance.py`](../tests/conformance/test_quality_gate_formal_conformance.py) (Quality Gate conformance)
- [`tests/conformance/test_retrieval_metrics_formal_conformance.py`](../tests/conformance/test_retrieval_metrics_formal_conformance.py) (Retrieval IR metric conformance)
- [`tests/conformance/test_formal_runtime_isolation.py`](../tests/conformance/test_formal_runtime_isolation.py) (Runtime & wheel/`sdist` isolation)

### Mode A: Offline Golden Artifact Mode (Default — Zero Lean Installation Required)

Standard `pytest` runs compare real Python `QualityGate` and IR metric (`PrecisionAtKMetric`, `RecallAtKMetric`, `HitRateAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, `_prepare_retrieval_inputs`) outputs against the CI-verified golden oracle fixtures ([`quality_gate_oracle.json`](../tests/conformance/golden/quality_gate_oracle.json) and [`retrieval_metrics_oracle.json`](../tests/conformance/golden/retrieval_metrics_oracle.json)):

```bash
uv run pytest --strict-markers -W error tests/conformance/
```

### Mode B: Fail-Closed Live Lean Oracle Mode (Mandatory in CI & Release)

After `cd formal && lake build`, execute conformance tests directly against both compiled Lean binaries (`evalforge-gate-oracle` and `evalforge-retrieval-oracle`):

```bash
# Verify byte-for-byte deterministic parity for BOTH golden oracle fixtures
./formal/.lake/build/bin/evalforge-gate-oracle export-golden | diff -u tests/conformance/golden/quality_gate_oracle.json -
./formal/.lake/build/bin/evalforge-retrieval-oracle export-golden | diff -u tests/conformance/golden/retrieval_metrics_oracle.json -

# Run fail-closed live-oracle conformance across both Quality Gate and Retrieval suites
uv run pytest --strict-markers -W error --lean-live-oracle tests/conformance/
```

---

## 5. CI & Release Enforcement

Both PR CI (`.github/workflows/ci.yml`, job `formal-assurance`) and tag-driven release verification (`.github/workflows/release.yml`, job `formal-assurance-gate` blocking `publish-testpypi`) run on `ubuntu-latest` independently of the Python lint/unit jobs:
1. `leanprover/lean-action@v1` builds `formal/` (enforcing compile-time `EvalForgeAudit.lean` across all 58 theorems and compiling both oracles) and runs `leanchecker EvalForgeFormal`.
2. `bash formal/scripts/verify_negative_probes.sh` confirms `sorry` and custom `axiom` declarations fail verification.
3. `uv run pytest --strict-markers -W error --lean-live-oracle tests/conformance/` verifies golden artifact byte parity and evaluates all exercised Quality Gate and Retrieval Python scenarios live against `evalforge-gate-oracle` and `evalforge-retrieval-oracle`.

Meanwhile, `cross-os-and-packaging` (`ubuntu-latest`, `macos-latest`, `windows-latest`) and `verify-and-build` verify offline conformance without Lean installed and assert that built `.whl` and `.tar.gz` (`sdist`) archives contain zero `formal/`, `agy-logs/`, `.lean`, `lean-toolchain`, or `lakefile.toml` entries.

---

## 6. Explicit Verification Boundaries (What Is and Is Not Guaranteed)

### What machine-checked Lean 4 proofs establish
- The 58 mathematical properties listed in Section 2 hold **universally for all possible inputs** of the **Lean 4 formal models** (`EvalForgeFormal.QualityGate` and `EvalForgeFormal.Retrieval`), verified mechanically by Lean's kernel under at most `{propext, Classical.choice, Quot.sound}`.

### What Python conformance tests establish
- **Empirical agreement** between the actual Python implementations (`QualityGate.evaluate()`, `QualityGate.evaluate_cohort()`, `_RuleRecorder`, `PrecisionAtKMetric`, `RecallAtKMetric`, `HitRateAtKMetric`, `MRRMetric`, `NDCGAtKMetric`, `_prepare_retrieval_inputs`) and the proved Lean reference models across all exercised truth-table states, canonical vectors, cutoff sweeps, boundary thresholds, policy escalations, and negative drift probes.

### What is NOT established or claimed
- **The Python implementation itself is NOT formally verified.** Neither CPython, Pydantic v2 validation, nor the Python source code of `src/evalforge_maestro/` is proved by Lean's kernel.
- **IEEE-754 floating-point arithmetic and transcendental `math.log2` rounding are NOT formally verified.**
  - `NDCG@K` bounds and monotonicity are proved universally in Lean over any abstract strictly positive non-increasing rational `DiscountSchedule`; Python's IEEE-754 `math.log2(idx + 1)` approximation is checked empirically in conformance tests rather than proved in Lean.
  - Python's `round_score` rounds metric scores to 6 decimal places (`SCORE_ROUND_DECIMALS = 6`) prior to comparing `score >= threshold`. Exact-rational threshold soundness in Lean applies to unrounded `NNRat` values and does not model rounding-edge thresholds lying strictly between an unrounded rational `num / den` and `round_score(num / den)`.
- **Pre-evaluation / pre-aggregation Python validation sits outside the formal evaluation domains**: `ConfigurationError` guards in `QualityGate`, `MetricError` init guards (`k < 1`, non-finite or out-of-range `threshold`), and `EvaluationCase` duplicate `expected_context` ID rejection occur prior to formal evaluation and remain verified by Python unit/contract tests.
- **Deferred EvalForge subsystems remain outside Increments 1–2**: statistical tests and confidence intervals (`regression/stats.py`), deterministic text/JSON/agent metrics (`metrics/deterministic.py`, `metrics/agent.py`), judge calibration and threshold optimization (`judges/calibration.py`), floating-point error analysis, storage atomicity, OpenTelemetry ingestion, SQLite indexing, HTTP routing, and CLI argument parsing remain deferred (see [`docs/future-features.md`](future-features.md)).
