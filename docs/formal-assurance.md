# Formal Assurance Layer Guide (`Lean 4` — Quality Gate Decision Semantics)

EvalForge Maestro includes an independent, development-time and CI-time **Formal Assurance Layer** written in **Lean 4** (`formal/`), implementing Increment 1 of the architectural charter in [`docs/formal-assurance-intent.md`](formal-assurance-intent.md). Its first increment formally specifies and proves the core mathematical invariants of EvalForge's **Quality Gate** release-acceptance semantics and empirically checks conformance against the production Python implementation (`src/evalforge_maestro/regression/gate.py` and `src/evalforge_maestro/types.py`).

Python remains the sole production implementation and runtime language of `evalforge-maestro`. End users installing `evalforge-maestro` from PyPI or running the SDK/CLI **never require Lean, Lake, or Elan**.

---

## 1. Scope & Architectural Position

- **Standalone Lean 4 project**: `formal/` (pinned to `leanprover/lean4:v4.36.0` in [`formal/lean-toolchain`](../formal/lean-toolchain), pure Lean 4 core standard library with zero external Lean package dependencies in [`formal/lakefile.toml`](../formal/lakefile.toml)).
- **Excluded from Python distributions**: `pyproject.toml` excludes `/formal` from both built wheels (`[tool.hatch.build.targets.wheel]`) and PyPI source distributions (`[tool.hatch.build.targets.sdist]`), enforced in CI and release pipelines.
- **Authoritative Python runtime**: `src/evalforge_maestro/` is strictly unmodified and contains zero Lean imports, FFI bindings, Lean RPC/service processes, or subprocess calls.
- **Modeled layers (Increment 1)**:
  1. **`GateDecision` domain & total precedence** (`formal/EvalForgeFormal/QualityGate/Decision.lean`): four-state inductive type (`pass`, `warning`, `inconclusive`, `fail`) ordered strictly by `pass < warning < inconclusive < fail` (equivalently `FAIL > INCONCLUSIVE > WARNING > PASS`), mirroring `evalforge_maestro.types.GateDecision`.
  2. **`_RuleRecorder` check partitioning** (`formal/EvalForgeFormal/QualityGate/RuleRecorder.lean`): models `RuleCheck` (`status`, `message`), `ReasonState` (`failureReasons`, `inconclusiveReasons`, `warningReasons`), `recordCheck`, and `recordChecks`, mirroring `_RuleRecorder.add` in `src/evalforge_maestro/regression/gate.py` (where `PASS` checks leave all three non-PASS reason lists empty/unchanged).
  3. **Reason-collection decision aggregation & derived flags** (`formal/EvalForgeFormal/QualityGate/Aggregation.lean`): models `selectDecision`, `GateOutcome` (`decision`, `passed`, `blocking`), `evaluateReasonState`, and `evaluateChecks`, mirroring `QualityGate.evaluate()` (`passed = (decision == PASS)`, `blocking = (decision == FAIL)`).

---

## 2. Machine-Checked Theorem Inventory

All 22 theorems reside in [`formal/EvalForgeFormal/QualityGate/Properties.lean`](../formal/EvalForgeFormal/QualityGate/Properties.lean) and are audited at compile time by [`formal/EvalForgeAudit.lean`](../formal/EvalForgeAudit.lean) using `Lean.collectAxioms` to depend **only** on Lean's standard core axioms `{propext, Classical.choice, Quot.sound}` (strictly rejecting `sorryAx`, `Lean.ofReduceBool`, `Lean.trustCompiler`, and any user-declared `axiom`).

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
| **Determinism** | `selectDecision_depends_only_on_nonempty` | Decision depends solely on `(isEmpty, isEmpty, isEmpty)` across the three reason lists (invariant to ordering, multiplicity, and message text) |
| **Exhaustive 8-State** | `selectDecision_exhaustive_eight_states` | Every one of the `2^3 = 8` boolean `(hasFail, hasInc, hasWarn)` presence states maps uniquely to its expected `GateDecision` |
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

---

## 3. Building & Verifying the Lean 4 Project Locally

