import EvalForgeFormal.QualityGate.RuleRecorder

namespace EvalForgeFormal.QualityGate

/--
Final decision and derived acceptance/blocking flags mirroring `QualityGateResult`
(`src/evalforge_maestro/regression/gate.py` and `src/evalforge_maestro/types.py`).
-/
structure GateOutcome where
  decision : GateDecision
  passed : Bool
  blocking : Bool
  deriving DecidableEq, Repr, BEq

/--
Select the final `GateDecision` from accumulated reason collections using the exact
precedence cascade in `QualityGate.evaluate()`:
`FAIL > INCONCLUSIVE > WARNING > PASS`.
-/
def selectDecision (s : ReasonState) : GateDecision :=
  if !s.failureReasons.isEmpty then
    .fail
  else if !s.inconclusiveReasons.isEmpty then
    .inconclusive
  else if !s.warningReasons.isEmpty then
    .warning
  else
    .pass

/-- Compute final decision together with derived flags `passed` and `blocking`. -/
def evaluateReasonState (s : ReasonState) : GateOutcome :=
  let d := selectDecision s
  { decision := d, passed := d == .pass, blocking := d == .fail }

/-- Partition rule checks via `recordChecks` and evaluate the resulting `ReasonState`. -/
def evaluateChecks (checks : List RuleCheck) : GateOutcome :=
  evaluateReasonState (recordChecks checks)

end EvalForgeFormal.QualityGate
