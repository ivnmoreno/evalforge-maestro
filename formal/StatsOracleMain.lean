import Lean.Data.Json
import EvalForgeFormal.Stats.Inference

open Lean
open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration
open EvalForgeFormal.QualityGate
open EvalForgeFormal.Stats

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private def mkPct (n : Nat) : NNRat := ⟨n, 100, by omega⟩
private def mkMicro (n : Nat) : NNRat := ⟨n, 1000000, by omega⟩

private structure StatsCaseInput where
  caseId : String
  method : StatisticalMethod
  baselineScores : List NNRat
  candidateScores : List NNRat
  confidenceLevel : NNRat
  minSamples : Nat
  excludedPairCount : Nat
  directPValue : NNRat
  directMargin : NNRat

private def nnratToJson (r : NNRat) : Json :=
  let norm := NNRat.normalize r
  Json.mkObj [
    ("den", Json.num norm.den),
    ("num", Json.num norm.num)
  ]

private def optNNRatToJson : Option NNRat → Json
  | some r => nnratToJson r
  | none => Json.null

private def signedRatToJson (s : SignedRat) : Json :=
  let norm := SignedRat.normalize s
  Json.mkObj [
    ("den", Json.num norm.den),
    ("num", Json.num (JsonNumber.fromInt norm.num))
  ]

private def optSignedRatToJson : Option SignedRat → Json
  | some s => signedRatToJson s
  | none => Json.null

private def optEffectSignToJson : Option EffectSign → Json
  | some sg => Json.str sg.toCanonicalString
  | none => Json.null

private def effectSizeToJson (e : EffectSizeSpec) : Json :=
  Json.mkObj [
    ("defined", Json.bool e.defined),
    ("sign", optEffectSignToJson e.sign),
    ("sq_mag_exact", optNNRatToJson e.sqMag)
  ]

private def outcomeToJson (out : StatisticalOutcome) : Json :=
  Json.mkObj [
    ("baseline_sample_size", Json.num out.baselineSampleSize),
    ("candidate_sample_size", Json.num out.candidateSampleSize),
    ("ci_high_exact", optSignedRatToJson out.ciHigh),
    ("ci_low_exact", optSignedRatToJson out.ciLow),
    ("confidence_level_exact", nnratToJson out.confidenceLevel),
    ("df_exact", optNNRatToJson out.df),
    ("effect_size", effectSizeToJson out.effectSize),
    ("excluded_pair_count", Json.num out.excludedPairCount),
    ("mean_delta_exact", optSignedRatToJson out.meanDelta),
    ("method", Json.str out.method.toCanonicalString),
    ("p_value_exact", optNNRatToJson out.pValue),
    ("sample_size", Json.num out.sampleSize),
    ("se_sq_exact", optNNRatToJson out.seSq),
    ("significance", Json.str out.significance.toCanonicalString),
    ("statistically_significant", Json.bool out.statisticallySignificant)
  ]

private def evalStatsCase (c : StatsCaseInput) : StatisticalOutcome :=
  let inp :=
    match c.method with
    | .pairedTCase =>
      buildPairedInput c.baselineScores c.candidateScores c.confidenceLevel c.minSamples c.excludedPairCount
    | .welchTRun =>
      buildWelchInput c.baselineScores c.candidateScores c.confidenceLevel c.minSamples
    | .oneSampleTRun =>
      buildOneSampleInput c.baselineScores c.candidateScores c.confidenceLevel c.minSamples
  finalizeInferenceDirect inp c.directPValue c.directMargin

private def statsCaseInputToJson (c : StatsCaseInput) : Json :=
  Json.mkObj [
    ("baseline_scores", Json.arr (c.baselineScores.toArray.map nnratToJson)),
    ("candidate_scores", Json.arr (c.candidateScores.toArray.map nnratToJson)),
    ("case_id", Json.str c.caseId),
    ("confidence_level", nnratToJson c.confidenceLevel),
    ("direct_margin", nnratToJson c.directMargin),
    ("direct_p_value", nnratToJson c.directPValue),
    ("excluded_pair_count", Json.num c.excludedPairCount),
    ("method", Json.str c.method.toCanonicalString),
    ("min_samples", Json.num c.minSamples)
  ]

