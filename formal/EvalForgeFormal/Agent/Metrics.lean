import EvalForgeFormal.Agent.Preparation

namespace EvalForgeFormal.Agent

open EvalForgeFormal.Retrieval (NNRat enumFrom dedupPreserveFirst)

/-! ## Metric 1: `tool_selection` (`agent.py#L135-L200`) -/

/-- Deduplicated required tool names (non-optional items, falling back to all items if all optional). -/
def requiredToolNames (expected : List ExpectedTool) : List String :=
  let nonOpt := (expected.filter (fun e => !e.optional)).map ExpectedTool.name
  let base := if nonOpt.isEmpty then expected.map ExpectedTool.name else nonOpt
  dedupPreserveFirst base

/-- Deduplicated allowed tool names (all expected items, required or optional). -/
def allowedToolNames (expected : List ExpectedTool) : List String :=
  dedupPreserveFirst (expected.map ExpectedTool.name)

/-- Deduplicated invoked tool names. -/
def calledToolNames (calls : List ToolCall) : List String :=
  dedupPreserveFirst (calls.map ToolCall.name)

/-- True positive count `|called ∩ req|`. -/
def toolSelectionTp (req called : List String) : Nat :=
  (called.filter (fun n => decide (n ∈ req))).length

/-- False positive count `|called \ allowed|`. -/
def toolSelectionFp (allowed called : List String) : Nat :=
  (called.filter (fun n => !decide (n ∈ allowed))).length

/-- Missing required tool count `|req \ called|`. -/
def toolSelectionMissingCount (req called : List String) : Nat :=
  (req.filter (fun n => !decide (n ∈ called))).length

/-- Non-emptiness witness for `requiredToolNames` whenever `expected ≠ []`. -/
theorem requiredToolNames_pos_of_ne_nil {expected : List ExpectedTool} (h : expected ≠ []) :
    0 < (requiredToolNames expected).length := by
  unfold requiredToolNames
  cases expected with
  | nil => exact False.elim (h rfl)
  | cons e es =>
    by_cases hEmpty : ((e :: es).filter (fun x => !x.optional)).map ExpectedTool.name = []
    · simp only [hEmpty, List.isEmpty_nil, ↓reduceIte, List.map_cons]
      unfold dedupPreserveFirst EvalForgeFormal.Retrieval.dedupPreserveFirstAux
      simp
    · cases hNonOpt : ((e :: es).filter (fun x => !x.optional)).map ExpectedTool.name with
      | nil => exact False.elim (hEmpty hNonOpt)
      | cons r rs =>
        simp only [List.isEmpty_cons, Bool.false_eq_true, ↓reduceIte]
        unfold dedupPreserveFirst EvalForgeFormal.Retrieval.dedupPreserveFirstAux
        simp

/-- Exact rational recall `tp / |req|` for `tool_selection`. -/
def toolSelectionRecall (expected : List ExpectedTool) (calls : List ToolCall)
    (hNe : expected ≠ []) : NNRat :=
  let req := requiredToolNames expected
  let called := calledToolNames calls
  ⟨toolSelectionTp req called, req.length, requiredToolNames_pos_of_ne_nil hNe⟩

/-- Exact rational precision `tp / (tp + fp)` (or `0` when `tp + fp = 0`) for `tool_selection`. -/
def toolSelectionPrecision (expected : List ExpectedTool) (calls : List ToolCall) : NNRat :=
  let req := requiredToolNames expected
  let allowed := allowedToolNames expected
  let called := calledToolNames calls
  let tp := toolSelectionTp req called
  let fp := toolSelectionFp allowed called
  if h : 0 < tp + fp then ⟨tp, tp + fp, h⟩ else NNRat.zero

/-- Exact rational F1 (`2 * tp / (|req| + tp + fp)` when `tp > 0`, else `0`) for `tool_selection`. -/
def toolSelectionF1 (expected : List ExpectedTool) (calls : List ToolCall)
    (hNe : expected ≠ []) : NNRat :=
  let req := requiredToolNames expected
  let allowed := allowedToolNames expected
  let called := calledToolNames calls
  let tp := toolSelectionTp req called
  let fp := toolSelectionFp allowed called
  if tp = 0 then
    NNRat.zero
  else
    have hPos : 0 < req.length + tp + fp := by
      have hr : 0 < req.length := requiredToolNames_pos_of_ne_nil hNe
      omega
    ⟨2 * tp, req.length + tp + fp, hPos⟩

