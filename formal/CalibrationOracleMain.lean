import Lean.Data.Json
import EvalForgeFormal.Calibration.Aggregation

open Lean
open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private def mkPct (n : Nat) : NNRat := ⟨n, 100, by omega⟩

private structure CalibrationCaseInput where
  caseId : String
  config : CalibrationConfig
  samples : List CalibrationSample

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

private def optBoolToJson : Option Bool → Json
  | some b => Json.bool b
  | none => Json.null

private def sampleInputToJson (s : CalibrationSample) : Json :=
  Json.mkObj [
    ("case_id", Json.str s.caseId),
    ("human_passed", optBoolToJson s.humanPassed),
    ("human_score", optNNRatToJson s.humanScore),
    ("judge_score", optNNRatToJson s.judgeScore),
    ("judge_status", Json.str s.judgeStatus.toCanonicalString)
  ]

private def disagreementRecordToJson (d : DisagreementRecord) : Json :=
  Json.mkObj [
    ("case_id", Json.str d.caseId),
    ("disagreement_type", Json.str d.disagreementType.toCanonicalString),
    ("human_passed", Json.bool d.humanPassed),
    ("judge_passed", optBoolToJson d.judgePassed),
    ("judge_status", Json.str d.judgeStatus.toCanonicalString),
    ("score_delta_exact", optSignedRatToJson d.scoreDelta)
  ]

private def evalCalibrationCaseToJson (c : CalibrationCaseInput) : Json :=
  let summary := aggregateCalibration c.config c.samples
  let validRows := collectValidRows (c.samples.map (classifySample c.config))
  let candGrid : List NNRat :=
    if validRows.isEmpty then [] else buildCandidates validRows c.config.passThreshold
  Json.mkObj [
    ("agreed_count", Json.num summary.agreedCount),
    ("candidate_grid", Json.arr (candGrid.toArray.map nnratToJson)),
    ("disagreements", Json.arr (summary.disagreements.toArray.map disagreementRecordToJson)),
    ("exact_agreement_rate_exact", optNNRatToJson summary.exactAgreementRate),
    ("inconclusive_cases", Json.num summary.inconclusiveCases),
    ("mean_human_score_exact", optNNRatToJson summary.meanHumanScore),
    ("mean_judge_score_exact", optNNRatToJson summary.meanJudgeScore),
    ("mean_score_delta_exact", optSignedRatToJson summary.meanScoreDelta),
    ("recommended_pass_threshold_exact", nnratToJson summary.recommendedPassThreshold),
    ("too_generous_count", Json.num summary.tooGenerousCount),
    ("too_generous_rate_exact", optNNRatToJson summary.tooGenerousRate),
    ("too_harsh_count", Json.num summary.tooHarshCount),
    ("too_harsh_rate_exact", optNNRatToJson summary.tooHarshRate),
    ("total_cases", Json.num summary.totalCases),
    ("valid_cases", Json.num summary.validCases)
  ]

private def caseInputToJson (c : CalibrationCaseInput) : Json :=
  Json.mkObj [
    ("case_id", Json.str c.caseId),
    ("human_threshold", nnratToJson c.config.humanThreshold),
    ("pass_threshold", nnratToJson c.config.passThreshold),
    ("samples", Json.arr (c.samples.toArray.map sampleInputToJson)),
    ("score_divergence_threshold", nnratToJson c.config.scoreDivergenceThreshold)
  ]

private def mkCfg (passPct humanPct divPct : Nat) : CalibrationConfig :=
  {
    passThreshold := mkPct passPct
    humanThreshold := mkPct humanPct
    scoreDivergenceThreshold := mkPct divPct
  }

