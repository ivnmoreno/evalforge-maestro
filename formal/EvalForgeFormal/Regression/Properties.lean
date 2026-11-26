import EvalForgeFormal.Regression.Types
import EvalForgeFormal.Regression.Anomaly
import EvalForgeFormal.Regression.Drift
import EvalForgeFormal.Regression.Trend

namespace EvalForgeFormal.Regression

open EvalForgeFormal.Retrieval (NNRat dedupPreserveFirst dedupPreserveFirstAux)
open EvalForgeFormal.Calibration (SignedRat nnAbsDiff nnAbsDiff_le_one_of_unit nnAbsDiff_equiv_congr
  nnrat_lt_of_equiv_right)
open EvalForgeFormal.Stats (sOne sNegOne ofNNRat sNeg sAdd sSub sMul sDivNat sLe sLt sMeanList
  sLe_refl sLe_trans sLe_of_equiv sLe_of_equiv_left sLe_of_equiv_right
  sNeg_equiv_congr sNeg_le_sNeg_iff sNeg_sAdd_equiv sAdd_comm_equiv sAdd_assoc_equiv
  sAdd_equiv_congr sDivNat_equiv_congr sEquiv_zero_iff sNeg_zero_equiv)

/-!
# Formal Properties for Anti-Masking Anomalies, OLS Trend Analysis & Provenance Drift

32 machine-checked theorems in pure Lean 4 `Init` (zero Mathlib, zero `sorry`, strictly audited
under `{propext, Classical.choice, Quot.sound}` in `EvalForgeAudit.lean`):
- Group 1 (7): Disagreement spread `[0, 1]` bounds, permutation invariance, singleton/empty
  immunity, and `INCONCLUSIVE_SPIKE` rate bounds and biconditional.
- Group 2 (7): Anti-masking soundness (`MANDATORY_CASE_FAILURE`, macro-masked mandatory failure
  and metric floor breaches, comparison-masked metric drops, healthy-aggregate masked case drops,
  `DATASET_CAPPED` biconditional, clean compliant run zero-anomaly guarantee).
- Group 3 (10): Exact OLS trend algebra (`INSUFFICIENT_DATA` biconditional, point conservation,
  centered covariance equivalence, constant zero-slope & `STABLE`, exact linear recovery, vertical
  shift invariance, time-reversal anti-symmetry and direction duality, sharp universal unit bound
  `3m / (2(m^2 - 1)) ≤ 1`, exhaustive 3-way partition & threshold-tightening monotonicity).
- Group 4 (8): Provenance & cohort drift soundness (irreflexivity, uncapped reflexivity,
  baseline/candidate swap category symmetry, intentional target-change isolation, identical
  uncapped window zero-drift, adjacent window soundness, cohort empty-side guard, and 4-tuple
  deduplication `Nodup`).
-/

/-! ## Helper Lemmas: `listMinAux`, `listMaxAux`, `extractNumericPairs` -/

private theorem listMinAux_le_cur (cur : NNRat) (xs : List NNRat) :
    listMinAux cur xs ≤ cur := by
  induction xs generalizing cur with
  | nil => exact NNRat.le_refl cur
  | cons x xs ih =>
    unfold listMinAux
    by_cases h : NNRat.leBool x cur = true
    · simp only [h, ↓reduceIte]
      exact NNRat.le_trans (ih x) ((NNRat.leBool_true_iff x cur).mp h)
    · have hf : NNRat.leBool x cur = false := by cases hb : NNRat.leBool x cur <;> simp_all
      simp only [hf, Bool.false_eq_true, ↓reduceIte]
      exact ih cur

private theorem listMinAux_le_mem (cur : NNRat) (xs : List NNRat) {y : NNRat} (hy : y ∈ xs) :
    listMinAux cur xs ≤ y := by
  induction xs generalizing cur with
  | nil => simp at hy
  | cons x xs ih =>
    unfold listMinAux
    simp only [List.mem_cons] at hy
    rcases hy with rfl | htail
    · by_cases h : NNRat.leBool y cur = true
      · simp only [h, ↓reduceIte]
        exact listMinAux_le_cur y xs
      · have hf : NNRat.leBool y cur = false := by cases hb : NNRat.leBool y cur <;> simp_all
        simp only [hf, Bool.false_eq_true, ↓reduceIte]
        have hlt : cur < y := (NNRat.leBool_false_iff y cur).mp hf
        exact NNRat.le_trans (listMinAux_le_cur cur xs) (NNRat.le_of_lt hlt)
    · by_cases h : NNRat.leBool x cur = true
      · simp only [h, ↓reduceIte]
        exact ih x htail
      · have hf : NNRat.leBool x cur = false := by cases hb : NNRat.leBool x cur <;> simp_all
        simp only [hf, Bool.false_eq_true, ↓reduceIte]
        exact ih cur htail

private theorem listMinAux_mem_or_cur (cur : NNRat) (xs : List NNRat) :
    listMinAux cur xs = cur ∨ listMinAux cur xs ∈ xs := by
  induction xs generalizing cur with
  | nil => exact Or.inl rfl
  | cons x xs ih =>
    unfold listMinAux
    by_cases h : NNRat.leBool x cur = true
    · simp only [h, ↓reduceIte]
      rcases ih x with hEq | hMem
      · exact Or.inr (by rw [hEq]; exact List.mem_cons_self ..)
      · exact Or.inr (List.mem_cons_of_mem x hMem)
    · have hf : NNRat.leBool x cur = false := by cases hb : NNRat.leBool x cur <;> simp_all
      simp only [hf, Bool.false_eq_true, ↓reduceIte]
      rcases ih cur with hEq | hMem
      · exact Or.inl hEq
      · exact Or.inr (List.mem_cons_of_mem x hMem)

private theorem cur_le_listMaxAux (cur : NNRat) (xs : List NNRat) :
    cur ≤ listMaxAux cur xs := by
  induction xs generalizing cur with
  | nil => exact NNRat.le_refl cur
  | cons x xs ih =>
    unfold listMaxAux
    by_cases h : NNRat.leBool cur x = true
    · simp only [h, ↓reduceIte]
      exact NNRat.le_trans ((NNRat.leBool_true_iff cur x).mp h) (ih x)
    · have hf : NNRat.leBool cur x = false := by cases hb : NNRat.leBool cur x <;> simp_all
      simp only [hf, Bool.false_eq_true, ↓reduceIte]
      exact ih cur

private theorem mem_le_listMaxAux (cur : NNRat) (xs : List NNRat) {y : NNRat} (hy : y ∈ xs) :
    y ≤ listMaxAux cur xs := by
  induction xs generalizing cur with
  | nil => simp at hy
  | cons x xs ih =>
    unfold listMaxAux
    simp only [List.mem_cons] at hy
    rcases hy with rfl | htail
    · by_cases h : NNRat.leBool cur y = true
      · simp only [h, ↓reduceIte]
        exact cur_le_listMaxAux y xs
      · have hf : NNRat.leBool cur y = false := by cases hb : NNRat.leBool cur y <;> simp_all
        simp only [hf, Bool.false_eq_true, ↓reduceIte]
        have hlt : y < cur := (NNRat.leBool_false_iff cur y).mp hf
        exact NNRat.le_trans (NNRat.le_of_lt hlt) (cur_le_listMaxAux cur xs)
    · by_cases h : NNRat.leBool cur x = true
      · simp only [h, ↓reduceIte]
        exact ih x htail
      · have hf : NNRat.leBool cur x = false := by cases hb : NNRat.leBool cur x <;> simp_all
        simp only [hf, Bool.false_eq_true, ↓reduceIte]
        exact ih cur htail

private theorem listMaxAux_mem_or_cur (cur : NNRat) (xs : List NNRat) :
    listMaxAux cur xs = cur ∨ listMaxAux cur xs ∈ xs := by
  induction xs generalizing cur with
  | nil => exact Or.inl rfl
  | cons x xs ih =>
    unfold listMaxAux
    by_cases h : NNRat.leBool cur x = true
    · simp only [h, ↓reduceIte]
      rcases ih x with hEq | hMem
      · exact Or.inr (by rw [hEq]; exact List.mem_cons_self ..)
      · exact Or.inr (List.mem_cons_of_mem x hMem)
    · have hf : NNRat.leBool cur x = false := by cases hb : NNRat.leBool cur x <;> simp_all
      simp only [hf, Bool.false_eq_true, ↓reduceIte]
      rcases ih cur with hEq | hMem
      · exact Or.inl hEq
      · exact Or.inr (List.mem_cons_of_mem x hMem)

private theorem listMinAux_perm_equiv {x₁ x₂ : NNRat} {xs₁ xs₂ : List NNRat}
    (hp : List.Perm (x₁ :: xs₁) (x₂ :: xs₂)) :
    listMinAux x₁ xs₁ ≈ listMinAux x₂ xs₂ := by
  apply NNRat.equiv_of_le_antisymm
  · rcases listMinAux_mem_or_cur x₂ xs₂ with hEq | hMem
    · have hin : x₂ ∈ x₁ :: xs₁ := hp.symm.subset (List.mem_cons_self ..)
      rw [hEq]
      simp only [List.mem_cons] at hin
      rcases hin with rfl | htail
      · exact listMinAux_le_cur _ _
      · exact listMinAux_le_mem _ _ htail
    · have hin : listMinAux x₂ xs₂ ∈ x₁ :: xs₁ := hp.symm.subset (List.mem_cons_of_mem x₂ hMem)
      simp only [List.mem_cons] at hin
      rcases hin with hEq | htail
      · rw [hEq]; exact listMinAux_le_cur _ _
      · exact listMinAux_le_mem _ _ htail
  · rcases listMinAux_mem_or_cur x₁ xs₁ with hEq | hMem
    · have hin : x₁ ∈ x₂ :: xs₂ := hp.subset (List.mem_cons_self ..)
      rw [hEq]
      simp only [List.mem_cons] at hin
      rcases hin with rfl | htail
      · exact listMinAux_le_cur _ _
      · exact listMinAux_le_mem _ _ htail
    · have hin : listMinAux x₁ xs₁ ∈ x₂ :: xs₂ := hp.subset (List.mem_cons_of_mem x₁ hMem)
      simp only [List.mem_cons] at hin
      rcases hin with hEq | htail
      · rw [hEq]; exact listMinAux_le_cur _ _
      · exact listMinAux_le_mem _ _ htail

private theorem listMaxAux_perm_equiv {x₁ x₂ : NNRat} {xs₁ xs₂ : List NNRat}
    (hp : List.Perm (x₁ :: xs₁) (x₂ :: xs₂)) :
    listMaxAux x₁ xs₁ ≈ listMaxAux x₂ xs₂ := by
  apply NNRat.equiv_of_le_antisymm
  · rcases listMaxAux_mem_or_cur x₁ xs₁ with hEq | hMem
    · have hin : x₁ ∈ x₂ :: xs₂ := hp.subset (List.mem_cons_self ..)
      rw [hEq]
      simp only [List.mem_cons] at hin
      rcases hin with rfl | htail
      · exact cur_le_listMaxAux _ _
      · exact mem_le_listMaxAux _ _ htail
    · have hin : listMaxAux x₁ xs₁ ∈ x₂ :: xs₂ := hp.subset (List.mem_cons_of_mem x₁ hMem)
      simp only [List.mem_cons] at hin
      rcases hin with hEq | htail
      · rw [hEq]; exact cur_le_listMaxAux _ _
      · exact mem_le_listMaxAux _ _ htail
  · rcases listMaxAux_mem_or_cur x₂ xs₂ with hEq | hMem
    · have hin : x₂ ∈ x₁ :: xs₁ := hp.symm.subset (List.mem_cons_self ..)
      rw [hEq]
      simp only [List.mem_cons] at hin
      rcases hin with rfl | htail
      · exact cur_le_listMaxAux _ _
      · exact mem_le_listMaxAux _ _ htail
    · have hin : listMaxAux x₂ xs₂ ∈ x₁ :: xs₁ := hp.symm.subset (List.mem_cons_of_mem x₂ hMem)
      simp only [List.mem_cons] at hin
      rcases hin with hEq | htail
      · rw [hEq]; exact cur_le_listMaxAux _ _
      · exact mem_le_listMaxAux _ _ htail

private theorem ofNNRat_equiv_of_equiv {a b : NNRat} (h : a ≈ b) :
    ofNNRat a ≈ₛ ofNNRat b := by
  unfold ofNNRat SignedRat.equiv
  dsimp only
  have hNat : a.num * b.den = b.num * a.den := h
  exact_mod_cast hNat

private theorem checkScoreListDisagreement_isSome_iff
    (scope : AnomalyScope) (caseId : Option String)
    (pairs : List (String × Option NNRat)) (threshold : NNRat) :
    (checkScoreListDisagreement scope caseId pairs threshold).isSome = true ↔
    (2 ≤ (extractNumericPairs pairs).length ∧
     threshold < scoreSpread ((extractNumericPairs pairs).map Prod.snd)) := by
  unfold checkScoreListDisagreement
  dsimp only
  by_cases hlen : (extractNumericPairs pairs).length ≥ 2
  · simp only [hlen, ↓reduceIte]
    by_cases hlt : threshold < scoreSpread ((extractNumericPairs pairs).map Prod.snd)
    · simp [hlt]
    · simp [hlt]
  · simp [hlen]

/-! ## Group 1 — Disagreement Spread & Inconclusive Spikes (`7` Theorems) -/

/--
**Theorem 1 (`scoreSpread_unit_bounds`)**:
Whenever all input scores lie in `[0, 1]`, `scoreSpread scores` lies in `[0, 1]`.
-/
theorem scoreSpread_unit_bounds (scores : List NNRat)
    (hunit : ∀ s ∈ scores, s ≤ NNRat.one) :
    NNRat.zero ≤ scoreSpread scores ∧ scoreSpread scores ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  cases scores with
  | nil =>
    unfold scoreSpread
    rw [NNRat.le_one_iff]
    dsimp only [NNRat.zero]
    omega
  | cons x xs =>
    cases xs with
    | nil =>
      unfold scoreSpread
      rw [NNRat.le_one_iff]
      dsimp only [NNRat.zero]
      omega
    | cons y rest =>
      unfold scoreSpread
      have hmax : listMaxAux x (y :: rest) ≤ NNRat.one := by
        rcases listMaxAux_mem_or_cur x (y :: rest) with hEq | hMem
        · rw [hEq]; exact hunit x (List.mem_cons_self ..)
        · exact hunit _ (List.mem_cons_of_mem x hMem)
      have hmin : listMinAux x (y :: rest) ≤ NNRat.one := by
        rcases listMinAux_mem_or_cur x (y :: rest) with hEq | hMem
        · rw [hEq]; exact hunit x (List.mem_cons_self ..)
        · exact hunit _ (List.mem_cons_of_mem x hMem)
      exact nnAbsDiff_le_one_of_unit hmax hmin

/--
**Theorem 2 (`scoreSpread_perm_invariant`)**:
`scoreSpread` is invariant under arbitrary permutations of the score list.
-/
theorem scoreSpread_perm_invariant {s₁ s₂ : List NNRat} (hp : List.Perm s₁ s₂) :
    scoreSpread s₁ ≈ scoreSpread s₂ := by
  have hlen : s₁.length = s₂.length := hp.length_eq
  cases s₁ with
  | nil =>
    cases s₂ with
    | nil => exact NNRat.equiv_refl _
    | cons _ _ => simp at hlen
  | cons x₁ xs₁ =>
    cases xs₁ with
    | nil =>
      cases s₂ with
      | nil => simp at hlen
      | cons x₂ xs₂ =>
        cases xs₂ with
        | nil => exact NNRat.equiv_refl _
        | cons _ _ => simp at hlen
    | cons y₁ rest₁ =>
      cases s₂ with
      | nil => simp at hlen
      | cons x₂ xs₂ =>
        cases xs₂ with
        | nil => simp at hlen
        | cons y₂ rest₂ =>
          unfold scoreSpread
          exact nnAbsDiff_equiv_congr
            (listMaxAux_perm_equiv hp)
            (listMinAux_perm_equiv hp)

/--
**Theorem 3 (`scoreSpread_singleton_or_empty_zero`)**:
Score lists with 0 or 1 elements always have zero disagreement spread.
-/
theorem scoreSpread_singleton_or_empty_zero (scores : List NNRat) (h : scores.length ≤ 1) :
    scoreSpread scores = NNRat.zero := by
  cases scores with
  | nil => rfl
  | cons x xs =>
    cases xs with
    | nil => rfl
    | cons _ _ => simp at h

