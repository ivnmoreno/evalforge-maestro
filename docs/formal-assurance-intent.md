# EvalForge Formal Assurance Layer — Architectural Intent

**Project:** EvalForge Maestro  
**Capability:** Formal Assurance Layer  
**Technology:** Lean 4  
**Status:** Active Architectural Extension (Increment 1 — Quality Gate Decision Semantics, Increment 2 — Retrieval IR Metric Invariants & Increment 3 — Judge Calibration & Threshold Optimization Shipped)  
**Parent Charter:** [`intent.md`](intent.md)  
**Implementation Guide:** [`formal-assurance.md`](formal-assurance.md)  
**Primary Objective:** Machine-checked formal specifications of selected EvalForge correctness and decision-making properties.

## 1. Purpose

Introduce Lean 4 as an independent formal specification and theorem-proving layer within EvalForge.

The purpose is to establish mathematically precise specifications for selected algorithms, decision rules, and domain invariants, and to prove that these specifications satisfy explicitly stated properties.

The formal assurance layer complements, but does not replace, the existing Python implementation, Pydantic contracts, unit tests, property-based tests, integration tests, and regression tests.

## 2. Architectural Position

Python remains the primary implementation language and runtime.

Lean 4 is used for:

- Formal modeling of selected domain contracts.
- Mathematical specification of algorithms and decision rules.
- Machine-checked proofs of specified invariants.
- Reference models for independent conformance testing.
- Formal documentation of assumptions and guarantees.

Lean must not become a runtime dependency of the Python package.

Ordinary EvalForge users must not need Lean installed to install, import, or operate the Python application.

The formal project must be independently buildable using Lean's Lake build system.

## 3. Initial Scope

The first implementation increment focuses exclusively on the existing Quality Gate decision semantics.

The formal model must reflect the actual implementation in:

- `src/evalforge_maestro/types.py`
- `src/evalforge_maestro/regression/gate.py`

The existing decision precedence is:

`FAIL > INCONCLUSIVE > WARNING > PASS`

The formal specification must model the current behavior rather than introduce a new decision system.

Required properties include:

- Decision precedence correctness.
- Failure dominance.
- Inconclusive dominance over warnings and passes.
- Warning dominance over passes.
- Deterministic final decision selection.
- Correct equivalence between the presence of failure reasons and a FAIL decision.
- Correct equivalence between the absence of failure and inconclusive reasons, warnings, and a PASS decision.

The specification must account for the distinction between rule-level results and the final aggregated decision.

## 4. Verification Boundaries

A Lean theorem proves a property of its formal model, not automatically of the Python implementation.

Therefore, formal verification must be complemented by Python-to-Lean conformance testing.

Conformance testing must:

- Exercise representative and boundary decision combinations.
- Compare Python results against the formal reference model.
- Detect semantic divergence between the implementation and specification.
- Run automatically in CI.
- Avoid introducing Lean into the Python runtime.

No claim of complete Python implementation verification may be made without an independently established proof of implementation correspondence.

## 5. Future Extensions

The following areas are candidates for subsequent formalization (with Candidates #1–#2 delivered in Increments 2–3):

1. Retrieval metric invariants and mathematical bounds *(Shipped in Increment 2 — see [`docs/formal-assurance.md`](formal-assurance.md))*.
2. Judge calibration and threshold optimization *(Shipped in Increment 3 — see [`docs/formal-assurance.md`](formal-assurance.md))*.
3. Statistical methodology, including paired and Welch comparisons.
4. Numerical approximation and floating-point error analysis.
5. Additional domain contracts where formal verification provides measurable assurance.

Each extension requires its own requirements, feasibility assessment, and acceptance criteria.

## 6. Engineering Requirements

- Keep formal specifications modular and independently buildable.
- Use explicit types and mathematical definitions.
- Avoid axioms or unverified assumptions that trivialize required proofs.
- Document assumptions and theorem limitations.
- Keep the Lean toolchain version pinned.
- Make all mandatory proofs reproducibly checkable in CI.
- Preserve Python package installation and runtime independence.
- Maintain compatibility with the existing architecture and public API.
- Avoid duplicating business logic unnecessarily between Python and Lean.

## 7. CI/CD Requirements

The formal project must have an independent CI verification job.

The job must:

1. Install or activate the pinned Lean toolchain.
2. Build the formal project.
3. Reject failed or incomplete proofs.
4. Run the Python-to-Lean conformance suite as a separate verification stage.
5. Produce clear diagnostics when verification fails.

Mandatory formal verification must become part of the repository's release acceptance process.

## 8. Non-Goals

The Formal Assurance Layer must not:

- Replace Python with Lean.
- Introduce a Lean runtime service.
- Require Lean for ordinary package consumers.
- Claim that all EvalForge behavior is formally verified.
- Replace conventional testing.
- Attempt to formalize every schema or function indiscriminately.
- Change existing Quality Gate semantics merely to simplify proofs.

## 9. Definition of Success

The initial capability is successful when:

- A standalone Lean 4 project exists within the repository.
- The existing Quality Gate decision semantics are formally specified.
- The required decision properties have machine-checked proofs.
- Python conformance tests establish agreement with the formal reference model for the tested cases.
- CI independently enforces Lean compilation, proof checking, and conformance testing.
- Existing Python functionality, package behavior, and architectural boundaries remain intact.

**Architectural Principle:**

EvalForge uses empirical testing to establish observed behavior and formal verification to establish mathematical properties of explicitly defined models. Both contribute to assurance, and neither is misrepresented as a substitute for the other.
