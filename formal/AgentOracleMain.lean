import Lean.Data.Json
import EvalForgeFormal.Agent.Metrics

open Lean
open EvalForgeFormal.Retrieval
open EvalForgeFormal.Agent

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private def mkFrac (n d : Nat) (h : 0 < d) : NNRat := ⟨n, d, h⟩
private def mkPct (n : Nat) : NNRat := ⟨n, 100, by omega⟩

private structure SchemaEntry where
  constrainedExpIdx : Nat
  callIdx : Nat
  valid : Bool
  deriving DecidableEq, Repr

private def lookupSchemaOracle (entries : List SchemaEntry) : SchemaOracle :=
  fun eIdx cIdx =>
    match entries.find? (fun e => e.constrainedExpIdx == eIdx && e.callIdx == cIdx) with
    | some entry => entry.valid
    | none => false

private structure AgentCaseInput where
  caseId : String
  errors : List String := []
  expected : List ExpectedTool := []
  toolCalls : List ToolCall := []
  trace : List TraceStep := []
  criteria : AgentCriteria := {}
  schemaResults : List SchemaEntry := []
  defaultMaxSteps : Option Nat := none
  defaultMaxCalls : Option Nat := none
  defaultAllowRedundantFailures : Nat := 0
  loopPenalty : NNRat := mkPct 50
  metricForbiddenTools : List String := []
  metricForbiddenPatterns : List String := []
  toolSelectionThreshold : NNRat := mkPct 80
  argumentCorrectnessThreshold : NNRat := mkPct 80
  executionSequenceThreshold : NNRat := NNRat.one
  toolEfficiencyThreshold : NNRat := mkPct 70
  policyComplianceThreshold : NNRat := NNRat.one
  failureRecoveryThreshold : NNRat := mkPct 50

private structure ThresholdVectorInput where
  caseId : String
  criteria : AgentCriteria
  metricId : String
  defaultThreshold : NNRat

/-! ## JSON Serialization Helpers -/

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

private def optStatusToJson : Option ToolCallStatus → Json
  | some st => Json.str st.toCanonicalString
  | none => Json.null

private def kvListToJson (kvs : List (String × String)) : Json :=
  Json.arr (kvs.toArray.map fun (k, v) =>
    Json.mkObj [("key", Json.str k), ("value_json", Json.str v)])

private def optKvListToJson : Option (List (String × String)) → Json
  | some kvs => kvListToJson kvs
  | none => Json.null

private def expectedToolToJson (e : ExpectedTool) : Json :=
  Json.mkObj [
    ("argument_match_mode", Json.str e.argumentMatchMode.toCanonicalString),
    ("arguments", optKvListToJson e.arguments),
    ("has_schema", Json.bool e.hasSchema),
    ("name", Json.str e.name),
    ("optional", Json.bool e.optional),
    ("order", optNatToJson e.order)
  ]

private def toolCallToJson (c : ToolCall) : Json :=
  Json.mkObj [
    ("arg_blob_lower", Json.str c.argBlobLower),
    ("argument_parse_error", optStrToJson c.argumentParseError),
    ("arguments", kvListToJson c.arguments),
    ("canonical_sig", Json.str c.canonicalSig),
    ("has_error", Json.bool c.hasError),
    ("has_result", Json.bool c.hasResult),
    ("id", optStrToJson c.id),
    ("name", Json.str c.name),
    ("name_lower", Json.str c.nameLower),
    ("status", Json.str c.status.toCanonicalString)
  ]

private def traceStepToJson (s : TraceStep) : Json :=
  Json.mkObj [
    ("arg_blob_lower", Json.str s.argBlobLower),
    ("canonical_sig", Json.str s.canonicalSig),
    ("has_content", Json.bool s.hasContent),
    ("has_error", Json.bool s.hasError),
    ("kind", Json.str s.kind.toCanonicalString),
    ("name", optStrToJson s.name),
    ("name_lower", optStrToJson s.nameLower),
    ("status", optStatusToJson s.status),
    ("tool_call_id", optStrToJson s.toolCallId),
    ("tool_calls", Json.arr (s.toolCalls.toArray.map toolCallToJson))
  ]

