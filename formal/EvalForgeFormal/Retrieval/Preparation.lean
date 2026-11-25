import EvalForgeFormal.Retrieval.Types

namespace EvalForgeFormal.Retrieval

/-- Update an existing key in-place or append `(id, rel)` preserving insertion order and key uniqueness. -/
def upsertPositiveKey : RelevanceMap → String → Nat → RelevanceMap
  | [], id, rel => [(id, rel)]
  | (k, v) :: rest, id, rel =>
    if k = id then (k, rel) :: rest else (k, v) :: upsertPositiveKey rest id rel

/--
Insert an `ExpectedItem` into `G_pos` mirroring `retrieval.py#L38-L42`:
positive weights update/insert `G_pos[id] = relevance`, while `relevance = 0` is a no-op
(leaving any prior positive entry untouched).
-/
def upsertPositive (m : RelevanceMap) (item : ExpectedItem) : RelevanceMap :=
  if item.relevance = 0 then m else upsertPositiveKey m item.id item.relevance

/-- Build the positive relevance map `G_pos` by left-folding `upsertPositive`. -/
def buildRelevanceMap (expected : List ExpectedItem) : RelevanceMap :=
  expected.foldl upsertPositive []

/-- Test whether `id` has a positive relevance entry in `G_pos`. -/
def memGPos (gPos : RelevanceMap) (id : String) : Bool :=
  gPos.any (fun p => p.1 == id)

/-- Lookup relevance weight in `G_pos`, returning `0` when absent. -/
def lookupRel : RelevanceMap → String → Nat
  | [], _ => 0
  | (k, v) :: rest, id => if k = id then v else lookupRel rest id

/-- Attach sequential indices starting from `start` (mirrors Python `enumerate`). -/
def enumFrom {α : Type} (start : Nat) : List α → List (Nat × α)
  | [] => []
  | x :: xs => (start, x) :: enumFrom (start + 1) xs

/-- Sort key `(rank ?? idx + 1, idx)` mirroring `retrieval.py#L46-L49`. -/
def sortKey (p : Nat × RetrievedItem) : Nat × Nat :=
  (p.2.rank.getD (p.1 + 1), p.1)

/-- Total lexicographic `≤` comparator on `(rank ?? idx + 1, idx)`. -/
def sortKeyLe (a b : Nat × RetrievedItem) : Bool :=
  let (r1, i1) := sortKey a
  let (r2, i2) := sortKey b
  decide (r1 < r2 ∨ (r1 = r2 ∧ i1 ≤ i2))

/-- Stably sort indexed retrieved chunks by `sortKeyLe` via Lean core `List.mergeSort`. -/
def sortRetrievedIndexed (chunks : List RetrievedItem) : List (Nat × RetrievedItem) :=
  (enumFrom 0 chunks).mergeSort sortKeyLe

/-- Stably sort retrieved chunks by `(rank ?? idx + 1, idx)`. -/
def sortRetrieved (chunks : List RetrievedItem) : List RetrievedItem :=
  (sortRetrievedIndexed chunks).map Prod.snd

/--
Project a retrieved chunk to its effective ID mirroring `(chunk.parent_id or chunk.id)` when
`matchParentId = true` (falling back on both `none` and `some ""`), else `chunk.id`.
-/
def effectiveId (matchParentId : Bool) (c : RetrievedItem) : String :=
  if matchParentId then
    match c.parentId with
    | some pid => if pid.isEmpty then c.id else pid
    | none => c.id
  else
    c.id

/-- Auxiliary first-seen deduplicator maintaining the list of already-seen IDs. -/
def dedupPreserveFirstAux (seen : List String) : List String → List String
  | [] => []
  | x :: xs =>
    if x ∈ seen then
      dedupPreserveFirstAux seen xs
    else
      x :: dedupPreserveFirstAux (x :: seen) xs

/-- Deduplicate IDs while preserving the earliest rank of every unique effective ID. -/
def dedupPreserveFirst (xs : List String) : List String :=
  dedupPreserveFirstAux [] xs

/-- Formal model of `_prepare_retrieval_inputs` (`retrieval.py#L30-L60`). -/
def prepareRetrievalInputs
    (expected : List ExpectedItem)
    (retrieved : List RetrievedItem)
    (matchParentId : Bool) : PreparedRetrieval :=
  {
    gPos := buildRelevanceMap expected
    rankedIds := dedupPreserveFirst ((sortRetrieved retrieved).map (effectiveId matchParentId))
  }

