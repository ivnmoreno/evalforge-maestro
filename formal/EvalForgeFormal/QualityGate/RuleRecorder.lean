import EvalForgeFormal.QualityGate.Decision

namespace EvalForgeFormal.QualityGate

/-- Decision-relevant projection of `evalforge_maestro.types.GateRuleCheck`. -/
structure RuleCheck where
  status : GateDecision
  message : String
  deriving DecidableEq, Repr, BEq

/-- Three non-PASS diagnostic reason lists accumulated by `_RuleRecorder` (`gate.py`). -/
structure ReasonState where
  failureReasons : List String
  inconclusiveReasons : List String
  warningReasons : List String
  deriving DecidableEq, Repr, BEq

namespace ReasonState

/-- Initial empty reason state before any rule checks are recorded. -/
def empty : ReasonState :=
  { failureReasons := [], inconclusiveReasons := [], warningReasons := [] }

end ReasonState

/--
Record a single rule check into `ReasonState`, mirroring `_RuleRecorder.add`
in `src/evalforge_maestro/regression/gate.py`.

`pass` checks leave all three non-PASS reason lists unchanged.
-/
def recordCheck (s : ReasonState) (c : RuleCheck) : ReasonState :=
  match c.status with
  | .fail => { s with failureReasons := s.failureReasons ++ [c.message] }
  | .inconclusive => { s with inconclusiveReasons := s.inconclusiveReasons ++ [c.message] }
  | .warning => { s with warningReasons := s.warningReasons ++ [c.message] }
  | .pass => s

/-- Partition an ordered sequence of `RuleCheck` records into a `ReasonState`. -/
def recordChecks (checks : List RuleCheck) : ReasonState :=
  checks.foldl recordCheck ReasonState.empty

end EvalForgeFormal.QualityGate
