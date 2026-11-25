import EvalForgeFormal.Calibration.ThresholdOptimizer

namespace EvalForgeFormal.Calibration

open EvalForgeFormal.Retrieval

/--
Derive human pass verdict matching `acalibrate_judge` (`calibration.py#L263-L270`):
explicit `humanPassed` always takes precedence; otherwise `humanScore ≥ humanThreshold`
(returning `false` if both are `none`).
-/
def deriveHumanPassed (humanScore : Option NNRat) (humanPassed : Option Bool)
    (humanThreshold : NNRat) : Bool :=
  match humanPassed with
  | some b => b
  | none =>
    match humanScore with
    | some hs => decide (humanThreshold ≤ hs)
    | none => false

/--
Derive numeric human score matching `acalibrate_judge` (`calibration.py#L271-L275`):
uses `humanScore` when present, else `1` if `humanPassed` and `0` otherwise.
-/
def deriveHumanNumeric (humanScore : Option NNRat) (humanPassed : Bool) : NNRat :=
  match humanScore with
  | some hs => hs
  | none => if humanPassed then NNRat.one else NNRat.zero

/-- True iff the judge outcome is excluded from valid calibration scoring (`calibration.py#L277-L280`). -/
def isJudgeExcluded (judgeScore : Option NNRat) (judgeStatus : JudgeStatus) : Bool :=
  judgeScore.isNone || judgeStatus.isExcluded

/-- Mutually exclusive, exhaustive 5-way per-sample calibration classification. -/
inductive SampleClassification where
  | excluded (rec : DisagreementRecord)
  | tooGenerous (row : ValidRow) (rec : DisagreementRecord)
  | tooHarsh (row : ValidRow) (rec : DisagreementRecord)
  | agreedDivergent (row : ValidRow) (rec : DisagreementRecord)
  | agreedExact (row : ValidRow)
  deriving DecidableEq, Repr

/-- Classify a single calibration sample under `cfg`, matching `calibration.py#L262-L332`. -/
def classifySample (cfg : CalibrationConfig) (s : CalibrationSample) : SampleClassification :=
  let hPassed := deriveHumanPassed s.humanScore s.humanPassed cfg.humanThreshold
  let hNumeric := deriveHumanNumeric s.humanScore hPassed
  match s.judgeScore with
  | none =>
    .excluded {
      caseId := s.caseId
      disagreementType := .inconclusive
      humanPassed := hPassed
      judgeStatus := s.judgeStatus
      judgePassed := none
      scoreDelta := none
    }
  | some jScore =>
    if s.judgeStatus.isExcluded then
      .excluded {
        caseId := s.caseId
        disagreementType := .inconclusive
        humanPassed := hPassed
        judgeStatus := s.judgeStatus
        judgePassed := none
        scoreDelta := none
      }
    else
      let jPassed := decide (cfg.passThreshold ≤ jScore)
      let delta := SignedRat.normalize (SignedRat.subNNRat jScore hNumeric)
      let row : ValidRow := {
        humanNumeric := hNumeric
        judgeScore := jScore
        humanPassed := hPassed
      }
      if jPassed && !hPassed then
        .tooGenerous row {
          caseId := s.caseId
          disagreementType := .tooGenerous
          humanPassed := hPassed
          judgeStatus := s.judgeStatus
          judgePassed := some jPassed
          scoreDelta := some delta
        }
      else if !jPassed && hPassed then
        .tooHarsh row {
          caseId := s.caseId
          disagreementType := .tooHarsh
          humanPassed := hPassed
          judgeStatus := s.judgeStatus
          judgePassed := some jPassed
          scoreDelta := some delta
        }
      else
        let isDivergent : Bool :=
          match s.humanScore with
          | some hs => decide (cfg.scoreDivergenceThreshold < nnAbsDiff jScore hs)
          | none => false
        if isDivergent then
          .agreedDivergent row {
            caseId := s.caseId
            disagreementType := .scoreDivergence
            humanPassed := hPassed
            judgeStatus := s.judgeStatus
            judgePassed := some jPassed
            scoreDelta := some delta
          }
        else
          .agreedExact row

/-- Extract the valid row list from classified samples in input order. -/
def collectValidRows : List SampleClassification → List ValidRow
  | [] => []
  | .excluded _ :: rest => collectValidRows rest
  | .tooGenerous r _ :: rest => r :: collectValidRows rest
  | .tooHarsh r _ :: rest => r :: collectValidRows rest
  | .agreedDivergent r _ :: rest => r :: collectValidRows rest
  | .agreedExact r :: rest => r :: collectValidRows rest

