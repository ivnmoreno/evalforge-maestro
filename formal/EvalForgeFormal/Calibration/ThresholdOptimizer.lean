import EvalForgeFormal.Calibration.Types

namespace EvalForgeFormal.Calibration

open EvalForgeFormal.Retrieval

/-- Insert a normalized `NNRat` into a strictly ascending list, deduplicating equivalent values. -/
def insertUnique (x : NNRat) : List NNRat → List NNRat
  | [] => [NNRat.normalize x]
  | y :: ys =>
    let nx := NNRat.normalize x
    if nx < y then
      nx :: y :: ys
    else if y < nx then
      y :: insertUnique nx ys
    else
      y :: ys

/-- Sort and deduplicate a list of `NNRat` values into strictly ascending canonical form. -/
def sortUnique : List NNRat → List NNRat
  | [] => []
  | x :: xs => insertUnique x (sortUnique xs)

/-- Compute exact normalized midpoints between every adjacent pair of a sorted score list. -/
def adjacentMidpoints : List NNRat → List NNRat
  | [] => []
  | [_] => []
  | a :: b :: rest => NNRat.normalize (nnMidpoint a b) :: adjacentMidpoints (b :: rest)

/--
Build the deterministic candidate threshold grid matching `_optimize_pass_threshold`
in `src/evalforge_maestro/judges/calibration.py`:
`sorted({0, active_threshold, 1} ∪ unique_scores ∪ adjacent_midpoints)`.
-/
def buildCandidates (rows : List ValidRow) (activeThreshold : NNRat) : List NNRat :=
  let uniqueScores := sortUnique (rows.map (·.judgeScore))
  let base : List NNRat := [NNRat.zero, activeThreshold, NNRat.one]
  sortUnique (base ++ uniqueScores ++ adjacentMidpoints uniqueScores)

/-- Count `(agree, generous, harsh)` classifications over `rows` at candidate `threshold`. -/
def evalCountsAt (rows : List ValidRow) (threshold : NNRat) : Nat × Nat × Nat :=
  match rows with
  | [] => (0, 0, 0)
  | r :: rs =>
    let (ag, gen, har) := evalCountsAt rs threshold
    let judgePassed := decide (threshold ≤ r.judgeScore)
    if judgePassed == r.humanPassed then
      (ag + 1, gen, har)
    else if judgePassed then
      (ag, gen + 1, har)
    else
      (ag, gen, har + 1)

/-- Evaluate a single candidate threshold under the 3-tier calibration objective. -/
def scoreCandidate (rows : List ValidRow) (activeThreshold threshold : NNRat) : CandidateEval :=
  let (ag, gen, har) := evalCountsAt rows threshold
  {
    threshold := threshold
    agree := ag
    generous := gen
    harsh := har
    biasSkew := natAbsDiff gen har
    dist := NNRat.normalize (nnAbsDiff threshold activeThreshold)
  }

/-- Maximum `agree` across a non-empty list of candidate evaluations. -/
def maxAgreeOf (xs : List CandidateEval) : Nat :=
  xs.foldl (fun acc c => Nat.max acc c.agree) 0

/-- Minimum `biasSkew` across a non-empty list of candidate evaluations. -/
def minBiasSkewOf : List CandidateEval → Nat
  | [] => 0
  | c :: cs => cs.foldl (fun acc x => Nat.min acc x.biasSkew) c.biasSkew

/-- Minimum exact rational distance `|t - active_threshold|` across a non-empty candidate list. -/
def minDistOf : List CandidateEval → NNRat
  | [] => NNRat.zero
  | c :: cs =>
    cs.foldl (fun acc x => if x.dist ≤ acc then x.dist else acc) c.dist

/-- Extract the last element of a non-empty list. -/
def lastOf : (xs : List α) → xs ≠ [] → α
  | [x], _ => x
  | _ :: y :: ys, _ => lastOf (y :: ys) (List.cons_ne_nil y ys)

/--
Deterministic threshold optimizer mirroring `_optimize_pass_threshold` in
`src/evalforge_maestro/judges/calibration.py#L81-L127`:
1. Empty `rows` returns normalized `activeThreshold`.
2. Evaluates every candidate in `buildCandidates rows activeThreshold`.
3. Filters sequentially by `maxAgree`, `minBiasSkew`, and `minDist` (`winners`).
4. If `winners` is singleton, returns that unique winner; otherwise computes the
   normalized midpoint `(winners.head + winners.last) / 2` and returns it iff it
   preserves `(maxAgree, minBiasSkew)`, else returns `winners.last`.
-/
def optimizePassThreshold (rows : List ValidRow) (activeThreshold : NNRat) : NNRat :=
  if rows.isEmpty then
    NNRat.normalize activeThreshold
  else
    let candidates := buildCandidates rows activeThreshold
    let scored := candidates.map (scoreCandidate rows activeThreshold)
    let maxAg := maxAgreeOf scored
    let bestAgree := scored.filter (fun c => c.agree == maxAg)
    let minSkew := minBiasSkewOf bestAgree
    let bestBias := bestAgree.filter (fun c => c.biasSkew == minSkew)
    let minD := minDistOf bestBias
    let winners := (bestBias.filter (fun c => decide (c.dist ≈ minD))).map (·.threshold)
    match winners with
    | [] => NNRat.normalize activeThreshold
    | [w] => w
    | wFirst :: wSecond :: wRest =>
      let wLast := lastOf (wSecond :: wRest) (List.cons_ne_nil wSecond wRest)
      let mid := NNRat.normalize (nnMidpoint wFirst wLast)
      let midEval := scoreCandidate rows activeThreshold mid
      if midEval.agree == maxAg && midEval.biasSkew == minSkew then
        mid
      else
        wLast

end EvalForgeFormal.Calibration
