import EvalForgeFormal.Retrieval.Metrics

namespace EvalForgeFormal.Retrieval

/-! ## Elementary Pure-Core List & Relevance-Map Helpers -/

private theorem nodup_length_le_of_subset {α : Type} {a b : List α}
    (hnd : a.Nodup) (hsub : ∀ x ∈ a, x ∈ b) : a.length ≤ b.length := by
  induction a generalizing b with
  | nil => exact Nat.zero_le _
  | cons x xs ih =>
    rw [List.nodup_cons] at hnd
    have hxMem : x ∈ b := hsub x (List.mem_cons_self ..)
    obtain ⟨b₁, b₂, rfl⟩ := List.mem_iff_append.mp hxMem
    have hsub' : ∀ y ∈ xs, y ∈ b₁ ++ b₂ := by
      intro y hy
      have hyB : y ∈ b₁ ++ x :: b₂ := hsub y (List.mem_cons_of_mem x hy)
      rw [List.mem_append, List.mem_cons] at hyB
      rw [List.mem_append]
      rcases hyB with h1 | rfl | h2
      · exact Or.inl h1
      · exact False.elim (hnd.1 hy)
      · exact Or.inr h2
    have hle := ih hnd.2 hsub'
    simp only [List.length_cons, List.length_append] at hle ⊢
    omega

private theorem memGPos_true_iff (gPos : RelevanceMap) (id : String) :
    memGPos gPos id = true ↔ id ∈ gPos.map Prod.fst := by
  unfold memGPos
  simp only [List.any_eq_true, beq_iff_eq, List.mem_map]

private theorem memGPos_false_iff (gPos : RelevanceMap) (id : String) :
    memGPos gPos id = false ↔ id ∉ gPos.map Prod.fst := by
  rw [← Bool.not_eq_true, memGPos_true_iff]

private theorem upsertPositiveKey_keys_mem_iff (m : RelevanceMap) (id : String) (rel : Nat)
    (q : String) :
    q ∈ (upsertPositiveKey m id rel).map Prod.fst ↔ q = id ∨ q ∈ m.map Prod.fst := by
  induction m with
  | nil => simp [upsertPositiveKey]
  | cons p ps ih =>
    cases p with
    | mk k v =>
      unfold upsertPositiveKey
      by_cases hEq : k = id
      · simp only [hEq, ↓reduceIte, List.map_cons, List.mem_cons]
        constructor
        · rintro (rfl | h)
          · exact Or.inl rfl
          · exact Or.inr (Or.inr h)
        · rintro (rfl | rfl | h)
          · exact Or.inl rfl
          · exact Or.inl rfl
          · exact Or.inr h
      · simp only [hEq, ↓reduceIte, List.map_cons, List.mem_cons, ih]
        constructor
        · rintro (rfl | rfl | h)
          · exact Or.inr (Or.inl rfl)
          · exact Or.inl rfl
          · exact Or.inr (Or.inr h)
        · rintro (rfl | rfl | h)
          · exact Or.inr (Or.inl rfl)
          · exact Or.inl rfl
          · exact Or.inr (Or.inr h)

private theorem upsertPositiveKey_keys_nodup {m : RelevanceMap} (hnd : (m.map Prod.fst).Nodup)
    (id : String) (rel : Nat) :
    ((upsertPositiveKey m id rel).map Prod.fst).Nodup := by
  induction m with
  | nil => simp [upsertPositiveKey]
  | cons p ps ih =>
    cases p with
    | mk k v =>
      simp only [List.map_cons, List.nodup_cons] at hnd
      unfold upsertPositiveKey
      by_cases hEq : k = id
      · simp only [hEq, ↓reduceIte, List.map_cons, List.nodup_cons]
        exact ⟨hEq ▸ hnd.1, hnd.2⟩
      · simp only [hEq, ↓reduceIte, List.map_cons, List.nodup_cons]
        refine ⟨?_, ih hnd.2⟩
        rw [upsertPositiveKey_keys_mem_iff]
        rintro (rfl | hmem)
        · exact hEq rfl
        · exact hnd.1 hmem

private theorem upsertPositive_keys_nodup {m : RelevanceMap} (hnd : (m.map Prod.fst).Nodup)
    (item : ExpectedItem) :
    ((upsertPositive m item).map Prod.fst).Nodup := by
  unfold upsertPositive
  split
  · exact hnd
  · exact upsertPositiveKey_keys_nodup hnd item.id item.relevance

private theorem foldl_upsertPositive_keys_nodup (m : RelevanceMap) (expected : List ExpectedItem)
    (hnd : (m.map Prod.fst).Nodup) :
    ((expected.foldl upsertPositive m).map Prod.fst).Nodup := by
  induction expected generalizing m with
  | nil => exact hnd
  | cons e es ih =>
    simp only [List.foldl_cons]
    exact ih (upsertPositive m e) (upsertPositive_keys_nodup hnd e)

private theorem upsertPositive_keys_mem_iff (m : RelevanceMap) (item : ExpectedItem) (q : String) :
    q ∈ (upsertPositive m item).map Prod.fst ↔
      (q = item.id ∧ 0 < item.relevance) ∨ q ∈ m.map Prod.fst := by
  unfold upsertPositive
  by_cases h0 : item.relevance = 0
  · simp [h0]
  · simp only [h0, ↓reduceIte, upsertPositiveKey_keys_mem_iff]
    have hpos : 0 < item.relevance := Nat.pos_of_ne_zero h0
    constructor
    · rintro (rfl | hm)
      · exact Or.inl ⟨rfl, hpos⟩
      · exact Or.inr hm
    · rintro (⟨rfl, _⟩ | hm)
      · exact Or.inl rfl
      · exact Or.inr hm

private theorem foldl_upsertPositive_keys_mem_iff (m : RelevanceMap) (expected : List ExpectedItem)
    (q : String) :
    q ∈ (expected.foldl upsertPositive m).map Prod.fst ↔
      q ∈ m.map Prod.fst ∨ ∃ e ∈ expected, e.id = q ∧ 0 < e.relevance := by
  induction expected generalizing m with
  | nil => simp
  | cons e es ih =>
    simp only [List.foldl_cons, ih, upsertPositive_keys_mem_iff, List.mem_cons]
    constructor
    · rintro ((⟨rfl, hpos⟩ | hm) | ⟨e', he', hid, hpos⟩)
      · exact Or.inr ⟨e, Or.inl rfl, rfl, hpos⟩
      · exact Or.inl hm
      · exact Or.inr ⟨e', Or.inr he', hid, hpos⟩
    · rintro (hm | ⟨e', rfl | he', hid, hpos⟩)
      · exact Or.inl (Or.inr hm)
      · exact Or.inl (Or.inl ⟨hid.symm, hpos⟩)
      · exact Or.inr ⟨e', he', hid, hpos⟩

/-! ## Input Preparation & Deduplication Soundness (`FR-003`, `FR-005` #2) -/

/-- `buildRelevanceMap` produces unique keys (`Nodup`). -/
theorem buildRelevanceMap_keys_nodup (expected : List ExpectedItem) :
    ((buildRelevanceMap expected).map Prod.fst).Nodup :=
  foldl_upsertPositive_keys_nodup [] expected List.nodup_nil

/-- Every entry retained in `buildRelevanceMap` has strictly positive relevance weight. -/
theorem buildRelevanceMap_all_pos (expected : List ExpectedItem) :
    ∀ p ∈ buildRelevanceMap expected, 0 < p.2 :=
  buildRelevanceMap_all_pos_core expected

/-- Membership in `G_pos` holds iff `expected` contains a positively weighted item with that ID. -/
theorem buildRelevanceMap_mem_iff (expected : List ExpectedItem) (id : String) :
    memGPos (buildRelevanceMap expected) id = true ↔
      ∃ e ∈ expected, e.id = id ∧ 0 < e.relevance := by
  rw [memGPos_true_iff]
  unfold buildRelevanceMap
  simpa using foldl_upsertPositive_keys_mem_iff [] expected id

private theorem sortKeyLe_trans (a b c : Nat × RetrievedItem)
    (hab : sortKeyLe a b = true) (hbc : sortKeyLe b c = true) :
    sortKeyLe a c = true := by
  unfold sortKeyLe at *
  simp only [decide_eq_true_eq] at hab hbc ⊢
  omega

private theorem sortKeyLe_total (a b : Nat × RetrievedItem) :
    (sortKeyLe a b || sortKeyLe b a) = true := by
  unfold sortKeyLe
  simp only [Bool.or_eq_true, decide_eq_true_eq]
  omega

