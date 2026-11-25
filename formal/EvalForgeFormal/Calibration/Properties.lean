import EvalForgeFormal.Calibration.Aggregation

namespace EvalForgeFormal.Calibration

open EvalForgeFormal.Retrieval

/-!
## Group A — Human Label Derivation & Sample Classification (Theorems 1–7)
-/

/-- Theorem 1: Explicit `humanPassed = some b` always overrides score-based derivation. -/
theorem deriveHumanPassed_explicit_override (hs : Option NNRat) (b : Bool) (ht : NNRat) :
    deriveHumanPassed hs (some b) ht = b :=
  rfl

/-- Theorem 2: When `humanPassed = none` and `humanScore = some hs`, pass iff `ht ≤ hs`. -/
theorem deriveHumanPassed_score_fallback_iff (hs ht : NNRat) :
    deriveHumanPassed (some hs) none ht = true ↔ ht ≤ hs := by
  unfold deriveHumanPassed
  exact decide_eq_true_iff

/-- Theorem 3: Derived numeric human score always lies within `[0, 1]` for unit inputs. -/
theorem deriveHumanNumeric_unit (hs : Option NNRat) (hp : Bool)
    (h : ∀ s, hs = some s → s ≤ NNRat.one) :
    NNRat.zero ≤ deriveHumanNumeric hs hp ∧ deriveHumanNumeric hs hp ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  cases hs with
  | none =>
    cases hp <;> simp [deriveHumanNumeric, NNRat.le_refl, NNRat.zero_le]
  | some s =>
    exact h s rfl