/-- 16 canonical conformance vectors per `contracts/formal-calibration-oracle-and-theorems.md`. -/
private def canonicalCases : List CalibrationCaseInput :=
  [
    -- 1. Too-generous bias raises threshold from 0.50 to 0.75
    {
      caseId := "cal_too_generous_midpoint_raise"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "c1", humanScore := some (mkPct 20), humanPassed := some false,
          judgeScore := some (mkPct 55), judgeStatus := .pass },
        { caseId := "c2", humanScore := some (mkPct 30), humanPassed := some false,
          judgeScore := some (mkPct 65), judgeStatus := .pass },
        { caseId := "c3", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 85), judgeStatus := .pass },
        { caseId := "c4", humanScore := some (mkPct 95), humanPassed := some true,
          judgeScore := some (mkPct 90), judgeStatus := .pass }
      ]
    },
    -- 2. Too-harsh bias lowers threshold from 0.60 to 0.35 (human_passed only)
    {
      caseId := "cal_too_harsh_threshold_lower"
      config := mkCfg 60 60 25
      samples := [
        { caseId := "h1", humanScore := none, humanPassed := some false,
          judgeScore := some (mkPct 15), judgeStatus := .fail },
        { caseId := "h2", humanScore := none, humanPassed := some true,
          judgeScore := some (mkPct 35), judgeStatus := .fail },
        { caseId := "h3", humanScore := none, humanPassed := some true,
          judgeScore := some (mkPct 45), judgeStatus := .fail },
        { caseId := "h4", humanScore := none, humanPassed := some true,
          judgeScore := some (mkPct 80), judgeStatus := .pass }
      ]
    },
    -- 3. Same-verdict SCORE_DIVERGENCE preserves 100% agreement & 0 bias
    {
      caseId := "cal_score_divergence_preserves_agreement"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "s1", humanScore := some (mkPct 95), humanPassed := some true,
          judgeScore := some (mkPct 55), judgeStatus := .pass },
        { caseId := "s2", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 90), judgeStatus := .pass }
      ]
    },
    -- 4. Exact boundary |judge - human| == score_divergence_threshold does NOT flag divergence
    {
      caseId := "cal_score_divergence_exact_boundary_no_flag"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "b1", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := some (mkPct 55), judgeStatus := .pass },
        { caseId := "b2", humanScore := some (mkPct 20), humanPassed := some false,
          judgeScore := some (mkPct 45), judgeStatus := .fail }
      ]
    },
    -- 5. Authoritative human_passed=false overrides high human_score=0.85
    {
      caseId := "cal_authoritative_human_passed_false_override"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "af1", humanScore := some (mkPct 85), humanPassed := some false,
          judgeScore := some (mkPct 70), judgeStatus := .pass }
      ]
    },
    -- 6. Authoritative human_passed=true overrides low human_score=0.15
    {
      caseId := "cal_authoritative_human_passed_true_override"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "at1", humanScore := some (mkPct 15), humanPassed := some true,
          judgeScore := some (mkPct 30), judgeStatus := .fail }
      ]
    },
    -- 7. Score-derived human_passed with custom human_threshold=0.70 (<, ==, >)
    {
      caseId := "cal_score_derived_human_passed_custom_threshold"
      config := mkCfg 50 70 25
      samples := [
        { caseId := "d1", humanScore := some (mkPct 65), humanPassed := none,
          judgeScore := some (mkPct 40), judgeStatus := .fail },
        { caseId := "d2", humanScore := some (mkPct 70), humanPassed := none,
          judgeScore := some (mkPct 60), judgeStatus := .pass },
        { caseId := "d3", humanScore := some (mkPct 85), humanPassed := none,
          judgeScore := some (mkPct 45), judgeStatus := .fail }
      ]
    },
    -- 8. Mixed INCONCLUSIVE, NOT_APPLICABLE, WARNING with score=none, and valid rows
    {
      caseId := "cal_mixed_inconclusive_not_applicable_and_none_score"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "m1", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := none, judgeStatus := .inconclusive },
        { caseId := "m2", humanScore := none, humanPassed := some false,
          judgeScore := none, judgeStatus := .notApplicable },
        { caseId := "m3", humanScore := some (mkPct 60), humanPassed := none,
          judgeScore := none, judgeStatus := .warning },
        { caseId := "m4", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 80), judgeStatus := .pass }
      ]
    },
    -- 9. All samples inconclusive/NA -> valid_cases=0 zero-divisor guard
    {
      caseId := "cal_all_inconclusive_zero_valid_guard"
      config := mkCfg 65 50 25
      samples := [
        { caseId := "z1", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := none, judgeStatus := .inconclusive },
        { caseId := "z2", humanScore := none, humanPassed := some false,
          judgeScore := none, judgeStatus := .notApplicable }
      ]
    },
    -- 10. Single valid sample at exact pass_threshold boundary (judge_score == pass_threshold)
    {
      caseId := "cal_single_valid_sample_exact_pass_boundary"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "e1", humanScore := some (mkPct 50), humanPassed := none,
          judgeScore := some (mkPct 50), judgeStatus := .pass }
      ]
    },
    -- 11. Duplicate judge scores (0.50) with conflicting human labels
    {
      caseId := "cal_duplicate_judge_scores_conflict"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "dup1", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 50), judgeStatus := .pass },
        { caseId := "dup2", humanScore := some (mkPct 10), humanPassed := some false,
          judgeScore := some (mkPct 50), judgeStatus := .pass },
        { caseId := "dup3", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := some (mkPct 50), judgeStatus := .pass }
      ]
    },
    -- 12. Equidistant 2-winner tie ([0.20, 1.00] around active=0.60) -> midpoint 0.60 fails -> 1.00
    {
      caseId := "cal_equidistant_two_winners_fallback_to_last"
      config := mkCfg 60 60 25
      samples := [
        { caseId := "eq1", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := some (mkPct 20), judgeStatus := .fail },
        { caseId := "eq2", humanScore := some (mkPct 20), humanPassed := some false,
          judgeScore := some (mkPct 80), judgeStatus := .pass }
      ]
    },
    -- 13. Boundary pass_threshold = 0.0
    {
      caseId := "cal_boundary_threshold_zero"
      config := mkCfg 0 50 25
      samples := [
        { caseId := "tz1", humanScore := some (mkPct 0), humanPassed := some false,
          judgeScore := some (mkPct 0), judgeStatus := .pass },
        { caseId := "tz2", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := some (mkPct 60), judgeStatus := .pass }
      ]
    },
    -- 14. Boundary pass_threshold = 1.0
    {
      caseId := "cal_boundary_threshold_one"
      config := mkCfg 100 50 25
      samples := [
        { caseId := "to1", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 100), judgeStatus := .pass },
        { caseId := "to2", humanScore := some (mkPct 40), humanPassed := some false,
          judgeScore := some (mkPct 80), judgeStatus := .fail }
      ]
    },
    -- 15. Balanced bias-skew tiebreak: max_agree tied across candidates, min |gen - harsh| wins
    {
      caseId := "cal_balanced_bias_skew_tiebreak"
      config := mkCfg 50 50 25
      samples := [
        { caseId := "bs1", humanScore := some (mkPct 80), humanPassed := some true,
          judgeScore := some (mkPct 20), judgeStatus := .fail },
        { caseId := "bs2", humanScore := some (mkPct 20), humanPassed := some false,
          judgeScore := some (mkPct 60), judgeStatus := .pass },
        { caseId := "bs3", humanScore := some (mkPct 85), humanPassed := some true,
          judgeScore := some (mkPct 90), judgeStatus := .pass }
      ]
    },
    -- 16. Distance tiebreak closer to active_threshold when (max_agree, min_bias_skew) tie
    {
      caseId := "cal_distance_tiebreak_closer_to_active"
      config := mkCfg 80 50 25
      samples := [
        { caseId := "dt1", humanScore := some (mkPct 20), humanPassed := some false,
          judgeScore := some (mkPct 20), judgeStatus := .fail },
        { caseId := "dt2", humanScore := some (mkPct 90), humanPassed := some true,
          judgeScore := some (mkPct 70), judgeStatus := .fail }
      ]
    }
  ]