/--
**Theorem 4 (`checkDisagreements_fires_iff`)**:
`checkDisagreements` emits at least one `METRIC_DISAGREEMENT` flag iff either some case or the
run-level aggregate map has `≥ 2` numeric metric scores whose spread strictly exceeds `threshold`.
-/
theorem checkDisagreements_fires_iff (run : AnomalyRunSummary) (threshold : NNRat) :
    checkDisagreements run threshold ≠ [] ↔
    (∃ c ∈ run.cases,
        2 ≤ (extractNumericPairs c.metricScores).length ∧
        threshold < scoreSpread ((extractNumericPairs c.metricScores).map Prod.snd)) ∨
    (2 ≤ (extractNumericPairs run.aggregates).length ∧
     threshold < scoreSpread ((extractNumericPairs run.aggregates).map Prod.snd)) := by
  unfold checkDisagreements checkCaseDisagreement checkRunDisagreement
  dsimp only
  have hCaseIff :
      (run.cases.filterMap fun c =>
          checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold) ≠ [] ↔
      ∃ c ∈ run.cases,
        2 ≤ (extractNumericPairs c.metricScores).length ∧
        threshold < scoreSpread ((extractNumericPairs c.metricScores).map Prod.snd) := by
    constructor
    · intro hne
      cases hfl : (run.cases.filterMap fun c =>
          checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold) with
      | nil => exact absurd hfl hne
      | cons f _ =>
        have hf : f ∈ run.cases.filterMap fun c =>
            checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold := by
          rw [hfl]; exact List.mem_cons_self ..
        rw [List.mem_filterMap] at hf
        obtain ⟨c, hcMem, hcSome⟩ := hf
        refine ⟨c, hcMem, ?_⟩
        exact (checkScoreListDisagreement_isSome_iff .case (some c.caseId) c.metricScores threshold).mp
          (by rw [hcSome]; rfl)
    · rintro ⟨c, hcMem, hlen, hlt⟩
      have his := (checkScoreListDisagreement_isSome_iff .case (some c.caseId) c.metricScores threshold).mpr ⟨hlen, hlt⟩
      cases hf : checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold with
      | none => simp [hf] at his
      | some fl =>
        intro hemp
        have hmem : fl ∈ run.cases.filterMap fun c =>
            checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold := by
          rw [List.mem_filterMap]
          exact ⟨c, hcMem, hf⟩
        rw [hemp] at hmem
        simp at hmem
  have hRunIff :
      (match checkScoreListDisagreement .run none run.aggregates threshold with
       | some f => [f]
       | none => []) ≠ [] ↔
      (2 ≤ (extractNumericPairs run.aggregates).length ∧
       threshold < scoreSpread ((extractNumericPairs run.aggregates).map Prod.snd)) := by
    rw [← checkScoreListDisagreement_isSome_iff .run none run.aggregates threshold]
    cases checkScoreListDisagreement .run none run.aggregates threshold <;> simp
  rw [← hCaseIff, ← hRunIff]
  constructor
  · intro hne
    by_cases h1 : (run.cases.filterMap fun c =>
        checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold) = []
    · right
      intro h2
      apply hne
      rw [h1, List.nil_append]
      cases hrun : checkScoreListDisagreement .run none run.aggregates threshold with
      | none => rfl
      | some f => simp [hrun] at h2
    · exact Or.inl h1
  · intro h hemp
    have ⟨h1, h2⟩ := List.append_eq_nil_iff.mp hemp
    rcases h with hA | hB
    · exact hA h1
    · exact hB h2

/--
**Theorem 5 (`checkDisagreements_perm_invariant`)**:
Permuting metric `(metricId, score?)` entries preserves both whether `METRIC_DISAGREEMENT` fires
and its exact rational `spread` value up to rational equivalence (`≈ₛ`).
-/
theorem checkDisagreements_perm_invariant
    (scope : AnomalyScope) (caseId : Option String)
    {p₁ p₂ : List (String × Option NNRat)} (hp : List.Perm p₁ p₂)
    (threshold : NNRat) :
    (checkScoreListDisagreement scope caseId p₁ threshold).isSome =
    (checkScoreListDisagreement scope caseId p₂ threshold).isSome ∧
    (∀ f₁ f₂,
      checkScoreListDisagreement scope caseId p₁ threshold = some f₁ →
      checkScoreListDisagreement scope caseId p₂ threshold = some f₂ →
      ∃ s₁ s₂, f₁.spread = some s₁ ∧ f₂.spread = some s₂ ∧ s₁ ≈ₛ s₂) := by
  have hpNum : List.Perm (extractNumericPairs p₁) (extractNumericPairs p₂) :=
    hp.filterMap _
  have hlenEq : (extractNumericPairs p₁).length = (extractNumericPairs p₂).length :=
    hpNum.length_eq
  have hpScores :
      List.Perm ((extractNumericPairs p₁).map Prod.snd) ((extractNumericPairs p₂).map Prod.snd) :=
    hpNum.map Prod.snd
  have hspreadEq :
      scoreSpread ((extractNumericPairs p₁).map Prod.snd) ≈
      scoreSpread ((extractNumericPairs p₂).map Prod.snd) :=
    scoreSpread_perm_invariant hpScores
  have hltIff :
      threshold < scoreSpread ((extractNumericPairs p₁).map Prod.snd) ↔
      threshold < scoreSpread ((extractNumericPairs p₂).map Prod.snd) :=
    ⟨nnrat_lt_of_equiv_right hspreadEq, nnrat_lt_of_equiv_right hspreadEq.symm⟩
  constructor
  · apply Bool.eq_iff_iff.mpr
    rw [checkScoreListDisagreement_isSome_iff, checkScoreListDisagreement_isSome_iff, hlenEq, hltIff]
  · intro f₁ f₂ h₁ h₂
    unfold checkScoreListDisagreement at h₁ h₂
    dsimp only at h₁ h₂
    split at h₁
    · split at h₁
      · split at h₂
        · split at h₂
          · injection h₁ with hEq₁
            injection h₂ with hEq₂
            subst hEq₁
            subst hEq₂
            exact ⟨_, _, rfl, rfl, ofNNRat_equiv_of_equiv hspreadEq⟩
          · simp at h₂
        · simp at h₂
      · simp at h₁
    · simp at h₁

/--
**Theorem 6 (`inconclusiveRate_unit_bounds`)**:
Whenever `inconclusiveCount ≤ evaluatedCount` with `0 < evaluatedCount`, the exact rational
inconclusive rate lies in `[0, 1]`.
-/
theorem inconclusiveRate_unit_bounds (k n : Nat) (hPos : 0 < n) (hle : k ≤ n) :
    NNRat.zero ≤ inconclusiveRate k n hPos ∧ inconclusiveRate k n hPos ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  rw [NNRat.le_one_iff]
  unfold inconclusiveRate
  dsimp only
  exact hle

/--
**Theorem 7 (`inconclusiveSpike_fires_iff`)**:
`checkInconclusiveSpike` emits an `INCONCLUSIVE_SPIKE` flag iff at least one case is inconclusive.
-/
theorem inconclusiveSpike_fires_iff (run : AnomalyRunSummary) :
    checkInconclusiveSpike run ≠ [] ↔ 0 < countInconclusiveCases run := by
  unfold checkInconclusiveSpike inconclusiveRate
  have hiff : NNRat.zero < (⟨countInconclusiveCases run, run.evaluatedCaseCount, run.evaluatedCaseCountPos⟩ : NNRat) ↔
      0 < countInconclusiveCases run := NNRat.zero_lt_iff _
  by_cases h : 0 < countInconclusiveCases run
  · have hlt : NNRat.zero < (⟨countInconclusiveCases run, run.evaluatedCaseCount, run.evaluatedCaseCountPos⟩ : NNRat) :=
      hiff.mpr h
    simp [decide_eq_true hlt, h]
  · have hnlt : ¬ (NNRat.zero < (⟨countInconclusiveCases run, run.evaluatedCaseCount, run.evaluatedCaseCountPos⟩ : NNRat)) :=
      fun hc => h (hiff.mp hc)
    simp [decide_eq_false hnlt, h]

/-! ## Group 2 — Anti-Masking Soundness (`7` Theorems) -/

/--
**Theorem 8 (`mandatoryCaseFailure_unconditional_fail`)**:
Every mandatory failed case ID unconditionally produces a `FAIL`-severity `CASE`-scoped
`MANDATORY_CASE_FAILURE` anomaly in `detectAnomalies`, regardless of comparison or policy.
-/
theorem mandatoryCaseFailure_unconditional_fail
    (run : AnomalyRunSummary)
    (cmp : Option AnomalyComparisonSummary)
    (policy : AnomalyPolicy)
    (cid : String)
    (hcid : cid ∈ run.mandatoryFailedCaseIds) :
    ∃ f ∈ detectAnomalies run cmp policy,
      f.anomalyType = .mandatoryCaseFailure ∧
      f.severity = .fail ∧
      f.scope = .case ∧
      f.caseId = some cid := by
  let failedMetrics :=
    match lookupCaseSummary run.cases cid with
    | some c => c.failedMetrics
    | none => []
  refine ⟨{
    anomalyType := .mandatoryCaseFailure
    severity := .fail
    scope := .case
    caseId := some cid
    metricIds := failedMetrics
    spread := none
  }, ?_, rfl, rfl, rfl, rfl⟩
  unfold detectAnomalies
  apply List.mem_append_left
  apply List.mem_append_left
  apply List.mem_append_right
  unfold checkMandatoryAndMaskedDrops
  have hBase :
      ({
        anomalyType := .mandatoryCaseFailure
        severity := .fail
        scope := .case
        caseId := some cid
        metricIds := failedMetrics
        spread := none
      } : AnomalyFlagSpec) ∈
      checkMandatoryFailures run ++ checkMacroMaskedMandatory run ++ checkMacroMaskedFloors run policy := by
    apply List.mem_append_left
    apply List.mem_append_left
    unfold checkMandatoryFailures
    rw [List.mem_map]
    exact ⟨cid, hcid, rfl⟩
  cases cmp with
  | none => exact hBase
  | some _ =>
    apply List.mem_append_left
    apply List.mem_append_left
    exact hBase

/--
**Theorem 9 (`macroMasked_mandatory_fires_iff`)**:
`checkMacroMaskedMandatory` fires iff the macro aggregate mean is passing (`≥ 0.5`) AND at least
one mandatory case failed.
-/
theorem macroMasked_mandatory_fires_iff (run : AnomalyRunSummary) :
    checkMacroMaskedMandatory run ≠ [] ↔
    (isMacroPassing run = true ∧ run.mandatoryFailedCaseIds ≠ []) := by
  unfold checkMacroMaskedMandatory isMacroPassing
  cases hMean : runMacroMean run with
  | none => simp
  | some m =>
    cases hPass : NNRat.leBool halfNNRat m with
    | false => simp
    | true =>
      cases hMand : run.mandatoryFailedCaseIds with
      | nil => simp
      | cons _ _ => simp

/--
**Theorem 10 (`macroMasked_floor_breach_sound`)**:
Whenever the macro aggregate mean passes (`≥ 0.5`) and any metric's aggregate mean strictly falls
below its resolved policy floor (`minMetricScores[m] ?? minScore`), `detectAnomalies` emits a
run-scoped `WARNING` `AGGREGATE_MASKED_DROP` flag naming that metric.
-/
theorem macroMasked_floor_breach_sound
    (run : AnomalyRunSummary)
    (cmp : Option AnomalyComparisonSummary)
    (policy : AnomalyPolicy)
    (mid : String)
    (meanScore floor : NNRat)
    (hpass : isMacroPassing run = true)
    (hagg : (mid, some meanScore) ∈ run.aggregates)
    (hfloor : resolveMetricFloor policy mid = some floor)
    (hbreach : meanScore < floor) :
    ∃ f ∈ detectAnomalies run cmp policy,
      f.anomalyType = .aggregateMaskedDrop ∧
      f.severity = .warning ∧
      f.scope = .run ∧
      f.metricIds = [mid] := by
  refine ⟨{
    anomalyType := .aggregateMaskedDrop
    severity := .warning
    scope := .run
    caseId := none
    metricIds := [mid]
    spread := some (SignedRat.subNNRat meanScore floor)
  }, ?_, rfl, rfl, rfl, rfl⟩
  have hInFloors :
      ({
        anomalyType := .aggregateMaskedDrop
        severity := .warning
        scope := .run
        caseId := none
        metricIds := [mid]
        spread := some (SignedRat.subNNRat meanScore floor)
      } : AnomalyFlagSpec) ∈ checkMacroMaskedFloors run policy := by
    unfold checkMacroMaskedFloors
    simp only [hpass, ↓reduceIte]
    rw [List.mem_filterMap]
    refine ⟨(mid, some meanScore), hagg, ?_⟩
    simp only [hfloor, decide_eq_true hbreach, ↓reduceIte]
  unfold detectAnomalies
  apply List.mem_append_left
  apply List.mem_append_left
  apply List.mem_append_right
  unfold checkMandatoryAndMaskedDrops
  cases cmp with
  | none => exact List.mem_append_right _ hInFloors
  | some _ =>
    apply List.mem_append_left
    apply List.mem_append_left
    exact List.mem_append_right _ hInFloors

/--
**Theorem 11 (`comparisonMasked_metric_drop_sound`)**:
When either the macro aggregate mean passes (`≥ 0.5`) or the comparison mean delta is non-negative,
any individual metric drop strictly exceeding its resolved allowed drop emits a run-scoped
`WARNING` `AGGREGATE_MASKED_DROP` flag naming that metric with `spread = some delta`.
-/
theorem comparisonMasked_metric_drop_sound
    (run : AnomalyRunSummary)
    (cmp : AnomalyComparisonSummary)
    (policy : AnomalyPolicy)
    (mc : AnomalyMetricDelta)
    (d : SignedRat)
    (hmask : isMacroPassing run = true ∨ isMacroNonRegressing cmp = true)
    (hmc : mc ∈ cmp.metricComparisons)
    (hd : mc.delta = some d)
    (hdrop : ofNNRat (resolveAllowedDrop policy mc.metricId) <ₛ sNeg d) :
    ∃ f ∈ detectAnomalies run (some cmp) policy,
      f.anomalyType = .aggregateMaskedDrop ∧
      f.severity = .warning ∧
      f.scope = .run ∧
      f.metricIds = [mc.metricId] ∧
      f.spread = some d := by
  refine ⟨{
    anomalyType := .aggregateMaskedDrop
    severity := .warning
    scope := .run
    caseId := none
    metricIds := [mc.metricId]
    spread := some d
  }, ?_, rfl, rfl, rfl, rfl, rfl⟩
  have hCond : (isMacroPassing run || isMacroNonRegressing cmp) = true := by
    rcases hmask with h1 | h2
    · simp [h1]
    · simp [h2]
  have hInCmp :
      ({
        anomalyType := .aggregateMaskedDrop
        severity := .warning
        scope := .run
        caseId := none
        metricIds := [mc.metricId]
        spread := some d
      } : AnomalyFlagSpec) ∈ checkComparisonMaskedMetrics run cmp policy := by
    unfold checkComparisonMaskedMetrics
    simp only [hCond, ↓reduceIte]
    rw [List.mem_filterMap]
    refine ⟨mc, hmc, ?_⟩
    simp only [hd, decide_eq_true hdrop, ↓reduceIte]
  unfold detectAnomalies
  apply List.mem_append_left
  apply List.mem_append_left
  apply List.mem_append_right
  unfold checkMandatoryAndMaskedDrops
  apply List.mem_append_left
  exact List.mem_append_right _ hInCmp

/--
**Theorem 12 (`comparisonMasked_case_drop_sound`)**:
Whenever a metric's aggregate comparison is healthy (`isMetricAggregateHealthy = true`) and a
single case drops on that metric by at least `caseDropWarningThreshold` (`-delta ≥ threshold`),
`detectAnomalies` emits a case-scoped `WARNING` `AGGREGATE_MASKED_DROP` flag identifying that case
and metric.
-/
theorem comparisonMasked_case_drop_sound
    (run : AnomalyRunSummary)
    (cmp : AnomalyComparisonSummary)
    (policy : AnomalyPolicy)
    (cc : AnomalyCaseDelta)
    (cmd : AnomalyMetricDelta)
    (d : SignedRat)
    (hcc : cc ∈ cmp.caseComparisons)
    (hcmd : cmd ∈ cc.metricDeltas)
    (hd : cmd.delta = some d)
    (hhealthy : isMetricAggregateHealthy cmp policy cmd.metricId = true)
    (hdrop : ofNNRat policy.caseDropWarningThreshold ≤ₛ sNeg d) :
    ∃ f ∈ detectAnomalies run (some cmp) policy,
      f.anomalyType = .aggregateMaskedDrop ∧
      f.severity = .warning ∧
      f.scope = .case ∧
      f.caseId = some cc.caseId ∧
      f.metricIds = [cmd.metricId] ∧
      f.spread = some d := by
  refine ⟨{
    anomalyType := .aggregateMaskedDrop
    severity := .warning
    scope := .case
    caseId := some cc.caseId
    metricIds := [cmd.metricId]
    spread := some d
  }, ?_, rfl, rfl, rfl, rfl, rfl, rfl⟩
  have hInCaseDrops :
      ({
        anomalyType := .aggregateMaskedDrop
        severity := .warning
        scope := .case
        caseId := some cc.caseId
        metricIds := [cmd.metricId]
        spread := some d
      } : AnomalyFlagSpec) ∈ checkComparisonMaskedCaseDrops cmp policy := by
    unfold checkComparisonMaskedCaseDrops
    rw [List.mem_flatMap]
    refine ⟨cc, hcc, ?_⟩
    rw [List.mem_filterMap]
    refine ⟨cmd, hcmd, ?_⟩
    simp only [hd, hhealthy, decide_eq_true hdrop, Bool.and_self, ↓reduceIte]
  unfold detectAnomalies
  apply List.mem_append_left
  apply List.mem_append_left
  apply List.mem_append_right
  unfold checkMandatoryAndMaskedDrops
  exact List.mem_append_right _ hInCaseDrops