private def criteriaToJson (cr : AgentCriteria) : Json :=
  Json.mkObj [
    ("allow_redundant_failures", Json.num cr.allowRedundantFailures),
    ("forbidden_arg_patterns", Json.arr (cr.forbiddenArgPatterns.toArray.map Json.str)),
    ("forbidden_tools", Json.arr (cr.forbiddenTools.toArray.map Json.str)),
    ("max_steps", optNatToJson cr.maxSteps),
    ("max_tool_calls", optNatToJson cr.maxToolCalls),
    ("metric_thresholds", Json.arr (cr.metricThresholds.toArray.map fun (k, v) =>
      Json.mkObj [("metric_id", Json.str k), ("threshold", nnratToJson v)])),
    ("pass_threshold", optNNRatToJson cr.passThreshold)
  ]

private def schemaEntryToJson (e : SchemaEntry) : Json :=
  Json.mkObj [
    ("call_idx", Json.num e.callIdx),
    ("constrained_exp_idx", Json.num e.constrainedExpIdx),
    ("valid", Json.bool e.valid)
  ]

private def outcomeToJson (out : AgentMetricOutcome) : Json :=
  Json.mkObj [
    ("score_exact", optNNRatToJson out.score),
    ("status", Json.str out.status.toCanonicalString),
    ("threshold_exact", nnratToJson out.threshold)
  ]

private def preparedCallSummaryToJson (c : ToolCall) : Json :=
  Json.mkObj [
    ("has_error", Json.bool c.hasError),
    ("has_result", Json.bool c.hasResult),
    ("id", optStrToJson c.id),
    ("name", Json.str c.name),
    ("status", Json.str c.status.toCanonicalString)
  ]

private def evalAgentCaseToJson (c : AgentCaseInput) : Json :=
  let prepared := prepareAgentInputs c.toolCalls c.trace
  let oracle := lookupSchemaOracle c.schemaResults
  Json.mkObj [
    ("argument_correctness_non_strict",
      outcomeToJson (evaluateArgumentCorrectness false c.errors c.expected c.toolCalls c.trace
        oracle c.criteria c.argumentCorrectnessThreshold)),
    ("argument_correctness_strict",
      outcomeToJson (evaluateArgumentCorrectness true c.errors c.expected c.toolCalls c.trace
        oracle c.criteria c.argumentCorrectnessThreshold)),
    ("execution_sequence_exact",
      outcomeToJson (evaluateExecutionSequence .exact c.errors c.expected c.toolCalls c.trace
        c.criteria c.executionSequenceThreshold)),
    ("execution_sequence_prefix",
      outcomeToJson (evaluateExecutionSequence .prefix c.errors c.expected c.toolCalls c.trace
        c.criteria c.executionSequenceThreshold)),
    ("execution_sequence_subsequence",
      outcomeToJson (evaluateExecutionSequence .subsequence c.errors c.expected c.toolCalls c.trace
        c.criteria c.executionSequenceThreshold)),
    ("failure_recovery",
      outcomeToJson (evaluateFailureRecovery c.errors c.toolCalls c.trace
        c.criteria c.failureRecoveryThreshold)),
    ("policy_compliance",
      outcomeToJson (evaluatePolicyCompliance c.metricForbiddenTools c.metricForbiddenPatterns
        c.errors c.toolCalls c.trace c.criteria c.policyComplianceThreshold)),
    ("prepared_calls", Json.arr (prepared.toArray.map preparedCallSummaryToJson)),
    ("tool_efficiency",
      outcomeToJson (evaluateToolEfficiency c.defaultMaxSteps c.defaultMaxCalls
        c.defaultAllowRedundantFailures c.loopPenalty c.errors c.toolCalls c.trace
        c.criteria c.toolEfficiencyThreshold)),
    ("tool_selection_exact_set",
      outcomeToJson (evaluateToolSelection .exactSet c.errors c.expected c.toolCalls c.trace
        c.criteria c.toolSelectionThreshold)),
    ("tool_selection_f1",
      outcomeToJson (evaluateToolSelection .f1 c.errors c.expected c.toolCalls c.trace
        c.criteria c.toolSelectionThreshold)),
    ("tool_selection_recall",
      outcomeToJson (evaluateToolSelection .recall c.errors c.expected c.toolCalls c.trace
        c.criteria c.toolSelectionThreshold))
  ]

