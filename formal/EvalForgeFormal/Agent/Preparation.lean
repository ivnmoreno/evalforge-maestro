import EvalForgeFormal.Agent.Types
import EvalForgeFormal.Retrieval.Preparation

namespace EvalForgeFormal.Agent

open EvalForgeFormal.Retrieval (NNRat enumFrom dedupPreserveFirst)

/-! ## Rational Min/Max Helpers -/

/-- Minimum of two non-negative exact rationals. -/
def nnratMin (a b : NNRat) : NNRat :=
  if NNRat.leBool a b then a else b

/-- Maximum of two non-negative exact rationals. -/
def nnratMax (a b : NNRat) : NNRat :=
  if NNRat.leBool a b then b else a

/-! ## Shared Threshold Precedence & Outcome Finalization (`deterministic.py`) -/

/-- Lookup a per-metric threshold override in `criteria.metricThresholds`. -/
def lookupMetricThreshold : List (String × NNRat) → String → Option NNRat
  | [], _ => none
  | (k, v) :: rest, metricId =>
    if k = metricId then some v else lookupMetricThreshold rest metricId

/--
Formal model of `_resolve_threshold` (`deterministic.py`):
enforces strict 3-tier precedence `metric_thresholds[metric_id] > pass_threshold > default_threshold`.
-/
def resolveThreshold
    (criteria : AgentCriteria)
    (metricId : String)
    (defaultThreshold : NNRat) : NNRat :=
  match lookupMetricThreshold criteria.metricThresholds metricId with
  | some v => v
  | none =>
    match criteria.passThreshold with
    | some p => p
    | none => defaultThreshold

/-- Finalize a numeric score in `[0, 1]` against its resolved threshold (`PASS` iff `threshold ≤ score`). -/
def finalizeAgentMetric (score threshold : NNRat) : AgentMetricOutcome :=
  if NNRat.leBool threshold score then
    { status := .pass, score := some score, threshold := threshold }
  else
    { status := .fail, score := some score, threshold := threshold }

/-! ## Agent Trace Preparation & Enrichment (`_prepare_agent_inputs`, `agent.py#L31-L82`) -/

/-- Upsert a `TOOL_RESULT` step by `tool_call_id` (last matching step wins, mirroring Python dict). -/
def upsertToolResult (m : List (String × TraceStep)) (cid : String) (step : TraceStep) :
    List (String × TraceStep) :=
  match m with
  | [] => [(cid, step)]
  | (k, v) :: rest =>
    if k = cid then (k, step) :: rest else (k, v) :: upsertToolResult rest cid step

/-- Lookup the last `TOOL_RESULT` trace step recorded for a given `tool_call_id`. -/
def lookupToolResult : List (String × TraceStep) → String → Option TraceStep
  | [], _ => none
  | (k, v) :: rest, cid =>
    if k = cid then some v else lookupToolResult rest cid

/-- Collect `tool_results` map from `execution.trace` (`agent.py#L40-L43`). -/
def collectToolResults (trace : List TraceStep) : List (String × TraceStep) :=
  trace.foldl (fun acc step =>
    match step.kind, step.toolCallId with
    | .toolResult, some cid => upsertToolResult acc cid step
    | _, _ => acc
  ) []

/-- Append a tool call unless its non-`none` ID has already been recorded in `seen`. -/
def appendUniqueCall (calls : List ToolCall) (seen : List String) (c : ToolCall) :
    List ToolCall × List String :=
  match c.id with
  | none => (calls ++ [c], seen)
  | some cid =>
    if cid ∈ seen then (calls, seen)
    else (calls ++ [c], cid :: seen)

/-- Synthesize a `ToolCall` from a standalone `TOOL_CALL` trace step (`agent.py#L53-L61`). -/
def synthesizeStepToolCall (step : TraceStep) (nm : String) : ToolCall :=
  {
    id := step.toolCallId
    name := nm
    nameLower := step.nameLower.getD ""
    arguments := []
    canonicalSig := step.canonicalSig
    argBlobLower := step.argBlobLower
    argumentParseError := none
    status := step.status.getD .success
    hasError := step.hasError
    hasResult := false
  }

/-- Merge one trace step's nested `tool_calls` or standalone `TOOL_CALL` into `(calls, seen)`. -/
def mergeTraceStep (state : List ToolCall × List String) (step : TraceStep) :
    List ToolCall × List String :=
  if !step.toolCalls.isEmpty then
    step.toolCalls.foldl (fun st nested => appendUniqueCall st.1 st.2 nested) state
  else
    match step.kind, step.name with
    | .toolCall, some nm =>
      appendUniqueCall state.1 state.2 (synthesizeStepToolCall step nm)
    | _, _ => state

