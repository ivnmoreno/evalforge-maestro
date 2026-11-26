import EvalForgeFormal.Stats.Types

namespace EvalForgeFormal.Stats

open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration
open EvalForgeFormal.QualityGate

/-!
# Statistical Inference State Machine, Method Builders & QualityGate Bridge

Mirrors:
- `_finalize_inference`, `compute_paired_case_statistics`, `compute_welch_run_statistics`,
  `compute_one_sample_run_statistics` (`src/evalforge_maestro/regression/stats.py`)
- `_extract_aligned_case_pairs` and `compare_run_cohorts` method dispatch
  (`src/evalforge_maestro/regression/compare.py`)
- `statistical_regression:<metric_id>` escalation (`src/evalforge_maestro/regression/gate.py`)
-/

/-- Exact significance level `α = 1 - confidence_level` for `confidence_level ≤ 1`. -/
def alphaOf (confidenceLevel : NNRat) : NNRat :=
  ⟨confidenceLevel.den - confidenceLevel.num, confidenceLevel.den, confidenceLevel.denPos⟩

theorem alphaOf_pos {c : NNRat} (h : c < NNRat.one) : NNRat.zero < alphaOf c := by
  unfold alphaOf
  rw [NNRat.zero_lt_iff]
  have hlt : c.num * 1 < 1 * c.den := h
  dsimp only
  omega

theorem alphaOf_lt_one {c : NNRat} (h : NNRat.zero < c) : alphaOf c < NNRat.one := by
  unfold alphaOf
  show (c.den - c.num) * 1 < 1 * c.den
  have hpos : 0 < c.num := (NNRat.zero_lt_iff c).mp h
  have hd : 0 < c.den := c.denPos
  omega

/--
Exact sqrt-free `effect_size` computation (`mean_delta / sd`): defined iff both `meanDelta`
and strictly positive dispersion variance `denomVar > 0` are present.
-/
def computeEffectSize (meanDelta : Option SignedRat) (denomVar : Option NNRat) : EffectSizeSpec :=
  match meanDelta, denomVar with
  | some d, some v =>
    if hv : 0 < v.num then
      {
        defined := true
        sqMag := some (NNRat.div (sSqNNRat d) v hv)
        sign := some (EffectSign.ofSignedRat d)
      }
    else
      { defined := false, sqMag := none, sign := none }
  | _, _ =>
    { defined := false, sqMag := none, sign := none }

/-- Disabled `EffectSizeSpec` returned under `INSUFFICIENT_DATA`. -/
def emptyEffectSize : EffectSizeSpec :=
  { defined := false, sqMag := none, sign := none }