/--
**Theorem 13 (`datasetCapped_anomaly_iff`)**:
`checkDatasetCapped` emits a `DATASET_CAPPED` warning iff `run.datasetCapped = true`.
-/
theorem datasetCapped_anomaly_iff (run : AnomalyRunSummary) :
    checkDatasetCapped run ≠ [] ↔ run.datasetCapped = true := by
  unfold checkDatasetCapped
  cases run.datasetCapped <;> simp

/--
**Theorem 14 (`cleanCompliantRun_zero_anomalies`)**:
An uncapped, fully conclusive standalone run with no mandatory failures, all inter-metric spreads
within `disagreementThreshold`, and all metric aggregates meeting their resolved policy floors
emits zero anomalies (`detectAnomalies run none policy = []`).
-/
theorem cleanCompliantRun_zero_anomalies
    (run : AnomalyRunSummary)
    (policy : AnomalyPolicy)
    (huncapped : run.datasetCapped = false)
    (hnoMand : run.mandatoryFailedCaseIds = [])
    (hnoInc : ∀ c ∈ run.cases, c.isInconclusive = false)
    (hnoCaseDis : ∀ c ∈ run.cases,
      scoreSpread ((extractNumericPairs c.metricScores).map Prod.snd) ≤ policy.disagreementThreshold)
    (hnoRunDis :
      scoreSpread ((extractNumericPairs run.aggregates).map Prod.snd) ≤ policy.disagreementThreshold)
    (hfloors : ∀ mid meanScore floor,
      (mid, some meanScore) ∈ run.aggregates →
      resolveMetricFloor policy mid = some floor →
      floor ≤ meanScore) :
    detectAnomalies run none policy = [] := by
  have hDis : checkDisagreements run policy.disagreementThreshold = [] := by
    by_cases hne : checkDisagreements run policy.disagreementThreshold = []
    · exact hne
    · exfalso
      rcases (checkDisagreements_fires_iff run policy.disagreementThreshold).mp hne with
        ⟨c, hcMem, _, hlt⟩ | ⟨_, hlt⟩
      · exact (NNRat.lt_iff_not_le _ _).mp hlt (hnoCaseDis c hcMem)
      · exact (NNRat.lt_iff_not_le _ _).mp hlt hnoRunDis
  have hMand : checkMandatoryFailures run = [] := by
    unfold checkMandatoryFailures
    rw [hnoMand]
    rfl
  have hMacroMand : checkMacroMaskedMandatory run = [] := by
    by_cases hne : checkMacroMaskedMandatory run = []
    · exact hne
    · exfalso
      have ⟨_, hMandNe⟩ := (macroMasked_mandatory_fires_iff run).mp hne
      exact hMandNe hnoMand
  have hFloors : checkMacroMaskedFloors run policy = [] := by
    unfold checkMacroMaskedFloors
    cases isMacroPassing run with
    | false => rfl
    | true =>
      simp only [↓reduceIte]
      apply List.eq_nil_iff_forall_not_mem.mpr
      intro f hf
      rw [List.mem_filterMap] at hf
      obtain ⟨⟨mid, optMean⟩, hagg, hsome⟩ := hf
      cases optMean with
      | none => simp at hsome
      | some meanScore =>
        cases hfl : resolveMetricFloor policy mid with
        | none => simp [hfl] at hsome
        | some floor =>
          simp only [hfl] at hsome
          have hle : floor ≤ meanScore := hfloors mid meanScore floor hagg hfl
          have hnlt : ¬ (meanScore < floor) := fun hlt => (NNRat.lt_iff_not_le _ _).mp hlt hle
          simp [decide_eq_false hnlt] at hsome
  have hCap : checkDatasetCapped run = [] := by
    unfold checkDatasetCapped
    simp [huncapped]
  have hInc : checkInconclusiveSpike run = [] := by
    by_cases hne : checkInconclusiveSpike run = []
    · exact hne
    · exfalso
      have hpos : 0 < countInconclusiveCases run := (inconclusiveSpike_fires_iff run).mp hne
      unfold countInconclusiveCases at hpos
      have hfilt : run.cases.filter AnomalyCaseSummary.isInconclusive = [] := by
        apply List.eq_nil_iff_forall_not_mem.mpr
        intro c hc
        rw [List.mem_filter] at hc
        have hf := hnoInc c hc.1
        rw [hf] at hc
        simp at hc
      rw [hfilt] at hpos
      simp at hpos
  unfold detectAnomalies checkMandatoryAndMaskedDrops
  simp [hDis, hMand, hMacroMand, hFloors, hCap, hInc]

/-! ## Helper Lemmas: Exact-Rational OLS Algebra -/

private theorem length_filterMap_le {α β : Type} (f : α → Option β) (xs : List α) :
    (xs.filterMap f).length ≤ xs.length := by
  induction xs with
  | nil => simp
  | cons x xs ih =>
    cases hf : f x with
    | none =>
      simp only [List.filterMap_cons, hf, List.length_cons]
      omega
    | some y =>
      simp only [List.filterMap_cons, hf, List.length_cons]
      omega

private theorem sAdd_zero_right_equiv (a : SignedRat) : sAdd a SignedRat.zero ≈ₛ a := by
  unfold sAdd SignedRat.zero SignedRat.equiv
  dsimp only
  simp

private theorem sAdd_zero_left_equiv (a : SignedRat) : sAdd SignedRat.zero a ≈ₛ a := by
  unfold sAdd SignedRat.zero SignedRat.equiv
  dsimp only
  simp

private theorem sMul_equiv_congr {a₁ a₂ b₁ b₂ : SignedRat} (ha : a₁ ≈ₛ a₂) (hb : b₁ ≈ₛ b₂) :
    sMul a₁ b₁ ≈ₛ sMul a₂ b₂ := by
  unfold sMul SignedRat.equiv at *
  dsimp only
  rw [Int.natCast_mul, Int.natCast_mul]
  calc
    (a₁.num * b₁.num) * ((a₂.den : Int) * (b₂.den : Int))
        = (a₁.num * (a₂.den : Int)) * (b₁.num * (b₂.den : Int)) := by
          rw [Int.mul_assoc, Int.mul_left_comm b₁.num (a₂.den : Int) (b₂.den : Int), ← Int.mul_assoc]
    _ = (a₂.num * (a₁.den : Int)) * (b₂.num * (b₁.den : Int)) := by rw [ha, hb]
    _ = (a₂.num * b₂.num) * ((a₁.den : Int) * (b₁.den : Int)) := by
          rw [Int.mul_assoc, Int.mul_left_comm (a₁.den : Int) b₂.num (b₁.den : Int), ← Int.mul_assoc]

private theorem sMul_sAdd_distrib_left (w a b : SignedRat) :
    sMul w (sAdd a b) ≈ₛ sAdd (sMul w a) (sMul w b) := by
  unfold sMul sAdd SignedRat.equiv
  dsimp only
  push_cast
  rw [Int.mul_add, Int.add_mul, Int.add_mul]
  have h1 :
      (w.num * (a.num * (b.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int))) =
      ((w.num * a.num) * ((w.den : Int) * (b.den : Int))) * ((w.den : Int) * ((a.den : Int) * (b.den : Int))) := by
    have hL :
        (w.num * (a.num * (b.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int))) =
        ((w.num * a.num) * ((w.den : Int) * (b.den : Int))) * ((b.den : Int) * ((w.den : Int) * (a.den : Int))) := by
      calc
        (w.num * (a.num * (b.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int)))
            = ((w.num * a.num) * (b.den : Int)) * (((w.den : Int) * (a.den : Int)) * ((w.den : Int) * (b.den : Int))) := by
              rw [← Int.mul_assoc w.num a.num (b.den : Int)]
        _ = ((w.num * a.num) * (b.den : Int)) * (((w.den : Int) * (b.den : Int)) * ((w.den : Int) * (a.den : Int))) := by
              rw [Int.mul_comm ((w.den : Int) * (a.den : Int)) ((w.den : Int) * (b.den : Int))]
        _ = ((w.num * a.num) * ((w.den : Int) * (b.den : Int))) * ((b.den : Int) * ((w.den : Int) * (a.den : Int))) := by
              rw [Int.mul_assoc (w.num * a.num) (b.den : Int),
                  Int.mul_left_comm (b.den : Int) ((w.den : Int) * (b.den : Int)),
                  ← Int.mul_assoc (w.num * a.num)]
    rw [hL]
    apply congrArg (((w.num * a.num) * ((w.den : Int) * (b.den : Int))) * ·)
    rw [Int.mul_left_comm (b.den : Int) (w.den : Int) (a.den : Int),
        Int.mul_comm (b.den : Int) (a.den : Int)]
  have h2 :
      (w.num * (b.num * (a.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int))) =
      ((w.num * b.num) * ((w.den : Int) * (a.den : Int))) * ((w.den : Int) * ((a.den : Int) * (b.den : Int))) := by
    have hL :
        (w.num * (b.num * (a.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int))) =
        ((w.num * b.num) * ((w.den : Int) * (a.den : Int))) * ((a.den : Int) * ((w.den : Int) * (b.den : Int))) := by
      calc
        (w.num * (b.num * (a.den : Int))) * ((w.den : Int) * (a.den : Int) * ((w.den : Int) * (b.den : Int)))
            = ((w.num * b.num) * (a.den : Int)) * (((w.den : Int) * (a.den : Int)) * ((w.den : Int) * (b.den : Int))) := by
              rw [← Int.mul_assoc w.num b.num (a.den : Int)]
        _ = ((w.num * b.num) * ((w.den : Int) * (a.den : Int))) * ((a.den : Int) * ((w.den : Int) * (b.den : Int))) := by
              rw [Int.mul_assoc (w.num * b.num) (a.den : Int),
                  Int.mul_left_comm (a.den : Int) ((w.den : Int) * (a.den : Int)),
                  ← Int.mul_assoc (w.num * b.num)]
    rw [hL]
    apply congrArg (((w.num * b.num) * ((w.den : Int) * (a.den : Int))) * ·)
    rw [Int.mul_left_comm (a.den : Int) (w.den : Int) (b.den : Int)]
  rw [h1, h2]

private theorem sMul_int_add_distrib (u v : Int) (c : SignedRat) :
    sAdd (sMul ⟨u, 1, Nat.zero_lt_one⟩ c) (sMul ⟨v, 1, Nat.zero_lt_one⟩ c) ≈ₛ
    sMul ⟨u + v, 1, Nat.zero_lt_one⟩ c := by
  unfold sAdd sMul SignedRat.equiv
  dsimp only
  simp only [Nat.one_mul]
  rw [Int.add_mul, Int.add_mul]
  have h3 : (u * c.num) * (c.den : Int) * (c.den : Int) = u * c.num * ((c.den : Int) * (c.den : Int)) :=
    Int.mul_assoc _ _ _
  have h4 : (v * c.num) * (c.den : Int) * (c.den : Int) = v * c.num * ((c.den : Int) * (c.den : Int)) :=
    Int.mul_assoc _ _ _
  rw [Int.natCast_mul, h3, h4, ← Int.add_mul]

private theorem sMul_int_mul_assoc (u v : Int) (c : SignedRat) :
    sMul ⟨u, 1, Nat.zero_lt_one⟩ (sMul ⟨v, 1, Nat.zero_lt_one⟩ c) ≈ₛ
    sMul ⟨u * v, 1, Nat.zero_lt_one⟩ c := by
  unfold sMul SignedRat.equiv
  dsimp only
  simp only [Nat.one_mul, Int.mul_assoc]

private theorem sMul_zero_int_equiv (c : SignedRat) :
    sMul ⟨0, 1, Nat.zero_lt_one⟩ c ≈ₛ SignedRat.zero := by
  rw [sEquiv_zero_iff]
  unfold sMul
  dsimp only
  simp

private theorem sMul_neg_int_equiv (w : Int) (c : SignedRat) :
    sMul ⟨-w, 1, Nat.zero_lt_one⟩ c ≈ₛ sNeg (sMul ⟨w, 1, Nat.zero_lt_one⟩ c) := by
  unfold sMul sNeg SignedRat.equiv
  dsimp only
  rw [Int.neg_mul]

private theorem sDivNat_sNeg_equiv (a : SignedRat) (n : Nat) (hn : 0 < n) :
    sDivNat (sNeg a) n hn ≈ₛ sNeg (sDivNat a n hn) := by
  unfold sDivNat sNeg SignedRat.equiv
  dsimp only

private theorem sMul_sNeg_right_equiv (a b : SignedRat) :
    sMul a (sNeg b) ≈ₛ sNeg (sMul a b) := by
  unfold sMul sNeg SignedRat.equiv
  dsimp only
  rw [Int.mul_neg]

private theorem sAdd_rearrange_four (a b c d : SignedRat) :
    sAdd (sAdd a b) (sAdd c d) ≈ₛ sAdd (sAdd a c) (sAdd b d) := by
  have h1 : sAdd (sAdd a b) (sAdd c d) ≈ₛ sAdd a (sAdd b (sAdd c d)) :=
    sAdd_assoc_equiv a b (sAdd c d)
  have h2 : sAdd b (sAdd c d) ≈ₛ sAdd c (sAdd b d) :=
    SignedRat.equiv_trans (sAdd_assoc_equiv b c d).symm
      (SignedRat.equiv_trans (sAdd_equiv_congr (sAdd_comm_equiv b c) (SignedRat.equiv_refl d))
        (sAdd_assoc_equiv c b d))
  have h3 : sAdd a (sAdd b (sAdd c d)) ≈ₛ sAdd a (sAdd c (sAdd b d)) :=
    sAdd_equiv_congr (SignedRat.equiv_refl a) h2
  have h4 : sAdd a (sAdd c (sAdd b d)) ≈ₛ sAdd (sAdd a c) (sAdd b d) :=
    (sAdd_assoc_equiv a c (sAdd b d)).symm
  exact SignedRat.equiv_trans h1 (SignedRat.equiv_trans h3 h4)

private def intWeightSum (idx : Nat) : Nat → Nat → Int
  | 0, _ => 0
  | k + 1, m => olsWeight idx m + intWeightSum (idx + 1) k m

private theorem intWeightSum_closed (idx k m : Nat) :
    intWeightSum idx k m = (k : Int) * (2 * (idx : Int) + (k : Int) - 1 - ((m - 1 : Nat) : Int)) := by
  induction k generalizing idx with
  | zero => simp [intWeightSum]
  | succ k ih =>
    unfold intWeightSum olsWeight
    rw [ih (idx + 1)]
    push_cast
    have h1 :
        2 * (idx : Int) - ((m - 1 : Nat) : Int) +
          (k : Int) * (2 * ((idx : Int) + 1) + (k : Int) - 1 - ((m - 1 : Nat) : Int)) =
        ((k : Int) + 1) * (2 * (idx : Int) + ((k : Int) + 1) - 1 - ((m - 1 : Nat) : Int)) := by
      have hL :
          (k : Int) * (2 * ((idx : Int) + 1) + (k : Int) - 1 - ((m - 1 : Nat) : Int)) =
          (k : Int) * (2 * (idx : Int) + (k : Int) - ((m - 1 : Nat) : Int)) + (k : Int) := by
        have hEq : 2 * ((idx : Int) + 1) + (k : Int) - 1 - ((m - 1 : Nat) : Int) =
            (2 * (idx : Int) + (k : Int) - ((m - 1 : Nat) : Int)) + 1 := by omega
        rw [hEq, Int.mul_add, Int.mul_one]
      have hR :
          ((k : Int) + 1) * (2 * (idx : Int) + ((k : Int) + 1) - 1 - ((m - 1 : Nat) : Int)) =
          (k : Int) * (2 * (idx : Int) + (k : Int) - ((m - 1 : Nat) : Int)) +
            (2 * (idx : Int) + (k : Int) - ((m - 1 : Nat) : Int)) := by
        have hEq : 2 * (idx : Int) + ((k : Int) + 1) - 1 - ((m - 1 : Nat) : Int) =
            2 * (idx : Int) + (k : Int) - ((m - 1 : Nat) : Int) := by omega
        rw [hEq, Int.add_mul, Int.one_mul]
      rw [hL, hR]
      omega
    exact h1

private theorem intWeightSum_full_zero {m : Nat} (hm : 1 ≤ m) :
    intWeightSum 0 m m = 0 := by
  rw [intWeightSum_closed]
  have hcast : ((m - 1 : Nat) : Int) = (m : Int) - 1 := by omega
  rw [hcast]
  have hz : 2 * ((0 : Nat) : Int) + (m : Int) - 1 - ((m : Int) - 1) = 0 := by omega
  rw [hz, Int.mul_zero]