/-- Exact rational `exact_set` indicator (`1` iff `missing = 0 ∧ fp = 0`, else `0`). -/
def toolSelectionExactSet (expected : List ExpectedTool) (calls : List ToolCall) : NNRat :=
  let req := requiredToolNames expected
  let allowed := allowedToolNames expected
  let called := calledToolNames calls
  if toolSelectionMissingCount req called == 0 && toolSelectionFp allowed called == 0 then
    NNRat.one
  else
    NNRat.zero

/-- Exact rational score for `tool_selection` under the chosen mode. -/
def toolSelectionScore (mode : ToolSelectionMode) (expected : List ExpectedTool)
    (calls : List ToolCall) (hNe : expected ≠ []) : NNRat :=
  match mode with
  | .recall => toolSelectionRecall expected calls hNe
  | .exactSet => toolSelectionExactSet expected calls
  | .f1 => toolSelectionF1 expected calls hNe

/-- Full evaluator for `tool_selection` (`agent.py#L135-L200`). -/
def evaluateToolSelection
    (mode : ToolSelectionMode)
    (errors : List String)
    (expected : List ExpectedTool)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "tool_selection" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    if h : expected = [] then
      { status := .notApplicable, score := none, threshold := threshold }
    else
      finalizeAgentMetric (toolSelectionScore mode expected calls h) threshold

/-! ## Metric 2: `argument_correctness` (`agent.py#L100-L132`, `#L203-L270`) -/

/-- Exact rational dictionary-argument score (`exact` vs. `subset` mode). -/
def scoreDictArgs (expArgs callArgs : List (String × String)) (useExact : Bool) : NNRat :=
  if useExact then
    if argMapsEqual callArgs expArgs then NNRat.one else NNRat.zero
  else
    match expArgs.length with
    | 0 => NNRat.one
    | n + 1 => ⟨countMatchedKeys expArgs callArgs, n + 1, Nat.succ_pos n⟩

/--
Formal model of `_score_single_call_args` (`agent.py#L100-L132`).
`schemaValid` is supplied by `SchemaOracle constrainedExpIdx callIdx`.
-/
def scoreSingleCallArgs
    (exp : ExpectedTool)
    (call : ToolCall)
    (strictMode : Bool)
    (schemaValid : Bool) : NNRat :=
  if call.argumentParseError.isSome then
    NNRat.zero
  else
    let useExact := strictMode || (exp.argumentMatchMode == .exact)
    match exp.hasSchema, exp.arguments with
    | true, some expArgs =>
      let sScore := if schemaValid then NNRat.one else NNRat.zero
      let dScore := scoreDictArgs expArgs call.arguments useExact
      NNRat.div (NNRat.add sScore dScore) (NNRat.ofNat 2) (by decide)
    | true, none =>
      if schemaValid then NNRat.one else NNRat.zero
    | false, some expArgs =>
      scoreDictArgs expArgs call.arguments useExact
    | false, none =>
      NNRat.zero

/-- Filter expected tools to those declaring `arguments` or `arguments_schema`. -/
def constrainedExpectedTools (expected : List ExpectedTool) : List ExpectedTool :=
  expected.filter (fun item => item.arguments.isSome || item.hasSchema)

/-- Greedy search for the earliest unconsumed call of matching tool name achieving maximal score. -/
def findBestCallAux
    (exp : ExpectedTool)
    (expIdx : Nat)
    (strictMode : Bool)
    (schemaOracle : SchemaOracle)
    (used : List Nat) :
    List (Nat × ToolCall) → Option (Nat × NNRat) → Option (Nat × NNRat)
  | [], best => best
  | (callIdx, call) :: rest, best =>
    if callIdx ∈ used || call.name != exp.name then
      findBestCallAux exp expIdx strictMode schemaOracle used rest best
    else
      let cand := scoreSingleCallArgs exp call strictMode (schemaOracle expIdx callIdx)
      let nextBest :=
        match best with
        | none => some (callIdx, cand)
        | some (_, bScore) =>
          if NNRat.leBool cand bScore then best else some (callIdx, cand)
      findBestCallAux exp expIdx strictMode schemaOracle used rest nextBest

/-- Greedy one-to-one matching loop across indexed constrained expectations (`agent.py#L238-L255`). -/
def greedyMatchLoop
    (calls : List ToolCall)
    (strictMode : Bool)
    (schemaOracle : SchemaOracle)
    (used : List Nat)
    (accScores : List NNRat) :
    List (Nat × ExpectedTool) → List Nat × List NNRat
  | [] => (used, accScores)
  | (expIdx, exp) :: rest =>
    match findBestCallAux exp expIdx strictMode schemaOracle used (enumFrom 0 calls) none with
    | none =>
      greedyMatchLoop calls strictMode schemaOracle used (accScores ++ [NNRat.zero]) rest
    | some (bestIdx, bestScore) =>
      greedyMatchLoop calls strictMode schemaOracle (bestIdx :: used)
        (accScores ++ [bestScore]) rest

