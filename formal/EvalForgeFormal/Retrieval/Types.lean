import EvalForgeFormal.Retrieval.ExactRat

namespace EvalForgeFormal.Retrieval

/-- Ground-truth expected context item mirroring `ExpectedContextItem` / `str` (`relevance := 1`). -/
structure ExpectedItem where
  id : String
  relevance : Nat
  deriving DecidableEq, Repr

/-- Retrieved chunk projection mirroring `RetrievedChunk(id, parent_id, rank)`. -/
structure RetrievedItem where
  id : String
  parentId : Option String := none
  rank : Option Nat := none
  deriving DecidableEq, Repr

/-- Association-list positive relevance map `G_pos` (`keys.Nodup` and every weight `> 0`). -/
abbrev RelevanceMap := List (String × Nat)

/-- Prepared retrieval inputs `(G_pos, ranked_ids)` mirroring `_prepare_retrieval_inputs`. -/
structure PreparedRetrieval where
  gPos : RelevanceMap
  rankedIds : List String
  deriving DecidableEq, Repr

/--
Abstract strictly positive, monotonically non-increasing rational discount schedule over
1-based ranks `i ≥ 1`, generalizing `1 / log2(i + 1)` for `NDCG@K`.
-/
structure DiscountSchedule where
  weight : Nat → NNRat
  pos : ∀ i, 1 ≤ i → NNRat.zero < weight i
  antitone : ∀ i j, 1 ≤ i → i ≤ j → weight j ≤ weight i

/-- Concrete executable rational discount schedule `w(i) = 1 / (i + 1)` used in the live oracle. -/
def harmonicDiscount : DiscountSchedule where
  weight i := ⟨1, i + 1, Nat.succ_pos i⟩
  pos i _ := by
    rw [NNRat.zero_lt_iff]
    exact Nat.zero_lt_one
  antitone i j _ hij := by
    show 1 * (i + 1) ≤ 1 * (j + 1)
    omega

/-- Four-state retrieval metric status mirroring `MetricStatus` for deterministic IR metrics. -/
inductive IRStatus where
  | inconclusive
  | notApplicable
  | pass
  | fail
  deriving DecidableEq, Repr

namespace IRStatus

/-- Canonical string serialization matching `evalforge_maestro.types.MetricStatus.value`. -/
def toCanonicalString : IRStatus → String
  | .inconclusive => "INCONCLUSIVE"
  | .notApplicable => "NOT_APPLICABLE"
  | .pass => "PASS"
  | .fail => "FAIL"

/-- Parse canonical `MetricStatus` string into `IRStatus`. -/
def ofCanonicalString? : String → Option IRStatus
  | "INCONCLUSIVE" => some .inconclusive
  | "NOT_APPLICABLE" => some .notApplicable
  | "PASS" => some .pass
  | "FAIL" => some .fail
  | _ => none

end IRStatus

/-- Guard evaluation outcome mirroring `_prepare_ir_evaluation` (`retrieval.py#L63-L92`). -/
inductive GuardOutcome where
  | inconclusive (errors : List String)
  | notApplicable
  | ready (gPos : RelevanceMap) (rankedIds : List String)
  deriving DecidableEq, Repr

/-- Final formal metric evaluation outcome mirroring `MetricResult(status, score, evidence)`. -/
structure MetricOutcome where
  status : IRStatus
  score : Option NNRat
  evidence : List String
  deriving DecidableEq, Repr

end EvalForgeFormal.Retrieval