private theorem olsWeightedSumAux_map_add (idx m : Nat) (ys : List SignedRat) (c : SignedRat) :
    olsWeightedSumAux idx m (ys.map fun y => sAdd y c) ≈ₛ
    sAdd (olsWeightedSumAux idx m ys) (sMul ⟨intWeightSum idx ys.length m, 1, Nat.zero_lt_one⟩ c) := by
  induction ys generalizing idx with
  | nil =>
    simp only [List.map_nil, List.length_nil, olsWeightedSumAux, intWeightSum]
    exact (SignedRat.equiv_trans (sAdd_equiv_congr (SignedRat.equiv_refl _) (sMul_zero_int_equiv c))
      (sAdd_zero_right_equiv SignedRat.zero)).symm
  | cons y ys ih =>
    simp only [List.map_cons, List.length_cons, olsWeightedSumAux, intWeightSum]
    have hDist := sMul_sAdd_distrib_left ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩ y c
    have hStep := sAdd_equiv_congr hDist (ih (idx + 1))
    have hRearr := sAdd_rearrange_four
      (sMul ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩ y)
      (sMul ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩ c)
      (olsWeightedSumAux (idx + 1) m ys)
      (sMul ⟨intWeightSum (idx + 1) ys.length m, 1, Nat.zero_lt_one⟩ c)
    have hCombine := sAdd_equiv_congr
      (SignedRat.equiv_refl (sAdd (sMul ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩ y)
        (olsWeightedSumAux (idx + 1) m ys)))
      (sMul_int_add_distrib (olsWeight idx m) (intWeightSum (idx + 1) ys.length m) c)
    exact SignedRat.equiv_trans hStep (SignedRat.equiv_trans hRearr hCombine)

private theorem olsWeightedSumAux_shift_full (ys : List SignedRat) (c : SignedRat)
    (hpos : 1 ≤ ys.length) :
    olsWeightedSumAux 0 ys.length (ys.map fun y => sAdd y c) ≈ₛ
    olsWeightedSumAux 0 ys.length ys := by
  have h1 := olsWeightedSumAux_map_add 0 ys.length ys c
  rw [intWeightSum_full_zero hpos] at h1
  exact SignedRat.equiv_trans h1
    (SignedRat.equiv_trans
      (sAdd_equiv_congr (SignedRat.equiv_refl _) (sMul_zero_int_equiv c))
      (sAdd_zero_right_equiv _))

private theorem olsCenteredSumAux_eq_map (idx m : Nat) (yMean : SignedRat) (ys : List SignedRat) :
    olsCenteredSumAux idx m yMean ys = olsWeightedSumAux idx m (ys.map fun y => sAdd y (sNeg yMean)) := by
  induction ys generalizing idx with
  | nil => rfl
  | cons y ys ih =>
    simp only [olsCenteredSumAux, List.map_cons, olsWeightedSumAux, sSub]
    rw [ih (idx + 1)]

private theorem olsWeightedSumAux_replicate_zero (idx m k : Nat) :
    olsWeightedSumAux idx m (List.replicate k SignedRat.zero) ≈ₛ SignedRat.zero := by
  induction k generalizing idx with
  | zero => exact SignedRat.equiv_refl _
  | succ k ih =>
    simp only [List.replicate_succ, olsWeightedSumAux]
    have h0 : sMul ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩ SignedRat.zero ≈ₛ SignedRat.zero := by
      rw [sEquiv_zero_iff]
      unfold sMul SignedRat.zero
      dsimp only
      simp
    exact SignedRat.equiv_trans (sAdd_equiv_congr h0 (ih (idx + 1))) (sAdd_zero_right_equiv _)

private theorem olsWeightedSumAux_append (idx m : Nat) (xs ys : List SignedRat) :
    olsWeightedSumAux idx m (xs ++ ys) ≈ₛ
    sAdd (olsWeightedSumAux idx m xs) (olsWeightedSumAux (idx + xs.length) m ys) := by
  induction xs generalizing idx with
  | nil =>
    simp only [List.nil_append, List.length_nil, Nat.add_zero, olsWeightedSumAux]
    exact (sAdd_zero_left_equiv _).symm
  | cons x xs ih =>
    simp only [List.cons_append, List.length_cons, olsWeightedSumAux]
    have hRec := ih (idx + 1)
    have hIdx : idx + 1 + xs.length = idx + (xs.length + 1) := by omega
    rw [hIdx] at hRec
    exact SignedRat.equiv_trans
      (sAdd_equiv_congr (SignedRat.equiv_refl _) hRec)
      (sAdd_assoc_equiv _ _ _).symm

private def linearWeightSum : Nat → Nat → Int
  | 0, _ => 0
  | k + 1, m => linearWeightSum k m + olsWeight k m * (k : Int)

private theorem linearWeightSum_six_closed (k m : Nat) :
    6 * linearWeightSum k m =
    (k : Int) * ((k : Int) - 1) * (4 * (k : Int) - 2 - 3 * ((m - 1 : Nat) : Int)) := by
  induction k with
  | zero => simp [linearWeightSum]
  | succ k ih =>
    unfold linearWeightSum olsWeight
    rw [Int.mul_add, ih]
    let c : Int := ((m - 1 : Nat) : Int)
    show (k : Int) * ((k : Int) - 1) * (4 * (k : Int) - 2 - 3 * c) +
          6 * ((2 * (k : Int) - c) * (k : Int)) =
        (((k + 1 : Nat) : Int)) * ((((k + 1 : Nat) : Int)) - 1) *
          (4 * (((k + 1 : Nat) : Int)) - 2 - 3 * c)
    push_cast
    have hSub : ((k : Int) + 1) - 1 = (k : Int) := by omega
    rw [hSub]
    have hL1 :
        (k : Int) * ((k : Int) - 1) * (4 * (k : Int) - 2 - 3 * c) =
        (k : Int) * (((k : Int) - 1) * (4 * (k : Int) - 2 - 3 * c)) :=
      Int.mul_assoc _ _ _
    have hL2 :
        6 * ((2 * (k : Int) - c) * (k : Int)) =
        (k : Int) * (6 * (2 * (k : Int) - c)) := by
      rw [Int.mul_comm (2 * (k : Int) - c) (k : Int), ← Int.mul_assoc,
          Int.mul_comm 6 (k : Int), Int.mul_assoc]
    have hR1 :
        ((k : Int) + 1) * (k : Int) * (4 * ((k : Int) + 1) - 2 - 3 * c) =
        (k : Int) * (((k : Int) + 1) * (4 * ((k : Int) + 1) - 2 - 3 * c)) := by
      rw [Int.mul_comm ((k : Int) + 1) (k : Int), Int.mul_assoc]
    rw [hL1, hL2, hR1, ← Int.mul_add]
    apply congrArg ((k : Int) * ·)
    rw [Int.sub_mul, Int.one_mul, Int.add_mul, Int.one_mul]
    have hA : (k : Int) * (4 * ((k : Int) + 1) - 2 - 3 * c) =
              (k : Int) * (4 * (k : Int) - 2 - 3 * c) + 4 * (k : Int) := by
      have hEq : 4 * ((k : Int) + 1) - 2 - 3 * c = (4 * (k : Int) - 2 - 3 * c) + 4 := by omega
      rw [hEq, Int.mul_add, Int.mul_comm (k : Int) 4]
    rw [hA]
    omega

private theorem linearWeightSum_six_full {m : Nat} (hm : 2 ≤ m) :
    6 * linearWeightSum m m = ((m * (m * m - 1) : Nat) : Int) := by
  rw [linearWeightSum_six_closed]
  have hm1 : ((m - 1 : Nat) : Int) = (m : Int) - 1 := by omega
  rw [hm1]
  have hFactor : 4 * (m : Int) - 2 - 3 * ((m : Int) - 1) = (m : Int) + 1 := by omega
  rw [hFactor]
  have hsq : 1 ≤ m * m := by
    have : 4 ≤ m * m := Nat.mul_le_mul hm hm
    omega
  rw [Int.natCast_mul, Int.natCast_sub hsq, Int.natCast_mul, Int.natCast_one]
  rw [Int.mul_assoc]
  apply congrArg ((m : Int) * ·)
  rw [Int.sub_mul, Int.mul_add, Int.one_mul, Int.mul_one]
  omega

private theorem olsWeightedSumAux_linear_range (k m : Nat) (b : SignedRat) :
    olsWeightedSumAux 0 m ((List.range k).map fun (i : Nat) => sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b) ≈ₛ
    sMul ⟨linearWeightSum k m, 1, Nat.zero_lt_one⟩ b := by
  induction k with
  | zero =>
    exact (sMul_zero_int_equiv b).symm
  | succ k ih =>
    rw [List.range_succ, List.map_append, List.map_singleton]
    have hApp := olsWeightedSumAux_append 0 m
      ((List.range k).map fun (i : Nat) => sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b)
      [sMul ⟨(k : Int), 1, Nat.zero_lt_one⟩ b]
    rw [List.length_map, List.length_range, Nat.zero_add] at hApp
    have hTail :
        olsWeightedSumAux k m [sMul ⟨(k : Int), 1, Nat.zero_lt_one⟩ b] ≈ₛ
        sMul ⟨olsWeight k m * (k : Int), 1, Nat.zero_lt_one⟩ b := by
      simp only [olsWeightedSumAux]
      exact SignedRat.equiv_trans (sAdd_zero_right_equiv _)
        (sMul_int_mul_assoc (olsWeight k m) (k : Int) b)
    have hSum := sAdd_equiv_congr ih hTail
    have hCombine := sMul_int_add_distrib (linearWeightSum k m) (olsWeight k m * (k : Int)) b
    unfold linearWeightSum
    exact SignedRat.equiv_trans hApp (SignedRat.equiv_trans hSum hCombine)

private theorem olsWeightedSumAux_reverse_aux (ys : List SignedRat) :
    ∀ idx m, idx + ys.length ≤ m →
      olsWeightedSumAux idx m ys.reverse ≈ₛ
      sNeg (olsWeightedSumAux (m - idx - ys.length) m ys) := by
  induction ys with
  | nil =>
    intro idx m _
    simp only [List.reverse_nil, olsWeightedSumAux]
    exact sNeg_zero_equiv.symm
  | cons y rest ih =>
    intro idx m hle
    rw [List.reverse_cons]
    have hApp := olsWeightedSumAux_append idx m rest.reverse [y]
    rw [List.length_reverse] at hApp
    have hleRest : idx + rest.length ≤ m := by simp only [List.length_cons] at hle; omega
    have hRec := ih idx m hleRest
    have hj : m - idx - rest.length = (m - idx - (y :: rest).length) + 1 := by
      simp only [List.length_cons] at hle ⊢
      omega
    rw [hj] at hRec
    have hwEq : olsWeight (idx + rest.length) m = -olsWeight (m - idx - (y :: rest).length) m := by
      unfold olsWeight
      simp only [List.length_cons] at hle ⊢
      omega
    have hTail :
        olsWeightedSumAux (idx + rest.length) m [y] ≈ₛ
        sNeg (sMul ⟨olsWeight (m - idx - (y :: rest).length) m, 1, Nat.zero_lt_one⟩ y) := by
      simp only [olsWeightedSumAux]
      rw [hwEq]
      exact SignedRat.equiv_trans (sAdd_zero_right_equiv _)
        (sMul_neg_int_equiv (olsWeight (m - idx - (y :: rest).length) m) y)
    have hStep := SignedRat.equiv_trans hApp (sAdd_equiv_congr hRec hTail)
    have hComm := sAdd_comm_equiv
      (sNeg (olsWeightedSumAux ((m - idx - (y :: rest).length) + 1) m rest))
      (sNeg (sMul ⟨olsWeight (m - idx - (y :: rest).length) m, 1, Nat.zero_lt_one⟩ y))
    have hNeg := (sNeg_sAdd_equiv
      (sMul ⟨olsWeight (m - idx - (y :: rest).length) m, 1, Nat.zero_lt_one⟩ y)
      (olsWeightedSumAux ((m - idx - (y :: rest).length) + 1) m rest)).symm
    exact SignedRat.equiv_trans hStep (SignedRat.equiv_trans hComm hNeg)

private theorem sLt_equiv_congr_left {a₁ a₂ b : SignedRat} (ha : a₁ ≈ₛ a₂) (h : a₁ <ₛ b) :
    a₂ <ₛ b := by
  unfold sLt SignedRat.equiv at *
  have ha₁Pos : (0 : Int) < (a₁.den : Int) := by have := a₁.denPos; omega
  have ha₂Pos : (0 : Int) < (a₂.den : Int) := by have := a₂.denPos; omega
  have h1 : (a₁.num * (b.den : Int)) * (a₂.den : Int) < (b.num * (a₁.den : Int)) * (a₂.den : Int) :=
    Int.mul_lt_mul_of_pos_right h ha₂Pos
  have hL : (a₁.num * (b.den : Int)) * (a₂.den : Int) = (a₁.den : Int) * (a₂.num * (b.den : Int)) := by
    calc
      (a₁.num * (b.den : Int)) * (a₂.den : Int)
          = (a₁.num * (a₂.den : Int)) * (b.den : Int) := by
            rw [Int.mul_assoc, Int.mul_comm (b.den : Int) (a₂.den : Int), ← Int.mul_assoc]
      _ = (a₂.num * (a₁.den : Int)) * (b.den : Int) := by rw [ha]
      _ = (a₁.den : Int) * (a₂.num * (b.den : Int)) := by
            rw [Int.mul_assoc, Int.mul_left_comm]
  have hR : (b.num * (a₁.den : Int)) * (a₂.den : Int) = (a₁.den : Int) * (b.num * (a₂.den : Int)) := by
    rw [Int.mul_assoc, Int.mul_left_comm]
  rw [hL, hR] at h1
  exact Int.lt_of_mul_lt_mul_left h1 (Int.le_of_lt ha₁Pos)

private theorem sLt_equiv_congr_right {a b₁ b₂ : SignedRat} (hb : b₁ ≈ₛ b₂) (h : a <ₛ b₁) :
    a <ₛ b₂ := by
  unfold sLt SignedRat.equiv at *
  have hb₁Pos : (0 : Int) < (b₁.den : Int) := by have := b₁.denPos; omega
  have hb₂Pos : (0 : Int) < (b₂.den : Int) := by have := b₂.denPos; omega
  have h1 : (a.num * (b₁.den : Int)) * (b₂.den : Int) < (b₁.num * (a.den : Int)) * (b₂.den : Int) :=
    Int.mul_lt_mul_of_pos_right h hb₂Pos
  have hL : (a.num * (b₁.den : Int)) * (b₂.den : Int) = (b₁.den : Int) * (a.num * (b₂.den : Int)) := by
    rw [Int.mul_assoc, Int.mul_left_comm]
  have hR : (b₁.num * (a.den : Int)) * (b₂.den : Int) = (b₁.den : Int) * (b₂.num * (a.den : Int)) := by
    calc
      (b₁.num * (a.den : Int)) * (b₂.den : Int)
          = (b₁.num * (b₂.den : Int)) * (a.den : Int) := by
            rw [Int.mul_assoc, Int.mul_comm (a.den : Int) (b₂.den : Int), ← Int.mul_assoc]
      _ = (b₂.num * (b₁.den : Int)) * (a.den : Int) := by rw [hb]
      _ = (b₁.den : Int) * (b₂.num * (a.den : Int)) := by
            rw [Int.mul_assoc, Int.mul_left_comm]
  rw [hL, hR] at h1
  exact Int.lt_of_mul_lt_mul_left h1 (Int.le_of_lt hb₁Pos)

private theorem sNeg_lt_sNeg_iff (a b : SignedRat) : sNeg b <ₛ sNeg a ↔ a <ₛ b := by
  unfold sNeg sLt
  dsimp only
  rw [Int.neg_mul, Int.neg_mul]
  omega

private theorem sLt_iff_not_sLe (a b : SignedRat) : a <ₛ b ↔ ¬ (b ≤ₛ a) := by
  unfold sLt sLe
  omega