private def agentCaseInputToJson (c : AgentCaseInput) : Json :=
  Json.mkObj [
    ("argument_correctness_threshold", nnratToJson c.argumentCorrectnessThreshold),
    ("case_id", Json.str c.caseId),
    ("criteria", criteriaToJson c.criteria),
    ("default_allow_redundant_failures", Json.num c.defaultAllowRedundantFailures),
    ("default_max_calls", optNatToJson c.defaultMaxCalls),
    ("default_max_steps", optNatToJson c.defaultMaxSteps),
    ("errors", Json.arr (c.errors.toArray.map Json.str)),
    ("execution_sequence_threshold", nnratToJson c.executionSequenceThreshold),
    ("expected_tools", Json.arr (c.expected.toArray.map expectedToolToJson)),
    ("failure_recovery_threshold", nnratToJson c.failureRecoveryThreshold),
    ("loop_penalty", nnratToJson c.loopPenalty),
    ("metric_forbidden_patterns", Json.arr (c.metricForbiddenPatterns.toArray.map Json.str)),
    ("metric_forbidden_tools", Json.arr (c.metricForbiddenTools.toArray.map Json.str)),
    ("policy_compliance_threshold", nnratToJson c.policyComplianceThreshold),
    ("schema_results", Json.arr (c.schemaResults.toArray.map schemaEntryToJson)),
    ("tool_calls", Json.arr (c.toolCalls.toArray.map toolCallToJson)),
    ("tool_efficiency_threshold", nnratToJson c.toolEfficiencyThreshold),
    ("tool_selection_threshold", nnratToJson c.toolSelectionThreshold),
    ("trace", Json.arr (c.trace.toArray.map traceStepToJson))
  ]

/-! ## Canonical Threshold & Agent Vectors -/

private def mkEmptySig (name : String) : String :=
  "{\"arguments\":{},\"name\":\"" ++ name ++ "\",\"raw\":null}"

private def emptyArgBlob : String :=
  "{\"arguments\":{},\"raw\":null}"

private def mkSimpleCall (name : String) (status : ToolCallStatus := .success)
    (cid : Option String := none) : ToolCall :=
  {
    id := cid
    name := name
    nameLower := name
    arguments := []
    canonicalSig := mkEmptySig name
    argBlobLower := emptyArgBlob
    status := status
    hasError := status.isFailure
  }

private def thresholdResolutionVectors : List ThresholdVectorInput :=
  [
    {
      caseId := "metric_threshold_override"
      criteria := {
        metricThresholds := [("tool_selection", mkPct 90)]
        passThreshold := some (mkPct 60)
      }
      metricId := "tool_selection"
      defaultThreshold := mkPct 80
    },
    {
      caseId := "pass_threshold_fallback"
      criteria := {
        metricThresholds := []
        passThreshold := some (mkPct 60)
      }
      metricId := "tool_selection"
      defaultThreshold := mkPct 80
    },
    {
      caseId := "default_threshold_fallback"
      criteria := {}
      metricId := "tool_selection"
      defaultThreshold := mkPct 80
    },
    {
      caseId := "unrelated_metric_override_falls_back_to_pass"
      criteria := {
        metricThresholds := [("policy_compliance", mkPct 95)]
        passThreshold := some (mkPct 65)
      }
      metricId := "tool_efficiency"
      defaultThreshold := mkPct 70
    }
  ]

