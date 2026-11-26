import EvalForgeFormal.Regression.Types
import EvalForgeFormal.Retrieval.Preparation

namespace EvalForgeFormal.Regression

open EvalForgeFormal.Retrieval (dedupPreserveFirst)

/-! ## String Ordering & Association Helpers -/

/-- Total reflexive transitive string ordering via core `Ord.compare`. -/
def strLe (a b : String) : Bool :=
  compare a b != Ordering.gt

/-- Deduplicated sorted union of string lists (mirrors `sorted(set(a) | set(b))`). -/
def unionSortedStrings (a b : List String) : List String :=
  (dedupPreserveFirst (a ++ b)).mergeSort strLe

/-- Lookup metric version string in a `metricVersions` association list. -/
def lookupMetricVersion : List (String × String) → String → Option String
  | [], _ => none
  | (k, v) :: rest, target => if k = target then some v else lookupMetricVersion rest target

/-! ## Pairwise Provenance Drift (`_pair_provenance_drift`, `drift.py#L11-L120`) -/

/--
Formal model of `_pair_provenance_drift` (`drift.py#L11-L120`).
Intentionally ignores target-change fields (`systemVersion`, `modelId`, `configFingerprint`).
-/
def pairProvenanceDrift (baseline candidate : ProvenanceSnapshot) : List DriftWarningSpec :=
  let dsFlag : List DriftWarningSpec :=
    if baseline.datasetFingerprint != candidate.datasetFingerprint then
      [{
        category := .datasetFingerprint
        metricId := none
        baselineRunId := some baseline.runId
        candidateRunId := some candidate.runId
      }]
    else
      []
  let allMetrics := unionSortedStrings
    (baseline.metricVersions.map Prod.fst)
    (candidate.metricVersions.map Prod.fst)
  let metricFlags : List DriftWarningSpec :=
    allMetrics.filterMap fun mid =>
      match lookupMetricVersion baseline.metricVersions mid,
            lookupMetricVersion candidate.metricVersions mid with
      | some _, none =>
        some {
          category := .metricSet
          metricId := some mid
          baselineRunId := some baseline.runId
          candidateRunId := some candidate.runId
        }
      | none, some _ =>
        some {
          category := .metricSet
          metricId := some mid
          baselineRunId := some baseline.runId
          candidateRunId := some candidate.runId
        }
      | some bVer, some cVer =>
        if bVer != cVer then
          some {
            category := .metricVersion
            metricId := some mid
            baselineRunId := some baseline.runId
            candidateRunId := some candidate.runId
          }
        else
          none
      | none, none => none
  let judgeFlag : List DriftWarningSpec :=
    if baseline.judgeConfigFingerprint != candidate.judgeConfigFingerprint then
      [{
        category := .judgeConfig
        metricId := none
        baselineRunId := some baseline.runId
        candidateRunId := some candidate.runId
      }]
    else
      []
  let embFlag : List DriftWarningSpec :=
    if baseline.embeddingConfigFingerprint != candidate.embeddingConfigFingerprint then
      [{
        category := .embeddingConfig
        metricId := none
        baselineRunId := some baseline.runId
        candidateRunId := some candidate.runId
      }]
    else
      []
  dsFlag ++ metricFlags ++ judgeFlag ++ embFlag

/-! ## Pairwise Run Drift (`detect_drift`, `drift.py#L123-L169`) -/

/-- Returns `true` iff `a` and `b` differ as sets of case IDs (`added ≠ [] ∨ removed ≠ []`). -/
def caseSetsDiffer (baseIds candIds : List String) : Bool :=
  candIds.any (fun cid => !decide (cid ∈ baseIds)) ||
  baseIds.any (fun cid => !decide (cid ∈ candIds))