private theorem sAdd_le_sAdd {a b c d : SignedRat} (hab : a ≤ₛ b) (hcd : c ≤ₛ d) :
    sAdd a c ≤ₛ sAdd b d := by
  unfold sAdd sLe at *
  dsimp only
  rw [Int.natCast_mul, Int.natCast_mul, Int.add_mul, Int.add_mul]
  have hcdPos : (0 : Int) ≤ (c.den : Int) * (d.den : Int) :=
    Int.mul_nonneg (Int.natCast_nonneg c.den) (Int.natCast_nonneg d.den)
  have habPos : (0 : Int) ≤ (a.den : Int) * (b.den : Int) :=
    Int.mul_nonneg (Int.natCast_nonneg a.den) (Int.natCast_nonneg b.den)
  have h1 : (a.num * (c.den : Int)) * ((b.den : Int) * (d.den : Int)) ≤
            (b.num * (d.den : Int)) * ((a.den : Int) * (c.den : Int)) := by
    have hL : (a.num * (c.den : Int)) * ((b.den : Int) * (d.den : Int)) =
              (a.num * (b.den : Int)) * ((c.den : Int) * (d.den : Int)) := by
      rw [Int.mul_assoc, Int.mul_left_comm (c.den : Int) (b.den : Int) (d.den : Int), ← Int.mul_assoc]
    have hR : (b.num * (d.den : Int)) * ((a.den : Int) * (c.den : Int)) =
              (b.num * (a.den : Int)) * ((c.den : Int) * (d.den : Int)) := by
      rw [Int.mul_assoc, Int.mul_left_comm (d.den : Int) (a.den : Int) (c.den : Int),
          Int.mul_comm (d.den : Int) (c.den : Int), ← Int.mul_assoc]
    rw [hL, hR]
    exact Int.mul_le_mul_of_nonneg_right hab hcdPos
  have h2 : (c.num * (a.den : Int)) * ((b.den : Int) * (d.den : Int)) ≤
            (d.num * (b.den : Int)) * ((a.den : Int) * (c.den : Int)) := by
    have hL : (c.num * (a.den : Int)) * ((b.den : Int) * (d.den : Int)) =
              (c.num * (d.den : Int)) * ((a.den : Int) * (b.den : Int)) := by
      rw [Int.mul_assoc, Int.mul_comm (b.den : Int) (d.den : Int),
          Int.mul_left_comm (a.den : Int) (d.den : Int) (b.den : Int), ← Int.mul_assoc]
    have hR : (d.num * (b.den : Int)) * ((a.den : Int) * (c.den : Int)) =
              (d.num * (c.den : Int)) * ((a.den : Int) * (b.den : Int)) := by
      rw [Int.mul_assoc, Int.mul_comm (a.den : Int) (c.den : Int),
          Int.mul_left_comm (b.den : Int) (c.den : Int) (a.den : Int),
          Int.mul_comm (b.den : Int) (a.den : Int), ← Int.mul_assoc]
    rw [hL, hR]
    exact Int.mul_le_mul_of_nonneg_right hcd habPos
  exact Int.add_le_add h1 h2

private def intPosPart (w : Int) : Int := if 0 ≤ w then w else 0
private def intNegPart (w : Int) : Int := if w ≤ 0 then -w else 0

private def posWeightSumAux (idx : Nat) : Nat → Nat → Int
  | 0, _ => 0
  | k + 1, m => intPosPart (olsWeight idx m) + posWeightSumAux (idx + 1) k m

private def negWeightSumAux (idx : Nat) : Nat → Nat → Int
  | 0, _ => 0
  | k + 1, m => intNegPart (olsWeight idx m) + negWeightSumAux (idx + 1) k m

private theorem sMul_weight_unit_bounds (w : Int) {y : NNRat} (hy : y ≤ NNRat.one) :
    (⟨-intNegPart w, 1, Nat.zero_lt_one⟩ : SignedRat) ≤ₛ sMul ⟨w, 1, Nat.zero_lt_one⟩ (ofNNRat y) ∧
    sMul ⟨w, 1, Nat.zero_lt_one⟩ (ofNNRat y) ≤ₛ ⟨intPosPart w, 1, Nat.zero_lt_one⟩ := by
  have hyLe : (y.num : Int) ≤ (y.den : Int) := by
    rw [NNRat.le_one_iff] at hy
    omega
  have hy0 : (0 : Int) ≤ (y.num : Int) := Int.natCast_nonneg y.num
  have hd0 : (0 : Int) ≤ (y.den : Int) := Int.natCast_nonneg y.den
  unfold sMul ofNNRat sLe intPosPart intNegPart
  dsimp only
  simp only [Nat.one_mul, Int.natCast_one, Int.mul_one]
  by_cases hw : 0 ≤ w
  · have hNegIf : (if w ≤ 0 then -w else 0) = 0 := by
      split
      · omega
      · rfl
    simp only [hw, ↓reduceIte, hNegIf, Int.neg_zero, Int.zero_mul]
    exact ⟨Int.mul_nonneg hw hy0, Int.mul_le_mul_of_nonneg_left hyLe hw⟩
  · have hwLe : w ≤ 0 := by omega
    have hwNeg : 0 ≤ -w := by omega
    simp only [hw, hwLe, ↓reduceIte, Int.neg_neg, Int.zero_mul]
    have h1 : (-w) * (y.num : Int) ≤ (-w) * (y.den : Int) :=
      Int.mul_le_mul_of_nonneg_left hyLe hwNeg
    have h2 : (0 : Int) ≤ (-w) * (y.num : Int) := Int.mul_nonneg hwNeg hy0
    rw [Int.neg_mul, Int.neg_mul] at h1
    rw [Int.neg_mul] at h2
    omega

private theorem olsWeightedSumAux_unit_bounds (idx m : Nat) (ys : List NNRat)
    (hunit : ∀ y ∈ ys, y ≤ NNRat.one) :
    (⟨-negWeightSumAux idx ys.length m, 1, Nat.zero_lt_one⟩ : SignedRat) ≤ₛ
      olsWeightedSumAux idx m (ys.map ofNNRat) ∧
    olsWeightedSumAux idx m (ys.map ofNNRat) ≤ₛ
      ⟨posWeightSumAux idx ys.length m, 1, Nat.zero_lt_one⟩ := by
  induction ys generalizing idx with
  | nil =>
    simp only [List.length_nil, List.map_nil, olsWeightedSumAux, posWeightSumAux, negWeightSumAux]
    exact ⟨sLe_refl _, sLe_refl _⟩
  | cons y ys ih =>
    simp only [List.length_cons, List.map_cons, olsWeightedSumAux, posWeightSumAux, negWeightSumAux]
    have ⟨hLo1, hHi1⟩ := sMul_weight_unit_bounds (olsWeight idx m) (hunit y (List.mem_cons_self ..))
    have ⟨hLo2, hHi2⟩ := ih (idx + 1) (fun z hz => hunit z (List.mem_cons_of_mem y hz))
    have hLoAdd := sAdd_le_sAdd hLo1 hLo2
    have hHiAdd := sAdd_le_sAdd hHi1 hHi2
    have hEqLo :
        sAdd ⟨-intNegPart (olsWeight idx m), 1, Nat.zero_lt_one⟩
             ⟨-negWeightSumAux (idx + 1) ys.length m, 1, Nat.zero_lt_one⟩ ≈ₛ
        ⟨-(intNegPart (olsWeight idx m) + negWeightSumAux (idx + 1) ys.length m), 1, Nat.zero_lt_one⟩ := by
      unfold sAdd SignedRat.equiv
      dsimp only
      omega
    have hEqHi :
        sAdd ⟨intPosPart (olsWeight idx m), 1, Nat.zero_lt_one⟩
             ⟨posWeightSumAux (idx + 1) ys.length m, 1, Nat.zero_lt_one⟩ ≈ₛ
        ⟨intPosPart (olsWeight idx m) + posWeightSumAux (idx + 1) ys.length m, 1, Nat.zero_lt_one⟩ := by
      unfold sAdd SignedRat.equiv
      dsimp only
      omega
    exact ⟨sLe_of_equiv_left hEqLo hLoAdd, sLe_of_equiv_right hEqHi hHiAdd⟩

private theorem posWeightSumAux_shift_step (idx k m : Nat) (hm : 1 ≤ m) :
    posWeightSumAux (idx + 1) k (m + 2) = posWeightSumAux idx k m := by
  induction k generalizing idx with
  | zero => rfl
  | succ k ih =>
    unfold posWeightSumAux
    have hw : olsWeight (idx + 1) (m + 2) = olsWeight idx m := by
      unfold olsWeight
      omega
    rw [hw, ih (idx + 1)]

private theorem negWeightSumAux_shift_step (idx k m : Nat) (hm : 1 ≤ m) :
    negWeightSumAux (idx + 1) k (m + 2) = negWeightSumAux idx k m := by
  induction k generalizing idx with
  | zero => rfl
  | succ k ih =>
    unfold negWeightSumAux
    have hw : olsWeight (idx + 1) (m + 2) = olsWeight idx m := by
      unfold olsWeight
      omega
    rw [hw, ih (idx + 1)]

private theorem posWeightSumAux_append (idx k m : Nat) :
    posWeightSumAux idx (k + 1) m = posWeightSumAux idx k m + intPosPart (olsWeight (idx + k) m) := by
  induction k generalizing idx with
  | zero =>
    simp [posWeightSumAux]
  | succ k ih =>
    unfold posWeightSumAux
    rw [ih (idx + 1)]
    have hIdx : idx + 1 + k = idx + (k + 1) := by omega
    rw [hIdx, Int.add_assoc]

private theorem negWeightSumAux_append (idx k m : Nat) :
    negWeightSumAux idx (k + 1) m = negWeightSumAux idx k m + intNegPart (olsWeight (idx + k) m) := by
  induction k generalizing idx with
  | zero =>
    simp [negWeightSumAux]
  | succ k ih =>
    unfold negWeightSumAux
    rw [ih (idx + 1)]
    have hIdx : idx + 1 + k = idx + (k + 1) := by omega
    rw [hIdx, Int.add_assoc]

private theorem pos_and_neg_weightSum_quad_bound (m : Nat) :
    4 * posWeightSumAux 0 m m ≤ (m : Int) * (m : Int) ∧
    4 * negWeightSumAux 0 m m ≤ (m : Int) * (m : Int) := by
  induction m using Nat.strongRecOn with
  | ind m ih =>
    match m with
    | 0 =>
      simp [posWeightSumAux, negWeightSumAux]
    | 1 =>
      simp [posWeightSumAux, negWeightSumAux, intPosPart, intNegPart, olsWeight]
    | 2 =>
      simp [posWeightSumAux, negWeightSumAux, intPosPart, intNegPart, olsWeight]
    | n + 3 =>
      have ⟨hPosPrev, hNegPrev⟩ := ih (n + 1) (by omega)
      have hPosStep : posWeightSumAux 0 (n + 3) (n + 3) =
          posWeightSumAux 0 (n + 1) (n + 1) + ((n + 2 : Nat) : Int) := by
        have hUnf : posWeightSumAux 0 (n + 3) (n + 3) =
            intPosPart (olsWeight 0 (n + 3)) + posWeightSumAux 1 (n + 2) (n + 3) := rfl
        rw [hUnf]
        have h0 : intPosPart (olsWeight 0 (n + 3)) = 0 := by
          unfold intPosPart olsWeight; split <;> omega
        rw [h0, Int.zero_add, posWeightSumAux_append 1 (n + 1) (n + 3),
            posWeightSumAux_shift_step 0 (n + 1) (n + 1) (by omega)]
        have hLast : intPosPart (olsWeight (1 + (n + 1)) (n + 3)) = ((n + 2 : Nat) : Int) := by
          unfold intPosPart olsWeight; split <;> omega
        rw [hLast]
      have hNegStep : negWeightSumAux 0 (n + 3) (n + 3) =
          negWeightSumAux 0 (n + 1) (n + 1) + ((n + 2 : Nat) : Int) := by
        have hUnf : negWeightSumAux 0 (n + 3) (n + 3) =
            intNegPart (olsWeight 0 (n + 3)) + negWeightSumAux 1 (n + 2) (n + 3) := rfl
        rw [hUnf]
        have h0 : intNegPart (olsWeight 0 (n + 3)) = ((n + 2 : Nat) : Int) := by
          unfold intNegPart olsWeight; split <;> omega
        rw [h0, negWeightSumAux_append 1 (n + 1) (n + 3),
            negWeightSumAux_shift_step 0 (n + 1) (n + 1) (by omega)]
        have hLast : intNegPart (olsWeight (1 + (n + 1)) (n + 3)) = 0 := by
          unfold intNegPart olsWeight; split <;> omega
        rw [hLast, Int.add_zero, Int.add_comm]
      have hQuad : ((n + 3 : Nat) : Int) * ((n + 3 : Nat) : Int) =
          ((n + 1 : Nat) : Int) * ((n + 1 : Nat) : Int) + 4 * ((n + 2 : Nat) : Int) := by
        push_cast
        rw [Int.add_mul, Int.mul_add, Int.mul_add, Int.add_mul, Int.mul_add, Int.mul_add]
        omega
      rw [hPosStep, hNegStep, hQuad, Int.mul_add, Int.mul_add]
      exact ⟨Int.add_le_add_right hPosPrev _, Int.add_le_add_right hNegPrev _⟩

/-! ## Group 3 — Exact OLS Trend Algebra (`10` Theorems) -/

/--
**Theorem 15 (`summarizeMetricTrend_insufficientData_iff`)**:
`summarizeMetricTrend` classifies a metric as `INSUFFICIENT_DATA` (with `slope = none`) iff the
number of valid numeric points in the window is strictly less than `2`.
-/
theorem summarizeMetricTrend_insufficientData_iff
    (metricId : String)
    (windowRuns : List TrendRunEntry)
    (slopeThreshold : NNRat) :
    ((summarizeMetricTrend metricId windowRuns slopeThreshold).direction = .insufficientData ↔
     (summarizeMetricTrend metricId windowRuns slopeThreshold).validPoints < 2) ∧
    ((summarizeMetricTrend metricId windowRuns slopeThreshold).slope = none ↔
     (summarizeMetricTrend metricId windowRuns slopeThreshold).validPoints < 2) := by
  unfold summarizeMetricTrend
  dsimp only
  by_cases h2 : 2 ≤ (windowRuns.filterMap fun entry => lookupOptScore entry.metricScores metricId).length
  · simp only [h2, ↓reduceDIte]
    have hDirNe :
        classifyTrendDirection
          (computeOlsSlopeNNRat
            (windowRuns.filterMap fun entry => lookupOptScore entry.metricScores metricId) h2)
          slopeThreshold ≠ .insufficientData := by
      unfold classifyTrendDirection
      split
      · decide
      · split <;> decide
    constructor
    · constructor
      · intro h; exact absurd h hDirNe
      · intro hlt; omega
    · constructor
      · intro h; simp at h
      · intro hlt; omega
  · simp only [h2, ↓reduceDIte]
    constructor
    · exact ⟨fun _ => by omega, fun _ => trivial⟩
    · exact ⟨fun _ => by omega, fun _ => trivial⟩

/--
**Theorem 16 (`summarizeMetricTrend_point_conservation`)**:
Every metric trend summary strictly conserves window points: `validPoints + missingPoints = windowRuns`
and `windowRuns = entries.length`.
-/
theorem summarizeMetricTrend_point_conservation
    (metricId : String)
    (windowRuns : List TrendRunEntry)
    (slopeThreshold : NNRat) :
    let s := summarizeMetricTrend metricId windowRuns slopeThreshold
    s.validPoints + s.missingPoints = s.windowRuns ∧ s.windowRuns = windowRuns.length := by
  have hle : (windowRuns.filterMap fun entry => lookupOptScore entry.metricScores metricId).length ≤
      windowRuns.length := length_filterMap_le _ windowRuns
  unfold summarizeMetricTrend
  dsimp only
  by_cases h2 : 2 ≤ (windowRuns.filterMap fun entry => lookupOptScore entry.metricScores metricId).length
  · simp only [h2, ↓reduceDIte]
    exact ⟨by omega, trivial⟩
  · simp only [h2, ↓reduceDIte]
    exact ⟨by omega, trivial⟩

/--
**Theorem 17 (`computeOlsSlope_eq_centered_form`)**:
The uncentered weighted-sum OLS slope formula (`computeOlsSlopeSigned`) is identically equivalent
(`≈ₛ`) to the direct centered-covariance formula (`computeOlsSlopeCentered`) mirroring `trend.py#L28-L34`.
-/
theorem computeOlsSlope_eq_centered_form (ys : List SignedRat) (hm : 2 ≤ ys.length) :
    computeOlsSlopeSigned ys hm ≈ₛ computeOlsSlopeCentered ys hm := by
  unfold computeOlsSlopeSigned computeOlsSlopeCentered
  dsimp only
  rw [olsCenteredSumAux_eq_map]
  have hSum := (olsWeightedSumAux_shift_full ys (sNeg (sMeanList ys (by omega))) (by omega)).symm
  exact sDivNat_equiv_congr
    (sMul_equiv_congr (SignedRat.equiv_refl _) hSum)
    rfl (olsDenom_pos hm) (olsDenom_pos hm)