Install [`elan`](https://lean-lang.org/install/) (which automatically reads `formal/lean-toolchain` pinned to `leanprover/lean4:v4.36.0`), then run:

```bash
# 1. Compile EvalForgeFormal, compile-time EvalForgeAudit, and evalforge-gate-oracle
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

Python conformance tests live in [`tests/conformance/test_quality_gate_formal_conformance.py`](../tests/conformance/test_quality_gate_formal_conformance.py) alongside runtime/packaging isolation tests in [`tests/conformance/test_formal_runtime_isolation.py`](../tests/conformance/test_formal_runtime_isolation.py).

### Mode A: Offline Golden Artifact Mode (Default — Zero Lean Installation Required)

Standard `pytest` runs compare real `QualityGate.evaluate()`, `QualityGate.evaluate_cohort()`, and `_RuleRecorder` outputs against the CI-verified golden oracle fixture ([`tests/conformance/golden/quality_gate_oracle.json`](../tests/conformance/golden/quality_gate_oracle.json)):

```bash
uv run pytest --strict-markers -W error tests/conformance/
```

### Mode B: Fail-Closed Live Lean Oracle Mode (Mandatory in CI & Release)

After `cd formal && lake build`, execute conformance tests directly against the compiled Lean binary (`formal/.lake/build/bin/evalforge-gate-oracle`):

```bash
# Verify byte-for-byte deterministic parity between live export-golden and checked-in JSON
./formal/.lake/build/bin/evalforge-gate-oracle export-golden | diff -u tests/conformance/golden/quality_gate_oracle.json -

# Run fail-closed live-oracle conformance (never silently falls back if binary is missing or fails)
uv run pytest --strict-markers -W error --lean-live-oracle tests/conformance/
```

Covered Python conformance scenarios:
- **Exhaustive `8/8` boolean reason-presence combinations** `(failure_reasons, inconclusive_reasons, warning_reasons)` realized via concrete `QualityGate.evaluate()` calls, verifying all three diagnostic lists are retained when simultaneously populated.
- **`_RuleRecorder` partitioning and permutation parity** across empty, single-status, multi-status, and reordered rule-check sequences.
- **Boundary, policy-escalation, and cohort scenarios**: `min_score`, `max_regression_drop`, and `max_inconclusive_rate` epsilon boundaries (`FLOAT_EPSILON = 1e-9`), optional `NOT_APPLICABLE` metric vs. zero applicable run evidence, mandatory case failures alongside warnings/inconclusive rates, all four `fail_on_*` escalations (`fail_on_drift`, `fail_on_anomaly`, `fail_on_degrading_trend`, `fail_on_significant_regression`), and multi-run `evaluate_cohort()`.
- **Automated negative drift detection**: verifies injected Python decision discrepancies fail conformance assertions loudly, tampered golden artifacts fail validation/parity checks, and a missing `--lean-oracle-bin` fails closed under `--lean-live-oracle`.

---

## 5. CI & Release Enforcement

Both PR CI (`.github/workflows/ci.yml`, job `formal-assurance`) and tag-driven release verification (`.github/workflows/release.yml`, job `formal-assurance-gate` blocking `publish-testpypi`) run on `ubuntu-latest` independently of the Python lint/unit jobs:
1. `leanprover/lean-action@v1` builds `formal/` (enforcing compile-time `EvalForgeAudit.lean`) and runs `leanchecker EvalForgeFormal`.
2. `bash formal/scripts/verify_negative_probes.sh` confirms `sorry` and custom `axiom` declarations fail verification.
3. `uv run pytest --strict-markers -W error --lean-live-oracle tests/conformance/` verifies golden artifact byte parity and evaluates all exercised Python scenarios live against `evalforge-gate-oracle`.

Meanwhile, `cross-os-and-packaging` (`ubuntu-latest`, `macos-latest`, `windows-latest`) and `verify-and-build` verify offline conformance without Lean installed and assert that built `.whl` and `.tar.gz` (`sdist`) archives contain zero `formal/` directory entries, `.lean` files, `lean-toolchain`, or `lakefile.toml`.

---

## 6. Explicit Verification Boundaries (What Is and Is Not Guaranteed)

### What machine-checked Lean 4 proofs establish
- The mathematical properties listed in Section 2 hold **universally for all possible inputs** of the **Lean 4 formal model** (`EvalForgeFormal.QualityGate`), verified mechanically by Lean's kernel under at most `{propext, Classical.choice, Quot.sound}`.

### What Python conformance tests establish
- **Empirical agreement** between the actual Python implementation (`QualityGate.evaluate()`, `QualityGate.evaluate_cohort()`, `_RuleRecorder`) and the proved Lean reference model across all 8 boolean reason-presence combinations, canonical rule-check permutations, boundary thresholds, policy escalations, and cohort evaluations.

### What is NOT established or claimed
- **The Python implementation itself is NOT formally verified.** Neither CPython, Pydantic v2 validation, nor the Python source code of `src/evalforge_maestro/` is proved by Lean's kernel.
- **Pre-aggregation input validation is outside the formal aggregation domain**: raising `ConfigurationError` on mismatched `comparison.candidate_run_id`, empty `evaluate_cohort([])`, or mismatched cohort run IDs occurs prior to reason-list aggregation and is verified by Python unit tests rather than Lean.
- **Deferred EvalForge subsystems are excluded from Increment 1**: statistical tests and confidence intervals (`regression/stats.py`), IR/text/agent metric formulas (`metrics/`), judge calibration and threshold optimization (`judges/calibration.py`), floating-point error analysis, storage atomicity, OpenTelemetry ingestion, SQLite indexing, HTTP routing, and CLI argument parsing remain outside the formal model (see [`docs/future-features.md`](future-features.md)).