/--
Core executable `_finalize_inference` decision state machine accepting explicit positive-variance
`(directPVal, directMargin)` outputs (used both directly by `evalforge-stats-oracle` and by
`finalizeInferenceWith oracle`).
-/
def finalizeInferenceDirect (inp : InferenceInput) (directPVal directMargin : NNRat) :
    StatisticalOutcome :=
  let clampedMean := inp.meanDelta.map sClampUnit
  match inp.hasEnoughSamples, inp.meanDelta, inp.seSq, inp.df with
  | true, some d, some seSqVal, some dfVal =>
    let eff := computeEffectSize (some d) inp.effectDenomVar
    if seSqVal.num = 0 then
      let clamped := sClampUnit d
      if d.num = 0 then
        {
          method := inp.method
          confidenceLevel := inp.confidenceLevel
          sampleSize := inp.sampleSize
          baselineSampleSize := inp.baselineSampleSize
          candidateSampleSize := inp.candidateSampleSize
          excludedPairCount := inp.excludedPairCount
          meanDelta := some clamped
          seSq := some NNRat.zero
          ciLow := some clamped
          ciHigh := some clamped
          pValue := some NNRat.one
          df := some dfVal
          effectSize := eff
          significance := .notSignificant
          statisticallySignificant := false
        }
      else if 0 < d.num then
        {
          method := inp.method
          confidenceLevel := inp.confidenceLevel
          sampleSize := inp.sampleSize
          baselineSampleSize := inp.baselineSampleSize
          candidateSampleSize := inp.candidateSampleSize
          excludedPairCount := inp.excludedPairCount
          meanDelta := some clamped
          seSq := some NNRat.zero
          ciLow := some clamped
          ciHigh := some clamped
          pValue := some NNRat.zero
          df := some dfVal
          effectSize := eff
          significance := .significantImprovement
          statisticallySignificant := true
        }
      else
        {
          method := inp.method
          confidenceLevel := inp.confidenceLevel
          sampleSize := inp.sampleSize
          baselineSampleSize := inp.baselineSampleSize
          candidateSampleSize := inp.candidateSampleSize
          excludedPairCount := inp.excludedPairCount
          meanDelta := some clamped
          seSq := some NNRat.zero
          ciLow := some clamped
          ciHigh := some clamped
          pValue := some NNRat.zero
          df := some dfVal
          effectSize := eff
          significance := .significantRegression
          statisticallySignificant := true
        }
    else
      let ciLo := sClampUnit (sSub d (ofNNRat directMargin))
      let ciHi := sClampUnit (sAdd d (ofNNRat directMargin))
      let alpha := alphaOf inp.confidenceLevel
      let isSig := decide (directPVal < alpha)
      let sig :=
        if isSig then
          if 0 < d.num then SignificanceStatus.significantImprovement
          else SignificanceStatus.significantRegression
        else
          SignificanceStatus.notSignificant
      {
        method := inp.method
        confidenceLevel := inp.confidenceLevel
        sampleSize := inp.sampleSize
        baselineSampleSize := inp.baselineSampleSize
        candidateSampleSize := inp.candidateSampleSize
        excludedPairCount := inp.excludedPairCount
        meanDelta := some (sClampUnit d)
        seSq := some seSqVal
        ciLow := some ciLo
        ciHigh := some ciHi
        pValue := some directPVal
        df := some dfVal
        effectSize := eff
        significance := sig
        statisticallySignificant := isSig
      }
  | _, _, _, _ =>
    {
      method := inp.method
      confidenceLevel := inp.confidenceLevel
      sampleSize := inp.sampleSize
      baselineSampleSize := inp.baselineSampleSize
      candidateSampleSize := inp.candidateSampleSize
      excludedPairCount := inp.excludedPairCount
      meanDelta := clampedMean
      seSq := none
      ciLow := none
      ciHigh := none
      pValue := none
      df := none
      effectSize := emptyEffectSize
      significance := .insufficientData
      statisticallySignificant := false
    }

/--
Abstract `_finalize_inference` parameterized over any symmetric `TwoTailedOracle`.
-/
def finalizeInferenceWith (oracle : TwoTailedOracle) (inp : InferenceInput) : StatisticalOutcome :=
  match inp.meanDelta, inp.seSq, inp.df with
  | some d, some seSqVal, some dfVal =>
    finalizeInferenceDirect inp
      (oracle.pValue d seSqVal dfVal)
      (oracle.margin seSqVal dfVal inp.confidenceLevel)
  | _, _, _ =>
    finalizeInferenceDirect inp NNRat.one NNRat.zero

/-- Negate `meanDelta` inside an `InferenceInput` (baseline/candidate swap transformation). -/
def negateInputDelta (inp : InferenceInput) : InferenceInput :=
  { inp with meanDelta := inp.meanDelta.map sNeg }

/-- Exact input builder mirroring `compute_paired_case_statistics` (`stats.py:261-302`). -/
def buildPairedInput (base cand : List NNRat) (confidenceLevel : NNRat)
    (minSamples excludedPairs : Nat) : InferenceInput :=
  let diffs := pairedDiffs base cand
  let n := diffs.length
  let meanD : Option SignedRat :=
    if hpos : 0 < n then some (sMeanList diffs hpos) else none
  let hasEnough := decide (max 2 minSamples ≤ n)
  if h2 : 2 ≤ n then
    let varD := sampleVarSigned diffs h2
    have hnPos : 0 < (NNRat.ofNat n).num := by dsimp [NNRat.ofNat]; omega
    let seSq := NNRat.div varD (NNRat.ofNat n) hnPos
    {
      method := .pairedTCase
      confidenceLevel := confidenceLevel
      sampleSize := n
      baselineSampleSize := base.length
      candidateSampleSize := cand.length
      excludedPairCount := excludedPairs
      meanDelta := meanD
      seSq := some seSq
      df := some (NNRat.ofNat (n - 1))
      effectDenomVar := some varD
      hasEnoughSamples := hasEnough
    }
  else
    {
      method := .pairedTCase
      confidenceLevel := confidenceLevel
      sampleSize := n
      baselineSampleSize := base.length
      candidateSampleSize := cand.length
      excludedPairCount := excludedPairs
      meanDelta := meanD
      seSq := none
      df := none
      effectDenomVar := none
      hasEnoughSamples := hasEnough
    }

