import Lean.Data.Json
import EvalForgeFormal.Regression.Anomaly
import EvalForgeFormal.Regression.Drift
import EvalForgeFormal.Regression.Trend

open Lean
open EvalForgeFormal.Retrieval
open EvalForgeFormal.Calibration
open EvalForgeFormal.Stats
open EvalForgeFormal.Regression

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private def mkPct (n : Nat) : NNRat := ⟨n, 100, by omega⟩
private def mkSignedPct (n : Int) : SignedRat := ⟨n, 100, by omega⟩

/-! ## Request Input Records -/

private structure AnomalyVectorInput where
  caseId : String
  run : AnomalyRunSummary
  comparison : Option AnomalyComparisonSummary := none
  policy : AnomalyPolicy := {}

private structure TrendVectorInput where
  caseId : String
  runs : List TrendRunEntry
  window : Nat
  datasetId : Option String := none
  allDatasets : Bool := false
  modelId : Option String := none
  metricIds : Option (List String) := none
  slopeThreshold : NNRat := ⟨1, 100, by omega⟩

private structure DriftPairVectorInput where
  caseId : String
  mode : String -- "pair" or "window"
  baseline : Option ProvenanceSnapshot := none
  candidate : Option ProvenanceSnapshot := none
  runs : List ProvenanceSnapshot := []

private structure DriftCohortVectorInput where
  caseId : String
  baselineRuns : List ProvenanceSnapshot
  candidateRuns : List ProvenanceSnapshot

/-! ## Canonical JSON Serialization Helpers -/

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

private def optStrToJson : Option String → Json
  | some s => Json.str s
  | none => Json.null

private def strListToJson (xs : List String) : Json :=
  Json.arr (xs.toArray.map Json.str)

private def optStrListToJson : Option (List String) → Json
  | some xs => strListToJson xs
  | none => Json.null

private def kvStrToJson (kvs : List (String × String)) : Json :=
  Json.arr (kvs.toArray.map fun (k, v) =>
    Json.mkObj [("key", Json.str k), ("value", Json.str v)])

private def kvNNRatToJson (kvs : List (String × NNRat)) : Json :=
  Json.arr (kvs.toArray.map fun (k, v) =>
    Json.mkObj [("metric_id", Json.str k), ("value", nnratToJson v)])

private def kvOptNNRatToJson (kvs : List (String × Option NNRat)) : Json :=
  Json.arr (kvs.toArray.map fun (k, v) =>
    Json.mkObj [("metric_id", Json.str k), ("score", optNNRatToJson v)])

private def anomalyFlagToJson (f : AnomalyFlagSpec) : Json :=
  Json.mkObj [
    ("anomaly_type", Json.str f.anomalyType.toCanonicalString),
    ("case_id", optStrToJson f.caseId),
    ("metric_ids", strListToJson f.metricIds),
    ("scope", Json.str f.scope.toCanonicalString),
    ("severity", Json.str f.severity.toCanonicalString),
    ("spread_exact", optSignedRatToJson f.spread)
  ]

private def anomalyPolicyToJson (p : AnomalyPolicy) : Json :=
  Json.mkObj [
    ("case_drop_warning_threshold", nnratToJson p.caseDropWarningThreshold),
    ("disagreement_threshold", nnratToJson p.disagreementThreshold),
    ("max_metric_regression_drops", kvNNRatToJson p.maxMetricRegressionDrops),
    ("max_regression_drop", nnratToJson p.maxRegressionDrop),
    ("min_metric_scores", kvNNRatToJson p.minMetricScores),
    ("min_score", optNNRatToJson p.minScore)
  ]

private def anomalyCaseSummaryToJson (c : AnomalyCaseSummary) : Json :=
  Json.mkObj [
    ("case_id", Json.str c.caseId),
    ("failed_metrics", strListToJson c.failedMetrics),
    ("is_inconclusive", Json.bool c.isInconclusive),
    ("metric_scores", kvOptNNRatToJson c.metricScores)
  ]

private def anomalyRunSummaryToJson (r : AnomalyRunSummary) : Json :=
  Json.mkObj [
    ("aggregates", kvOptNNRatToJson r.aggregates),
    ("cases", Json.arr (r.cases.toArray.map anomalyCaseSummaryToJson)),
    ("dataset_capped", Json.bool r.datasetCapped),
    ("evaluated_case_count", Json.num r.evaluatedCaseCount),
    ("mandatory_failed_case_ids", strListToJson r.mandatoryFailedCaseIds),
    ("run_id", Json.str r.runId)
  ]

private def anomalyMetricDeltaToJson (m : AnomalyMetricDelta) : Json :=
  Json.mkObj [
    ("delta", optSignedRatToJson m.delta),
    ("metric_id", Json.str m.metricId)
  ]

private def anomalyCaseDeltaToJson (c : AnomalyCaseDelta) : Json :=
  Json.mkObj [
    ("case_id", Json.str c.caseId),
    ("metric_deltas", Json.arr (c.metricDeltas.toArray.map anomalyMetricDeltaToJson))
  ]

private def anomalyComparisonToJson (cmp : AnomalyComparisonSummary) : Json :=
  Json.mkObj [
    ("case_comparisons", Json.arr (cmp.caseComparisons.toArray.map anomalyCaseDeltaToJson)),
    ("metric_comparisons", Json.arr (cmp.metricComparisons.toArray.map anomalyMetricDeltaToJson))
  ]

private def optAnomalyComparisonToJson : Option AnomalyComparisonSummary → Json
  | some cmp => anomalyComparisonToJson cmp
  | none => Json.null