/--
**Theorem 18 (`computeOlsSlope_const_zero`)**:
Any constant score series of length `m ≥ 2` has exact OLS slope `0` and classifies as `STABLE`
for every non-negative slope threshold.
-/
theorem computeOlsSlope_const_zero (c : SignedRat) (m : Nat) (hm : 2 ≤ m)
    (slopeThreshold : NNRat) :
    let slope := computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm)
    slope ≈ₛ SignedRat.zero ∧ classifyTrendDirection slope slopeThreshold = .stable := by
  have hRepAll : ∀ k : Nat, List.replicate k c = (List.replicate k SignedRat.zero).map (fun y => sAdd y c) := by
    intro k
    induction k with
    | zero => rfl
    | succ k ih =>
      simp only [List.replicate_succ, List.map_cons]
      have h0 : sAdd SignedRat.zero c = c := by
        cases c with
        | mk num den denPos =>
          unfold sAdd SignedRat.zero
          simp
      rw [h0, ← ih]
  have hRep := hRepAll m
  have hmRep : 2 ≤ (List.replicate m c).length := by rw [List.length_replicate]; exact hm
  have hSumZero : olsWeightedSumAux 0 (List.replicate m c).length (List.replicate m c) ≈ₛ SignedRat.zero := by
    rw [hRep]
    have hLen : ((List.replicate m SignedRat.zero).map fun y => sAdd y c).length =
        (List.replicate m SignedRat.zero).length := List.length_map _
    rw [hLen]
    have hShift := olsWeightedSumAux_shift_full (List.replicate m SignedRat.zero) c
      (by rw [List.length_replicate]; omega)
    exact SignedRat.equiv_trans hShift (olsWeightedSumAux_replicate_zero 0 _ m)
  have hSlopeZero :
      computeOlsSlopeSigned (List.replicate m c) hmRep ≈ₛ SignedRat.zero := by
    unfold computeOlsSlopeSigned
    dsimp only
    have hNum : sMul ⟨6, 1, Nat.zero_lt_one⟩
        (olsWeightedSumAux 0 (List.replicate m c).length (List.replicate m c)) ≈ₛ SignedRat.zero := by
      have h1 := sMul_equiv_congr (SignedRat.equiv_refl ⟨6, 1, Nat.zero_lt_one⟩) hSumZero
      have h2 : sMul ⟨6, 1, Nat.zero_lt_one⟩ SignedRat.zero ≈ₛ SignedRat.zero := by
        rw [sEquiv_zero_iff]; unfold sMul SignedRat.zero; simp
      exact SignedRat.equiv_trans h1 h2
    have hDiv := sDivNat_equiv_congr hNum rfl (olsDenom_pos hmRep) (olsDenom_pos hmRep)
    have hDivZ : sDivNat SignedRat.zero
        ((List.replicate m c).length * ((List.replicate m c).length * (List.replicate m c).length - 1))
        (olsDenom_pos hmRep) ≈ₛ SignedRat.zero := by
      rw [sEquiv_zero_iff]; rfl
    exact SignedRat.equiv_trans hDiv hDivZ
  refine ⟨hSlopeZero, ?_⟩
  have hNumZero : (computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm)).num = 0 :=
    (sEquiv_zero_iff _).mp hSlopeZero
  unfold classifyTrendDirection
  have hNotDeg : ¬ (computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm) <ₛ
      sNeg (ofNNRat slopeThreshold)) := by
    unfold sLt sNeg ofNNRat
    dsimp only
    rw [hNumZero, Int.zero_mul, Int.neg_mul]
    have hnn : (0 : Int) ≤ (slopeThreshold.num : Int) *
        ((computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm)).den : Int) :=
      Int.mul_nonneg (Int.natCast_nonneg _) (Int.natCast_nonneg _)
    omega
  have hNotImp : ¬ (ofNNRat slopeThreshold <ₛ
      computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm)) := by
    unfold sLt ofNNRat
    dsimp only
    rw [hNumZero, Int.zero_mul]
    have hnn : (0 : Int) ≤ (slopeThreshold.num : Int) *
        ((computeOlsSlopeSigned (List.replicate m c) (by rw [List.length_replicate]; exact hm)).den : Int) :=
      Int.mul_nonneg (Int.natCast_nonneg _) (Int.natCast_nonneg _)
    omega
  simp [decide_eq_false hNotDeg, decide_eq_false hNotImp]

/--
**Theorem 19 (`computeOlsSlope_linear_exact`)**:
For any exact affine series `y_i = a + i · b` (`i = 0, ..., m - 1`, `m ≥ 2`), `computeOlsSlopeSigned`
recovers the exact rational slope `b`.
-/
theorem computeOlsSlope_linear_exact (a b : SignedRat) (m : Nat) (hm : 2 ≤ m) :
    let ys := (List.range m).map (fun (i : Nat) => sAdd a (sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b))
    computeOlsSlopeSigned ys (by rw [List.length_map, List.length_range]; exact hm) ≈ₛ b := by
  let ys := (List.range m).map (fun (i : Nat) => sAdd a (sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b))
  let lin := (List.range m).map (fun (i : Nat) => sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b)
  let shifted := lin.map (fun y => sAdd y a)
  have hLenLin : lin.length = m := by rw [List.length_map, List.length_range]
  have hLenYs : ys.length = m := by rw [List.length_map, List.length_range]
  have hmYs : 2 ≤ ys.length := by rw [hLenYs]; exact hm
  have hCommList :
      olsWeightedSumAux 0 m ys ≈ₛ olsWeightedSumAux 0 m shifted := by
    have hGen : ∀ (idx : Nat) (ks : List Nat),
        olsWeightedSumAux idx m (ks.map fun (i : Nat) => sAdd a (sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b)) ≈ₛ
        olsWeightedSumAux idx m ((ks.map fun (i : Nat) => sMul ⟨(i : Int), 1, Nat.zero_lt_one⟩ b).map fun y => sAdd y a) := by
      intro idx ks
      induction ks generalizing idx with
      | nil => exact SignedRat.equiv_refl _
      | cons k ks ih =>
        simp only [List.map_cons, olsWeightedSumAux]
        exact sAdd_equiv_congr
          (sMul_equiv_congr (SignedRat.equiv_refl _) (sAdd_comm_equiv a _))
          (ih (idx + 1))
    exact hGen 0 (List.range m)
  have hShift : olsWeightedSumAux 0 m shifted ≈ₛ olsWeightedSumAux 0 m lin := by
    have hS := olsWeightedSumAux_shift_full lin a (by rw [hLenLin]; omega)
    rw [hLenLin] at hS
    exact hS
  have hLin : olsWeightedSumAux 0 m lin ≈ₛ sMul ⟨linearWeightSum m m, 1, Nat.zero_lt_one⟩ b :=
    olsWeightedSumAux_linear_range m m b
  have hTotalSum :
      olsWeightedSumAux 0 m ys ≈ₛ sMul ⟨linearWeightSum m m, 1, Nat.zero_lt_one⟩ b :=
    SignedRat.equiv_trans hCommList (SignedRat.equiv_trans hShift hLin)
  show computeOlsSlopeSigned ys hmYs ≈ₛ b
  unfold computeOlsSlopeSigned
  dsimp only
  have hNumEq :
      sMul ⟨6, 1, Nat.zero_lt_one⟩ (olsWeightedSumAux 0 ys.length ys) ≈ₛ
      sMul ⟨((m * (m * m - 1) : Nat) : Int), 1, Nat.zero_lt_one⟩ b := by
    rw [hLenYs]
    have h1 := sMul_equiv_congr (SignedRat.equiv_refl ⟨6, 1, Nat.zero_lt_one⟩) hTotalSum
    have h2 := sMul_int_mul_assoc 6 (linearWeightSum m m) b
    rw [linearWeightSum_six_full hm] at h2
    exact SignedRat.equiv_trans h1 h2
  have hDenEq : ys.length * (ys.length * ys.length - 1) = m * (m * m - 1) := by rw [hLenYs]
  have hDiv := sDivNat_equiv_congr hNumEq hDenEq (olsDenom_pos hmYs) (olsDenom_pos hm)
  apply SignedRat.equiv_trans hDiv
  unfold sDivNat sMul SignedRat.equiv
  dsimp only
  simp only [Nat.one_mul]
  rw [Int.natCast_mul b.den (m * (m * m - 1)), Int.mul_comm ((m * (m * m - 1) : Nat) : Int) b.num,
      Int.mul_assoc, Int.mul_comm ((m * (m * m - 1) : Nat) : Int) (b.den : Int)]

/--
**Theorem 20 (`computeOlsSlope_shift_invariant`)**:
Adding any vertical constant `c` to every observation leaves the exact OLS slope unchanged (`≈ₛ`).
-/
theorem computeOlsSlope_shift_invariant (ys : List SignedRat) (c : SignedRat)
    (hm : 2 ≤ ys.length) :
    computeOlsSlopeSigned (ys.map fun y => sAdd y c) (by rw [List.length_map]; exact hm) ≈ₛ
    computeOlsSlopeSigned ys hm := by
  unfold computeOlsSlopeSigned
  dsimp only
  have hLen : (ys.map fun y => sAdd y c).length = ys.length := List.length_map _
  have hSum :
      olsWeightedSumAux 0 (ys.map fun y => sAdd y c).length (ys.map fun y => sAdd y c) ≈ₛ
      olsWeightedSumAux 0 ys.length ys := by
    rw [hLen]
    exact olsWeightedSumAux_shift_full ys c (by omega)
  exact sDivNat_equiv_congr
    (sMul_equiv_congr (SignedRat.equiv_refl _) hSum)
    (by rw [hLen])
    (olsDenom_pos (by rw [hLen]; exact hm))
    (olsDenom_pos hm)

/--
**Theorem 21 (`computeOlsSlope_reverse_antisymm`)**:
Reversing the chronological order of observations negates the exact OLS slope (`≈ₛ`).
-/
theorem computeOlsSlope_reverse_antisymm (ys : List SignedRat) (hm : 2 ≤ ys.length) :
    computeOlsSlopeSigned ys.reverse (by rw [List.length_reverse]; exact hm) ≈ₛ
    sNeg (computeOlsSlopeSigned ys hm) := by
  unfold computeOlsSlopeSigned
  dsimp only
  have hLen : ys.reverse.length = ys.length := List.length_reverse
  have hRevSum :
      olsWeightedSumAux 0 ys.reverse.length ys.reverse ≈ₛ
      sNeg (olsWeightedSumAux 0 ys.length ys) := by
    rw [hLen]
    have hAux := olsWeightedSumAux_reverse_aux ys 0 ys.length (by omega)
    have hSub : ys.length - 0 - ys.length = 0 := by omega
    rw [hSub] at hAux
    exact hAux
  have hMul :
      sMul ⟨6, 1, Nat.zero_lt_one⟩ (olsWeightedSumAux 0 ys.reverse.length ys.reverse) ≈ₛ
      sNeg (sMul ⟨6, 1, Nat.zero_lt_one⟩ (olsWeightedSumAux 0 ys.length ys)) :=
    SignedRat.equiv_trans
      (sMul_equiv_congr (SignedRat.equiv_refl _) hRevSum)
      (sMul_sNeg_right_equiv _ _)
  have hmRev : 2 ≤ ys.reverse.length := by rw [hLen]; exact hm
  have hDenEq : ys.reverse.length * (ys.reverse.length * ys.reverse.length - 1) =
      ys.length * (ys.length * ys.length - 1) := by rw [hLen]
  have hDiv := sDivNat_equiv_congr hMul hDenEq (olsDenom_pos hmRev) (olsDenom_pos hm)
  exact SignedRat.equiv_trans hDiv (sDivNat_sNeg_equiv _ _ _)

/--
**Theorem 22 (`classifyTrendDirection_reverse_duality`)**:
Reversing a series swaps `IMPROVING ↔ DEGRADING` and preserves `STABLE` identically.
-/
theorem classifyTrendDirection_reverse_duality
    (ys : List SignedRat) (hm : 2 ≤ ys.length) (slopeThreshold : NNRat) :
    let s := computeOlsSlopeSigned ys hm
    let sRev := computeOlsSlopeSigned ys.reverse (by rw [List.length_reverse]; exact hm)
    (classifyTrendDirection s slopeThreshold = .improving ↔
     classifyTrendDirection sRev slopeThreshold = .degrading) ∧
    (classifyTrendDirection s slopeThreshold = .degrading ↔
     classifyTrendDirection sRev slopeThreshold = .improving) ∧
    (classifyTrendDirection s slopeThreshold = .stable ↔
     classifyTrendDirection sRev slopeThreshold = .stable) := by
  let s := computeOlsSlopeSigned ys hm
  let sRev := computeOlsSlopeSigned ys.reverse (by rw [List.length_reverse]; exact hm)
  have hEq : sRev ≈ₛ sNeg s := computeOlsSlope_reverse_antisymm ys hm
  have hDegIff : sRev <ₛ sNeg (ofNNRat slopeThreshold) ↔ ofNNRat slopeThreshold <ₛ s := by
    constructor
    · intro h
      have h1 : sNeg s <ₛ sNeg (ofNNRat slopeThreshold) := sLt_equiv_congr_left hEq h
      exact (sNeg_lt_sNeg_iff _ _).mp h1
    · intro h
      have h1 : sNeg s <ₛ sNeg (ofNNRat slopeThreshold) := (sNeg_lt_sNeg_iff _ _).mpr h
      exact sLt_equiv_congr_left hEq.symm h1
  have hImpIff : ofNNRat slopeThreshold <ₛ sRev ↔ s <ₛ sNeg (ofNNRat slopeThreshold) := by
    constructor
    · intro h
      have h1 : ofNNRat slopeThreshold <ₛ sNeg s := sLt_equiv_congr_right hEq h
      have h2 : sNeg (sNeg s) <ₛ sNeg (ofNNRat slopeThreshold) := (sNeg_lt_sNeg_iff _ _).mpr h1
      simpa [EvalForgeFormal.Stats.sNeg_involutive] using h2
    · intro h
      have h1 : sNeg (sNeg s) <ₛ sNeg (ofNNRat slopeThreshold) := by
        simpa [EvalForgeFormal.Stats.sNeg_involutive] using h
      have h2 : ofNNRat slopeThreshold <ₛ sNeg s := (sNeg_lt_sNeg_iff _ _).mp h1
      exact sLt_equiv_congr_right hEq.symm h2
  have hMutex : ¬ (s <ₛ sNeg (ofNNRat slopeThreshold) ∧ ofNNRat slopeThreshold <ₛ s) := by
    rintro ⟨h1, h2⟩
    unfold sLt at h1 h2
    unfold sNeg ofNNRat at h1
    unfold ofNNRat at h2
    dsimp only at h1 h2
    rw [Int.neg_mul] at h1
    have hnn : (0 : Int) ≤ (slopeThreshold.num : Int) * (s.den : Int) :=
      Int.mul_nonneg (Int.natCast_nonneg _) (Int.natCast_nonneg _)
    omega
  dsimp only
  change
    (classifyTrendDirection s slopeThreshold = .improving ↔
     classifyTrendDirection sRev slopeThreshold = .degrading) ∧
    (classifyTrendDirection s slopeThreshold = .degrading ↔
     classifyTrendDirection sRev slopeThreshold = .improving) ∧
    (classifyTrendDirection s slopeThreshold = .stable ↔
     classifyTrendDirection sRev slopeThreshold = .stable)
  refine ⟨?_, ?_, ?_⟩
  · unfold classifyTrendDirection
    by_cases hA : s <ₛ sNeg (ofNNRat slopeThreshold)
    · have hB : ¬ (ofNNRat slopeThreshold <ₛ s) := fun hb => hMutex ⟨hA, hb⟩
      have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
      have hRevB : ofNNRat slopeThreshold <ₛ sRev := hImpIff.mpr hA
      simp [decide_eq_true hA, decide_eq_false hRevA, decide_eq_true hRevB]
    · by_cases hB : ofNNRat slopeThreshold <ₛ s
      · have hRevA : sRev <ₛ sNeg (ofNNRat slopeThreshold) := hDegIff.mpr hB
        simp [decide_eq_false hA, decide_eq_true hB, decide_eq_true hRevA]
      · have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
        have hRevB : ¬ (ofNNRat slopeThreshold <ₛ sRev) := fun hc => hA (hImpIff.mp hc)
        simp [decide_eq_false hA, decide_eq_false hB, decide_eq_false hRevA, decide_eq_false hRevB]
  · unfold classifyTrendDirection
    by_cases hA : s <ₛ sNeg (ofNNRat slopeThreshold)
    · have hB : ¬ (ofNNRat slopeThreshold <ₛ s) := fun hb => hMutex ⟨hA, hb⟩
      have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
      have hRevB : ofNNRat slopeThreshold <ₛ sRev := hImpIff.mpr hA
      simp [decide_eq_true hA, decide_eq_false hRevA, decide_eq_true hRevB]
    · by_cases hB : ofNNRat slopeThreshold <ₛ s
      · have hRevA : sRev <ₛ sNeg (ofNNRat slopeThreshold) := hDegIff.mpr hB
        simp [decide_eq_false hA, decide_eq_true hB, decide_eq_true hRevA]
      · have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
        have hRevB : ¬ (ofNNRat slopeThreshold <ₛ sRev) := fun hc => hA (hImpIff.mp hc)
        simp [decide_eq_false hA, decide_eq_false hB, decide_eq_false hRevA, decide_eq_false hRevB]
  · unfold classifyTrendDirection
    by_cases hA : s <ₛ sNeg (ofNNRat slopeThreshold)
    · have hB : ¬ (ofNNRat slopeThreshold <ₛ s) := fun hb => hMutex ⟨hA, hb⟩
      have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
      have hRevB : ofNNRat slopeThreshold <ₛ sRev := hImpIff.mpr hA
      simp [decide_eq_true hA, decide_eq_false hRevA, decide_eq_true hRevB]
    · by_cases hB : ofNNRat slopeThreshold <ₛ s
      · have hRevA : sRev <ₛ sNeg (ofNNRat slopeThreshold) := hDegIff.mpr hB
        simp [decide_eq_false hA, decide_eq_true hB, decide_eq_true hRevA]
      · have hRevA : ¬ (sRev <ₛ sNeg (ofNNRat slopeThreshold)) := fun hc => hB (hDegIff.mp hc)
        have hRevB : ¬ (ofNNRat slopeThreshold <ₛ sRev) := fun hc => hA (hImpIff.mp hc)
        simp [decide_eq_false hA, decide_eq_false hB, decide_eq_false hRevA, decide_eq_false hRevB]

