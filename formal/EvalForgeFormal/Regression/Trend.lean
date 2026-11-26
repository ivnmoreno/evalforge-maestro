import EvalForgeFormal.Regression.Types
import EvalForgeFormal.Regression.Anomaly
import EvalForgeFormal.Regression.Drift

namespace EvalForgeFormal.Regression

open EvalForgeFormal.Retrieval (NNRat dedupPreserveFirst)
open EvalForgeFormal.Calibration (SignedRat nnMeanList)
open EvalForgeFormal.Stats (ofNNRat sNeg sAdd sSub sMul sDivNat sLe sLt sMeanList)

/-! ## Exact-Rational OLS Linear Regression Slope (`_compute_ols_slope`, `trend.py#L28-L34`) -/

/-- Centered doubled integer weight `2*idx - (m - 1)` for index `idx` in a series of length `m`. -/
def olsWeight (idx m : Nat) : Int :=
  2 * (idx : Int) - ((m - 1 : Nat) : Int)

/-- Weighted sum `∑ (2*i - (m - 1)) * y_i` over `ys` starting at index `idx`. -/
def olsWeightedSumAux (idx m : Nat) : List SignedRat → SignedRat
  | [] => SignedRat.zero
  | y :: ys =>
    let w : SignedRat := ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩
    sAdd (sMul w y) (olsWeightedSumAux (idx + 1) m ys)

/-- Centered covariance sum `∑ (2*i - (m - 1)) * (y_i - yMean)` starting at index `idx`. -/
def olsCenteredSumAux (idx m : Nat) (yMean : SignedRat) : List SignedRat → SignedRat
  | [] => SignedRat.zero
  | y :: ys =>
    let w : SignedRat := ⟨olsWeight idx m, 1, Nat.zero_lt_one⟩
    sAdd (sMul w (sSub y yMean)) (olsCenteredSumAux (idx + 1) m yMean ys)

/-- Denominator `m * (m^2 - 1)` is strictly positive for all `m ≥ 2`. -/
theorem olsDenom_pos {m : Nat} (hm : 2 ≤ m) : 0 < m * (m * m - 1) := by
  have h1 : 4 ≤ m * m := Nat.mul_le_mul hm hm
  have h2 : 0 < m * m - 1 := by omega
  exact Nat.mul_pos (by omega) h2

/--
Exact rational OLS slope for a `SignedRat` series `ys` of length `m ≥ 2`:
`6 * (∑ (2*i - (m - 1)) * y_i) / (m * (m^2 - 1))`.
-/
def computeOlsSlopeSigned (ys : List SignedRat) (hm : 2 ≤ ys.length) : SignedRat :=
  let m := ys.length
  let num := sMul ⟨6, 1, Nat.zero_lt_one⟩ (olsWeightedSumAux 0 m ys)
  sDivNat num (m * (m * m - 1)) (olsDenom_pos hm)

/--
Direct centered-covariance OLS slope mirroring `trend.py#L28-L34`:
`6 * (∑ (2*i - (m - 1)) * (y_i - y_mean)) / (m * (m^2 - 1))`, equivalent to
`(∑ (i - (m - 1)/2) * (y_i - y_mean)) / (m * (m^2 - 1) / 12)`.
-/
def computeOlsSlopeCentered (ys : List SignedRat) (hm : 2 ≤ ys.length) : SignedRat :=
  let m := ys.length
  let yMean := sMeanList ys (by omega)
  let num := sMul ⟨6, 1, Nat.zero_lt_one⟩ (olsCenteredSumAux 0 m yMean ys)
  sDivNat num (m * (m * m - 1)) (olsDenom_pos hm)

/-- Exact rational OLS slope for a `List NNRat` score series of length `m ≥ 2`. -/
def computeOlsSlopeNNRat (ys : List NNRat) (hm : 2 ≤ ys.length) : SignedRat :=
  computeOlsSlopeSigned (ys.map ofNNRat) (by rw [List.length_map]; exact hm)

/-! ## Direction Classification & Per-Metric Summary (`_summarize_metric_trend`, `trend.py#L37-L116`) -/

/-- Exact 3-way trend direction classifier for a computed slope and threshold `> 0`. -/
def classifyTrendDirection (slope : SignedRat) (slopeThreshold : NNRat) : TrendDirection :=
  if decide (slope <ₛ sNeg (ofNNRat slopeThreshold)) then
    .degrading
  else if decide (ofNNRat slopeThreshold <ₛ slope) then
    .improving
  else
    .stable

/-- Lookup optional metric score in `entry.metricScores`. -/
def lookupOptScore : List (String × Option NNRat) → String → Option NNRat
  | [], _ => none
  | (k, v) :: rest, target => if k = target then v else lookupOptScore rest target

