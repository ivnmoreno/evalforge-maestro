import EvalForgeFormal.Retrieval.ExactRat

namespace EvalForgeFormal.Agent

open EvalForgeFormal.Retrieval (NNRat)

/--
Execution status of a tool call, mirroring `evalforge_maestro.types.ToolCallStatus`.
-/
inductive ToolCallStatus where
  | success
  | error
  | timeout
  | blocked
  deriving DecidableEq, Repr

namespace ToolCallStatus

/-- Returns `true` iff status is in `_TOOL_FAILURE_STATUSES = {ERROR, TIMEOUT}`. -/
def isFailure : ToolCallStatus → Bool
  | .error | .timeout => true
  | .success | .blocked => false

/-- Canonical serialized string matching `ToolCallStatus.value`. -/
def toCanonicalString : ToolCallStatus → String
  | .success => "success"
  | .error => "error"
  | .timeout => "timeout"
  | .blocked => "blocked"

end ToolCallStatus

/--
Step kind in an agent trace, mirroring `evalforge_maestro.types.TraceStepKind`.
-/
inductive TraceStepKind where
  | userInput
  | reasoning
  | llmResponse
  | toolCall
  | toolResult
  | error
  | finalOutput
  | other
  deriving DecidableEq, Repr

namespace TraceStepKind

/-- Canonical serialized string matching `TraceStepKind.value`. -/
def toCanonicalString : TraceStepKind → String
  | .userInput => "user_input"
  | .reasoning => "reasoning"
  | .llmResponse => "llm_response"
  | .toolCall => "tool_call"
  | .toolResult => "tool_result"
  | .error => "error"
  | .finalOutput => "final_output"
  | .other => "other"

end TraceStepKind

/--
Metric evaluation status for deterministic agent metrics, mirroring `MetricStatus`.
-/
inductive AgentMetricStatus where
  | pass
  | fail
  | inconclusive
  | notApplicable
  deriving DecidableEq, Repr

namespace AgentMetricStatus

/-- Canonical serialized string matching `MetricStatus.value`. -/
def toCanonicalString : AgentMetricStatus → String
  | .pass => "PASS"
  | .fail => "FAIL"
  | .inconclusive => "INCONCLUSIVE"
  | .notApplicable => "NOT_APPLICABLE"

end AgentMetricStatus

/-- Argument matching mode on `ExpectedTool`, mirroring `ExpectedToolCall.argument_match_mode`. -/
inductive ArgumentMatchMode where
  | subset
  | exact
  deriving DecidableEq, Repr

namespace ArgumentMatchMode

def toCanonicalString : ArgumentMatchMode → String
  | .subset => "subset"
  | .exact => "exact"

end ArgumentMatchMode

/-- Scoring mode for `ToolSelectionMetric`. -/
inductive ToolSelectionMode where
  | f1
  | recall
  | exactSet
  deriving DecidableEq, Repr

namespace ToolSelectionMode

def toCanonicalString : ToolSelectionMode → String
  | .f1 => "f1"
  | .recall => "recall"
  | .exactSet => "exact_set"

end ToolSelectionMode

/-- Scoring mode for `ExecutionSequenceMetric`. -/
inductive SequenceMode where
  | subsequence
  | prefix
  | exact
  deriving DecidableEq, Repr

namespace SequenceMode

def toCanonicalString : SequenceMode → String
  | .subsequence => "subsequence"
  | .prefix => "prefix"
  | .exact => "exact"

end SequenceMode

/--
Formal representation of `evalforge_maestro.types.ExpectedToolCall`.
`arguments` stores canonical `(key, canonicalJsonValueString)` pairs with unique keys.
-/
structure ExpectedTool where
  name : String
  arguments : Option (List (String × String)) := none
  hasSchema : Bool := false
  argumentMatchMode : ArgumentMatchMode := .subset
  optional : Bool := false
  order : Option Nat := none
  deriving DecidableEq, Repr

/--
Formal representation of `evalforge_maestro.types.ToolCallRecord` with pre-normalized boundary
fields (`nameLower`, `canonicalSig`, `argBlobLower`) provided by the Python caller/oracle.
-/
structure ToolCall where
  id : Option String := none
  name : String
  nameLower : String := ""
  arguments : List (String × String) := []
  canonicalSig : String := ""
  argBlobLower : String := ""
  argumentParseError : Option String := none
  status : ToolCallStatus := .success
  hasError : Bool := false
  hasResult : Bool := false
  deriving DecidableEq, Repr

/--
Formal representation of `evalforge_maestro.types.AgentTraceStep`.
-/
structure TraceStep where
  kind : TraceStepKind
  name : Option String := none
  nameLower : Option String := none
  toolCalls : List ToolCall := []
  toolCallId : Option String := none
  status : Option ToolCallStatus := none
  hasError : Bool := false
  hasContent : Bool := false
  canonicalSig : String := ""
  argBlobLower : String := ""
  deriving DecidableEq, Repr

/--
Formal representation of agent-relevant fields in `evalforge_maestro.types.CaseCriteria`.
Policy lists (`forbiddenTools`, `forbiddenArgPatterns`) carry pre-casefolded entries.
-/
structure AgentCriteria where
  metricThresholds : List (String × NNRat) := []
  passThreshold : Option NNRat := none
  forbiddenTools : List String := []
  forbiddenArgPatterns : List String := []
  maxSteps : Option Nat := none
  maxToolCalls : Option Nat := none
  allowRedundantFailures : Nat := 0
  deriving DecidableEq, Repr

/--
Abstract JSON Schema validation oracle mapping `(constrainedExpIdx, callIdx)` to pre-evaluated
schema validity, decoupling Lean proofs from `jsonschema` Draft validator internals.
-/
abbrev SchemaOracle := Nat → Nat → Bool

/--
Uniform formal outcome contract across all six deterministic agent metrics.
-/
structure AgentMetricOutcome where
  status : AgentMetricStatus
  score : Option NNRat
  threshold : NNRat
  deriving DecidableEq, Repr

end EvalForgeFormal.Agent