/-- Theorem 4: A sample is classified `.excluded` iff `judgeScore = none` or status is excluded. -/
theorem classifySample_excluded_iff (cfg : CalibrationConfig) (s : CalibrationSample) :
    (∃ rec, classifySample cfg s = .excluded rec) ↔
      isJudgeExcluded s.judgeScore s.judgeStatus = true := by
  unfold classifySample isJudgeExcluded
  cases hjs : s.judgeScore with
  | none =>
    simp
  | some js =>
    cases hex : s.judgeStatus.isExcluded with
    | true =>
      simp
    | false =>
      simp only [Option.isNone_some, Bool.false_or, Bool.false_eq_true, iff_false, not_exists,
        ↓reduceIte]
      intro rec
      cases h1 : (decide (cfg.passThreshold ≤ js) &&
          !deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
      | true => simp
      | false =>
        cases h2 : (!decide (cfg.passThreshold ≤ js) &&
            deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
        | true => simp
        | false =>
          cases hhs : s.humanScore with
          | none => simp
          | some hs =>
            by_cases h3 : cfg.scoreDivergenceThreshold < nnAbsDiff js hs <;> simp [h3]

/-- Theorem 5: Every non-excluded sample maps to one of the 4 valid classification cases. -/
theorem classifySample_valid_partition (cfg : CalibrationConfig) (s : CalibrationSample)
    (js : NNRat) (hjs : s.judgeScore = some js) (hne : s.judgeStatus.isExcluded = false) :
    (∃ r d, classifySample cfg s = .tooGenerous r d) ∨
    (∃ r d, classifySample cfg s = .tooHarsh r d) ∨
    (∃ r d, classifySample cfg s = .agreedDivergent r d) ∨
    (∃ r, classifySample cfg s = .agreedExact r) := by
  unfold classifySample
  simp only [hjs, hne, Bool.false_eq_true, ↓reduceIte]
  cases h1 : (decide (cfg.passThreshold ≤ js) &&
      !deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
  | true =>
    simp only [↓reduceIte]
    exact Or.inl ⟨_, _, rfl⟩
  | false =>
    simp only [Bool.false_eq_true, ↓reduceIte]
    cases h2 : (!decide (cfg.passThreshold ≤ js) &&
        deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
    | true =>
      simp only [↓reduceIte]
      exact Or.inr (Or.inl ⟨_, _, rfl⟩)
    | false =>
      simp only [Bool.false_eq_true, ↓reduceIte]
      cases hhs : s.humanScore with
      | none =>
        simp only [Bool.false_eq_true, ↓reduceIte]
        exact Or.inr (Or.inr (Or.inr ⟨_, rfl⟩))
      | some hs =>
        by_cases h3 : cfg.scoreDivergenceThreshold < nnAbsDiff js hs
        · simp only [decide_eq_true_iff.mpr h3, ↓reduceIte]
          exact Or.inr (Or.inr (Or.inl ⟨_, _, rfl⟩))
        · simp only [decide_eq_false_iff_not.mpr h3, Bool.false_eq_true, ↓reduceIte]
          exact Or.inr (Or.inr (Or.inr ⟨_, rfl⟩))

/-- Theorem 6: `SCORE_DIVERGENCE` requires pass/fail agreement, present `humanScore`, and gap `> threshold`. -/
theorem classifySample_scoreDivergence_requires_agreement_and_humanScore
    (cfg : CalibrationConfig) (s : CalibrationSample)
    (row : ValidRow) (rec : DisagreementRecord)
    (h : classifySample cfg s = .agreedDivergent row rec) :
    rec.disagreementType = .scoreDivergence ∧
    rec.judgePassed = some rec.humanPassed ∧
    ∃ hs js, s.humanScore = some hs ∧ s.judgeScore = some js ∧
      cfg.scoreDivergenceThreshold < nnAbsDiff js hs := by
  unfold classifySample at h
  cases hjs : s.judgeScore with
  | none => simp [hjs] at h
  | some js =>
    simp only [hjs] at h
    cases hex : s.judgeStatus.isExcluded with
    | true => simp [hex] at h
    | false =>
      simp only [hex, Bool.false_eq_true, ↓reduceIte] at h
      cases hgen : (decide (cfg.passThreshold ≤ js) &&
          !deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
      | true => simp [hgen] at h
      | false =>
        simp only [hgen, Bool.false_eq_true, ↓reduceIte] at h
        cases hhar : (!decide (cfg.passThreshold ≤ js) &&
            deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
        | true => simp [hhar] at h
        | false =>
          simp only [hhar, Bool.false_eq_true, ↓reduceIte] at h
          cases hhs : s.humanScore with
          | none =>
            simp [hhs] at h
          | some hs =>
            simp only [hhs] at h
            cases hdiv : decide (cfg.scoreDivergenceThreshold < nnAbsDiff js hs) with
            | false => simp [hdiv] at h
            | true =>
              simp only [hdiv, ↓reduceIte] at h
              injection h with _ hrec
              subst hrec
              have hjpEq : decide (cfg.passThreshold ≤ js) =
                  deriveHumanPassed (some hs) s.humanPassed cfg.humanThreshold := by
                rw [hhs] at hgen hhar
                cases h1 : decide (cfg.passThreshold ≤ js) <;>
                cases h2 : deriveHumanPassed (some hs) s.humanPassed cfg.humanThreshold <;>
                simp_all
              refine ⟨rfl, by simp [hjpEq], hs, js, rfl, rfl, ?_⟩
              exact decide_eq_true_iff.mp hdiv

/-- Helper extracting any `scoreDelta` emitted by a sample classification. -/
def classificationScoreDelta : SampleClassification → Option SignedRat
  | .excluded rec => rec.scoreDelta
  | .tooGenerous _ rec => rec.scoreDelta
  | .tooHarsh _ rec => rec.scoreDelta
  | .agreedDivergent _ rec => rec.scoreDelta
  | .agreedExact _ => none

/-- Theorem 7: Every emitted per-sample `scoreDelta` lies in `[-1, 1]` for unit-bounded inputs. -/
theorem classifySample_scoreDelta_unit (cfg : CalibrationConfig) (s : CalibrationSample)
    (hunit : s.scoresUnit) (d : SignedRat)
    (hd : classificationScoreDelta (classifySample cfg s) = some d) :
    d.inUnitInterval := by
  unfold classifySample at hd
  cases hjs : s.judgeScore with
  | none => simp [hjs, classificationScoreDelta] at hd
  | some js =>
    simp only [hjs] at hd
    cases hex : s.judgeStatus.isExcluded with
    | true => simp [hex, classificationScoreDelta] at hd
    | false =>
      simp only [hex, Bool.false_eq_true, ↓reduceIte] at hd
      have hjUnit : js ≤ NNRat.one := hunit.2 js hjs
      have hhUnit : deriveHumanNumeric s.humanScore
          (deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) ≤ NNRat.one :=
        (deriveHumanNumeric_unit s.humanScore _ hunit.1).2
      have hSubUnit : (SignedRat.subNNRat js (deriveHumanNumeric s.humanScore
          (deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold))).inUnitInterval :=
        SignedRat.subNNRat_inUnitInterval hjUnit hhUnit
      have hNormUnit : (SignedRat.normalize (SignedRat.subNNRat js (deriveHumanNumeric s.humanScore
          (deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold)))).inUnitInterval :=
        SignedRat.inUnitInterval_of_equiv (SignedRat.normalize_equiv _).symm hSubUnit
      cases h1 : (decide (cfg.passThreshold ≤ js) &&
          !deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
      | true =>
        simp only [h1, ↓reduceIte, classificationScoreDelta, Option.some.injEq] at hd
        exact hd ▸ hNormUnit
      | false =>
        simp only [h1, Bool.false_eq_true, ↓reduceIte] at hd
        cases h2 : (!decide (cfg.passThreshold ≤ js) &&
            deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
        | true =>
          simp only [h2, ↓reduceIte, classificationScoreDelta, Option.some.injEq] at hd
          exact hd ▸ hNormUnit
        | false =>
          simp only [h2, Bool.false_eq_true, ↓reduceIte] at hd
          cases hhs : s.humanScore with
          | none =>
            simp [hhs, classificationScoreDelta] at hd
          | some hs =>
            simp only [hhs] at hd
            cases h3 : decide (cfg.scoreDivergenceThreshold < nnAbsDiff js hs) with
            | true =>
              simp only [h3, ↓reduceIte, classificationScoreDelta, Option.some.injEq] at hd
              rw [hhs] at hNormUnit
              exact hd ▸ hNormUnit
            | false =>
              simp [h3, classificationScoreDelta] at hd

/-!
## Group B — Exact Count Conservation & Disagreement Bounds (Theorems 8–12)
-/

private theorem collectValidRows_len_add_countInconclusive (cs : List SampleClassification) :
    (collectValidRows cs).length + countInconclusive cs = cs.length := by
  induction cs with
  | nil => simp [collectValidRows, countInconclusive]
  | cons c rest ih =>
    cases c <;> simp [collectValidRows, countInconclusive] <;> omega

private theorem counts_partition_validRows (cs : List SampleClassification) :
    countAgreed cs + countTooGenerous cs + countTooHarsh cs = (collectValidRows cs).length := by
  induction cs with
  | nil => simp [collectValidRows, countAgreed, countTooGenerous, countTooHarsh]
  | cons c rest ih =>
    cases c <;> simp [collectValidRows, countAgreed, countTooGenerous, countTooHarsh] <;> omega

private theorem disagreements_len_ge (cs : List SampleClassification) :
    countInconclusive cs + countTooGenerous cs + countTooHarsh cs ≤
      (collectDisagreements cs).length := by
  induction cs with
  | nil => simp [collectDisagreements, countInconclusive, countTooGenerous, countTooHarsh]
  | cons c rest ih =>
    cases c <;>
      simp [collectDisagreements, countInconclusive, countTooGenerous, countTooHarsh] <;>
      omega

private theorem disagreements_len_le (cs : List SampleClassification) :
    (collectDisagreements cs).length ≤ cs.length := by
  induction cs with
  | nil => simp [collectDisagreements]
  | cons c rest ih =>
    cases c <;> simp [collectDisagreements] <;> omega

/-- Theorem 8: Exact total partition `validCases + inconclusiveCases = totalCases`. -/
theorem aggregateCalibration_total_partition (cfg : CalibrationConfig)
    (samples : List CalibrationSample) :
    (aggregateCalibration cfg samples).validCases +
      (aggregateCalibration cfg samples).inconclusiveCases =
      (aggregateCalibration cfg samples).totalCases := by
  unfold aggregateCalibration
  dsimp only
  have h := collectValidRows_len_add_countInconclusive (samples.map (classifySample cfg))
  rw [List.length_map] at h
  split
  · rename_i h0
    simp only
    omega
  · simp only
    exact h

/-- Theorem 9: Exact valid partition `agreedCount + tooGenerousCount + tooHarshCount = validCases`. -/
theorem aggregateCalibration_valid_partition (cfg : CalibrationConfig)
    (samples : List CalibrationSample) :
    (aggregateCalibration cfg samples).agreedCount +
      (aggregateCalibration cfg samples).tooGenerousCount +
      (aggregateCalibration cfg samples).tooHarshCount =
      (aggregateCalibration cfg samples).validCases := by
  unfold aggregateCalibration
  dsimp only
  have h := counts_partition_validRows (samples.map (classifySample cfg))
  split
  · rename_i h0
    simp only
    omega
  · simp only
    exact h

/-- Theorem 10: Disagreements lower bound `inconclusive + tooGenerous + tooHarsh ≤ disagreements.length`. -/
theorem aggregateCalibration_disagreements_lower_bound (cfg : CalibrationConfig)
    (samples : List CalibrationSample) :
    (aggregateCalibration cfg samples).inconclusiveCases +
      (aggregateCalibration cfg samples).tooGenerousCount +
      (aggregateCalibration cfg samples).tooHarshCount ≤
      (aggregateCalibration cfg samples).disagreements.length := by
  unfold aggregateCalibration
  dsimp only
  have h := disagreements_len_ge (samples.map (classifySample cfg))
  split <;> exact h

/-- Theorem 11: Disagreements upper bound `disagreements.length ≤ totalCases`. -/
theorem aggregateCalibration_disagreements_upper_bound (cfg : CalibrationConfig)
    (samples : List CalibrationSample) :
    (aggregateCalibration cfg samples).disagreements.length ≤
      (aggregateCalibration cfg samples).totalCases := by
  unfold aggregateCalibration
  dsimp only
  have h := disagreements_len_le (samples.map (classifySample cfg))
  rw [List.length_map] at h
  split <;> exact h

/-- Theorem 12: Same-verdict `SCORE_DIVERGENCE` entries never reduce `exactAgreementRate` below `100%`. -/
theorem aggregateCalibration_scoreDivergence_preserves_agreement
    (cfg : CalibrationConfig) (samples : List CalibrationSample)
    (hPos : 0 < (aggregateCalibration cfg samples).validCases)
    (hGen : (aggregateCalibration cfg samples).tooGenerousCount = 0)
    (hHar : (aggregateCalibration cfg samples).tooHarshCount = 0) :
    ∃ r, (aggregateCalibration cfg samples).exactAgreementRate = some r ∧
      r ≈ NNRat.ofNat 100 := by
  have hPart := aggregateCalibration_valid_partition cfg samples
  unfold aggregateCalibration at hPos hGen hHar hPart ⊢
  dsimp only at hPos hGen hHar hPart ⊢
  split at hPos
  · simp at hPos
  · rename_i hNe
    simp only [hNe, ↓reduceDIte] at hGen hHar hPart ⊢
    refine ⟨_, rfl, ?_⟩
    have hAgEq : countAgreed (samples.map (classifySample cfg)) =
        (collectValidRows (samples.map (classifySample cfg))).length := by omega
    apply NNRat.equiv_trans (NNRat.normalize_equiv _)
    show (countAgreed (samples.map (classifySample cfg)) * 100) * 1 =
         100 * (collectValidRows (samples.map (classifySample cfg))).length
    rw [hAgEq, Nat.mul_one, Nat.mul_comm]

/-!
## Group C — Zero-Valid-Case Guard & Summary Metric Bounds (Theorems 13–20)
-/

/-- Theorem 13: When `validCases = 0`, all 6 optional metrics are `none` and threshold is unchanged. -/
theorem aggregateCalibration_zero_valid_guard (cfg : CalibrationConfig)
    (samples : List CalibrationSample)
    (hZero : (aggregateCalibration cfg samples).validCases = 0) :
    let s := aggregateCalibration cfg samples
    s.exactAgreementRate = none ∧
    s.tooGenerousRate = none ∧
    s.tooHarshRate = none ∧
    s.meanHumanScore = none ∧
    s.meanJudgeScore = none ∧
    s.meanScoreDelta = none ∧
    s.recommendedPassThreshold ≈ cfg.passThreshold := by
  unfold aggregateCalibration at hZero ⊢
  dsimp only at hZero ⊢
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte]
    exact ⟨trivial, trivial, trivial, trivial, trivial, trivial, NNRat.normalize_equiv cfg.passThreshold⟩
  · simp only [h0, ↓reduceDIte] at hZero

/-- Theorem 14: When `0 < validCases`, all 6 optional summary metrics are `some`. -/
theorem aggregateCalibration_positive_valid_some (cfg : CalibrationConfig)
    (samples : List CalibrationSample)
    (hPos : 0 < (aggregateCalibration cfg samples).validCases) :
    let s := aggregateCalibration cfg samples
    s.exactAgreementRate.isSome = true ∧
    s.tooGenerousRate.isSome = true ∧
    s.tooHarshRate.isSome = true ∧
    s.meanHumanScore.isSome = true ∧
    s.meanJudgeScore.isSome = true ∧
    s.meanScoreDelta.isSome = true := by
  unfold aggregateCalibration at hPos ⊢
  dsimp only at hPos ⊢
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hPos
    omega
  · simp only [h0, ↓reduceDIte, Option.isSome_some, and_self]

/-- Theorem 15: `exactAgreementRate` always lies within `[0, 100]`. -/
theorem aggregateCalibration_exactAgreementRate_bounds (cfg : CalibrationConfig)
    (samples : List CalibrationSample) (r : NNRat)
    (hr : (aggregateCalibration cfg samples).exactAgreementRate = some r) :
    NNRat.zero ≤ r ∧ r ≤ NNRat.ofNat 100 := by
  have hPart := counts_partition_validRows (samples.map (classifySample cfg))
  unfold aggregateCalibration at hr
  dsimp only at hr
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hr
    nomatch hr
  · simp only [h0, ↓reduceDIte, Option.some.injEq] at hr
    subst hr
    refine ⟨NNRat.zero_le _, ?_⟩
    apply nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm
    show (countAgreed (samples.map (classifySample cfg)) * 100) * 1 ≤
         100 * (collectValidRows (samples.map (classifySample cfg))).length
    omega

/-- Theorem 16: `tooGenerousRate` and `tooHarshRate` always lie within `[0, 1]`. -/
theorem aggregateCalibration_bias_rates_bounds (cfg : CalibrationConfig)
    (samples : List CalibrationSample) (g h : NNRat)
    (hg : (aggregateCalibration cfg samples).tooGenerousRate = some g)
    (hh : (aggregateCalibration cfg samples).tooHarshRate = some h) :
    NNRat.zero ≤ g ∧ g ≤ NNRat.one ∧ NNRat.zero ≤ h ∧ h ≤ NNRat.one := by
  have hPart := counts_partition_validRows (samples.map (classifySample cfg))
  unfold aggregateCalibration at hg hh
  dsimp only at hg hh
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hg
    nomatch hg
  · simp only [h0, ↓reduceDIte, Option.some.injEq] at hg hh
    subst hg
    subst hh
    refine ⟨NNRat.zero_le _, ?_, NNRat.zero_le _, ?_⟩
    · apply nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm
      rw [NNRat.le_one_iff]
      dsimp only
      omega
    · apply nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm
      rw [NNRat.le_one_iff]
      dsimp only
      omega

/-- Theorem 17: Exact rate conservation `(agreed/valid) + (generous/valid) + (harsh/valid) = 1`. -/
theorem aggregateCalibration_rates_sum_to_one (cfg : CalibrationConfig)
    (samples : List CalibrationSample)
    (hPos : 0 < (aggregateCalibration cfg samples).validCases) :
    let s := aggregateCalibration cfg samples
    let agR : NNRat := ⟨s.agreedCount, s.validCases, hPos⟩
    let genR : NNRat := ⟨s.tooGenerousCount, s.validCases, hPos⟩
    let harR : NNRat := ⟨s.tooHarshCount, s.validCases, hPos⟩
    (agR.add genR).add harR ≈ NNRat.one := by
  have hPart := aggregateCalibration_valid_partition cfg samples
  dsimp only
  rw [NNRat.equiv_one_iff]
  let a := (aggregateCalibration cfg samples).agreedCount
  let g := (aggregateCalibration cfg samples).tooGenerousCount
  let h := (aggregateCalibration cfg samples).tooHarshCount
  let v := (aggregateCalibration cfg samples).validCases
  change ((a * v + g * v) * v + h * (v * v)) = (v * v) * v
  have hPart' : a + g + h = v := hPart
  calc
    (a * v + g * v) * v + h * (v * v)
        = ((a + g) * v) * v + h * (v * v) := by rw [← Nat.add_mul]
    _ = (a + g) * (v * v) + h * (v * v) := by rw [Nat.mul_assoc]
    _ = (a + g + h) * (v * v) := (Nat.add_mul _ _ _).symm
    _ = v * (v * v) := by rw [hPart']
    _ = (v * v) * v := (Nat.mul_assoc _ _ _).symm

private theorem classifySample_validRow_unit (cfg : CalibrationConfig) (s : CalibrationSample)
    (hsUnit : s.scoresUnit) (r : ValidRow)
    (hmem : r ∈ collectValidRows [classifySample cfg s]) :
    r.humanNumeric ≤ NNRat.one ∧ r.judgeScore ≤ NNRat.one := by
  unfold classifySample at hmem
  cases hjs : s.judgeScore with
  | none => simp [hjs, collectValidRows] at hmem
  | some js =>
    simp only [hjs] at hmem
    cases hex : s.judgeStatus.isExcluded with
    | true => simp [hex, collectValidRows] at hmem
    | false =>
      simp only [hex, Bool.false_eq_true, ↓reduceIte] at hmem
      have hPair : deriveHumanNumeric s.humanScore
          (deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) ≤ NNRat.one ∧
          js ≤ NNRat.one :=
        ⟨(deriveHumanNumeric_unit s.humanScore _ hsUnit.1).2, hsUnit.2 js hjs⟩
      cases h1 : (decide (cfg.passThreshold ≤ js) &&
          !deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
      | true =>
        simp only [h1, ↓reduceIte, collectValidRows, List.mem_singleton] at hmem
        subst hmem
        exact hPair
      | false =>
        simp only [h1, Bool.false_eq_true, ↓reduceIte] at hmem
        cases h2 : (!decide (cfg.passThreshold ≤ js) &&
            deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold) with
        | true =>
          simp only [h2, ↓reduceIte, collectValidRows, List.mem_singleton] at hmem
          subst hmem
          exact hPair
        | false =>
          simp only [h2, Bool.false_eq_true, ↓reduceIte] at hmem
          cases hhs : s.humanScore with
          | none =>
            simp only [hhs, Bool.false_eq_true, ↓reduceIte, collectValidRows, List.mem_singleton] at hmem
            subst hmem
            rw [hhs] at hPair
            exact hPair
          | some hs =>
            simp only [hhs] at hmem
            cases h3 : decide (cfg.scoreDivergenceThreshold < nnAbsDiff js hs) with
            | true =>
              simp only [h3, ↓reduceIte, collectValidRows, List.mem_singleton] at hmem
              subst hmem
              rw [hhs] at hPair
              exact hPair
            | false =>
              simp only [h3, Bool.false_eq_true, ↓reduceIte, collectValidRows, List.mem_singleton] at hmem
              subst hmem
              rw [hhs] at hPair
              exact hPair

private theorem collectValidRows_cons_append (c : SampleClassification) (cs : List SampleClassification) :
    collectValidRows (c :: cs) = collectValidRows [c] ++ collectValidRows cs := by
  cases c <;> simp [collectValidRows]

private theorem validRows_unit_of_samples_unit (cfg : CalibrationConfig)
    (samples : List CalibrationSample) (hunit : ∀ s ∈ samples, s.scoresUnit) :
    ∀ r ∈ collectValidRows (samples.map (classifySample cfg)),
      r.humanNumeric ≤ NNRat.one ∧ r.judgeScore ≤ NNRat.one := by
  induction samples with
  | nil =>
    intro r hr
    simp [collectValidRows] at hr
  | cons s rest ih =>
    intro r hr
    simp only [List.map_cons] at hr
    rw [collectValidRows_cons_append, List.mem_append] at hr
    rcases hr with hHead | hTail
    · exact classifySample_validRow_unit cfg s (hunit s List.mem_cons_self) r hHead
    · exact ih (fun x hx => hunit x (List.mem_cons_of_mem s hx)) r hTail

/-- Theorem 18: `meanHumanScore` always lies within `[0, 1]` for unit-bounded samples. -/
theorem aggregateCalibration_meanHumanScore_bounds (cfg : CalibrationConfig)
    (samples : List CalibrationSample) (hunit : ∀ s ∈ samples, s.scoresUnit)
    (m : NNRat) (hm : (aggregateCalibration cfg samples).meanHumanScore = some m) :
    NNRat.zero ≤ m ∧ m ≤ NNRat.one := by
  have hRowsUnit := validRows_unit_of_samples_unit cfg samples hunit
  unfold aggregateCalibration at hm
  dsimp only at hm
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hm
    nomatch hm
  · simp only [h0, ↓reduceDIte, Option.some.injEq] at hm
    subst hm
    refine ⟨NNRat.zero_le _, ?_⟩
    apply nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm
    apply nnMeanList_le_one
    intro x hx
    rw [List.mem_map] at hx
    rcases hx with ⟨r, hr, rfl⟩
    exact (hRowsUnit r hr).1

/-- Theorem 19: `meanJudgeScore` always lies within `[0, 1]` for unit-bounded samples. -/
theorem aggregateCalibration_meanJudgeScore_bounds (cfg : CalibrationConfig)
    (samples : List CalibrationSample) (hunit : ∀ s ∈ samples, s.scoresUnit)
    (m : NNRat) (hm : (aggregateCalibration cfg samples).meanJudgeScore = some m) :
    NNRat.zero ≤ m ∧ m ≤ NNRat.one := by
  have hRowsUnit := validRows_unit_of_samples_unit cfg samples hunit
  unfold aggregateCalibration at hm
  dsimp only at hm
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hm
    nomatch hm
  · simp only [h0, ↓reduceDIte, Option.some.injEq] at hm
    subst hm
    refine ⟨NNRat.zero_le _, ?_⟩
    apply nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm
    apply nnMeanList_le_one
    intro x hx
    rw [List.mem_map] at hx
    rcases hx with ⟨r, hr, rfl⟩
    exact (hRowsUnit r hr).2

/-- Theorem 20: `meanScoreDelta` equals `meanJudgeScore - meanHumanScore` and lies in `[-1, 1]`. -/
theorem aggregateCalibration_meanScoreDelta_bounds_and_identity
    (cfg : CalibrationConfig) (samples : List CalibrationSample)
    (hunit : ∀ s ∈ samples, s.scoresUnit)
    (mh mj : NNRat) (md : SignedRat)
    (hmh : (aggregateCalibration cfg samples).meanHumanScore = some mh)
    (hmj : (aggregateCalibration cfg samples).meanJudgeScore = some mj)
    (hmd : (aggregateCalibration cfg samples).meanScoreDelta = some md) :
    md ≈ₛ SignedRat.subNNRat mj mh ∧ md.inUnitInterval := by
  have hmhBound := (aggregateCalibration_meanHumanScore_bounds cfg samples hunit mh hmh).2
  have hmjBound := (aggregateCalibration_meanJudgeScore_bounds cfg samples hunit mj hmj).2
  unfold aggregateCalibration at hmh hmj hmd
  dsimp only at hmh hmj hmd
  by_cases h0 : (collectValidRows (samples.map (classifySample cfg))).length = 0
  · simp only [h0, ↓reduceDIte] at hmh
    nomatch hmh
  · simp only [h0, ↓reduceDIte, Option.some.injEq] at hmh hmj hmd
    have hPos : 0 < (collectValidRows (samples.map (classifySample cfg))).length :=
      Nat.pos_of_ne_zero h0
    let mhRaw := nnMeanList ((collectValidRows (samples.map (classifySample cfg))).map (·.humanNumeric))
      (by simpa using hPos)
    let mjRaw := nnMeanList ((collectValidRows (samples.map (classifySample cfg))).map (·.judgeScore))
      (by simpa using hPos)
    have hmhEq' : NNRat.normalize mhRaw = mh := hmh
    have hmjEq' : NNRat.normalize mjRaw = mj := hmj
    have hmdEq' : SignedRat.normalize (SignedRat.subNNRat mjRaw mhRaw) = md := hmd
    have hEq : md ≈ₛ SignedRat.subNNRat mj mh := by
      rw [← hmdEq', ← hmjEq', ← hmhEq']
      exact SignedRat.equiv_trans (SignedRat.normalize_equiv (SignedRat.subNNRat mjRaw mhRaw))
        (SignedRat.subNNRat_equiv_congr
          (NNRat.normalize_equiv mjRaw).symm
          (NNRat.normalize_equiv mhRaw).symm)
    have hUnit : (SignedRat.subNNRat mj mh).inUnitInterval :=
      SignedRat.subNNRat_inUnitInterval hmjBound hmhBound
    exact ⟨hEq, SignedRat.inUnitInterval_of_equiv hEq.symm hUnit⟩

/-!
## Group D — Candidate Grid, Monotonicity, Optimality, Tie-Breaking & Invariance (Theorems 21–32)
-/

/-- Predicate asserting every element of a list is in canonical `NNRat.normalize` form. -/
private def AllNormalized (xs : List NNRat) : Prop :=
  ∀ a ∈ xs, NNRat.normalize a = a

private theorem insertUnique_props (x : NNRat) (xs : List NNRat)
    (hNorm : AllNormalized xs) (hPair : List.Pairwise (· < ·) xs) :
    AllNormalized (insertUnique x xs) ∧
    List.Pairwise (· < ·) (insertUnique x xs) ∧
    (∀ z, z ∈ insertUnique x xs ↔ z = NNRat.normalize x ∨ z ∈ xs) := by
  induction xs generalizing x with
  | nil =>
    refine ⟨?_, ?_, ?_⟩
    · intro a ha
      simp only [insertUnique, List.mem_singleton] at ha
      subst ha
      exact nnrat_normalize_idempotent x
    · simp [insertUnique]
    · intro z
      simp [insertUnique]
  | cons y ys ih =>
    have hyNorm : NNRat.normalize y = y := hNorm y (by simp)
    have hysNorm : AllNormalized ys := fun a ha => hNorm a (by simp [ha])
    have hPair' := List.pairwise_cons.mp hPair
    have hyLt : ∀ u ∈ ys, y < u := hPair'.1
    have hysPair : List.Pairwise (· < ·) ys := hPair'.2
    unfold insertUnique
    dsimp only
    by_cases h1 : NNRat.normalize x < y
    · simp only [h1, ↓reduceIte]
      refine ⟨?_, ?_, ?_⟩
      · intro a ha
        simp only [List.mem_cons] at ha
        rcases ha with rfl | rfl | hmem
        · exact nnrat_normalize_idempotent x
        · exact hyNorm
        · exact hysNorm a hmem
      · refine List.pairwise_cons.mpr ⟨?_, hPair⟩
        intro u hu
        simp only [List.mem_cons] at hu
        rcases hu with rfl | hmem
        · exact h1
        · exact (NNRat.lt_iff_not_le _ _).mpr (fun hle =>
            (NNRat.lt_iff_not_le _ _).mp h1 (NNRat.le_trans (NNRat.le_of_lt (hyLt u hmem)) hle))
      · intro z
        constructor
        · intro hz
          simp only [List.mem_cons] at hz
          rcases hz with rfl | hmem
          · exact Or.inl rfl
          · exact Or.inr (List.mem_cons.mpr hmem)
        · intro hz
          rcases hz with rfl | hmem
          · exact List.mem_cons_self
          · exact List.mem_cons_of_mem _ hmem
    · simp only [h1, ↓reduceIte]
      by_cases h2 : y < NNRat.normalize x
      · simp only [h2, ↓reduceIte]
        have hSub := ih (NNRat.normalize x) hysNorm hysPair
        rcases hSub with ⟨hSubNorm, hSubPair, hSubMem⟩
        have hNormNx : NNRat.normalize (NNRat.normalize x) = NNRat.normalize x :=
          nnrat_normalize_idempotent x
        refine ⟨?_, ?_, ?_⟩
        · intro a ha
          simp only [List.mem_cons] at ha
          rcases ha with rfl | hmem
          · exact hyNorm
          · exact hSubNorm a hmem
        · refine List.pairwise_cons.mpr ⟨?_, hSubPair⟩
          intro u hu
          rcases (hSubMem u).mp hu with rfl | hmem
          · rw [hNormNx]; exact h2
          · exact hyLt u hmem
        · intro z
          constructor
          · intro hz
            simp only [List.mem_cons] at hz
            rcases hz with rfl | hmem
            · exact Or.inr List.mem_cons_self
            · rcases (hSubMem z).mp hmem with rfl | hys
              · exact Or.inl hNormNx
              · exact Or.inr (List.mem_cons_of_mem y hys)
          · intro hz
            rcases hz with rfl | hmem
            · exact List.mem_cons_of_mem y ((hSubMem (NNRat.normalize x)).mpr (Or.inl hNormNx.symm))
            · simp only [List.mem_cons] at hmem
              rcases hmem with rfl | hys
              · exact List.mem_cons_self
              · exact List.mem_cons_of_mem y ((hSubMem z).mpr (Or.inr hys))
      · simp only [h2, ↓reduceIte]
        have hEqv : NNRat.normalize x ≈ y := by
          have hle1 : y ≤ NNRat.normalize x := by
            rw [NNRat.lt_iff_not_le] at h1
            exact Classical.byContradiction (fun hc => h1 hc)
          have hle2 : NNRat.normalize x ≤ y := by
            rw [NNRat.lt_iff_not_le] at h2
            exact Classical.byContradiction (fun hc => h2 hc)
          exact NNRat.equiv_of_le_antisymm hle2 hle1
        have hEq : NNRat.normalize x = y := by
          have hN := nnrat_normalize_eq_of_equiv hEqv
          rw [nnrat_normalize_idempotent, hyNorm] at hN
          exact hN
        refine ⟨hNorm, hPair, ?_⟩
        intro z
        constructor
        · intro hz; exact Or.inr hz
        · intro hz
          rcases hz with rfl | hmem
          · rw [hEq]; exact List.mem_cons_self
          · exact hmem

private theorem sortUnique_props (xs : List NNRat) :
    AllNormalized (sortUnique xs) ∧
    List.Pairwise (· < ·) (sortUnique xs) ∧
    (∀ z, z ∈ sortUnique xs ↔ ∃ x ∈ xs, z = NNRat.normalize x) := by
  induction xs with
  | nil =>
    refine ⟨?_, ?_, ?_⟩
    · intro a ha; simp [sortUnique] at ha
    · simp [sortUnique]
    · intro z; simp [sortUnique]
  | cons x rest ih =>
    rcases ih with ⟨hNorm, hPair, hMem⟩
    have hIns := insertUnique_props x (sortUnique rest) hNorm hPair
    rcases hIns with ⟨hINorm, hIPair, hIMem⟩
    refine ⟨hINorm, hIPair, ?_⟩
    intro z
    rw [sortUnique, hIMem, hMem]
    constructor
    · intro h
      rcases h with hz | ⟨y, hy, hz⟩
      · exact ⟨x, List.mem_cons_self, hz⟩
      · exact ⟨y, List.mem_cons_of_mem x hy, hz⟩
    · intro ⟨y, hy, hz⟩
      simp only [List.mem_cons] at hy
      rcases hy with rfl | hrest
      · exact Or.inl hz
      · exact Or.inr ⟨y, hrest, hz⟩

private theorem pairwise_lt_eq_of_mem_iff {xs ys : List NNRat}
    (hNormX : AllNormalized xs) (hNormY : AllNormalized ys)
    (hPairX : List.Pairwise (· < ·) xs) (hPairY : List.Pairwise (· < ·) ys)
    (hMem : ∀ z, z ∈ xs ↔ z ∈ ys) :
    xs = ys := by
  induction xs generalizing ys with
  | nil =>
    cases ys with
    | nil => rfl
    | cons y _ =>
      have := (hMem y).mpr List.mem_cons_self
      simp at this
  | cons x xt ih =>
    cases ys with
    | nil =>
      have := (hMem x).mp List.mem_cons_self
      simp at this
    | cons y yt =>
      have hPX := List.pairwise_cons.mp hPairX
      have hPY := List.pairwise_cons.mp hPairY
      have hxInY : x ∈ y :: yt := (hMem x).mp List.mem_cons_self
      have hyInX : y ∈ x :: xt := (hMem y).mpr List.mem_cons_self
      have hxy : x = y := by
        simp only [List.mem_cons] at hxInY hyInX
        rcases hxInY with rfl | hxTail
        · rfl
        · rcases hyInX with rfl | hyTail
          · rfl
          · have h1 : y < x := hPY.1 x hxTail
            have h2 : x < y := hPX.1 y hyTail
            exact absurd (NNRat.le_of_lt h1) ((NNRat.lt_iff_not_le x y).mp h2)
      subst hxy
      congr 1
      apply ih
      · exact fun a ha => hNormX a (List.mem_cons_of_mem x ha)
      · exact fun a ha => hNormY a (List.mem_cons_of_mem x ha)
      · exact hPX.2
      · exact hPY.2
      · intro z
        constructor
        · intro hz
          have hIn : z ∈ x :: yt := (hMem z).mp (List.mem_cons_of_mem x hz)
          simp only [List.mem_cons] at hIn
          rcases hIn with rfl | hyt
          · have hlt : z < z := hPX.1 z hz
            exact absurd (NNRat.le_refl z) ((NNRat.lt_iff_not_le z z).mp hlt)
          · exact hyt
        · intro hz
          have hIn : z ∈ x :: xt := (hMem z).mpr (List.mem_cons_of_mem x hz)
          simp only [List.mem_cons] at hIn
          rcases hIn with rfl | hxt
          · have hlt : z < z := hPY.1 z hz
            exact absurd (NNRat.le_refl z) ((NNRat.lt_iff_not_le z z).mp hlt)
          · exact hxt

private theorem sortUnique_perm_eq {xs ys : List NNRat} (hp : List.Perm xs ys) :
    sortUnique xs = sortUnique ys := by
  have hx := sortUnique_props xs
  have hy := sortUnique_props ys
  apply pairwise_lt_eq_of_mem_iff hx.1 hy.1 hx.2.1 hy.2.1
  intro z
  rw [hx.2.2, hy.2.2]
  constructor
  · intro ⟨a, ha, hz⟩; exact ⟨a, hp.subset ha, hz⟩
  · intro ⟨a, ha, hz⟩; exact ⟨a, hp.symm.subset ha, hz⟩

private theorem adjacentMidpoints_unit (xs : List NNRat) (hunit : ∀ x ∈ xs, x ≤ NNRat.one) :
    ∀ m ∈ adjacentMidpoints xs, m ≤ NNRat.one := by
  match xs with
  | [] => intro m hm; simp [adjacentMidpoints] at hm
  | [_] => intro m hm; simp [adjacentMidpoints] at hm
  | a :: b :: rest =>
    intro m hm
    simp only [adjacentMidpoints, List.mem_cons] at hm
    rcases hm with rfl | htail
    · have ha : a ≤ NNRat.one := hunit a (by simp)
      have hb : b ≤ NNRat.one := hunit b (by simp)
      exact nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm (nnMidpoint_unit ha hb)
    · exact adjacentMidpoints_unit (b :: rest) (fun x hx => hunit x (by simp [hx])) m htail

private theorem adjacentMidpoints_normalized :
    ∀ (xs : List NNRat) (z : NNRat), z ∈ adjacentMidpoints xs → NNRat.normalize z = z
  | [], _, hz => by simp [adjacentMidpoints] at hz
  | [_], _, hz => by simp [adjacentMidpoints] at hz
  | a :: b :: rest, z, hz => by
    simp only [adjacentMidpoints, List.mem_cons] at hz
    rcases hz with rfl | htail
    · exact nnrat_normalize_idempotent _
    · exact adjacentMidpoints_normalized (b :: rest) z htail

/-- Theorem 21: Empty `valid_rows` immediately returns normalized `activeThreshold`. -/
theorem optimizePassThreshold_empty_fallback (activeThreshold : NNRat) :
    optimizePassThreshold [] activeThreshold = NNRat.normalize activeThreshold := by
  simp [optimizePassThreshold]

/-- Theorem 22: `buildCandidates` is non-empty, strictly ascending (`Nodup`), containing `0`, `active`, `1`. -/
theorem buildCandidates_nonempty_and_strictly_sorted (rows : List ValidRow) (activeThreshold : NNRat) :
    let cands := buildCandidates rows activeThreshold
    cands ≠ [] ∧
    List.Pairwise (· < ·) cands ∧
    cands.Nodup ∧
    NNRat.normalize NNRat.zero ∈ cands ∧
    NNRat.normalize activeThreshold ∈ cands ∧
    NNRat.normalize NNRat.one ∈ cands := by
  unfold buildCandidates
  dsimp only
  let raw : List NNRat :=
    [NNRat.zero, activeThreshold, NNRat.one] ++
    sortUnique (rows.map (·.judgeScore)) ++
    adjacentMidpoints (sortUnique (rows.map (·.judgeScore)))
  have hP := sortUnique_props raw
  have hZero : NNRat.normalize NNRat.zero ∈ sortUnique raw :=
    (hP.2.2 _).mpr ⟨NNRat.zero, by simp [raw], rfl⟩
  have hAct : NNRat.normalize activeThreshold ∈ sortUnique raw :=
    (hP.2.2 _).mpr ⟨activeThreshold, by simp [raw], rfl⟩
  have hOne : NNRat.normalize NNRat.one ∈ sortUnique raw :=
    (hP.2.2 _).mpr ⟨NNRat.one, by simp [raw], rfl⟩
  have hNe : sortUnique raw ≠ [] := by
    intro hemp
    rw [hemp] at hZero
    simp at hZero
  have hNodup : (sortUnique raw).Nodup :=
    hP.2.1.imp (fun {a b} hab heq => by
      subst heq
      exact (NNRat.lt_iff_not_le a a).mp hab (NNRat.le_refl a))
  exact ⟨hNe, hP.2.1, hNodup, hZero, hAct, hOne⟩

/-- Theorem 23: Every generated candidate threshold lies within `[0, 1]` for unit-bounded inputs. -/
theorem buildCandidates_unit_closed (rows : List ValidRow) (activeThreshold : NNRat)
    (hAct : activeThreshold ≤ NNRat.one)
    (hRows : ∀ r ∈ rows, r.judgeScore ≤ NNRat.one) :
    ∀ c ∈ buildCandidates rows activeThreshold, NNRat.zero ≤ c ∧ c ≤ NNRat.one := by
  unfold buildCandidates
  dsimp only
  intro c hc
  refine ⟨NNRat.zero_le c, ?_⟩
  let uScores := sortUnique (rows.map (·.judgeScore))
  let raw : List NNRat := [NNRat.zero, activeThreshold, NNRat.one] ++ uScores ++ adjacentMidpoints uScores
  have hU := sortUnique_props (rows.map (·.judgeScore))
  have hUniqueUnit : ∀ u ∈ uScores, u ≤ NNRat.one := by
    intro u hu
    rcases (hU.2.2 u).mp hu with ⟨x, hx, rfl⟩
    rw [List.mem_map] at hx
    rcases hx with ⟨r, hr, rfl⟩
    exact nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm (hRows r hr)
  have hMidUnit : ∀ m ∈ adjacentMidpoints uScores, m ≤ NNRat.one :=
    adjacentMidpoints_unit uScores hUniqueUnit
  have hC := sortUnique_props raw
  rcases (hC.2.2 c).mp hc with ⟨x, hx, rfl⟩
  apply nnrat_le_of_equiv_left (NNRat.normalize_equiv x).symm
  simp only [raw, List.mem_append, List.mem_cons, List.not_mem_nil, or_false] at hx
  rcases hx with ((rfl | rfl | rfl) | hu) | hm
  · exact NNRat.zero_le NNRat.one
  · exact hAct
  · exact NNRat.le_refl NNRat.one
  · exact hUniqueUnit x hu
  · exact hMidUnit x hm

/-- Theorem 24: `buildCandidates` contains every normalized judge score and adjacent midpoint. -/
theorem buildCandidates_contains_scores_and_midpoints (rows : List ValidRow)
    (activeThreshold : NNRat) :
    (∀ r ∈ rows, NNRat.normalize r.judgeScore ∈ buildCandidates rows activeThreshold) ∧
    (∀ m ∈ adjacentMidpoints (sortUnique (rows.map (·.judgeScore))),
      m ∈ buildCandidates rows activeThreshold) := by
  unfold buildCandidates
  dsimp only
  let uScores := sortUnique (rows.map (·.judgeScore))
  let raw : List NNRat := [NNRat.zero, activeThreshold, NNRat.one] ++ uScores ++ adjacentMidpoints uScores
  have hU := sortUnique_props (rows.map (·.judgeScore))
  have hC := sortUnique_props raw
  constructor
  · intro r hr
    have huMem : NNRat.normalize r.judgeScore ∈ uScores :=
      (hU.2.2 _).mpr ⟨r.judgeScore, List.mem_map.mpr ⟨r, hr, rfl⟩, rfl⟩
    exact (hC.2.2 _).mpr ⟨NNRat.normalize r.judgeScore, by simp [raw, huMem],
      (nnrat_normalize_idempotent r.judgeScore).symm⟩
  · intro m hm
    have hmNorm : NNRat.normalize m = m := adjacentMidpoints_normalized uScores m hm
    exact (hC.2.2 m).mpr ⟨m, List.mem_append_right _ hm, hmNorm.symm⟩

/-- Theorem 25: For any threshold `t`, `agree + generous + harsh = rows.length`. -/
theorem evalCountsAt_partition (rows : List ValidRow) (t : NNRat) :
    let (ag, gen, har) := evalCountsAt rows t
    ag + gen + har = rows.length := by
  induction rows with
  | nil => simp [evalCountsAt]
  | cons r rs ih =>
    simp only [evalCountsAt]
    cases h : evalCountsAt rs t with
    | mk ag p =>
      cases p with
      | mk gen har =>
        rw [h] at ih
        dsimp only at ih ⊢
        split
        · simp only [List.length_cons]; omega
        · split <;> simp only [List.length_cons] <;> omega

/-- Theorem 26: Raising the threshold never increases `generous` counts (antitone in `t`). -/
theorem evalCountsAt_generous_antitone (rows : List ValidRow) {t₁ t₂ : NNRat} (h : t₁ ≤ t₂) :
    (evalCountsAt rows t₂).2.1 ≤ (evalCountsAt rows t₁).2.1 := by
  induction rows with
  | nil => simp [evalCountsAt]
  | cons r rs ih =>
    simp only [evalCountsAt]
    cases h1 : evalCountsAt rs t₁ with
    | mk ag1 p1 =>
      cases p1 with
      | mk gen1 har1 =>
        cases h2 : evalCountsAt rs t₂ with
        | mk ag2 p2 =>
          cases p2 with
          | mk gen2 har2 =>
            rw [h1, h2] at ih
            dsimp only at ih ⊢
            have hImp : decide (t₂ ≤ r.judgeScore) = true → decide (t₁ ≤ r.judgeScore) = true := by
              intro ht2
              exact decide_eq_true_iff.mpr (NNRat.le_trans h (decide_eq_true_iff.mp ht2))
            cases hp1 : decide (t₁ ≤ r.judgeScore) <;>
            cases hp2 : decide (t₂ ≤ r.judgeScore) <;>
            cases hr : r.humanPassed <;>
            simp_all <;> omega

/-- Theorem 27: Raising the threshold never decreases `harsh` counts (monotone in `t`). -/
theorem evalCountsAt_harsh_monotone (rows : List ValidRow) {t₁ t₂ : NNRat} (h : t₁ ≤ t₂) :
    (evalCountsAt rows t₁).2.2 ≤ (evalCountsAt rows t₂).2.2 := by
  induction rows with
  | nil => simp [evalCountsAt]
  | cons r rs ih =>
    simp only [evalCountsAt]
    cases h1 : evalCountsAt rs t₁ with
    | mk ag1 p1 =>
      cases p1 with
      | mk gen1 har1 =>
        cases h2 : evalCountsAt rs t₂ with
        | mk ag2 p2 =>
          cases p2 with
          | mk gen2 har2 =>
            rw [h1, h2] at ih
            dsimp only at ih ⊢
            have hImp : decide (t₂ ≤ r.judgeScore) = true → decide (t₁ ≤ r.judgeScore) = true := by
              intro ht2
              exact decide_eq_true_iff.mpr (NNRat.le_trans h (decide_eq_true_iff.mp ht2))
            cases hp1 : decide (t₁ ≤ r.judgeScore) <;>
            cases hp2 : decide (t₂ ≤ r.judgeScore) <;>
            cases hr : r.humanPassed <;>
            simp_all <;> omega

private theorem evalCountsAt_equiv_congr (rows : List ValidRow) {t₁ t₂ : NNRat} (h : t₁ ≈ t₂) :
    evalCountsAt rows t₁ = evalCountsAt rows t₂ := by
  induction rows with
  | nil => rfl
  | cons r rs ih =>
    have hDec : decide (t₁ ≤ r.judgeScore) = decide (t₂ ≤ r.judgeScore) := by
      apply Bool.eq_iff_iff.mpr
      simp only [decide_eq_true_iff]
      exact ⟨nnrat_le_of_equiv_left h, nnrat_le_of_equiv_left h.symm⟩
    simp [evalCountsAt, ih, hDec]

private theorem evalCountsAt_perm {rows₁ rows₂ : List ValidRow} (hp : List.Perm rows₁ rows₂)
    (t : NNRat) :
    evalCountsAt rows₁ t = evalCountsAt rows₂ t := by
  induction hp with
  | nil => rfl
  | cons r _ ih => simp [evalCountsAt, ih]
  | swap x y l =>
    simp only [evalCountsAt]
    cases evalCountsAt l t with
    | mk ag p =>
      cases p with
      | mk gen har =>
        cases decide (t ≤ x.judgeScore) <;> cases x.humanPassed <;>
        cases decide (t ≤ y.judgeScore) <;> cases y.humanPassed <;>
        simp [Nat.add_comm]
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

private theorem foldl_max_ge (xs : List CandidateEval) (init : Nat) :
    init ≤ xs.foldl (fun acc c => Nat.max acc c.agree) init ∧
    ∀ c ∈ xs, c.agree ≤ xs.foldl (fun acc c => Nat.max acc c.agree) init := by
  induction xs generalizing init with
  | nil => simp
  | cons x rest ih =>
    simp only [List.foldl_cons]
    have h := ih (Nat.max init x.agree)
    refine ⟨Nat.le_trans (Nat.le_max_left _ _) h.1, ?_⟩
    intro c hc
    simp only [List.mem_cons] at hc
    rcases hc with rfl | hmem
    · exact Nat.le_trans (Nat.le_max_right _ _) h.1
    · exact h.2 c hmem

private theorem foldl_max_attained (xs : List CandidateEval) (init : Nat) :
    xs.foldl (fun acc c => Nat.max acc c.agree) init = init ∨
    ∃ c ∈ xs, c.agree = xs.foldl (fun acc c => Nat.max acc c.agree) init := by
  induction xs generalizing init with
  | nil => exact Or.inl rfl
  | cons x rest ih =>
    simp only [List.foldl_cons]
    cases ih (Nat.max init x.agree) with
    | inl hEq =>
      by_cases hle : init ≤ x.agree
      · have hmax : Nat.max init x.agree = x.agree := Nat.max_eq_right hle
        exact Or.inr ⟨x, List.mem_cons_self, (hEq.trans hmax).symm⟩
      · have hmax : Nat.max init x.agree = init := Nat.max_eq_left (by omega)
        exact Or.inl (hEq.trans hmax)
    | inr hEx =>
      rcases hEx with ⟨c, hc, heq⟩
      exact Or.inr ⟨c, List.mem_cons_of_mem x hc, heq⟩

private theorem maxAgreeOf_spec (xs : List CandidateEval) (hne : xs ≠ []) :
    (∀ c ∈ xs, c.agree ≤ maxAgreeOf xs) ∧
    (∃ c ∈ xs, c.agree = maxAgreeOf xs) := by
  refine ⟨(foldl_max_ge xs 0).2, ?_⟩
  cases xs with
  | nil => exact absurd rfl hne
  | cons x rest =>
    cases foldl_max_attained (x :: rest) 0 with
    | inl h0 =>
      have hxLe : x.agree ≤ maxAgreeOf (x :: rest) := (foldl_max_ge (x :: rest) 0).2 x List.mem_cons_self
      exact ⟨x, List.mem_cons_self, by unfold maxAgreeOf at hxLe ⊢; omega⟩
    | inr hEx => exact hEx

private theorem foldl_min_skew_le (xs : List CandidateEval) (init : Nat) :
    xs.foldl (fun acc c => Nat.min acc c.biasSkew) init ≤ init ∧
    ∀ c ∈ xs, xs.foldl (fun acc c => Nat.min acc c.biasSkew) init ≤ c.biasSkew := by
  induction xs generalizing init with
  | nil => simp
  | cons x rest ih =>
    simp only [List.foldl_cons]
    have h := ih (Nat.min init x.biasSkew)
    refine ⟨Nat.le_trans h.1 (Nat.min_le_left _ _), ?_⟩
    intro c hc
    simp only [List.mem_cons] at hc
    rcases hc with rfl | hmem
    · exact Nat.le_trans h.1 (Nat.min_le_right _ _)
    · exact h.2 c hmem

private theorem foldl_min_skew_attained (xs : List CandidateEval) (init : Nat) :
    xs.foldl (fun acc c => Nat.min acc c.biasSkew) init = init ∨
    ∃ c ∈ xs, c.biasSkew = xs.foldl (fun acc c => Nat.min acc c.biasSkew) init := by
  induction xs generalizing init with
  | nil => exact Or.inl rfl
  | cons x rest ih =>
    simp only [List.foldl_cons]
    cases ih (Nat.min init x.biasSkew) with
    | inl hEq =>
      by_cases hle : init ≤ x.biasSkew
      · exact Or.inl (hEq.trans (Nat.min_eq_left hle))
      · exact Or.inr ⟨x, List.mem_cons_self, (hEq.trans (Nat.min_eq_right (by omega))).symm⟩
    | inr hEx =>
      rcases hEx with ⟨c, hc, heq⟩
      exact Or.inr ⟨c, List.mem_cons_of_mem x hc, heq⟩

private theorem minBiasSkewOf_spec (xs : List CandidateEval) (hne : xs ≠ []) :
    (∀ c ∈ xs, minBiasSkewOf xs ≤ c.biasSkew) ∧
    (∃ c ∈ xs, c.biasSkew = minBiasSkewOf xs) := by
  cases xs with
  | nil => exact absurd rfl hne
  | cons x rest =>
    unfold minBiasSkewOf
    dsimp only
    have hLe := foldl_min_skew_le rest x.biasSkew
    refine ⟨?_, ?_⟩
    · intro c hc
      simp only [List.mem_cons] at hc
      rcases hc with rfl | hmem
      · exact hLe.1
      · exact hLe.2 c hmem
    · cases foldl_min_skew_attained rest x.biasSkew with
      | inl hEq => exact ⟨x, List.mem_cons_self, hEq.symm⟩
      | inr hEx =>
        rcases hEx with ⟨c, hc, heq⟩
        exact ⟨c, List.mem_cons_of_mem x hc, heq⟩

private theorem foldl_min_dist_le (xs : List CandidateEval) (init : NNRat) :
    xs.foldl (fun acc x => if x.dist ≤ acc then x.dist else acc) init ≤ init ∧
    ∀ c ∈ xs, xs.foldl (fun acc x => if x.dist ≤ acc then x.dist else acc) init ≤ c.dist := by
  induction xs generalizing init with
  | nil => exact ⟨NNRat.le_refl _, fun _ h => by simp at h⟩
  | cons x rest ih =>
    simp only [List.foldl_cons]
    by_cases hle : x.dist ≤ init
    · simp only [hle, ↓reduceIte]
      have h := ih x.dist
      refine ⟨NNRat.le_trans h.1 hle, ?_⟩
      intro c hc
      simp only [List.mem_cons] at hc
      rcases hc with rfl | hmem
      · exact h.1
      · exact h.2 c hmem
    · simp only [hle, ↓reduceIte]
      have hlt : init ≤ x.dist := NNRat.le_of_lt ((NNRat.lt_iff_not_le init x.dist).mpr hle)
      have h := ih init
      refine ⟨h.1, ?_⟩
      intro c hc
      simp only [List.mem_cons] at hc
      rcases hc with rfl | hmem
      · exact NNRat.le_trans h.1 hlt
      · exact h.2 c hmem

private theorem foldl_min_dist_attained (xs : List CandidateEval) (init : NNRat) :
    xs.foldl (fun acc x => if x.dist ≤ acc then x.dist else acc) init = init ∨
    ∃ c ∈ xs, c.dist = xs.foldl (fun acc x => if x.dist ≤ acc then x.dist else acc) init := by
  induction xs generalizing init with
  | nil => exact Or.inl rfl
  | cons x rest ih =>
    simp only [List.foldl_cons]
    by_cases hle : x.dist ≤ init
    · simp only [hle, ↓reduceIte]
      cases ih x.dist with
      | inl hEq => exact Or.inr ⟨x, List.mem_cons_self, hEq.symm⟩
      | inr hEx =>
        rcases hEx with ⟨c, hc, heq⟩
        exact Or.inr ⟨c, List.mem_cons_of_mem x hc, heq⟩
    · simp only [hle, ↓reduceIte]
      cases ih init with
      | inl hEq => exact Or.inl hEq
      | inr hEx =>
        rcases hEx with ⟨c, hc, heq⟩
        exact Or.inr ⟨c, List.mem_cons_of_mem x hc, heq⟩

private theorem minDistOf_spec (xs : List CandidateEval) (hne : xs ≠ []) :
    (∀ c ∈ xs, minDistOf xs ≤ c.dist) ∧
    (∃ c ∈ xs, c.dist ≈ minDistOf xs) := by
  cases xs with
  | nil => exact absurd rfl hne
  | cons x rest =>
    unfold minDistOf
    dsimp only
    have hLe := foldl_min_dist_le rest x.dist
    refine ⟨?_, ?_⟩
    · intro c hc
      simp only [List.mem_cons] at hc
      rcases hc with rfl | hmem
      · exact hLe.1
      · exact hLe.2 c hmem
    · cases foldl_min_dist_attained rest x.dist with
      | inl hEq => exact ⟨x, List.mem_cons_self, by rw [hEq]; exact NNRat.equiv_refl _⟩
      | inr hEx =>
        rcases hEx with ⟨c, hc, heq⟩
        exact ⟨c, List.mem_cons_of_mem x hc, by rw [heq]; exact NNRat.equiv_refl _⟩

private theorem lastOf_mem {α : Type} : ∀ (xs : List α) (hne : xs ≠ []), lastOf xs hne ∈ xs
  | [_], _ => List.mem_cons_self
  | _ :: y :: ys, _ => List.mem_cons_of_mem _ (lastOf_mem (y :: ys) (List.cons_ne_nil y ys))

private theorem pairwise_filter_map_threshold {xs : List NNRat} {f : NNRat → CandidateEval}
    {p : CandidateEval → Bool}
    (hPair : List.Pairwise (· < ·) xs)
    (hf : ∀ x, (f x).threshold = x) :
    List.Pairwise (· < ·) (((xs.map f).filter p).map (·.threshold)) := by
  induction xs with
  | nil => simp
  | cons x rest ih =>
    have hP := List.pairwise_cons.mp hPair
    simp only [List.map_cons, List.filter_cons]
    by_cases hp : p (f x) = true
    · simp only [hp, ↓reduceIte, List.map_cons]
      refine List.pairwise_cons.mpr ⟨?_, ih hP.2⟩
      intro u hu
      rw [List.mem_map] at hu
      rcases hu with ⟨ce, hce, rfl⟩
      rw [List.mem_filter, List.mem_map] at hce
      rcases hce.1 with ⟨y, hy, rfl⟩
      rw [hf x, hf y]
      exact hP.1 y hy
    · simp only [hp, Bool.false_eq_true, ↓reduceIte]
      exact ih hP.2

/-- Theorem 28: `optimizePassThreshold` always produces a threshold in `[0, 1]` for unit inputs. -/
theorem optimizePassThreshold_unit_bounds (rows : List ValidRow) (activeThreshold : NNRat)
    (hAct : activeThreshold ≤ NNRat.one)
    (hRows : ∀ r ∈ rows, r.judgeScore ≤ NNRat.one) :
    NNRat.zero ≤ optimizePassThreshold rows activeThreshold ∧
    optimizePassThreshold rows activeThreshold ≤ NNRat.one := by
  refine ⟨NNRat.zero_le _, ?_⟩
  unfold optimizePassThreshold
  split
  · exact nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm hAct
  · dsimp only
    have hCandUnit := buildCandidates_unit_closed rows activeThreshold hAct hRows
    let cands := buildCandidates rows activeThreshold
    let scored := cands.map (scoreCandidate rows activeThreshold)
    let maxAg := maxAgreeOf scored
    let bestAgree := scored.filter (fun c => c.agree == maxAg)
    let minSkew := minBiasSkewOf bestAgree
    let bestBias := bestAgree.filter (fun c => c.biasSkew == minSkew)
    let minD := minDistOf bestBias
    let winners := (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
    have hWinUnit : ∀ w ∈ winners, w ≤ NNRat.one := by
      intro w hw
      rw [List.mem_map] at hw
      rcases hw with ⟨ce, hce, rfl⟩
      rw [List.mem_filter, List.mem_filter, List.mem_filter, List.mem_map] at hce
      rcases hce.1.1.1 with ⟨c, hc, rfl⟩
      exact (hCandUnit c hc).2
    split
    · exact nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm hAct
    · rename_i w heq
      have hw : w ∈ winners := by
        show w ∈ (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
        rw [heq]
        exact List.mem_cons_self
      exact hWinUnit w hw
    · rename_i wFirst wSecond wRest heq
      have hFMem : wFirst ∈ winners := by
        show wFirst ∈ (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
        rw [heq]
        exact List.mem_cons_self
      have hLMem : lastOf (wSecond :: wRest) (List.cons_ne_nil wSecond wRest) ∈ winners := by
        show lastOf (wSecond :: wRest) (List.cons_ne_nil wSecond wRest) ∈
          (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
        rw [heq]
        exact List.mem_cons_of_mem _ (lastOf_mem _ _)
      have hF : wFirst ≤ NNRat.one := hWinUnit wFirst hFMem
      have hL : lastOf (wSecond :: wRest) (List.cons_ne_nil wSecond wRest) ≤ NNRat.one :=
        hWinUnit _ hLMem
      split
      · exact nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm (nnMidpoint_unit hF hL)
      · exact hL

/--
Theorem 29: For non-empty `rows`, `optimizePassThreshold` achieves full 3-tier lexicographic
optimality over `buildCandidates rows activeThreshold` (`max agree`, then `min biasSkew`,
then `min |t - activeThreshold|`), proving that under exact rational arithmetic any
2-winner equidistant midpoint equals `activeThreshold` and cannot preserve `(maxAgree, minSkew)`.
-/
theorem optimizePassThreshold_lexicographic_optimal (rows : List ValidRow)
    (activeThreshold : NNRat) (hne : rows ≠ []) :
    let cands := buildCandidates rows activeThreshold
    let tStar := optimizePassThreshold rows activeThreshold
    let eStar := scoreCandidate rows activeThreshold tStar
    tStar ∈ cands ∧
    (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree ≤ eStar.agree) ∧
    (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree = eStar.agree →
      eStar.biasSkew ≤ (scoreCandidate rows activeThreshold c).biasSkew) ∧
    (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree = eStar.agree →
      (scoreCandidate rows activeThreshold c).biasSkew = eStar.biasSkew →
      eStar.dist ≤ (scoreCandidate rows activeThreshold c).dist) := by
  have hEmpty : rows.isEmpty = false := by
    cases rows with
    | nil => exact absurd rfl hne
    | cons _ _ => rfl
  have hCandProps := buildCandidates_nonempty_and_strictly_sorted rows activeThreshold
  let cands := buildCandidates rows activeThreshold
  let scored := cands.map (scoreCandidate rows activeThreshold)
  have hScoredNe : scored ≠ [] := by
    intro h
    exact hCandProps.1 (List.map_eq_nil_iff.mp h)
  have hMaxSpec := maxAgreeOf_spec scored hScoredNe
  let maxAg := maxAgreeOf scored
  let bestAgree := scored.filter (fun c => c.agree == maxAg)
  have hBestAgreeNe : bestAgree ≠ [] := by
    rcases hMaxSpec.2 with ⟨ce, hce, heq⟩
    have hmem : ce ∈ bestAgree := List.mem_filter.mpr ⟨hce, by simp [maxAg, heq]⟩
    intro hemp; rw [hemp] at hmem; simp at hmem
  have hSkewSpec := minBiasSkewOf_spec bestAgree hBestAgreeNe
  let minSkew := minBiasSkewOf bestAgree
  let bestBias := bestAgree.filter (fun c => c.biasSkew == minSkew)
  have hBestBiasNe : bestBias ≠ [] := by
    rcases hSkewSpec.2 with ⟨ce, hce, heq⟩
    have hmem : ce ∈ bestBias := List.mem_filter.mpr ⟨hce, by simp [minSkew, heq]⟩
    intro hemp; rw [hemp] at hmem; simp at hmem
  have hDistSpec := minDistOf_spec bestBias hBestBiasNe
  let minD := minDistOf bestBias
  let winEvals := bestBias.filter (fun c => decide (c.dist ≈ minD))
  let winners := winEvals.map (·.threshold)
  have hWinnersNe : winners ≠ [] := by
    rcases hDistSpec.2 with ⟨ce, hce, heqv⟩
    have hmem : ce ∈ winEvals := List.mem_filter.mpr ⟨hce, decide_eq_true_iff.mpr heqv⟩
    have hw : ce.threshold ∈ winners := List.mem_map.mpr ⟨ce, hmem, rfl⟩
    intro hemp; rw [hemp] at hw; simp at hw
  have hWinProps : ∀ w ∈ winners, w ∈ cands ∧
      (scoreCandidate rows activeThreshold w).agree = maxAg ∧
      (scoreCandidate rows activeThreshold w).biasSkew = minSkew ∧
      (scoreCandidate rows activeThreshold w).dist ≈ minD := by
    intro w hw
    rw [List.mem_map] at hw
    rcases hw with ⟨ce, hce, rfl⟩
    rw [List.mem_filter, List.mem_filter, List.mem_filter, List.mem_map] at hce
    rcases hce with ⟨⟨⟨⟨c, hc, rfl⟩, hAg⟩, hSk⟩, hDi⟩
    exact ⟨hc, beq_iff_eq.mp hAg, beq_iff_eq.mp hSk, decide_eq_true_iff.mp hDi⟩
  have hOptimalOfWinner : ∀ w ∈ winners,
      w ∈ cands ∧
      (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree ≤ (scoreCandidate rows activeThreshold w).agree) ∧
      (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree = (scoreCandidate rows activeThreshold w).agree →
        (scoreCandidate rows activeThreshold w).biasSkew ≤ (scoreCandidate rows activeThreshold c).biasSkew) ∧
      (∀ c ∈ cands, (scoreCandidate rows activeThreshold c).agree = (scoreCandidate rows activeThreshold w).agree →
        (scoreCandidate rows activeThreshold c).biasSkew = (scoreCandidate rows activeThreshold w).biasSkew →
        (scoreCandidate rows activeThreshold w).dist ≤ (scoreCandidate rows activeThreshold c).dist) := by
    intro w hw
    rcases hWinProps w hw with ⟨hwC, hwAg, hwSk, hwDi⟩
    refine ⟨hwC, ?_, ?_, ?_⟩
    · intro c hc
      rw [hwAg]
      exact hMaxSpec.1 _ (List.mem_map.mpr ⟨c, hc, rfl⟩)
    · intro c hc hEqAg
      rw [hwSk]
      have hcInBA : scoreCandidate rows activeThreshold c ∈ bestAgree :=
        List.mem_filter.mpr ⟨List.mem_map.mpr ⟨c, hc, rfl⟩, beq_iff_eq.mpr (hEqAg.trans hwAg)⟩
      exact hSkewSpec.1 _ hcInBA
    · intro c hc hEqAg hEqSk
      have hcInBB : scoreCandidate rows activeThreshold c ∈ bestBias := by
        refine List.mem_filter.mpr ⟨?_, beq_iff_eq.mpr (hEqSk.trans hwSk)⟩
        exact List.mem_filter.mpr ⟨List.mem_map.mpr ⟨c, hc, rfl⟩, beq_iff_eq.mpr (hEqAg.trans hwAg)⟩
      exact nnrat_le_of_equiv_left hwDi.symm (hDistSpec.1 _ hcInBB)
  have hWinPairwise : List.Pairwise (· < ·) winners := by
    have hFilterMerge :
        winEvals = scored.filter (fun a => (decide (a.dist ≈ minD) && a.biasSkew == minSkew) && a.agree == maxAg) := by
      simp only [winEvals, bestBias, bestAgree, List.filter_filter]
    rw [show winners = winEvals.map (·.threshold) from rfl, hFilterMerge]
    exact pairwise_filter_map_threshold hCandProps.2.1 (fun _ => rfl)
  have hOptIsWinner : optimizePassThreshold rows activeThreshold ∈ winners := by
    unfold optimizePassThreshold
    simp only [hEmpty, Bool.false_eq_true, ↓reduceIte]
    split
    · rename_i hNil
      exact absurd hNil hWinnersNe
    · rename_i w hSing
      show w ∈ winners
      change w ∈ (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
      rw [hSing]
      exact List.mem_cons_self
    · rename_i wFirst wSecond wRest hCons
      let wLast := lastOf (wSecond :: wRest) (List.cons_ne_nil wSecond wRest)
      let mid := NNRat.normalize (nnMidpoint wFirst wLast)
      let midEval := scoreCandidate rows activeThreshold mid
      have hFirstMem : wFirst ∈ winners := by
        show wFirst ∈ (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
        rw [hCons]; exact List.mem_cons_self
      have hLastMem : wLast ∈ winners := by
        show wLast ∈ (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
        rw [hCons]; exact List.mem_cons_of_mem _ (lastOf_mem (wSecond :: wRest) _)
      have hFirstLtLast : wFirst < wLast := by
        have hP : List.Pairwise (· < ·) (wFirst :: wSecond :: wRest) := by
          have hW' : winners = wFirst :: wSecond :: wRest := hCons
          rw [← hW']
          exact hWinPairwise
        exact (List.pairwise_cons.mp hP).1 wLast (lastOf_mem (wSecond :: wRest) _)
      have hFirstP := hWinProps wFirst hFirstMem
      have hLastP := hWinProps wLast hLastMem
      have hDistEqv : nnAbsDiff wFirst activeThreshold ≈ nnAbsDiff wLast activeThreshold := by
        have h1 : (scoreCandidate rows activeThreshold wFirst).dist ≈
            (scoreCandidate rows activeThreshold wLast).dist :=
          NNRat.equiv_trans hFirstP.2.2.2 hLastP.2.2.2.symm
        exact NNRat.equiv_trans (NNRat.normalize_equiv _).symm
          (NNRat.equiv_trans h1 (NNRat.normalize_equiv _))
      have hMidEqvAct : mid ≈ activeThreshold :=
        NNRat.equiv_trans (NNRat.normalize_equiv _)
          (nnMidpoint_equiv_of_equidistant hFirstLtLast hDistEqv)
      have hNotMid : ¬ (midEval.agree == maxAg && midEval.biasSkew == minSkew) = true := by
        intro hBoth
        simp only [Bool.and_eq_true, beq_iff_eq] at hBoth
        rcases hBoth with ⟨hMAg, hMSk⟩
        have hActEqvMid : NNRat.normalize activeThreshold ≈ mid :=
          NNRat.equiv_trans (NNRat.normalize_equiv _) hMidEqvAct.symm
        have hCountsEq : evalCountsAt rows (NNRat.normalize activeThreshold) = evalCountsAt rows mid :=
          evalCountsAt_equiv_congr rows hActEqvMid
        have hActAg : (scoreCandidate rows activeThreshold (NNRat.normalize activeThreshold)).agree = maxAg := by
          dsimp only [midEval] at hMAg
          unfold scoreCandidate at hMAg ⊢
          rw [hCountsEq]
          exact hMAg
        have hActSk : (scoreCandidate rows activeThreshold (NNRat.normalize activeThreshold)).biasSkew = minSkew := by
          dsimp only [midEval] at hMSk
          unfold scoreCandidate at hMSk ⊢
          rw [hCountsEq]
          exact hMSk
        have hActInBB : scoreCandidate rows activeThreshold (NNRat.normalize activeThreshold) ∈ bestBias := by
          refine List.mem_filter.mpr ⟨?_, beq_iff_eq.mpr hActSk⟩
          exact List.mem_filter.mpr ⟨List.mem_map.mpr ⟨NNRat.normalize activeThreshold, hCandProps.2.2.2.2.1, rfl⟩,
            beq_iff_eq.mpr hActAg⟩
        have hActDistZero : (scoreCandidate rows activeThreshold (NNRat.normalize activeThreshold)).dist ≈ NNRat.zero := by
          unfold scoreCandidate
          dsimp only
          exact NNRat.equiv_trans (NNRat.normalize_equiv _)
            (NNRat.equiv_trans (nnAbsDiff_equiv_congr (NNRat.normalize_equiv _) (NNRat.equiv_refl _))
              (nnAbsDiff_self_equiv_zero _))
        have hMinLeZero : minD ≤ NNRat.zero :=
          nnrat_le_of_equiv_right hActDistZero (hDistSpec.1 _ hActInBB)
        have hFirstLeZero : nnAbsDiff wFirst activeThreshold ≤ NNRat.zero :=
          NNRat.le_trans (nnrat_le_of_equiv_left (NNRat.normalize_equiv _) (NNRat.le_of_equiv hFirstP.2.2.2)) hMinLeZero
        have hLastLeZero : nnAbsDiff wLast activeThreshold ≤ NNRat.zero :=
          NNRat.le_trans (nnrat_le_of_equiv_left (NNRat.normalize_equiv _) (NNRat.le_of_equiv hLastP.2.2.2)) hMinLeZero
        have hFirstEqvAct : wFirst ≈ activeThreshold :=
          (nnAbsDiff_equiv_zero_iff wFirst activeThreshold).mp
            (NNRat.equiv_of_le_antisymm hFirstLeZero (NNRat.zero_le _))
        have hLastEqvAct : wLast ≈ activeThreshold :=
          (nnAbsDiff_equiv_zero_iff wLast activeThreshold).mp
            (NNRat.equiv_of_le_antisymm hLastLeZero (NNRat.zero_le _))
        have hFirstEqvLast : wFirst ≈ wLast := NNRat.equiv_trans hFirstEqvAct hLastEqvAct.symm
        exact (NNRat.lt_iff_not_le wFirst wLast).mp hFirstLtLast (NNRat.le_of_equiv hFirstEqvLast.symm)
      split
      · rename_i hCond
        exact absurd hCond hNotMid
      · exact hLastMem
  exact hOptimalOfWinner (optimizePassThreshold rows activeThreshold) hOptIsWinner

/-- Theorem 30: `optimizePassThreshold` is invariant under arbitrary permutations of `valid_rows`. -/
theorem optimizePassThreshold_perm_invariant {rows₁ rows₂ : List ValidRow}
    (hp : List.Perm rows₁ rows₂) (activeThreshold : NNRat) :
    optimizePassThreshold rows₁ activeThreshold = optimizePassThreshold rows₂ activeThreshold := by
  have hEmpty : rows₁.isEmpty = rows₂.isEmpty := by
    cases rows₁ with
    | nil =>
      have : rows₂ = [] := hp.nil_eq.symm
      subst this; rfl
    | cons _ _ =>
      cases rows₂ with
      | nil => exact absurd hp.symm.nil_eq.symm (List.cons_ne_nil _ _)
      | cons _ _ => rfl
  have hCands : buildCandidates rows₁ activeThreshold = buildCandidates rows₂ activeThreshold := by
    unfold buildCandidates
    have hU : sortUnique (rows₁.map (·.judgeScore)) = sortUnique (rows₂.map (·.judgeScore)) :=
      sortUnique_perm_eq (hp.map (·.judgeScore))
    rw [hU]
  have hScoreEq : scoreCandidate rows₁ activeThreshold = scoreCandidate rows₂ activeThreshold := by
    funext t
    unfold scoreCandidate
    rw [evalCountsAt_perm hp t]
  unfold optimizePassThreshold
  rw [hEmpty, hCands, hScoreEq]

private theorem collectValidRows_perm {cs₁ cs₂ : List SampleClassification} (hp : List.Perm cs₁ cs₂) :
    List.Perm (collectValidRows cs₁) (collectValidRows cs₂) := by
  induction hp with
  | nil => exact List.Perm.nil
  | cons c _ ih =>
    cases c <;> simp only [collectValidRows]
    · exact ih
    · exact ih.cons _
    · exact ih.cons _
    · exact ih.cons _
    · exact ih.cons _
  | swap x y l =>
    cases x <;> cases y <;> simp only [collectValidRows] <;>
      first | exact List.Perm.refl _ | exact List.Perm.swap _ _ _
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

private theorem countInconclusive_perm {cs₁ cs₂ : List SampleClassification} (hp : List.Perm cs₁ cs₂) :
    countInconclusive cs₁ = countInconclusive cs₂ := by
  induction hp with
  | nil => rfl
  | cons c _ ih => cases c <;> simp [countInconclusive, ih]
  | swap x y l => cases x <;> cases y <;> simp [countInconclusive] <;> omega
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

private theorem countAgreed_perm {cs₁ cs₂ : List SampleClassification} (hp : List.Perm cs₁ cs₂) :
    countAgreed cs₁ = countAgreed cs₂ := by
  induction hp with
  | nil => rfl
  | cons c _ ih => cases c <;> simp [countAgreed, ih]
  | swap x y l => cases x <;> cases y <;> simp [countAgreed] <;> omega
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

private theorem countTooGenerous_perm {cs₁ cs₂ : List SampleClassification} (hp : List.Perm cs₁ cs₂) :
    countTooGenerous cs₁ = countTooGenerous cs₂ := by
  induction hp with
  | nil => rfl
  | cons c _ ih => cases c <;> simp [countTooGenerous, ih]
  | swap x y l => cases x <;> cases y <;> simp [countTooGenerous] <;> omega
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

private theorem countTooHarsh_perm {cs₁ cs₂ : List SampleClassification} (hp : List.Perm cs₁ cs₂) :
    countTooHarsh cs₁ = countTooHarsh cs₂ := by
  induction hp with
  | nil => rfl
  | cons c _ ih => cases c <;> simp [countTooHarsh, ih]
  | swap x y l => cases x <;> cases y <;> simp [countTooHarsh] <;> omega
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

/--
Theorem 31: All calibration scalar counts, exact rates, exact means, exact mean delta, and
recommended pass threshold are invariant under arbitrary permutations of input samples.
-/
theorem aggregateCalibration_perm_invariant_scalars (cfg : CalibrationConfig)
    {s₁ s₂ : List CalibrationSample} (hp : List.Perm s₁ s₂) :
    let r₁ := aggregateCalibration cfg s₁
    let r₂ := aggregateCalibration cfg s₂
    r₁.totalCases = r₂.totalCases ∧
    r₁.validCases = r₂.validCases ∧
    r₁.inconclusiveCases = r₂.inconclusiveCases ∧
    r₁.agreedCount = r₂.agreedCount ∧
    r₁.tooGenerousCount = r₂.tooGenerousCount ∧
    r₁.tooHarshCount = r₂.tooHarshCount ∧
    r₁.exactAgreementRate = r₂.exactAgreementRate ∧
    r₁.tooGenerousRate = r₂.tooGenerousRate ∧
    r₁.tooHarshRate = r₂.tooHarshRate ∧
    r₁.meanHumanScore = r₂.meanHumanScore ∧
    r₁.meanJudgeScore = r₂.meanJudgeScore ∧
    (match r₁.meanScoreDelta, r₂.meanScoreDelta with
     | none, none => True
     | some d₁, some d₂ => d₁ ≈ₛ d₂
     | _, _ => False) ∧
    r₁.recommendedPassThreshold = r₂.recommendedPassThreshold := by
  have hClsPerm : List.Perm (s₁.map (classifySample cfg)) (s₂.map (classifySample cfg)) :=
    hp.map (classifySample cfg)
  have hRowsPerm : List.Perm (collectValidRows (s₁.map (classifySample cfg)))
      (collectValidRows (s₂.map (classifySample cfg))) :=
    collectValidRows_perm hClsPerm
  have hLenEq : s₁.length = s₂.length := hp.length_eq
  have hValidEq : (collectValidRows (s₁.map (classifySample cfg))).length =
      (collectValidRows (s₂.map (classifySample cfg))).length := hRowsPerm.length_eq
  have hIncEq := countInconclusive_perm hClsPerm
  have hAgEq := countAgreed_perm hClsPerm
  have hGenEq := countTooGenerous_perm hClsPerm
  have hHarEq := countTooHarsh_perm hClsPerm
  have hOptEq := optimizePassThreshold_perm_invariant hRowsPerm cfg.passThreshold
  unfold aggregateCalibration
  dsimp only
  by_cases h0 : (collectValidRows (s₁.map (classifySample cfg))).length = 0
  · have h0' : (collectValidRows (s₂.map (classifySample cfg))).length = 0 := hValidEq ▸ h0
    simp only [h0, h0', ↓reduceDIte]
    exact ⟨hLenEq, trivial, hIncEq, hAgEq, hGenEq, hHarEq, trivial, trivial, trivial, trivial, trivial, trivial, trivial⟩
  · have h0' : (collectValidRows (s₂.map (classifySample cfg))).length ≠ 0 := by omega
    simp only [h0, h0', ↓reduceDIte]
    have hPos1 : 0 < (collectValidRows (s₁.map (classifySample cfg))).length := Nat.pos_of_ne_zero h0
    have hPos2 : 0 < (collectValidRows (s₂.map (classifySample cfg))).length := Nat.pos_of_ne_zero h0'
    have hH1 : 0 < ((collectValidRows (s₁.map (classifySample cfg))).map (·.humanNumeric)).length := by
      simpa using hPos1
    have hH2 : 0 < ((collectValidRows (s₂.map (classifySample cfg))).map (·.humanNumeric)).length := by
      simpa using hPos2
    have hJ1 : 0 < ((collectValidRows (s₁.map (classifySample cfg))).map (·.judgeScore)).length := by
      simpa using hPos1
    have hJ2 : 0 < ((collectValidRows (s₂.map (classifySample cfg))).map (·.judgeScore)).length := by
      simpa using hPos2
    have hMH : NNRat.normalize (nnMeanList ((collectValidRows (s₁.map (classifySample cfg))).map (·.humanNumeric)) hH1) =
        NNRat.normalize (nnMeanList ((collectValidRows (s₂.map (classifySample cfg))).map (·.humanNumeric)) hH2) :=
      nnrat_normalize_eq_of_equiv (nnMeanList_perm (hRowsPerm.map (·.humanNumeric)) hH1 hH2)
    have hMJ : NNRat.normalize (nnMeanList ((collectValidRows (s₁.map (classifySample cfg))).map (·.judgeScore)) hJ1) =
        NNRat.normalize (nnMeanList ((collectValidRows (s₂.map (classifySample cfg))).map (·.judgeScore)) hJ2) :=
      nnrat_normalize_eq_of_equiv (nnMeanList_perm (hRowsPerm.map (·.judgeScore)) hJ1 hJ2)
    have hMD : SignedRat.normalize (SignedRat.subNNRat
          (nnMeanList ((collectValidRows (s₁.map (classifySample cfg))).map (·.judgeScore)) hJ1)
          (nnMeanList ((collectValidRows (s₁.map (classifySample cfg))).map (·.humanNumeric)) hH1)) ≈ₛ
        SignedRat.normalize (SignedRat.subNNRat
          (nnMeanList ((collectValidRows (s₂.map (classifySample cfg))).map (·.judgeScore)) hJ2)
          (nnMeanList ((collectValidRows (s₂.map (classifySample cfg))).map (·.humanNumeric)) hH2)) :=
      SignedRat.equiv_trans (SignedRat.normalize_equiv _)
        (SignedRat.equiv_trans
          (SignedRat.subNNRat_equiv_congr
            (nnMeanList_perm (hRowsPerm.map (·.judgeScore)) hJ1 hJ2)
            (nnMeanList_perm (hRowsPerm.map (·.humanNumeric)) hH1 hH2))
          (SignedRat.normalize_equiv _).symm)
    have hAgRate : NNRat.normalize ⟨countAgreed (s₁.map (classifySample cfg)) * 100,
          (collectValidRows (s₁.map (classifySample cfg))).length, hPos1⟩ =
        NNRat.normalize ⟨countAgreed (s₂.map (classifySample cfg)) * 100,
          (collectValidRows (s₂.map (classifySample cfg))).length, hPos2⟩ := by
      apply nnrat_normalize_eq_of_equiv
      show (countAgreed (s₁.map (classifySample cfg)) * 100) *
            (collectValidRows (s₂.map (classifySample cfg))).length =
           (countAgreed (s₂.map (classifySample cfg)) * 100) *
            (collectValidRows (s₁.map (classifySample cfg))).length
      rw [hAgEq, hValidEq]
    have hGenRate : NNRat.normalize ⟨countTooGenerous (s₁.map (classifySample cfg)),
          (collectValidRows (s₁.map (classifySample cfg))).length, hPos1⟩ =
        NNRat.normalize ⟨countTooGenerous (s₂.map (classifySample cfg)),
          (collectValidRows (s₂.map (classifySample cfg))).length, hPos2⟩ := by
      apply nnrat_normalize_eq_of_equiv
      show countTooGenerous (s₁.map (classifySample cfg)) *
            (collectValidRows (s₂.map (classifySample cfg))).length =
           countTooGenerous (s₂.map (classifySample cfg)) *
            (collectValidRows (s₁.map (classifySample cfg))).length
      rw [hGenEq, hValidEq]
    have hHarRate : NNRat.normalize ⟨countTooHarsh (s₁.map (classifySample cfg)),
          (collectValidRows (s₁.map (classifySample cfg))).length, hPos1⟩ =
        NNRat.normalize ⟨countTooHarsh (s₂.map (classifySample cfg)),
          (collectValidRows (s₂.map (classifySample cfg))).length, hPos2⟩ := by
      apply nnrat_normalize_eq_of_equiv
      show countTooHarsh (s₁.map (classifySample cfg)) *
            (collectValidRows (s₂.map (classifySample cfg))).length =
           countTooHarsh (s₂.map (classifySample cfg)) *
            (collectValidRows (s₁.map (classifySample cfg))).length
      rw [hHarEq, hValidEq]
    exact ⟨hLenEq, hValidEq, hIncEq, hAgEq, hGenEq, hHarEq,
      congrArg some hAgRate, congrArg some hGenRate, congrArg some hHarRate,
      congrArg some hMH, congrArg some hMJ, hMD, hOptEq⟩

/-- Theorem 32: End-to-end `aggregateCalibration` always recommends a threshold in `[0, 1]`. -/
theorem aggregateCalibration_recommendedThreshold_unit (cfg : CalibrationConfig)
    (samples : List CalibrationSample)
    (hCfg : cfg.isValid)
    (hUnit : ∀ s ∈ samples, s.scoresUnit) :
    NNRat.zero ≤ (aggregateCalibration cfg samples).recommendedPassThreshold ∧
    (aggregateCalibration cfg samples).recommendedPassThreshold ≤ NNRat.one := by
  have hRowsUnit := validRows_unit_of_samples_unit cfg samples hUnit
  unfold aggregateCalibration
  dsimp only
  split
  · exact ⟨NNRat.zero_le _, nnrat_le_of_equiv_left (NNRat.normalize_equiv _).symm hCfg.1⟩
  · exact optimizePassThreshold_unit_bounds _ cfg.passThreshold hCfg.1 (fun r hr => (hRowsUnit r hr).2)

end EvalForgeFormal.Calibration