/-- Exact input builder mirroring `compute_welch_run_statistics` (`stats.py:305-356`). -/
def buildWelchInput (base cand : List NNRat) (confidenceLevel : NNRat)
    (minSamples : Nat) : InferenceInput :=
  let k := base.length
  let m := cand.length
  let meanD : Option SignedRat :=
    if hk : 0 < k then
      if hm : 0 < m then
        some (SignedRat.subNNRat (nnMeanList cand hm) (nnMeanList base hk))
      else none
    else none
  let hasEnough := decide (max 2 minSamples ≤ k ∧ max 2 minSamples ≤ m)
  if hk2 : 2 ≤ k then
    if hm2 : 2 ≤ m then
      let varB := sampleVarNNRat base hk2
      let varC := sampleVarNNRat cand hm2
      have hkPos : 0 < (NNRat.ofNat k).num := by dsimp [NNRat.ofNat]; omega
      have hmPos : 0 < (NNRat.ofNat m).num := by dsimp [NNRat.ofNat]; omega
      let vB := NNRat.div varB (NNRat.ofNat k) hkPos
      let vC := NNRat.div varC (NNRat.ofNat m) hmPos
      let seSq := vB.add vC
      let dfVal := welchSatterthwaiteDf vB vC k m hk2 hm2
      let pVar := pooledVarNNRat varB varC k m hk2 hm2
      {
        method := .welchTRun
        confidenceLevel := confidenceLevel
        sampleSize := min k m
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := meanD
        seSq := some seSq
        df := some dfVal
        effectDenomVar := some pVar
        hasEnoughSamples := hasEnough
      }
    else
      {
        method := .welchTRun
        confidenceLevel := confidenceLevel
        sampleSize := min k m
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := meanD
        seSq := none
        df := none
        effectDenomVar := none
        hasEnoughSamples := false
      }
  else
    {
      method := .welchTRun
      confidenceLevel := confidenceLevel
      sampleSize := min k m
      baselineSampleSize := k
      candidateSampleSize := m
      excludedPairCount := 0
      meanDelta := meanD
      seSq := none
      df := none
      effectDenomVar := none
      hasEnoughSamples := false
    }

/--
Exact input builder mirroring `compute_one_sample_run_statistics` (`stats.py:359-405`).
Valid domain: `(k = 1 ∧ 2 ≤ m) ∨ (m = 1 ∧ 2 ≤ k)`. Invalid cardinalities safely produce
an `INSUFFICIENT_DATA` input.
-/
def buildOneSampleInput (base cand : List NNRat) (confidenceLevel : NNRat)
    (minSamples : Nat) : InferenceInput :=
  let k := base.length
  let m := cand.length
  if hk1 : k = 1 then
    if hm2 : 2 ≤ m then
      have hkPos : 0 < k := by omega
      have hmPos : 0 < m := by omega
      let meanD := SignedRat.subNNRat (nnMeanList cand hmPos) (nnMeanList base hkPos)
      let varRep := sampleVarNNRat cand hm2
      have hmNumPos : 0 < (NNRat.ofNat m).num := by dsimp [NNRat.ofNat]; omega
      let seSq := NNRat.div varRep (NNRat.ofNat m) hmNumPos
      {
        method := .oneSampleTRun
        confidenceLevel := confidenceLevel
        sampleSize := m
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := some meanD
        seSq := some seSq
        df := some (NNRat.ofNat (m - 1))
        effectDenomVar := some varRep
        hasEnoughSamples := decide (max 2 minSamples ≤ m)
      }
    else
      {
        method := .oneSampleTRun
        confidenceLevel := confidenceLevel
        sampleSize := max k m
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := none
        seSq := none
        df := none
        effectDenomVar := none
        hasEnoughSamples := false
      }
  else if hm1 : m = 1 then
    if hk2 : 2 ≤ k then
      have hkPos : 0 < k := by omega
      have hmPos : 0 < m := by omega
      let meanD := SignedRat.subNNRat (nnMeanList cand hmPos) (nnMeanList base hkPos)
      let varRep := sampleVarNNRat base hk2
      have hkNumPos : 0 < (NNRat.ofNat k).num := by dsimp [NNRat.ofNat]; omega
      let seSq := NNRat.div varRep (NNRat.ofNat k) hkNumPos
      {
        method := .oneSampleTRun
        confidenceLevel := confidenceLevel
        sampleSize := k
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := some meanD
        seSq := some seSq
        df := some (NNRat.ofNat (k - 1))
        effectDenomVar := some varRep
        hasEnoughSamples := decide (max 2 minSamples ≤ k)
      }
    else
      {
        method := .oneSampleTRun
        confidenceLevel := confidenceLevel
        sampleSize := max k m
        baselineSampleSize := k
        candidateSampleSize := m
        excludedPairCount := 0
        meanDelta := none
        seSq := none
        df := none
        effectDenomVar := none
        hasEnoughSamples := false
      }
  else
    {
      method := .oneSampleTRun
      confidenceLevel := confidenceLevel
      sampleSize := min k m
      baselineSampleSize := k
      candidateSampleSize := m
      excludedPairCount := 0
      meanDelta := none
      seSq := none
      df := none
      effectDenomVar := none
      hasEnoughSamples := false
    }