private def canonicalStatsCases : List StatsCaseInput :=
  [
    -- 1. Paired zero variance, zero delta
    {
      caseId := "paired_zero_var_zero_delta"
      method := .pairedTCase
      baselineScores := [mkPct 80, mkPct 90, mkPct 70]
      candidateScores := [mkPct 80, mkPct 90, mkPct 70]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.one
      directMargin := NNRat.zero
    },
    -- 2. Paired zero variance, constant positive improvement
    {
      caseId := "paired_zero_var_const_improvement"
      method := .pairedTCase
      baselineScores := [mkPct 20, mkPct 30, mkPct 40, mkPct 50]
      candidateScores := [mkPct 70, mkPct 80, mkPct 90, mkPct 100]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.zero
      directMargin := NNRat.zero
    },
    -- 3. Paired zero variance, constant negative regression
    {
      caseId := "paired_zero_var_const_regression"
      method := .pairedTCase
      baselineScores := [mkPct 80, mkPct 90, mkPct 70]
      candidateScores := [mkPct 50, mkPct 60, mkPct 40]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.zero
      directMargin := NNRat.zero
    },
    -- 4. Paired empty input -> INSUFFICIENT_DATA
    {
      caseId := "paired_insufficient_empty"
      method := .pairedTCase
      baselineScores := []
      candidateScores := []
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 1
      directPValue := NNRat.one
      directMargin := NNRat.zero
    },
    -- 5. Paired single sample -> INSUFFICIENT_DATA
    {
      caseId := "paired_insufficient_single"
      method := .pairedTCase
      baselineScores := [mkPct 80]
      candidateScores := [mkPct 50]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.one
      directMargin := NNRat.zero
    },
    -- 6. Paired n=2 below min_samples=3 -> INSUFFICIENT_DATA preserving excluded_pair_count
    {
      caseId := "paired_insufficient_below_min_samples"
      method := .pairedTCase
      baselineScores := [mkPct 80, mkPct 90]
      candidateScores := [mkPct 50, mkPct 60]
      confidenceLevel := mkPct 95
      minSamples := 3
      excludedPairCount := 2
      directPValue := NNRat.zero
      directMargin := NNRat.zero
    },
    -- 7. Paired consistent noisy regression (positive variance)
    {
      caseId := "paired_noisy_regression"
      method := .pairedTCase
      baselineScores := [mkPct 90, mkPct 85, mkPct 88, mkPct 92, mkPct 87]
      candidateScores := [mkPct 65, mkPct 63, mkPct 64, mkPct 70, mkPct 65]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 3
      directMargin := mkMicro 17560
    },
    -- 8. Paired consistent noisy improvement (exact baseline/candidate swap of #7)
    {
      caseId := "paired_noisy_improvement"
      method := .pairedTCase
      baselineScores := [mkPct 65, mkPct 63, mkPct 64, mkPct 70, mkPct 65]
      candidateScores := [mkPct 90, mkPct 85, mkPct 88, mkPct 92, mkPct 87]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 3
      directMargin := mkMicro 17560
    },
    -- 9. Paired n=2 wide interval clamped cleanly to [-1, 1]
    {
      caseId := "paired_wide_ci_clamped"
      method := .pairedTCase
      baselineScores := [mkPct 10, mkPct 90]
      candidateScores := [mkPct 90, mkPct 10]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.one
      directMargin := mkMicro 10164964
    },
    -- 10. Paired positive variance with exact zero mean delta -> NOT_SIGNIFICANT
    {
      caseId := "paired_positive_var_zero_delta"
      method := .pairedTCase
      baselineScores := [mkPct 40, mkPct 60, mkPct 50, mkPct 50]
      candidateScores := [mkPct 60, mkPct 40, mkPct 50, mkPct 50]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.one
      directMargin := mkMicro 259846
    },
    -- 11. Welch min(k, m) < min_samples -> INSUFFICIENT_DATA
    {
      caseId := "welch_insufficient_min_samples"
      method := .welchTRun
      baselineScores := [mkPct 80, mkPct 82]
      candidateScores := [mkPct 50, mkPct 52]
      confidenceLevel := mkPct 95
      minSamples := 3
      excludedPairCount := 0
      directPValue := NNRat.one
      directMargin := NNRat.zero
    },
    -- 12. Welch both sides zero variance constant regression -> df = k + m - 2 = 4
    {
      caseId := "welch_both_zero_var_regression"
      method := .welchTRun
      baselineScores := [mkPct 90, mkPct 90, mkPct 90]
      candidateScores := [mkPct 60, mkPct 60, mkPct 60]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.zero
      directMargin := NNRat.zero
    },
    -- 13. Welch one-sided zero variance -> df = m - 1 = 2
    {
      caseId := "welch_one_sided_zero_var_reg"
      method := .welchTRun
      baselineScores := [mkPct 90, mkPct 90, mkPct 90]
      candidateScores := [mkPct 50, mkPct 52, mkPct 51]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 219
      directMargin := mkMicro 24841
    },
    -- 14. Welch unequal n (k=3, m=5) -> exact rational Welch-Satterthwaite df = 100/17
    {
      caseId := "welch_unequal_n_improvement"
      method := .welchTRun
      baselineScores := [mkPct 50, mkPct 52, mkPct 51]
      candidateScores := [mkPct 85, mkPct 88, mkPct 86, mkPct 89, mkPct 87]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := NNRat.zero
      directMargin := mkMicro 22446
    },
    -- 15. Welch noisy overlapping cohorts -> NOT_SIGNIFICANT
    {
      caseId := "welch_noisy_not_significant"
      method := .welchTRun
      baselineScores := [mkPct 50, mkPct 90, mkPct 70]
      candidateScores := [mkPct 60, mkPct 80, mkPct 65]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 906197
      directMargin := mkMicro 413539
    },
    -- 16. One-sample 1 baseline vs 4 candidate runs -> SIGNIFICANT_REGRESSION
    {
      caseId := "one_sample_1_vs_4_regression"
      method := .oneSampleTRun
      baselineScores := [mkPct 90]
      candidateScores := [mkPct 60, mkPct 62, mkPct 61, mkPct 59]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 23
      directMargin := mkMicro 20543
    },
    -- 17. One-sample mirrored 4 baseline vs 1 candidate run -> SIGNIFICANT_IMPROVEMENT
    {
      caseId := "one_sample_4_vs_1_improvement"
      method := .oneSampleTRun
      baselineScores := [mkPct 60, mkPct 62, mkPct 61, mkPct 59]
      candidateScores := [mkPct 90]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 23
      directMargin := mkMicro 20543
    },
    -- 18. One-sample wide CI clamped to [-1, 1] with positive delta
    {
      caseId := "one_sample_wide_ci_clamped"
      method := .oneSampleTRun
      baselineScores := [mkPct 20]
      candidateScores := [mkPct 10, mkPct 90]
      confidenceLevel := mkPct 95
      minSamples := 2
      excludedPairCount := 0
      directPValue := mkMicro 590334
      directMargin := mkMicro 5082482
    }
  ]

private def cohortDispatchMatrixJson : Json :=
  let ks : List Nat := [0, 1, 2, 3]
  let ms : List Nat := [0, 1, 2, 3]
  let rows : List Json :=
    ks.flatMap fun (k : Nat) =>
      ms.map fun (m : Nat) =>
        Json.mkObj [
          ("baseline_run_count", Json.num k),
          ("candidate_run_count", Json.num m),
          ("route", Json.str (dispatchCohortMethod k m).toCanonicalString)
        ]
  Json.arr rows.toArray

private def allSignificanceStatuses : List SignificanceStatus :=
  [.significantImprovement, .significantRegression, .notSignificant, .insufficientData]

private def gateEscalationTruthTableJson : Json :=
  let rows : List Json :=
    allSignificanceStatuses.flatMap fun sig =>
      [false, true].map fun failFlag =>
        let out := evaluateMetricSignificanceChecks [sig] failFlag
        Json.mkObj [
          ("blocking", Json.bool out.blocking),
          ("decision", Json.str out.decision.toCanonicalString),
          ("fail_on_significant_regression", Json.bool failFlag),
          ("passed", Json.bool out.passed),
          ("rule_status", Json.str (statisticalRegressionCheck sig failFlag).toCanonicalString),
          ("significance", Json.str sig.toCanonicalString)
        ]
  Json.arr rows.toArray

private def sharedRowToJson (r : SharedCaseScores) : Json :=
  Json.mkObj [
    ("baseline_metric_present", Json.bool r.baselineMetricPresent),
    ("baseline_score", optNNRatToJson r.baselineScore),
    ("candidate_metric_present", Json.bool r.candidateMetricPresent),
    ("candidate_score", optNNRatToJson r.candidateScore),
    ("case_id", Json.str r.caseId)
  ]

private def alignedPairExtractionToJson (ext : AlignedPairExtraction) : Json :=
  Json.mkObj [
    ("baseline_scores", Json.arr (ext.baselineScores.toArray.map nnratToJson)),
    ("candidate_scores", Json.arr (ext.candidateScores.toArray.map nnratToJson)),
    ("excluded_pair_count", Json.num ext.excludedPairCount)
  ]

private def canonicalAlignedPairVectors : List (String × List SharedCaseScores) :=
  [
    ("pairs_all_numeric", [
      { caseId := "q1", baselineScore := some (mkPct 90), candidateScore := some (mkPct 70),
        baselineMetricPresent := true, candidateMetricPresent := true },
      { caseId := "q2", baselineScore := some (mkPct 80), candidateScore := some (mkPct 60),
        baselineMetricPresent := true, candidateMetricPresent := true }
    ]),
    ("pairs_partial_na_excluded", [
      { caseId := "q1", baselineScore := some (mkPct 100), candidateScore := some (mkPct 70),
        baselineMetricPresent := true, candidateMetricPresent := true },
      { caseId := "na_base", baselineScore := none, candidateScore := some (mkPct 100),
        baselineMetricPresent := true, candidateMetricPresent := true },
      { caseId := "na_cand", baselineScore := some (mkPct 80), candidateScore := none,
        baselineMetricPresent := true, candidateMetricPresent := true },
      { caseId := "missing_both", baselineScore := none, candidateScore := none,
        baselineMetricPresent := false, candidateMetricPresent := false }
    ]),
    ("pairs_all_excluded", [
      { caseId := "x1", baselineScore := none, candidateScore := none,
        baselineMetricPresent := true, candidateMetricPresent := true },
      { caseId := "x2", baselineScore := some (mkPct 50), candidateScore := none,
        baselineMetricPresent := true, candidateMetricPresent := false }
    ]),
    ("pairs_empty", [])
  ]

private def goldenDocumentJson : Json :=
  Json.mkObj [
    ("aligned_pair_vectors", Json.arr (canonicalAlignedPairVectors.toArray.map fun (cid, rows) =>
      Json.mkObj [
        ("case_id", Json.str cid),
        ("expected", alignedPairExtractionToJson (extractAlignedPairs rows)),
        ("shared_rows", Json.arr (rows.toArray.map sharedRowToJson))
      ])),
    ("canonical_vectors", Json.arr (canonicalStatsCases.toArray.map fun c =>
      Json.mkObj [
        ("case_id", Json.str c.caseId),
        ("expected", outcomeToJson (evalStatsCase c)),
        ("input", statsCaseInputToJson c)
      ])),
    ("cohort_dispatch_matrix", cohortDispatchMatrixJson),
    ("gate_escalation_truth_table", gateEscalationTruthTableJson),
    ("lean_toolchain", Json.str leanToolchain),
    ("schema_version", Json.str schemaVersion),
    ("significance_statuses", Json.arr (allSignificanceStatuses.toArray.map fun s => Json.str s.toCanonicalString)),
    ("statistical_methods", Json.arr #[
      Json.str StatisticalMethod.pairedTCase.toCanonicalString,
      Json.str StatisticalMethod.welchTRun.toCanonicalString,
      Json.str StatisticalMethod.oneSampleTRun.toCanonicalString
    ])
  ]