private def provenanceToJson (p : ProvenanceSnapshot) : Json :=
  Json.mkObj [
    ("case_ids", strListToJson p.caseIds),
    ("config_fingerprint", optStrToJson p.configFingerprint),
    ("dataset_capped", Json.bool p.datasetCapped),
    ("dataset_fingerprint", Json.str p.datasetFingerprint),
    ("embedding_config_fingerprint", optStrToJson p.embeddingConfigFingerprint),
    ("judge_config_fingerprint", optStrToJson p.judgeConfigFingerprint),
    ("metric_versions", kvStrToJson p.metricVersions),
    ("model_id", optStrToJson p.modelId),
    ("run_id", Json.str p.runId),
    ("system_version", optStrToJson p.systemVersion)
  ]

private def driftWarningToJson (w : DriftWarningSpec) : Json :=
  Json.mkObj [
    ("baseline_run_id", optStrToJson w.baselineRunId),
    ("candidate_run_id", optStrToJson w.candidateRunId),
    ("category", Json.str w.category.toCanonicalString),
    ("metric_id", optStrToJson w.metricId)
  ]

private def trendRunEntryToJson (e : TrendRunEntry) : Json :=
  Json.mkObj [
    ("dataset_id", Json.str e.datasetId),
    ("metric_scores", kvOptNNRatToJson e.metricScores),
    ("model_id", optStrToJson e.modelId),
    ("provenance", provenanceToJson e.provenance),
    ("run_id", Json.str e.runId),
    ("timestamp_key", Json.num (JsonNumber.fromInt e.timestampKey))
  ]

private def metricTrendOutcomeToJson (m : MetricTrendOutcome) : Json :=
  Json.mkObj [
    ("direction", Json.str m.direction.toCanonicalString),
    ("first_score_exact", optNNRatToJson m.firstScore),
    ("last_score_exact", optNNRatToJson m.lastScore),
    ("max_score_exact", optNNRatToJson m.maxScore),
    ("mean_score_exact", optNNRatToJson m.meanScore),
    ("metric_id", Json.str m.metricId),
    ("min_score_exact", optNNRatToJson m.minScore),
    ("missing_points", Json.num m.missingPoints),
    ("slope_exact", optSignedRatToJson m.slope),
    ("valid_points", Json.num m.validPoints),
    ("window_runs", Json.num m.windowRuns)
  ]

private def trendReportOutcomeToJson (r : TrendReportOutcome) : Json :=
  Json.mkObj [
    ("dataset_id_filter", optStrToJson r.datasetIdFilter),
    ("drift_warnings", Json.arr (r.driftWarnings.toArray.map driftWarningToJson)),
    ("inspected_run_ids", strListToJson r.inspectedRunIds),
    ("metrics", Json.arr (r.metrics.toArray.map metricTrendOutcomeToJson)),
    ("model_id_filter", optStrToJson r.modelIdFilter),
    ("slope_threshold_exact", nnratToJson r.slopeThreshold),
    ("window", Json.num r.window)
  ]

/-! ## Canonical Golden Vectors (`8` Anomaly + `8` Trend + `5` Pair/Window Drift + `4` Cohort Drift) -/

private def mkBaseProvenance
    (runId : String)
    (dsFp : String := "ds-fp-v1")
    (metricVers : List (String × String) := [("exact_match", "1.0.0"), ("groundedness", "1.0.0")])
    (judgeFp : Option String := some "judge-fp-v1")
    (embFp : Option String := some "emb-fp-v1")
    (capped : Bool := false)
    (caseIds : List String := ["c1", "c2"])
    (sysVer : Option String := some "sys-v1")
    (modelId : Option String := some "gpt-a")
    (cfgFp : Option String := some "cfg-v1") : ProvenanceSnapshot :=
  {
    runId := runId
    datasetFingerprint := dsFp
    metricVersions := metricVers
    judgeConfigFingerprint := judgeFp
    embeddingConfigFingerprint := embFp
    datasetCapped := capped
    caseIds := caseIds
    systemVersion := sysVer
    modelId := modelId
    configFingerprint := cfgFp
  }

