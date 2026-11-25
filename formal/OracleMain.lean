import Lean.Data.Json
import EvalForgeFormal.QualityGate.Aggregation

open Lean
open EvalForgeFormal.QualityGate

private def schemaVersion : String := "1.0"
private def leanToolchain : String := "leanprover/lean4:v4.36.0"

private def boolToReasonList (present : Bool) (label : String) : List String :=
  if present then [label] else []

private def mkTruthTableEntry (hasFailures hasInconclusive hasWarnings : Bool) : Json :=
  let state : ReasonState := {
    failureReasons := boolToReasonList hasFailures "synthetic_failure"
    inconclusiveReasons := boolToReasonList hasInconclusive "synthetic_inconclusive"
    warningReasons := boolToReasonList hasWarnings "synthetic_warning"
  }
  let outcome := evaluateReasonState state
  Json.mkObj [
    ("blocking", Json.bool outcome.blocking),
    ("decision", Json.str outcome.decision.toCanonicalString),
    ("has_failures", Json.bool hasFailures),
    ("has_inconclusive", Json.bool hasInconclusive),
    ("has_warnings", Json.bool hasWarnings),
    ("passed", Json.bool outcome.passed)
  ]

private def ruleCheckToJson (c : RuleCheck) : Json :=
  Json.mkObj [
    ("message", Json.str c.message),
    ("status", Json.str c.status.toCanonicalString)
  ]

private def mkRuleCheckVector (vectorId : String) (checks : List RuleCheck) : Json :=
  let recorded := recordChecks checks
  let outcome := evaluateChecks checks
  Json.mkObj [
    ("blocking", Json.bool outcome.blocking),
    ("checks", Json.arr (checks.toArray.map ruleCheckToJson)),
    ("decision", Json.str outcome.decision.toCanonicalString),
    ("expected_failure_count", Json.num recorded.failureReasons.length),
    ("expected_inconclusive_count", Json.num recorded.inconclusiveReasons.length),
    ("expected_warning_count", Json.num recorded.warningReasons.length),
    ("passed", Json.bool outcome.passed),
    ("vector_id", Json.str vectorId)
  ]

private def canonicalRuleCheckVectors : List (String × List RuleCheck) := [
  ("empty", []),
  ("single_pass", [
    { status := .pass, message := "mandatory_cases ok" }
  ]),
  ("single_warning", [
    { status := .pass, message := "mandatory_cases ok" },
    { status := .warning, message := "soft regression" }
  ]),
  ("single_inconclusive", [
    { status := .pass, message := "mandatory_cases ok" },
    { status := .inconclusive, message := "missing baseline" }
  ]),
  ("single_fail", [
    { status := .fail, message := "mandatory case failed" }
  ]),
  ("warning_then_inconclusive", [
    { status := .warning, message := "provenance drift" },
    { status := .inconclusive, message := "inconclusive rate exceeded" }
  ]),
  ("inconclusive_then_warning_perm", [
    { status := .inconclusive, message := "inconclusive rate exceeded" },
    { status := .warning, message := "provenance drift" }
  ]),
  ("warning_inconclusive_fail", [
    { status := .warning, message := "anomaly warning" },
    { status := .inconclusive, message := "missing trend" },
    { status := .fail, message := "metric floor breached" }
  ]),
  ("fail_pass_warning_inconclusive_perm", [
    { status := .fail, message := "metric floor breached" },
    { status := .pass, message := "other rule passed" },
    { status := .warning, message := "anomaly warning" },
    { status := .inconclusive, message := "missing trend" }
  ]),
  ("multi_fail_with_pass_and_warnings", [
    { status := .pass, message := "clean check" },
    { status := .fail, message := "mandatory failure" },
    { status := .warning, message := "drift warning 1" },
    { status := .fail, message := "floor breach" },
    { status := .warning, message := "drift warning 2" }
  ])
]

