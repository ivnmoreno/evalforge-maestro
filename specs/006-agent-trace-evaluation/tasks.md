---

description: "Actionable, dependency-ordered task list for Milestone 6 — Agent Trace Evaluation"
---

# Tasks: Agent Trace Evaluation (Milestone M6)

**Input**: Design documents from `/specs/006-agent-trace-evaluation/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/schemas-v1.json](contracts/schemas-v1.json), [contracts/agent-metrics.md](contracts/agent-metrics.md), [quickstart.md](quickstart.md)

**Tests**: Required by Constitution Principle VII (`100%` branch coverage on `evalforge_maestro.metrics` and `evalforge_maestro.regression.gate`, `>=85%` global branch coverage, normalized AST source-hash guards, Draft 2020-12 schema parity, AST import purity, public API pinning, `@pytest.mark.gate_determinism`, and `@pytest.mark.gate_immutability`). Write/update tests first inside each phase before completing implementation.

**Organization**: Organized by user story in priority order (`US1`, `US2`, `US3`, `US4`) for independent validation.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Verify clean environment baseline (`uv lock --check`, `ruff`, `mypy --strict`, `pytest`) and confirm `../docpipe-maestro` remains unmodified on branch `006-agent-trace-evaluation` in repository root.
- [X] T002 Create skeleton contract test file in `tests/contract/test_m6_schemas.py` merging M1–M6 Draft 2020-12 schemas from `specs/006-agent-trace-evaluation/contracts/schemas-v1.json`.

---

## Phase 2: Foundational Typed Contracts (`types.py`)

**Purpose**: Single source of truth schemas (`schema_version = "1.0"`) required before any user story metrics, adapters, truncation, or reporting work begins.

- [X] T003 [P] Add unit tests covering legacy `1.0` dict/shorthand normalization, strict bounds, JSON-Schema validation, malformed argument fields, and policy constraints in `tests/unit/test_types.py`.
- [X] T004 [P] Update `tests/contract/test_m5_schemas.py` M5-snapshot assertion to continue validating M5 fields strictly without blocking M6 additions and populate Draft 2020-12 assertions in `tests/contract/test_m6_schemas.py`.
- [X] T005 Implement `ToolCallStatus`, `TraceStepKind`, `TargetType.AGENT`, and extended `EvidenceDecouplingCategory` enumerations in `src/evalforge_maestro/types.py` citing `data-model.md` (`TargetType`, `EvidenceDecouplingCategory`, `ToolCallStatus`, `TraceStepKind`).
- [X] T006 Implement `ExpectedToolCall` (`ExpectedToolCall.name`, `.arguments`, `.arguments_schema`, `.argument_match_mode`, `.optional`, `.order`), `ToolCallRecord` (`ToolCallRecord.id`, `.name`, `.arguments`, `.raw_arguments`, `.argument_parse_error`, `.result`, `.status`, `.error`, `.step_index`, `.elapsed_seconds`, `.metadata`), and `AgentTraceStep` (`AgentTraceStep.step_index`, `.kind`, `.name`, `.content`, `.tool_calls`, `.tool_call_id`, `.status`, `.error`, `.elapsed_seconds`, `.tokens`, `.metadata`) in `src/evalforge_maestro/types.py` citing `data-model.md`.
- [X] T007 Extend `CaseCriteria` (`CaseCriteria.forbidden_tools`, `.forbidden_argument_patterns`, `.max_steps`, `.max_tool_calls`, `.allow_redundant_failures`), `EvaluationCase.expected_tools`, `ExecutionResult.trace`, and `ExecutionResult.tool_calls` with backward-compatible input normalization in `src/evalforge_maestro/types.py` citing `data-model.md`.
- [X] T008 Add `AgentExtractorConfig` (`AgentExtractorConfig.output`, `.tool_calls`, `.trace`, `.tokens`, `.errors`, `.tool_id`, `.tool_name`, `.tool_arguments`, `.tool_result`, `.tool_status`, `.tool_error`, `.step_kind`, `.step_content`) and `ResolvedTargetConfig.agent_extractors` in `src/evalforge_maestro/types.py` citing `data-model.md`, and re-export M6 types in `src/evalforge_maestro/__init__.py`.

**Checkpoint**: All M1–M6 schema contract tests and `tests/unit/test_types.py` pass with zero regressions on historical `1.0` payloads.

---

## Phase 3: User Story 1 — Deterministic Tool Selection, Argument & Sequence Verification (Priority: P1) 🎯 MVP

**Goal**: Score `tool_selection`, `argument_correctness`, and `execution_sequence` deterministically with `100%` branch coverage and AST formula pinning.

**Independent Test**: Run `tests/unit/test_agent_metrics.py` (`US1` cases) and `tests/contract/test_metric_formulas.py` offline against expected tool datasets and captured tool/trace results.

- [X] T009 [P] [US1] Write unit tests for `tool_selection` (`f1`/`recall`/`exact_set`, optional tools, zero expectations `NOT_APPLICABLE`, `execution.errors` `INCONCLUSIVE`), `argument_correctness` (`subset`/`exact`/JSON Schema/`argument_parse_error`/missing constraints `NOT_APPLICABLE`), and `execution_sequence` (`subsequence`/`prefix`/`exact`/explicit `.order`/empty expectations `NOT_APPLICABLE`) in `tests/unit/test_agent_metrics.py`.
- [X] T010 [P] [US1] Implement pure chronological tool extraction (`_prepare_agent_inputs`) merging `ExecutionResult.tool_calls` and trace tool events without adapter imports in `src/evalforge_maestro/metrics/agent.py` (citing `contracts/agent-metrics.md` & `data-model.md`: `ExecutionResult.tool_calls`, `ExecutionResult.trace`).
- [X] T011 [US1] Implement `ToolSelectionMetric` (`tool_selection` singleton, AST-pinnable `_score_tool_selection`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `ExpectedToolCall.name` / `ExpectedToolCall.optional`.
- [X] T012 [US1] Implement `ArgumentCorrectnessMetric` (`argument_correctness` singleton, AST-pinnable `_score_argument_correctness`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `ExpectedToolCall.arguments`, `.arguments_schema`, `.argument_match_mode`, `ToolCallRecord.arguments`, `.argument_parse_error`.
- [X] T013 [US1] Implement `ExecutionSequenceMetric` (`execution_sequence` singleton, AST-pinnable `_score_execution_sequence`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `ExpectedToolCall.order`, `.optional`.
- [X] T014 [US1] Export `ToolSelectionMetric`, `ArgumentCorrectnessMetric`, `ExecutionSequenceMetric` and singletons in `src/evalforge_maestro/metrics/__init__.py` and `src/evalforge_maestro/__init__.py`, and pin AST hashes in `tests/contract/test_metric_formulas.py`.

---

## Phase 4: User Story 2 — Policy Compliance, Tool Efficiency & Failure Recovery Scoring (Priority: P1)

**Goal**: Score `tool_efficiency`, `policy_compliance`, and `failure_recovery` independently of final text answers with `100%` branch coverage and AST formula pinning.

**Independent Test**: Run `tests/unit/test_agent_metrics.py` (`US2` cases) and verify clean zero-error `NOT_APPLICABLE` recovery behavior, error recovery credit, forbidden-tool/arg binary failures, and loop/budget penalties.

- [X] T015 [P] [US2] Write full-branch unit tests for `tool_efficiency` (step/call budgets, identical failing call loops, `allow_redundant_failures`), `policy_compliance` (`forbidden_tools`, `forbidden_argument_patterns`, `ToolCallStatus.BLOCKED`), and `failure_recovery` (clean trace `NOT_APPLICABLE`, recovered retry/fallback `PASS`, unresolved terminal error `FAIL`, `ERROR` trace steps) in `tests/unit/test_agent_metrics.py`.
- [X] T016 [US2] Implement `ToolEfficiencyMetric` (`tool_efficiency` singleton, AST-pinnable `_score_tool_efficiency`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `data-model.md` (`CaseCriteria.max_steps`, `.max_tool_calls`, `.allow_redundant_failures`).
- [X] T017 [US2] Implement `PolicyComplianceMetric` (`policy_compliance` singleton, AST-pinnable `_score_policy_compliance`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `data-model.md` (`CaseCriteria.forbidden_tools`, `.forbidden_argument_patterns`, `ToolCallRecord.status`).
- [X] T018 [US2] Implement `FailureRecoveryMetric` (`failure_recovery` singleton, AST-pinnable `_score_failure_recovery`) in `src/evalforge_maestro/metrics/agent.py` per `contracts/agent-metrics.md` and `data-model.md` (`ToolCallRecord.status`, `.error`, `AgentTraceStep.kind`, `.status`, `.error`).
- [X] T019 [US2] Export `ToolEfficiencyMetric`, `PolicyComplianceMetric`, `FailureRecoveryMetric` and singletons in `src/evalforge_maestro/metrics/__init__.py` and `src/evalforge_maestro/__init__.py`, and pin AST hashes in `tests/contract/test_metric_formulas.py`.
- [X] T020 [US2] Verify `100%` branch coverage on `evalforge_maestro.metrics` via `tests/unit/test_metrics.py`, `tests/unit/test_ir_metrics.py`, `tests/unit/test_agent_metrics.py`, and `tests/contract/test_metric_formulas.py`.

---

## Phase 5: User Story 3 — `AgentAdapter`, Trace Normalizers, `ReplayAdapter` & Post-Scoring Truncation (Priority: P2)

**Goal**: Capture and normalize heterogeneous agent traces cleanly without framework lock-in, scrub secrets, replay JSONL traces offline, and truncate oversized traces post-scoring without breaking typed schemas.

**Independent Test**: Run `tests/unit/test_agent_adapter.py`, `tests/unit/test_replay_adapter.py`, `tests/unit/test_execution.py`, and `tests/integration/test_agent_eval_pipeline.py`.

- [X] T021 [P] [US3] Write unit tests for structural trace normalizers (OpenAI `tool_calls` chat messages, Anthropic `tool_use`/`tool_result` blocks, flat/legacy dicts, malformed JSON args, secret redaction), `AgentAdapter` (sync/async, `AgentExtractorConfig` dotted/callable paths, `pass_case`), and `ReplayAdapter` trace loading/redaction in `tests/unit/test_agent_adapter.py`.
- [X] T022 [P] [US3] Write unit tests for field-level post-scoring truncation of oversized `ExecutionResult.tool_calls` and `ExecutionResult.trace` (retaining un-truncated metric scoring while keeping persisted records strictly typed and setting `ExecutionResult.truncated = True`) in `tests/unit/test_execution.py`.
- [X] T023 [US3] Implement dependency-free trace & tool-call normalizers (`normalize_tool_calls`, `normalize_agent_trace`, secret redaction via `_canonical.redact_secrets` and `scrub_secret_text`) in `src/evalforge_maestro/adapters/_trace_norm.py` citing `data-model.md` (`ToolCallRecord`, `AgentTraceStep`).
- [X] T024 [US3] Implement protocol `AgentAdapter` supporting `AgentExtractorConfig` (citing `data-model.md`: `AgentExtractorConfig.*`), token usage normalization, secret redaction, and `config_fingerprint` in `src/evalforge_maestro/adapters/agent.py`.
- [X] T025 [US3] Update `src/evalforge_maestro/adapters/replay.py` to normalize & redact secrets across loaded `tool_calls` and `trace` payloads cleanly and export `AgentAdapter`, `normalize_agent_trace`, `normalize_tool_calls` in `src/evalforge_maestro/adapters/__init__.py` and `src/evalforge_maestro/__init__.py`.
- [X] T026 [US3] Extend `_truncate_execution_result` in `src/evalforge_maestro/execution/orchestrator.py` to perform field-level string trimming and trailing-item capping inside `ExecutionResult.tool_calls` (`ToolCallRecord`) and `ExecutionResult.trace` (`AgentTraceStep`) citing `data-model.md`, preserving typed validity and `truncated = True`.
- [X] T027 [US3] Add end-to-end integration tests (including `@pytest.mark.gate_determinism` and `@pytest.mark.gate_immutability` coverage for agent runs, baselines, and truncated disk reloads) in `tests/integration/test_agent_eval_pipeline.py`.
- [X] T028 [US3] Confirm strict AST boundaries in `tests/test_library_purity.py` (`execution/` & `metrics/` never import `adapters/`, cold-start imports stay pure).

---

## Phase 6: User Story 4 — CLI Agent Target Wiring & Decoupled Trace-vs-Answer Diagnostics (Priority: P2)

**Goal**: Enable CLI `--target-type agent` + `[target.agent_extractors]` configuration alongside high-visibility decoupled trace-vs-answer diagnostics in JSON and Markdown reports.

**Independent Test**: Run `tests/unit/test_cli_config.py`, `tests/unit/test_reporting.py`, and `tests/integration/test_cli_workflow.py` verifying config validation, `--target-type agent` execution, exit codes `0`–`4`, secret redaction, and decoupling reports.

- [X] T029 [P] [US4] Write CLI config and workflow tests covering `type = "agent"`, `[target.agent_extractors]`, `--target-type agent`, and all 6 agent `--metric` options in `tests/unit/test_cli_config.py` and `tests/integration/test_cli_workflow.py`.
- [X] T030 [P] [US4] Write reporting unit tests verifying `answer_passed_agent_trace_failed` and `agent_trace_passed_answer_failed` classification, tool summaries, secret scrubbing, and Markdown rendering in `tests/unit/test_reporting.py`.
- [X] T031 [US4] Extend `src/evalforge_maestro/cli/parser.py` (`--target-type` choices including `"agent"`, updated help text for agent metrics) keeping cold-start imports strictly lazy.
- [X] T032 [US4] Extend `src/evalforge_maestro/cli/config.py` to parse `[target.agent_extractors]` into `ResolvedTargetConfig.agent_extractors` citing `data-model.md`.
- [X] T033 [US4] Extend `src/evalforge_maestro/cli/targets.py` to resolve `TargetType.AGENT` via `AgentAdapter` with `AgentExtractorConfig` and register all 6 deterministic agent metrics in `_DIRECT_DETERMINISTIC_FACTORIES`.
- [X] T034 [US4] Extend `src/evalforge_maestro/reporting/builder.py` (`_AGENT_TRACE_METRIC_IDS`, `detect_decoupled_evidence`) to classify `EvidenceDecouplingCategory.ANSWER_PASSED_AGENT_TRACE_FAILED` and `EvidenceDecouplingCategory.AGENT_TRACE_PASSED_ANSWER_FAILED` citing `data-model.md`, scrubbing trace/tool secrets cleanly.
- [X] T035 [US4] Update `src/evalforge_maestro/reporting/markdown.py` to render decoupled agent trace-vs-answer diagnostics and involved tool names clearly in Markdown reports.
- [X] T036 [US4] Verify PII/secret hygiene across agent traces and CLI `--json` stdout / stderr streams in `tests/integration/test_cli_workflow.py`.

---

## Phase 7: Polish & Cross-Cutting Verification

**Purpose**: Ensure public API pinning, documentation, static analysis, full coverage gates, and packaging checks pass cleanly.

- [X] T037 [P] Pin all new M6 public `__all__` exports, dataclasses/models, adapters, normalizers, and metric signatures in `tests/test_api_stability.py`.
- [X] T038 [P] Update `README.md` (and `examples/ci/` documentation if helpful) documenting M6 agent trace evaluation SDK & CLI usage without touching `../docpipe-maestro`.
- [X] T039 Run full Constitution Principle VII checks (`uv lock --check`, `ruff format --check .`, `ruff check .`, `ruff check --select S src/`, `mypy --strict src tests`).
- [X] T040 Run global branch coverage (`>=85%`), 100% metrics & gate branch coverage, `@pytest.mark.gate_determinism` / `@pytest.mark.gate_immutability`, AST purity/cold-start subprocess probes, and Draft 2020-12 contract tests.
- [X] T041 Validate `quickstart.md` scenarios end-to-end and verify clean wheel build (`uv build`, `uv run twine check --strict dist/*`) + clean `--no-dev` minimal install cold-start behavior.
- [X] T042 Inspect final git diff (`git status -sb`, verify `../docpipe-maestro` completely untouched) and present validated Commitizen commit message verbatim for VS Code Source Control.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** -> **Phase 2 (Foundational `types.py`)** MUST complete first.
- **Phase 3 (US1)** & **Phase 4 (US2)** depend on Phase 2 and can execute cleanly in sequence within `metrics/agent.py` (all 6 metrics stay adapter-free).
- **Phase 5 (US3)** depends on Phase 2 (`types.py`) and interacts cleanly with Phase 3/4 via integration tests (`test_agent_eval_pipeline.py`).
- **Phase 6 (US4)** depends on Phases 3–5 (`metrics/agent.py`, `AgentAdapter`, typed schemas).
- **Phase 7 (Polish)** runs across the completed M6 surface before final verification & commit preparation.

## MVP Scope & Delivery Strategy

- **MVP Increment**: Phases 1–4 (`types.py` typed trace contracts + all 6 deterministic AST-pinned agent metrics at `100%` branch coverage).
- **Full M6 Delivery (`v0.2.0`)**: Phases 1–7 complete (`AgentAdapter` + structural trace normalizers + `ReplayAdapter` + post-scoring truncation + CLI `--target-type agent` + decoupled trace-vs-answer diagnostics + full CI verification).