private def canonicalAnomalyVectors : List AnomalyVectorInput :=
  [
    -- 1. Clean compliant run -> zero anomalies
    {
      caseId := "clean_compliant_run"
      run := {
        runId := "run-clean"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        datasetCapped := false
        mandatoryFailedCaseIds := []
        aggregates := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 80))]
        cases := [
          {
            caseId := "c1"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 80))]
          },
          {
            caseId := "c2"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 80))]
          }
        ]
      }
      policy := {
        minScore := some (mkPct 70)
        disagreementThreshold := mkPct 30
      }
    },
    -- 2. Exact boundary non-trigger (spread = 0.30) vs strict trigger (spread = 0.40)
    {
      caseId := "disagreement_boundary_vs_strict"
      run := {
        runId := "run-disagree"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        aggregates := [("exact_match", some (mkPct 92)), ("groundedness", some (mkPct 52))]
        cases := [
          {
            caseId := "c_boundary"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 60))]
          },
          {
            caseId := "c_strict"
            metricScores := [("exact_match", some (mkPct 95)), ("groundedness", some (mkPct 55))]
          }
        ]
      }
      policy := { disagreementThreshold := mkPct 30 }
    },
    -- 3. Mandatory case failure + passing macro average masking mandatory failure & floor breach
    {
      caseId := "mandatory_failure_macro_mask_and_floor_breach"
      run := {
        runId := "run-mand-mask"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        mandatoryFailedCaseIds := ["c1"]
        aggregates := [("exact_match", some (mkPct 85)), ("groundedness", some (mkPct 60))]
        cases := [
          {
            caseId := "c1"
            metricScores := [("exact_match", some (mkPct 80)), ("groundedness", some (mkPct 55))]
            failedMetrics := ["groundedness"]
          },
          {
            caseId := "c2"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 65))]
          }
        ]
      }
      policy := {
        minMetricScores := [("groundedness", mkPct 70)]
        disagreementThreshold := mkPct 30
      }
    },
    -- 4. Pairwise comparison masked metric drop (offsetting positive gain on another metric)
    {
      caseId := "comparison_masked_metric_drop"
      run := {
        runId := "run-cmp-metric"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        aggregates := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 70))]
        cases := [
          {
            caseId := "c1"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 70))]
          },
          {
            caseId := "c2"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", some (mkPct 70))]
          }
        ]
      }
      comparison := some {
        metricComparisons := [
          { metricId := "exact_match", delta := some (mkSignedPct 20) },
          { metricId := "groundedness", delta := some (mkSignedPct (-12)) }
        ]
        caseComparisons := []
      }
      policy := {
        maxRegressionDrop := mkPct 5
        disagreementThreshold := mkPct 30
      }
    },
    -- 5. Healthy metric aggregate masking severe single-case drop (vs non-severe & unshared metric)
    {
      caseId := "comparison_masked_case_drop"
      run := {
        runId := "run-cmp-case"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        aggregates := [("exact_match", some (mkPct 88))]
        cases := [
          { caseId := "c1", metricScores := [("exact_match", some (mkPct 60))] },
          { caseId := "c2", metricScores := [("exact_match", some (mkPct 95))] }
        ]
      }
      comparison := some {
        metricComparisons := [
          { metricId := "exact_match", delta := some (mkSignedPct (-2)) }
        ]
        caseComparisons := [
          {
            caseId := "c1"
            metricDeltas := [
              { metricId := "exact_match", delta := some (mkSignedPct (-35)) },
              { metricId := "unshared_metric", delta := some (mkSignedPct (-40)) }
            ]
          },
          {
            caseId := "c2"
            metricDeltas := [
              { metricId := "exact_match", delta := some (mkSignedPct (-10)) }
            ]
          }
        ]
      }
      policy := {
        maxRegressionDrop := mkPct 5
        caseDropWarningThreshold := mkPct 25
      }
    },
    -- 6. DATASET_CAPPED + INCONCLUSIVE_SPIKE (1 of 4 cases inconclusive -> rate 1/4)
    {
      caseId := "dataset_capped_and_inconclusive_spike"
      run := {
        runId := "run-cap-inc"
        evaluatedCaseCount := 4
        evaluatedCaseCountPos := by omega
        datasetCapped := true
        aggregates := [("exact_match", some (mkPct 80))]
        cases := [
          { caseId := "c1", metricScores := [("exact_match", none)], isInconclusive := true },
          { caseId := "c2", metricScores := [("exact_match", some (mkPct 80))] },
          { caseId := "c3", metricScores := [("exact_match", some (mkPct 80))] },
          { caseId := "c4", metricScores := [("exact_match", some (mkPct 80))] }
        ]
      }
      policy := {}
    },
    -- 7. Low macro average (< 0.50) & negative comparison delta -> NO masking warnings, only MANDATORY_CASE_FAILURE
    {
      caseId := "low_macro_average_non_masking"
      run := {
        runId := "run-low-macro"
        evaluatedCaseCount := 2
        evaluatedCaseCountPos := by omega
        mandatoryFailedCaseIds := ["c1"]
        aggregates := [("exact_match", some (mkPct 30)), ("groundedness", some (mkPct 40))]
        cases := [
          {
            caseId := "c1"
            metricScores := [("exact_match", some (mkPct 30)), ("groundedness", some (mkPct 40))]
            failedMetrics := ["exact_match", "groundedness"]
          },
          {
            caseId := "c2"
            metricScores := [("exact_match", some (mkPct 30)), ("groundedness", some (mkPct 40))]
          }
        ]
      }
      comparison := some {
        metricComparisons := [
          { metricId := "exact_match", delta := some (mkSignedPct (-20)) },
          { metricId := "groundedness", delta := some (mkSignedPct (-20)) }
        ]
        caseComparisons := [
          {
            caseId := "c1"
            metricDeltas := [
              { metricId := "exact_match", delta := some (mkSignedPct (-30)) }
            ]
          }
        ]
      }
      policy := {
        minScore := some (mkPct 50)
        maxRegressionDrop := mkPct 5
        caseDropWarningThreshold := mkPct 25
      }
    },
    -- 8. Singleton numeric score + null metric score immunity
    {
      caseId := "singleton_and_null_score_immunity"
      run := {
        runId := "run-singleton"
        evaluatedCaseCount := 1
        evaluatedCaseCountPos := by omega
        aggregates := [("exact_match", some (mkPct 90)), ("groundedness", none)]
        cases := [
          {
            caseId := "c1"
            metricScores := [("exact_match", some (mkPct 90)), ("groundedness", none)]
          }
        ]
      }
      policy := {
        minScore := some (mkPct 80)
        disagreementThreshold := mkPct 10
      }
    }
  ]