/--
Stable `(rank ?? idx+1, idx)` sorting preserves exact chunk multiset (`Perm`) and yields
a pairwise `sortKeyLe`-ordered sequence.
-/
theorem sortRetrieved_perm_and_sorted (retrieved : List RetrievedItem) :
    ((enumFrom 0 retrieved).mergeSort sortKeyLe).Perm (enumFrom 0 retrieved) ∧
    List.Pairwise (fun a b => sortKeyLe a b = true) ((enumFrom 0 retrieved).mergeSort sortKeyLe) := by
  refine ⟨List.mergeSort_perm _ _, ?_⟩
  exact List.pairwise_mergeSort sortKeyLe_trans sortKeyLe_total _

private theorem dedupPreserveFirstAux_not_mem_seen (seen xs : List String) :
    ∀ y ∈ dedupPreserveFirstAux seen xs, y ∉ seen := by
  induction xs generalizing seen with
  | nil => intro _ h; cases h
  | cons x xs ih =>
    intro y hy
    unfold dedupPreserveFirstAux at hy
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte] at hy
      exact ih seen y hy
    · simp only [hseen, ↓reduceIte, List.mem_cons] at hy
      rcases hy with rfl | htail
      · exact hseen
      · intro hySeen
        exact ih (x :: seen) y htail (List.mem_cons_of_mem x hySeen)

private theorem dedupPreserveFirstAux_nodup (seen xs : List String) :
    (dedupPreserveFirstAux seen xs).Nodup := by
  induction xs generalizing seen with
  | nil => exact List.nodup_nil
  | cons x xs ih =>
    unfold dedupPreserveFirstAux
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte]
      exact ih seen
    · simp only [hseen, ↓reduceIte, List.nodup_cons]
      refine ⟨?_, ih (x :: seen)⟩
      intro hxTail
      exact dedupPreserveFirstAux_not_mem_seen (x :: seen) xs x hxTail (List.mem_cons_self ..)

