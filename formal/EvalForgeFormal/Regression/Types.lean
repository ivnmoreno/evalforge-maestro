import EvalForgeFormal.Retrieval.ExactRat
import EvalForgeFormal.Calibration.ExactMath
import EvalForgeFormal.Stats.ExactAlgebra

namespace EvalForgeFormal.Regression

open EvalForgeFormal.Retrieval (NNRat)
open EvalForgeFormal.Calibration (SignedRat)

/-! ## Anomaly Detection Domain (`types.py`, `anomaly.py`) -/

/-- Anomaly classification mirroring `evalforge_maestro.types.AnomalyType`. -/
inductive AnomalyType where
  | metricDisagreement
  | aggregateMaskedDrop
  | mandatoryCaseFailure
  | inconclusiveSpike
  | datasetCapped
  deriving DecidableEq, Repr

namespace AnomalyType

def toCanonicalString : AnomalyType → String
  | .metricDisagreement => "METRIC_DISAGREEMENT"
  | .aggregateMaskedDrop => "AGGREGATE_MASKED_DROP"
  | .mandatoryCaseFailure => "MANDATORY_CASE_FAILURE"
  | .inconclusiveSpike => "INCONCLUSIVE_SPIKE"
  | .datasetCapped => "DATASET_CAPPED"

end AnomalyType

/-- Anomaly severity mirroring `evalforge_maestro.types.AnomalySeverity`. -/
inductive AnomalySeverity where
  | warning
  | fail
  deriving DecidableEq, Repr

namespace AnomalySeverity

def toCanonicalString : AnomalySeverity → String
  | .warning => "WARNING"
  | .fail => "FAIL"

end AnomalySeverity

/-- Anomaly granularity mirroring `evalforge_maestro.types.AnomalyScope`. -/
inductive AnomalyScope where
  | run
  | case
  deriving DecidableEq, Repr

namespace AnomalyScope

def toCanonicalString : AnomalyScope → String
  | .run => "RUN"
  | .case => "CASE"

end AnomalyScope

/-- Formal representation of an emitted `AnomalyFlag` (`types.py`). -/
structure AnomalyFlagSpec where
  anomalyType : AnomalyType
  severity : AnomalySeverity
  scope : AnomalyScope
  caseId : Option String := none
  metricIds : List String := []
  spread : Option SignedRat := none
  deriving DecidableEq, Repr

/-- Formal anomaly-relevant subset of `QualityGatePolicy` (`types.py`). -/
structure AnomalyPolicy where
  minScore : Option NNRat := none
  minMetricScores : List (String × NNRat) := []
  maxRegressionDrop : NNRat := ⟨5, 100, by omega⟩
  maxMetricRegressionDrops : List (String × NNRat) := []
  disagreementThreshold : NNRat := ⟨30, 100, by omega⟩
  caseDropWarningThreshold : NNRat := ⟨25, 100, by omega⟩
  deriving DecidableEq, Repr

/-- Per-case summary required by `detect_anomalies` (`anomaly.py`). -/
structure AnomalyCaseSummary where
  caseId : String
  metricScores : List (String × Option NNRat) := []
  failedMetrics : List String := []
  isInconclusive : Bool := false
  deriving DecidableEq, Repr

/-- Metric-level comparison delta `(metricId, delta?)`. -/
structure AnomalyMetricDelta where
  metricId : String
  delta : Option SignedRat := none
  deriving DecidableEq, Repr

/-- Per-case comparison deltas `(caseId, metricDeltas)`. -/
structure AnomalyCaseDelta where
  caseId : String
  metricDeltas : List AnomalyMetricDelta := []
  deriving DecidableEq, Repr

/-- Comparison summary required by `_check_mandatory_and_masked_drops` (`anomaly.py`). -/
structure AnomalyComparisonSummary where
  metricComparisons : List AnomalyMetricDelta := []
  caseComparisons : List AnomalyCaseDelta := []
  deriving DecidableEq, Repr

/-- Run summary required by `detect_anomalies` (`anomaly.py`). -/
structure AnomalyRunSummary where
  runId : String
  evaluatedCaseCount : Nat
  evaluatedCaseCountPos : 0 < evaluatedCaseCount
  datasetCapped : Bool := false
  mandatoryFailedCaseIds : List String := []
  aggregates : List (String × Option NNRat) := []
  cases : List AnomalyCaseSummary := []
  deriving DecidableEq, Repr

