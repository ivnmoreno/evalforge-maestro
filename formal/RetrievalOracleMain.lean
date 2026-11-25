import Lean.Data.Json
import EvalForgeFormal.Retrieval.Metrics

open Lean
open EvalForgeFormal.Retrieval

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private structure MetricThresholds where
  precisionAtK : NNRat
  recallAtK : NNRat
  hitRateAtK : NNRat
  mrr : NNRat
  ndcgAtK : NNRat

private structure RetrievalCaseInput where
  caseId : String
  errors : List String
  expectedContext : List ExpectedItem
  retrievedChunks : List RetrievedItem
  k : Nat
  hk : 0 < k
  matchParentId : Bool
  thresholds : MetricThresholds

private def defaultThresholds : MetricThresholds :=
  let half : NNRat := ⟨1, 2, by omega⟩
  {
    precisionAtK := half
    recallAtK := half
    hitRateAtK := NNRat.one
    mrr := half
    ndcgAtK := half
  }

private def zeroThresholds : MetricThresholds :=
  {
    precisionAtK := NNRat.zero
    recallAtK := NNRat.zero
    hitRateAtK := NNRat.zero
    mrr := NNRat.zero
    ndcgAtK := NNRat.zero
  }

private def nnratToJson (r : NNRat) : Json :=
  let norm := NNRat.normalize r
  Json.mkObj [
    ("den", Json.num norm.den),
    ("num", Json.num norm.num)
  ]

private def optNNRatToJson : Option NNRat → Json
  | some r => nnratToJson r
  | none => Json.null

private def optStrToJson : Option String → Json
  | some s => Json.str s
  | none => Json.null

private def optNatToJson : Option Nat → Json
  | some n => Json.num n
  | none => Json.null

private def strListToJson (xs : List String) : Json :=
  Json.arr (xs.toArray.map Json.str)

private def natListToJson (xs : List Nat) : Json :=
  Json.arr (xs.toArray.map (fun (n : Nat) => Json.num n))

private def expectedItemToJson (e : ExpectedItem) : Json :=
  Json.mkObj [
    ("id", Json.str e.id),
    ("relevance", Json.num e.relevance)
  ]

private def gPosEntryToJson (p : String × Nat) : Json :=
  Json.mkObj [
    ("id", Json.str p.1),
    ("relevance", Json.num p.2)
  ]

private def retrievedItemToJson (c : RetrievedItem) : Json :=
  Json.mkObj [
    ("id", Json.str c.id),
    ("parent_id", optStrToJson c.parentId),
    ("rank", optNatToJson c.rank)
  ]

private def thresholdsToJson (t : MetricThresholds) : Json :=
  Json.mkObj [
    ("hit_rate_at_k", nnratToJson t.hitRateAtK),
    ("mrr", nnratToJson t.mrr),
    ("ndcg_at_k", nnratToJson t.ndcgAtK),
    ("precision_at_k", nnratToJson t.precisionAtK),
    ("recall_at_k", nnratToJson t.recallAtK)
  ]

private def metricOutcomeToJson (o : MetricOutcome) : Json :=
  Json.mkObj [
    ("evidence", strListToJson o.evidence),
    ("score_exact", optNNRatToJson o.score),
    ("status", Json.str o.status.toCanonicalString)
  ]