private def goldenDocumentJson : Json :=
  let vectors := canonicalCases.toArray.map fun c =>
    Json.mkObj [
      ("expected", evalCalibrationCaseToJson c),
      ("input", caseInputToJson c)
    ]
  Json.mkObj [
    ("canonical_vectors", Json.arr vectors),
    ("disagreement_types", Json.arr #[
      Json.str "too_generous",
      Json.str "too_harsh",
      Json.str "score_divergence",
      Json.str "inconclusive"
    ]),
    ("lean_toolchain", Json.str leanToolchain),
    ("schema_version", Json.str schemaVersion)
  ]

private def parseNatField (obj : Json) (field : String) : Except String Nat := do
  let val ← obj.getObjVal? field
  val.getNat?

private def parseNNRat (j : Json) (label : String) : Except String NNRat := do
  let num ← parseNatField j "num"
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

private def parsePosUnitNNRat (j : Json) (label : String) : Except String NNRat := do
  let r ← parseUnitNNRat j label
  if 0 < r.num then
    pure r
  else
    throw s!"{label} must be in (0, 1], got {r.num}/{r.den}"

private def parseOptUnitNNRat (obj : Json) (field : String) : Except String (Option NNRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then
    pure none
  else
    let r ← parseUnitNNRat val field
    pure (some r)

private def parseOptBool (obj : Json) (field : String) : Except String (Option Bool) := do
  let val ← obj.getObjVal? field
  if val.isNull then
    pure none
  else
    let b ← val.getBool?
    pure (some b)

private def parseJudgeStatus (s : String) : Except String JudgeStatus :=
  match s with
  | "PASS" => pure .pass
  | "FAIL" => pure .fail
  | "WARNING" => pure .warning
  | "INCONCLUSIVE" => pure .inconclusive
  | "NOT_APPLICABLE" => pure .notApplicable
  | other => throw s!"Unsupported judge_status: '{other}'"

private def parseSample (j : Json) : Except String CalibrationSample := do
  let cid ← (← j.getObjVal? "case_id").getStr?
  if cid.isEmpty || cid.all Char.isWhitespace then
    throw "Sample case_id must be a non-empty string"
  let hScore ← parseOptUnitNNRat j "human_score"
  let hPassed ← parseOptBool j "human_passed"
  if hScore.isNone && hPassed.isNone then
    throw s!"Sample '{cid}' requires at least one of human_score or human_passed"
  let jScore ← parseOptUnitNNRat j "judge_score"
  let jStatusStr ← (← j.getObjVal? "judge_status").getStr?
  let jStatus ← parseJudgeStatus jStatusStr
  pure {
    caseId := cid
    humanScore := hScore
    humanPassed := hPassed
    judgeScore := jScore
    judgeStatus := jStatus
  }

private def checkUniqueIds (seen : List String) : List CalibrationSample → Except String Unit
  | [] => pure ()
  | s :: rest =>
    if seen.contains s.caseId then
      throw s!"Duplicate sample case_id: '{s.caseId}'"
    else
      checkUniqueIds (s.caseId :: seen) rest

private def parseCalibrationRequest (raw : String) : Except String CalibrationCaseInput := do
  let j ← Json.parse raw
  let cid ← (← j.getObjVal? "case_id").getStr?
  if cid.isEmpty || cid.all Char.isWhitespace then
    throw "case_id must be a non-empty string"
  let passT ← parseUnitNNRat (← j.getObjVal? "pass_threshold") "pass_threshold"
  let humanT ← parseUnitNNRat (← j.getObjVal? "human_threshold") "human_threshold"
  let divT ← parsePosUnitNNRat (← j.getObjVal? "score_divergence_threshold") "score_divergence_threshold"
  let samplesArr ← (← j.getObjVal? "samples").getArr?
  if samplesArr.isEmpty then
    throw "samples must be a non-empty array"
  let samples ← samplesArr.toList.mapM parseSample
  checkUniqueIds [] samples
  pure {
    caseId := cid
    config := {
      passThreshold := passT
      humanThreshold := humanT
      scoreDivergenceThreshold := divT
    }
    samples := samples
  }

def main (args : List String) : IO UInt32 := do
  match args with
  | ["export-golden"] =>
    IO.println goldenDocumentJson.pretty
    return 0
  | ["eval-stdin"] =>
    let stdin ← IO.getStdin
    let raw ← stdin.readToEnd
    match parseCalibrationRequest raw with
    | .ok req =>
      IO.println (evalCalibrationCaseToJson req).pretty
      return 0
    | .error err =>
      IO.eprintln s!"evalforge-calibration-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-calibration-oracle <export-golden|eval-stdin>"
    return 1
