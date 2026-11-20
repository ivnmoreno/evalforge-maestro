# Phase 0 Research: Agent Trace Evaluation (Milestone M6)

**Feature**: `006-agent-trace-evaluation`  
**Date**: 2026-11-20  
**Status**: Resolved (Zero open clarifications)

## 1. Backward-Compatible Typed Trace & Tool Contracts (`src/evalforge_maestro/types.py`)

- **Decision**: Introduce strict Pydantic v2 models (`ToolCallStatus`, `TraceStepKind`, `ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`, `AgentExtractorConfig`) while adding `mode="before"` legacy input normalizers on `EvaluationCase.expected_tools`, `ExecutionResult.tool_calls`, and `ExecutionResult.trace`, plus additive optional policy/budget fields on `CaseCriteria` (`forbidden_tools`, `forbidden_argument_patterns`, `max_steps`, `max_tool_calls`, `allow_redundant_failures`). Preserve `schema_version: Literal["1.0"] = "1.0"`.
- **Rationale**:
  - Satisfies Constitution Principle III (no untyped `dict[str, Any]` payloads crossing subsystem boundaries, storage, or JSON outputs).
  - Satisfies Principle V (historical `1.0` `.evalforge/runs/*.json`, `.evalforge/manifest.jsonl`, and datasets load without breaking deserialization; raw `"search"` or legacy `{"tool": ..., "args": ...}` records upgrade seamlessly on read).
  - Keeps `EvaluationCase.model_dump(mode="json")["expected_tools"]` and `ExecutionResult.model_dump(mode="json")["trace" | "tool_calls"]` as lists of JSON objects matching M1's `"items": {"type": "object"}` schema shape while refining item contracts strictly under M6 `$defs`.
- **Alternatives Considered**:
  - Bumping `schema_version` to `"2.0"` immediately -> Rejected because M1–M5 artifacts and `SCHEMA_VERSION == "1.0"` baselines remain actively compared against M6 runs during `v0.2.0` transition.
  - Keeping `list[dict[str, Any]]` and validating ad-hoc inside metrics -> Rejected because untyped dict shapes leak across storage, orchestrator truncation, and reporting boundaries (violating Principle III).

## 2. Deterministic Agent Metric Suite & AST/Coverage Protection (`src/evalforge_maestro/metrics/agent.py`)

- **Decision**: Ship all six deterministic Domain 4 metrics in a new leaf-pure module `src/evalforge_maestro/metrics/agent.py` (zero adapter/CLI/judge imports), each with formal `MetricMetadata`, normalized `[0.0, 1.0]` / `None` scores, `NOT_APPLICABLE` zero-divisor safety, `100%` branch test coverage, and normalized AST hash pinning in `tests/contract/test_metric_formulas.py`:
  1. `tool_selection` (`mode = "f1" | "recall" | "exact_set"`, default `"f1"`).
  2. `argument_correctness` (`strict_mode: bool = False`, subset/exact structural equality + JSON Schema validation; parses JSON-stringified model arguments cleanly).
  3. `execution_sequence` (`mode = "subsequence" | "prefix" | "exact"`, default `"subsequence"` ordered alignment).
  4. `tool_efficiency` (step/call budget checks via `max_steps` / `max_tool_calls` plus identical failing-call loop detection honoring `allow_redundant_failures`).
  5. `policy_compliance` (`forbidden_tools`, case-insensitive/regex-safe literal `forbidden_argument_patterns`, and `ToolCallStatus.BLOCKED` steps; binary `0.0` `FAIL` on violation).
  6. `failure_recovery` (`NOT_APPLICABLE` when zero tool failures exist; proportional recovery score when failed tool steps are followed by clean retry/alternative recovery without unresolved terminal failures).
- **Rationale**:
  - F1 default on `tool_selection` prevents runaway extraneous tool calls from gaming recall `1.0`.
  - Ordered subsequence default on `execution_sequence` avoids brittle failures on harmless helper/read steps while supporting strict `"prefix"` / `"exact"` modes when required.
  - `NOT_APPLICABLE` on clean zero-error traces in `failure_recovery` avoids artificially inflating recovery scores across clean happy-path datasets.
