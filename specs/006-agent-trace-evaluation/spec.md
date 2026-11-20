# Feature Specification: Agent Trace Evaluation (Milestone M6)

**Feature Branch**: `006-agent-trace-evaluation`

**Created**: 2026-11-20

**Status**: Draft

**Input**: Milestone M6 — Agent Trace Evaluation (`docs/intent.md` Domain 4 & `docs/future-features.md`) aligned via design interview: backward-compatible typed trace/tool contracts, full deterministic agent metric suite (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`), dependency-free protocol `AgentAdapter` + enhanced `ReplayAdapter` + built-in common message/tool trace normalizers, CLI `--target-type agent` support, field-level post-scoring `max_context_chars` trace truncation, and decoupled trace-vs-answer reporting diagnostics.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic Tool Selection, Argument & Sequence Verification (Priority: P1)

As an engineer validating an AI agent workflow, I want to evaluate whether the agent selected the right tools, supplied valid expected arguments, and invoked tools in an acceptable execution order based on captured execution traces, without needing external model calls or modifying historical evaluation archives.

**Why this priority**: Tool selection, argument accuracy, and step ordering form the core deterministic foundation of agent evaluation (`Domain 4`) and enable repeatable, zero-cost regression checks across offline replay datasets and live runs.

**Independent Test**: Load a golden dataset with expected tool calls alongside offline or captured execution traces, score `tool_selection`, `argument_correctness`, and `execution_sequence`, and verify deterministic `[0.0, 1.0]` scores, `NOT_APPLICABLE` handling when no expected tools are defined, and identical results across repeated runs.

**Acceptance Scenarios**:

1. **Given** an evaluation case specifying expected tool calls with arguments and an execution trace that invoked the matching tools with valid arguments in order, **When** `tool_selection`, `argument_correctness`, and `execution_sequence` evaluate the case, **Then** each metric returns `PASS` with score `1.0` and structured supporting evidence referencing the matched tool calls.
2. **Given** an evaluation case whose expected tools include helper-tolerant ordering (`subsequence` default) and the agent runs extra diagnostic helper calls before/between expected steps, **When** `execution_sequence` evaluates under default `subsequence` mode, **Then** it passes (`1.0`), whereas switching to `prefix` or `exact` mode penalizes deviations strictly according to that mode.
3. **Given** an evaluation case calling expected tool names alongside unexpected extra tool invocations under default `tool_selection` (`mode = "f1"`), **When** `tool_selection` scores the trace, **Then** precision loss from extraneous calls reduces the F1 score deterministically while `mode = "recall"` measures expectation coverage alone and `mode = "exact_set"` requires exact set equality.
4. **Given** an evaluation case where no expected tools (or no argument constraints) are declared, **When** `tool_selection`, `argument_correctness`, or `execution_sequence` runs, **Then** the affected metric returns `score = None` with status `NOT_APPLICABLE` instead of dividing by zero or failing.

---

### User Story 2 - Policy Compliance, Tool Efficiency & Failure Recovery Scoring (Priority: P1)

As a reliability and safety owner, I want to score whether an agent respected step budgets, avoided redundant retry loops, obeyed forbidden-tool or forbidden-argument policies, and recovered when a tool returned an error, independently of whether the final synthesized text looked plausible.

**Why this priority**: In agentic workflows, an agent can hallucinate or guess a plausible answer while exceeding step budgets, looping endlessly on a failing tool, or invoking restricted tools; automated release gates must flag these process failures directly.

**Independent Test**: Run `policy_compliance`, `tool_efficiency`, and `failure_recovery` across traces containing (a) forbidden tools or disallowed arguments, (b) redundant identical failing calls or step budget overruns, (c) clean zero-error traces, and (d) tool-error traces that recover vs. abort without recovery; verify exact `PASS` / `FAIL` / `NOT_APPLICABLE` outcomes.

**Acceptance Scenarios**:

1. **Given** case criteria or metric policy specifying forbidden tool names or disallowed argument patterns and an agent trace that invokes a forbidden tool or restricted argument, **When** `policy_compliance` evaluates the trace, **Then** it returns `FAIL` with score `0.0` and explicit evidence naming the violated tool/rule.
2. **Given** a step or tool-call budget (`max_steps`) or redundant identical-failing-call guard, **When** an agent exceeds the allowed steps or repeats an identical failing tool call without new inputs or recovery, **Then** `tool_efficiency` penalizes the score deterministically below threshold (`FAIL`) and identifies the excess/looped steps.
3. **Given** a trace containing zero failed tool invocations, **When** `failure_recovery` evaluates the case, **Then** it returns `score = None` with status `NOT_APPLICABLE` so clean non-error cases never inflate recovery accuracy.
4. **Given** a trace where at least one tool invocation fails with an error, **When** a subsequent step succeeds cleanly (either via retry with clean success or an alternative tool/recovery step rather than leaving an unresolved fatal tool loop), **Then** `failure_recovery` returns `PASS` with proportional recovery credit, whereas unrecovered errors score `0.0` (`FAIL`).

---

### User Story 3 - Backward-Compatible Typed Trace Contracts, Adapter Capture & Trace Normalization (Priority: P2)

As an application developer integrating diverse agent runtimes or importing logged traces, I want a unified adapter and replay experience that normalizes tool calls and step traces from custom Python functions, replay files, or common chat/tool message trace dictionaries into strictly typed contracts while staying fully compatible with existing saved evaluation records.

**Why this priority**: Real agents emit heterogeneous trace formats (custom objects, OpenAI-style tool calls, Anthropic tool-use blocks, or legacy dictionaries); normalizing them cleanly at ingestion avoids vendor lock-in while preserving historical run compatibility.

**Independent Test**: Load legacy `1.0` run records and datasets containing raw dicts, replay JSONL agent traces, invoke a live custom agent callable via the agent adapter, and ingest common chat/tool-call trace dictionaries; confirm all normalize cleanly into typed trace/tool contracts with zero secrets leaked and full schema validation.

**Acceptance Scenarios**:

1. **Given** existing `1.0` dataset or persisted run records containing empty lists or legacy untyped dictionary entries for `expected_tools`, `tool_calls`, or `trace`, **When** loaded and validated, **Then** existing artifacts deserialize cleanly into typed trace/tool structures without breaking historical baselines or manifest continuity.
2. **Given** a Python agent callable returning nested objects or common chat/tool-call message dictionaries (including OpenAI-style `tool_calls` payloads or Anthropic-style `tool_use` / `tool_result` content blocks), **When** processed through the dependency-free agent adapter or trace normalizer, **Then** tool names, arguments, outputs, statuses/errors, and ordered step records populate the captured execution result deterministically without requiring external framework packages.
3. **Given** oversized trace payloads exceeding the configured `max_context_chars` resource cap, **When** evaluation finishes scoring and persists the run artifact, **Then** metrics evaluate the complete un-truncated evidence while post-scoring truncation trims oversized argument/observation/output strings inside individual trace and tool-call entries (capping trailing steps only if still necessary), preserving valid typed structures and flagging `truncated = true`.

---

### User Story 4 - CLI Agent Target Integration & Decoupled Trace-vs-Answer Diagnostics (Priority: P2)

As a CI operator reviewing an agent release gate report, I want CLI support for running agent evaluations (`--target-type agent` and TOML configuration) alongside high-visibility diagnostic separation showing when a run produced a good final answer despite broken/unsafe tool execution (or executed tools properly before failing final answer synthesis).

**Why this priority**: Surfacing process-vs-outcome decoupling directly in JSON and Markdown reports operationalizes evidence-aware gating for agent pipelines just as existing diagnostics separate retrieval from answers.

**Independent Test**: Run `evalforge-maestro run` via CLI with `type = "agent"` (and via offline replay `--executions`), evaluate cases with divergent answer vs. agent trace scores, inspect the exit code, JSON report diagnostics, and rendered Markdown summary to confirm trace-vs-answer decoupling sections and secret redaction.

**Acceptance Scenarios**:

1. **Given** a CLI invocation with `--target-type agent --target module:fn` or matching `[target]` TOML configuration, **When** `config validate` and `run` execute, **Then** the resolved configuration selects the agent adapter, supports configurable trace/tool extractors, honors `--max-context-chars` and `--strict`, and exits with standard POSIX codes (`0`–`4`).
2. **Given** an evaluated case where answer metrics pass (`PASS`) while one or more agent process metrics fail (`FAIL`), or where agent process metrics pass (`PASS`) while answer metrics fail (`FAIL`), **When** the JSON and Markdown reports are built, **Then** the diagnostics summary explicitly classifies and lists the decoupled trace-vs-answer case with failed/passed metric names, involved tool names, and an actionable explanation.
3. **Given** tool arguments, trace errors, or adapter metadata containing sensitive tokens or credentials, **When** captured, evaluated, logged, or rendered into reports, **Then** secret redaction scrubs sensitive values cleanly prior to storage or output.

---

### Edge Cases

- What happens when `expected_tools` is `[]` vs `None`, or specifies argument expectations only on a subset of expected tools? Reference-dependent checks return `NOT_APPLICABLE` when empty/absent, while `argument_correctness` evaluates strictly over expected tools that declare argument expectations (`NOT_APPLICABLE` if none do).
- What happens when identical tool names are invoked multiple times in different orders (`retry` after failure vs deliberate multi-step search)? Ordered metrics preserve chronological index order (`step_index` / list index); `argument_correctness` aligns matched calls consistently; `tool_efficiency` distinguishes legitimate recovery retries after a failure from identical repeated failing loops without intervening change.
- What happens when a tool argument expectation uses a subset dictionary vs strict full dictionary vs JSON Schema constraint? Default subset/exact normalization handles scalar and nested structures consistently while explicit schema rules validate structural compliance deterministically.
- What happens when a trace has malformed or partially missing optional fields (missing latency, omitted `tool_call_id`, stringified JSON arguments from model outputs)? Normalizers parse valid JSON argument strings cleanly and assign sensible defaults or record structured parse failures on malformed tool calls rather than crashing the batch.
- What happens when `trace` steps exist alongside separate `tool_calls`, or only one of the two is populated? Metrics read normalized tool invocations seamlessly from populated `tool_calls` or tool events present in `trace` without double-counting duplicates sharing the same identifier/step.
- What happens when historical runs recorded prior to Milestone M6 (`tool_calls = []`, `trace = []`) are compared against M6 agent runs? Baseline comparison, drift detection, and quality gating remain backwards-compatible, flagging `metric_version` or missing-metric mismatches transparently rather than failing deserialization.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define strict, schema-versioned Pydantic v2 contracts for expected tool calls, recorded tool invocations, agent trace steps, and agent policy/efficiency constraints while maintaining backward compatibility for loading existing `1.0` golden datasets, replay fixtures, and persisted run archives containing empty lists or legacy dict shapes.
- **FR-002**: System MUST verify every built-in agent metric returns strictly bounded scores (`float | None` in `[0.0, 1.0]`, never `NaN` or `Inf`), explicit `metric_version`, explicit status (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, `NOT_APPLICABLE`), structured evidence, supporting explanation, and formal capability/limitation metadata, enforced by AST/source-hash determinism guards and `100%` branch test coverage.
- **FR-003**: System MUST provide deterministic `tool_selection` scoring supporting configurable matching modes (`"f1"` default balanced over precision and recall, `"recall"`, and `"exact_set"`), returning `NOT_APPLICABLE` when no expected tools are specified.
- **FR-004**: System MUST provide deterministic `argument_correctness` scoring comparing actual tool arguments against expected arguments via normalized exact/subset structural comparison and JSON Schema validation, safely handling stringified JSON arguments and returning `NOT_APPLICABLE` when no expected argument constraints exist.
- **FR-005**: System MUST provide deterministic `execution_sequence` scoring supporting `"subsequence"` (default, tolerant of helper calls in order), `"prefix"`, and `"exact"` ordered alignment modes, returning `NOT_APPLICABLE` when no expected sequence/tools exist.
- **FR-006**: System MUST provide deterministic `tool_efficiency` scoring evaluating maximum step/tool-call budget constraints and detecting excessive redundant identical failing tool-call loops.
- **FR-007**: System MUST provide deterministic `policy_compliance` scoring checking invoked tools and arguments against configured forbidden tools and restricted argument patterns, failing immediately (`0.0`, `FAIL`) upon any policy breach.
- **FR-008**: System MUST provide deterministic `failure_recovery` scoring evaluating whether traces encountering at least one tool error subsequently achieve successful recovery, returning `NOT_APPLICABLE` (`score = None`) when zero tool failures occurred.
- **FR-009**: System MUST expose a dependency-free protocol-based `AgentAdapter` supporting configurable dotted-path or callable extractors (for `output`, `tool_calls`, `trace`, `tokens`, and `errors`) alongside built-in structural normalizers for common chat/tool-call trace dictionaries (such as OpenAI-style `tool_calls` messages and Anthropic-style `tool_use`/`tool_result` blocks) with zero hard dependencies on external agent frameworks.
- **FR-010**: System MUST extend `ReplayAdapter` and CLI dataset/execution validation so pre-captured JSONL/JSON agent traces validate and execute identically to live adapter runs for deterministic offline CI gates.
- **FR-011**: System MUST extend CLI target configuration (`evalforge.toml`, `EVALFORGE_*` environment variables, and `--target-type agent` plus extractor/trace options) and orchestrator post-scoring truncation (`max_context_chars`) to perform field-level trimming inside typed trace and tool-call records while preserving valid schema structures and recording `truncated = true`.
- **FR-012**: System MUST extend decoupled evidence diagnostics in JSON and Markdown reports to flag trace-vs-answer divergences (`answer passed despite invalid/unsafe trace` and `valid trace despite failed final answer`) alongside mandatory failures, anomaly flags, drift warnings, and secret scrubbing.
- **FR-013**: System MUST preserve cold-start import purity, unidirectional architecture boundaries (`types`, `metrics`, `execution`, `regression`, `storage`, and `reporting` MUST NOT import concrete `adapters` or `cli`), secret redaction across trace arguments/outputs/logs, and strict static/security verification (`ruff`, `mypy --strict`, Bandit `S`, public API signature pinning, determinism/immutability markers).

### Key Entities

- **Expected Tool Expectation**: Declarative ground-truth expectation defining required tool name, optional argument expectations or JSON Schema constraints, ordering/optionality hints, or policy rules associated with an evaluation case.
- **Tool Call Record**: Immutable normalized representation of a single tool invocation captured during agent execution (`tool_call_id`, tool `name`, structured `arguments`, optional `result`/`output`, execution status/error indicator, `step_index`, optional duration/metadata).
- **Agent Trace Step**: Ordered step entry within an execution trajectory capturing step kind (e.g., reasoning/thought, LLM message, tool call, tool result, error, final output), step index, timestamp/duration, content/payload, and optional linked tool call IDs.
- **Agent Extractor Configuration**: Configurable mapping rules (field names, dotted paths, or callables) enabling protocol `AgentAdapter` to normalize custom agent return objects into canonical `ExecutionResult` contracts.
- **Agent Policy & Efficiency Constraints**: Configurable case-level or metric-level boundaries specifying `forbidden_tools`, forbidden argument patterns, `max_steps` / `max_tool_calls`, and duplicate failing call tolerance.
- **Trace Decoupling Diagnostic**: High-visibility diagnostic entry recording cases where final answer evaluation and agent tool/trace evaluation diverge.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All six deterministic agent metrics (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`) execute completely offline with `100%` branch test coverage and `100%` reproducibility across repeated runs (`@pytest.mark.gate_determinism`).
- **SC-002**: Existing MVP test suites, schemas, and historical `1.0` run artifacts pass with zero regressions (`0` broken deserializations across legacy `1.0` fixtures), maintaining `>= 85%` global branch coverage and `100%` coverage on gate decision logic.
- **SC-003**: Protocol `AgentAdapter`, built-in message/tool-call trace normalizers, and offline `ReplayAdapter` handle raw custom outputs, multi-turn chat/tool dictionaries, malformed JSON argument strings, and empty/zero-error traces without crashing batch execution or leaking secrets (`0` raw credentials persisted).
- **SC-004**: Post-scoring trace truncation reduces persisted oversized trace and tool-call field payloads strictly within bounded limits while retaining valid schema-validated records (`100%` pass strict re-parsing of saved artifacts) and zero impact on pre-truncation metric scores.
- **SC-005**: CLI cold-start (`--help`) and minimal installation footprint remain pure with zero third-party agent framework imports introduced into core dependencies, and decoupled trace-vs-answer diagnostics surface accurately in both `--json` reports and Markdown summaries.

## Assumptions

- Target package milestone target is Milestone M6 (`v0.2.0` trajectory) while keeping compatibility with existing `1.0` artifact files created under `v0.1.x`.
- Built-in trace normalizers translate purely structural dictionary/JSON patterns (no dependency on `openai`, `anthropic`, `langchain`, `llama-index`, or `langgraph` packages).
- OpenTelemetry trace span ingestion, embedding similarity metrics, SQLite read indexes, and HTTP API servers remain explicitly deferred beyond M6 per `docs/future-features.md`.
- Local `docpipe-maestro` repository remains completely untouched and unmodified throughout M6 development.