/--
Formal model of `_prepare_ir_evaluation` (`retrieval.py#L63-L92`):
enforces `INCONCLUSIVE` on non-empty execution errors strictly ahead of `NOT_APPLICABLE`
on empty `G_pos`.
-/
def prepareIREvaluation
    (errors : List String)
    (expected : List ExpectedItem)
    (retrieved : List RetrievedItem)
    (matchParentId : Bool) : GuardOutcome :=
  if !errors.isEmpty then
    .inconclusive errors
  else
    let prep := prepareRetrievalInputs expected retrieved matchParentId
    if prep.gPos.isEmpty then
      .notApplicable
    else
      .ready prep.gPos prep.rankedIds

/-- Extract unique relevant hits inside the top-`k` prefix of `rankedIds`. -/
def extractHits (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) : List String :=
  (rankedIds.take k).filter (memGPos gPos)

/-! ## Core Structural Preparation Lemmas Used by Metric Definitions -/

theorem upsertPositiveKey_all_pos {m : RelevanceMap} {id : String} {rel : Nat}
    (hm : ∀ p ∈ m, 0 < p.2) (hrel : 0 < rel) :
    ∀ p ∈ upsertPositiveKey m id rel, 0 < p.2 := by
  induction m with
  | nil =>
    intro p hp
    simp only [upsertPositiveKey, List.mem_singleton] at hp
    subst hp
    exact hrel
  | cons hd tl ih =>
    intro p hp
    unfold upsertPositiveKey at hp
    split at hp
    · simp only [List.mem_cons] at hp
      rcases hp with rfl | htl
      · exact hrel
      · exact hm p (List.mem_cons_of_mem hd htl)
    · simp only [List.mem_cons] at hp
      rcases hp with rfl | htl
      · exact hm hd (List.mem_cons_self ..)
      · exact ih (fun q hq => hm q (List.mem_cons_of_mem hd hq)) p htl

theorem upsertPositive_all_pos {m : RelevanceMap} {item : ExpectedItem}
    (hm : ∀ p ∈ m, 0 < p.2) :
    ∀ p ∈ upsertPositive m item, 0 < p.2 := by
  unfold upsertPositive
  split
  · exact hm
  · rename_i hne
    exact upsertPositiveKey_all_pos hm (Nat.pos_of_ne_zero hne)

theorem foldl_upsertPositive_all_pos (m : RelevanceMap) (expected : List ExpectedItem)
    (hm : ∀ p ∈ m, 0 < p.2) :
    ∀ p ∈ expected.foldl upsertPositive m, 0 < p.2 := by
  induction expected generalizing m with
  | nil => exact hm
  | cons e es ih =>
    simp only [List.foldl_cons]
    exact ih (upsertPositive m e) (upsertPositive_all_pos hm)

theorem buildRelevanceMap_all_pos_core (expected : List ExpectedItem) :
    ∀ p ∈ buildRelevanceMap expected, 0 < p.2 :=
  foldl_upsertPositive_all_pos [] expected (fun _ h => nomatch h)

theorem prepareIREvaluation_ready_gPos_ne_nil
    {errors : List String} {expected : List ExpectedItem} {retrieved : List RetrievedItem}
    {matchParentId : Bool} {gPos : RelevanceMap} {rankedIds : List String}
    (h : prepareIREvaluation errors expected retrieved matchParentId = .ready gPos rankedIds) :
    gPos ≠ [] ∧ (∀ p ∈ gPos, 0 < p.2) := by
  unfold prepareIREvaluation at h
  cases errors with
  | cons _ _ => simp at h
  | nil =>
    simp only [List.isEmpty_nil, Bool.not_true, Bool.false_eq_true, ↓reduceIte] at h
    cases hg : (prepareRetrievalInputs expected retrieved matchParentId).gPos with
    | nil => simp [hg] at h
    | cons hd tl =>
      simp only [hg, List.isEmpty_cons, Bool.false_eq_true, ↓reduceIte,
        GuardOutcome.ready.injEq] at h
      obtain ⟨rfl, _⟩ := h
      refine ⟨List.cons_ne_nil hd tl, ?_⟩
      have hpos := buildRelevanceMap_all_pos_core expected
      rw [show buildRelevanceMap expected = hd :: tl from hg] at hpos
      exact hpos

end EvalForgeFormal.Retrieval