/-- Sum a list of exact non-negative rationals. -/
def sumNNRat : List NNRat → NNRat
  | [] => NNRat.zero
  | r :: rs => NNRat.add r (sumNNRat rs)

/-- Exact rational score for `argument_correctness` given non-empty `constrained` expectations. -/
def argumentCorrectnessScore
    (constrained : List ExpectedTool)
    (calls : List ToolCall)
    (strictMode : Bool)
    (schemaOracle : SchemaOracle)
    (hNe : constrained ≠ []) : NNRat :=
  let (_, itemScores) := greedyMatchLoop calls strictMode schemaOracle [] [] (enumFrom 0 constrained)
  have hLenPos : 0 < constrained.length := List.length_pos_iff.mpr hNe
  NNRat.div (sumNNRat itemScores) (NNRat.ofNat constrained.length) hLenPos

/-- Full evaluator for `argument_correctness` (`agent.py#L203-L270`). -/
def evaluateArgumentCorrectness
    (strictMode : Bool)
    (errors : List String)
    (expected : List ExpectedTool)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (schemaOracle : SchemaOracle)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "argument_correctness" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    let constrained := constrainedExpectedTools expected
    if h : constrained = [] then
      { status := .notApplicable, score := none, threshold := threshold }
    else
      finalizeAgentMetric (argumentCorrectnessScore constrained calls strictMode schemaOracle h) threshold

/-! ## Metric 3: `execution_sequence` (`agent.py#L273-L336`) -/

/-- Ordered required tool name sequence (non-optional items, falling back to all ordered items). -/
def requiredSequence (expected : List ExpectedTool) : List String :=
  let ordered := orderedExpectedTools expected
  let nonOpt := ordered.filter (fun item => !item.optional)
  let reqItems := if nonOpt.isEmpty then ordered else nonOpt
  reqItems.map ExpectedTool.name

/-- Non-emptiness witness for `requiredSequence` whenever `expected ≠ []`. -/
theorem requiredSequence_pos_of_ne_nil {expected : List ExpectedTool} (h : expected ≠ []) :
    0 < (requiredSequence expected).length := by
  unfold requiredSequence
  have hOrdLen : (orderedExpectedTools expected).length = expected.length := by
    unfold orderedExpectedTools orderedExpectedToolsIndexed
    split
    · rw [List.length_map]
      have hPerm := List.mergeSort_perm (enumFrom 0 expected) (expectedSortKeyLe expected.length)
      rw [hPerm.length_eq]
      clear hPerm
      have hEnumLen : ∀ (k : Nat) (xs : List ExpectedTool), (enumFrom k xs).length = xs.length := by
        intro k xs
        induction xs generalizing k with
        | nil => rfl
        | cons _ _ ih => simp [enumFrom, ih]
      exact hEnumLen 0 expected
    · rw [List.length_map]
      have hEnumLen : ∀ (k : Nat) (xs : List ExpectedTool), (enumFrom k xs).length = xs.length := by
        intro k xs
        induction xs generalizing k with
        | nil => rfl
        | cons _ _ ih => simp [enumFrom, ih]
      exact hEnumLen 0 expected
  have hPos : 0 < expected.length := List.length_pos_iff.mpr h
  dsimp only
  cases hNonOpt : (orderedExpectedTools expected).filter (fun item => !item.optional) with
  | nil =>
    simp only [List.isEmpty_nil, ↓reduceIte, List.length_map]
    omega
  | cons _ _ =>
    simp only [List.isEmpty_cons, Bool.false_eq_true, ↓reduceIte, List.length_map, List.length_cons]
    omega

/-- Longest common prefix length between `expSeq` and `actSeq` (`agent.py#L308-L312`). -/
def prefixMatchCount : List String → List String → Nat
  | [], _ => 0
  | _, [] => 0
  | e :: es, a :: as => if e = a then 1 + prefixMatchCount es as else 0

/-- Greedy left-to-right ordered subsequence match count (`agent.py#L315-L320`). -/
def subseqMatchCount : List String → List String → Nat
  | [], _ => 0
  | _, [] => 0
  | e :: es, a :: as =>
    if e = a then 1 + subseqMatchCount es as
    else subseqMatchCount (e :: es) as