private def canonicalAgentCases : List AgentCaseInput :=
  [
    -- 1. Upstream execution errors supersede NOT_APPLICABLE across all 6 metrics
    {
      caseId := "errors_inconclusive_all_six"
      errors := ["agent runtime timeout"]
      expected := []
      toolCalls := []
      trace := []
      criteria := { passThreshold := some (mkPct 75) }
    },
    -- 2. Empty expected_tools and clean empty trace
    {
      caseId := "empty_expected_clean_trace"
      expected := []
      toolCalls := []
      trace := []
    },
    -- 3. Perfect single tool call matching expected dict args
    {
      caseId := "perfect_single_call"
      expected := [{ name := "search", arguments := some [("q", "\"rag\"")] }]
      toolCalls := [{
        id := some "c1"
        name := "search"
        nameLower := "search"
        arguments := [("q", "\"rag\"")]
        canonicalSig := "{\"arguments\":{\"q\":\"rag\"},\"name\":\"search\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"q\":\"rag\"},\"raw\":null}"
      }]
    },
    -- 4. Optional expected tool invoked: non-penalizing across all tool_selection modes
    {
      caseId := "tool_selection_optional_non_penalizing"
      expected := [
        { name := "search", optional := false },
        { name := "audit_log", optional := true }
      ]
      toolCalls := [mkSimpleCall "search", mkSimpleCall "audit_log"]
    },
    -- 5. All-optional fallback (1 of 2 invoked: recall = 1/2 < f1 = 2/3, exact_set = 0)
    {
      caseId := "tool_selection_all_optional_fallback"
      expected := [
        { name := "search", optional := true },
        { name := "summarize", optional := true }
      ]
      toolCalls := [mkSimpleCall "search"]
    },
    -- 6. Duplicate calls + unexpected extra tool (tp=1, fp=1, |req|=2 -> recall=1/2, f1=1/2)
    {
      caseId := "tool_selection_extra_unexpected_and_dups"
      expected := [{ name := "search" }, { name := "fetch" }]
      toolCalls := [mkSimpleCall "search", mkSimpleCall "search", mkSimpleCall "unknown_tool"]
    },
    -- 7. Full recall with unexpected tool (tp=1, fp=1, |req|=1 -> prec=1/2 < f1=2/3 < recall=1)
    {
      caseId := "tool_selection_full_recall_with_extra"
      expected := [{ name := "search" }]
      toolCalls := [mkSimpleCall "search", mkSimpleCall "extra_tool"]
    },
    -- 8. Argument correctness partial subset (1/2) vs strict exact (0)
    {
      caseId := "argument_correctness_subset_vs_strict_partial"
      expected := [{
        name := "search"
        arguments := some [("limit", "10"), ("q", "\"rag\"")]
        argumentMatchMode := .subset
      }]
      toolCalls := [{
        name := "search"
        nameLower := "search"
        arguments := [("extra", "1"), ("limit", "5"), ("q", "\"rag\"")]
        canonicalSig := "{\"arguments\":{\"extra\":1,\"limit\":5,\"q\":\"rag\"},\"name\":\"search\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"extra\":1,\"limit\":5,\"q\":\"rag\"},\"raw\":null}"
      }]
    },
    -- 9. Empty expected arguments dict: subset -> 1, strict -> 0 when actual non-empty
    {
      caseId := "argument_correctness_empty_expected_dict"
      expected := [{
        name := "ping"
        arguments := some []
        argumentMatchMode := .subset
      }]
      toolCalls := [{
        name := "ping"
        nameLower := "ping"
        arguments := [("debug", "true")]
        canonicalSig := "{\"arguments\":{\"debug\":true},\"name\":\"ping\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"debug\":true},\"raw\":null}"
      }]
    },
    -- 10. Schema + dict blend: schema fails (0), dict matches (1) -> average 1/2
    {
      caseId := "argument_correctness_schema_and_dict_blend"
      expected := [{
        name := "search"
        arguments := some [("q", "\"rag\"")]
        hasSchema := true
      }]
      toolCalls := [{
        name := "search"
        nameLower := "search"
        arguments := [("q", "\"rag\"")]
        canonicalSig := "{\"arguments\":{\"q\":\"rag\"},\"name\":\"search\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"q\":\"rag\"},\"raw\":null}"
      }]
      schemaResults := [{ constrainedExpIdx := 0, callIdx := 0, valid := false }]
    },
    -- 11. argument_parse_error dominates schema and dict -> 0
    {
      caseId := "argument_correctness_parse_error_zero"
      expected := [{
        name := "search"
        arguments := some [("q", "\"rag\"")]
        hasSchema := true
      }]
      toolCalls := [{
        name := "search"
        nameLower := "search"
        arguments := [("q", "\"rag\"")]
        canonicalSig := "{\"arguments\":{\"q\":\"rag\"},\"name\":\"search\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"q\":\"rag\"},\"raw\":null}"
        argumentParseError := some "invalid JSON payload"
      }]
      schemaResults := [{ constrainedExpIdx := 0, callIdx := 0, valid := true }]
    },
    -- 12. Greedy one-to-one usage cap: two identical expectations, one call -> 1/2
    {
      caseId := "argument_correctness_greedy_one_to_one_cap"
      expected := [
        { name := "search", arguments := some [("q", "\"a\"")] },
        { name := "search", arguments := some [("q", "\"a\"")] }
      ]
      toolCalls := [{
        name := "search"
        nameLower := "search"
        arguments := [("q", "\"a\"")]
        canonicalSig := "{\"arguments\":{\"q\":\"a\"},\"name\":\"search\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"q\":\"a\"},\"raw\":null}"
      }]
    },
    -- 13. Execution sequence explicit ordering with interleaved helper (subseq=1, prefix=1/3, exact=0)
    {
      caseId := "execution_sequence_explicit_order_interleaved"
      expected := [
        { name := "step_b", order := some 1 },
        { name := "step_a", order := some 0 },
        { name := "step_c", order := none }
      ]
      toolCalls := [
        mkSimpleCall "step_a",
        mkSimpleCall "helper",
        mkSimpleCall "step_b",
        mkSimpleCall "step_c"
      ]
    },
    -- 14. Strict hierarchy witness exact (0) < prefix (1/3) < subsequence (2/3)
    {
      caseId := "execution_sequence_hierarchy_witness"
      expected := [{ name := "a" }, { name := "b" }, { name := "c" }]
      toolCalls := [mkSimpleCall "a", mkSimpleCall "c", mkSimpleCall "b"]
    },
    -- 15. Tool efficiency step and call budgets exceeded (min(1, 2/5, 3/4, 1) = 2/5)
    {
      caseId := "tool_efficiency_step_and_call_budgets"
      expected := [{ name := "search" }]
      toolCalls := [
        mkSimpleCall "search",
        mkSimpleCall "search",
        mkSimpleCall "search",
        mkSimpleCall "search"
      ]
      trace := [
        { kind := .userInput },
        { kind := .reasoning },
        { kind := .reasoning },
        { kind := .reasoning },
        { kind := .finalOutput }
      ]
      criteria := { maxSteps := some 2, maxToolCalls := some 3 }
    },
    -- 16. Redundant identical failing loop penalized (1 redundant repeat * 0.5 = 0.5) + recovered
    {
      caseId := "tool_efficiency_redundant_failing_loop"
      expected := [{ name := "search" }]
      toolCalls := [
        mkSimpleCall "search" .error,
        mkSimpleCall "search" .error,
        mkSimpleCall "search" .success
      ]
      defaultAllowRedundantFailures := 0
      loopPenalty := mkPct 50
    },
    -- 17. Single failing retry that recovers cleanly is immune to loop penalty (score=1)
    {
      caseId := "tool_efficiency_single_retry_immune"
      expected := [{ name := "search" }]
      toolCalls := [
        mkSimpleCall "search" .timeout,
        mkSimpleCall "search" .success
      ]
      defaultAllowRedundantFailures := 0
      loopPenalty := mkPct 50
    },
    -- 18. Policy compliance forbidden argument pattern violation -> 0
    {
      caseId := "policy_compliance_forbidden_arg_pattern"
      expected := [{ name := "run_cmd" }]
      toolCalls := [{
        name := "run_cmd"
        nameLower := "run_cmd"
        arguments := [("cmd", "\"echo rm -rf /tmp\"")]
        canonicalSig := "{\"arguments\":{\"cmd\":\"echo rm -rf /tmp\"},\"name\":\"run_cmd\",\"raw\":null}"
        argBlobLower := "{\"arguments\":{\"cmd\":\"echo rm -rf /tmp\"},\"raw\":null}"
      }]
      criteria := {
        forbiddenTools := ["shell"]
        forbiddenArgPatterns := ["rm -rf"]
      }
    },
    -- 19. Policy compliance blocked trace step violation -> 0
    {
      caseId := "policy_compliance_blocked_trace_step"
      expected := [{ name := "search" }]
      toolCalls := [mkSimpleCall "search" .success]
      trace := [{ kind := .reasoning, status := some .blocked }]
    },
    -- 20. Trace merging, ID dedup, TOOL_RESULT implicit ERROR enrichment, and trailing trace ERROR (recovery = 1/2)
    {
      caseId := "trace_enrichment_dedup_and_partial_recovery"
      expected := [{ name := "search" }, { name := "fetch" }, { name := "fallback" }]
      toolCalls := [mkSimpleCall "search" .success (some "c1")]
      trace := [
        {
          kind := .llmResponse
          toolCalls := [mkSimpleCall "search" .error (some "c1")]
        },
        {
          kind := .toolCall
          name := some "fetch"
          nameLower := some "fetch"
          toolCallId := some "c2"
          canonicalSig := mkEmptySig "fetch"
          argBlobLower := emptyArgBlob
        },
        {
          kind := .toolResult
          toolCallId := some "c2"
          hasError := true
          hasContent := true
        },
        {
          kind := .toolCall
          name := some "fallback"
          nameLower := some "fallback"
          toolCallId := some "c3"
          status := some .success
          canonicalSig := mkEmptySig "fallback"
          argBlobLower := emptyArgBlob
        },
        {
          kind := .error
          hasError := true
        }
      ]
      criteria := {
        metricThresholds := [("failure_recovery", mkPct 60)]
      }
    }
  ]