private theorem dedupPreserveFirstAux_mem_iff (seen xs : List String) (y : String) :
    y ∈ dedupPreserveFirstAux seen xs ↔ y ∈ xs ∧ y ∉ seen := by
  induction xs generalizing seen with
  | nil => simp [dedupPreserveFirstAux]
  | cons x xs ih =>
    unfold dedupPreserveFirstAux
    by_cases hseen : x ∈ seen
    · simp only [hseen, ↓reduceIte, ih, List.mem_cons]
      constructor
      · rintro ⟨hyXs, hyNotSeen⟩
        exact ⟨Or.inr hyXs, hyNotSeen⟩
      · rintro ⟨rfl | hyXs, hyNotSeen⟩
        · exact False.elim (hyNotSeen hseen)
        · exact ⟨hyXs, hyNotSeen⟩
    · simp only [hseen, ↓reduceIte, List.mem_cons, ih]
      constructor
      · rintro (rfl | ⟨hyXs, hyNotSeen'⟩)
        · exact ⟨Or.inl rfl, hseen⟩
        · exact ⟨Or.inr hyXs, fun h => hyNotSeen' (Or.inr h)⟩
      · rintro ⟨rfl | hyXs, hyNotSeen⟩
        · exact Or.inl rfl
        · by_cases hyx : y = x
          · exact Or.inl hyx
          · exact Or.inr ⟨hyXs, by rintro (rfl | h); exact hyx rfl; exact hyNotSeen h⟩

/-- First-seen deduplication always yields a duplicate-free list (`Nodup`). -/
theorem dedupPreserveFirst_nodup (xs : List String) :
    (dedupPreserveFirst xs).Nodup :=
  dedupPreserveFirstAux_nodup [] xs

/-- First-seen deduplication preserves exact set membership of all effective IDs. -/
theorem dedupPreserveFirst_mem_iff (xs : List String) (x : String) :
    x ∈ dedupPreserveFirst xs ↔ x ∈ xs := by
  simpa [dedupPreserveFirst] using dedupPreserveFirstAux_mem_iff [] xs x

private theorem mem_enumFrom_snd_iff {α : Type} (start : Nat) (xs : List α) (c : α) :
    c ∈ (enumFrom start xs).map Prod.snd ↔ c ∈ xs := by
  induction xs generalizing start with
  | nil => simp [enumFrom]
  | cons x xs ih => simp [enumFrom, ih]

/--
End-to-end `_prepare_retrieval_inputs` membership preservation: a chunk ID appears in
`rankedIds` iff some retrieved chunk projects to it under `effectiveId matchParentId`.
-/
theorem prepareRetrievalInputs_rankedIds_mem_iff
    (expected : List ExpectedItem) (retrieved : List RetrievedItem) (matchParentId : Bool)
    (cid : String) :
    cid ∈ (prepareRetrievalInputs expected retrieved matchParentId).rankedIds ↔
      ∃ c ∈ retrieved, effectiveId matchParentId c = cid := by
  unfold prepareRetrievalInputs sortRetrieved sortRetrievedIndexed
  rw [dedupPreserveFirst_mem_iff, List.mem_map]
  have hperm : ((enumFrom 0 retrieved).mergeSort sortKeyLe).Perm (enumFrom 0 retrieved) :=
    (sortRetrieved_perm_and_sorted retrieved).1
  have hmemSort : ∀ c, c ∈ ((enumFrom 0 retrieved).mergeSort sortKeyLe).map Prod.snd ↔ c ∈ retrieved := by
    intro c
    rw [(hperm.map Prod.snd).mem_iff, mem_enumFrom_snd_iff]
  simp only [hmemSort]

/--
Deduplication anti-inflation cap: unique hits in top-`k` never exceed `min k |G_pos|`.
-/
theorem extractHits_length_le_min (k : Nat) (gPos : RelevanceMap) (rankedIds : List String)
    (hndR : rankedIds.Nodup) :
    (extractHits k gPos rankedIds).length ≤ min k gPos.length := by
  apply Nat.le_min.mpr
  constructor
  · have h1 : (extractHits k gPos rankedIds).length ≤ (rankedIds.take k).length :=
      List.length_filter_le _ _
    have h2 : (rankedIds.take k).length ≤ k := by
      rw [List.length_take]
      exact Nat.min_le_left _ _
    exact Nat.le_trans h1 h2
  · have hndTake : (rankedIds.take k).Nodup := hndR.sublist (List.take_sublist k rankedIds)
    have hndHits : (extractHits k gPos rankedIds).Nodup :=
      hndTake.sublist (List.filter_sublist)
    have hsub : ∀ cid ∈ extractHits k gPos rankedIds, cid ∈ gPos.map Prod.fst := by
      intro cid hcid
      unfold extractHits at hcid
      rw [List.mem_filter] at hcid
      exact (memGPos_true_iff gPos cid).mp hcid.2
    have hle := nodup_length_le_of_subset hndHits hsub
    simpa [List.length_map] using hle

/-! ## Guard Precedence & Zero-Divisor Safety (`FR-002`, `FR-005` #1) -/

/-- Execution errors strictly supersede empty/all-zero ground truth (`INCONCLUSIVE > NOT_APPLICABLE`). -/
theorem prepareIREvaluation_errors_precedence
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (matchParentId : Bool) (herr : errors ≠ []) :
    prepareIREvaluation errors expected retrieved matchParentId = .inconclusive errors := by
  unfold prepareIREvaluation
  cases errors with
  | nil => exact False.elim (herr rfl)
  | cons _ _ => rfl

/-- When execution errors are empty and all expected items have relevance `0`, evaluation is `NOT_APPLICABLE`. -/
theorem prepareIREvaluation_empty_gpos_notApplicable
    (expected : List ExpectedItem) (retrieved : List RetrievedItem) (matchParentId : Bool)
    (hzero : ∀ e ∈ expected, e.relevance = 0) :
    prepareIREvaluation [] expected retrieved matchParentId = .notApplicable := by
  unfold prepareIREvaluation prepareRetrievalInputs
  have hempty : buildRelevanceMap expected = [] := by
    cases hmap : buildRelevanceMap expected with
    | nil => rfl
    | cons p ps =>
      have hmem : memGPos (buildRelevanceMap expected) p.1 = true := by
        rw [hmap]
        simp [memGPos]
      obtain ⟨e, heMem, _, hePos⟩ := (buildRelevanceMap_mem_iff expected p.1).mp hmem
      have hz := hzero e heMem
      omega
  simp [hempty]

/--
Zero-divisor safety guarantee: reaching `.ready gPos rankedIds` guarantees empty errors,
`|G_pos| ≥ 1`, strictly positive weights, unique `G_pos` keys, and duplicate-free `rankedIds`.
-/
theorem prepareIREvaluation_ready_guarantees
    (errors : List String) (expected : List ExpectedItem) (retrieved : List RetrievedItem)
    (matchParentId : Bool) (gPos : RelevanceMap) (rankedIds : List String)
    (hready : prepareIREvaluation errors expected retrieved matchParentId = .ready gPos rankedIds) :
    errors = [] ∧ 0 < gPos.length ∧ (∀ p ∈ gPos, 0 < p.2) ∧
      (gPos.map Prod.fst).Nodup ∧ rankedIds.Nodup := by
  unfold prepareIREvaluation at hready
  cases errors with
  | cons _ _ => simp at hready
  | nil =>
    simp only [List.isEmpty_nil, Bool.not_true, Bool.false_eq_true, ↓reduceIte] at hready
    cases hg : (prepareRetrievalInputs expected retrieved matchParentId).gPos with
    | nil => simp [hg] at hready
    | cons hd tl =>
      simp only [hg, List.isEmpty_cons, Bool.false_eq_true, ↓reduceIte,
        GuardOutcome.ready.injEq] at hready
      obtain ⟨rfl, rfl⟩ := hready
      refine ⟨rfl, Nat.succ_pos _, ?_, ?_, ?_⟩
      · have hpos := buildRelevanceMap_all_pos expected
        rw [show buildRelevanceMap expected = hd :: tl from hg] at hpos
        exact hpos
      · have hnd := buildRelevanceMap_keys_nodup expected
        rw [show buildRelevanceMap expected = hd :: tl from hg] at hnd
        exact hnd
      · exact dedupPreserveFirst_nodup _

/-- All 5 IR metric evaluators consistently return `INCONCLUSIVE` on errors and `NOT_APPLICABLE` on empty `G_pos`. -/
theorem evaluate_guards_match_all_metrics
    (w : DiscountSchedule) (errors : List String) (expected : List ExpectedItem)
    (retrieved : List RetrievedItem) (k : Nat) (hk : 0 < k) (matchParentId : Bool)
    (threshold : NNRat) :
    (errors ≠ [] →
      evaluatePrecisionAtK errors expected retrieved k hk matchParentId threshold =
        { status := .inconclusive, score := none, evidence := errors } ∧
      evaluateRecallAtK errors expected retrieved k matchParentId threshold =
        { status := .inconclusive, score := none, evidence := errors } ∧
      evaluateHitRateAtK errors expected retrieved k matchParentId threshold =
        { status := .inconclusive, score := none, evidence := errors } ∧
      evaluateMRR errors expected retrieved matchParentId threshold =
        { status := .inconclusive, score := none, evidence := errors } ∧
      evaluateNDCGAtK w errors expected retrieved k hk matchParentId threshold =
        { status := .inconclusive, score := none, evidence := errors }) ∧
    (errors = [] → buildRelevanceMap expected = [] →
      evaluatePrecisionAtK errors expected retrieved k hk matchParentId threshold =
        { status := .notApplicable, score := none, evidence := [] } ∧
      evaluateRecallAtK errors expected retrieved k matchParentId threshold =
        { status := .notApplicable, score := none, evidence := [] } ∧
      evaluateHitRateAtK errors expected retrieved k matchParentId threshold =
        { status := .notApplicable, score := none, evidence := [] } ∧
      evaluateMRR errors expected retrieved matchParentId threshold =
        { status := .notApplicable, score := none, evidence := [] } ∧
      evaluateNDCGAtK w errors expected retrieved k hk matchParentId threshold =
        { status := .notApplicable, score := none, evidence := [] }) := by
  constructor
  · intro herr
    have hprep := prepareIREvaluation_errors_precedence errors expected retrieved matchParentId herr
    refine ⟨?_, ?_, ?_, ?_, ?_⟩
    · simp [evaluatePrecisionAtK, hprep]
    · unfold evaluateRecallAtK; split <;> simp_all
    · simp [evaluateHitRateAtK, hprep]
    · simp [evaluateMRR, hprep]
    · unfold evaluateNDCGAtK; split <;> simp_all
  · rintro rfl hempty
    have hprep : prepareIREvaluation [] expected retrieved matchParentId = .notApplicable := by
      simp [prepareIREvaluation, prepareRetrievalInputs, hempty]
    refine ⟨?_, ?_, ?_, ?_, ?_⟩
    · simp [evaluatePrecisionAtK, hprep]
    · unfold evaluateRecallAtK; split <;> simp_all
    · simp [evaluateHitRateAtK, hprep]
    · simp [evaluateMRR, hprep]
    · unfold evaluateNDCGAtK; split <;> simp_all

/-! ## Universal `[0, 1]` Score Bounds & Abstract-Discount `NDCG@K` Proofs (`FR-004`, `FR-005` #3) -/

/-- `0 ≤ Precision@K ≤ 1` for every `k ≥ 1` and deduplicated ranking. -/
theorem precisionAtK_bounds (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (rankedIds : List String)
    (hndR : rankedIds.Nodup) :
    NNRat.zero ≤ precisionAtK k hk gPos rankedIds ∧
    precisionAtK k hk gPos rankedIds ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  rw [NNRat.le_one_iff]
  exact Nat.le_trans (extractHits_length_le_min k gPos rankedIds hndR) (Nat.min_le_left _ _)

/-- `0 ≤ Recall@K ≤ 1` for every `|G_pos| ≥ 1` and deduplicated ranking. -/
theorem recallAtK_bounds (k : Nat) (gPos : RelevanceMap) (hg : 0 < gPos.length)
    (rankedIds : List String) (hndR : rankedIds.Nodup) :
    NNRat.zero ≤ recallAtK k gPos hg rankedIds ∧
    recallAtK k gPos hg rankedIds ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  rw [NNRat.le_one_iff]
  exact Nat.le_trans (extractHits_length_le_min k gPos rankedIds hndR) (Nat.min_le_right _ _)

/-- `Hit Rate@K` is strictly binary (`0` or `1`). -/
theorem hitRateAtK_binary (k : Nat) (gPos : RelevanceMap) (rankedIds : List String) :
    hitRateAtK k gPos rankedIds = NNRat.zero ∨ hitRateAtK k gPos rankedIds = NNRat.one := by
  unfold hitRateAtK
  split
  · exact Or.inl rfl
  · exact Or.inr rfl

/-- `0 ≤ MRR ≤ 1` universally. -/
theorem mrr_bounds (gPos : RelevanceMap) (rankedIds : List String) :
    NNRat.zero ≤ mrr gPos rankedIds ∧ mrr gPos rankedIds ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  unfold mrr
  split
  · rename_i r cid hmatch
    rw [NNRat.le_one_iff]
    exact firstMatchAux_rank_ge hmatch
  · exact NNRat.zero_le _

/-- `IDCG@K > 0` whenever `k ≥ 1`, `G_pos ≠ []`, and all entries in `G_pos` are positive. -/
theorem idcgAtK_pos (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hpos : ∀ p ∈ gPos, 0 < p.2) :
    NNRat.zero < idcgAtK w k gPos :=
  idcgAtK_pos_core w k hk gPos hg hpos

/-! ### Pure-Core Rearrangement Inequality & Pointwise Domination for `DCG@K ≤ IDCG@K` -/

private def insertDesc (x : Nat) : List Nat → List Nat
  | [] => [x]
  | y :: ys => if y ≤ x then x :: y :: ys else y :: insertDesc x ys

private def insertionSortDesc : List Nat → List Nat
  | [] => []
  | x :: xs => insertDesc x (insertionSortDesc xs)

private theorem insertDesc_perm (x : Nat) (ys : List Nat) :
    (insertDesc x ys).Perm (x :: ys) := by
  induction ys with
  | nil => exact List.Perm.refl _
  | cons y ys ih =>
    unfold insertDesc
    split
    · exact List.Perm.refl _
    · exact (List.Perm.cons y ih).trans (List.Perm.swap x y ys)

private theorem insertionSortDesc_perm (xs : List Nat) :
    (insertionSortDesc xs).Perm xs := by
  induction xs with
  | nil => exact List.Perm.refl _
  | cons x xs ih =>
    unfold insertionSortDesc
    exact (insertDesc_perm x _).trans (List.Perm.cons x ih)

private theorem insertDesc_pairwise (x : Nat) (ys : List Nat)
    (h : List.Pairwise (fun a b => b ≤ a) ys) :
    List.Pairwise (fun a b => b ≤ a) (insertDesc x ys) := by
  induction ys with
  | nil => simp [insertDesc]
  | cons y ys ih =>
    rw [List.pairwise_cons] at h
    unfold insertDesc
    split
    · rename_i hyx
      refine List.pairwise_cons.mpr ⟨?_, List.pairwise_cons.mpr h⟩
      intro z hz
      rw [List.mem_cons] at hz
      rcases hz with rfl | hzs
      · exact hyx
      · exact Nat.le_trans (h.1 z hzs) hyx
    · rename_i hnot
      refine List.pairwise_cons.mpr ⟨?_, ih h.2⟩
      intro z hz
      have hmem : z ∈ x :: ys := (insertDesc_perm x ys).subset hz
      rw [List.mem_cons] at hmem
      rcases hmem with rfl | hzs
      · omega
      · exact h.1 z hzs

private theorem insertionSortDesc_pairwise (xs : List Nat) :
    List.Pairwise (fun a b => b ≤ a) (insertionSortDesc xs) := by
  induction xs with
  | nil => exact List.Pairwise.nil
  | cons x xs ih => exact insertDesc_pairwise x _ ih

private theorem eq_of_perm_pairwise_ge {l₁ l₂ : List Nat}
    (hperm : l₁.Perm l₂)
    (h1 : List.Pairwise (fun a b => b ≤ a) l₁)
    (h2 : List.Pairwise (fun a b => b ≤ a) l₂) : l₁ = l₂ := by
  induction l₁ generalizing l₂ with
  | nil => exact List.Perm.nil_eq hperm
  | cons a as ih =>
    cases l₂ with
    | nil => exact False.elim (List.cons_ne_nil a as (List.Perm.nil_eq hperm.symm).symm)
    | cons b bs =>
      rw [List.pairwise_cons] at h1 h2
      have hab : a ≤ b := by
        have haMem : a ∈ b :: bs := hperm.subset (List.mem_cons_self ..)
        rw [List.mem_cons] at haMem
        rcases haMem with rfl | habs
        · exact Nat.le_refl _
        · exact h2.1 a habs
      have hba : b ≤ a := by
        have hbMem : b ∈ a :: as := hperm.symm.subset (List.mem_cons_self ..)
        rw [List.mem_cons] at hbMem
        rcases hbMem with rfl | hbas
        · exact Nat.le_refl _
        · exact h1.1 b hbas
      have heq : a = b := Nat.le_antisymm hab hba
      subst heq
      exact congrArg (List.cons a) (ih hperm.cons_inv h1.2 h2.2)

private theorem descNatLe_trans (a b c : Nat)
    (hab : descNatLe a b = true) (hbc : descNatLe b c = true) :
    descNatLe a c = true := by
  unfold descNatLe at *
  simp only [decide_eq_true_eq] at hab hbc ⊢
  omega

private theorem descNatLe_total (a b : Nat) :
    (descNatLe a b || descNatLe b a) = true := by
  unfold descNatLe
  simp only [Bool.or_eq_true, decide_eq_true_eq]
  omega

private theorem mergeSort_desc_pairwise (xs : List Nat) :
    List.Pairwise (fun a b => b ≤ a) (xs.mergeSort descNatLe) := by
  have hp := List.pairwise_mergeSort descNatLe_trans descNatLe_total xs
  exact hp.imp (fun {a b} h => by simpa [descNatLe] using h)

private theorem insertionSortDesc_eq_mergeSort (xs : List Nat) :
    insertionSortDesc xs = xs.mergeSort descNatLe := by
  apply eq_of_perm_pairwise_ge
  · exact (insertionSortDesc_perm xs).trans (List.mergeSort_perm xs descNatLe).symm
  · exact insertionSortDesc_pairwise xs
  · exact mergeSort_desc_pairwise xs

private theorem weightedGainSumFrom_insertDesc_le
    (w : DiscountSchedule) (pos : Nat) (hpos : 1 ≤ pos) (x : Nat) (ys : List Nat) :
    weightedGainSumFrom w pos (x :: ys) ≤ weightedGainSumFrom w pos (insertDesc x ys) := by
  induction ys generalizing pos with
  | nil => exact NNRat.le_refl _
  | cons y ys ih =>
    unfold insertDesc
    split
    · exact NNRat.le_refl _
    · rename_i hnot
      have hxy : x ≤ y := by omega
      have hgain : gain x ≤ gain y := gain_mono hxy
      have hw : w.weight (pos + 1) ≤ w.weight pos := w.antitone pos (pos + 1) hpos (Nat.le_succ pos)
      let tail := weightedGainSumFrom w (pos + 2) ys
      let ax := NNRat.scaleNat (gain x) (w.weight pos)
      let by1 := NNRat.scaleNat (gain y) (w.weight (pos + 1))
      let ay := NNRat.scaleNat (gain y) (w.weight pos)
      let bx1 := NNRat.scaleNat (gain x) (w.weight (pos + 1))
      have hswap : ax.add by1 ≤ ay.add bx1 :=
        NNRat.swap_le_of_le (gain x) (gain y) (w.weight pos) (w.weight (pos + 1)) hgain hw
      have hstep1 : ax.add (by1.add tail) ≤ (ax.add by1).add tail :=
        NNRat.le_of_equiv (NNRat.equiv_symm (NNRat.add_assoc_equiv ax by1 tail))
      have hstep2 : (ax.add by1).add tail ≤ (ay.add bx1).add tail :=
        NNRat.add_le_add hswap (NNRat.le_refl tail)
      have hstep3 : (ay.add bx1).add tail ≤ ay.add (bx1.add tail) :=
        NNRat.le_of_equiv (NNRat.add_assoc_equiv ay bx1 tail)
      have hstep4 : ay.add (bx1.add tail) ≤ ay.add (weightedGainSumFrom w (pos + 1) (insertDesc x ys)) :=
        NNRat.add_le_add (NNRat.le_refl ay) (ih (pos + 1) (by omega))
      exact NNRat.le_trans hstep1 (NNRat.le_trans hstep2 (NNRat.le_trans hstep3 hstep4))

private theorem weightedGainSumFrom_le_mergeSort_desc
    (w : DiscountSchedule) (pos : Nat) (hpos : 1 ≤ pos) (xs : List Nat) :
    weightedGainSumFrom w pos xs ≤ weightedGainSumFrom w pos (xs.mergeSort descNatLe) := by
  rw [← insertionSortDesc_eq_mergeSort]
  induction xs generalizing pos with
  | nil => exact NNRat.le_refl _
  | cons x xs ih =>
    unfold insertionSortDesc
    have h1 : weightedGainSumFrom w pos (x :: xs) ≤
        weightedGainSumFrom w pos (x :: insertionSortDesc xs) :=
      NNRat.add_le_add (NNRat.le_refl _) (ih (pos + 1) (by omega))
    exact NNRat.le_trans h1 (weightedGainSumFrom_insertDesc_le w pos hpos x (insertionSortDesc xs))

private theorem lookupRel_mem_of_pos {gPos : RelevanceMap} {cid : String}
    (hpos : 0 < lookupRel gPos cid) : (cid, lookupRel gPos cid) ∈ gPos := by
  induction gPos with
  | nil => simp [lookupRel] at hpos
  | cons p ps ih =>
    cases p with
    | mk k v =>
      unfold lookupRel at hpos ⊢
      by_cases hEq : k = cid
      · subst hEq
        simp only [↓reduceIte]
        exact List.mem_cons_self ..
      · simp only [hEq, ↓reduceIte] at hpos ⊢
        exact List.mem_cons_of_mem (k, v) (ih hpos)

private theorem filter_ge_length_actual_le_ideal
    (k : Nat) (gPos : RelevanceMap) (rankedIds : List String)
    (hndR : rankedIds.Nodup) (t : Nat) (ht : 0 < t) :
    ((actualRelevances k gPos rankedIds).filter (fun r => decide (t ≤ r))).length ≤
    ((gPos.map Prod.snd).filter (fun r => decide (t ≤ r))).length := by
  unfold actualRelevances
  rw [List.filter_map, List.length_map, List.filter_map, List.length_map]
  have hndTake : (rankedIds.take k).Nodup := hndR.sublist (List.take_sublist k rankedIds)
  have hndF : ((rankedIds.take k).filter (fun cid => decide (t ≤ lookupRel gPos cid))).Nodup :=
    hndTake.sublist List.filter_sublist
  have hsub : ∀ cid ∈ (rankedIds.take k).filter (fun cid => decide (t ≤ lookupRel gPos cid)),
      cid ∈ (gPos.filter (fun p => decide (t ≤ p.2))).map Prod.fst := by
    intro cid hcid
    rw [List.mem_filter] at hcid
    have hge : t ≤ lookupRel gPos cid := by simpa using hcid.2
    have hmemG : (cid, lookupRel gPos cid) ∈ gPos :=
      lookupRel_mem_of_pos (Nat.lt_of_lt_of_le ht hge)
    refine List.mem_map.mpr ⟨(cid, lookupRel gPos cid), ?_, rfl⟩
    rw [List.mem_filter]
    exact ⟨hmemG, by simpa using hge⟩
  have hle := nodup_length_le_of_subset hndF hsub
  simpa [List.length_map, Function.comp_def] using hle

private theorem getD_eq_getElem_of_lt {xs : List Nat} {idx : Nat} (h : idx < xs.length) :
    xs.getD idx 0 = xs[idx] := by
  rw [List.getD_eq_getElem?_getD, List.getElem?_eq_getElem h]
  rfl

private theorem getD_eq_default_of_le {xs : List Nat} {idx : Nat} (h : xs.length ≤ idx) :
    xs.getD idx 0 = 0 := by
  rw [List.getD_eq_getElem?_getD, List.getElem?_eq_none h]
  rfl

private theorem pairwise_ge_head_le_all {a : Nat} {as : List Nat}
    (h : List.Pairwise (fun x y => y ≤ x) (a :: as)) (t : Nat) (hat : a < t) :
    ((a :: as).filter (fun x => decide (t ≤ x))).length = 0 := by
  rw [List.pairwise_cons] at h
  rw [List.length_eq_zero_iff, List.filter_eq_nil_iff]
  intro x hx
  simp only [decide_eq_true_eq]
  rw [List.mem_cons] at hx
  rcases hx with rfl | hxs
  · omega
  · have hxa := h.1 x hxs
    omega

private theorem pairwise_ge_filter_head_succ {a : Nat} {as : List Nat}
    (t : Nat) (hta : t ≤ a) :
    ((a :: as).filter (fun x => decide (t ≤ x))).length =
      (as.filter (fun x => decide (t ≤ x))).length + 1 := by
  have hdec : decide (t ≤ a) = true := decide_eq_true hta
  simp [hdec]

private theorem pairwise_ge_index_le_of_filter_le
    {as bs : List Nat}
    (has : List.Pairwise (fun x y => y ≤ x) as)
    (hbs : List.Pairwise (fun x y => y ≤ x) bs)
    (hcnt : ∀ t, 0 < t →
      (as.filter (fun x => decide (t ≤ x))).length ≤
      (bs.filter (fun x => decide (t ≤ x))).length) :
    ∀ idx, as.getD idx 0 ≤ bs.getD idx 0 := by
  intro idx
  induction idx generalizing as bs with
  | zero =>
    cases as with
    | nil => exact Nat.zero_le _
    | cons a as' =>
      by_cases ha0 : a = 0
      · simp [ha0]
      · have hapos : 0 < a := Nat.pos_of_ne_zero ha0
        have h1 : 1 ≤ ((a :: as').filter (fun x => decide (a ≤ x))).length := by
          rw [pairwise_ge_filter_head_succ a (Nat.le_refl a)]
          omega
        have hb1 : 1 ≤ (bs.filter (fun x => decide (a ≤ x))).length :=
          Nat.le_trans h1 (hcnt a hapos)
        cases bs with
        | nil => simp at hb1
        | cons b bs' =>
          simp only [List.getD_cons_zero]
          by_cases hba : a ≤ b
          · exact hba
          · have hlt : b < a := by omega
            have hz := pairwise_ge_head_le_all hbs a hlt
            omega
  | succ n ih =>
    cases as with
    | nil => exact Nat.zero_le _
    | cons a as' =>
      cases bs with
      | nil =>
        simp only [List.getD_cons_succ, List.getD_nil]
        by_cases hval : as'.getD n 0 = 0
        · omega
        · have hpos : 0 < as'.getD n 0 := Nat.pos_of_ne_zero hval
          have hmem : as'.getD n 0 ∈ as' := by
            by_cases hlt : n < as'.length
            · rw [getD_eq_getElem_of_lt hlt]
              exact List.getElem_mem hlt
            · rw [getD_eq_default_of_le (Nat.le_of_not_lt hlt)] at hval
              exact False.elim (hval rfl)
          have hfa : 1 ≤ ((a :: as').filter (fun x => decide (as'.getD n 0 ≤ x))).length := by
            have hmemF : as'.getD n 0 ∈ (a :: as').filter (fun x => decide (as'.getD n 0 ≤ x)) := by
              rw [List.mem_filter]
              exact ⟨List.mem_cons_of_mem a hmem, decide_eq_true (Nat.le_refl _)⟩
            exact List.length_pos_of_mem hmemF
          have hfb := hcnt (as'.getD n 0) hpos
          simp only [List.filter_nil, List.length_nil] at hfb
          omega
      | cons b bs' =>
        simp only [List.getD_cons_succ]
        rw [List.pairwise_cons] at has hbs
        apply ih has.2 hbs.2
        intro t ht
        have htot := hcnt t ht
        by_cases hta : t ≤ a
        · rw [pairwise_ge_filter_head_succ t hta] at htot
          by_cases htb : t ≤ b
          · rw [pairwise_ge_filter_head_succ t htb] at htot
            omega
          · have hz := pairwise_ge_head_le_all (List.pairwise_cons.mpr hbs) t (by omega)
            omega
        · have hzA : (as'.filter (fun x => decide (t ≤ x))).length = 0 := by
            rw [List.length_eq_zero_iff, List.filter_eq_nil_iff]
            intro x hx
            have hxa := has.1 x hx
            simp only [decide_eq_true_eq]
            omega
          omega

private theorem weightedGainSumFrom_zero_of_all_zero
    (w : DiscountSchedule) (pos : Nat) (as : List Nat) (h : ∀ x ∈ as, x = 0) :
    weightedGainSumFrom w pos as ≈ NNRat.zero := by
  induction as generalizing pos with
  | nil => exact NNRat.equiv_refl _
  | cons a as' ih =>
    have ha : a = 0 := h a (List.mem_cons_self ..)
    have htail : weightedGainSumFrom w (pos + 1) as' ≈ NNRat.zero :=
      ih (pos + 1) (fun x hx => h x (List.mem_cons_of_mem a hx))
    unfold weightedGainSumFrom
    rw [ha, gain_zero]
    have hz1 : NNRat.scaleNat 0 (w.weight pos) ≈ NNRat.zero := NNRat.scaleNat_zero_equiv _
    have hle1 : (NNRat.scaleNat 0 (w.weight pos)).add (weightedGainSumFrom w (pos + 1) as') ≤
        NNRat.zero.add NNRat.zero :=
      NNRat.add_le_add (NNRat.le_of_equiv hz1) (NNRat.le_of_equiv htail)
    have hle2 : NNRat.zero.add NNRat.zero ≤ NNRat.zero :=
      NNRat.le_of_equiv (NNRat.add_zero_right_equiv NNRat.zero)
    exact NNRat.equiv_of_le_antisymm (NNRat.le_trans hle1 hle2) (NNRat.zero_le _)

private theorem weightedGainSumFrom_le_of_pointwise
    (w : DiscountSchedule) (pos : Nat) (as bs : List Nat)
    (hpt : ∀ idx, as.getD idx 0 ≤ bs.getD idx 0) :
    weightedGainSumFrom w pos as ≤ weightedGainSumFrom w pos bs := by
  induction as generalizing bs pos with
  | nil => exact NNRat.zero_le _
  | cons a as' ih =>
    cases bs with
    | nil =>
      have hall : ∀ x ∈ a :: as', x = 0 := by
        intro x hx
        obtain ⟨i, hi, rfl⟩ := List.getElem_of_mem hx
        have hle := hpt i
        rw [getD_eq_getElem_of_lt hi, List.getD_nil] at hle
        omega
      exact NNRat.le_of_equiv (weightedGainSumFrom_zero_of_all_zero w pos (a :: as') hall)
    | cons b bs' =>
      have hhead : a ≤ b := by simpa using hpt 0
      have htail : ∀ idx, as'.getD idx 0 ≤ bs'.getD idx 0 := by
        intro idx
        simpa using hpt (idx + 1)
      unfold weightedGainSumFrom
      exact NNRat.add_le_add
        (NNRat.scaleNat_le_scaleNat (gain_mono hhead) (NNRat.le_refl _))
        (ih (pos + 1) bs' htail)

/--
Universal `NDCG@K` numerator bound: for any positive non-increasing `DiscountSchedule`,
deduplicated retrieval satisfies `DCG@K ≤ IDCG@K`.
-/
theorem dcgAtK_le_idcgAtK
    (w : DiscountSchedule) (k : Nat) (gPos : RelevanceMap) (rankedIds : List String)
    (hndR : rankedIds.Nodup) :
    dcgAtK w k gPos rankedIds ≤ idcgAtK w k gPos := by
  unfold dcgAtK idcgAtK idealRelevances
  let actual := actualRelevances k gPos rankedIds
  let actualSorted := actual.mergeSort descNatLe
  let idealAll := (gPos.map Prod.snd).mergeSort descNatLe
  have h1 : weightedGainSumFrom w 1 actual ≤ weightedGainSumFrom w 1 actualSorted :=
    weightedGainSumFrom_le_mergeSort_desc w 1 (Nat.le_refl 1) actual
  have hpermA : actualSorted.Perm actual := List.mergeSort_perm actual descNatLe
  have hpermI : idealAll.Perm (gPos.map Prod.snd) := List.mergeSort_perm _ descNatLe
  have hcnt : ∀ t, 0 < t →
      (actualSorted.filter (fun x => decide (t ≤ x))).length ≤
      (idealAll.filter (fun x => decide (t ≤ x))).length := by
    intro t ht
    rw [(hpermA.filter _).length_eq, (hpermI.filter _).length_eq]
    exact filter_ge_length_actual_le_ideal k gPos rankedIds hndR t ht
  have hptAll : ∀ idx, actualSorted.getD idx 0 ≤ idealAll.getD idx 0 :=
    pairwise_ge_index_le_of_filter_le
      (mergeSort_desc_pairwise actual) (mergeSort_desc_pairwise (gPos.map Prod.snd)) hcnt
  have hlenA : actualSorted.length ≤ k := by
    rw [hpermA.length_eq]
    unfold actual actualRelevances
    rw [List.length_map, List.length_take]
    exact Nat.min_le_left _ _
  have hptTake : ∀ idx, actualSorted.getD idx 0 ≤ (idealAll.take k).getD idx 0 := by
    intro idx
    by_cases hlt : idx < k
    · have htakeEq : (idealAll.take k).getD idx 0 = idealAll.getD idx 0 := by
        by_cases hi : idx < idealAll.length
        · have hiTake : idx < (idealAll.take k).length := by
            rw [List.length_take]
            exact Nat.lt_min.mpr ⟨hlt, hi⟩
          rw [getD_eq_getElem_of_lt hiTake, getD_eq_getElem_of_lt hi, List.getElem_take]
        · have hgeTake : (idealAll.take k).length ≤ idx := by
            rw [List.length_take]
            have : idealAll.length ≤ idx := Nat.le_of_not_lt hi
            exact Nat.le_trans (Nat.min_le_right _ _) this
          rw [getD_eq_default_of_le hgeTake, getD_eq_default_of_le (Nat.le_of_not_lt hi)]
      rw [htakeEq]
      exact hptAll idx
    · have hgeA : actualSorted.length ≤ idx := Nat.le_trans hlenA (Nat.le_of_not_lt hlt)
      rw [getD_eq_default_of_le hgeA]
      exact Nat.zero_le _
  exact NNRat.le_trans h1 (weightedGainSumFrom_le_of_pointwise w 1 actualSorted (idealAll.take k) hptTake)

/-- Universal `[0, 1]` bounds for `NDCG@K` over any `DiscountSchedule`. -/
theorem ndcgAtK_bounds
    (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hpos : ∀ p ∈ gPos, 0 < p.2)
    (rankedIds : List String) (hndR : rankedIds.Nodup) :
    NNRat.zero ≤ ndcgAtK w k hk gPos hg hpos rankedIds ∧
    ndcgAtK w k hk gPos hg hpos rankedIds ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  unfold ndcgAtK
  exact NNRat.div_le_one_of_le (dcgAtK_le_idcgAtK w k gPos rankedIds hndR) _

/-! ## Cutoff Monotonicity in `K` (`FR-005` #4) -/

private theorem take_sublist_of_le {α : Type} {k₁ k₂ : Nat} (hk : k₁ ≤ k₂) (xs : List α) :
    (xs.take k₁).Sublist (xs.take k₂) := by
  induction xs generalizing k₁ k₂ with
  | nil => simp
  | cons x xs ih =>
    cases k₁ with
    | zero => exact List.nil_sublist _
    | succ n₁ =>
      cases k₂ with
      | zero => omega
      | succ n₂ =>
        simp only [List.take_succ_cons]
        exact List.Sublist.cons_cons x (ih (Nat.le_of_succ_le_succ hk))

/-- Hit count is monotonically non-decreasing in cutoff `K`. -/
theorem extractHits_length_mono {k₁ k₂ : Nat} (hk : k₁ ≤ k₂)
    (gPos : RelevanceMap) (rankedIds : List String) :
    (extractHits k₁ gPos rankedIds).length ≤ (extractHits k₂ gPos rankedIds).length := by
  unfold extractHits
  exact ((take_sublist_of_le hk rankedIds).filter (memGPos gPos)).length_le

/-- `Recall@K` is monotonically non-decreasing in cutoff `K`. -/
theorem recallAtK_mono {k₁ k₂ : Nat} (hk : k₁ ≤ k₂)
    (gPos : RelevanceMap) (hg : 0 < gPos.length) (rankedIds : List String) :
    recallAtK k₁ gPos hg rankedIds ≤ recallAtK k₂ gPos hg rankedIds := by
  show (extractHits k₁ gPos rankedIds).length * gPos.length ≤
       (extractHits k₂ gPos rankedIds).length * gPos.length
  exact Nat.mul_le_mul_right gPos.length (extractHits_length_mono hk gPos rankedIds)

/-- `Hit Rate@K` is monotonically non-decreasing in cutoff `K`. -/
theorem hitRateAtK_mono {k₁ k₂ : Nat} (hk : k₁ ≤ k₂)
    (gPos : RelevanceMap) (rankedIds : List String) :
    hitRateAtK k₁ gPos rankedIds ≤ hitRateAtK k₂ gPos rankedIds := by
  unfold hitRateAtK
  cases h1 : (extractHits k₁ gPos rankedIds).isEmpty with
  | true => exact NNRat.zero_le _
  | false =>
    have hpos1 : 0 < (extractHits k₁ gPos rankedIds).length := by
      cases hEq : extractHits k₁ gPos rankedIds with
      | nil => simp [hEq] at h1
      | cons _ _ => exact Nat.succ_pos _
    have hpos2 : 0 < (extractHits k₂ gPos rankedIds).length :=
      Nat.lt_of_lt_of_le hpos1 (extractHits_length_mono hk gPos rankedIds)
    cases h2 : extractHits k₂ gPos rankedIds with
    | nil => simp [h2] at hpos2
    | cons _ _ =>
      simp only [List.isEmpty_cons, Bool.false_eq_true, ↓reduceIte]
      exact NNRat.le_refl _

private theorem weightedGainSumFrom_append_le
    (w : DiscountSchedule) (pos : Nat) (xs ys : List Nat) :
    weightedGainSumFrom w pos xs ≤ weightedGainSumFrom w pos (xs ++ ys) := by
  induction xs generalizing pos with
  | nil => exact NNRat.zero_le _
  | cons x xs ih =>
    simp only [List.cons_append, weightedGainSumFrom]
    exact NNRat.add_le_add (NNRat.le_refl _) (ih (pos + 1))

private theorem take_prefix_append {α : Type} {k₁ k₂ : Nat} (hk : k₁ ≤ k₂) (xs : List α) :
    ∃ rest, xs.take k₂ = xs.take k₁ ++ rest := by
  induction xs generalizing k₁ k₂ with
  | nil => exact ⟨[], by simp⟩
  | cons x xs ih =>
    cases k₁ with
    | zero => exact ⟨(x :: xs).take k₂, by simp⟩
    | succ n₁ =>
      cases k₂ with
      | zero => omega
      | succ n₂ =>
        obtain ⟨rest, hrest⟩ := ih (Nat.le_of_succ_le_succ hk)
        exact ⟨rest, by simp [List.take_succ_cons, hrest]⟩

/-- `DCG@K` is monotonically non-decreasing in cutoff `K`. -/
theorem dcgAtK_mono (w : DiscountSchedule) {k₁ k₂ : Nat} (hk : k₁ ≤ k₂)
    (gPos : RelevanceMap) (rankedIds : List String) :
    dcgAtK w k₁ gPos rankedIds ≤ dcgAtK w k₂ gPos rankedIds := by
  unfold dcgAtK actualRelevances
  obtain ⟨rest, hrest⟩ := take_prefix_append hk rankedIds
  rw [hrest, List.map_append]
  exact weightedGainSumFrom_append_le w 1 _ _

/-- `IDCG@K` is monotonically non-decreasing in cutoff `K`. -/
theorem idcgAtK_mono (w : DiscountSchedule) {k₁ k₂ : Nat} (hk : k₁ ≤ k₂)
    (gPos : RelevanceMap) :
    idcgAtK w k₁ gPos ≤ idcgAtK w k₂ gPos := by
  unfold idcgAtK idealRelevances
  obtain ⟨rest, hrest⟩ := take_prefix_append hk ((gPos.map Prod.snd).mergeSort descNatLe)
  rw [hrest]
  exact weightedGainSumFrom_append_le w 1 _ _

/-! ## Cross-Metric Identities & Boundary Characterizations (`FR-005` #5) -/

/-- Exact rational cross-metric identity: `Precision@K · K = Recall@K · |G_pos|`. -/
theorem precision_recall_exact_identity
    (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (hg : 0 < gPos.length)
    (rankedIds : List String) :
    (precisionAtK k hk gPos rankedIds).mul (NNRat.ofNat k) ≈
    (recallAtK k gPos hg rankedIds).mul (NNRat.ofNat gPos.length) := by
  show ((extractHits k gPos rankedIds).length * k) * (gPos.length * 1) =
       ((extractHits k gPos rankedIds).length * gPos.length) * (k * 1)
  simp only [Nat.mul_one]
  exact Nat.mul_right_comm _ _ _

/-- `Hit Rate@K = 1 ↔ Precision@K > 0`. -/
theorem hitRate_one_iff_precision_pos
    (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (rankedIds : List String) :
    hitRateAtK k gPos rankedIds = NNRat.one ↔ NNRat.zero < precisionAtK k hk gPos rankedIds := by
  unfold hitRateAtK precisionAtK
  rw [NNRat.zero_lt_iff]
  cases h : extractHits k gPos rankedIds with
  | nil => simp [NNRat.zero, NNRat.one]
  | cons _ _ => simp

/-- `Hit Rate@K = 1 ↔ Recall@K > 0`. -/
theorem hitRate_one_iff_recall_pos
    (k : Nat) (gPos : RelevanceMap) (hg : 0 < gPos.length) (rankedIds : List String) :
    hitRateAtK k gPos rankedIds = NNRat.one ↔ NNRat.zero < recallAtK k gPos hg rankedIds := by
  unfold hitRateAtK recallAtK
  rw [NNRat.zero_lt_iff]
  cases h : extractHits k gPos rankedIds with
  | nil => simp [NNRat.zero, NNRat.one]
  | cons _ _ => simp

/-- `Hit Rate@K = 0 ↔ hits = [] ↔ Precision@K = 0 ↔ Recall@K = 0`. -/
theorem hitRate_zero_iff_no_hits
    (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (hg : 0 < gPos.length)
    (rankedIds : List String) :
    (hitRateAtK k gPos rankedIds = NNRat.zero ↔ extractHits k gPos rankedIds = []) ∧
    (hitRateAtK k gPos rankedIds = NNRat.zero ↔ precisionAtK k hk gPos rankedIds ≈ NNRat.zero) ∧
    (hitRateAtK k gPos rankedIds = NNRat.zero ↔ recallAtK k gPos hg rankedIds ≈ NNRat.zero) := by
  unfold hitRateAtK precisionAtK recallAtK
  rw [NNRat.equiv_zero_iff, NNRat.equiv_zero_iff]
  cases h : extractHits k gPos rankedIds with
  | nil => simp [NNRat.zero]
  | cons _ _ => simp [NNRat.zero, NNRat.one]

/-- `MRR = 1 ↔` rank-1 deduplicated chunk is in `G_pos`. -/
theorem mrr_eq_one_iff_rank_one_relevant (gPos : RelevanceMap) (rankedIds : List String) :
    mrr gPos rankedIds ≈ NNRat.one ↔
      ∃ cid rest, rankedIds = cid :: rest ∧ memGPos gPos cid = true := by
  cases rankedIds with
  | nil =>
    simp [mrr, firstMatch, firstMatchAux, NNRat.equiv, NNRat.zero, NNRat.one]
  | cons cid rest =>
    by_cases hm : memGPos gPos cid = true
    · constructor
      · intro _; exact ⟨cid, rest, rfl, hm⟩
      · intro _
        have hfm : firstMatch gPos (cid :: rest) = some (1, cid) := by
          simp [firstMatch, firstMatchAux, hm]
        unfold mrr
        split
        · rename_i r _ hmatch
          rw [hfm] at hmatch
          cases hmatch
          exact NNRat.equiv_refl _
        · rename_i hnone
          rw [hfm] at hnone
          cases hnone
    · have hmf : memGPos gPos cid = false := Bool.eq_false_iff.mpr hm
      constructor
      · intro heq
        unfold mrr at heq
        have hfm : firstMatch gPos (cid :: rest) = firstMatchAux 2 gPos rest := by
          simp [firstMatch, firstMatchAux, hmf]
        split at heq
        · rename_i r matched hmatch
          rw [NNRat.equiv_one_iff] at heq
          rw [hfm] at hmatch
          have hge : 2 ≤ r := firstMatchAux_rank_ge hmatch
          have hr1 : 1 = r := heq
          omega
        · simp [NNRat.equiv, NNRat.zero, NNRat.one] at heq
      · rintro ⟨c', r', hcons, hc'⟩
        cases hcons
        exact False.elim (hm hc')

private theorem firstMatchAux_none_iff (rank : Nat) (gPos : RelevanceMap) (xs : List String) :
    firstMatchAux rank gPos xs = none ↔ ∀ cid ∈ xs, memGPos gPos cid = false := by
  induction xs generalizing rank with
  | nil => simp [firstMatchAux]
  | cons x xs ih =>
    unfold firstMatchAux
    cases hm : memGPos gPos x with
    | true =>
      simp only [↓reduceIte, reduceCtorEq, false_iff]
      intro hall
      have hx := hall x (List.mem_cons_self ..)
      simp [hm] at hx
    | false =>
      simp only [Bool.false_eq_true, ↓reduceIte, ih, List.mem_cons]
      constructor
      · intro h cid hcid
        rcases hcid with rfl | hrest
        · exact hm
        · exact h cid hrest
      · intro h cid hcid
        exact h cid (Or.inr hcid)

/-- `MRR = 0 ↔` no deduplicated retrieved chunk is relevant. -/
theorem mrr_eq_zero_iff_no_relevant (gPos : RelevanceMap) (rankedIds : List String) :
    mrr gPos rankedIds ≈ NNRat.zero ↔ ∀ cid ∈ rankedIds, memGPos gPos cid = false := by
  unfold mrr
  split
  · rename_i r cid hmatch
    rw [NNRat.equiv_zero_iff]
    simp only [Nat.one_ne_zero, false_iff]
    intro hall
    have hnone := (firstMatchAux_none_iff 1 gPos rankedIds).mpr hall
    rw [show firstMatch gPos rankedIds = none from hnone] at hmatch
    cases hmatch
  · rename_i hnone
    constructor
    · intro _
      exact (firstMatchAux_none_iff 1 gPos rankedIds).mp hnone
    · intro _
      exact NNRat.equiv_refl _

private theorem firstMatchAux_le_of_mem_take (rank k : Nat) (gPos : RelevanceMap) (xs : List String)
    (hne : ((xs.take k).filter (memGPos gPos)) ≠ []) :
    ∃ r cid, firstMatchAux rank gPos xs = some (r, cid) ∧ r + 1 ≤ rank + k := by
  induction xs generalizing rank k with
  | nil => simp at hne
  | cons x xs ih =>
    cases k with
    | zero => simp at hne
    | succ k' =>
      cases hm : memGPos gPos x with
      | true =>
        refine ⟨rank, x, ?_, by omega⟩
        simp [firstMatchAux, hm]
      | false =>
        simp only [List.take_succ_cons, List.filter_cons, hm, Bool.false_eq_true, ↓reduceIte] at hne
        obtain ⟨r, cid, hrec, hle⟩ := ih (rank + 1) k' hne
        refine ⟨r, cid, ?_, by omega⟩
        simp [firstMatchAux, hm, hrec]

/-- If `Hit Rate@K = 1`, then the first relevant hit appears at rank `≤ K`, so `MRR ≥ 1 / K`. -/
theorem hitRate_one_implies_mrr_ge_inv_k
    (k : Nat) (hk : 0 < k) (gPos : RelevanceMap) (rankedIds : List String)
    (hhr : hitRateAtK k gPos rankedIds = NNRat.one) :
    NNRat.mkNat 1 k hk ≤ mrr gPos rankedIds := by
  have hne : extractHits k gPos rankedIds ≠ [] := by
    intro hempty
    unfold hitRateAtK at hhr
    simp [hempty, NNRat.zero, NNRat.one] at hhr
  obtain ⟨r, cid, hmatch, hle⟩ := firstMatchAux_le_of_mem_take 1 k gPos rankedIds hne
  unfold mrr
  have hfm : firstMatch gPos rankedIds = some (r, cid) := hmatch
  split
  · rename_i r' cid' hmatch'
    rw [hfm] at hmatch'
    cases hmatch'
    show 1 * r ≤ 1 * k
    omega
  · rename_i hnone
    rw [hfm] at hnone
    cases hnone

/-- Empty retrieval (`rankedIds = []`) yields exact `0` across all 5 IR metrics. -/
theorem empty_retrieval_scores_zero
    (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hgLen : 0 < gPos.length)
    (hpos : ∀ p ∈ gPos, 0 < p.2) :
    precisionAtK k hk gPos [] ≈ NNRat.zero ∧
    recallAtK k gPos hgLen [] ≈ NNRat.zero ∧
    hitRateAtK k gPos [] ≈ NNRat.zero ∧
    mrr gPos [] ≈ NNRat.zero ∧
    ndcgAtK w k hk gPos hg hpos [] ≈ NNRat.zero := by
  refine ⟨?_, ?_, ?_, ?_, ?_⟩
  · simp [precisionAtK, extractHits, NNRat.equiv, NNRat.zero]
  · simp [recallAtK, extractHits, NNRat.equiv, NNRat.zero]
  · simp [hitRateAtK, extractHits, NNRat.equiv, NNRat.zero]
  · simp [mrr, firstMatch, firstMatchAux, NNRat.equiv, NNRat.zero]
  · unfold ndcgAtK dcgAtK actualRelevances weightedGainSumFrom
    simp only [List.take_nil, List.map_nil]
    exact NNRat.div_zero_equiv_zero _ _

/-- Optimal descending ranking of `G_pos` keys by relevance weight. -/
def optimalRankedIds (gPos : RelevanceMap) : List String :=
  (gPos.mergeSort (fun a b => decide (b.2 ≤ a.2))).map Prod.fst

private theorem lookupRel_of_nodup_mem {gPos : RelevanceMap} (hnd : (gPos.map Prod.fst).Nodup)
    {p : String × Nat} (hp : p ∈ gPos) : lookupRel gPos p.1 = p.2 := by
  induction gPos with
  | nil => cases hp
  | cons hd tl ih =>
    cases hd with
    | mk k v =>
      simp only [List.map_cons, List.nodup_cons] at hnd
      rw [List.mem_cons] at hp
      unfold lookupRel
      rcases hp with rfl | htl
      · simp
      · have hne : k ≠ p.1 := by
          intro heq
          subst heq
          exact hnd.1 (List.mem_map.mpr ⟨p, htl, rfl⟩)
        simp only [hne, ↓reduceIte]
        exact ih hnd.2 htl

private theorem relPairLe_trans (a b c : String × Nat)
    (hab : decide (b.2 ≤ a.2) = true) (hbc : decide (c.2 ≤ b.2) = true) :
    decide (c.2 ≤ a.2) = true := by
  simp only [decide_eq_true_eq] at hab hbc ⊢
  omega

private theorem relPairLe_total (a b : String × Nat) :
    (decide (b.2 ≤ a.2) || decide (a.2 ≤ b.2)) = true := by
  simp only [Bool.or_eq_true, decide_eq_true_eq]
  omega

/-- Retrieving `G_pos` keys sorted descending by relevance achieves optimal `NDCG@K = 1`. -/
theorem ndcgAtK_optimal_order_eq_one
    (w : DiscountSchedule) (k : Nat) (hk : 0 < k)
    (gPos : RelevanceMap) (hg : gPos ≠ []) (hpos : ∀ p ∈ gPos, 0 < p.2)
    (hndG : (gPos.map Prod.fst).Nodup) :
    ndcgAtK w k hk gPos hg hpos (optimalRankedIds gPos) ≈ NNRat.one := by
  unfold ndcgAtK
  have heq : dcgAtK w k gPos (optimalRankedIds gPos) = idcgAtK w k gPos := by
    unfold dcgAtK idcgAtK actualRelevances idealRelevances optimalRankedIds
    let sortedPairs := gPos.mergeSort (fun a b => decide (b.2 ≤ a.2))
    have hpermP : sortedPairs.Perm gPos := List.mergeSort_perm _ _
    have hpwPairs : List.Pairwise (fun a b => b.2 ≤ a.2) sortedPairs := by
      have hp := List.pairwise_mergeSort relPairLe_trans relPairLe_total gPos
      exact hp.imp (fun {a b} h => by simpa using h)
    have hpwSnd : List.Pairwise (fun a b => b ≤ a) (sortedPairs.map Prod.snd) := by
      rw [List.pairwise_map]
      exact hpwPairs
    have hvalsEq : sortedPairs.map Prod.snd = (gPos.map Prod.snd).mergeSort descNatLe := by
      apply eq_of_perm_pairwise_ge
      · exact (hpermP.map Prod.snd).trans (List.mergeSort_perm _ _).symm
      · exact hpwSnd
      · exact mergeSort_desc_pairwise (gPos.map Prod.snd)
    have hmapEq : (sortedPairs.map Prod.fst).map (lookupRel gPos) = sortedPairs.map Prod.snd := by
      rw [List.map_map]
      apply List.map_congr_left
      intro p hp
      exact lookupRel_of_nodup_mem hndG (hpermP.subset hp)
    have hfin : (List.take k (List.map Prod.fst sortedPairs)).map (lookupRel gPos) =
        List.take k ((gPos.map Prod.snd).mergeSort descNatLe) := by
      rw [List.map_take, hmapEq, hvalsEq]
    exact congrArg (weightedGainSumFrom w 1) hfin
  rw [heq]
  exact NNRat.div_self_equiv_one _ _

/-! ## Threshold Finalization Soundness (`FR-005` #6) -/

/-- Numeric finalization yields `PASS` iff `threshold ≤ score`. -/
theorem finalizeOutcome_pass_iff (score threshold : NNRat) (evidence : List String) :
    (finalizeOutcome score threshold evidence).status = .pass ↔ threshold ≤ score := by
  unfold finalizeOutcome
  cases hb : NNRat.leBool threshold score with
  | true =>
    simp only [↓reduceIte, true_iff]
    exact (NNRat.leBool_true_iff threshold score).mp hb
  | false =>
    simp only [Bool.false_eq_true, ↓reduceIte, reduceCtorEq, false_iff]
    have hlt := (NNRat.leBool_false_iff threshold score).mp hb
    exact (NNRat.lt_iff_not_le score threshold).mp hlt

/-- Numeric finalization yields `FAIL` iff `score < threshold`. -/
theorem finalizeOutcome_fail_iff (score threshold : NNRat) (evidence : List String) :
    (finalizeOutcome score threshold evidence).status = .fail ↔ score < threshold := by
  unfold finalizeOutcome
  cases hb : NNRat.leBool threshold score with
  | true =>
    simp only [↓reduceIte, reduceCtorEq, false_iff]
    have hle := (NNRat.leBool_true_iff threshold score).mp hb
    intro hlt
    exact (NNRat.lt_iff_not_le score threshold).mp hlt hle
  | false =>
    simp only [Bool.false_eq_true, ↓reduceIte, true_iff]
    exact (NNRat.leBool_false_iff threshold score).mp hb

/-- `PASS` and `FAIL` are exhaustive and mutually exclusive on numeric outcomes. -/
theorem finalizeOutcome_pass_fail_mutex (score threshold : NNRat) (evidence : List String) :
    ((finalizeOutcome score threshold evidence).status = .pass ∨
     (finalizeOutcome score threshold evidence).status = .fail) ∧
    ¬ ((finalizeOutcome score threshold evidence).status = .pass ∧
       (finalizeOutcome score threshold evidence).status = .fail) := by
  unfold finalizeOutcome
  cases NNRat.leBool threshold score <;> simp

end EvalForgeFormal.Retrieval