/-- Formal model of `_summarize_metric_trend` (`trend.py#L37-L116`). -/
def summarizeMetricTrend
    (metricId : String)
    (windowRuns : List TrendRunEntry)
    (slopeThreshold : NNRat) : MetricTrendOutcome :=
  let validScores := windowRuns.filterMap fun entry => lookupOptScore entry.metricScores metricId
  let validCount := validScores.length
  let missingCount := windowRuns.length - validCount
  let firstScore := validScores.head?
  let lastScore := validScores.getLast?
  let minScore :=
    match validScores with
    | [] => none
    | x :: xs => some (listMinAux x xs)
  let maxScore :=
    match validScores with
    | [] => none
    | x :: xs => some (listMaxAux x xs)
  let meanScore :=
    if h : 0 < validScores.length then some (nnMeanList validScores h) else none
  if h2 : 2 ≤ validScores.length then
    let slope := computeOlsSlopeNNRat validScores h2
    let dir := classifyTrendDirection slope slopeThreshold
    {
      metricId := metricId
      windowRuns := windowRuns.length
      validPoints := validCount
      missingPoints := missingCount
      slope := some slope
      direction := dir
      firstScore := firstScore
      lastScore := lastScore
      minScore := minScore
      maxScore := maxScore
      meanScore := meanScore
    }
  else
    {
      metricId := metricId
      windowRuns := windowRuns.length
      validPoints := validCount
      missingPoints := missingCount
      slope := none
      direction := .insufficientData
      firstScore := firstScore
      lastScore := lastScore
      minScore := minScore
      maxScore := maxScore
      meanScore := meanScore
    }

/-! ## Chronological Sorting, Dataset/Model Scoping & Window Slicing (`analyze_trend`, `trend.py#L119-L193`) -/

/-- Total lexicographic comparator on `(timestampKey, runId)`. -/
def trendRunLe (a b : TrendRunEntry) : Bool :=
  if a.timestampKey < b.timestampKey then true
  else if b.timestampKey < a.timestampKey then false
  else strLe a.runId b.runId

/-- Sort runs chronologically by `(timestampKey, runId)`. -/
def sortTrendRuns (runs : List TrendRunEntry) : List TrendRunEntry :=
  runs.mergeSort trendRunLe

/-- Take the trailing `window` elements of `xs` (mirrors Python `xs[-window:]`). -/
def takeLast {α : Type} (window : Nat) (xs : List α) : List α :=
  xs.drop (xs.length - window)

/-- Resolve metric IDs across `windowRuns` when no explicit `metricIds` filter is provided. -/
def discoverWindowMetricIds (windowRuns : List TrendRunEntry) : List String :=
  let allKeys := windowRuns.flatMap fun entry =>
    entry.provenance.metricVersions.map Prod.fst ++ entry.metricScores.map Prod.fst
  (dedupPreserveFirst allKeys).mergeSort strLe

/-- Formal model of `analyze_trend` (`trend.py#L119-L193`). -/
def analyzeTrend
    (runs : List TrendRunEntry)
    (window : Nat)
    (datasetId : Option String)
    (allDatasets : Bool)
    (modelId : Option String)
    (metricIds : Option (List String))
    (slopeThreshold : NNRat) : TrendReportOutcome :=
  let sortedRuns := sortTrendRuns runs
  let (effectiveDataset, datasetScoped) :=
    match datasetId with
    | some ds => (some ds, sortedRuns.filter fun (r : TrendRunEntry) => r.datasetId == ds)
    | none =>
      if !allDatasets then
        match sortedRuns.getLast? with
        | some latest =>
          (some latest.datasetId, sortedRuns.filter fun (r : TrendRunEntry) => r.datasetId == latest.datasetId)
        | none => (none, [])
      else
        (none, sortedRuns)
  let scopedRuns :=
    match modelId with
    | some mid => datasetScoped.filter fun (r : TrendRunEntry) => r.modelId == some mid
    | none => datasetScoped
  let windowRuns := takeLast window scopedRuns
  let resolvedMetricIds :=
    match metricIds with
    | some mids => dedupPreserveFirst mids
    | none => discoverWindowMetricIds windowRuns
  let metrics := resolvedMetricIds.map fun mid =>
    summarizeMetricTrend mid windowRuns slopeThreshold
  let driftWarnings := detectWindowDrift (windowRuns.map TrendRunEntry.provenance)
  {
    window := window
    datasetIdFilter := effectiveDataset
    modelIdFilter := modelId
    inspectedRunIds := windowRuns.map TrendRunEntry.runId
    slopeThreshold := slopeThreshold
    metrics := metrics
    driftWarnings := driftWarnings
  }

end EvalForgeFormal.Regression