/-- Exact rational score for `execution_sequence` on raw sequences `expSeq` (`≠ []`) and `actSeq`. -/
def executionSequenceRawScore (mode : SequenceMode) (expSeq actSeq : List String)
    (hPos : 0 < expSeq.length) : NNRat :=
  match mode with
  | .exact => if actSeq == expSeq then NNRat.one else NNRat.zero
  | .prefix => ⟨prefixMatchCount expSeq actSeq, expSeq.length, hPos⟩
  | .subsequence => ⟨subseqMatchCount expSeq actSeq, expSeq.length, hPos⟩

/-- Exact rational score for `execution_sequence` from `expected` (`≠ []`) and `calls`. -/
def executionSequenceScore (mode : SequenceMode) (expected : List ExpectedTool)
    (calls : List ToolCall) (hNe : expected ≠ []) : NNRat :=
  executionSequenceRawScore mode (requiredSequence expected) (calls.map ToolCall.name)
    (requiredSequence_pos_of_ne_nil hNe)

/-- Full evaluator for `execution_sequence` (`agent.py#L273-L336`). -/
def evaluateExecutionSequence
    (mode : SequenceMode)
    (errors : List String)
    (expected : List ExpectedTool)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "execution_sequence" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    if h : expected = [] then
      { status := .notApplicable, score := none, threshold := threshold }
    else
      finalizeAgentMetric (executionSequenceScore mode expected calls h) threshold

/-! ## Metric 4: `tool_efficiency` (`agent.py#L339-L419`) -/

/-- Sequential redundant failing-signature loop counter (`agent.py#L379-L389`). -/
def countRedundantLoopsAux (seenFailed : List String) : List ToolCall → Nat
  | [] => 0
  | c :: cs =>
    if c.status != .success then
      if c.canonicalSig ∈ seenFailed then
        1 + countRedundantLoopsAux seenFailed cs
      else
        countRedundantLoopsAux (c.canonicalSig :: seenFailed) cs
    else
      countRedundantLoopsAux seenFailed cs

/-- Total redundant identical failing tool-call repeats across `calls`. -/
def countRedundantLoops (calls : List ToolCall) : Nat :=
  countRedundantLoopsAux [] calls

/-- Step or call budget factor: `limit / actual` when `limit < actual`, else `1`. -/
def budgetFactor (limit : Option Nat) (actual : Nat) : NNRat :=
  match limit with
  | none => NNRat.one
  | some m =>
    if h : m < actual then
      ⟨m, actual, by omega⟩
    else
      NNRat.one

/-- Excess loop penalty factor: `max(0, 1 - excess * loopPenalty)`. -/
def loopPenaltyFactor (loops maxRepeats : Nat) (loopPenalty : NNRat) : NNRat :=
  let excess := loops - maxRepeats
  if excess = 0 then
    NNRat.one
  else
    let totalPen := NNRat.scaleNat excess loopPenalty
    if NNRat.leBool NNRat.one totalPen then
      NNRat.zero
    else
      ⟨totalPen.den - totalPen.num, totalPen.den, totalPen.denPos⟩

/-- Exact rational raw score for `tool_efficiency`: `min(1, stepFactor, callFactor, loopFactor)`. -/
def toolEfficiencyRawScore
    (maxSteps maxCalls : Option Nat)
    (actualSteps actualCalls loops maxRepeats : Nat)
    (loopPenalty : NNRat) : NNRat :=
  nnratMin
    (nnratMin NNRat.one (budgetFactor maxSteps actualSteps))
    (nnratMin (budgetFactor maxCalls actualCalls) (loopPenaltyFactor loops maxRepeats loopPenalty))

/-- Full evaluator for `tool_efficiency` (`agent.py#L339-L419`). -/
def evaluateToolEfficiency
    (defaultMaxSteps defaultMaxCalls : Option Nat)
    (defaultAllowRedundantFailures : Nat)
    (loopPenalty : NNRat)
    (errors : List String)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "tool_efficiency" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    let maxSteps := match criteria.maxSteps with | some v => some v | none => defaultMaxSteps
    let maxCalls := match criteria.maxToolCalls with | some v => some v | none => defaultMaxCalls
    let maxRepeats :=
      if criteria.allowRedundantFailures > 0 then criteria.allowRedundantFailures
      else defaultAllowRedundantFailures
    let actualSteps := if trace.isEmpty then calls.length else trace.length
    let actualCalls := calls.length
    let loops := countRedundantLoops calls
    let score := toolEfficiencyRawScore maxSteps maxCalls actualSteps actualCalls loops maxRepeats loopPenalty
    finalizeAgentMetric score threshold

