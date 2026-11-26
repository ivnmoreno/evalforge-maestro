import EvalForgeFormal.Stats.ExactAlgebra
import EvalForgeFormal.QualityGate.Decision
import EvalForgeFormal.QualityGate.RuleRecorder
import EvalForgeFormal.QualityGate.Aggregation

namespace EvalForgeFormal.Stats

open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration
open EvalForgeFormal.QualityGate

/-!
# Statistical Inference Domain Types

Mirrors `evalforge_maestro.types.{StatisticalMethod, SignificanceStatus, StatisticalSummary}`
(`src/evalforge_maestro/types.py`), cohort dispatch (`src/evalforge_maestro/regression/compare.py`),
and statistical-regression escalation (`src/evalforge_maestro/regression/gate.py`).
-/

/-- Inferential method applied to compute intervals and p-values (`StatisticalMethod`). -/
inductive StatisticalMethod where
  | pairedTCase
  | welchTRun
  | oneSampleTRun
  deriving DecidableEq, Repr, BEq

namespace StatisticalMethod

def toCanonicalString : StatisticalMethod → String
  | .pairedTCase => "paired_t_case"
  | .welchTRun => "welch_t_run"
  | .oneSampleTRun => "one_sample_t_run"

def ofCanonicalString? : String → Option StatisticalMethod
  | "paired_t_case" => some .pairedTCase
  | "welch_t_run" => some .welchTRun
  | "one_sample_t_run" => some .oneSampleTRun
  | _ => none

end StatisticalMethod

/-- Four-state hypothesis-test classification (`SignificanceStatus`). -/
inductive SignificanceStatus where
  | significantImprovement
  | significantRegression
  | notSignificant
  | insufficientData
  deriving DecidableEq, Repr, BEq

namespace SignificanceStatus

def toCanonicalString : SignificanceStatus → String
  | .significantImprovement => "significant_improvement"
  | .significantRegression => "significant_regression"
  | .notSignificant => "not_significant"
  | .insufficientData => "insufficient_data"

def ofCanonicalString? : String → Option SignificanceStatus
  | "significant_improvement" => some .significantImprovement
  | "significant_regression" => some .significantRegression
  | "not_significant" => some .notSignificant
  | "insufficient_data" => some .insufficientData
  | _ => none

/-- Negation duality swap on significance classification (`improvement ↔ regression`). -/
def swapDirection : SignificanceStatus → SignificanceStatus
  | .significantImprovement => .significantRegression
  | .significantRegression => .significantImprovement
  | .notSignificant => .notSignificant
  | .insufficientData => .insufficientData

end SignificanceStatus

/-- Sign of a defined standardized effect size (`mean_delta / sd`). -/
inductive EffectSign where
  | negative
  | zero
  | positive
  deriving DecidableEq, Repr, BEq

namespace EffectSign

def toCanonicalString : EffectSign → String
  | .negative => "negative"
  | .zero => "zero"
  | .positive => "positive"

/-- Determine the exact sign of a signed rational. -/
def ofSignedRat (s : SignedRat) : EffectSign :=
  if 0 < s.num then .positive
  else if s.num < 0 then .negative
  else .zero

/-- Flip effect sign under baseline/candidate swap (`mean_delta ↦ -mean_delta`). -/
def flip : EffectSign → EffectSign
  | .negative => .positive
  | .zero => .zero
  | .positive => .negative

theorem ofSignedRat_neg (s : SignedRat) : ofSignedRat (sNeg s) = (ofSignedRat s).flip := by
  unfold ofSignedRat sNeg flip
  dsimp only
  by_cases h1 : 0 < s.num
  · have hn1 : ¬ (0 < -s.num) := by omega
    have hn2 : -s.num < 0 := by omega
    simp only [hn1, hn2, h1, ↓reduceIte]
  · by_cases h2 : s.num < 0
    · have hn1 : 0 < -s.num := by omega
      simp only [hn1, h1, h2, ↓reduceIte]
    · have h0 : s.num = 0 := by omega
      simp [h0]

theorem ofSignedRat_congr {a b : SignedRat} (h : a ≈ₛ b) : ofSignedRat a = ofSignedRat b := by
  unfold SignedRat.equiv at h
  have haPos : (0 : Int) < (a.den : Int) := by have := a.denPos; omega
  have hbPos : (0 : Int) < (b.den : Int) := by have := b.denPos; omega
  unfold ofSignedRat
  by_cases ha1 : 0 < a.num
  · have hmul : (0 : Int) < a.num * (b.den : Int) := Int.mul_pos ha1 hbPos
    rw [h] at hmul
    have hb1 : 0 < b.num := by
      by_cases hb : 0 < b.num
      · exact hb
      · have hle : b.num ≤ 0 := by omega
        have := Int.mul_nonpos_of_nonpos_of_nonneg hle (Int.le_of_lt haPos)
        omega
    simp [ha1, hb1]
  · by_cases ha2 : a.num < 0
    · have hmul : a.num * (b.den : Int) < 0 := Int.mul_neg_of_neg_of_pos ha2 hbPos
      rw [h] at hmul
      have hb2 : b.num < 0 := by
        by_cases hb : b.num < 0
        · exact hb
        · have hge : 0 ≤ b.num := by omega
          have := Int.mul_nonneg hge (Int.le_of_lt haPos)
          omega
      have hb1 : ¬ (0 < b.num) := by omega
      simp [ha1, ha2, hb1, hb2]
    · have ha0 : a.num = 0 := by omega
      have hmul : b.num * (a.den : Int) = 0 := by
        rw [← h, ha0, Int.zero_mul]
      have hb0 : b.num = 0 := by
        cases Int.mul_eq_zero.mp hmul with
        | inl h0 => exact h0
        | inr h0 => omega
      simp [ha0, hb0]