- **Alternatives Considered**:
  - Deferring `tool_efficiency` / `policy_compliance` / `failure_recovery` -> Rejected because `docs/intent.md` Domain 4 and Principle IV explicitly mandate process-efficiency, policy, and recovery checks independent of final output.
  - Adding an LLM-judge trajectory metric in M6 -> Deferred so M6 remains 100% deterministic, fast, offline-safe, and free of judge flakiness.

## 3. Dependency-Free `AgentAdapter`, Enhanced `ReplayAdapter` & Trace Normalizers (`src/evalforge_maestro/adapters/`)

- **Decision**: Add `src/evalforge_maestro/adapters/_trace_norm.py` and `src/evalforge_maestro/adapters/agent.py` implementing:
  - Protocol-based `AgentAdapter` with configurable `AgentExtractorConfig` (dotted paths or callables for `output`, `tool_calls`, `trace`, `tokens`, `errors`, plus tool/step sub-extractors).
  - Structural, zero-dependency normalizers translating OpenAI-style `tool_calls` messages (with stringified JSON arguments), Anthropic-style `tool_use` / `tool_result` content blocks, flat trace steps, and legacy dict payloads into canonical `ToolCallRecord` and `AgentTraceStep` lists with secret redaction via `redact_secrets`.
  - Extended `ReplayAdapter` hydration passing loaded `trace` / `tool_calls` cleanly through structural normalization and redaction.
- **Rationale**:
  - Honors Constitution Principle I (zero LangChain/LlamaIndex/LangGraph/OpenAI/Anthropic SDK dependencies in core `pyproject.toml`).
  - Honors Principle II (`adapters/` depends downward on `types`, `_canonical`, `exceptions`; `metrics/` and `execution/` never import `adapters/`).
- **Alternatives Considered**:
  - Adding optional `[agents]` third-party SDK dependencies -> Rejected until a concrete consumer framework integration is requested; structural message/dict normalizers cover the vast majority of agent harnesses with zero extra dependencies or cold-start impact.

## 4. Field-Level Post-Scoring Trace Truncation (`src/evalforge_maestro/execution/orchestrator.py`)

- **Decision**: Extend `_truncate_execution_result(execution, max_context_chars)` (which already executes strictly *after* `_evaluate_metrics_safe` completes) to trim bulky strings/JSON values inside `ToolCallRecord` (`raw_arguments`, `argument_parse_error`, `error`, stringified `result`, large string values inside `arguments` & `metadata`) and `AgentTraceStep` (`content`, `error`, nested `tool_calls`, `metadata`), and if serialized `trace` or `tool_calls` still exceeds budget (e.g., excessive step count), cap trailing items up to budget and mark `truncated = True`.
- **Rationale**:
  - Preserves metric scoring integrity (metrics always score full un-truncated evidence).
  - Guarantees persisted `.evalforge/runs/<run_id>.json` and `.evalforge/tmp/<run_id>.jsonl` never store untyped raw strings inside typed `list[ToolCallRecord]` / `list[AgentTraceStep]` fields, so historical reloads always pass strict Pydantic validation (`100%` re-parseable).
- **Alternatives Considered**:
  - Replacing oversized `trace`/`tool_calls` lists with a flat summary string -> Rejected because it breaks strict typed persistence contracts (`ExecutionResult.trace: list[AgentTraceStep]`).

## 5. CLI Agent Wiring & Decoupled Trace-vs-Answer Reporting (`cli/`, `reporting/`)

- **Decision**:
  - Extend `TargetType` with `AGENT = "agent"`, add `--target-type agent` and `agent_extractors` config support (`[target.agent_extractors]` in `evalforge.toml`, `EVALFORGE_TARGET` / `CLIResolvedConfig`), and register all 6 deterministic agent metrics in `cli/targets.py`.
  - Extend `EvidenceDecouplingCategory` with `answer_passed_agent_trace_failed` and `agent_trace_passed_answer_failed`, detect both inside `reporting/builder.py:detect_decoupled_evidence`, and render trace/tool decoupling findings cleanly in Markdown and JSON diagnostics with full secret scrubbing.
- **Rationale**:
  - Mirrors M5's retrieval-vs-answer decoupling diagnostics cleanly without introducing breaking changes to CLI syntax, stream hygiene, or three-way reporting separation.
