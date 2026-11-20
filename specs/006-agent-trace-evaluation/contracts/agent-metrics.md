# Agent Metrics, Adapter & CLI Contracts (Milestone M6)

## 1. Deterministic Agent Metrics (`evalforge_maestro.metrics.agent`)

All built-in agent metrics share the formal `Metric` protocol (`MetricMetadata`, `[0.0, 1.0] | None`, AST/source-hash determinism guard, `100%` branch coverage) and return `MetricStatus.INCONCLUSIVE` (`score = None`) if `execution.errors` is non-empty.

| Metric ID | Class / Singleton | Default Threshold | Parameters | When `NOT_APPLICABLE` | Scoring Formula |
| --- | --- | --- | --- | --- | --- |
| `tool_selection` | `ToolSelectionMetric` / `tool_selection` | `0.8` | `mode="f1" \| "recall" \| "exact_set"`, `threshold=0.8` | `expected_tools` is `None` or `[]` | Unique required vs. called tool names (`optional=True` excluded from unexpected penalty). Default `f1 = 2*P*R/(P+R)` (`0.0` if `tp == 0`). |
| `argument_correctness` | `ArgumentCorrectnessMetric` / `argument_correctness` | `0.8` | `strict_mode=False`, `threshold=0.8` | Zero `ExpectedToolCall` entries specify `arguments` or `arguments_schema` | Average across constrained expectations matched greedily in call order (JSON Schema compliance or key-wise/exact argument match; unparseable `argument_parse_error` scores `0.0`). |
| `execution_sequence` | `ExecutionSequenceMetric` / `execution_sequence` | `1.0` | `mode="subsequence" \| "prefix" \| "exact"`, `threshold=1.0` | `expected_tools` is `None` or `[]` | Ordered sequence alignment of actual tool call names against expected sequence (sorted by `.order` if provided). `"subsequence"`: matched prefix of expected order / `len(exp)`; `"prefix"`: exact prefix length ratio; `"exact"`: `1.0` iff `act == exp`. |
| `tool_efficiency` | `ToolEfficiencyMetric` / `tool_efficiency` | `0.7` | `default_max_steps=None`, `default_max_tool_calls=None`, `allow_redundant_failures=0`, `loop_penalty=0.5`, `threshold=0.7` | Never (always applicable; clean traces with no overruns/loops score `1.0`) | Minimum of step budget factor (`min(1.0, max_steps/steps)`), call budget factor (`min(1.0, max_calls/calls)`), and redundant failing loop penalty (`max(0.0, 1.0 - excess_loops * loop_penalty)`). |
| `policy_compliance` | `PolicyComplianceMetric` / `policy_compliance` | `1.0` | `forbidden_tools=()`, `forbidden_argument_patterns=()`, `threshold=1.0` | Never | Binary `0.0` (`FAIL`) if any invoked tool matches `forbidden_tools`, any `BLOCKED` step/call exists, or any serialized call argument matches `forbidden_argument_patterns`; otherwise `1.0` (`PASS`). |
| `failure_recovery` | `FailureRecoveryMetric` / `failure_recovery` | `0.5` | `threshold=0.5` | Zero in-trace failed/timed-out tool calls or `ERROR` trace steps | For each in-trace failure event, scores recovered iff a subsequent `SUCCESS` tool call follows and the trace does not leave an unresolved trailing tool failure/error loop (`recovered / total_failures`). |

## 2. Structural Trace Normalizers & `AgentAdapter` (`evalforge_maestro.adapters`)

- `normalize_tool_calls(raw: Any) -> list[ToolCallRecord]`
- `normalize_agent_trace(raw: Any) -> list[AgentTraceStep]`
- Zero external framework dependencies; handles OpenAI-style `tool_calls` message dicts, Anthropic-style `tool_use` / `tool_result` blocks, custom extractor mappings (`AgentExtractorConfig`), and legacy dict entries while redacting sensitive tokens via `redact_secrets`.
- `AgentAdapter(target, *, extractors=None, system_version=None, model_id=None, pass_case=False)` satisfies `TargetAdapter` protocol cleanly.

## 3. CLI & Reporting Extensions

- `--target-type agent` added alongside `callable`, `rag`, `docpipe`, `replay`.
- TOML `[target]` accepts `type = "agent"` and `[target.agent_extractors]` path overrides (`CLIResolvedConfig.target.agent_extractors`).
- All 6 agent metric IDs supported cleanly by `--metric <id>[:key=val,...]` and `[metrics]` in `evalforge.toml`.
- `EvidenceDecouplingCategory` adds `answer_passed_agent_trace_failed` and `agent_trace_passed_answer_failed` reported in `ReportDocument.diagnostics` and Markdown reports.