private def mkTrendEntry
    (runId : String)
    (ts : Int)
    (datasetId : String)
    (modelId : Option String)
    (scores : List (String × Option NNRat))
    (prov : ProvenanceSnapshot) : TrendRunEntry :=
  {
    runId := runId
    timestampKey := ts
    datasetId := datasetId
    modelId := modelId
    metricScores := scores
    provenance := prov
  }

private def canonicalTrendVectors : List TrendVectorInput :=
  [
    -- 1. Linear degrading series ([0.90, 0.80, 0.70, 0.60] -> slope = -1/10, DEGRADING)
    {
      caseId := "linear_degrading_series"
      window := 5
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 90))] (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r2" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 70))] (mkBaseProvenance "r3" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r4" 400 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 60))] (mkBaseProvenance "r4" (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 2. Linear improving series (exact reversal of #1 -> slope = +1/10, IMPROVING)
    {
      caseId := "linear_improving_series"
      window := 5
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 60))] (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 70))] (mkBaseProvenance "r2" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r3" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r4" 400 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 90))] (mkBaseProvenance "r4" (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 3. Constant stable series ([0.80, 0.80, 0.80, 0.80] -> slope = 0, STABLE)
    {
      caseId := "constant_stable_series"
      window := 5
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r2" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r3" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r4" 400 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))] (mkBaseProvenance "r4" (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 4. Single valid point -> INSUFFICIENT_DATA (valid=1, missing=2, slope=null)
    {
      caseId := "single_valid_point_insufficient"
      window := 5
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", none)] (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 75))] (mkBaseProvenance "r2" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a") [("exact_match", none)] (mkBaseProvenance "r3" (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 5. Zero valid points with explicit metric filter -> INSUFFICIENT_DATA (valid=0, missing=3)
    {
      caseId := "zero_valid_points_insufficient"
      window := 5
      metricIds := some ["exact_match"]
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", none)] (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a") [("exact_match", none)] (mkBaseProvenance "r2" (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a") [("exact_match", none)] (mkBaseProvenance "r3" (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 6. Unordered runs + timestamp tie-break + default latest dataset + trailing window=3
    {
      caseId := "unordered_tiebreak_default_dataset_and_window"
      window := 3
      datasetId := none
      allDatasets := false
      runs := [
        mkTrendEntry "run-c" 300 "ds-new" (some "gpt-a") [("exact_match", some (mkPct 90))] (mkBaseProvenance "run-c" (dsFp := "fp-new") (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "run-b" 200 "ds-new" (some "gpt-a") [("exact_match", some (mkPct 70))] (mkBaseProvenance "run-b" (dsFp := "fp-new") (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "run-old-ds" 250 "ds-old" (some "gpt-a") [("exact_match", some (mkPct 10))] (mkBaseProvenance "run-old-ds" (dsFp := "fp-old") (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "run-0" 100 "ds-new" (some "gpt-a") [("exact_match", some (mkPct 20))] (mkBaseProvenance "run-0" (dsFp := "fp-new") (metricVers := [("exact_match", "1.0.0")])),
        mkTrendEntry "run-a" 200 "ds-new" (some "gpt-a") [("exact_match", some (mkPct 50))] (mkBaseProvenance "run-a" (dsFp := "fp-new") (metricVers := [("exact_match", "1.0.0")]))
      ]
    },
    -- 7. Model-filtered trend with None gap and within-window metric version & capping drift
    {
      caseId := "model_filtered_gaps_and_window_drift"
      window := 5
      modelId := some "gpt-a"
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 60))]
          (mkBaseProvenance "r1" (metricVers := [("exact_match", "1.0.0")]) (modelId := some "gpt-a")),
        mkTrendEntry "r2_other_model" 150 "ds-main" (some "gpt-b") [("exact_match", some (mkPct 99))]
          (mkBaseProvenance "r2_other_model" (metricVers := [("exact_match", "1.0.0")]) (modelId := some "gpt-b")),
        mkTrendEntry "r3" 200 "ds-main" (some "gpt-a") [("exact_match", none)]
          (mkBaseProvenance "r3" (metricVers := [("exact_match", "2.0.0")]) (capped := true) (modelId := some "gpt-a")),
        mkTrendEntry "r4" 300 "ds-main" (some "gpt-a") [("exact_match", some (mkPct 80))]
          (mkBaseProvenance "r4" (metricVers := [("exact_match", "2.0.0")]) (modelId := some "gpt-a"))
      ]
    },
    -- 8. Extreme unit oscillation saturating universal sharp bound 3m / (2(m^2 - 1)) at m=2 and m=4
    {
      caseId := "extreme_unit_oscillation_sharp_bound"
      window := 4
      runs := [
        mkTrendEntry "r1" 100 "ds-main" (some "gpt-a")
          [("m_four", some NNRat.zero), ("m_two", none)]
          (mkBaseProvenance "r1" (metricVers := [("m_four", "1.0.0"), ("m_two", "1.0.0")])),
        mkTrendEntry "r2" 200 "ds-main" (some "gpt-a")
          [("m_four", some NNRat.zero), ("m_two", none)]
          (mkBaseProvenance "r2" (metricVers := [("m_four", "1.0.0"), ("m_two", "1.0.0")])),
        mkTrendEntry "r3" 300 "ds-main" (some "gpt-a")
          [("m_four", some NNRat.one), ("m_two", some NNRat.zero)]
          (mkBaseProvenance "r3" (metricVers := [("m_four", "1.0.0"), ("m_two", "1.0.0")])),
        mkTrendEntry "r4" 400 "ds-main" (some "gpt-a")
          [("m_four", some NNRat.one), ("m_two", some NNRat.one)]
          (mkBaseProvenance "r4" (metricVers := [("m_four", "1.0.0"), ("m_two", "1.0.0")]))
      ]
    }
  ]

private def driftBaseAllSeven : ProvenanceSnapshot :=
  mkBaseProvenance "base-7"
    (dsFp := "ds-fp-a")
    (metricVers := [("exact_match", "1.0.0"), ("removed_metric", "1.0.0")])
    (judgeFp := some "judge-a")
    (embFp := some "emb-a")
    (capped := false)
    (caseIds := ["c1", "c2"])

private def driftCandAllSeven : ProvenanceSnapshot :=
  mkBaseProvenance "cand-7"
    (dsFp := "ds-fp-b")
    (metricVers := [("added_metric", "1.0.0"), ("exact_match", "2.0.0")])
    (judgeFp := some "judge-b")
    (embFp := some "emb-b")
    (capped := true)
    (caseIds := ["c1", "c3"])

private def canonicalDriftPairVectors : List DriftPairVectorInput :=
  [
    -- 1. Identical uncapped snapshots -> zero drift
    {
      caseId := "pair_identical_uncapped_zero_drift"
      mode := "pair"
      baseline := some (mkBaseProvenance "r-same")
      candidate := some (mkBaseProvenance "r-same")
    },
    -- 2. Intentional target-only change (run_id, system_version, model_id, config_fingerprint) -> zero drift
    {
      caseId := "pair_intentional_target_change_isolated"
      mode := "pair"
      baseline := some (mkBaseProvenance "r-base"
        (sysVer := some "sys-v1") (modelId := some "gpt-4o-mini") (cfgFp := some "cfg-v1"))
      candidate := some (mkBaseProvenance "r-cand"
        (sysVer := some "sys-v2") (modelId := some "claude-sonnet") (cfgFp := some "cfg-v2"))
    },
    -- 3. All 7 drift categories active simultaneously (including EMBEDDING_CONFIG)
    {
      caseId := "pair_all_seven_categories_active"
      mode := "pair"
      baseline := some driftBaseAllSeven
      candidate := some driftCandAllSeven
    },
    -- 4. Exact baseline/candidate swap of #3 verifying category-set symmetry
    {
      caseId := "pair_swap_symmetry_counterpart"
      mode := "pair"
      baseline := some driftCandAllSeven
      candidate := some driftBaseAllSeven
    },
    -- 5. 3-run rollback window drift (r1 -> r2 -> r3 where r2 mutates & caps, r3 rolls back)
    {
      caseId := "window_three_run_rollback_drift"
      mode := "window"
      runs := [
        mkBaseProvenance "w1" (dsFp := "ds-v1") (embFp := some "emb-v1") (capped := false),
        mkBaseProvenance "w2" (dsFp := "ds-v2") (embFp := some "emb-v2") (capped := true),
        mkBaseProvenance "w3" (dsFp := "ds-v1") (embFp := some "emb-v1") (capped := false)
      ]
    }
  ]

private def canonicalDriftCohortVectors : List DriftCohortVectorInput :=
  [
    -- 1. Empty baseline side -> immediate empty list
    {
      caseId := "cohort_empty_side_guard"
      baselineRuns := []
      candidateRuns := [mkBaseProvenance "c1" (capped := true)]
    },
    -- 2. Clean multi-run cohorts with identical uncapped provenance & differing target models
    {
      caseId := "cohort_clean_identical_multi_run"
      baselineRuns := [
        mkBaseProvenance "b1" (modelId := some "model-v1") (sysVer := some "v1"),
        mkBaseProvenance "b2" (modelId := some "model-v1") (sysVer := some "v1")
      ]
      candidateRuns := [
        mkBaseProvenance "c1" (modelId := some "model-v2") (sysVer := some "v2"),
        mkBaseProvenance "c2" (modelId := some "model-v2") (sysVer := some "v2")
      ]
    },
    -- 3. Intra-cohort + cross-cohort tail + non-tail DATASET_CAPPED warnings
    {
      caseId := "cohort_intra_cross_and_nontail_capped"
      baselineRuns := [
        mkBaseProvenance "b1" (judgeFp := some "judge-1") (capped := true) (caseIds := ["c1", "c2"]),
        mkBaseProvenance "b2" (judgeFp := some "judge-2") (capped := false) (caseIds := ["c1", "c2"])
      ]
      candidateRuns := [
        mkBaseProvenance "c1" (judgeFp := some "judge-2")
          (metricVers := [("exact_match", "1.0.0"), ("groundedness", "1.0.0")]) (caseIds := ["c1", "c3"]),
        mkBaseProvenance "c2" (judgeFp := some "judge-2")
          (metricVers := [("exact_match", "2.0.0"), ("groundedness", "1.0.0")]) (caseIds := ["c1", "c3"])
      ]
    },
    -- 4. Duplicate-key deduplication verification (repeated intra-cohort pair key collapsed)
    {
      caseId := "cohort_dedup_key_preservation"
      baselineRuns := [
        mkBaseProvenance "b1" (dsFp := "ds-1") (capped := true),
        mkBaseProvenance "b2" (dsFp := "ds-2") (capped := false),
        mkBaseProvenance "b2" (dsFp := "ds-2") (capped := false)
      ]
      candidateRuns := [
        mkBaseProvenance "c1" (dsFp := "ds-2") (capped := false)
      ]
    }
  ]

/-! ## Golden Document Builder -/

private def anomalyVectorToJson (v : AnomalyVectorInput) : Json :=
  let flags := detectAnomalies v.run v.comparison v.policy
  Json.mkObj [
    ("case_id", Json.str v.caseId),
    ("expected", Json.mkObj [
      ("anomalies", Json.arr (flags.toArray.map anomalyFlagToJson))
    ]),
    ("input", Json.mkObj [
      ("comparison", optAnomalyComparisonToJson v.comparison),
      ("policy", anomalyPolicyToJson v.policy),
      ("run", anomalyRunSummaryToJson v.run)
    ])
  ]

private def trendVectorToJson (v : TrendVectorInput) : Json :=
  let out := analyzeTrend v.runs v.window v.datasetId v.allDatasets v.modelId v.metricIds v.slopeThreshold
  Json.mkObj [
    ("case_id", Json.str v.caseId),
    ("expected", trendReportOutcomeToJson out),
    ("input", Json.mkObj [
      ("all_datasets", Json.bool v.allDatasets),
      ("dataset_id", optStrToJson v.datasetId),
      ("metric_ids", optStrListToJson v.metricIds),
      ("model_id", optStrToJson v.modelId),
      ("runs", Json.arr (v.runs.toArray.map trendRunEntryToJson)),
      ("slope_threshold", nnratToJson v.slopeThreshold),
      ("window", Json.num v.window)
    ])
  ]

private def driftPairVectorToJson (v : DriftPairVectorInput) : Json :=
  let warnings :=
    if v.mode == "pair" then
      match v.baseline, v.candidate with
      | some b, some c => detectDrift b c
      | _, _ => []
    else
      detectWindowDrift v.runs
  let inputJson :=
    if v.mode == "pair" then
      Json.mkObj [
        ("baseline", match v.baseline with | some b => provenanceToJson b | none => Json.null),
        ("candidate", match v.candidate with | some c => provenanceToJson c | none => Json.null)
      ]
    else
      Json.mkObj [
        ("runs", Json.arr (v.runs.toArray.map provenanceToJson))
      ]
  Json.mkObj [
    ("case_id", Json.str v.caseId),
    ("expected", Json.mkObj [
      ("warnings", Json.arr (warnings.toArray.map driftWarningToJson))
    ]),
    ("input", inputJson),
    ("mode", Json.str v.mode)
  ]

private def driftCohortVectorToJson (v : DriftCohortVectorInput) : Json :=
  let warnings := detectCohortDrift v.baselineRuns v.candidateRuns
  Json.mkObj [
    ("case_id", Json.str v.caseId),
    ("expected", Json.mkObj [
      ("warnings", Json.arr (warnings.toArray.map driftWarningToJson))
    ]),
    ("input", Json.mkObj [
      ("baseline_runs", Json.arr (v.baselineRuns.toArray.map provenanceToJson)),
      ("candidate_runs", Json.arr (v.candidateRuns.toArray.map provenanceToJson))
    ])
  ]

private def goldenDocumentJson : Json :=
  Json.mkObj [
    ("anomaly_scopes", Json.arr #[
      Json.str AnomalyScope.run.toCanonicalString,
      Json.str AnomalyScope.case.toCanonicalString
    ]),
    ("anomaly_severities", Json.arr #[
      Json.str AnomalySeverity.warning.toCanonicalString,
      Json.str AnomalySeverity.fail.toCanonicalString
    ]),
    ("anomaly_types", Json.arr #[
      Json.str AnomalyType.metricDisagreement.toCanonicalString,
      Json.str AnomalyType.aggregateMaskedDrop.toCanonicalString,
      Json.str AnomalyType.mandatoryCaseFailure.toCanonicalString,
      Json.str AnomalyType.inconclusiveSpike.toCanonicalString,
      Json.str AnomalyType.datasetCapped.toCanonicalString
    ]),
    ("anomaly_vectors", Json.arr (canonicalAnomalyVectors.toArray.map anomalyVectorToJson)),
    ("drift_categories", Json.arr #[
      Json.str DriftCategory.datasetFingerprint.toCanonicalString,
      Json.str DriftCategory.metricVersion.toCanonicalString,
      Json.str DriftCategory.metricSet.toCanonicalString,
      Json.str DriftCategory.judgeConfig.toCanonicalString,
      Json.str DriftCategory.embeddingConfig.toCanonicalString,
      Json.str DriftCategory.datasetCapped.toCanonicalString,
      Json.str DriftCategory.caseSetMismatch.toCanonicalString
    ]),
    ("drift_cohort_vectors", Json.arr (canonicalDriftCohortVectors.toArray.map driftCohortVectorToJson)),
    ("drift_pair_vectors", Json.arr (canonicalDriftPairVectors.toArray.map driftPairVectorToJson)),
    ("lean_toolchain", Json.str leanToolchain),
    ("schema_version", Json.str schemaVersion),
    ("trend_directions", Json.arr #[
      Json.str TrendDirection.improving.toCanonicalString,
      Json.str TrendDirection.stable.toCanonicalString,
      Json.str TrendDirection.degrading.toCanonicalString,
      Json.str TrendDirection.insufficientData.toCanonicalString
    ]),
    ("trend_vectors", Json.arr (canonicalTrendVectors.toArray.map trendVectorToJson))
  ]

/-! ## Fail-Closed JSON Parsers (`eval-stdin`) -/

private def parseNatField (obj : Json) (field : String) : Except String Nat := do
  let val ← obj.getObjVal? field
  val.getNat?

private def parseIntField (obj : Json) (field : String) : Except String Int := do
  let val ← obj.getObjVal? field
  val.getInt?

private def parseOptStrField (obj : Json) (field : String) : Except String (Option String) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> val.getStr?

private def parseStrList (j : Json) : Except String (List String) := do
  let arr ← j.getArr?
  arr.toList.mapM Json.getStr?

private def parseOptStrListField (obj : Json) (field : String) : Except String (Option (List String)) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseStrList val

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
  let r ← parseNNRat j label
  if 0 < r.num && r.num ≤ r.den then
    pure r
  else
    throw s!"{label} must be in (0, 1], got {r.num}/{r.den}"

private def parseOptUnitNNRat (obj : Json) (field : String) : Except String (Option NNRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseUnitNNRat val field

private def parseUnitSignedRat (j : Json) (label : String) : Except String SignedRat := do
  let num ← parseIntField j "num"
  let den ← parseNatField j "den"
  if h : 0 < den then
    if -((den : Int)) ≤ num && num ≤ (den : Int) then
      pure ⟨num, den, h⟩
    else
      throw s!"{label} must be in [-1, 1], got {num}/{den}"
  else
    throw s!"{label}.den must be > 0, got {den}"

private def parseOptUnitSignedRat (obj : Json) (field : String) : Except String (Option SignedRat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseUnitSignedRat val field

private def parseKvStr (j : Json) : Except String (List (String × String)) := do
  let arr ← j.getArr?
  arr.toList.mapM fun item => do
    let k ← (← item.getObjVal? "key").getStr?
    let v ← (← item.getObjVal? "value").getStr?
    pure (k, v)

private def parseKvNNRat (j : Json) (label : String) : Except String (List (String × NNRat)) := do
  let arr ← j.getArr?
  arr.toList.mapM fun item => do
    let k ← (← item.getObjVal? "metric_id").getStr?
    let v ← parseUnitNNRat (← item.getObjVal? "value") s!"{label}.{k}"
    pure (k, v)

private def parseKvOptNNRat (j : Json) (label : String) : Except String (List (String × Option NNRat)) := do
  let arr ← j.getArr?
  arr.toList.mapM fun item => do
    let k ← (← item.getObjVal? "metric_id").getStr?
    let v ← parseOptUnitNNRat item "score"
    let _ := label
    pure (k, v)

private def parseAnomalyPolicy (j : Json) : Except String AnomalyPolicy := do
  let minScore ← parseOptUnitNNRat j "min_score"
  let minMetricScores ← parseKvNNRat (← j.getObjVal? "min_metric_scores") "min_metric_scores"
  let maxDrop ← parseUnitNNRat (← j.getObjVal? "max_regression_drop") "max_regression_drop"
  let maxMetricDrops ← parseKvNNRat (← j.getObjVal? "max_metric_regression_drops") "max_metric_regression_drops"
  let disThr ← parseUnitNNRat (← j.getObjVal? "disagreement_threshold") "disagreement_threshold"
  let caseDropThr ← parseUnitNNRat (← j.getObjVal? "case_drop_warning_threshold") "case_drop_warning_threshold"
  pure {
    minScore := minScore
    minMetricScores := minMetricScores
    maxRegressionDrop := maxDrop
    maxMetricRegressionDrops := maxMetricDrops
    disagreementThreshold := disThr
    caseDropWarningThreshold := caseDropThr
  }

private def parseAnomalyCaseSummary (j : Json) : Except String AnomalyCaseSummary := do
  let cid ← (← j.getObjVal? "case_id").getStr?
  let scores ← parseKvOptNNRat (← j.getObjVal? "metric_scores") "metric_scores"
  let failed ← parseStrList (← j.getObjVal? "failed_metrics")
  let inc ← (← j.getObjVal? "is_inconclusive").getBool?
  pure {
    caseId := cid
    metricScores := scores
    failedMetrics := failed
    isInconclusive := inc
  }

private def parseAnomalyRunSummary (j : Json) : Except String AnomalyRunSummary := do
  let runId ← (← j.getObjVal? "run_id").getStr?
  let evalCount ← parseNatField j "evaluated_case_count"
  if hPos : 0 < evalCount then
    let capped ← (← j.getObjVal? "dataset_capped").getBool?
    let mand ← parseStrList (← j.getObjVal? "mandatory_failed_case_ids")
    let aggs ← parseKvOptNNRat (← j.getObjVal? "aggregates") "aggregates"
    let casesArr ← (← j.getObjVal? "cases").getArr?
    let cases ← casesArr.toList.mapM parseAnomalyCaseSummary
    pure {
      runId := runId
      evaluatedCaseCount := evalCount
      evaluatedCaseCountPos := hPos
      datasetCapped := capped
      mandatoryFailedCaseIds := mand
      aggregates := aggs
      cases := cases
    }
  else
    throw s!"evaluated_case_count must be >= 1, got {evalCount}"

private def parseAnomalyMetricDelta (j : Json) : Except String AnomalyMetricDelta := do
  let mid ← (← j.getObjVal? "metric_id").getStr?
  let delta ← parseOptUnitSignedRat j "delta"
  pure { metricId := mid, delta := delta }

private def parseAnomalyCaseDelta (j : Json) : Except String AnomalyCaseDelta := do
  let cid ← (← j.getObjVal? "case_id").getStr?
  let mArr ← (← j.getObjVal? "metric_deltas").getArr?
  let deltas ← mArr.toList.mapM parseAnomalyMetricDelta
  pure { caseId := cid, metricDeltas := deltas }

private def parseOptAnomalyComparison (obj : Json) (field : String) :
    Except String (Option AnomalyComparisonSummary) := do
  let val ← obj.getObjVal? field
  if val.isNull then
    pure none
  else
    let mArr ← (← val.getObjVal? "metric_comparisons").getArr?
    let mCmp ← mArr.toList.mapM parseAnomalyMetricDelta
    let cArr ← (← val.getObjVal? "case_comparisons").getArr?
    let cCmp ← cArr.toList.mapM parseAnomalyCaseDelta
    pure (some { metricComparisons := mCmp, caseComparisons := cCmp })

private def parseProvenanceSnapshot (j : Json) : Except String ProvenanceSnapshot := do
  let runId ← (← j.getObjVal? "run_id").getStr?
  let dsFp ← (← j.getObjVal? "dataset_fingerprint").getStr?
  let mVers ← parseKvStr (← j.getObjVal? "metric_versions")
  let judgeFp ← parseOptStrField j "judge_config_fingerprint"
  let embFp ← parseOptStrField j "embedding_config_fingerprint"
  let capped ← (← j.getObjVal? "dataset_capped").getBool?
  let caseIds ← parseStrList (← j.getObjVal? "case_ids")
  let sysVer ← parseOptStrField j "system_version"
  let modelId ← parseOptStrField j "model_id"
  let cfgFp ← parseOptStrField j "config_fingerprint"
  pure {
    runId := runId
    datasetFingerprint := dsFp
    metricVersions := mVers
    judgeConfigFingerprint := judgeFp
    embeddingConfigFingerprint := embFp
    datasetCapped := capped
    caseIds := caseIds
    systemVersion := sysVer
    modelId := modelId
    configFingerprint := cfgFp
  }

private def parseTrendRunEntry (j : Json) : Except String TrendRunEntry := do
  let runId ← (← j.getObjVal? "run_id").getStr?
  let ts ← parseIntField j "timestamp_key"
  let dsId ← (← j.getObjVal? "dataset_id").getStr?
  let modelId ← parseOptStrField j "model_id"
  let scores ← parseKvOptNNRat (← j.getObjVal? "metric_scores") "metric_scores"
  let prov ← parseProvenanceSnapshot (← j.getObjVal? "provenance")
  pure {
    runId := runId
    timestampKey := ts
    datasetId := dsId
    modelId := modelId
    metricScores := scores
    provenance := prov
  }

private def handleAnomalyCase (j : Json) : Except String Json := do
  let run ← parseAnomalyRunSummary (← j.getObjVal? "run")
  let cmp ← parseOptAnomalyComparison j "comparison"
  let policy ← parseAnomalyPolicy (← j.getObjVal? "policy")
  let flags := detectAnomalies run cmp policy
  pure (Json.mkObj [("anomalies", Json.arr (flags.toArray.map anomalyFlagToJson))])

private def handleTrendCase (j : Json) : Except String Json := do
  let runsArr ← (← j.getObjVal? "runs").getArr?
  let runs ← runsArr.toList.mapM parseTrendRunEntry
  let window ← parseNatField j "window"
  if window < 2 then
    throw s!"window must be >= 2, got {window}"
  let datasetId ← parseOptStrField j "dataset_id"
  let allDatasets ← (← j.getObjVal? "all_datasets").getBool?
  let modelId ← parseOptStrField j "model_id"
  let metricIds ← parseOptStrListField j "metric_ids"
  let slopeThr ← parsePosUnitNNRat (← j.getObjVal? "slope_threshold") "slope_threshold"
  let report := analyzeTrend runs window datasetId allDatasets modelId metricIds slopeThr
  pure (trendReportOutcomeToJson report)

private def handleDriftPair (j : Json) : Except String Json := do
  let baseline ← parseProvenanceSnapshot (← j.getObjVal? "baseline")
  let candidate ← parseProvenanceSnapshot (← j.getObjVal? "candidate")
  let warnings := detectDrift baseline candidate
  pure (Json.mkObj [("warnings", Json.arr (warnings.toArray.map driftWarningToJson))])

private def handleDriftWindow (j : Json) : Except String Json := do
  let runsArr ← (← j.getObjVal? "runs").getArr?
  let runs ← runsArr.toList.mapM parseProvenanceSnapshot
  let warnings := detectWindowDrift runs
  pure (Json.mkObj [("warnings", Json.arr (warnings.toArray.map driftWarningToJson))])

private def handleDriftCohort (j : Json) : Except String Json := do
  let baseArr ← (← j.getObjVal? "baseline_runs").getArr?
  let baseRuns ← baseArr.toList.mapM parseProvenanceSnapshot
  let candArr ← (← j.getObjVal? "candidate_runs").getArr?
  let candRuns ← candArr.toList.mapM parseProvenanceSnapshot
  let warnings := detectCohortDrift baseRuns candRuns
  pure (Json.mkObj [("warnings", Json.arr (warnings.toArray.map driftWarningToJson))])

private def evalStdinRequest (raw : String) : Except String Json := do
  let j ← Json.parse raw
  let kind ← (← j.getObjVal? "kind").getStr?
  match kind with
  | "anomaly_case" => handleAnomalyCase j
  | "trend_case" => handleTrendCase j
  | "drift_pair" => handleDriftPair j
  | "drift_window" => handleDriftWindow j
  | "drift_cohort" => handleDriftCohort j
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
      IO.eprintln s!"evalforge-regression-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-regression-oracle <export-golden|eval-stdin>"
    return 1