private def goldenDocumentJson : Json :=
  Json.mkObj [
    ("canonical_vectors", Json.arr (canonicalAgentCases.toArray.map fun c =>
      Json.mkObj [
        ("case_id", Json.str c.caseId),
        ("expected", evalAgentCaseToJson c),
        ("input", agentCaseInputToJson c)
      ])),
    ("lean_toolchain", Json.str leanToolchain),
    ("schema_version", Json.str schemaVersion),
    ("sequence_modes", Json.arr #[
      Json.str SequenceMode.subsequence.toCanonicalString,
      Json.str SequenceMode.prefix.toCanonicalString,
      Json.str SequenceMode.exact.toCanonicalString
    ]),
    ("threshold_resolution_vectors", Json.arr (thresholdResolutionVectors.toArray.map fun tv =>
      Json.mkObj [
        ("case_id", Json.str tv.caseId),
        ("criteria", criteriaToJson tv.criteria),
        ("default_threshold", nnratToJson tv.defaultThreshold),
        ("expected_threshold_exact",
          nnratToJson (resolveThreshold tv.criteria tv.metricId tv.defaultThreshold)),
        ("metric_id", Json.str tv.metricId)
      ])),
    ("tool_call_statuses", Json.arr #[
      Json.str ToolCallStatus.success.toCanonicalString,
      Json.str ToolCallStatus.error.toCanonicalString,
      Json.str ToolCallStatus.timeout.toCanonicalString,
      Json.str ToolCallStatus.blocked.toCanonicalString
    ]),
    ("tool_selection_modes", Json.arr #[
      Json.str ToolSelectionMode.f1.toCanonicalString,
      Json.str ToolSelectionMode.recall.toCanonicalString,
      Json.str ToolSelectionMode.exactSet.toCanonicalString
    ]),
    ("trace_step_kinds", Json.arr #[
      Json.str TraceStepKind.userInput.toCanonicalString,
      Json.str TraceStepKind.reasoning.toCanonicalString,
      Json.str TraceStepKind.llmResponse.toCanonicalString,
      Json.str TraceStepKind.toolCall.toCanonicalString,
      Json.str TraceStepKind.toolResult.toCanonicalString,
      Json.str TraceStepKind.error.toCanonicalString,
      Json.str TraceStepKind.finalOutput.toCanonicalString,
      Json.str TraceStepKind.other.toCanonicalString
    ])
  ]