/-! ## Metric 5: `policy_compliance` (`agent.py#L422-L488`) -/

/-- Returns `true` iff `call` violates any blocked-status, forbidden-tool, or forbidden-pattern rule. -/
def callHasPolicyViolation
    (forbiddenTools forbiddenPatterns : List String)
    (call : ToolCall) : Bool :=
  (call.status == .blocked) ||
  decide (call.nameLower ∈ forbiddenTools) ||
  forbiddenPatterns.any (fun pat => containsSubstr call.argBlobLower pat)

/-- Returns `true` iff a trace step carries `status = blocked`. -/
def traceStepHasPolicyViolation (step : TraceStep) : Bool :=
  step.status == some .blocked

/-- Returns `true` iff any call or trace step breaches policy constraints. -/
def hasAnyPolicyViolation
    (forbiddenTools forbiddenPatterns : List String)
    (calls : List ToolCall)
    (trace : List TraceStep) : Bool :=
  calls.any (callHasPolicyViolation forbiddenTools forbiddenPatterns) ||
  trace.any traceStepHasPolicyViolation

/-- Exact rational raw score for `policy_compliance`: `0` on any violation, else `1`. -/
def policyComplianceRawScore
    (forbiddenTools forbiddenPatterns : List String)
    (calls : List ToolCall)
    (trace : List TraceStep) : NNRat :=
  if hasAnyPolicyViolation forbiddenTools forbiddenPatterns calls trace then
    NNRat.zero
  else
    NNRat.one

/-- Full evaluator for `policy_compliance` (`agent.py#L422-L488`). -/
def evaluatePolicyCompliance
    (metricForbiddenTools metricForbiddenPatterns : List String)
    (errors : List String)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "policy_compliance" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    let allForbiddenTools := metricForbiddenTools ++ criteria.forbiddenTools
    let allPatterns := metricForbiddenPatterns ++ criteria.forbiddenArgPatterns
    finalizeAgentMetric (policyComplianceRawScore allForbiddenTools allPatterns calls trace) threshold

/-! ## Metric 6: `failure_recovery` (`agent.py#L491-L552`) -/

/-- Build chronological `(isFail, isOk)` recovery timeline (`agent.py#L505-L516`). -/
def buildRecoveryTimeline (calls : List ToolCall) (trace : List TraceStep) : List (Bool × Bool) :=
  let callEntries := calls.map (fun c => (c.status.isFailure, c.status == .success))
  let seenCallIds := calls.filterMap ToolCall.id
  let traceErrorSteps := trace.filter (fun s =>
    s.kind == .error &&
    match s.toolCallId with
    | none => true
    | some cid => !decide (cid ∈ seenCallIds))
  let traceEntries := traceErrorSteps.map (fun _ => (true, false))
  callEntries ++ traceEntries

/-- Count failure events (`isFail = true`) in a recovery timeline. -/
def countFailures (timeline : List (Bool × Bool)) : Nat :=
  (timeline.filter Prod.fst).length

/-- Count failure events followed strictly later by at least one `SUCCESS` event (`isOk = true`). -/
def countRecovered : List (Bool × Bool) → Nat
  | [] => 0
  | (isFail, _) :: rest =>
    (if isFail && rest.any Prod.snd then 1 else 0) + countRecovered rest

/-- Exact rational raw score for `failure_recovery`: `none` iff zero failures, else `recovered / failures`. -/
def failureRecoveryRawScore (timeline : List (Bool × Bool)) : Option NNRat :=
  match countFailures timeline with
  | 0 => none
  | n + 1 => some ⟨countRecovered timeline, n + 1, Nat.succ_pos n⟩

/-- Full evaluator for `failure_recovery` (`agent.py#L491-L552`). -/
def evaluateFailureRecovery
    (errors : List String)
    (topCalls : List ToolCall)
    (trace : List TraceStep)
    (criteria : AgentCriteria)
    (defaultThreshold : NNRat) : AgentMetricOutcome :=
  let threshold := resolveThreshold criteria "failure_recovery" defaultThreshold
  if !errors.isEmpty then
    { status := .inconclusive, score := none, threshold := threshold }
  else
    let calls := prepareAgentInputs topCalls trace
    let timeline := buildRecoveryTimeline calls trace
    match failureRecoveryRawScore timeline with
    | none => { status := .notApplicable, score := none, threshold := threshold }
    | some score => finalizeAgentMetric score threshold

end EvalForgeFormal.Agent
