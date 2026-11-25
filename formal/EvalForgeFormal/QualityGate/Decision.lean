namespace EvalForgeFormal.QualityGate

/--
Four-state release acceptance verdict mirroring `evalforge_maestro.types.GateDecision`
(`src/evalforge_maestro/types.py`).

Strict precedence order: `fail > inconclusive > warning > pass`.
-/
inductive GateDecision where
  | pass
  | warning
  | inconclusive
  | fail
  deriving DecidableEq, Repr, BEq

namespace GateDecision

/-- Numeric severity rank defining total precedence (`pass < warning < inconclusive < fail`). -/
def precedenceRank : GateDecision → Nat
  | .pass => 0
  | .warning => 1
  | .inconclusive => 2
  | .fail => 3

instance : LT GateDecision where
  lt a b := a.precedenceRank < b.precedenceRank

instance : LE GateDecision where
  le a b := a.precedenceRank ≤ b.precedenceRank

instance : DecidableRel (· < · : GateDecision → GateDecision → Prop) :=
  fun a b => inferInstanceAs (Decidable (a.precedenceRank < b.precedenceRank))

instance : DecidableRel (· ≤ · : GateDecision → GateDecision → Prop) :=
  fun a b => inferInstanceAs (Decidable (a.precedenceRank ≤ b.precedenceRank))

/-- Canonical uppercase string matching `evalforge_maestro.types.GateDecision.value`. -/
def toCanonicalString : GateDecision → String
  | .pass => "PASS"
  | .warning => "WARNING"
  | .inconclusive => "INCONCLUSIVE"
  | .fail => "FAIL"

/-- Inverse parser from canonical uppercase `GateDecision` strings. -/
def ofCanonicalString? : String → Option GateDecision
  | "PASS" => some .pass
  | "WARNING" => some .warning
  | "INCONCLUSIVE" => some .inconclusive
  | "FAIL" => some .fail
  | _ => none

end GateDecision
end EvalForgeFormal.QualityGate
