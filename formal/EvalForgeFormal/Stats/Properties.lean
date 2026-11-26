import EvalForgeFormal.Stats.Inference
import EvalForgeFormal.QualityGate.Properties

namespace EvalForgeFormal.Stats

open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration
open EvalForgeFormal.QualityGate

/-!
# Machine-Checked Statistical Inference Properties (`36` Audited Theorems)

All 36 mandatory theorems below are compile-time audited by `formal/EvalForgeAudit.lean`
under `{propext, Classical.choice, Quot.sound}` only (zero `sorry`, zero Mathlib, zero `Lean.*`).
-/

/-- Exact rational equivalence lifted to `Option NNRat`. -/
def optNNRatEquiv : Option NNRat → Option NNRat → Prop
  | none, none => True
  | some a, some b => a ≈ b
  | _, _ => False

/-- Exact rational equivalence lifted to `Option SignedRat`. -/
def optSignedRatEquiv : Option SignedRat → Option SignedRat → Prop
  | none, none => True
  | some a, some b => a ≈ₛ b
  | _, _ => False

/-! ## Group 1 — Exact Sample Algebra & Paired Linearity (6 Theorems) -/

/-- 1. Paired mean delta equals the exact difference of candidate and baseline means. -/
theorem signedMeanList_pairedDiffs_linear (base cand : List NNRat)
    (hlen : base.length = cand.length)
    (hpos : 0 < base.length)
    (hdp : 0 < (pairedDiffs base cand).length)
    (hcp : 0 < cand.length) :
    sMeanList (pairedDiffs base cand) hdp ≈ₛ
    SignedRat.subNNRat (nnMeanList cand hcp) (nnMeanList base hpos) :=
  sMeanList_pairedDiffs_eq_sub_means base cand hlen hpos hdp hcp

/-- 2. Unit-bounded `[0, 1]` baseline and candidate pairs yield `mean_delta ∈ [-1, 1]`. -/
theorem signedMeanList_pairedDiffs_unit (base cand : List NNRat)
    (hlen : base.length = cand.length)
    (hpos : 0 < base.length)
    (hdp : 0 < (pairedDiffs base cand).length)
    (hcp : 0 < cand.length)
    (hBaseUnit : ∀ b ∈ base, b ≤ NNRat.one)
    (hCandUnit : ∀ c ∈ cand, c ≤ NNRat.one) :
    (sMeanList (pairedDiffs base cand) hdp).inUnitInterval := by
  have hlin := signedMeanList_pairedDiffs_linear base cand hlen hpos hdp hcp
  have hbMean : nnMeanList base hpos ≤ NNRat.one := nnMeanList_le_one base hpos hBaseUnit
  have hcMean : nnMeanList cand hcp ≤ NNRat.one := nnMeanList_le_one cand hcp hCandUnit
  have hSubUnit := SignedRat.subNNRat_inUnitInterval hcMean hbMean
  exact SignedRat.inUnitInterval_of_equiv hlin.symm hSubUnit

/-- 3. Unbiased sample variance is universally non-negative. -/
theorem sampleVarNNRat_nonneg (xs : List NNRat) (h : 2 ≤ xs.length) :
    NNRat.zero ≤ sampleVarNNRat xs h :=
  NNRat.zero_le _

/-- 4. Sample variance vanishes iff every observation equals the sample mean. -/
theorem sampleVarNNRat_zero_iff_all_eq_mean (xs : List NNRat) (h : 2 ≤ xs.length) :
    sampleVarNNRat xs h ≈ NNRat.zero ↔ ∀ x ∈ xs, x ≈ nnMeanList xs (by omega) :=
  sampleVarNNRat_eq_zero_iff xs h