/--
**Theorem 23 (`computeOlsSlope_unit_sharp_bound`)**:
For any series of `m ≥ 2` scores in `[0, 1]`, the exact OLS slope satisfies the sharp universal
bound `|slope| ≤ 3m / (2(m^2 - 1)) ≤ 1` (hence `slope ∈ [-1, 1]`).
-/
theorem computeOlsSlope_unit_sharp_bound (ys : List NNRat) (hm : 2 ≤ ys.length)
    (hunit : ∀ y ∈ ys, y ≤ NNRat.one) :
    let m := ys.length
    let slope := computeOlsSlopeNNRat ys hm
    let sharpBound : NNRat := ⟨3 * m, 2 * (m * m - 1), by
      have : 4 ≤ m * m := Nat.mul_le_mul hm hm
      omega⟩
    sNeg (ofNNRat sharpBound) ≤ₛ slope ∧
    slope ≤ₛ ofNNRat sharpBound ∧
    sharpBound ≤ NNRat.one ∧
    sNegOne ≤ₛ slope ∧
    slope ≤ₛ sOne := by
  let m := ys.length
  let sharpBound : NNRat := ⟨3 * m, 2 * (m * m - 1), by
    have : 4 ≤ m * m := Nat.mul_le_mul hm hm
    omega⟩
  have hSharpLeOne : sharpBound ≤ NNRat.one := by
    rw [NNRat.le_one_iff]
    dsimp only [sharpBound]
    have h4 : 4 ≤ m * m := Nat.mul_le_mul hm hm
    have h2m : 2 * m ≤ m * m := Nat.mul_le_mul_right m hm
    omega
  have ⟨hSumLo, hSumHi⟩ := olsWeightedSumAux_unit_bounds 0 m ys hunit
  have ⟨hPosQuad, hNegQuad⟩ := pos_and_neg_weightSum_quad_bound m
  have hMm1Pos : (0 : Int) < ((m * m - 1 : Nat) : Int) := by
    have : 4 ≤ m * m := Nat.mul_le_mul hm hm
    omega
  have hLenMap : (ys.map ofNNRat).length = m := List.length_map _
  have hHi : computeOlsSlopeNNRat ys hm ≤ₛ ofNNRat sharpBound := by
    unfold computeOlsSlopeNNRat computeOlsSlopeSigned sDivNat sMul sharpBound sLe
    dsimp only
    rw [hLenMap]
    let S := olsWeightedSumAux 0 m (ys.map ofNNRat)
    have hSLe : S.num ≤ posWeightSumAux 0 m m * (S.den : Int) := by
      unfold sLe at hSumHi
      dsimp only at hSumHi
      simpa using hSumHi
    unfold ofNNRat
    dsimp only
    simp only [Nat.one_mul]
    have hSdenPos : (0 : Int) ≤ (S.den : Int) := Int.natCast_nonneg S.den
    have hStep1 :
        (6 * S.num) * ((2 * (m * m - 1) : Nat) : Int) ≤
        (6 * (posWeightSumAux 0 m m * (S.den : Int))) * ((2 * (m * m - 1) : Nat) : Int) := by
      have h6 : 6 * S.num ≤ 6 * (posWeightSumAux 0 m m * (S.den : Int)) :=
        Int.mul_le_mul_of_nonneg_left hSLe (by omega)
      exact Int.mul_le_mul_of_nonneg_right h6 (Int.natCast_nonneg _)
    have hStep2 :
        (6 * (posWeightSumAux 0 m m * (S.den : Int))) * ((2 * (m * m - 1) : Nat) : Int) =
        (3 * (4 * posWeightSumAux 0 m m)) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
      push_cast
      have hA : 6 * (posWeightSumAux 0 m m * (S.den : Int)) * (2 * ((m * m - 1 : Nat) : Int)) =
                (6 * 2 * posWeightSumAux 0 m m) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
        calc
          6 * (posWeightSumAux 0 m m * (S.den : Int)) * (2 * ((m * m - 1 : Nat) : Int))
              = (6 * posWeightSumAux 0 m m) * ((S.den : Int) * (2 * ((m * m - 1 : Nat) : Int))) := by
                rw [← Int.mul_assoc 6 (posWeightSumAux 0 m m) (S.den : Int),
                    Int.mul_assoc (6 * posWeightSumAux 0 m m) (S.den : Int)]
          _ = (6 * posWeightSumAux 0 m m) * (2 * ((S.den : Int) * ((m * m - 1 : Nat) : Int))) := by
                rw [Int.mul_left_comm (S.den : Int) 2]
          _ = ((6 * posWeightSumAux 0 m m) * 2) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) :=
                (Int.mul_assoc (6 * posWeightSumAux 0 m m) 2 _).symm
          _ = (6 * 2 * posWeightSumAux 0 m m) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
                rw [Int.mul_right_comm 6 (posWeightSumAux 0 m m) 2]
      rw [hA]
      have h12 : 6 * 2 * posWeightSumAux 0 m m = 3 * (4 * posWeightSumAux 0 m m) := by omega
      rw [h12]
    have hStep3 :
        (3 * (4 * posWeightSumAux 0 m m)) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) ≤
        (3 * ((m : Int) * (m : Int))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
      have h3 : 3 * (4 * posWeightSumAux 0 m m) ≤ 3 * ((m : Int) * (m : Int)) :=
        Int.mul_le_mul_of_nonneg_left hPosQuad (by omega)
      exact Int.mul_le_mul_of_nonneg_right h3
        (Int.mul_nonneg hSdenPos (Int.le_of_lt hMm1Pos))
    have hStep4 :
        (3 * ((m : Int) * (m : Int))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) =
        ((3 * m : Nat) : Int) * ((S.den * (m * (m * m - 1)) : Nat) : Int) := by
      push_cast
      calc
        (3 * ((m : Int) * (m : Int))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int))
            = (3 * (m : Int)) * ((m : Int) * ((S.den : Int) * ((m * m - 1 : Nat) : Int))) := by
              rw [← Int.mul_assoc 3 (m : Int) (m : Int), Int.mul_assoc]
        _ = (3 * (m : Int)) * ((S.den : Int) * ((m : Int) * ((m * m - 1 : Nat) : Int))) := by
              rw [Int.mul_left_comm (m : Int) (S.den : Int)]
    exact Int.le_trans hStep1 (hStep2 ▸ (hStep4 ▸ hStep3))
  have hLo : sNeg (ofNNRat sharpBound) ≤ₛ computeOlsSlopeNNRat ys hm := by
    unfold computeOlsSlopeNNRat computeOlsSlopeSigned sDivNat sMul sNeg sharpBound sLe
    dsimp only
    rw [hLenMap]
    let S := olsWeightedSumAux 0 m (ys.map ofNNRat)
    have hSGe : (-negWeightSumAux 0 m m) * (S.den : Int) ≤ S.num := by
      unfold sLe at hSumLo
      dsimp only at hSumLo
      simpa using hSumLo
    unfold ofNNRat
    dsimp only
    simp only [Nat.one_mul]
    have hSdenPos : (0 : Int) ≤ (S.den : Int) := Int.natCast_nonneg S.den
    have hStep1 :
        (6 * ((-negWeightSumAux 0 m m) * (S.den : Int))) * ((2 * (m * m - 1) : Nat) : Int) ≤
        (6 * S.num) * ((2 * (m * m - 1) : Nat) : Int) := by
      have h6 : 6 * ((-negWeightSumAux 0 m m) * (S.den : Int)) ≤ 6 * S.num :=
        Int.mul_le_mul_of_nonneg_left hSGe (by omega)
      exact Int.mul_le_mul_of_nonneg_right h6 (Int.natCast_nonneg _)
    have hStep2 :
        (6 * ((-negWeightSumAux 0 m m) * (S.den : Int))) * ((2 * (m * m - 1) : Nat) : Int) =
        (-(3 * (4 * negWeightSumAux 0 m m))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
      push_cast
      have hA : 6 * ((-negWeightSumAux 0 m m) * (S.den : Int)) * (2 * ((m * m - 1 : Nat) : Int)) =
                (6 * 2 * (-negWeightSumAux 0 m m)) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
        calc
          6 * ((-negWeightSumAux 0 m m) * (S.den : Int)) * (2 * ((m * m - 1 : Nat) : Int))
              = (6 * (-negWeightSumAux 0 m m)) * ((S.den : Int) * (2 * ((m * m - 1 : Nat) : Int))) := by
                rw [← Int.mul_assoc 6 (-negWeightSumAux 0 m m) (S.den : Int),
                    Int.mul_assoc (6 * (-negWeightSumAux 0 m m)) (S.den : Int)]
          _ = (6 * (-negWeightSumAux 0 m m)) * (2 * ((S.den : Int) * ((m * m - 1 : Nat) : Int))) := by
                rw [Int.mul_left_comm (S.den : Int) 2]
          _ = ((6 * (-negWeightSumAux 0 m m)) * 2) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) :=
                (Int.mul_assoc (6 * (-negWeightSumAux 0 m m)) 2 _).symm
          _ = (6 * 2 * (-negWeightSumAux 0 m m)) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
                rw [Int.mul_right_comm 6 (-negWeightSumAux 0 m m) 2]
      rw [hA]
      have h12 : 6 * 2 * (-negWeightSumAux 0 m m) = -(3 * (4 * negWeightSumAux 0 m m)) := by omega
      rw [h12]
    have hStep3 :
        (-(3 * ((m : Int) * (m : Int)))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) ≤
        (-(3 * (4 * negWeightSumAux 0 m m))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) := by
      have h3 : -(3 * ((m : Int) * (m : Int))) ≤ -(3 * (4 * negWeightSumAux 0 m m)) := by omega
      exact Int.mul_le_mul_of_nonneg_right h3
        (Int.mul_nonneg hSdenPos (Int.le_of_lt hMm1Pos))
    have hStep4 :
        (-(3 * ((m : Int) * (m : Int)))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int)) =
        (-((3 * m : Nat) : Int)) * ((S.den * (m * (m * m - 1)) : Nat) : Int) := by
      push_cast
      rw [Int.neg_mul, Int.neg_mul]
      apply congrArg (fun x => -x)
      calc
        (3 * ((m : Int) * (m : Int))) * ((S.den : Int) * ((m * m - 1 : Nat) : Int))
            = (3 * (m : Int)) * ((m : Int) * ((S.den : Int) * ((m * m - 1 : Nat) : Int))) := by
              rw [← Int.mul_assoc 3 (m : Int) (m : Int), Int.mul_assoc]
        _ = (3 * (m : Int)) * ((S.den : Int) * ((m : Int) * ((m * m - 1 : Nat) : Int))) := by
              rw [Int.mul_left_comm (m : Int) (S.den : Int)]
    exact Int.le_trans (hStep4 ▸ hStep3) (hStep2 ▸ hStep1)
  have hOfSharpLeOne : ofNNRat sharpBound ≤ₛ sOne := by
    unfold ofNNRat sOne sLe
    rw [NNRat.le_one_iff] at hSharpLeOne
    dsimp only
    omega
  have hNegOneLeNegSharp : sNegOne ≤ₛ sNeg (ofNNRat sharpBound) := by
    have h : sNeg sOne ≤ₛ sNeg (ofNNRat sharpBound) := (sNeg_le_sNeg_iff _ _).mpr hOfSharpLeOne
    exact h
  exact ⟨hLo, hHi, hSharpLeOne, sLe_trans hNegOneLeNegSharp hLo, sLe_trans hHi hOfSharpLeOne⟩

/--
**Theorem 24 (`classifyTrendDirection_partition_and_threshold_mono`)**:
`classifyTrendDirection` exhaustively partitions slopes into `{DEGRADING, IMPROVING, STABLE}`
(never `INSUFFICIENT_DATA`), and widening the slope threshold (`t₁ ≤ t₂`) preserves `STABLE`.
-/
theorem classifyTrendDirection_partition_and_threshold_mono
    (slope : SignedRat) (t₁ t₂ : NNRat) :
    (classifyTrendDirection slope t₁ = .degrading ∨
     classifyTrendDirection slope t₁ = .improving ∨
     classifyTrendDirection slope t₁ = .stable) ∧
    classifyTrendDirection slope t₁ ≠ .insufficientData ∧
    (t₁ ≤ t₂ → classifyTrendDirection slope t₁ = .stable →
     classifyTrendDirection slope t₂ = .stable) := by
  refine ⟨?_, ?_, ?_⟩
  · unfold classifyTrendDirection
    split
    · exact Or.inl rfl
    · split
      · exact Or.inr (Or.inl rfl)
      · exact Or.inr (Or.inr rfl)
  · unfold classifyTrendDirection
    split
    · decide
    · split <;> decide
  · intro hle hStab
    unfold classifyTrendDirection at hStab ⊢
    have hNotDeg1 : ¬ (slope <ₛ sNeg (ofNNRat t₁)) := by
      intro hc
      simp [decide_eq_true hc] at hStab
    have hNotImp1 : ¬ (ofNNRat t₁ <ₛ slope) := by
      intro hc
      simp [decide_eq_false hNotDeg1, decide_eq_true hc] at hStab
    have hLeOfNN : ofNNRat t₁ ≤ₛ ofNNRat t₂ := by
      unfold ofNNRat sLe
      dsimp only
      have hNat : t₁.num * t₂.den ≤ t₂.num * t₁.den := hle
      exact_mod_cast hNat
    have hNegLe : sNeg (ofNNRat t₂) ≤ₛ sNeg (ofNNRat t₁) :=
      (sNeg_le_sNeg_iff _ _).mpr hLeOfNN
    have hGeNeg1 : sNeg (ofNNRat t₁) ≤ₛ slope := by
      by_cases h : sNeg (ofNNRat t₁) ≤ₛ slope
      · exact h
      · exact absurd ((sLt_iff_not_sLe slope (sNeg (ofNNRat t₁))).mpr h) hNotDeg1
    have hLePos1 : slope ≤ₛ ofNNRat t₁ := by
      by_cases h : slope ≤ₛ ofNNRat t₁
      · exact h
      · exact absurd ((sLt_iff_not_sLe (ofNNRat t₁) slope).mpr h) hNotImp1
    have hNotDeg2 : ¬ (slope <ₛ sNeg (ofNNRat t₂)) := fun hlt =>
      ((sLt_iff_not_sLe _ _).mp hlt) (sLe_trans hNegLe hGeNeg1)
    have hNotImp2 : ¬ (ofNNRat t₂ <ₛ slope) := fun hlt =>
      ((sLt_iff_not_sLe _ _).mp hlt) (sLe_trans hLePos1 hLeOfNN)
    simp [decide_eq_false hNotDeg2, decide_eq_false hNotImp2]

/-! ## Helper Lemmas: Provenance & Cohort Drift -/

private theorem mem_dedupPreserveFirstAux (seen xs : List String) (x : String) :
    x ∈ dedupPreserveFirstAux seen xs ↔ x ∈ xs ∧ x ∉ seen := by
  induction xs generalizing seen with
  | nil => simp [dedupPreserveFirstAux]
  | cons hd tl ih =>
    unfold dedupPreserveFirstAux
    by_cases hIn : hd ∈ seen
    · simp only [hIn, ↓reduceIte, List.mem_cons]
      rw [ih seen]
      constructor
      · intro ⟨htl, hnot⟩; exact ⟨Or.inr htl, hnot⟩
      · intro ⟨hmem, hnot⟩
        rcases hmem with rfl | htl
        · exact absurd hIn hnot
        · exact ⟨htl, hnot⟩
    · simp only [hIn, ↓reduceIte, List.mem_cons]
      rw [ih (hd :: seen)]
      constructor
      · intro h
        rcases h with rfl | ⟨htl, hnot⟩
        · exact ⟨Or.inl rfl, hIn⟩
        · simp only [List.mem_cons, not_or] at hnot
          exact ⟨Or.inr htl, hnot.2⟩
      · intro ⟨hmem, hnot⟩
        by_cases hEq : x = hd
        · exact Or.inl hEq
        · rcases hmem with rfl | htl
          · exact absurd rfl hEq
          · right
            refine ⟨htl, ?_⟩
            simp [hEq, hnot]

private theorem mem_unionSortedStrings (a b : List String) (s : String) :
    s ∈ unionSortedStrings a b ↔ s ∈ a ∨ s ∈ b := by
  unfold unionSortedStrings dedupPreserveFirst
  rw [(List.mergeSort_perm _ _).mem_iff, mem_dedupPreserveFirstAux]
  simp