private def parseNatField (obj : Json) (field : String) : Except String Nat := do
  let val ← obj.getObjVal? field
  val.getNat?

private def parseIntField (obj : Json) (field : String) : Except String Int := do
  let val ← obj.getObjVal? field
  val.getInt?

private def parseNNRat (j : Json) (label : String) : Except String NNRat := do
  let num ← parseNatField j "num"
  let den ← parseNatField j "den"
  if h : 0 < den then
    pure ⟨num, den, h⟩
  else
    throw s!"{label}.den must be > 0, got {den}"

private def parseSignedRat (j : Json) (label : String) : Except String SignedRat := do
  let num ← parseIntField j "num"
  let den ← parseNatField j "den"
  if h : 0 < den then
    pure ⟨num, den, h⟩
  else
    throw s!"{label}.den must be > 0, got {den}"

private def parseUnitNNRat (j : Json) (label : String) : Except String NNRat := do
  let r ← parseNNRat j label
  if r.num ≤ r.den then
    pure r
  else
    throw s!"{label} must be in [0, 1], got {r.num}/{r.den}"

private def parseOpenUnitNNRat (j : Json) (label : String) : Except String NNRat := do
  let r ← parseNNRat j label
  if 0 < r.num && r.num < r.den then
    pure r
  else
    throw s!"{label} must be strictly in (0, 1), got {r.num}/{r.den}"