/-! ## Fail-Closed JSON Parsers (`eval-stdin`) -/

private def parseNatField (obj : Json) (field : String) : Except String Nat := do
  let val ← obj.getObjVal? field
  val.getNat?

private def parseOptNatField (obj : Json) (field : String) : Except String (Option Nat) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> val.getNat?

private def parseOptPosNatField (obj : Json) (field : String) : Except String (Option Nat) := do
  match ← parseOptNatField obj field with
  | none => pure none
  | some n =>
    if n ≥ 1 then pure (some n)
    else throw s!"{field} must be >= 1 when set, got {n}"

private def parseOptStrField (obj : Json) (field : String) : Except String (Option String) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> val.getStr?

private def parseStrList (j : Json) : Except String (List String) := do
  let arr ← j.getArr?
  arr.toList.mapM Json.getStr?

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

private def parseToolCallStatus (s : String) : Except String ToolCallStatus :=
  match s with
  | "success" => pure .success
  | "error" => pure .error
  | "timeout" => pure .timeout
  | "blocked" => pure .blocked
  | other => throw s!"Unsupported ToolCallStatus: '{other}'"

private def parseOptToolCallStatus (obj : Json) (field : String) : Except String (Option ToolCallStatus) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else
    let s ← val.getStr?
    some <$> parseToolCallStatus s

private def parseTraceStepKind (s : String) : Except String TraceStepKind :=
  match s with
  | "user_input" => pure .userInput
  | "reasoning" => pure .reasoning
  | "llm_response" => pure .llmResponse
  | "tool_call" => pure .toolCall
  | "tool_result" => pure .toolResult
  | "error" => pure .error
  | "final_output" => pure .finalOutput
  | "other" => pure .other
  | other => throw s!"Unsupported TraceStepKind: '{other}'"