private def buildGoldenJson : Json :=
  let truthEntries : List Json := [
    mkTruthTableEntry false false false,
    mkTruthTableEntry false false true,
    mkTruthTableEntry false true false,
    mkTruthTableEntry false true true,
    mkTruthTableEntry true false false,
    mkTruthTableEntry true false true,
    mkTruthTableEntry true true false,
    mkTruthTableEntry true true true
  ]
  let vectors : List Json :=
    canonicalRuleCheckVectors.map fun (vid, checks) => mkRuleCheckVector vid checks
  Json.mkObj [
    ("lean_toolchain", Json.str leanToolchain),
    ("precedence_order", Json.arr #[
      Json.str GateDecision.fail.toCanonicalString,
      Json.str GateDecision.inconclusive.toCanonicalString,
      Json.str GateDecision.warning.toCanonicalString,
      Json.str GateDecision.pass.toCanonicalString
    ]),
    ("reason_presence_truth_table", Json.arr truthEntries.toArray),
    ("rule_check_vectors", Json.arr vectors.toArray),
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

private def parseRuleCheck (j : Json) : Except String RuleCheck := do
  let statusStr ← (← j.getObjVal? "status").getStr?
  let msg ← (← j.getObjVal? "message").getStr?
  match GateDecision.ofCanonicalString? statusStr with
  | some st => return { status := st, message := msg }
  | none => throw s!"Invalid GateDecision status string: {statusStr}"

private def evalReasonCase (j : Json) : Except String Json := do
  let caseId ← (← j.getObjVal? "case_id").getStr?
  let failures ← parseStringList j "failure_reasons"
  let inconclusives ← parseStringList j "inconclusive_reasons"
  let warnings ← parseStringList j "warning_reasons"
  let outcome := evaluateReasonState {
    failureReasons := failures
    inconclusiveReasons := inconclusives
    warningReasons := warnings
  }
  return Json.mkObj [
    ("blocking", Json.bool outcome.blocking),
    ("case_id", Json.str caseId),
    ("decision", Json.str outcome.decision.toCanonicalString),
    ("passed", Json.bool outcome.passed)
  ]

private def evalCheckCase (j : Json) : Except String Json := do
  let caseId ← (← j.getObjVal? "case_id").getStr?
  let checksArr ← (← j.getObjVal? "checks").getArr?
  let mut checks : List RuleCheck := []
  for elem in checksArr do
    let c ← parseRuleCheck elem
    checks := checks ++ [c]
  let recorded := recordChecks checks
  let outcome := evaluateChecks checks
  return Json.mkObj [
    ("blocking", Json.bool outcome.blocking),
    ("case_id", Json.str caseId),
    ("decision", Json.str outcome.decision.toCanonicalString),
    ("failure_count", Json.num recorded.failureReasons.length),
    ("inconclusive_count", Json.num recorded.inconclusiveReasons.length),
    ("passed", Json.bool outcome.passed),
    ("warning_count", Json.num recorded.warningReasons.length)
  ]

private def evalStdinPayload (raw : String) : Except String Json := do
  let req ← Json.parse raw
  let ver ← (← req.getObjVal? "schema_version").getStr?
  if ver != schemaVersion then
    throw s!"Unsupported schema_version: expected '{schemaVersion}', got '{ver}'"
  let reasonArr ← (← req.getObjVal? "reason_cases").getArr?
  let checkArr ← (← req.getObjVal? "check_cases").getArr?
  let mut reasonResults : Array Json := #[]
  for item in reasonArr do
    reasonResults := reasonResults.push (← evalReasonCase item)
  let mut checkResults : Array Json := #[]
  for item in checkArr do
    checkResults := checkResults.push (← evalCheckCase item)
  return Json.mkObj [
    ("check_results", Json.arr checkResults),
    ("reason_results", Json.arr reasonResults),
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
      IO.eprintln s!"evalforge-gate-oracle error: {err}"
      return 1
  | _ =>
    IO.eprintln "Usage: evalforge-gate-oracle <export-golden | eval-stdin>"
    return 2
