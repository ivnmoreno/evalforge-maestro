import EvalForgeFormal.Regression.Types

namespace EvalForgeFormal.Regression

open EvalForgeFormal.Retrieval (NNRat)
open EvalForgeFormal.Calibration (SignedRat nnAbsDiff nnMeanList)
open EvalForgeFormal.Stats (ofNNRat sNeg sLe sLt sMeanList)

/-! ## Exact Non-Negative List Extrema & Disagreement Spread -/

/-- Running minimum over `List NNRat` seeded by `cur`. -/
def listMinAux (cur : NNRat) : List NNRat → NNRat
  | [] => cur
  | x :: xs => listMinAux (if NNRat.leBool x cur then x else cur) xs

/-- Running maximum over `List NNRat` seeded by `cur`. -/
def listMaxAux (cur : NNRat) : List NNRat → NNRat
  | [] => cur
  | x :: xs => listMaxAux (if NNRat.leBool cur x then x else cur) xs

/-- Exact rational spread `max(scores) - min(scores)` for `len ≥ 2`, else `0`. -/
def scoreSpread : List NNRat → NNRat
  | [] => NNRat.zero
  | [_] => NNRat.zero
  | x :: y :: rest => nnAbsDiff (listMaxAux x (y :: rest)) (listMinAux x (y :: rest))

/-- Exact rational `1 / 2` (`0.5`), the macro passing threshold in `anomaly.py:106`. -/
def halfNNRat : NNRat := ⟨1, 2, by omega⟩

/-- Lookup an `NNRat` entry by metric ID in an association list. -/
def lookupNNRat : List (String × NNRat) → String → Option NNRat
  | [], _ => none
  | (k, v) :: rest, target => if k = target then some v else lookupNNRat rest target

/-- Lookup an `AnomalyMetricDelta` by metric ID. -/
def lookupMetricDelta : List AnomalyMetricDelta → String → Option AnomalyMetricDelta
  | [], _ => none
  | m :: rest, target => if m.metricId = target then some m else lookupMetricDelta rest target

/-- Lookup an `AnomalyCaseSummary` by case ID. -/
def lookupCaseSummary : List AnomalyCaseSummary → String → Option AnomalyCaseSummary
  | [], _ => none
  | c :: rest, target => if c.caseId = target then some c else lookupCaseSummary rest target

/-- Extract numeric `(metricId, score)` pairs from an optional score list. -/
def extractNumericPairs (pairs : List (String × Option NNRat)) : List (String × NNRat) :=
  pairs.filterMap fun (mid, optS) => optS.map fun s => (mid, s)

/-! ## Disagreement Detection (`_check_disagreements`, `anomaly.py#L18-L73`) -/

/-- Check inter-metric disagreement for a single score list (case or run scope). -/
def checkScoreListDisagreement
    (scope : AnomalyScope)
    (caseId : Option String)
    (pairs : List (String × Option NNRat))
    (threshold : NNRat) : Option AnomalyFlagSpec :=
  let numericPairs := extractNumericPairs pairs
  if numericPairs.length ≥ 2 then
    let scores := numericPairs.map Prod.snd
    let spread := scoreSpread scores
    if decide (threshold < spread) then
      some {
        anomalyType := .metricDisagreement
        severity := .warning
        scope := scope
        caseId := caseId
        metricIds := numericPairs.map Prod.fst
        spread := some (ofNNRat spread)
      }
    else
      none
  else
    none

/-- Check inter-metric disagreement for a single case summary. -/
def checkCaseDisagreement (c : AnomalyCaseSummary) (threshold : NNRat) : Option AnomalyFlagSpec :=
  checkScoreListDisagreement .case (some c.caseId) c.metricScores threshold

/-- Check inter-metric disagreement across run-level aggregate metric scores. -/
def checkRunDisagreement (run : AnomalyRunSummary) (threshold : NNRat) : Option AnomalyFlagSpec :=
  checkScoreListDisagreement .run none run.aggregates threshold

/-- Formal model of `_check_disagreements` (`anomaly.py#L18-L73`). -/
def checkDisagreements (run : AnomalyRunSummary) (threshold : NNRat) : List AnomalyFlagSpec :=
  let caseFlags := run.cases.filterMap fun c =>
    checkCaseDisagreement c threshold
  let runFlag :=
    match checkRunDisagreement run threshold with
    | some f => [f]
    | none => []
  caseFlags ++ runFlag

/-! ## Mandatory Failure & Anti-Masking Detection (`anomaly.py#L76-L203`) -/