private def evalRetrievalCaseToJson (c : RetrievalCaseInput) : Json :=
  let prep := prepareIREvaluation c.errors c.expectedContext c.retrievedChunks c.matchParentId
  let precOut := evaluatePrecisionAtK c.errors c.expectedContext c.retrievedChunks c.k c.hk c.matchParentId c.thresholds.precisionAtK
  let recOut := evaluateRecallAtK c.errors c.expectedContext c.retrievedChunks c.k c.matchParentId c.thresholds.recallAtK
  let hrOut := evaluateHitRateAtK c.errors c.expectedContext c.retrievedChunks c.k c.matchParentId c.thresholds.hitRateAtK
  let mrrOut := evaluateMRR c.errors c.expectedContext c.retrievedChunks c.matchParentId c.thresholds.mrr
  let ndcgOut := evaluateNDCGAtK harmonicDiscount c.errors c.expectedContext c.retrievedChunks c.k c.hk c.matchParentId c.thresholds.ndcgAtK
  let (prepStatusStr, gPosJson, rankedIdsJson, topKJson, hitsJson, firstRankJson, firstIdJson, ndcgJson) :=
    match prep with
    | .inconclusive errs =>
      ( "INCONCLUSIVE"
      , Json.arr #[]
      , Json.arr #[]
      , Json.arr #[]
      , Json.arr #[]
      , Json.null
      , Json.null
      , Json.mkObj [
          ("actual_gains", Json.arr #[]),
          ("evidence", strListToJson errs),
          ("guard_status", Json.str "INCONCLUSIVE"),
          ("harmonic_ndcg_exact", Json.null),
          ("harmonic_status", Json.str ndcgOut.status.toCanonicalString),
          ("ideal_gains", Json.arr #[])
        ]
      )
    | .notApplicable =>
      let prepared := prepareRetrievalInputs c.expectedContext c.retrievedChunks c.matchParentId
      ( "NOT_APPLICABLE"
      , Json.arr #[]
      , strListToJson prepared.rankedIds
      , strListToJson (prepared.rankedIds.take c.k)
      , Json.arr #[]
      , Json.null
      , Json.null
      , Json.mkObj [
          ("actual_gains", Json.arr #[]),
          ("evidence", Json.arr #[]),
          ("guard_status", Json.str "NOT_APPLICABLE"),
          ("harmonic_ndcg_exact", Json.null),
          ("harmonic_status", Json.str ndcgOut.status.toCanonicalString),
          ("ideal_gains", Json.arr #[])
        ]
      )
    | .ready gPos rankedIds =>
      let topK := rankedIds.take c.k
      let hits := extractHits c.k gPos rankedIds
      let fm := firstMatch gPos rankedIds
      let fRank := fm.map Prod.fst
      let fId := fm.map Prod.snd
      let actGains := actualGains c.k gPos rankedIds
      let idGains := idealGains c.k gPos
      ( "READY"
      , Json.arr (gPos.toArray.map gPosEntryToJson)
      , strListToJson rankedIds
      , strListToJson topK
      , strListToJson hits
      , optNatToJson fRank
      , optStrToJson fId
      , Json.mkObj [
          ("actual_gains", natListToJson actGains),
          ("evidence", strListToJson hits),
          ("guard_status", Json.str "READY"),
          ("harmonic_ndcg_exact", optNNRatToJson ndcgOut.score),
          ("harmonic_status", Json.str ndcgOut.status.toCanonicalString),
          ("ideal_gains", natListToJson idGains)
        ]
      )
  Json.mkObj [
    ("case_id", Json.str c.caseId),
    ("first_match_id", firstIdJson),
    ("first_match_rank", firstRankJson),
    ("g_pos", gPosJson),
    ("hit_rate_at_k", metricOutcomeToJson hrOut),
    ("hits", hitsJson),
    ("mrr", metricOutcomeToJson mrrOut),
    ("ndcg_at_k", ndcgJson),
    ("precision_at_k", metricOutcomeToJson precOut),
    ("prep_status", Json.str prepStatusStr),
    ("ranked_ids", rankedIdsJson),
    ("recall_at_k", metricOutcomeToJson recOut),
    ("top_k_ids", topKJson)
  ]

private def mkGoldenVector (c : RetrievalCaseInput) : Json :=
  Json.mkObj [
    ("expected", evalRetrievalCaseToJson c),
    ("input", Json.mkObj [
      ("errors", strListToJson c.errors),
      ("expected_context", Json.arr (c.expectedContext.toArray.map expectedItemToJson)),
      ("k", Json.num c.k),
      ("match_parent_id", Json.bool c.matchParentId),
      ("retrieved_chunks", Json.arr (c.retrievedChunks.toArray.map retrievedItemToJson)),
      ("thresholds", thresholdsToJson c.thresholds)
    ]),
    ("vector_id", Json.str c.caseId)
  ]

private def gradedExpected : List ExpectedItem := [
  { id := "d1", relevance := 3 },
  { id := "d2", relevance := 2 },
  { id := "d0", relevance := 0 },
  { id := "d3", relevance := 1 }
]

private def gradedRetrieved : List RetrievedItem := [
  { id := "d3", parentId := none, rank := some 1 },
  { id := "d1", parentId := none, rank := some 2 },
  { id := "d0", parentId := none, rank := some 3 },
  { id := "d2", parentId := none, rank := some 4 },
  { id := "d9", parentId := none, rank := some 5 }
]

private def canonicalRetrievalVectors : List RetrievalCaseInput := [
  {
    caseId := "guard_errors_with_empty_gt"
    errors := ["timeout"]
    expectedContext := []
    retrievedChunks := []
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "guard_errors_with_all_zero_gt"
    errors := ["adapter crashed"]
    expectedContext := [{ id := "d1", relevance := 0 }]
    retrievedChunks := [{ id := "d1", parentId := none, rank := some 1 }]
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "guard_errors_with_valid_gt"
    errors := ["rate_limit", "retry_exhausted"]
    expectedContext := [{ id := "d1", relevance := 1 }]
    retrievedChunks := [{ id := "d1", parentId := none, rank := some 1 }]
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "guard_empty_gt"
    errors := []
    expectedContext := []
    retrievedChunks := [{ id := "d1", parentId := none, rank := some 1 }]
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "guard_all_zero_gt"
    errors := []
    expectedContext := [{ id := "d1", relevance := 0 }, { id := "d2", relevance := 0 }]
    retrievedChunks := [{ id := "d1", parentId := none, rank := some 1 }, { id := "d2", parentId := none, rank := some 2 }]
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "empty_retrieval_default_thresholds"
    errors := []
    expectedContext := [{ id := "d1", relevance := 1 }, { id := "d2", relevance := 2 }]
    retrievedChunks := []
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "empty_retrieval_zero_threshold_pass"
    errors := []
    expectedContext := [{ id := "d1", relevance := 1 }]
    retrievedChunks := []
    k := 3
    hk := by omega
    matchParentId := false
    thresholds := zeroThresholds
  },
  {
    caseId := "under_retrieval_preserves_k"
    errors := []
    expectedContext := [{ id := "d1", relevance := 1 }, { id := "d2", relevance := 1 }]
    retrievedChunks := [{ id := "d1", parentId := none, rank := some 1 }]
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "exact_cutoff_perfect_order"
    errors := []
    expectedContext := [
      { id := "d1", relevance := 3 },
      { id := "d2", relevance := 2 },
      { id := "d3", relevance := 1 }
    ]
    retrievedChunks := [
      { id := "d1", parentId := none, rank := some 1 },
      { id := "d2", parentId := none, rank := some 2 },
      { id := "d3", parentId := none, rank := some 3 }
    ]
    k := 3
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "over_retrieval_and_mrr_beyond_k"
    errors := []
    expectedContext := [{ id := "d4", relevance := 1 }]
    retrievedChunks := [
      { id := "d1", parentId := none, rank := some 1 },
      { id := "d2", parentId := none, rank := some 2 },
      { id := "d3", parentId := none, rank := some 3 },
      { id := "d4", parentId := none, rank := some 4 },
      { id := "d5", parentId := none, rank := some 5 }
    ]
    k := 2
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "out_of_order_ranks_and_null_tiebreak"
    errors := []
    expectedContext := [{ id := "c-rank1", relevance := 1 }]
    retrievedChunks := [
      { id := "c-pos0-no-rank", parentId := some "doc-late", rank := none },
      { id := "c-rank2", parentId := some "doc-b", rank := some 2 },
      { id := "c-rank1", parentId := some "doc-a", rank := some 1 },
      { id := "c-rank1", parentId := some "doc-a", rank := some 5 },
      { id := "c-sibling", parentId := some "doc-a", rank := some 3 }
    ]
    k := 2
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "duplicate_chunk_ids_anti_inflation"
    errors := []
    expectedContext := [{ id := "d1", relevance := 1 }]
    retrievedChunks := [
      { id := "d1", parentId := none, rank := some 1 },
      { id := "d1", parentId := none, rank := some 2 },
      { id := "d1", parentId := none, rank := some 3 },
      { id := "d2", parentId := none, rank := some 4 }
    ]
    k := 3
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "match_parent_id_sibling_dedup_and_fallbacks"
    errors := []
    expectedContext := [
      { id := "doc-a", relevance := 2 },
      { id := "only-id", relevance := 1 },
      { id := "empty-parent-id", relevance := 1 }
    ]
    retrievedChunks := [
      { id := "c-pos0-no-rank", parentId := some "doc-late", rank := none },
      { id := "c-rank1", parentId := some "doc-a", rank := some 1 },
      { id := "c-sibling", parentId := some "doc-a", rank := some 2 },
      { id := "only-id", parentId := none, rank := some 3 },
      { id := "empty-parent-id", parentId := some "", rank := some 4 }
    ]
    k := 4
    hk := by omega
    matchParentId := true
    thresholds := defaultThresholds
  },
  {
    caseId := "duplicate_expected_ids_last_positive_and_zero_noop"
    errors := []
    expectedContext := [
      { id := "d1", relevance := 1 },
      { id := "d1", relevance := 3 },
      { id := "d1", relevance := 0 },
      { id := "d2", relevance := 2 }
    ]
    retrievedChunks := [
      { id := "d2", parentId := none, rank := some 1 },
      { id := "d1", parentId := none, rank := some 2 }
    ]
    k := 2
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "cutoff_sweep_k1"
    errors := []
    expectedContext := gradedExpected
    retrievedChunks := gradedRetrieved
    k := 1
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "cutoff_sweep_k2"
    errors := []
    expectedContext := gradedExpected
    retrievedChunks := gradedRetrieved
    k := 2
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  },
  {
    caseId := "cutoff_sweep_k3"
    errors := []
    expectedContext := gradedExpected
    retrievedChunks := gradedRetrieved
    k := 3
    hk := by omega
    matchParentId := false
    thresholds := {
      precisionAtK := ⟨2, 5, by omega⟩
      recallAtK := ⟨4, 5, by omega⟩
      hitRateAtK := NNRat.one
      mrr := ⟨4, 5, by omega⟩
      ndcgAtK := ⟨4, 5, by omega⟩
    }
  },
  {
    caseId := "cutoff_sweep_k5"
    errors := []
    expectedContext := gradedExpected
    retrievedChunks := gradedRetrieved
    k := 5
    hk := by omega
    matchParentId := false
    thresholds := defaultThresholds
  }
]

private def buildGoldenJson : Json :=
  let vectors := canonicalRetrievalVectors.map mkGoldenVector
  Json.mkObj [
    ("canonical_vectors", Json.arr vectors.toArray),
    ("guard_precedence_order", Json.arr #[
      Json.str "INCONCLUSIVE",
      Json.str "NOT_APPLICABLE",
      Json.str "NUMERIC"
    ]),
    ("harmonic_discount_schedule", Json.str "1/(rank+1)"),
    ("lean_toolchain", Json.str leanToolchain),
    ("metric_ids", Json.arr #[
      Json.str "precision_at_k",
      Json.str "recall_at_k",
      Json.str "hit_rate_at_k",
      Json.str "mrr",
      Json.str "ndcg_at_k"
    ]),
    ("schema_version", Json.str schemaVersion)
  ]

private def parseStringList (obj : Json) (field : String) : Except String (List String) := do
  let raw ← obj.getObjVal? field
  let arr ← raw.getArr?
  let mut out : List String := []
  for elem in arr do
    let s ← elem.getStr?
    out := out ++ [s]
  return out

private def parseUnitRat (j : Json) (label : String) : Except String NNRat := do
  let num ← (← j.getObjVal? "num").getNat?
  let den ← (← j.getObjVal? "den").getNat?
  if h : 0 < den then
    if num ≤ den then
      return ⟨num, den, h⟩
    else
      throw s!"Threshold '{label}' out of [0, 1] bounds: {num}/{den}"
  else
    throw s!"Threshold '{label}' denominator must be >= 1, got {den}"

private def parseThresholds (j : Json) : Except String MetricThresholds := do
  let p ← parseUnitRat (← j.getObjVal? "precision_at_k") "precision_at_k"
  let r ← parseUnitRat (← j.getObjVal? "recall_at_k") "recall_at_k"
  let hr ← parseUnitRat (← j.getObjVal? "hit_rate_at_k") "hit_rate_at_k"
  let m ← parseUnitRat (← j.getObjVal? "mrr") "mrr"
  let n ← parseUnitRat (← j.getObjVal? "ndcg_at_k") "ndcg_at_k"
  return { precisionAtK := p, recallAtK := r, hitRateAtK := hr, mrr := m, ndcgAtK := n }

private def parseExpectedItem (j : Json) : Except String ExpectedItem := do
  let id ← (← j.getObjVal? "id").getStr?
  let rel ← (← j.getObjVal? "relevance").getNat?
  return { id := id, relevance := rel }

private def parseRetrievedItem (j : Json) : Except String RetrievedItem := do
  let id ← (← j.getObjVal? "id").getStr?
  let parentRaw ← j.getObjVal? "parent_id"
  let parentId : Option String ←
    if parentRaw.isNull then pure none else pure (some (← parentRaw.getStr?))
  let rankRaw ← j.getObjVal? "rank"
  let rankOpt : Option Nat ←
    if rankRaw.isNull then
      pure none
    else
      let r ← rankRaw.getNat?
      if r = 0 then
        throw s!"RetrievedItem.rank must be >= 1 when present, got {r}"
      else
        pure (some r)
  return { id := id, parentId := parentId, rank := rankOpt }

private def parseCaseInput (j : Json) : Except String RetrievalCaseInput := do
  let caseId ← (← j.getObjVal? "case_id").getStr?
  let errors ← parseStringList j "errors"
  let expArr ← (← j.getObjVal? "expected_context").getArr?
  let mut expected : List ExpectedItem := []
  for elem in expArr do
    expected := expected ++ [← parseExpectedItem elem]
  let retArr ← (← j.getObjVal? "retrieved_chunks").getArr?
  let mut retrieved : List RetrievedItem := []
  for elem in retArr do
    retrieved := retrieved ++ [← parseRetrievedItem elem]
  let k ← (← j.getObjVal? "k").getNat?
  if hk : 0 < k then
    let matchParentId ← (← j.getObjVal? "match_parent_id").getBool?
    let thresholds ← parseThresholds (← j.getObjVal? "thresholds")
    return {
      caseId := caseId
      errors := errors
      expectedContext := expected
      retrievedChunks := retrieved
      k := k
      hk := hk
      matchParentId := matchParentId
      thresholds := thresholds
    }
  else
    throw s!"RetrievalEvalCaseInput.k must be >= 1, got {k}"

private def evalStdinPayload (raw : String) : Except String Json := do
  let req ← Json.parse raw
  let ver ← (← req.getObjVal? "schema_version").getStr?
  if ver != schemaVersion then
    throw s!"Unsupported schema_version: expected '{schemaVersion}', got '{ver}'"
  let casesArr ← (← req.getObjVal? "cases").getArr?
  let mut results : Array Json := #[]
  for item in casesArr do
    let parsed ← parseCaseInput item
    results := results.push (evalRetrievalCaseToJson parsed)
  return Json.mkObj [
    ("results", Json.arr results),
    ("schema_version", Json.str schemaVersion)
  ]

def main (args : List String) : IO UInt32 := do
  match args with
  | ["export-golden"] =>
    IO.println (buildGoldenJson.pretty 2)
    return 0
  | ["eval-stdin"] =>
    let stdin ← IO.getStdin
    let raw ← stdin.readToEnd
    match evalStdinPayload raw with
    | .ok resp =>
      IO.println (resp.pretty 2)
      return 0
    | .error err =>
      IO.eprintln s!"evalforge-retrieval-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-retrieval-oracle <export-golden | eval-stdin>"
    return 2