private def parseArgumentMatchMode (s : String) : Except String ArgumentMatchMode :=
  match s with
  | "subset" => pure .subset
  | "exact" => pure .exact
  | other => throw s!"Unsupported argument_match_mode: '{other}'"

private def parseKvList (j : Json) : Except String (List (String × String)) := do
  let arr ← j.getArr?
  arr.toList.mapM fun item => do
    let k ← (← item.getObjVal? "key").getStr?
    let v ← (← item.getObjVal? "value_json").getStr?
    pure (k, v)

private def parseOptKvList (obj : Json) (field : String) : Except String (Option (List (String × String))) := do
  let val ← obj.getObjVal? field
  if val.isNull then pure none
  else some <$> parseKvList val

private def parseExpectedTool (j : Json) : Except String ExpectedTool := do
  let name ← (← j.getObjVal? "name").getStr?
  if name.isEmpty then throw "ExpectedTool.name must be non-empty"
  let args ← parseOptKvList j "arguments"
  let hasSchema ← (← j.getObjVal? "has_schema").getBool?
  let modeStr ← (← j.getObjVal? "argument_match_mode").getStr?
  let mode ← parseArgumentMatchMode modeStr
  let opt ← (← j.getObjVal? "optional").getBool?
  let ord ← parseOptNatField j "order"
  pure {
    name := name
    arguments := args
    hasSchema := hasSchema
    argumentMatchMode := mode
    optional := opt
    order := ord
  }

private def parseToolCall (j : Json) : Except String ToolCall := do
  let cid ← parseOptStrField j "id"
  let name ← (← j.getObjVal? "name").getStr?
  if name.isEmpty then throw "ToolCall.name must be non-empty"
  let nameLower ← (← j.getObjVal? "name_lower").getStr?
  let args ← parseKvList (← j.getObjVal? "arguments")
  let canonicalSig ← (← j.getObjVal? "canonical_sig").getStr?
  let argBlobLower ← (← j.getObjVal? "arg_blob_lower").getStr?
  let parseErr ← parseOptStrField j "argument_parse_error"
  let statusStr ← (← j.getObjVal? "status").getStr?
  let status ← parseToolCallStatus statusStr
  let hasError ← (← j.getObjVal? "has_error").getBool?
  let hasResult ← (← j.getObjVal? "has_result").getBool?
  pure {
    id := cid
    name := name
    nameLower := nameLower
    arguments := args
    canonicalSig := canonicalSig
    argBlobLower := argBlobLower
    argumentParseError := parseErr
    status := status
    hasError := hasError
    hasResult := hasResult
  }

private def parseTraceStep (j : Json) : Except String TraceStep := do
  let kindStr ← (← j.getObjVal? "kind").getStr?
  let kind ← parseTraceStepKind kindStr
  let name ← parseOptStrField j "name"
  let nameLower ← parseOptStrField j "name_lower"
  let callsArr ← (← j.getObjVal? "tool_calls").getArr?
  let toolCalls ← callsArr.toList.mapM parseToolCall
  let toolCallId ← parseOptStrField j "tool_call_id"
  let status ← parseOptToolCallStatus j "status"
  let hasError ← (← j.getObjVal? "has_error").getBool?
  let hasContent ← (← j.getObjVal? "has_content").getBool?
  let canonicalSig ← (← j.getObjVal? "canonical_sig").getStr?
  let argBlobLower ← (← j.getObjVal? "arg_blob_lower").getStr?
  pure {
    kind := kind
    name := name
    nameLower := nameLower
    toolCalls := toolCalls
    toolCallId := toolCallId
    status := status
    hasError := hasError
    hasContent := hasContent
    canonicalSig := canonicalSig
    argBlobLower := argBlobLower
  }

private def parseCriteria (j : Json) : Except String AgentCriteria := do
  let mtArr ← (← j.getObjVal? "metric_thresholds").getArr?
  let mt ← mtArr.toList.mapM fun item => do
    let mid ← (← item.getObjVal? "metric_id").getStr?
    let thr ← parseUnitNNRat (← item.getObjVal? "threshold") s!"metric_thresholds.{mid}"
    pure (mid, thr)
  let passThr ← parseOptUnitNNRat j "pass_threshold"
  let forbTools ← parseStrList (← j.getObjVal? "forbidden_tools")
  let forbPats ← parseStrList (← j.getObjVal? "forbidden_arg_patterns")
  let maxSteps ← parseOptPosNatField j "max_steps"
  let maxCalls ← parseOptPosNatField j "max_tool_calls"
  let allowRep ← parseNatField j "allow_redundant_failures"
  pure {
    metricThresholds := mt
    passThreshold := passThr
    forbiddenTools := forbTools
    forbiddenArgPatterns := forbPats
    maxSteps := maxSteps
    maxToolCalls := maxCalls
    allowRedundantFailures := allowRep
  }

