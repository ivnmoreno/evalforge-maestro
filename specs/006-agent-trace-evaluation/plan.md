# Implementation Plan: Milestone 6 — Agent Trace Evaluation

**Branch**: `006-agent-trace-evaluation` | **Date**: 2026-11-20 | **Spec**: [spec.md](file:///home/maestro/LifeFolder/10_PUBLIC/projects/evalforge-maestro/specs/006-agent-trace-evaluation/spec.md)

**Input**: Feature specification from `/specs/006-agent-trace-evaluation/spec.md`

## Summary

Milestone M6 adds full deterministic agent trace evaluation on top of `evalforge-maestro`'s library-pure architecture (`v0.2.0` trajectory): (1) strict, backward-compatible Pydantic v2 models (`ToolCallStatus`, `TraceStepKind`, `ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`, `AgentExtractorConfig`, plus `CaseCriteria` policy/budget constraints) upgrading `expected_tools`, `tool_calls`, and `trace` inside `types.py` while reading legacy `1.0` JSON/JSONL shapes cleanly; (2) six versioned deterministic agent metrics (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`) in `metrics/agent.py` with `100%` branch coverage and AST formula pinning; (3) dependency-free protocol `AgentAdapter`, structural OpenAI/Anthropic/message-dict trace normalizers, and extended `ReplayAdapter`; (4) field-level post-scoring `max_context_chars` trace/tool-call truncation in `execution/orchestrator.py`; and (5) CLI `--target-type agent` wiring plus decoupled trace-vs-answer diagnostics in JSON & Markdown reporting.

## Technical Context

**Language/Version**: Python `>=3.10` (`3.10`–`3.13`, `mypy --strict`)

**Primary Dependencies**: Unchanged core (`pydantic>=2.7,<3`, `jsonschema>=4.23,<5`, `tomli` Python `<3.11` only); zero external agent framework SDKs (`langchain`, `llama-index`, `langgraph`, `openai`, `anthropic` remain strictly absent).

**Storage**: Existing immutable `.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`, `.evalforge/baselines.json`, and incremental `.evalforge/tmp/<run_id>.jsonl` (`LocalRunStore`, `0o700`/`0o600`), preserving backward load compatibility with pre-M6 `1.0` runs.

**Testing**: `pytest --strict-markers -W error`, `>=85%` global branch coverage, **`100%` branch coverage** on `evalforge_maestro.metrics` (including `metrics/agent.py`) and `evalforge_maestro.regression.gate`, normalized AST source-hash contract checks in `tests/contract/test_metric_formulas.py`, Draft 2020-12 schema contract tests (`tests/contract/test_m6_schemas.py`), AST purity & `--help` cold-start probes (`tests/test_library_purity.py`), public API signature pinning (`tests/test_api_stability.py`), `@pytest.mark.gate_determinism`, and `@pytest.mark.gate_immutability`.

**Target Platform**: Cross-platform (`ubuntu-latest`, `macos-latest`, `windows-latest`), offline CI (`--mock --local-only --strict`).

**Project Type**: Independent evaluation & regression library + CLI (`evalforge-maestro`).

**Performance Goals**: Zero additional cold-start module imports; bounded async orchestrator streaming and post-scoring field-level trace truncation keep workstation memory bounded under large multi-step traces.

**Constraints**: Strict unidirectional imports (`metrics`, `execution`, `regression`, `storage`, `reporting` NEVER import `adapters` or `cli`); zero leaked credentials across trace arguments, tool results, logs, or reports; `../docpipe-maestro` remains untouched.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Research | Post-Design | Justification / Enforcement Mechanism |
| --- | --- | --- | --- |
| **I. One-Sentence Scope Tiebreaker** | PASS | PASS | Evaluates captured/replayed agent traces externally via adapters and normalizers without hosting an agent runtime, orchestrator loop, or third-party agent SDK dependencies. |
| **II. Library Purity & Unidirectional Deps** | PASS | PASS | Trace/tool contracts reside in `types.py`; deterministic metrics live strictly in `metrics/agent.py` importing zero adapter modules; trace normalizers & `AgentAdapter` live inside `adapters/`; `reporting/` imports only `types`, `_canonical`, `exceptions`, and stdlib. Verified by `tests/test_library_purity.py`. |
| **III. Single Schema Source of Truth** | PASS | PASS | `ExpectedToolCall`, `ToolCallRecord`, `AgentTraceStep`, `ToolCallStatus`, `TraceStepKind`, `AgentExtractorConfig`, `CaseCriteria` policy fields, `TargetType.AGENT`, and extended `EvidenceDecouplingCategory` all live in `src/evalforge_maestro/types.py` and `specs/006-agent-trace-evaluation/contracts/schemas-v1.json`. |
| **IV. Evidence-Aware & Anomaly-Safe Eval** | PASS | PASS | Decouples process compliance/efficiency/recovery (`tool_selection`, `argument_correctness`, `execution_sequence`, `tool_efficiency`, `policy_compliance`, `failure_recovery`) from final synthesis, returns `NOT_APPLICABLE` safely on empty expectations or zero-error recovery traces, and surfaces trace-vs-answer decoupling in `ReportDiagnosticsSummary`. |
| **V. Immutable Artifacts & Determinism** | PASS | PASS | All 6 metrics produce identical `[0.0, 1.0]` / `None` scores and canonical JSON hashes across repeated runs; post-scoring `max_context_chars` truncation preserves valid schema structures without mutating pre-truncation scores; AST hashes pin metric logic to `metric_version`. |
| **VI. Stream & Secret Hygiene** | PASS | PASS | `AgentAdapter`, `ReplayAdapter`, `reporting`, and `cli` redact secrets inside tool arguments, raw arguments, results, errors, and trace metadata; CLI streams preserve strict `--json` stdout / stderr isolation. |
| **VII. Automated Quality Gates** | PASS | PASS | Preserves `ruff format/check`, Bandit `S`, `mypy --strict`, `>=85%` total / `100%` metrics & gate branch coverage, `pip-audit`, `cz check`, `@pytest.mark.gate_determinism`, and `@pytest.mark.gate_immutability`. |

## Project Structure

### Documentation (this feature)

```text
specs/006-agent-trace-evaluation/
├── spec.md                         # Stakeholder-aligned feature specification
├── plan.md                         # This implementation plan
├── research.md                     # Phase 0 architectural & semantic decisions
├── data-model.md                   # Phase 1 entity schemas & validation rules
├── quickstart.md                   # End-to-end validation scenarios
├── checklists/
│   └── requirements.md             # Spec quality checklist
└── contracts/
    ├── schemas-v1.json             # Draft 2020-12 M6 schema definitions
    └── agent-metrics.md            # Formal metric formulas, adapter & CLI contracts
```

### Source Code (repository root)

```text
src/evalforge_maestro/
├── __init__.py                     # Export typed M6 trace/tool models, AgentAdapter, trace normalizers, and 6 agent metrics
├── types.py                        # Add ToolCallStatus, TraceStepKind, ExpectedToolCall, ToolCallRecord, AgentTraceStep, AgentExtractorConfig, CaseCriteria & TargetType.AGENT / EvidenceDecouplingCategory extensions
├── metrics/
│   ├── __init__.py                 # Export 6 agent metric classes & singletons
│   └── agent.py                    # Deterministic agent metrics + pure chronological tool extraction helpers (100% branch coverage)
├── adapters/
│   ├── __init__.py                 # Export AgentAdapter, normalize_agent_trace, normalize_tool_calls
│   ├── _trace_norm.py              # Zero-dep structural trace/tool-call normalizers (OpenAI, Anthropic, generic/legacy dicts) + secret redaction
│   ├── agent.py                    # Protocol AgentAdapter with AgentExtractorConfig
│   └── replay.py                   # Ensure loaded ReplayAdapter traces/tool_calls normalize & redact secrets cleanly
├── execution/
│   └── orchestrator.py             # Extend _truncate_execution_result for typed field-level trace & tool_calls truncation
├── reporting/
│   ├── builder.py                  # Add _AGENT_TRACE_METRIC_IDS & decoupled trace-vs-answer diagnostics (+ secret scrubbing)
│   └── markdown.py                 # Render trace-vs-answer decoupling & key trace tool summaries clearly
└── cli/
    ├── parser.py                   # Allow 'agent' in --target-type help/choices and document agent metrics
    ├── config.py                   # Parse [target.agent_extractors] into ResolvedTargetConfig.agent_extractors
    └── targets.py                  # Register TargetType.AGENT -> AgentAdapter & all 6 agent metrics in _DIRECT_DETERMINISTIC_FACTORIES
tests/
├── contract/
│   ├── test_metric_formulas.py     # Pin AST source hashes & MetricMetadata for all 6 M6 agent metrics + helpers
│   ├── test_m5_schemas.py          # Preserve M5 schema check cleanly alongside additive M6 agent_extractors field
│   └── test_m6_schemas.py          # Draft 2020-12 schema validation across M1-M6 models & backward 1.0 deserialization
├── unit/
│   ├── test_types.py               # Overlay M6 schema parity + test legacy/malformed ToolCallRecord/AgentTraceStep/ExpectedToolCall
│   ├── test_agent_metrics.py       # 100% branch coverage across all 6 metrics & edge cases
│   ├── test_agent_adapter.py       # AgentAdapter extractors, OpenAI/Anthropic trace normalizers, secret redaction & ReplayAdapter traces
│   ├── test_execution.py           # Field-level post-scoring trace & tool_calls truncation under max_context_chars
│   ├── test_cli_config.py          # [target.agent_extractors] & target.type="agent" config resolution
│   └── test_reporting.py           # Decoupled answer-vs-trace Markdown & JSON diagnostics
├── integration/
│   ├── test_agent_eval_pipeline.py # End-to-end orchestrator + AgentAdapter/ReplayAdapter + QualityGate + @gate_determinism/@gate_immutability
│   └── test_cli_workflow.py        # CLI --target-type agent & offline trace replay workflow checks
├── test_api_stability.py           # Pin M6 __all__ exports, classes, functions, and signatures
└── test_library_purity.py          # Verify metrics/agent.py & cold-start import boundaries remain 100% pure
```