/-- Formal model of `detect_drift` (`drift.py#L123-L169`). -/
def detectDrift (baseline candidate : ProvenanceSnapshot) : List DriftWarningSpec :=
  let baseWarnings := pairProvenanceDrift baseline candidate
  let cappedFlag : List DriftWarningSpec :=
    if baseline.datasetCapped || candidate.datasetCapped then
      [{
        category := .datasetCapped
        metricId := none
        baselineRunId := some baseline.runId
        candidateRunId := some candidate.runId
      }]
    else
      []
  let caseFlag : List DriftWarningSpec :=
    if caseSetsDiffer baseline.caseIds candidate.caseIds then
      [{
        category := .caseSetMismatch
        metricId := none
        baselineRunId := some baseline.runId
        candidateRunId := some candidate.runId
      }]
    else
      []
  baseWarnings ++ cappedFlag ++ caseFlag

/-! ## Sliding-Window Drift (`detect_window_drift`, `drift.py#L172-L192`) -/

/-- Collect pairwise provenance drift across adjacent chronological pairs (`itertools.pairwise`). -/
def adjacentPairDrift : List ProvenanceSnapshot → List DriftWarningSpec
  | [] => []
  | [_] => []
  | a :: b :: rest => pairProvenanceDrift a b ++ adjacentPairDrift (b :: rest)

/-- Formal model of `detect_window_drift` (`drift.py#L172-L192`). -/
def detectWindowDrift (runs : List ProvenanceSnapshot) : List DriftWarningSpec :=
  let pairWarnings := adjacentPairDrift runs
  let cappedWarnings := runs.filterMap fun r =>
    if r.datasetCapped then
      some {
        category := .datasetCapped
        metricId := none
        baselineRunId := none
        candidateRunId := some r.runId
      }
    else
      none
  pairWarnings ++ cappedWarnings

/-! ## Cohort Drift & First-Seen Key Deduplication (`detect_cohort_drift`, `drift.py#L195-L236`) -/

/-- Auxiliary first-seen deduplicator on `DriftWarningSpec.key`. -/
def dedupDriftWarningsAux (seen : List DriftKey) : List DriftWarningSpec → List DriftWarningSpec
  | [] => []
  | w :: ws =>
    if w.key ∈ seen then
      dedupDriftWarningsAux seen ws
    else
      w :: dedupDriftWarningsAux (w.key :: seen) ws

/-- First-seen deduplication of drift warnings by 4-tuple key `(category, metricId, baselineRunId, candidateRunId)`. -/
def dedupDriftWarnings (warnings : List DriftWarningSpec) : List DriftWarningSpec :=
  dedupDriftWarningsAux [] warnings

/-- Drop the final element of a list (mirrors Python `xs[:-1]`). -/
def initList {α : Type} : List α → List α
  | [] => []
  | [_] => []
  | x :: xs => x :: initList xs

/-- Last element of a non-empty list, with default fallback. -/
def lastWithDefault {α : Type} (d : α) : List α → α
  | [] => d
  | [x] => x
  | _ :: xs => lastWithDefault d xs

/-- Formal model of `detect_cohort_drift` (`drift.py#L195-L236`). -/
def detectCohortDrift (baselineRuns candidateRuns : List ProvenanceSnapshot) :
    List DriftWarningSpec :=
  match baselineRuns, candidateRuns with
  | [], _ => []
  | _, [] => []
  | b0 :: bRest, c0 :: cRest =>
    let intraBase := bRest.flatMap (pairProvenanceDrift b0)
    let intraCand := cRest.flatMap (pairProvenanceDrift c0)
    let bLast := lastWithDefault b0 bRest
    let cLast := lastWithDefault c0 cRest
    let crossTail := detectDrift bLast cLast
    let nonTail := initList (b0 :: bRest) ++ initList (c0 :: cRest)
    let nonTailCapped := nonTail.filterMap fun r =>
      if r.datasetCapped then
        some {
          category := .datasetCapped
          metricId := none
          baselineRunId := none
          candidateRunId := some r.runId
        }
      else
        none
    dedupDriftWarnings (intraBase ++ intraCand ++ crossTail ++ nonTailCapped)

end EvalForgeFormal.Regression