/-- 5. Negating every signed difference preserves unbiased sample variance. -/
theorem sampleVarSigned_neg_invariant (xs : List SignedRat) (h : 2 ≤ xs.length)
    (h' : 2 ≤ (xs.map sNeg).length) :
    sampleVarSigned (xs.map sNeg) h' ≈ sampleVarSigned xs h :=
  sampleVarSigned_neg xs h h'

/-- 6. Unbiased sample variance is invariant under arbitrary input permutations. -/
theorem sampleVarNNRat_perm_invariant {xs ys : List NNRat} (hp : List.Perm xs ys)
    (hx : 2 ≤ xs.length) (hy : 2 ≤ ys.length) :
    sampleVarNNRat xs hx ≈ sampleVarNNRat ys hy :=
  sampleVarNNRat_perm hp hx hy

/-! ## Group 2 — Welch–Satterthwaite Degrees of Freedom (5 Theorems) -/

/-- 7. Welch–Satterthwaite degrees of freedom are strictly positive for all `k, m ≥ 2`. -/
theorem welchSatterthwaiteDf_pos (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    NNRat.zero < welchSatterthwaiteDf vB vC k m hk hm :=
  welchSatterthwaiteDf_pos_core vB vC k m hk hm

/-- 8. Welch–Satterthwaite `df` is universally bounded below by `min(k - 1, m - 1)`. -/
theorem welchSatterthwaiteDf_lower_bound (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    NNRat.ofNat (min (k - 1) (m - 1)) ≤ welchSatterthwaiteDf vB vC k m hk hm :=
  welchSatterthwaiteDf_lower_bound_core vB vC k m hk hm

/-- 9. Welch–Satterthwaite `df` is universally bounded above by `k + m - 2`. -/
theorem welchSatterthwaiteDf_upper_bound (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf vB vC k m hk hm ≤ NNRat.ofNat (k + m - 2) :=
  welchSatterthwaiteDf_upper_bound_core vB vC k m hk hm

/-- 10. Positive rescaling of `(vB, vC)` leaves Welch–Satterthwaite `df` invariant. -/
theorem welchSatterthwaiteDf_scale_invariant (s vB vC : NNRat) (hs : 0 < s.num)
    (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf (s.mul vB) (s.mul vC) k m hk hm ≈
    welchSatterthwaiteDf vB vC k m hk hm :=
  welchSatterthwaiteDf_scale_invariant_core s vB vC hs k m hk hm

/-- 11. Swapping baseline and candidate variance terms preserves Welch–Satterthwaite `df`. -/
theorem welchSatterthwaiteDf_symm (vB vC : NNRat) (k m : Nat) (hk : 2 ≤ k) (hm : 2 ≤ m) :
    welchSatterthwaiteDf vB vC k m hk hm ≈ welchSatterthwaiteDf vC vB m k hm hk :=
  welchSatterthwaiteDf_symm_core vB vC k m hk hm

/-! ## Group 3 — Finalization Classification, Guards & Trichotomy (8 Theorems) -/

/-- 12. `statisticallySignificant` holds iff significance is improvement or regression. -/
theorem finalizeInference_statisticallySignificant_iff (oracle : TwoTailedOracle)
    (inp : InferenceInput) :
    (finalizeInferenceWith oracle inp).statisticallySignificant = true ↔
    (finalizeInferenceWith oracle inp).significance = .significantImprovement ∨
    (finalizeInferenceWith oracle inp).significance = .significantRegression := by
  unfold finalizeInferenceWith finalizeInferenceDirect
  cases hmd : inp.meanDelta <;> cases hse : inp.seSq <;> cases hdf : inp.df <;>
    cases he : inp.hasEnoughSamples
  all_goals dsimp only
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · simp
  · rename_i d s f
    by_cases hs0 : s.num = 0
    · simp only [hs0, ↓reduceIte]
      by_cases hd0 : d.num = 0
      · simp [hd0]
      · by_cases hdPos : 0 < d.num <;> simp [hd0, hdPos]
    · simp only [hs0, ↓reduceIte]
      by_cases hsig : oracle.pValue d s f < alphaOf inp.confidenceLevel
      · by_cases hdPos : 0 < d.num <;> simp [hsig, hdPos]
      · simp [hsig]

/-- 13. Insufficient-data guard dominates all inference outputs and disables statistical fields. -/
theorem finalizeInference_insufficientData_guard (oracle : TwoTailedOracle) (inp : InferenceInput)
    (h : inp.hasEnoughSamples = false ∨ inp.meanDelta = none ∨ inp.seSq = none ∨ inp.df = none) :
    let out := finalizeInferenceWith oracle inp
    out.significance = .insufficientData ∧
    out.statisticallySignificant = false ∧
    out.seSq = none ∧
    out.ciLow = none ∧
    out.ciHigh = none ∧
    out.pValue = none ∧
    out.df = none ∧
    out.effectSize.defined = false := by
  unfold finalizeInferenceWith finalizeInferenceDirect emptyEffectSize
  rcases h with he | hmd | hse | hdf
  · cases inp.meanDelta <;> cases inp.seSq <;> cases inp.df <;> simp [he]
  · simp [hmd]
  · cases inp.meanDelta <;> simp [hse]
  · cases inp.meanDelta <;> cases inp.seSq <;> simp [hdf]

/-- 14. `INSUFFICIENT_DATA` characterizes the exact guard disjunction. -/
theorem finalizeInference_insufficientData_iff (oracle : TwoTailedOracle) (inp : InferenceInput) :
    (finalizeInferenceWith oracle inp).significance = .insufficientData ↔
    inp.hasEnoughSamples = false ∨ inp.meanDelta = none ∨ inp.seSq = none ∨ inp.df = none := by
  constructor
  · intro hsig
    by_cases hguard : inp.hasEnoughSamples = false ∨ inp.meanDelta = none ∨ inp.seSq = none ∨ inp.df = none
    · exact hguard
    · exfalso
      cases he : inp.hasEnoughSamples with
      | false => exact hguard (Or.inl he)
      | true =>
        cases hmd : inp.meanDelta with
        | none => exact hguard (Or.inr (Or.inl hmd))
        | some d =>
          cases hse : inp.seSq with
          | none => exact hguard (Or.inr (Or.inr (Or.inl hse)))
          | some s =>
            cases hdf : inp.df with
            | none => exact hguard (Or.inr (Or.inr (Or.inr hdf)))
            | some f =>
              unfold finalizeInferenceWith finalizeInferenceDirect at hsig
              simp only [he, hmd, hse, hdf] at hsig
              by_cases hs0 : s.num = 0
              · simp only [hs0, ↓reduceIte] at hsig
                by_cases hd0 : d.num = 0
                · simp [hd0] at hsig
                · by_cases hdPos : 0 < d.num <;> simp [hd0, hdPos] at hsig
              · simp only [hs0, ↓reduceIte] at hsig
                by_cases hp : oracle.pValue d s f < alphaOf inp.confidenceLevel
                · by_cases hdPos : 0 < d.num <;> simp [hp, hdPos] at hsig
                · simp [hp] at hsig
  · intro h
    exact (finalizeInference_insufficientData_guard oracle inp h).1

/-- 15. Zero-variance trichotomy case 1: zero delta yields `p = 1`, `NOT_SIGNIFICANT`, and `CI = [0, 0]`. -/
theorem finalizeInference_zeroVar_zeroDelta (oracle : TwoTailedOracle) (inp : InferenceInput)
    (d : SignedRat) (s f : NNRat)
    (he : inp.hasEnoughSamples = true) (hmd : inp.meanDelta = some d)
    (hse : inp.seSq = some s) (hdf : inp.df = some f)
    (hs0 : s ≈ NNRat.zero) (hd0 : d ≈ₛ SignedRat.zero) :
    let out := finalizeInferenceWith oracle inp
    out.pValue = some NNRat.one ∧
    out.significance = .notSignificant ∧
    out.statisticallySignificant = false ∧
    out.ciLow = some (sClampUnit d) ∧
    out.ciHigh = some (sClampUnit d) ∧
    sClampUnit d ≈ₛ SignedRat.zero := by
  have hsNum : s.num = 0 := (NNRat.equiv_zero_iff s).mp hs0
  have hdNum : d.num = 0 := (sEquiv_zero_iff d).mp hd0
  have hclampZero : sClampUnit d ≈ₛ SignedRat.zero := by
    have hunit : d.inUnitInterval := by unfold SignedRat.inUnitInterval; omega
    rw [sClampUnit_of_inUnit hunit]
    exact hd0
  unfold finalizeInferenceWith finalizeInferenceDirect
  simp [he, hmd, hse, hdf, hsNum, hdNum, hclampZero]

/-- 16. Zero-variance trichotomy case 2: positive constant shift yields `p = 0` and `SIGNIFICANT_IMPROVEMENT`. -/
theorem finalizeInference_zeroVar_posDelta (oracle : TwoTailedOracle) (inp : InferenceInput)
    (d : SignedRat) (s f : NNRat)
    (he : inp.hasEnoughSamples = true) (hmd : inp.meanDelta = some d)
    (hse : inp.seSq = some s) (hdf : inp.df = some f)
    (hs0 : s ≈ NNRat.zero) (hdPos : 0 < d.num) :
    let out := finalizeInferenceWith oracle inp
    out.pValue = some NNRat.zero ∧
    out.significance = .significantImprovement ∧
    out.statisticallySignificant = true ∧
    out.ciLow = some (sClampUnit d) ∧
    out.ciHigh = some (sClampUnit d) := by
  have hsNum : s.num = 0 := (NNRat.equiv_zero_iff s).mp hs0
  have hdNe : d.num ≠ 0 := by omega
  unfold finalizeInferenceWith finalizeInferenceDirect
  simp [he, hmd, hse, hdf, hsNum, hdNe, hdPos]

/-- 17. Zero-variance trichotomy case 3: negative constant shift yields `p = 0` and `SIGNIFICANT_REGRESSION`. -/
theorem finalizeInference_zeroVar_negDelta (oracle : TwoTailedOracle) (inp : InferenceInput)
    (d : SignedRat) (s f : NNRat)
    (he : inp.hasEnoughSamples = true) (hmd : inp.meanDelta = some d)
    (hse : inp.seSq = some s) (hdf : inp.df = some f)
    (hs0 : s ≈ NNRat.zero) (hdNeg : d.num < 0) :
    let out := finalizeInferenceWith oracle inp
    out.pValue = some NNRat.zero ∧
    out.significance = .significantRegression ∧
    out.statisticallySignificant = true ∧
    out.ciLow = some (sClampUnit d) ∧
    out.ciHigh = some (sClampUnit d) := by
  have hsNum : s.num = 0 := (NNRat.equiv_zero_iff s).mp hs0
  have hdNe : d.num ≠ 0 := by omega
  have hdNotPos : ¬ (0 < d.num) := by omega
  unfold finalizeInferenceWith finalizeInferenceDirect
  simp [he, hmd, hse, hdf, hsNum, hdNe, hdNotPos]

/-- 18. Positive-variance zero delta can never be classified as significant when `0 < confidence_level`. -/
theorem finalizeInference_posVar_zeroDelta_notSignificant (oracle : TwoTailedOracle)
    (inp : InferenceInput) (d : SignedRat) (s f : NNRat)
    (he : inp.hasEnoughSamples = true) (hcPos : NNRat.zero < inp.confidenceLevel)
    (hmd : inp.meanDelta = some d) (hse : inp.seSq = some s) (hdf : inp.df = some f)
    (hsPos : 0 < s.num) (hd0 : d ≈ₛ SignedRat.zero) :
    let out := finalizeInferenceWith oracle inp
    out.significance = .notSignificant ∧ out.statisticallySignificant = false := by
  have hsNe : s.num ≠ 0 := by omega
  have hpOne : oracle.pValue d s f ≈ NNRat.one := oracle.pValue_zero_delta d s f hd0
  have hAlphaLt : alphaOf inp.confidenceLevel < NNRat.one := alphaOf_lt_one hcPos
  have hAlphaLtP : alphaOf inp.confidenceLevel < oracle.pValue d s f :=
    nnrat_lt_of_equiv_right hpOne.symm hAlphaLt
  have hNotLt : ¬ (oracle.pValue d s f < alphaOf inp.confidenceLevel) := by
    rw [NNRat.lt_iff_not_le]
    intro hcontra
    exact hcontra (NNRat.le_of_lt hAlphaLtP)
  unfold finalizeInferenceWith finalizeInferenceDirect
  simp [he, hmd, hse, hdf, hsNe, hNotLt]

/-- 19. Positive-variance classification biconditionals under valid `confidence_level ∈ (0, 1)`. -/
theorem finalizeInference_posVar_classification_sound (oracle : TwoTailedOracle)
    (inp : InferenceInput) (d : SignedRat) (s f : NNRat)
    (he : inp.hasEnoughSamples = true) (hcPos : NNRat.zero < inp.confidenceLevel)
    (hmd : inp.meanDelta = some d) (hse : inp.seSq = some s) (hdf : inp.df = some f)
    (hsPos : 0 < s.num) :
    let out := finalizeInferenceWith oracle inp
    (out.significance = .significantImprovement ↔
      oracle.pValue d s f < alphaOf inp.confidenceLevel ∧ 0 < d.num) ∧
    (out.significance = .significantRegression ↔
      oracle.pValue d s f < alphaOf inp.confidenceLevel ∧ d.num < 0) ∧
    (out.significance = .notSignificant ↔
      alphaOf inp.confidenceLevel ≤ oracle.pValue d s f) := by
  have hsNe : s.num ≠ 0 := by omega
  have hzeroNotLt : d.num = 0 → ¬ (oracle.pValue d s f < alphaOf inp.confidenceLevel) := by
    intro hd0
    have hpOne : oracle.pValue d s f ≈ NNRat.one :=
      oracle.pValue_zero_delta d s f ((sEquiv_zero_iff d).mpr hd0)
    have hAlphaLtP : alphaOf inp.confidenceLevel < oracle.pValue d s f :=
      nnrat_lt_of_equiv_right hpOne.symm (alphaOf_lt_one hcPos)
    rw [NNRat.lt_iff_not_le]
    intro hle
    exact hle (NNRat.le_of_lt hAlphaLtP)
  dsimp only
  unfold finalizeInferenceWith finalizeInferenceDirect
  simp only [he, hmd, hse, hdf, hsNe, ↓reduceIte]
  by_cases hp : oracle.pValue d s f < alphaOf inp.confidenceLevel
  · have hnotLe : ¬ (alphaOf inp.confidenceLevel ≤ oracle.pValue d s f) :=
      (NNRat.lt_iff_not_le _ _).mp hp
    have hdNe0 : d.num ≠ 0 := fun hd0 => hzeroNotLt hd0 hp
    by_cases hdPos : 0 < d.num
    · have hdNotNeg : ¬ (d.num < 0) := by omega
      simp [hp, hdPos, hdNotNeg, hnotLe]
    · have hdNeg : d.num < 0 := by omega
      simp [hp, hdPos, hdNeg, hnotLe]
  · have hle : alphaOf inp.confidenceLevel ≤ oracle.pValue d s f :=
      Classical.byContradiction fun hnot =>
        hp ((NNRat.lt_iff_not_le (oracle.pValue d s f) (alphaOf inp.confidenceLevel)).mpr hnot)
    simp [hp, hle]

/-! ## Group 4 — CI Clamping/Ordering & Effect-Size Invariants (5 Theorems) -/

/-- 20. Every emitted CI satisfies `-1 ≤ ci_low ≤ clamped_mean_delta ≤ ci_high ≤ 1`. -/
theorem finalizeInference_ci_bounds_and_order (oracle : TwoTailedOracle) (inp : InferenceInput)
    (lo hi md : SignedRat)
    (hlo : (finalizeInferenceWith oracle inp).ciLow = some lo)
    (hhi : (finalizeInferenceWith oracle inp).ciHigh = some hi)
    (hmd : (finalizeInferenceWith oracle inp).meanDelta = some md) :
    sNegOne ≤ₛ lo ∧ lo ≤ₛ md ∧ md ≤ₛ hi ∧ hi ≤ₛ sOne := by
  unfold finalizeInferenceWith finalizeInferenceDirect at hlo hhi hmd
  cases he : inp.hasEnoughSamples <;> cases hdm : inp.meanDelta <;>
    cases hse : inp.seSq <;> cases hdf : inp.df
  all_goals simp only [he, hdm, hse, hdf] at hlo hhi hmd
  any_goals cases hlo
  rename_i d s f
  by_cases hs0 : s.num = 0
  · simp only [hs0, ↓reduceIte] at hlo hhi hmd
    by_cases hd0 : d.num = 0
    · simp only [hd0, ↓reduceIte, Option.some.injEq] at hlo hhi hmd
      subst hlo; subst hhi; subst hmd
      have hb := sClampUnit_bounds d
      exact ⟨hb.1, sLe_refl _, sLe_refl _, hb.2⟩
    · by_cases hdPos : 0 < d.num
      · simp only [hd0, hdPos, ↓reduceIte, Option.some.injEq] at hlo hhi hmd
        subst hlo; subst hhi; subst hmd
        have hb := sClampUnit_bounds d
        exact ⟨hb.1, sLe_refl _, sLe_refl _, hb.2⟩
      · simp only [hd0, hdPos, ↓reduceIte, Option.some.injEq] at hlo hhi hmd
        subst hlo; subst hhi; subst hmd
        have hb := sClampUnit_bounds d
        exact ⟨hb.1, sLe_refl _, sLe_refl _, hb.2⟩
  · simp only [hs0, ↓reduceIte, Option.some.injEq] at hlo hhi hmd
    subst hlo; subst hhi; subst hmd
    let m := oracle.margin s f inp.confidenceLevel
    have hloB := sClampUnit_bounds (sSub d (ofNNRat m))
    have hhiB := sClampUnit_bounds (sAdd d (ofNNRat m))
    have hloLe : sClampUnit (sSub d (ofNNRat m)) ≤ₛ sClampUnit d :=
      sClampUnit_mono (sSub_ofNNRat_le_self d m)
    have hhiGe : sClampUnit d ≤ₛ sClampUnit (sAdd d (ofNNRat m)) :=
      sClampUnit_mono (self_le_sAdd_ofNNRat d m)
    exact ⟨hloB.1, hloLe, hhiGe, hhiB.2⟩

/-- 21. Every emitted p-value lies in `[0, 1]`. -/
theorem finalizeInference_pValue_unit_bounds (oracle : TwoTailedOracle) (inp : InferenceInput)
    (p : NNRat) (hp : (finalizeInferenceWith oracle inp).pValue = some p) :
    NNRat.zero ≤ p ∧ p ≤ NNRat.one := by
  unfold finalizeInferenceWith finalizeInferenceDirect at hp
  cases he : inp.hasEnoughSamples <;> cases hdm : inp.meanDelta <;>
    cases hse : inp.seSq <;> cases hdf : inp.df
  all_goals simp only [he, hdm, hse, hdf] at hp
  any_goals cases hp
  rename_i d s f
  by_cases hs0 : s.num = 0
  · simp only [hs0, ↓reduceIte] at hp
    by_cases hd0 : d.num = 0
    · simp only [hd0, ↓reduceIte, Option.some.injEq] at hp
      subst hp
      exact ⟨NNRat.zero_le _, NNRat.le_refl _⟩
    · by_cases hdPos : 0 < d.num <;> simp only [hd0, hdPos, ↓reduceIte, Option.some.injEq] at hp <;>
      · subst hp
        exact ⟨NNRat.zero_le _, NNRat.zero_le _⟩
  · simp only [hs0, ↓reduceIte, Option.some.injEq] at hp
    subst hp
    exact ⟨NNRat.zero_le _, oracle.pValue_le_one d s f⟩

/-- 22. Standardized effect size is defined iff `mean_delta` is present and dispersion variance `> 0`. -/
theorem computeEffectSize_defined_iff (md : Option SignedRat) (dv : Option NNRat) :
    (computeEffectSize md dv).defined = true ↔
    ∃ d v, md = some d ∧ dv = some v ∧ 0 < v.num := by
  unfold computeEffectSize
  cases md with
  | none => simp
  | some d =>
    cases dv with
    | none => simp
    | some v =>
      by_cases hv : 0 < v.num
      · simp [hv]
      · simp [hv]

/-- 23. When effect size is defined, its sign matches `mean_delta` and `sqMag = mean_delta² / var`. -/
theorem computeEffectSize_sign_matches_delta (d : SignedRat) (v : NNRat) (hv : 0 < v.num) :
    (computeEffectSize (some d) (some v)).sign = some (EffectSign.ofSignedRat d) ∧
    (computeEffectSize (some d) (some v)).sqMag = some (NNRat.div (sSqNNRat d) v hv) := by
  unfold computeEffectSize
  simp [hv]

/-- 24. Negating `mean_delta` preserves effect-size presence & squared magnitude while flipping sign. -/
theorem computeEffectSize_neg_swap (md : Option SignedRat) (dv : Option NNRat) :
    (computeEffectSize (md.map sNeg) dv).defined = (computeEffectSize md dv).defined ∧
    (computeEffectSize (md.map sNeg) dv).sqMag = (computeEffectSize md dv).sqMag ∧
    (computeEffectSize (md.map sNeg) dv).sign = (computeEffectSize md dv).sign.map EffectSign.flip := by
  unfold computeEffectSize
  cases md with
  | none => simp
  | some d =>
    cases dv with
    | none => simp
    | some v =>
      by_cases hv : 0 < v.num
      · simp [hv, sSqNNRat_neg, EffectSign.ofSignedRat_neg]
      · simp [hv]

/-! ## Group 5 — Permutation Invariance & Baseline/Candidate Swap Duality (7 Theorems) -/

/-- 25. Baseline/candidate sign-flip duality of `_finalize_inference`. -/
theorem finalizeInference_neg_swap_duality (oracle : TwoTailedOracle) (inp : InferenceInput)
    (hcPos : NNRat.zero < inp.confidenceLevel) :
    let out := finalizeInferenceWith oracle inp
    let outNeg := finalizeInferenceWith oracle (negateInputDelta inp)
    outNeg.significance = out.significance.swapDirection ∧
    outNeg.statisticallySignificant = out.statisticallySignificant ∧
    optNNRatEquiv outNeg.pValue out.pValue ∧
    optSignedRatEquiv outNeg.ciLow (out.ciHigh.map sNeg) ∧
    optSignedRatEquiv outNeg.ciHigh (out.ciLow.map sNeg) ∧
    outNeg.effectSize.defined = out.effectSize.defined ∧
    outNeg.effectSize.sign = out.effectSize.sign.map EffectSign.flip := by
  dsimp only
  unfold finalizeInferenceWith finalizeInferenceDirect negateInputDelta
  cases he : inp.hasEnoughSamples <;> cases hmd : inp.meanDelta <;>
    cases hse : inp.seSq <;> cases hdf : inp.df
  all_goals simp only [Option.map_none, Option.map_some]
  any_goals simp [SignificanceStatus.swapDirection, optNNRatEquiv, optSignedRatEquiv, emptyEffectSize]
  rename_i d s f
  have heff := computeEffectSize_neg_swap (some d) inp.effectDenomVar
  simp only [Option.map_some] at heff
  by_cases hs0 : s.num = 0
  · simp only [hs0, ↓reduceIte]
    by_cases hd0 : d.num = 0
    · have hnd0 : (sNeg d).num = 0 := by unfold sNeg; dsimp only; omega
      simp [hd0, hnd0, NNRat.equiv_refl, sClampUnit_neg, heff.1, heff.2.2]
    · by_cases hdPos : 0 < d.num
      · have hndNe : (sNeg d).num ≠ 0 := by unfold sNeg; dsimp only; omega
        have hndNotPos : ¬ (0 < (sNeg d).num) := by unfold sNeg; dsimp only; omega
        simp [hd0, hdPos, hndNe, hndNotPos, NNRat.equiv_refl, sClampUnit_neg, heff.1, heff.2.2]
      · have hdNeg : d.num < 0 := by omega
        have hndNe : (sNeg d).num ≠ 0 := by unfold sNeg; dsimp only; omega
        have hndPos : 0 < (sNeg d).num := by unfold sNeg; dsimp only; omega
        simp [hd0, hdPos, hndNe, hndPos, NNRat.equiv_refl, sClampUnit_neg, heff.1, heff.2.2]
  · simp only [hs0, ↓reduceIte]
    have hpSym : oracle.pValue (sNeg d) s f ≈ oracle.pValue d s f := oracle.pValue_neg d s f
    have hpIff : oracle.pValue (sNeg d) s f < alphaOf inp.confidenceLevel ↔
                 oracle.pValue d s f < alphaOf inp.confidenceLevel := by
      constructor
      · exact nnrat_lt_of_equiv_left hpSym
      · exact nnrat_lt_of_equiv_left hpSym.symm
    have hciLo : sClampUnit (sSub (sNeg d) (ofNNRat (oracle.margin s f inp.confidenceLevel))) ≈ₛ
                 sNeg (sClampUnit (sAdd d (ofNNRat (oracle.margin s f inp.confidenceLevel)))) := by
      have h1 := sNeg_sAdd_ofNNRat d (oracle.margin s f inp.confidenceLevel)
      exact SignedRat.equiv_trans (sClampUnit_equiv_congr h1.symm) (sClampUnit_neg _)
    have hciHi : sClampUnit (sAdd (sNeg d) (ofNNRat (oracle.margin s f inp.confidenceLevel))) ≈ₛ
                 sNeg (sClampUnit (sSub d (ofNNRat (oracle.margin s f inp.confidenceLevel)))) := by
      have h1 := sNeg_sSub_ofNNRat d (oracle.margin s f inp.confidenceLevel)
      exact SignedRat.equiv_trans (sClampUnit_equiv_congr h1.symm) (sClampUnit_neg _)
    have hzeroNotLt : d.num = 0 → ¬ (oracle.pValue d s f < alphaOf inp.confidenceLevel) := by
      intro hd0
      have hpOne := oracle.pValue_zero_delta d s f ((sEquiv_zero_iff d).mpr hd0)
      have hAlphaLtP := nnrat_lt_of_equiv_right hpOne.symm (alphaOf_lt_one hcPos)
      rw [NNRat.lt_iff_not_le]
      intro hle; exact hle (NNRat.le_of_lt hAlphaLtP)
    by_cases hp : oracle.pValue d s f < alphaOf inp.confidenceLevel
    · have hpNeg : oracle.pValue (sNeg d) s f < alphaOf inp.confidenceLevel := hpIff.mpr hp
      have hdNe0 : d.num ≠ 0 := fun hd0 => hzeroNotLt hd0 hp
      by_cases hdPos : 0 < d.num
      · have hndNotPos : ¬ (0 < (sNeg d).num) := by unfold sNeg; dsimp only; omega
        simp [hp, hpNeg, hdPos, hndNotPos, hpSym, hciLo, hciHi, heff.1, heff.2.2]
      · have hndPos : 0 < (sNeg d).num := by unfold sNeg; dsimp only; omega
        simp [hp, hpNeg, hdPos, hndPos, hpSym, hciLo, hciHi, heff.1, heff.2.2]
    · have hpNeg : ¬ (oracle.pValue (sNeg d) s f < alphaOf inp.confidenceLevel) :=
        fun h => hp (hpIff.mp h)
      simp [hp, hpNeg, hpSym, hciLo, hciHi, heff.1, heff.2.2]

private theorem pairedDiffs_map_pairs (ps : List (NNRat × NNRat)) :
    pairedDiffs (ps.map Prod.fst) (ps.map Prod.snd) =
    ps.map (fun p => SignedRat.subNNRat p.2 p.1) := by
  induction ps with
  | nil => rfl
  | cons p ps ih =>
    simp [pairedDiffs]

/-- 26. Permuting aligned `(baseline, candidate)` pairs leaves paired inference inputs invariant. -/
theorem buildPairedInput_perm_invariant {ps₁ ps₂ : List (NNRat × NNRat)}
    (hp : List.Perm ps₁ ps₂) (conf : NNRat) (minS excl : Nat) :
    let inp₁ := buildPairedInput (ps₁.map Prod.fst) (ps₁.map Prod.snd) conf minS excl
    let inp₂ := buildPairedInput (ps₂.map Prod.fst) (ps₂.map Prod.snd) conf minS excl
    inp₁.sampleSize = inp₂.sampleSize ∧
    inp₁.hasEnoughSamples = inp₂.hasEnoughSamples ∧
    optSignedRatEquiv inp₁.meanDelta inp₂.meanDelta ∧
    optNNRatEquiv inp₁.seSq inp₂.seSq ∧
    optNNRatEquiv inp₁.df inp₂.df ∧
    optNNRatEquiv inp₁.effectDenomVar inp₂.effectDenomVar := by
  dsimp only
  simp only [buildPairedInput, pairedDiffs_map_pairs]
  have hpDiff : List.Perm (ps₁.map fun p => SignedRat.subNNRat p.2 p.1)
                          (ps₂.map fun p => SignedRat.subNNRat p.2 p.1) :=
    hp.map _
  have hlen : (ps₁.map fun p => SignedRat.subNNRat p.2 p.1).length =
              (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length :=
    hpDiff.length_eq
  by_cases h2 : 2 ≤ (ps₁.map fun p => SignedRat.subNNRat p.2 p.1).length
  · have h2' : 2 ≤ (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length := hlen ▸ h2
    have hpos : 0 < (ps₁.map fun p => SignedRat.subNNRat p.2 p.1).length := by omega
    have hpos' : 0 < (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length := by omega
    simp only [h2, h2', hpos, hpos', ↓reduceDIte]
    have hvar := sampleVarSigned_perm hpDiff h2 h2'
    have hmean := sMeanList_perm hpDiff hpos hpos'
    have hdenEq : NNRat.ofNat (ps₁.map fun p => SignedRat.subNNRat p.2 p.1).length ≈
                  NNRat.ofNat (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length := by
      rw [hlen]; exact NNRat.equiv_refl _
    have hse := nnrat_div_equiv_congr hvar hdenEq
      (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
    refine ⟨hlen, by rw [hlen], hmean, hse, ?_, hvar⟩
    show NNRat.ofNat _ ≈ NNRat.ofNat _
    rw [hlen]; exact NNRat.equiv_refl _
  · have h2' : ¬ (2 ≤ (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length) := hlen ▸ h2
    simp only [h2, h2', ↓reduceDIte]
    by_cases hpos : 0 < (ps₁.map fun p => SignedRat.subNNRat p.2 p.1).length
    · have hpos' : 0 < (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length := hlen ▸ hpos
      simp only [hpos, hpos', ↓reduceDIte]
      exact ⟨hlen, by rw [hlen], sMeanList_perm hpDiff hpos hpos', trivial, trivial, trivial⟩
    · have hpos' : ¬ (0 < (ps₂.map fun p => SignedRat.subNNRat p.2 p.1).length) := hlen ▸ hpos
      simp only [hpos, hpos', ↓reduceDIte]
      exact ⟨hlen, by rw [hlen], trivial, trivial, trivial, trivial⟩

private inductive PointwiseEquiv : List SignedRat → List SignedRat → Prop where
  | nil : PointwiseEquiv [] []
  | cons {x y : SignedRat} {xs ys : List SignedRat} :
      x ≈ₛ y → PointwiseEquiv xs ys → PointwiseEquiv (x :: xs) (y :: ys)

private theorem sSumList_pointwise_equiv {xs ys : List SignedRat}
    (h : PointwiseEquiv xs ys) : sSumList xs ≈ₛ sSumList ys := by
  induction h with
  | nil => exact SignedRat.equiv_refl _
  | cons hx _ ih => exact sAdd_equiv_congr hx ih

private theorem sumSqDevSigned_pointwise_equiv {xs ys : List SignedRat}
    (h : PointwiseEquiv xs ys) {m₁ m₂ : SignedRat} (hm : m₁ ≈ₛ m₂) :
    sumSqDevSigned xs m₁ ≈ sumSqDevSigned ys m₂ := by
  induction h with
  | nil => exact NNRat.equiv_refl _
  | cons hx _ ih =>
    simp only [sumSqDevSigned, List.map_cons, nnSumList] at ih ⊢
    exact nnrat_add_equiv_congr (sSqNNRat_equiv_congr (sSub_equiv_congr hx hm)) ih

private theorem pairedDiffs_swap_pointwise (base cand : List NNRat) :
    PointwiseEquiv (pairedDiffs cand base) ((pairedDiffs base cand).map sNeg) := by
  induction base generalizing cand with
  | nil =>
    cases cand <;> exact PointwiseEquiv.nil
  | cons b bs ih =>
    cases cand with
    | nil => exact PointwiseEquiv.nil
    | cons c cs =>
      simp only [pairedDiffs, List.zipWith_cons_cons, List.map_cons]
      exact PointwiseEquiv.cons (sNeg_subNNRat c b).symm (ih cs)

/-- 27. Swapping baseline and candidate in paired statistics negates `meanDelta` and preserves `se²`, `df`, and `var`. -/
theorem buildPairedInput_swap_duality (base cand : List NNRat)
    (_hlen : base.length = cand.length) (conf : NNRat) (minS excl : Nat) :
    let inp := buildPairedInput base cand conf minS excl
    let inpSwap := buildPairedInput cand base conf minS excl
    inpSwap.sampleSize = inp.sampleSize ∧
    inpSwap.hasEnoughSamples = inp.hasEnoughSamples ∧
    optSignedRatEquiv inpSwap.meanDelta (inp.meanDelta.map sNeg) ∧
    optNNRatEquiv inpSwap.seSq inp.seSq ∧
    optNNRatEquiv inpSwap.df inp.df ∧
    optNNRatEquiv inpSwap.effectDenomVar inp.effectDenomVar := by
  dsimp only
  unfold buildPairedInput
  dsimp only
  have hpw := pairedDiffs_swap_pointwise base cand
  have hlenEq : (pairedDiffs cand base).length = (pairedDiffs base cand).length :=
    pairedDiffs_swap base cand
  have hlenMap : ((pairedDiffs base cand).map sNeg).length = (pairedDiffs base cand).length :=
    List.length_map _
  by_cases h2 : 2 ≤ (pairedDiffs base cand).length
  · have h2s : 2 ≤ (pairedDiffs cand base).length := hlenEq.symm ▸ h2
    have h2m : 2 ≤ ((pairedDiffs base cand).map sNeg).length := hlenMap.symm ▸ h2
    have hpos : 0 < (pairedDiffs base cand).length := by omega
    have hposs : 0 < (pairedDiffs cand base).length := by omega
    have hposm : 0 < ((pairedDiffs base cand).map sNeg).length := by omega
    simp only [h2, h2s, hpos, hposs, ↓reduceDIte, Option.map_some]
    have hmean1 : sMeanList (pairedDiffs cand base) hposs ≈ₛ
                  sMeanList ((pairedDiffs base cand).map sNeg) hposm :=
      sDivNat_equiv_congr (sSumList_pointwise_equiv hpw) (hlenEq.trans hlenMap.symm) hposs hposm
    have hmeanNeg : sMeanList (pairedDiffs cand base) hposs ≈ₛ
                    sNeg (sMeanList (pairedDiffs base cand) hpos) :=
      SignedRat.equiv_trans hmean1 (sMeanList_neg (pairedDiffs base cand) hpos hposm)
    have hvar1 : sampleVarSigned (pairedDiffs cand base) h2s ≈
                 sampleVarSigned ((pairedDiffs base cand).map sNeg) h2m := by
      unfold sampleVarSigned
      have hsq := sumSqDevSigned_pointwise_equiv hpw hmean1
      have hdenV : NNRat.ofNat ((pairedDiffs cand base).length - 1) ≈
                   NNRat.ofNat (((pairedDiffs base cand).map sNeg).length - 1) := by
        rw [hlenEq, hlenMap]; exact NNRat.equiv_refl _
      exact nnrat_div_equiv_congr hsq hdenV
        (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
    have hvar : sampleVarSigned (pairedDiffs cand base) h2s ≈
                sampleVarSigned (pairedDiffs base cand) h2 :=
      NNRat.equiv_trans hvar1 (sampleVarSigned_neg (pairedDiffs base cand) h2 h2m)
    have hdenS : NNRat.ofNat (pairedDiffs cand base).length ≈
                 NNRat.ofNat (pairedDiffs base cand).length := by
      rw [hlenEq]; exact NNRat.equiv_refl _
    have hse := nnrat_div_equiv_congr hvar hdenS
      (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
    refine ⟨hlenEq, by rw [hlenEq], hmeanNeg, hse, ?_, hvar⟩
    show NNRat.ofNat _ ≈ NNRat.ofNat _
    rw [hlenEq]; exact NNRat.equiv_refl _
  · have h2s : ¬ (2 ≤ (pairedDiffs cand base).length) := hlenEq.symm ▸ h2
    simp only [h2, h2s, ↓reduceDIte]
    by_cases hpos : 0 < (pairedDiffs base cand).length
    · have hposs : 0 < (pairedDiffs cand base).length := hlenEq.symm ▸ hpos
      have hposm : 0 < ((pairedDiffs base cand).map sNeg).length := hlenMap.symm ▸ hpos
      simp only [hpos, hposs, ↓reduceDIte, Option.map_some]
      have hmean1 : sMeanList (pairedDiffs cand base) hposs ≈ₛ
                    sMeanList ((pairedDiffs base cand).map sNeg) hposm :=
        sDivNat_equiv_congr (sSumList_pointwise_equiv hpw) (hlenEq.trans hlenMap.symm) hposs hposm
      have hmeanNeg := SignedRat.equiv_trans hmean1 (sMeanList_neg (pairedDiffs base cand) hpos hposm)
      exact ⟨hlenEq, by rw [hlenEq], hmeanNeg, trivial, trivial, trivial⟩
    · have hposs : ¬ (0 < (pairedDiffs cand base).length) := hlenEq.symm ▸ hpos
      simp only [hpos, hposs, ↓reduceDIte, Option.map_none]
      exact ⟨hlenEq, by rw [hlenEq], trivial, trivial, trivial, trivial⟩

private theorem welchDf_congr_full {vB₁ vB₂ vC₁ vC₂ : NNRat} {k₁ k₂ m₁ m₂ : Nat}
    (hb : vB₁ ≈ vB₂) (hc : vC₁ ≈ vC₂) (hkEq : k₁ = k₂) (hmEq : m₁ = m₂)
    (hk₁ : 2 ≤ k₁) (hm₁ : 2 ≤ m₁) (hk₂ : 2 ≤ k₂) (hm₂ : 2 ≤ m₂) :
    welchSatterthwaiteDf vB₁ vC₁ k₁ m₁ hk₁ hm₁ ≈ welchSatterthwaiteDf vB₂ vC₂ k₂ m₂ hk₂ hm₂ := by
  subst hkEq; subst hmEq
  exact welchSatterthwaiteDf_equiv_congr hb hc hk₁ hm₁

private theorem pooledVar_congr_full {vB₁ vB₂ vC₁ vC₂ : NNRat} {k₁ k₂ m₁ m₂ : Nat}
    (hb : vB₁ ≈ vB₂) (hc : vC₁ ≈ vC₂) (hkEq : k₁ = k₂) (hmEq : m₁ = m₂)
    (hk₁ : 2 ≤ k₁) (hm₁ : 2 ≤ m₁) (hk₂ : 2 ≤ k₂) (hm₂ : 2 ≤ m₂) :
    pooledVarNNRat vB₁ vC₁ k₁ m₁ hk₁ hm₁ ≈ pooledVarNNRat vB₂ vC₂ k₂ m₂ hk₂ hm₂ := by
  subst hkEq; subst hmEq
  exact pooledVarNNRat_equiv_congr hb hc hk₁ hm₁

/-- 28. Independent permutations of baseline and candidate runs leave Welch inputs invariant. -/
theorem buildWelchInput_perm_invariant {b₁ b₂ c₁ c₂ : List NNRat}
    (hb : List.Perm b₁ b₂) (hc : List.Perm c₁ c₂) (conf : NNRat) (minS : Nat) :
    let inp₁ := buildWelchInput b₁ c₁ conf minS
    let inp₂ := buildWelchInput b₂ c₂ conf minS
    inp₁.sampleSize = inp₂.sampleSize ∧
    inp₁.hasEnoughSamples = inp₂.hasEnoughSamples ∧
    optSignedRatEquiv inp₁.meanDelta inp₂.meanDelta ∧
    optNNRatEquiv inp₁.seSq inp₂.seSq ∧
    optNNRatEquiv inp₁.df inp₂.df ∧
    optNNRatEquiv inp₁.effectDenomVar inp₂.effectDenomVar := by
  dsimp only
  unfold buildWelchInput
  dsimp only
  have hbl : b₁.length = b₂.length := hb.length_eq
  have hcl : c₁.length = c₂.length := hc.length_eq
  by_cases hb2 : 2 ≤ b₁.length
  · have hb2' : 2 ≤ b₂.length := hbl ▸ hb2
    by_cases hc2 : 2 ≤ c₁.length
    · have hc2' : 2 ≤ c₂.length := hcl ▸ hc2
      have hbp : 0 < b₁.length := by omega
      have hbp' : 0 < b₂.length := by omega
      have hcp : 0 < c₁.length := by omega
      have hcp' : 0 < c₂.length := by omega
      simp only [hb2, hb2', hc2, hc2', hbp, hbp', hcp, hcp', ↓reduceDIte]
      have hmean := SignedRat.subNNRat_equiv_congr
        (nnMeanList_perm hc hcp hcp') (nnMeanList_perm hb hbp hbp')
      have hvarB := sampleVarNNRat_perm hb hb2 hb2'
      have hvarC := sampleVarNNRat_perm hc hc2 hc2'
      have hdenB : NNRat.ofNat b₁.length ≈ NNRat.ofNat b₂.length := by
        rw [hbl]; exact NNRat.equiv_refl _
      have hdenC : NNRat.ofNat c₁.length ≈ NNRat.ofNat c₂.length := by
        rw [hcl]; exact NNRat.equiv_refl _
      have hvB := nnrat_div_equiv_congr hvarB hdenB
        (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
      have hvC := nnrat_div_equiv_congr hvarC hdenC
        (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
      have hse := nnrat_add_equiv_congr hvB hvC
      have hdf := welchDf_congr_full hvB hvC hbl hcl hb2 hc2 hb2' hc2'
      have hpv := pooledVar_congr_full hvarB hvarC hbl hcl hb2 hc2 hb2' hc2'
      exact ⟨by rw [hbl, hcl], by rw [hbl, hcl], hmean, hse, hdf, hpv⟩
    · have hc2' : ¬ (2 ≤ c₂.length) := hcl ▸ hc2
      simp only [hb2, hb2', hc2, hc2', ↓reduceDIte]
      have hbp : 0 < b₁.length := by omega
      have hbp' : 0 < b₂.length := by omega
      by_cases hcp : 0 < c₁.length
      · have hcp' : 0 < c₂.length := hcl ▸ hcp
        simp only [hbp, hbp', hcp, hcp', ↓reduceDIte]
        have hmean := SignedRat.subNNRat_equiv_congr
          (nnMeanList_perm hc hcp hcp') (nnMeanList_perm hb hbp hbp')
        exact ⟨by rw [hbl, hcl], trivial, hmean, trivial, trivial, trivial⟩
      · have hcp' : ¬ (0 < c₂.length) := hcl ▸ hcp
        simp only [hbp, hbp', hcp, hcp', ↓reduceDIte]
        exact ⟨by rw [hbl, hcl], trivial, trivial, trivial, trivial, trivial⟩
  · have hb2' : ¬ (2 ≤ b₂.length) := hbl ▸ hb2
    simp only [hb2, hb2', ↓reduceDIte]
    by_cases hbp : 0 < b₁.length
    · have hbp' : 0 < b₂.length := hbl ▸ hbp
      by_cases hcp : 0 < c₁.length
      · have hcp' : 0 < c₂.length := hcl ▸ hcp
        simp only [hbp, hbp', hcp, hcp', ↓reduceDIte]
        have hmean := SignedRat.subNNRat_equiv_congr
          (nnMeanList_perm hc hcp hcp') (nnMeanList_perm hb hbp hbp')
        exact ⟨by rw [hbl, hcl], trivial, hmean, trivial, trivial, trivial⟩
      · have hcp' : ¬ (0 < c₂.length) := hcl ▸ hcp
        simp only [hbp, hbp', hcp, hcp', ↓reduceDIte]
        exact ⟨by rw [hbl, hcl], trivial, trivial, trivial, trivial, trivial⟩
    · have hbp' : ¬ (0 < b₂.length) := hbl ▸ hbp
      simp only [hbp, hbp', ↓reduceDIte]
      exact ⟨by rw [hbl, hcl], trivial, trivial, trivial, trivial, trivial⟩

/-- 29. Swapping baseline and candidate cohorts in Welch statistics negates `meanDelta` and preserves `se²`, `df`, and pooled variance. -/
theorem buildWelchInput_swap_duality (base cand : List NNRat) (conf : NNRat) (minS : Nat) :
    let inp := buildWelchInput base cand conf minS
    let inpSwap := buildWelchInput cand base conf minS
    inpSwap.sampleSize = inp.sampleSize ∧
    inpSwap.hasEnoughSamples = inp.hasEnoughSamples ∧
    optSignedRatEquiv inpSwap.meanDelta (inp.meanDelta.map sNeg) ∧
    optNNRatEquiv inpSwap.seSq inp.seSq ∧
    optNNRatEquiv inpSwap.df inp.df ∧
    optNNRatEquiv inpSwap.effectDenomVar inp.effectDenomVar := by
  dsimp only
  unfold buildWelchInput
  dsimp only
  by_cases hb2 : 2 ≤ base.length
  · by_cases hc2 : 2 ≤ cand.length
    · have hbp : 0 < base.length := by omega
      have hcp : 0 < cand.length := by omega
      simp only [hb2, hc2, hbp, hcp, ↓reduceDIte, Option.map_some]
      refine ⟨Nat.min_comm _ _, ?_, (sNeg_subNNRat _ _).symm, nnrat_add_comm_equiv _ _,
              welchSatterthwaiteDf_symm_core _ _ _ _ hc2 hb2,
              pooledVarNNRat_symm _ _ _ _ hc2 hb2⟩
      simp [and_comm]
    · simp only [hb2, hc2, ↓reduceDIte]
      have hbp : 0 < base.length := by omega
      by_cases hcp : 0 < cand.length
      · simp only [hbp, hcp, ↓reduceDIte, Option.map_some]
        exact ⟨Nat.min_comm _ _, trivial, (sNeg_subNNRat _ _).symm, trivial, trivial, trivial⟩
      · simp only [hbp, hcp, ↓reduceDIte, Option.map_none]
        exact ⟨Nat.min_comm _ _, trivial, trivial, trivial, trivial, trivial⟩
  · by_cases hc2 : 2 ≤ cand.length
    · simp only [hb2, hc2, ↓reduceDIte]
      have hcp : 0 < cand.length := by omega
      by_cases hbp : 0 < base.length
      · simp only [hbp, hcp, ↓reduceDIte, Option.map_some]
        exact ⟨Nat.min_comm _ _, trivial, (sNeg_subNNRat _ _).symm, trivial, trivial, trivial⟩
      · simp only [hbp, hcp, ↓reduceDIte, Option.map_none]
        exact ⟨Nat.min_comm _ _, trivial, trivial, trivial, trivial, trivial⟩
    · simp only [hb2, hc2, ↓reduceDIte]
      by_cases hbp : 0 < base.length
      · by_cases hcp : 0 < cand.length
        · simp only [hbp, hcp, ↓reduceDIte, Option.map_some]
          exact ⟨Nat.min_comm _ _, trivial, (sNeg_subNNRat _ _).symm, trivial, trivial, trivial⟩
        · simp only [hbp, hcp, ↓reduceDIte, Option.map_none]
          exact ⟨Nat.min_comm _ _, trivial, trivial, trivial, trivial, trivial⟩
      · by_cases hcp : 0 < cand.length
        · simp only [hbp, hcp, ↓reduceDIte, Option.map_none]
          exact ⟨Nat.min_comm _ _, trivial, trivial, trivial, trivial, trivial⟩
        · simp only [hbp, hcp, ↓reduceDIte, Option.map_none]
          exact ⟨Nat.min_comm _ _, trivial, trivial, trivial, trivial, trivial⟩

/-- 30. Permuting baseline or candidate trials leaves one-sample cohort inputs invariant. -/
theorem buildOneSampleInput_perm_invariant {b₁ b₂ c₁ c₂ : List NNRat}
    (hb : List.Perm b₁ b₂) (hc : List.Perm c₁ c₂) (conf : NNRat) (minS : Nat) :
    let inp₁ := buildOneSampleInput b₁ c₁ conf minS
    let inp₂ := buildOneSampleInput b₂ c₂ conf minS
    inp₁.sampleSize = inp₂.sampleSize ∧
    inp₁.hasEnoughSamples = inp₂.hasEnoughSamples ∧
    optSignedRatEquiv inp₁.meanDelta inp₂.meanDelta ∧
    optNNRatEquiv inp₁.seSq inp₂.seSq ∧
    optNNRatEquiv inp₁.df inp₂.df ∧
    optNNRatEquiv inp₁.effectDenomVar inp₂.effectDenomVar := by
  dsimp only
  unfold buildOneSampleInput
  dsimp only
  have hbl : b₁.length = b₂.length := hb.length_eq
  have hcl : c₁.length = c₂.length := hc.length_eq
  by_cases hb1 : b₁.length = 1
  · have hb1' : b₂.length = 1 := hbl ▸ hb1
    by_cases hc2 : 2 ≤ c₁.length
    · have hc2' : 2 ≤ c₂.length := hcl ▸ hc2
      simp only [hb1, hb1', hc2, hc2', ↓reduceDIte]
      have hmean := SignedRat.subNNRat_equiv_congr
        (nnMeanList_perm hc (by omega) (by omega))
        (nnMeanList_perm hb (by omega) (by omega))
      have hvar := sampleVarNNRat_perm hc hc2 hc2'
      have hdenC : NNRat.ofNat c₁.length ≈ NNRat.ofNat c₂.length := by
        rw [hcl]; exact NNRat.equiv_refl _
      have hse := nnrat_div_equiv_congr hvar hdenC
        (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
      refine ⟨hcl, by rw [hcl], hmean, hse, ?_, hvar⟩
      show NNRat.ofNat _ ≈ NNRat.ofNat _
      rw [hcl]; exact NNRat.equiv_refl _
    · have hc2' : ¬ (2 ≤ c₂.length) := hcl ▸ hc2
      simp only [hb1, hb1', hc2, hc2', ↓reduceDIte]
      exact ⟨by rw [hcl], trivial, trivial, trivial, trivial, trivial⟩
  · have hb1' : b₂.length ≠ 1 := hbl ▸ hb1
    by_cases hc1 : c₁.length = 1
    · have hc1' : c₂.length = 1 := hcl ▸ hc1
      by_cases hb2 : 2 ≤ b₁.length
      · have hb2' : 2 ≤ b₂.length := hbl ▸ hb2
        simp only [hb1, hb1', hc1, hc1', hb2, hb2', ↓reduceDIte]
        have hmean := SignedRat.subNNRat_equiv_congr
          (nnMeanList_perm hc (by omega) (by omega))
          (nnMeanList_perm hb (by omega) (by omega))
        have hvar := sampleVarNNRat_perm hb hb2 hb2'
        have hdenB : NNRat.ofNat b₁.length ≈ NNRat.ofNat b₂.length := by
          rw [hbl]; exact NNRat.equiv_refl _
        have hse := nnrat_div_equiv_congr hvar hdenB
          (by dsimp [NNRat.ofNat]; omega) (by dsimp [NNRat.ofNat]; omega)
        refine ⟨hbl, by rw [hbl], hmean, hse, ?_, hvar⟩
        show NNRat.ofNat _ ≈ NNRat.ofNat _
        rw [hbl]; exact NNRat.equiv_refl _
      · have hb2' : ¬ (2 ≤ b₂.length) := hbl ▸ hb2
        simp only [hb1, hb1', hc1, hc1', hb2, hb2', ↓reduceDIte]
        exact ⟨by rw [hbl], trivial, trivial, trivial, trivial, trivial⟩
    · have hc1' : c₂.length ≠ 1 := hcl ▸ hc1
      simp only [hb1, hb1', hc1, hc1', ↓reduceDIte]
      exact ⟨by rw [hbl, hcl], trivial, trivial, trivial, trivial, trivial⟩

/-- 31. Swapping baseline and candidate in one-sample statistics negates `meanDelta` and preserves `sampleSize`, `se²`, `df`, and `var`. -/
theorem buildOneSampleInput_swap_duality (base cand : List NNRat) (conf : NNRat) (minS : Nat)
    (hvalid : (base.length = 1 ∧ 2 ≤ cand.length) ∨ (cand.length = 1 ∧ 2 ≤ base.length)) :
    let inp := buildOneSampleInput base cand conf minS
    let inpSwap := buildOneSampleInput cand base conf minS
    inpSwap.sampleSize = inp.sampleSize ∧
    inpSwap.hasEnoughSamples = inp.hasEnoughSamples ∧
    optSignedRatEquiv inpSwap.meanDelta (inp.meanDelta.map sNeg) ∧
    optNNRatEquiv inpSwap.seSq inp.seSq ∧
    optNNRatEquiv inpSwap.df inp.df ∧
    optNNRatEquiv inpSwap.effectDenomVar inp.effectDenomVar := by
  dsimp only
  unfold buildOneSampleInput
  dsimp only
  rcases hvalid with ⟨hb1, hc2⟩ | ⟨hc1, hb2⟩
  · have hcNe1 : cand.length ≠ 1 := by omega
    simp only [hb1, hc2, hcNe1, ↓reduceDIte, Option.map_some]
    exact ⟨trivial, trivial, (sNeg_subNNRat _ _).symm, NNRat.equiv_refl _, NNRat.equiv_refl _, NNRat.equiv_refl _⟩
  · have hbNe1 : base.length ≠ 1 := by omega
    simp only [hc1, hb2, hbNe1, ↓reduceDIte, Option.map_some]
    exact ⟨trivial, trivial, (sNeg_subNNRat _ _).symm, NNRat.equiv_refl _, NNRat.equiv_refl _, NNRat.equiv_refl _⟩

/-! ## Group 6 — Cohort Dispatch, Aligned Pairs & `QualityGate` Escalation Bridge (5 Theorems) -/

/-- 32. Cohort method dispatch forms an exact total partition over all `(k, m) : Nat × Nat`. -/
theorem dispatchCohortMethod_total_partition (k m : Nat) :
    (dispatchCohortMethod k m = .oneSampleTRun ↔ (k = 1 ∧ 2 ≤ m) ∨ (m = 1 ∧ 2 ≤ k)) ∧
    (dispatchCohortMethod k m = .pairedTCaseFallback ↔ k = 1 ∧ m = 1) ∧
    (dispatchCohortMethod k m = .welchTRun ↔ (2 ≤ k ∧ 2 ≤ m) ∨ k = 0 ∨ m = 0) := by
  cases k with
  | zero =>
    cases m with
    | zero => simp [dispatchCohortMethod]
    | succ m' => cases m' <;> simp [dispatchCohortMethod]
  | succ k' =>
    cases k' with
    | zero =>
      cases m with
      | zero => simp [dispatchCohortMethod]
      | succ m' => cases m' <;> simp [dispatchCohortMethod]
    | succ k'' =>
      cases m with
      | zero => simp [dispatchCohortMethod]
      | succ m' => cases m' <;> simp [dispatchCohortMethod]

/-- 33. Cohort method dispatch is symmetric in `(k, m)`. -/
theorem dispatchCohortMethod_symm (k m : Nat) :
    dispatchCohortMethod k m = dispatchCohortMethod m k := by
  cases k with
  | zero =>
    cases m with
    | zero => rfl
    | succ m' => cases m' <;> simp [dispatchCohortMethod]
  | succ k' =>
    cases k' with
    | zero =>
      cases m with
      | zero => simp [dispatchCohortMethod]
      | succ m' => cases m' <;> simp [dispatchCohortMethod]
    | succ k'' =>
      cases m with
      | zero => simp [dispatchCohortMethod]
      | succ m' => cases m' <;> simp [dispatchCohortMethod]

/-- 34. Aligned case-pair extraction preserves equal paired lengths and bounded conservation. -/
theorem extractAlignedPairs_conservation (shared : List SharedCaseScores) :
    let r := extractAlignedPairs shared
    r.baselineScores.length = r.candidateScores.length ∧
    r.baselineScores.length + r.excludedPairCount ≤ shared.length ∧
    ((∀ row ∈ shared, row.baselineMetricPresent = true ∨ row.candidateMetricPresent = true) →
      r.baselineScores.length + r.excludedPairCount = shared.length) := by
  induction shared with
  | nil =>
    simp [extractAlignedPairs]
  | cons row rest ih =>
    rcases ih with ⟨hlen, hle, heq⟩
    simp only [extractAlignedPairs, List.length_cons]
    cases hb : row.baselineScore <;> cases hc : row.candidateScore <;>
      cases hbp : row.baselineMetricPresent <;> cases hcp : row.candidateMetricPresent
    all_goals
      simp only [Bool.and_false, Bool.and_true, Bool.or_false, Bool.or_true,
                 Bool.false_eq_true, ↓reduceIte, List.length_cons]
      refine ⟨by omega, by omega, fun hall => ?_⟩
      have hrest := heq (fun r hr => hall r (by simp [hr]))
      have hrow := hall row (by simp)
      simp [hbp, hcp] at hrow
      try omega

/-- 35. Per-metric statistical regression rule check mapping is exact and never emits `INCONCLUSIVE`. -/
theorem statisticalRegressionCheck_sound (sig : SignificanceStatus) (failFlag : Bool) :
    (statisticalRegressionCheck sig failFlag = .fail ↔
      sig = .significantRegression ∧ failFlag = true) ∧
    (statisticalRegressionCheck sig failFlag = .warning ↔
      sig = .significantRegression ∧ failFlag = false) ∧
    (statisticalRegressionCheck sig failFlag = .pass ↔
      sig ≠ .significantRegression) ∧
    statisticalRegressionCheck sig failFlag ≠ .inconclusive := by
  cases sig <;> cases failFlag <;> simp [statisticalRegressionCheck]

/-- 36. End-to-end `QualityGate` bridge proving only `SIGNIFICANT_REGRESSION` escalates the gate. -/
theorem evaluateMetricSignificanceChecks_gate_bridge (statuses : List SignificanceStatus)
    (failFlag : Bool) :
    let out := evaluateMetricSignificanceChecks statuses failFlag
    (out.decision = .fail ↔ failFlag = true ∧ SignificanceStatus.significantRegression ∈ statuses) ∧
    (out.decision = .warning ↔ failFlag = false ∧ SignificanceStatus.significantRegression ∈ statuses) ∧
    (out.decision = .pass ↔ SignificanceStatus.significantRegression ∉ statuses) ∧
    out.decision ≠ .inconclusive ∧
    (out.blocking = true ↔ failFlag = true ∧ SignificanceStatus.significantRegression ∈ statuses) ∧
    (out.passed = true ↔ SignificanceStatus.significantRegression ∉ statuses) := by
  dsimp only
  unfold evaluateMetricSignificanceChecks
  let checks : List RuleCheck :=
    statuses.map fun sig =>
      { status := statisticalRegressionCheck sig failFlag, message := sig.toCanonicalString }
  have hFailIff :
      (∃ c ∈ checks, c.status = .fail) ↔
      (failFlag = true ∧ SignificanceStatus.significantRegression ∈ statuses) := by
    constructor
    · rintro ⟨c, hc, hst⟩
      rcases List.mem_map.mp hc with ⟨sig, hsig, rfl⟩
      have hsound := (statisticalRegressionCheck_sound sig failFlag).1.mp hst
      exact ⟨hsound.2, hsound.1 ▸ hsig⟩
    · rintro ⟨hf, hmem⟩
      refine ⟨{ status := statisticalRegressionCheck .significantRegression failFlag,
                message := SignificanceStatus.significantRegression.toCanonicalString },
              List.mem_map.mpr ⟨.significantRegression, hmem, rfl⟩, ?_⟩
      simp [statisticalRegressionCheck, hf]
  have hIncNever : ¬ (∃ c ∈ checks, c.status = .inconclusive) := by
    rintro ⟨c, hc, hst⟩
    rcases List.mem_map.mp hc with ⟨sig, _, rfl⟩
    exact (statisticalRegressionCheck_sound sig failFlag).2.2.2 hst
  have hWarnIff :
      (∃ c ∈ checks, c.status = .warning) ↔
      (failFlag = false ∧ SignificanceStatus.significantRegression ∈ statuses) := by
    constructor
    · rintro ⟨c, hc, hst⟩
      rcases List.mem_map.mp hc with ⟨sig, hsig, rfl⟩
      have hsound := (statisticalRegressionCheck_sound sig failFlag).2.1.mp hst
      exact ⟨hsound.2, hsound.1 ▸ hsig⟩
    · rintro ⟨hf, hmem⟩
      refine ⟨{ status := statisticalRegressionCheck .significantRegression failFlag,
                message := SignificanceStatus.significantRegression.toCanonicalString },
              List.mem_map.mpr ⟨.significantRegression, hmem, rfl⟩, ?_⟩
      simp [statisticalRegressionCheck, hf]
  have hPassIff :
      (∀ c ∈ checks, c.status = .pass) ↔
      SignificanceStatus.significantRegression ∉ statuses := by
    constructor
    · intro hall hmem
      have hc := hall
        { status := statisticalRegressionCheck .significantRegression failFlag,
          message := SignificanceStatus.significantRegression.toCanonicalString }
        (List.mem_map.mpr ⟨.significantRegression, hmem, rfl⟩)
      have hne := (statisticalRegressionCheck_sound .significantRegression failFlag).2.2.1.mp hc
      exact hne rfl
    · intro hnotMem c hc
      rcases List.mem_map.mp hc with ⟨sig, hsig, rfl⟩
      have hne : sig ≠ .significantRegression := fun heq => hnotMem (heq ▸ hsig)
      exact (statisticalRegressionCheck_sound sig failFlag).2.2.1.mpr hne
  have hDecFail : (evaluateChecks checks).decision = .fail ↔
      (failFlag = true ∧ SignificanceStatus.significantRegression ∈ statuses) :=
    (evaluateChecks_eq_fail_iff checks).trans hFailIff
  have hDecPass : (evaluateChecks checks).decision = .pass ↔
      SignificanceStatus.significantRegression ∉ statuses :=
    (evaluateChecks_eq_pass_iff checks).trans hPassIff
  have hDecNotInc : (evaluateChecks checks).decision ≠ .inconclusive := by
    intro hinc
    have hstate := (selectDecision_eq_inconclusive_iff (recordChecks checks)).mp hinc
    have hex := (recordChecks_inconclusive_nonempty_iff checks).mp hstate.2
    exact hIncNever hex
  have hDecWarn : (evaluateChecks checks).decision = .warning ↔
      (failFlag = false ∧ SignificanceStatus.significantRegression ∈ statuses) := by
    constructor
    · intro hw
      have hstate := (selectDecision_eq_warning_iff (recordChecks checks)).mp hw
      exact hWarnIff.mp ((recordChecks_warning_nonempty_iff checks).mp hstate.2.2)
    · intro h
      have hnoFail : (recordChecks checks).failureReasons = [] := by
        by_cases hf : (recordChecks checks).failureReasons = []
        · exact hf
        · exfalso
          have := hFailIff.mp ((recordChecks_failure_nonempty_iff checks).mp hf)
          simp [h.1] at this
      have hnoInc : (recordChecks checks).inconclusiveReasons = [] := by
        by_cases hi : (recordChecks checks).inconclusiveReasons = []
        · exact hi
        · exfalso
          exact hIncNever ((recordChecks_inconclusive_nonempty_iff checks).mp hi)
      have hwarn := (recordChecks_warning_nonempty_iff checks).mpr (hWarnIff.mpr h)
      exact (selectDecision_eq_warning_iff (recordChecks checks)).mpr ⟨hnoFail, hnoInc, hwarn⟩
  have hBlocking : (evaluateChecks checks).blocking = true ↔
      (failFlag = true ∧ SignificanceStatus.significantRegression ∈ statuses) :=
    (evaluateReasonState_blocking_iff (recordChecks checks)).trans hDecFail
  have hPassed : (evaluateChecks checks).passed = true ↔
      SignificanceStatus.significantRegression ∉ statuses :=
    (evaluateReasonState_passed_iff (recordChecks checks)).trans hDecPass
  exact ⟨hDecFail, hDecWarn, hDecPass, hDecNotInc, hBlocking, hPassed⟩

end EvalForgeFormal.Stats