/-- Emit unconditional `FAIL`-severity `MANDATORY_CASE_FAILURE` flags (`anomaly.py#L84-L100`). -/
def checkMandatoryFailures (run : AnomalyRunSummary) : List AnomalyFlagSpec :=
  run.mandatoryFailedCaseIds.map fun cid =>
    let failedMetrics :=
      match lookupCaseSummary run.cases cid with
      | some c => c.failedMetrics
      | none => []
    {
      anomalyType := .mandatoryCaseFailure
      severity := .fail
      scope := .case
      caseId := some cid
      metricIds := failedMetrics
      spread := none
    }

/-- Macro arithmetic mean over all non-null aggregate metric scores (`anomaly.py#L102-L105`). -/
def runMacroMean (run : AnomalyRunSummary) : Option NNRat :=
  let aggScores := (extractNumericPairs run.aggregates).map Prod.snd
  if h : 0 < aggScores.length then
    some (nnMeanList aggScores h)
  else
    none

/-- Returns `true` iff macro aggregate mean exists and is `≥ 1/2` (`anomaly.py#L106`). -/
def isMacroPassing (run : AnomalyRunSummary) : Bool :=
  match runMacroMean run with
  | some m => NNRat.leBool halfNNRat m
  | none => false

/-- Emit `AGGREGATE_MASKED_DROP` when passing macro average masks mandatory failures (`anomaly.py#L109-L122`). -/
def checkMacroMaskedMandatory (run : AnomalyRunSummary) : List AnomalyFlagSpec :=
  match runMacroMean run with
  | some m =>
    if NNRat.leBool halfNNRat m && !run.mandatoryFailedCaseIds.isEmpty then
      [{
        anomalyType := .aggregateMaskedDrop
        severity := .warning
        scope := .run
        caseId := none
        metricIds := run.aggregates.map Prod.fst
        spread := some (ofNNRat m)
      }]
    else
      []
  | none => []

/-- Resolve effective minimum score floor for `metricId` (`policy.minMetricScores[m] ?? policy.minScore`). -/
def resolveMetricFloor (policy : AnomalyPolicy) (metricId : String) : Option NNRat :=
  match lookupNNRat policy.minMetricScores metricId with
  | some f => some f
  | none => policy.minScore

/-- Emit `AGGREGATE_MASKED_DROP` when passing macro average masks metric floor breaches (`anomaly.py#L124-L141`). -/
def checkMacroMaskedFloors (run : AnomalyRunSummary) (policy : AnomalyPolicy) : List AnomalyFlagSpec :=
  if isMacroPassing run then
    run.aggregates.filterMap fun (mid, optMean) =>
      match optMean, resolveMetricFloor policy mid with
      | some meanScore, some floor =>
        if decide (meanScore < floor) then
          some {
            anomalyType := .aggregateMaskedDrop
            severity := .warning
            scope := .run
            caseId := none
            metricIds := [mid]
            spread := some (SignedRat.subNNRat meanScore floor)
          }
        else
          none
      | _, _ => none
  else
    []

/-- Resolve allowed regression drop for `metricId` (`policy.maxMetricRegressionDrops[m] ?? policy.maxRegressionDrop`). -/
def resolveAllowedDrop (policy : AnomalyPolicy) (metricId : String) : NNRat :=
  match lookupNNRat policy.maxMetricRegressionDrops metricId with
  | some d => d
  | none => policy.maxRegressionDrop

/-- Returns `true` iff comparison has ≥1 numeric metric delta with non-negative mean (`anomaly.py#L144-L149`). -/
def isMacroNonRegressing (cmp : AnomalyComparisonSummary) : Bool :=
  let sharedDeltas := cmp.metricComparisons.filterMap AnomalyMetricDelta.delta
  if h : 0 < sharedDeltas.length then
    decide (SignedRat.zero ≤ₛ sMeanList sharedDeltas h)
  else
    false

/-- Emit run-level `AGGREGATE_MASKED_DROP` when overall summary masks an individual metric drop (`anomaly.py#L150-L170`). -/
def checkComparisonMaskedMetrics
    (run : AnomalyRunSummary)
    (cmp : AnomalyComparisonSummary)
    (policy : AnomalyPolicy) : List AnomalyFlagSpec :=
  if isMacroPassing run || isMacroNonRegressing cmp then
    cmp.metricComparisons.filterMap fun mc =>
      match mc.delta with
      | none => none
      | some d =>
        let allowedDrop := resolveAllowedDrop policy mc.metricId
        if decide (ofNNRat allowedDrop <ₛ sNeg d) then
          some {
            anomalyType := .aggregateMaskedDrop
            severity := .warning
            scope := .run
            caseId := none
            metricIds := [mc.metricId]
            spread := some d
          }
        else
          none
  else
    []

