import EvalForgeFormal.Retrieval.Preparation

namespace EvalForgeFormal.Retrieval

/-- Exact rational `Precision@K = |hits(top_k, G_pos)| / k` for `k ≥ 1`. -/
def precisionAtK (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (rankedIds : List String) : NNRat :=
  ⟨(extractHits k gPos rankedIds).length, k, hk⟩

/-- Exact rational `Recall@K = |hits(top_k, G_pos)| / |G_pos|` for `|G_pos| ≥ 1`. -/
def recallAtK (k : Nat) (gPos : RelevanceMap) (hg : 0 < gPos.length) (rankedIds : List String) : NNRat :=
  ⟨(extractHits k gPos rankedIds).length, gPos.length, hg⟩

/-- Exact binary `Hit Rate@K ∈ {0, 1}`. -/
def hitRateAtK (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) : NNRat :=
  if (extractHits k gPos rankedIds).isEmpty then NNRat.zero else NNRat.one

/-- Find the earliest 1-based rank and chunk ID matching `G_pos` across all `rankedIds`. -/
def firstMatchAux (rank : Nat) (gPos : RelevanceMap) : List String → Option (Nat × String)
  | [] => none
  | cid :: rest =>
    if memGPos gPos cid then
      some (rank, cid)
    else
      firstMatchAux (rank + 1) gPos rest

/-- Earliest 1-based relevant match `(rank, chunk_id)` in `rankedIds`. -/
def firstMatch (gPos : RelevanceMap) (rankedIds : List String) : Option (Nat × String) :=
  firstMatchAux 1 gPos rankedIds

theorem firstMatchAux_rank_ge {rank r : Nat} {gPos : RelevanceMap} {xs : List String} {cid : String}
    (h : firstMatchAux rank gPos xs = some (r, cid)) : rank ≤ r := by
  induction xs generalizing rank with
  | nil => simp [firstMatchAux] at h
  | cons x xs ih =>
    unfold firstMatchAux at h
    split at h
    · cases h
      exact Nat.le_refl _
    · have hle := ih h
      omega

/-- Exact rational Mean Reciprocal Rank `1 / first_rank` (or `0` when no relevant item appears). -/
def mrr (gPos : RelevanceMap) (rankedIds : List String) : NNRat :=
  match h : firstMatch gPos rankedIds with
  | some (r, _) =>
    have hr : 0 < r := Nat.lt_of_lt_of_le Nat.zero_lt_one (firstMatchAux_rank_ge h)
    ⟨1, r, hr⟩
  | none => NNRat.zero

/-- Exponential relevance gain `(2 ^ rel) - 1` mirroring `((2 ** rel) - 1)` in `retrieval.py#L322`. -/
def gain (rel : Nat) : Nat := (2 ^ rel) - 1

theorem gain_zero : gain 0 = 0 := rfl

theorem gain_pos_of_pos {rel : Nat} (h : 0 < rel) : 0 < gain rel := by
  unfold gain
  have h1 : 1 ≤ rel := h
  have h2 : 2 ^ 1 ≤ 2 ^ rel := Nat.pow_le_pow_right (by omega) h1
  simp only [Nat.pow_one] at h2
  omega

theorem gain_mono {r₁ r₂ : Nat} (h : r₁ ≤ r₂) : gain r₁ ≤ gain r₂ := by
  unfold gain
  have hp : 2 ^ r₁ ≤ 2 ^ r₂ := Nat.pow_le_pow_right (by omega) h
  omega

/-- Discounted cumulative gain sum starting at 1-based rank `pos`. -/
def weightedGainSumFrom (w : DiscountSchedule) (pos : Nat) : List Nat → NNRat
  | [] => NNRat.zero
  | r :: rs => (NNRat.scaleNat (gain r) (w.weight pos)).add (weightedGainSumFrom w (pos + 1) rs)

/-- Descending comparator `b ≤ a` for sorting ideal relevance weights. -/
def descNatLe (a b : Nat) : Bool := decide (b ≤ a)

/-- Actual relevance grades for the top-`k` deduplicated retrieved chunks. -/
def actualRelevances (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) : List Nat :=
  (rankedIds.take k).map (lookupRel gPos)

/-- Ideal top-`k` relevance grades sorted descending from `G_pos`. -/
def idealRelevances (k : Nat) (gPos : RelevanceMap) : List Nat :=
  ((gPos.map Prod.snd).mergeSort descNatLe).take k

/-- Actual gain sequence `[(2^rel - 1), ...]` for top-`k` retrieved chunks (for oracle parity). -/
def actualGains (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) : List Nat :=
  (actualRelevances k gPos rankedIds).map gain

/-- Ideal gain sequence `[(2^rel - 1), ...]` for top-`k` sorted `G_pos` values (for oracle parity). -/
def idealGains (k : Nat) (gPos : RelevanceMap) : List Nat :=
  (idealRelevances k gPos).map gain

/-- Discounted Cumulative Gain at cutoff `k` under discount schedule `w`. -/
def dcgAtK (w : DiscountSchedule) (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) : NNRat :=
  weightedGainSumFrom w 1 (actualRelevances k gPos rankedIds)

/-- Ideal Discounted Cumulative Gain at cutoff `k` under discount schedule `w`. -/
def idcgAtK (w : DiscountSchedule) (k : Nat) (gPos : RelevanceMap) : NNRat :=
  weightedGainSumFrom w 1 (idealRelevances k gPos)

theorem idcgAtK_pos_core
    (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hpos : ∀ p ∈ gPos, 0 < p.2) :
    NNRat.zero < idcgAtK w k gPos := by
  unfold idcgAtK idealRelevances
  let sortedRels := (gPos.map Prod.snd).mergeSort descNatLe
  have hperm : sortedRels.Perm (gPos.map Prod.snd) := List.mergeSort_perm _ _
  have hlenPos : 0 < sortedRels.length := by
    rw [hperm.length_eq, List.length_map]
    cases gPos with
    | nil => exact False.elim (hg rfl)
    | cons _ _ => exact Nat.succ_pos _
  cases htake : sortedRels.take k with
  | nil =>
    have hlt : 0 < (sortedRels.take k).length := by
      rw [List.length_take]
      exact Nat.lt_min.mpr ⟨hk, hlenPos⟩
    rw [htake] at hlt
    exact False.elim (Nat.lt_irrefl 0 hlt)
  | cons r rs =>
    have hmemTake : r ∈ sortedRels.take k := by rw [htake]; exact List.mem_cons_self ..
    have hmemSorted : r ∈ sortedRels := List.mem_of_mem_take hmemTake
    have hmemVals : r ∈ gPos.map Prod.snd := hperm.subset hmemSorted
    obtain ⟨p, hpMem, hpSnd⟩ := List.mem_map.mp hmemVals
    have hrPos : 0 < r := hpSnd ▸ hpos p hpMem
    have hgPos : 0 < gain r := gain_pos_of_pos hrPos
    have hwPos : NNRat.zero < w.weight 1 := w.pos 1 (Nat.le_refl 1)
    have hfirst : NNRat.zero < NNRat.scaleNat (gain r) (w.weight 1) :=
      NNRat.scaleNat_pos hgPos hwPos
    exact NNRat.add_pos_of_pos_left hfirst

/-- Exact rational `NDCG@K = DCG@K / IDCG@K` over any positive non-increasing `DiscountSchedule`. -/
def ndcgAtK
    (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hpos : ∀ p ∈ gPos, 0 < p.2)
    (rankedIds : List String) : NNRat :=
  have hidcgNumPos : 0 < (idcgAtK w k gPos).num :=
    (NNRat.zero_lt_iff _).mp (idcgAtK_pos_core w k hk gPos hg hpos)
  NNRat.div (dcgAtK w k gPos rankedIds) (idcgAtK w k gPos) hidcgNumPos

/-- Threshold finalization mirroring `_finalize_ir_result` (`score >= threshold → PASS else FAIL`). -/
def finalizeOutcome (score threshold : NNRat) (evidence : List String) : MetricOutcome :=
  let st := if NNRat.leBool threshold score then IRStatus.pass else IRStatus.fail
  { status := st, score := some score, evidence := evidence }

/-- End-to-end formal `Precision@K` evaluation mirroring `_score_precision_at_k`. -/
def evaluatePrecisionAtK
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (k : Nat) (hk : 0 < k) (matchParentId : Bool) (threshold : NNRat) : MetricOutcome :=
  match prepareIREvaluation errors expected retrieved matchParentId with
  | .inconclusive errs => { status := .inconclusive, score := none, evidence := errs }
  | .notApplicable => { status := .notApplicable, score := none, evidence := [] }
  | .ready gPos rankedIds =>
    let hits := extractHits k gPos rankedIds
    let score := precisionAtK k hk gPos rankedIds
    finalizeOutcome score threshold hits

/-- End-to-end formal `Recall@K` evaluation mirroring `_score_recall_at_k`. -/
def evaluateRecallAtK
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (k : Nat) (matchParentId : Bool) (threshold : NNRat) : MetricOutcome :=
  match h : prepareIREvaluation errors expected retrieved matchParentId with
  | .inconclusive errs => { status := .inconclusive, score := none, evidence := errs }
  | .notApplicable => { status := .notApplicable, score := none, evidence := [] }
  | .ready gPos rankedIds =>
    have hne : gPos ≠ [] := (prepareIREvaluation_ready_gPos_ne_nil h).1
    have hgLen : 0 < gPos.length := by
      cases gPos with
      | nil => exact False.elim (hne rfl)
      | cons _ _ => exact Nat.succ_pos _
    let hits := extractHits k gPos rankedIds
    let score := recallAtK k gPos hgLen rankedIds
    finalizeOutcome score threshold hits

/-- End-to-end formal `Hit Rate@K` evaluation mirroring `_score_hit_rate_at_k`. -/
def evaluateHitRateAtK
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (k : Nat) (matchParentId : Bool) (threshold : NNRat) : MetricOutcome :=
  match prepareIREvaluation errors expected retrieved matchParentId with
  | .inconclusive errs => { status := .inconclusive, score := none, evidence := errs }
  | .notApplicable => { status := .notApplicable, score := none, evidence := [] }
  | .ready gPos rankedIds =>
    let hits := extractHits k gPos rankedIds
    let score := hitRateAtK k gPos rankedIds
    finalizeOutcome score threshold hits

/-- End-to-end formal `MRR` evaluation mirroring `_score_mrr`. -/
def evaluateMRR
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (matchParentId : Bool) (threshold : NNRat) : MetricOutcome :=
  match prepareIREvaluation errors expected retrieved matchParentId with
  | .inconclusive errs => { status := .inconclusive, score := none, evidence := errs }
  | .notApplicable => { status := .notApplicable, score := none, evidence := [] }
  | .ready gPos rankedIds =>
    let ev := match firstMatch gPos rankedIds with
      | some (_, cid) => [cid]
      | none => []
    let score := mrr gPos rankedIds
    finalizeOutcome score threshold ev

/-- End-to-end formal `NDCG@K` evaluation under discount schedule `w`. -/
def evaluateNDCGAtK
    (w : DiscountSchedule)
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (k : Nat) (hk : 0 < k) (matchParentId : Bool) (threshold : NNRat) : MetricOutcome :=
  match h : prepareIREvaluation errors expected retrieved matchParentId with
  | .inconclusive errs => { status := .inconclusive, score := none, evidence := errs }
  | .notApplicable => { status := .notApplicable, score := none, evidence := [] }
  | .ready gPos rankedIds =>
    have hready := prepareIREvaluation_ready_gPos_ne_nil h
    let hits := extractHits k gPos rankedIds
    let score := ndcgAtK w k hk gPos hready.1 hready.2 rankedIds
    finalizeOutcome score threshold hits

end EvalForgeFormal.Retrieval