/-! ## Provenance & Drift Domain (`types.py`, `drift.py`) -/

/-- Provenance drift category mirroring `evalforge_maestro.types.DriftCategory`. -/
inductive DriftCategory where
  | datasetFingerprint
  | metricVersion
  | metricSet
  | judgeConfig
  | embeddingConfig
  | datasetCapped
  | caseSetMismatch
  deriving DecidableEq, Repr

namespace DriftCategory

def toCanonicalString : DriftCategory → String
  | .datasetFingerprint => "DATASET_FINGERPRINT"
  | .metricVersion => "METRIC_VERSION"
  | .metricSet => "METRIC_SET"
  | .judgeConfig => "JUDGE_CONFIG"
  | .embeddingConfig => "EMBEDDING_CONFIG"
  | .datasetCapped => "DATASET_CAPPED"
  | .caseSetMismatch => "CASE_SET_MISMATCH"

end DriftCategory

/--
Run provenance snapshot explicitly modeling both measurement-comparability fields and intentional
target-change fields (`systemVersion`, `modelId`, `configFingerprint`) to prove strict isolation.
-/
structure ProvenanceSnapshot where
  runId : String
  datasetFingerprint : String
  metricVersions : List (String × String) := []
  judgeConfigFingerprint : Option String := none
  embeddingConfigFingerprint : Option String := none
  datasetCapped : Bool := false
  caseIds : List String := []
  systemVersion : Option String := none
  modelId : Option String := none
  configFingerprint : Option String := none
  deriving DecidableEq, Repr

/-- Deduplication key matching `drift.py:225-232`. -/
abbrev DriftKey := DriftCategory × Option String × Option String × Option String

/-- Formal representation of an emitted `DriftWarning` (`types.py`, `drift.py`). -/
structure DriftWarningSpec where
  category : DriftCategory
  metricId : Option String := none
  baselineRunId : Option String := none
  candidateRunId : Option String := none
  deriving DecidableEq, Repr

namespace DriftWarningSpec

/-- Canonical 4-tuple deduplication key used in `detect_cohort_drift`. -/
def key (w : DriftWarningSpec) : DriftKey :=
  (w.category, w.metricId, w.baselineRunId, w.candidateRunId)

end DriftWarningSpec

/-! ## Sliding-Window OLS Trend Domain (`types.py`, `trend.py`) -/

/-- Trend trajectory classification mirroring `evalforge_maestro.types.TrendDirection`. -/
inductive TrendDirection where
  | improving
  | stable
  | degrading
  | insufficientData
  deriving DecidableEq, Repr

namespace TrendDirection

def toCanonicalString : TrendDirection → String
  | .improving => "IMPROVING"
  | .stable => "STABLE"
  | .degrading => "DEGRADING"
  | .insufficientData => "INSUFFICIENT_DATA"

end TrendDirection

/-- Single run/manifest entry entering `analyze_trend` (`trend.py`). -/
structure TrendRunEntry where
  runId : String
  timestampKey : Int
  datasetId : String
  modelId : Option String := none
  metricScores : List (String × Option NNRat) := []
  provenance : ProvenanceSnapshot
  deriving DecidableEq, Repr

/-- Formal per-metric summary mirroring `MetricTrendSummary` (`types.py`, `trend.py`). -/
structure MetricTrendOutcome where
  metricId : String
  windowRuns : Nat
  validPoints : Nat
  missingPoints : Nat
  slope : Option SignedRat
  direction : TrendDirection
  firstScore : Option NNRat
  lastScore : Option NNRat
  minScore : Option NNRat
  maxScore : Option NNRat
  meanScore : Option NNRat
  deriving DecidableEq, Repr

/-- Formal sliding-window report mirroring `TrendReport` (`types.py`, `trend.py`). -/
structure TrendReportOutcome where
  window : Nat
  datasetIdFilter : Option String
  modelIdFilter : Option String
  inspectedRunIds : List String
  slopeThreshold : NNRat
  metrics : List MetricTrendOutcome
  driftWarnings : List DriftWarningSpec
  deriving DecidableEq, Repr

end EvalForgeFormal.Regression