private theorem caseSetsDiffer_self (ids : List String) :
    caseSetsDiffer ids ids = false := by
  unfold caseSetsDiffer
  have h : ids.any (fun cid => !decide (cid ∈ ids)) = false := by
    rw [List.any_eq_false]
    intro x hx
    simp [hx]
  simp [h]

private theorem caseSetsDiffer_symm (a b : List String) :
    caseSetsDiffer a b = caseSetsDiffer b a := by
  unfold caseSetsDiffer
  exact Bool.or_comm _ _

private theorem pairProvenanceDrift_category_symm_imp (a b : ProvenanceSnapshot) (cat : DriftCategory)
    (h : ∃ w ∈ pairProvenanceDrift a b, w.category = cat) :
    ∃ w ∈ pairProvenanceDrift b a, w.category = cat := by
  obtain ⟨w, hw, hcat⟩ := h
  unfold pairProvenanceDrift at hw ⊢
  simp only [List.mem_append] at hw
  rcases hw with ((hds | hmet) | hjudge) | hemb
  · by_cases hne : a.datasetFingerprint != b.datasetFingerprint
    · simp only [hne, ↓reduceIte, List.mem_singleton] at hds
      subst hds
      have hne' : b.datasetFingerprint != a.datasetFingerprint := by
        simp only [bne_iff_ne, ne_eq] at hne ⊢
        exact Ne.symm hne
      refine ⟨{ category := .datasetFingerprint, metricId := none,
                baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
      simp [hne']
    · simp [hne] at hds
  · rw [List.mem_filterMap] at hmet
    obtain ⟨mid, hmidMem, hmidSome⟩ := hmet
    have hmidMem' : mid ∈ unionSortedStrings
        (b.metricVersions.map Prod.fst) (a.metricVersions.map Prod.fst) := by
      rw [mem_unionSortedStrings] at hmidMem ⊢
      exact hmidMem.symm
    cases ha : lookupMetricVersion a.metricVersions mid with
    | none =>
      cases hb : lookupMetricVersion b.metricVersions mid with
      | none => simp [ha, hb] at hmidSome
      | some cVer =>
        simp only [ha, hb, Option.some.injEq] at hmidSome
        subst hmidSome
        refine ⟨{ category := .metricSet, metricId := some mid,
                  baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
        apply List.mem_append_left
        apply List.mem_append_left
        apply List.mem_append_right
        rw [List.mem_filterMap]
        exact ⟨mid, hmidMem', by simp [ha, hb]⟩
    | some bVer =>
      cases hb : lookupMetricVersion b.metricVersions mid with
      | none =>
        simp only [ha, hb, Option.some.injEq] at hmidSome
        subst hmidSome
        refine ⟨{ category := .metricSet, metricId := some mid,
                  baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
        apply List.mem_append_left
        apply List.mem_append_left
        apply List.mem_append_right
        rw [List.mem_filterMap]
        exact ⟨mid, hmidMem', by simp [ha, hb]⟩
      | some cVer =>
        by_cases hne : bVer != cVer
        · simp only [ha, hb, hne, ↓reduceIte, Option.some.injEq] at hmidSome
          subst hmidSome
          have hne' : cVer != bVer := by
            simp only [bne_iff_ne, ne_eq] at hne ⊢
            exact Ne.symm hne
          refine ⟨{ category := .metricVersion, metricId := some mid,
                    baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
          apply List.mem_append_left
          apply List.mem_append_left
          apply List.mem_append_right
          rw [List.mem_filterMap]
          exact ⟨mid, hmidMem', by simp [ha, hb, hne']⟩
        · simp [ha, hb, hne] at hmidSome
  · by_cases hne : a.judgeConfigFingerprint != b.judgeConfigFingerprint
    · simp only [hne, ↓reduceIte, List.mem_singleton] at hjudge
      subst hjudge
      have hne' : b.judgeConfigFingerprint != a.judgeConfigFingerprint := by
        simp only [bne_iff_ne, ne_eq] at hne ⊢
        exact Ne.symm hne
      refine ⟨{ category := .judgeConfig, metricId := none,
                baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
      simp [hne']
    · simp [hne] at hjudge
  · by_cases hne : a.embeddingConfigFingerprint != b.embeddingConfigFingerprint
    · simp only [hne, ↓reduceIte, List.mem_singleton] at hemb
      subst hemb
      have hne' : b.embeddingConfigFingerprint != a.embeddingConfigFingerprint := by
        simp only [bne_iff_ne, ne_eq] at hne ⊢
        exact Ne.symm hne
      refine ⟨{ category := .embeddingConfig, metricId := none,
                baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
      simp [hne']
    · simp [hne] at hemb

private theorem detectDrift_category_symm_imp (a b : ProvenanceSnapshot) (cat : DriftCategory)
    (h : ∃ w ∈ detectDrift a b, w.category = cat) :
    ∃ w ∈ detectDrift b a, w.category = cat := by
  obtain ⟨w, hw, hcat⟩ := h
  unfold detectDrift at hw ⊢
  simp only [List.mem_append] at hw
  rcases hw with (hbase | hcap) | hcase
  · obtain ⟨w', hw', hcat'⟩ := pairProvenanceDrift_category_symm_imp a b cat ⟨w, hbase, hcat⟩
    exact ⟨w', List.mem_append_left _ (List.mem_append_left _ hw'), hcat'⟩
  · by_cases hc : a.datasetCapped || b.datasetCapped
    · simp only [hc, ↓reduceIte, List.mem_singleton] at hcap
      subst hcap
      have hc' : b.datasetCapped || a.datasetCapped := by rw [Bool.or_comm]; exact hc
      refine ⟨{ category := .datasetCapped, metricId := none,
                baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
      simp [hc']
    · simp [hc] at hcap
  · by_cases hcs : caseSetsDiffer a.caseIds b.caseIds
    · simp only [hcs, ↓reduceIte, List.mem_singleton] at hcase
      subst hcase
      have hcs' : caseSetsDiffer b.caseIds a.caseIds := by rw [caseSetsDiffer_symm]; exact hcs
      refine ⟨{ category := .caseSetMismatch, metricId := none,
                baselineRunId := some b.runId, candidateRunId := some a.runId }, ?_, hcat⟩
      simp [hcs']
    · simp [hcs] at hcase

private theorem pairProvenanceDrift_eq_nil_of_same_fields {a b : ProvenanceSnapshot}
    (hds : a.datasetFingerprint = b.datasetFingerprint)
    (hmv : a.metricVersions = b.metricVersions)
    (hjc : a.judgeConfigFingerprint = b.judgeConfigFingerprint)
    (hec : a.embeddingConfigFingerprint = b.embeddingConfigFingerprint) :
    pairProvenanceDrift a b = [] := by
  unfold pairProvenanceDrift
  rw [hds, hmv, hjc, hec]
  simp only [bne_self_eq_false, Bool.false_eq_true, ↓reduceIte, List.nil_append, List.append_nil]
  apply List.eq_nil_iff_forall_not_mem.mpr
  intro w hw
  rw [List.mem_filterMap] at hw
  obtain ⟨mid, _, hsome⟩ := hw
  cases hlk : lookupMetricVersion b.metricVersions mid with
  | none => simp [hlk] at hsome
  | some v => simp [hlk] at hsome

private theorem mem_dedupDriftWarningsAux_not_seen (seen : List DriftKey)
    (ws : List DriftWarningSpec) {w : DriftWarningSpec}
    (hw : w ∈ dedupDriftWarningsAux seen ws) : w.key ∉ seen := by
  induction ws generalizing seen with
  | nil => simp [dedupDriftWarningsAux] at hw
  | cons hd tl ih =>
    unfold dedupDriftWarningsAux at hw
    by_cases hIn : hd.key ∈ seen
    · simp only [hIn, ↓reduceIte] at hw
      exact ih seen hw
    · simp only [hIn, ↓reduceIte, List.mem_cons] at hw
      rcases hw with rfl | htl
      · exact hIn
      · have hNot := ih (hd.key :: seen) htl
        simp only [List.mem_cons, not_or] at hNot
        exact hNot.2

private theorem dedupDriftWarningsAux_keys_nodup (seen : List DriftKey)
    (ws : List DriftWarningSpec) :
    ((dedupDriftWarningsAux seen ws).map DriftWarningSpec.key).Nodup := by
  induction ws generalizing seen with
  | nil => simp [dedupDriftWarningsAux]
  | cons hd tl ih =>
    unfold dedupDriftWarningsAux
    by_cases hIn : hd.key ∈ seen
    · simp only [hIn, ↓reduceIte]
      exact ih seen
    · simp only [hIn, ↓reduceIte, List.map_cons, List.nodup_cons]
      refine ⟨?_, ih (hd.key :: seen)⟩
      intro hMem
      rw [List.mem_map] at hMem
      obtain ⟨w, hwMem, hwKey⟩ := hMem
      have hNot := mem_dedupDriftWarningsAux_not_seen (hd.key :: seen) tl hwMem
      rw [hwKey] at hNot
      exact hNot (List.mem_cons_self ..)

/-! ## Group 4 — Provenance & Cohort Drift Soundness (`8` Theorems) -/

/--
**Theorem 25 (`pairProvenanceDrift_irrefl`)**:
Comparing any provenance snapshot against itself produces zero pairwise provenance drift warnings.
-/
theorem pairProvenanceDrift_irrefl (p : ProvenanceSnapshot) :
    pairProvenanceDrift p p = [] :=
  pairProvenanceDrift_eq_nil_of_same_fields rfl rfl rfl rfl

/--
**Theorem 26 (`detectDrift_refl_uncapped`)**:
Comparing any uncapped provenance snapshot against itself produces zero `detectDrift` warnings.
-/
theorem detectDrift_refl_uncapped (p : ProvenanceSnapshot) (huncapped : p.datasetCapped = false) :
    detectDrift p p = [] := by
  unfold detectDrift
  rw [pairProvenanceDrift_irrefl, huncapped, caseSetsDiffer_self]
  simp

/--
**Theorem 27 (`detectDrift_category_symm`)**:
Swapping baseline and candidate snapshots preserves the exact set of emitted `DriftCategory` values.
-/
theorem detectDrift_category_symm (a b : ProvenanceSnapshot) (cat : DriftCategory) :
    (∃ w ∈ detectDrift a b, w.category = cat) ↔
    (∃ w ∈ detectDrift b a, w.category = cat) :=
  ⟨detectDrift_category_symm_imp a b cat, detectDrift_category_symm_imp b a cat⟩

/--
**Theorem 28 (`detectDrift_target_change_isolated`)**:
Changing ONLY intentional system-under-test target fields (`runId`, `systemVersion`, `modelId`,
`configFingerprint`) on an uncapped baseline produces zero drift warnings.
-/
theorem detectDrift_target_change_isolated
    (base : ProvenanceSnapshot)
    (newRunId : String)
    (newSysVer newModelId newCfgFp : Option String)
    (huncapped : base.datasetCapped = false) :
    let cand : ProvenanceSnapshot := {
      base with
      runId := newRunId
      systemVersion := newSysVer
      modelId := newModelId
      configFingerprint := newCfgFp
    }
    detectDrift base cand = [] := by
  dsimp only
  unfold detectDrift
  have hPair : pairProvenanceDrift base {
      base with
      runId := newRunId
      systemVersion := newSysVer
      modelId := newModelId
      configFingerprint := newCfgFp
    } = [] := pairProvenanceDrift_eq_nil_of_same_fields rfl rfl rfl rfl
  rw [hPair, huncapped, caseSetsDiffer_self]
  simp

/--
**Theorem 29 (`detectWindowDrift_identical_uncapped_empty`)**:
A window of uncapped runs whose measurement provenance matches a common template `p` (even with
distinct `runId`s and changing target attributes) produces zero window drift warnings.
-/
theorem detectWindowDrift_identical_uncapped_empty
    (runs : List ProvenanceSnapshot)
    (p : ProvenanceSnapshot)
    (huncapped : p.datasetCapped = false)
    (hall : ∀ r ∈ runs,
      r.datasetFingerprint = p.datasetFingerprint ∧
      r.metricVersions = p.metricVersions ∧
      r.judgeConfigFingerprint = p.judgeConfigFingerprint ∧
      r.embeddingConfigFingerprint = p.embeddingConfigFingerprint ∧
      r.datasetCapped = false) :
    detectWindowDrift runs = [] := by
  have hAdj : ∀ rs : List ProvenanceSnapshot,
      (∀ r ∈ rs,
        r.datasetFingerprint = p.datasetFingerprint ∧
        r.metricVersions = p.metricVersions ∧
        r.judgeConfigFingerprint = p.judgeConfigFingerprint ∧
        r.embeddingConfigFingerprint = p.embeddingConfigFingerprint ∧
        r.datasetCapped = false) →
      adjacentPairDrift rs = [] := by
    intro rs hrs
    induction rs with
    | nil => rfl
    | cons a tl ih =>
      cases tl with
      | nil => rfl
      | cons b rest =>
        unfold adjacentPairDrift
        have ha := hrs a (List.mem_cons_self ..)
        have hb := hrs b (List.mem_cons_of_mem a (List.mem_cons_self ..))
        have hPair : pairProvenanceDrift a b = [] :=
          pairProvenanceDrift_eq_nil_of_same_fields
            (ha.1.trans hb.1.symm)
            (ha.2.1.trans hb.2.1.symm)
            (ha.2.2.1.trans hb.2.2.1.symm)
            (ha.2.2.2.1.trans hb.2.2.2.1.symm)
        have hRest := ih (fun r hr => hrs r (List.mem_cons_of_mem a hr))
        rw [hPair, hRest]
        rfl
  have hCap : (runs.filterMap fun r =>
      if r.datasetCapped then
        some ({
          category := .datasetCapped
          metricId := none
          baselineRunId := none
          candidateRunId := some r.runId
        } : DriftWarningSpec)
      else none) = [] := by
    apply List.eq_nil_iff_forall_not_mem.mpr
    intro w hw
    rw [List.mem_filterMap] at hw
    obtain ⟨r, hrMem, hrSome⟩ := hw
    have hc := (hall r hrMem).2.2.2.2
    simp [hc] at hrSome
  unfold detectWindowDrift
  have _ := huncapped
  rw [hAdj runs hall, hCap]
  rfl

/--
**Theorem 30 (`detectWindowDrift_adjacent_sound`)**:
Every pairwise provenance drift warning between adjacent runs `(runs[i], runs[i + 1])` is
preserved in `detectWindowDrift runs`.
-/
theorem detectWindowDrift_adjacent_sound
    (runs : List ProvenanceSnapshot)
    (i : Nat)
    (hi : i + 1 < runs.length)
    (w : DriftWarningSpec)
    (hw : w ∈ pairProvenanceDrift runs[i] runs[i + 1]) :
    w ∈ detectWindowDrift runs := by
  have hAdj : ∀ (rs : List ProvenanceSnapshot) (idx : Nat) (hidx : idx + 1 < rs.length),
      w ∈ pairProvenanceDrift rs[idx] rs[idx + 1] → w ∈ adjacentPairDrift rs := by
    intro rs
    induction rs with
    | nil =>
      intro idx hidx _
      simp at hidx
    | cons a tl ih =>
      intro idx hidx hmem
      cases tl with
      | nil =>
        simp at hidx
      | cons b rest =>
        unfold adjacentPairDrift
        cases idx with
        | zero =>
          exact List.mem_append_left _ hmem
        | succ k =>
          apply List.mem_append_right
          exact ih k (by simp only [List.length_cons] at hidx ⊢; omega) hmem
  unfold detectWindowDrift
  exact List.mem_append_left _ (hAdj runs i hi hw)

/--
**Theorem 31 (`detectCohortDrift_empty_guard`)**:
If either cohort side (`baselineRuns` or `candidateRuns`) is empty, `detectCohortDrift` returns `[]`.
-/
theorem detectCohortDrift_empty_guard
    (baselineRuns candidateRuns : List ProvenanceSnapshot)
    (h : baselineRuns = [] ∨ candidateRuns = []) :
    detectCohortDrift baselineRuns candidateRuns = [] := by
  rcases h with rfl | rfl
  · rfl
  · cases baselineRuns <;> rfl

/--
**Theorem 32 (`detectCohortDrift_keys_nodup`)**:
Every warning emitted by `detectCohortDrift` has a strictly unique 4-tuple deduplication key
`(category, metricId, baselineRunId, candidateRunId)` (`Nodup`).
-/
theorem detectCohortDrift_keys_nodup
    (baselineRuns candidateRuns : List ProvenanceSnapshot) :
    ((detectCohortDrift baselineRuns candidateRuns).map DriftWarningSpec.key).Nodup := by
  unfold detectCohortDrift
  cases baselineRuns with
  | nil => simp
  | cons b0 bRest =>
    cases candidateRuns with
    | nil => simp
    | cons c0 cRest =>
      exact dedupDriftWarningsAux_keys_nodup [] _

end EvalForgeFormal.Regression