private def parseSchemaEntry (j : Json) : Except String SchemaEntry := do
  let eIdx ← parseNatField j "constrained_exp_idx"
  let cIdx ← parseNatField j "call_idx"
  let valid ← (← j.getObjVal? "valid").getBool?
  pure { constrainedExpIdx := eIdx, callIdx := cIdx, valid := valid }

private def handleAgentCase (j : Json) : Except String Json := do
  let cid ← (← j.getObjVal? "case_id").getStr?
  let errors ← parseStrList (← j.getObjVal? "errors")
  let expArr ← (← j.getObjVal? "expected_tools").getArr?
  let expected ← expArr.toList.mapM parseExpectedTool
  let callsArr ← (← j.getObjVal? "tool_calls").getArr?
  let calls ← callsArr.toList.mapM parseToolCall
  let traceArr ← (← j.getObjVal? "trace").getArr?
  let trace ← traceArr.toList.mapM parseTraceStep
  let criteria ← parseCriteria (← j.getObjVal? "criteria")
  let schemaArr ← (← j.getObjVal? "schema_results").getArr?
  let schemaResults ← schemaArr.toList.mapM parseSchemaEntry
  let defMaxSteps ← parseOptPosNatField j "default_max_steps"
  let defMaxCalls ← parseOptPosNatField j "default_max_calls"
  let defAllowRep ← parseNatField j "default_allow_redundant_failures"
  let loopPen ← parsePosUnitNNRat (← j.getObjVal? "loop_penalty") "loop_penalty"
  let mForbTools ← parseStrList (← j.getObjVal? "metric_forbidden_tools")
  let mForbPats ← parseStrList (← j.getObjVal? "metric_forbidden_patterns")
  let tSel ← parseUnitNNRat (← j.getObjVal? "tool_selection_threshold") "tool_selection_threshold"
  let tArg ← parseUnitNNRat (← j.getObjVal? "argument_correctness_threshold") "argument_correctness_threshold"
  let tSeq ← parseUnitNNRat (← j.getObjVal? "execution_sequence_threshold") "execution_sequence_threshold"
  let tEff ← parseUnitNNRat (← j.getObjVal? "tool_efficiency_threshold") "tool_efficiency_threshold"
  let tPol ← parseUnitNNRat (← j.getObjVal? "policy_compliance_threshold") "policy_compliance_threshold"
  let tRec ← parseUnitNNRat (← j.getObjVal? "failure_recovery_threshold") "failure_recovery_threshold"
  let req : AgentCaseInput := {
    caseId := cid
    errors := errors
    expected := expected
    toolCalls := calls
    trace := trace
    criteria := criteria
    schemaResults := schemaResults
    defaultMaxSteps := defMaxSteps
    defaultMaxCalls := defMaxCalls
    defaultAllowRedundantFailures := defAllowRep
    loopPenalty := loopPen
    metricForbiddenTools := mForbTools
    metricForbiddenPatterns := mForbPats
    toolSelectionThreshold := tSel
    argumentCorrectnessThreshold := tArg
    executionSequenceThreshold := tSeq
    toolEfficiencyThreshold := tEff
    policyComplianceThreshold := tPol
    failureRecoveryThreshold := tRec
  }
  pure (evalAgentCaseToJson req)

private def handleResolveThreshold (j : Json) : Except String Json := do
  let criteria ← parseCriteria (← j.getObjVal? "criteria")
  let metricId ← (← j.getObjVal? "metric_id").getStr?
  let defThr ← parseUnitNNRat (← j.getObjVal? "default_threshold") "default_threshold"
  let resolved := resolveThreshold criteria metricId defThr
  pure (Json.mkObj [("threshold_exact", nnratToJson resolved)])

private def evalStdinRequest (raw : String) : Except String Json := do
  let j ← Json.parse raw
  let kind ← (← j.getObjVal? "kind").getStr?
  match kind with
  | "agent_case" => handleAgentCase j
  | "resolve_threshold" => handleResolveThreshold j
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
      IO.eprintln s!"evalforge-agent-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-agent-oracle <export-golden|eval-stdin>"
    return 1