/-- Returns `true` iff metric aggregate in comparison is present and within allowed drop (`anomaly.py#L180-L182`). -/
def isMetricAggregateHealthy
    (cmp : AnomalyComparisonSummary)
    (policy : AnomalyPolicy)
    (metricId : String) : Bool :=
  match lookupMetricDelta cmp.metricComparisons metricId with
  | none => false
  | some mc =>
    match mc.delta with
    | none => true
    | some d =>
      let allowedDrop := resolveAllowedDrop policy metricId
      decide (sNeg d ≤ₛ ofNNRat allowedDrop)

/-- Emit case-level `AGGREGATE_MASKED_DROP` when a healthy metric aggregate masks a severe case drop (`anomaly.py#L172-L201`). -/
def checkComparisonMaskedCaseDrops
    (cmp : AnomalyComparisonSummary)
    (policy : AnomalyPolicy) : List AnomalyFlagSpec :=
  cmp.caseComparisons.flatMap fun cc =>
    cc.metricDeltas.filterMap fun cmd =>
      match cmd.delta with
      | none => none
      | some d =>
        if isMetricAggregateHealthy cmp policy cmd.metricId &&
           decide (ofNNRat policy.caseDropWarningThreshold ≤ₛ sNeg d) then
          some {
            anomalyType := .aggregateMaskedDrop
            severity := .warning
            scope := .case
            caseId := some cc.caseId
            metricIds := [cmd.metricId]
            spread := some d
          }
        else
          none

/-- Formal model of `_check_mandatory_and_masked_drops` (`anomaly.py#L76-L203`). -/
def checkMandatoryAndMaskedDrops
    (run : AnomalyRunSummary)
    (comparison : Option AnomalyComparisonSummary)
    (policy : AnomalyPolicy) : List AnomalyFlagSpec :=
  let baseFlags :=
    checkMandatoryFailures run ++
    checkMacroMaskedMandatory run ++
    checkMacroMaskedFloors run policy
  match comparison with
  | none => baseFlags
  | some cmp =>
    baseFlags ++
    checkComparisonMaskedMetrics run cmp policy ++
    checkComparisonMaskedCaseDrops cmp policy

/-! ## Dataset Capping, Inconclusive Spikes & Full `detectAnomalies` (`anomaly.py#L206-L254`) -/

/-- Count inconclusive cases in `run` (`anomaly.py#L233-L238`). -/
def countInconclusiveCases (run : AnomalyRunSummary) : Nat :=
  (run.cases.filter AnomalyCaseSummary.isInconclusive).length

/-- Exact rational inconclusive case rate `k / n` (`0 < n`). -/
def inconclusiveRate (inconclusiveCount evaluatedCount : Nat) (hPos : 0 < evaluatedCount) : NNRat :=
  ⟨inconclusiveCount, evaluatedCount, hPos⟩

/-- Check `DATASET_CAPPED` flag (`anomaly.py#L220-L231`). -/
def checkDatasetCapped (run : AnomalyRunSummary) : List AnomalyFlagSpec :=
  if run.datasetCapped then
    [{
      anomalyType := .datasetCapped
      severity := .warning
      scope := .run
      caseId := none
      metricIds := []
      spread := none
    }]
  else
    []

/-- Check `INCONCLUSIVE_SPIKE` flag (`anomaly.py#L233-L252`). -/
def checkInconclusiveSpike (run : AnomalyRunSummary) : List AnomalyFlagSpec :=
  let cnt := countInconclusiveCases run
  let rate := inconclusiveRate cnt run.evaluatedCaseCount run.evaluatedCaseCountPos
  if decide (NNRat.zero < rate) then
    [{
      anomalyType := .inconclusiveSpike
      severity := .warning
      scope := .run
      caseId := none
      metricIds := []
      spread := some (ofNNRat rate)
    }]
  else
    []

/-- Formal model of `detect_anomalies` (`anomaly.py#L206-L254`). -/
def detectAnomalies
    (run : AnomalyRunSummary)
    (comparison : Option AnomalyComparisonSummary)
    (policy : AnomalyPolicy) : List AnomalyFlagSpec :=
  checkDisagreements run policy.disagreementThreshold ++
  checkMandatoryAndMaskedDrops run comparison policy ++
  checkDatasetCapped run ++
  checkInconclusiveSpike run

end EvalForgeFormal.Regression