private def parseOptNNRat (obj : Json) (field : String) : Except String (Option NNRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseNNRat val field

private def parseOptUnitNNRat (obj : Json) (field : String) : Except String (Option NNRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseUnitNNRat val field

private def parseOptSignedRat (obj : Json) (field : String) : Except String (Option SignedRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseSignedRat val field

private def parseMethod (s : String) : Except String StatisticalMethod :=
  match StatisticalMethod.ofCanonicalString? s with
  | some m => pure m
  | none => throw s!"Unsupported statistical method: '{s}'"

private def parseSignificance (s : String) : Except String SignificanceStatus :=
  match SignificanceStatus.ofCanonicalString? s with
  | some st => pure st
  | none => throw s!"Unsupported significance status: '{s}'"

private def handleStatsCase (j : Json) : Except String Json := do
  let cid ← (← j.getObjVal? "case_id").getStr?
  let methodStr ← (← j.getObjVal? "method").getStr?
  let method ← parseMethod methodStr
  let conf ← parseOpenUnitNNRat (← j.getObjVal? "confidence_level") "confidence_level"
  let minSamples ← parseNatField j "min_samples"
  let excl ← parseNatField j "excluded_pair_count"
  let baseArr ← (← j.getObjVal? "baseline_scores").getArr?
  let candArr ← (← j.getObjVal? "candidate_scores").getArr?
  let baseScores ← baseArr.toList.mapM (fun x => parseUnitNNRat x "baseline_score")
  let candScores ← candArr.toList.mapM (fun x => parseUnitNNRat x "candidate_score")
  let directP ← parseUnitNNRat (← j.getObjVal? "direct_p_value") "direct_p_value"
  let directM ← parseNNRat (← j.getObjVal? "direct_margin") "direct_margin"
  match method with
  | .pairedTCase =>
    if baseScores.length != candScores.length then
      throw s!"paired_t_case requires equal lengths, got {baseScores.length} vs {candScores.length}"
  | .oneSampleTRun =>
    let k := baseScores.length
    let m := candScores.length
    if !((k == 1 && m >= 2) || (m == 1 && k >= 2)) then
      throw s!"one_sample_t_run requires one single-run side and one >=2-run side, got ({k}, {m})"
  | .welchTRun => pure ()
  let req : StatsCaseInput := {
    caseId := cid
    method := method
    baselineScores := baseScores
    candidateScores := candScores
    confidenceLevel := conf
    minSamples := minSamples
    excludedPairCount := excl
    directPValue := directP
    directMargin := directM
  }
  pure (outcomeToJson (evalStatsCase req))

private def handleFinalizeDirect (j : Json) : Except String Json := do
  let methodStr ← (← j.getObjVal? "method").getStr?
  let method ← parseMethod methodStr
  let conf ← parseOpenUnitNNRat (← j.getObjVal? "confidence_level") "confidence_level"
  let sampleSize ← parseNatField j "sample_size"
  let baseSize ← parseNatField j "baseline_sample_size"
  let candSize ← parseNatField j "candidate_sample_size"
  let excl ← parseNatField j "excluded_pair_count"
  let meanD ← parseOptSignedRat j "mean_delta"
  let seSq ← parseOptNNRat j "se_sq"
  let dfVal ← parseOptNNRat j "df"
  let effVar ← parseOptNNRat j "effect_denom_var"
  let hasEnough ← (← j.getObjVal? "has_enough_samples").getBool?
  let directP ← parseUnitNNRat (← j.getObjVal? "direct_p_value") "direct_p_value"
  let directM ← parseNNRat (← j.getObjVal? "direct_margin") "direct_margin"
  let inp : InferenceInput := {
    method := method
    confidenceLevel := conf
    sampleSize := sampleSize
    baselineSampleSize := baseSize
    candidateSampleSize := candSize
    excludedPairCount := excl
    meanDelta := meanD
    seSq := seSq
    df := dfVal
    effectDenomVar := effVar
    hasEnoughSamples := hasEnough
  }
  pure (outcomeToJson (finalizeInferenceDirect inp directP directM))

private def handleCohortDispatch (j : Json) : Except String Json := do
  let k ← parseNatField j "baseline_run_count"
  let m ← parseNatField j "candidate_run_count"
  pure (Json.mkObj [("route", Json.str (dispatchCohortMethod k m).toCanonicalString)])

private def handleAlignedPairs (j : Json) : Except String Json := do
  let rowsArr ← (← j.getObjVal? "shared_rows").getArr?
  let rows ← rowsArr.toList.mapM fun r => do
    let cid ← (← r.getObjVal? "case_id").getStr?
    let bs ← parseOptUnitNNRat r "baseline_score"
    let cs ← parseOptUnitNNRat r "candidate_score"
    let bp ← (← r.getObjVal? "baseline_metric_present").getBool?
    let cp ← (← r.getObjVal? "candidate_metric_present").getBool?
    pure {
      caseId := cid
      baselineScore := bs
      candidateScore := cs
      baselineMetricPresent := bp
      candidateMetricPresent := cp
    }
  pure (alignedPairExtractionToJson (extractAlignedPairs rows))

private def handleGateBridge (j : Json) : Except String Json := do
  let arr ← (← j.getObjVal? "statuses").getArr?
  let statuses ← arr.toList.mapM fun item => do
    let s ← item.getStr?
    parseSignificance s
  let failFlag ← (← j.getObjVal? "fail_on_significant_regression").getBool?
  let out := evaluateMetricSignificanceChecks statuses failFlag
  pure (Json.mkObj [
    ("blocking", Json.bool out.blocking),
    ("decision", Json.str out.decision.toCanonicalString),
    ("passed", Json.bool out.passed)
  ])

private def evalStdinRequest (raw : String) : Except String Json := do
  let j ← Json.parse raw
  let kind ← (← j.getObjVal? "kind").getStr?
  match kind with
  | "stats_case" => handleStatsCase j
  | "finalize_direct" => handleFinalizeDirect j
  | "cohort_dispatch" => handleCohortDispatch j
  | "aligned_pairs" => handleAlignedPairs j
  | "gate_bridge" => handleGateBridge j
  | other => throw s!"Unsupported request kind: '{other}'"

def main (args : List String) : IO UInt32 := do
  match args with
  | ["export-golden"] =>
    IO.println goldenDocumentJson.pretty
    return 0
  | ["eval-stdin"] =>
    let stdin ← IO.getStdin
    let raw ← stdin.readToEnd
    match evalStdinRequest raw with
    | .ok resp =>
      IO.println resp.pretty
      return 0
    | .error err =>
      IO.eprintln s!"evalforge-stats-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-stats-oracle <export-golden|eval-stdin>"
    return 1
