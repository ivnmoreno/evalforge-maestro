import Lean.Elab.Command
import Lean.Util.CollectAxioms
import EvalForgeFormal.QualityGate.Properties

namespace EvalForgeAudit

open Lean Elab Command

/-- Standard Lean 4 core axioms explicitly permitted by EvalForge formal assurance policy. -/
def allowedCoreAxioms : Array Name :=
  #[``propext, ``Classical.choice, ``Quot.sound]

/--
Compile-time command elaborator auditing a declaration's transitive axiom footprint via
`Lean.collectAxioms`. Throws an elaboration error (failing `lake build`) if any axiom
outside `{propext, Classical.choice, Quot.sound}`—including `sorryAx`, `Lean.ofReduceBool`,
`Lean.trustCompiler`, or any custom `axiom`—is detected.
-/
elab "audit_allowed_axioms " id:ident : command => do
  let declName ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo id
  let axioms ← Lean.collectAxioms declName
  let forbidden := axioms.filter fun ax => !allowedCoreAxioms.contains ax
  if !forbidden.isEmpty then
    let forbiddenStr := ", ".intercalate (forbidden.toList.map toString)
    throwError "Axiom audit failed for '{declName}': forbidden axiom(s) detected: [{forbiddenStr}]. Allowed core axioms: [propext, Classical.choice, Quot.sound]."

-- Audit all 22 mandatory theorems from EvalForgeFormal.QualityGate.Properties
audit_allowed_axioms EvalForgeFormal.QualityGate.precedence_strict_chain
audit_allowed_axioms EvalForgeFormal.QualityGate.precedence_total
audit_allowed_axioms EvalForgeFormal.QualityGate.fail_dominates
audit_allowed_axioms EvalForgeFormal.QualityGate.inconclusive_dominates_warning_and_pass
audit_allowed_axioms EvalForgeFormal.QualityGate.warning_dominates_pass
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_eq_fail_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_eq_inconclusive_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_eq_warning_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_eq_pass_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_deterministic
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_depends_only_on_nonempty
audit_allowed_axioms EvalForgeFormal.QualityGate.selectDecision_exhaustive_eight_states
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateReasonState_passed_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateReasonState_blocking_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateReasonState_passed_blocking_mutex
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateReasonState_warning_and_inconclusive_neither
audit_allowed_axioms EvalForgeFormal.QualityGate.recordChecks_failure_nonempty_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.recordChecks_inconclusive_nonempty_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.recordChecks_warning_nonempty_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateChecks_eq_fail_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateChecks_eq_pass_iff
audit_allowed_axioms EvalForgeFormal.QualityGate.evaluateChecks_status_set_invariance

end EvalForgeAudit