end EffectSign

/--
Sqrt-free exact specification of standardized `effect_size` (`mean_delta / sd`):
`defined = true` iff dispersion variance `> 0` and sufficient samples hold,
with exact squared magnitude `mean_delta² / denom_var` and sign matching `mean_delta`.
-/
structure EffectSizeSpec where
  defined : Bool
  sqMag : Option NNRat
  sign : Option EffectSign
  deriving DecidableEq, Repr, BEq

/--
Abstract mathematical contract for a symmetric two-tailed test distribution (e.g., Student's t),
separating transcendental numerical evaluation (`regularized_incomplete_beta`, `student_t_critical`)
from the exact rational inference decision state machine.
-/
structure TwoTailedOracle where
  pValue : SignedRat → NNRat → NNRat → NNRat
  margin : NNRat → NNRat → NNRat → NNRat
  pValue_le_one : ∀ d seSq df, pValue d seSq df ≤ NNRat.one
  pValue_zero_delta : ∀ d seSq df, d ≈ₛ SignedRat.zero → pValue d seSq df ≈ NNRat.one
  pValue_neg : ∀ d seSq df, pValue (sNeg d) seSq df ≈ pValue d seSq df
  pValue_congr : ∀ {d₁ d₂ : SignedRat} {s₁ s₂ f₁ f₂ : NNRat},
    d₁ ≈ₛ d₂ → s₁ ≈ s₂ → f₁ ≈ f₂ → pValue d₁ s₁ f₁ ≈ pValue d₂ s₂ f₂
  margin_congr : ∀ {s₁ s₂ f₁ f₂ c₁ c₂ : NNRat},
    s₁ ≈ s₂ → f₁ ≈ f₂ → c₁ ≈ c₂ → margin s₁ f₁ c₁ ≈ margin s₂ f₂ c₂

/-- Exact-rational input record mirroring `_finalize_inference` (`src/evalforge_maestro/regression/stats.py`). -/
structure InferenceInput where
  method : StatisticalMethod
  confidenceLevel : NNRat
  sampleSize : Nat
  baselineSampleSize : Nat
  candidateSampleSize : Nat
  excludedPairCount : Nat
  meanDelta : Option SignedRat
  seSq : Option NNRat
  df : Option NNRat
  effectDenomVar : Option NNRat
  hasEnoughSamples : Bool
  deriving DecidableEq, Repr

/-- Decision-relevant output record mirroring `evalforge_maestro.types.StatisticalSummary`. -/
structure StatisticalOutcome where
  method : StatisticalMethod
  confidenceLevel : NNRat
  sampleSize : Nat
  baselineSampleSize : Nat
  candidateSampleSize : Nat
  excludedPairCount : Nat
  meanDelta : Option SignedRat
  seSq : Option NNRat
  ciLow : Option SignedRat
  ciHigh : Option SignedRat
  pValue : Option NNRat
  df : Option NNRat
  effectSize : EffectSizeSpec
  significance : SignificanceStatus
  statisticallySignificant : Bool
  deriving DecidableEq, Repr

/-- Cohort inferential route selected by `compare_run_cohorts` (`compare.py:472-496`). -/
inductive CohortRoute where
  | welchTRun
  | oneSampleTRun
  | pairedTCaseFallback
  deriving DecidableEq, Repr, BEq

namespace CohortRoute

def toCanonicalString : CohortRoute → String
  | .welchTRun => "welch_t_run"
  | .oneSampleTRun => "one_sample_t_run"
  | .pairedTCaseFallback => "paired_t_case_fallback"

end CohortRoute

/--
Per-case score record for a `case_id` present in both baseline and candidate runs,
mirroring `_extract_aligned_case_pairs` (`src/evalforge_maestro/regression/compare.py:68-93`).
-/
structure SharedCaseScores where
  caseId : String
  baselineScore : Option NNRat
  candidateScore : Option NNRat
  baselineMetricPresent : Bool
  candidateMetricPresent : Bool
  deriving DecidableEq, Repr

/-- Result of extracting aligned numeric case pairs and excluded partial/non-applicable pairs. -/
structure AlignedPairExtraction where
  baselineScores : List NNRat
  candidateScores : List NNRat
  excludedPairCount : Nat
  deriving DecidableEq, Repr

end EvalForgeFormal.Stats