/-- Collect merged raw tool calls prior to `TOOL_RESULT` enrichment (`agent.py#L37-L63`). -/
def collectRawCalls (topCalls : List ToolCall) (trace : List TraceStep) : List ToolCall :=
  let initSeen := topCalls.filterMap ToolCall.id
  (trace.foldl mergeTraceStep (topCalls, initSeen)).1

/-- Enrich a single `ToolCall` using its matching `TOOL_RESULT` trace step (`agent.py#L65-L80`). -/
def enrichToolCall (results : List (String × TraceStep)) (call : ToolCall) : ToolCall :=
  match call.id with
  | none => call
  | some cid =>
    match lookupToolResult results cid with
    | none => call
    | some resStep =>
      let status1 :=
        match resStep.status with
        | some st => st
        | none => call.status
      let hasError1 := if resStep.hasError && !call.hasError then true else call.hasError
      let status2 :=
        if resStep.hasError && !call.hasError && resStep.status.isNone then
          ToolCallStatus.error
        else
          status1
      let hasResult1 := if resStep.hasContent && !call.hasResult then true else call.hasResult
      { call with status := status2, hasError := hasError1, hasResult := hasResult1 }

/--
Formal model of `_prepare_agent_inputs` (`agent.py#L31-L82`): merges top-level `tool_calls`,
nested trace `tool_calls`, and standalone `TOOL_CALL` steps with first-seen ID deduplication,
then enriches records from matching `TOOL_RESULT` steps.
-/
def prepareAgentInputs (topCalls : List ToolCall) (trace : List TraceStep) : List ToolCall :=
  let rawCalls := collectRawCalls topCalls trace
  let results := collectToolResults trace
  rawCalls.map (enrichToolCall results)

/-! ## Expected Tool Ordering (`_ordered_expected_tools`, `agent.py#L85-L97`) -/

/-- Sort key `(item.order ?? len(expected), idx)` mirroring `agent.py#L91-L94`. -/
def expectedSortKey (n : Nat) (p : Nat × ExpectedTool) : Nat × Nat :=
  (p.2.order.getD n, p.1)

/-- Total lexicographic `≤` comparator on `(item.order ?? n, idx)`. -/
def expectedSortKeyLe (n : Nat) (a b : Nat × ExpectedTool) : Bool :=
  let (o1, i1) := expectedSortKey n a
  let (o2, i2) := expectedSortKey n b
  decide (o1 < o2 ∨ (o1 = o2 ∧ i1 ≤ i2))

/-- Indexed stable sort of `expected` mirroring `_ordered_expected_tools`. -/
def orderedExpectedToolsIndexed (expected : List ExpectedTool) : List (Nat × ExpectedTool) :=
  if expected.any (fun item => item.order.isSome) then
    (enumFrom 0 expected).mergeSort (expectedSortKeyLe expected.length)
  else
    enumFrom 0 expected

/-- Formal model of `_ordered_expected_tools` (`agent.py#L85-L97`). -/
def orderedExpectedTools (expected : List ExpectedTool) : List ExpectedTool :=
  (orderedExpectedToolsIndexed expected).map Prod.snd

/-! ## Pure Substring & Argument-Map Helpers -/

/-- Pure list-prefix check over character lists. -/
def hasPrefixList : List Char → List Char → Bool
  | _, [] => true
  | [], _ :: _ => false
  | h :: hs, n :: ns => (h == n) && hasPrefixList hs ns

/-- Pure contiguous sublist check over character lists. -/
def containsSublist : List Char → List Char → Bool
  | [], needle => needle.isEmpty
  | h :: hs, needle => hasPrefixList (h :: hs) needle || containsSublist hs needle

/-- Pure deterministic substring match mirroring Python `needle in haystack`. -/
def containsSubstr (haystack needle : String) : Bool :=
  containsSublist haystack.toList needle.toList

/-- Returns `true` iff `(k, v)` appears in `callArgs`. -/
def argEntryMatches (callArgs : List (String × String)) (kv : String × String) : Bool :=
  callArgs.any (fun p => p.1 == kv.1 && p.2 == kv.2)

/-- Returns `true` iff every `(k, v)` in `expArgs` appears in `callArgs`. -/
def argMapSubset (expArgs callArgs : List (String × String)) : Bool :=
  expArgs.all (argEntryMatches callArgs)

/-- Order-independent exact equality of canonical argument key-value lists. -/
def argMapsEqual (callArgs expArgs : List (String × String)) : Bool :=
  argMapSubset expArgs callArgs && argMapSubset callArgs expArgs

/-- Count how many expected `(k, v)` entries match in `callArgs`. -/
def countMatchedKeys (expArgs callArgs : List (String × String)) : Nat :=
  (expArgs.filter (argEntryMatches callArgs)).length

end EvalForgeFormal.Agent