/-- Extract disagreement records from classified samples in input order. -/
def collectDisagreements : List SampleClassification → List DisagreementRecord
  | [] => []
  | .excluded d :: rest => d :: collectDisagreements rest
  | .tooGenerous _ d :: rest => d :: collectDisagreements rest
  | .tooHarsh _ d :: rest => d :: collectDisagreements rest
  | .agreedDivergent _ d :: rest => d :: collectDisagreements rest
  | .agreedExact _ :: rest => collectDisagreements rest

/-- Count inconclusive/excluded classified samples. -/
def countInconclusive : List SampleClassification → Nat
  | [] => 0
  | .excluded _ :: rest => countInconclusive rest + 1
  | _ :: rest => countInconclusive rest

/-- Count valid agreed classified samples (both `agreedExact` and `agreedDivergent`). -/
def countAgreed : List SampleClassification → Nat
  | [] => 0
  | .agreedExact _ :: rest => countAgreed rest + 1
  | .agreedDivergent _ _ :: rest => countAgreed rest + 1
  | _ :: rest => countAgreed rest

/-- Count valid `tooGenerous` classified samples. -/
def countTooGenerous : List SampleClassification → Nat
  | [] => 0
  | .tooGenerous _ _ :: rest => countTooGenerous rest + 1
  | _ :: rest => countTooGenerous rest

/-- Count valid `tooHarsh` classified samples. -/
def countTooHarsh : List SampleClassification → Nat
  | [] => 0
  | .tooHarsh _ _ :: rest => countTooHarsh rest + 1
  | _ :: rest => countTooHarsh rest

/--
Aggregate all calibration counts, exact rational rates/means/deltas, disagreements, and
recommended pass threshold matching `acalibrate_judge` (`calibration.py#L255-L382`).
-/
def aggregateCalibration (cfg : CalibrationConfig) (samples : List CalibrationSample) :
    CalibrationSummary :=
  let classified := samples.map (classifySample cfg)
  let validRows := collectValidRows classified
  let disagreements := collectDisagreements classified
  let total := samples.length
  let valid := validRows.length
  let inconc := countInconclusive classified
  let agreed := countAgreed classified
  let generous := countTooGenerous classified
  let harsh := countTooHarsh classified
  if hValid : valid = 0 then
    {
      totalCases := total
      validCases := 0
      inconclusiveCases := inconc
      agreedCount := agreed
      tooGenerousCount := generous
      tooHarshCount := harsh
      exactAgreementRate := none
      tooGenerousRate := none
      tooHarshRate := none
      meanHumanScore := none
      meanJudgeScore := none
      meanScoreDelta := none
      disagreements := disagreements
      recommendedPassThreshold := NNRat.normalize cfg.passThreshold
    }
  else
    have hPos : 0 < valid := Nat.pos_of_ne_zero hValid
    have hHumanPos : 0 < (validRows.map (·.humanNumeric)).length := by
      simpa [valid] using hPos
    have hJudgePos : 0 < (validRows.map (·.judgeScore)).length := by
      simpa [valid] using hPos
    let meanHuman := nnMeanList (validRows.map (·.humanNumeric)) hHumanPos
    let meanJudge := nnMeanList (validRows.map (·.judgeScore)) hJudgePos
    let meanDelta := SignedRat.normalize (SignedRat.subNNRat meanJudge meanHuman)
    {
      totalCases := total
      validCases := valid
      inconclusiveCases := inconc
      agreedCount := agreed
      tooGenerousCount := generous
      tooHarshCount := harsh
      exactAgreementRate := some (NNRat.normalize ⟨agreed * 100, valid, hPos⟩)
      tooGenerousRate := some (NNRat.normalize ⟨generous, valid, hPos⟩)
      tooHarshRate := some (NNRat.normalize ⟨harsh, valid, hPos⟩)
      meanHumanScore := some (NNRat.normalize meanHuman)
      meanJudgeScore := some (NNRat.normalize meanJudge)
      meanScoreDelta := some meanDelta
      disagreements := disagreements
      recommendedPassThreshold := optimizePassThreshold validRows cfg.passThreshold
    }

end EvalForgeFormal.Calibration