/-- End-to-end paired statistics evaluator parameterized over `TwoTailedOracle`. -/
def computePairedStats (oracle : TwoTailedOracle) (base cand : List NNRat)
    (confidenceLevel : NNRat) (minSamples excludedPairs : Nat) : StatisticalOutcome :=
  finalizeInferenceWith oracle (buildPairedInput base cand confidenceLevel minSamples excludedPairs)

/-- End-to-end Welch cohort statistics evaluator parameterized over `TwoTailedOracle`. -/
def computeWelchStats (oracle : TwoTailedOracle) (base cand : List NNRat)
    (confidenceLevel : NNRat) (minSamples : Nat) : StatisticalOutcome :=
  finalizeInferenceWith oracle (buildWelchInput base cand confidenceLevel minSamples)

/-- End-to-end one-sample cohort statistics evaluator parameterized over `TwoTailedOracle`. -/
def computeOneSampleStats (oracle : TwoTailedOracle) (base cand : List NNRat)
    (confidenceLevel : NNRat) (minSamples : Nat) : StatisticalOutcome :=
  finalizeInferenceWith oracle (buildOneSampleInput base cand confidenceLevel minSamples)

/--
Exact cohort inferential method dispatch mirroring `compare_run_cohorts`
(`src/evalforge_maestro/regression/compare.py:472-496`).
-/
def dispatchCohortMethod (k m : Nat) : CohortRoute :=
  if 2 ≤ k ∧ 2 ≤ m then
    .welchTRun
  else if (k = 1 ∧ 2 ≤ m) ∨ (m = 1 ∧ 2 ≤ k) then
    .oneSampleTRun
  else if k = 1 ∧ m = 1 then
    .pairedTCaseFallback
  else
    .welchTRun

/--
Exact aligned numeric pair extraction over shared case IDs, mirroring
`_extract_aligned_case_pairs` (`src/evalforge_maestro/regression/compare.py:68-93`).
-/
def extractAlignedPairs : List SharedCaseScores → AlignedPairExtraction
  | [] => { baselineScores := [], candidateScores := [], excludedPairCount := 0 }
  | row :: rest =>
    let tail := extractAlignedPairs rest
    match row.baselineScore, row.candidateScore with
    | some b, some c =>
      if row.baselineMetricPresent && row.candidateMetricPresent then
        {
          baselineScores := b :: tail.baselineScores
          candidateScores := c :: tail.candidateScores
          excludedPairCount := tail.excludedPairCount
        }
      else if row.baselineMetricPresent || row.candidateMetricPresent then
        { tail with excludedPairCount := tail.excludedPairCount + 1 }
      else
        tail
    | _, _ =>
      if row.baselineMetricPresent || row.candidateMetricPresent then
        { tail with excludedPairCount := tail.excludedPairCount + 1 }
      else
        tail

/--
Bridge from a metric's `SignificanceStatus` to its `QualityGate` rule check status,
mirroring `src/evalforge_maestro/regression/gate.py:267-292`.
-/
def statisticalRegressionCheck (sig : SignificanceStatus) (failOnSigRegression : Bool) :
    GateDecision :=
  match sig with
  | .significantRegression =>
    if failOnSigRegression then .fail else .warning
  | _ => .pass

/--
Evaluate a list of metric significance statuses through `EvalForgeFormal.QualityGate.evaluateChecks`,
mirroring the `statistical_regression:<metric_id>` / `statistical_significance` rule block in `gate.py`.
-/
def evaluateMetricSignificanceChecks (statuses : List SignificanceStatus)
    (failOnSigRegression : Bool) : GateOutcome :=
  let checks : List RuleCheck :=
    statuses.map fun sig =>
      {
        status := statisticalRegressionCheck sig failOnSigRegression
        message := sig.toCanonicalString
      }
  evaluateChecks checks

end EvalForgeFormal.Stats
