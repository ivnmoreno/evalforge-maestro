# Data Model: Agent Trace Evaluation (Milestone M6)

**Feature**: `006-agent-trace-evaluation` | **Single Source**: `src/evalforge_maestro/types.py` | **Schema Version**: `"1.0"`

## 1. Enumerations

### `TargetType` (extended)
- `"callable"`
- `"rag"`
- `"docpipe"`
- `"replay"`
- `"agent"` *(M6 addition)*

### `EvidenceDecouplingCategory` (extended)
- `"answer_passed_retrieval_or_grounding_failed"`
- `"retrieval_passed_answer_or_grounding_failed"`
- `"answer_passed_agent_trace_failed"` *(M6 addition)*
- `"agent_trace_passed_answer_failed"` *(M6 addition)*

### `ToolCallStatus` *(new)*
- `"success"`: Tool invocation completed without error.
- `"error"`: Tool invocation failed, returned error payload, or had unparseable arguments.
- `"timeout"`: Tool invocation exceeded timeout.
- `"blocked"`: Tool invocation blocked or flagged by runtime policy guardrails.

### `TraceStepKind` *(new)*
- `"user_input"`
- `"reasoning"`
- `"llm_response"`
- `"tool_call"`
- `"tool_result"`
- `"error"`
- `"final_output"`
- `"other"`

## 2. Typed Trace & Tool Entities

### `ExpectedToolCall`
- `name: str` (non-empty trimmed identifier; accepts input aliases `"tool"`, `"tool_name"`, or nested `"function.name"` and string shorthand `"search"` -> `{"name": "search"}`)
- `arguments: dict[str, Any] | None = None` (accepts input aliases `"args"`, `"input"`, `"parameters"`, or valid JSON object string; strictly JSON-serializable)
- `arguments_schema: dict[str, Any] | None = None` (Draft 2020-12 / valid JSON Schema validated on construction via `jsonschema`)
- `argument_match_mode: Literal["subset", "exact"] = "subset"`
- `optional: bool = False`
- `order: int | None = None` (`>= 0`, non-bool integer)

### `ToolCallRecord`
- `id: str | None = None` (aliases `"tool_call_id"`, `"call_id"`)
- `name: str` (non-empty trimmed identifier; aliases `"tool"`, `"tool_name"`, nested `"function.name"`)
- `arguments: dict[str, Any] = Field(default_factory=dict)` (JSON string auto-decoded when valid object JSON; malformed/non-object JSON populates `{}` with `argument_parse_error` and `status = "error"`)
- `raw_arguments: str | None = None` (preserved raw string when argument parsing failed or explicitly recorded)
- `argument_parse_error: str | None = None`
- `result: Any = None` (aliases `"output"`, `"response"`; strictly JSON-serializable)
- `status: ToolCallStatus = ToolCallStatus.SUCCESS` (normalizes `"failed"` -> `"error"`, or infers `"error"` when non-empty `error` / `argument_parse_error` is present alongside default status)
- `error: str | None = None`
- `step_index: int | None = None` (`>= 0`, non-bool integer)
- `elapsed_seconds: float | None = None` (`>= 0.0`, finite non-bool)
- `metadata: dict[str, Any] = Field(default_factory=dict)`

### `AgentTraceStep`
- `step_index: int | None = None` (`>= 0`, non-bool integer)
- `kind: TraceStepKind = TraceStepKind.OTHER` (accepts `"type"` / `"role"` aliases e.g. `"assistant"` -> `"llm_response"`, `"tool"` -> `"tool_result"`, `"user"` -> `"user_input"`, `"thought"` -> `"reasoning"`, `"output"` -> `"final_output"`)
- `name: str | None = None`
- `content: Any = None` (JSON-serializable payload)
- `tool_calls: list[ToolCallRecord] = Field(default_factory=list)`
- `tool_call_id: str | None = None`
- `status: ToolCallStatus | None = None`
- `error: str | None = None`
- `elapsed_seconds: float | None = None` (`>= 0.0`, finite non-bool)
- `tokens: TokenUsage | None = None`
- `metadata: dict[str, Any] = Field(default_factory=dict)`

## 3. Existing Contract Extensions

### `CaseCriteria` (additive defaults preserving legacy `1.0` data)
- Existing: `mandatory`, `json_schema`, `pass_threshold`, `metric_thresholds`
- M6 additions:
  - `forbidden_tools: list[str] = Field(default_factory=list)` (non-empty stripped strings)
  - `forbidden_argument_patterns: list[str] = Field(default_factory=list)` (non-empty strings)
  - `max_steps: int | None = Field(default=None, ge=1)` (non-bool int)
  - `max_tool_calls: int | None = Field(default=None, ge=1)` (non-bool int)
  - `allow_redundant_failures: int = Field(default=0, ge=0)` (non-bool int)

### `EvaluationCase`
- `expected_tools: list[ExpectedToolCall] | None = None` (automatically validates and normalizes `str`, legacy `dict`, or `ExpectedToolCall` entries; preserves `None` when omitted)

### `ExecutionResult`
- `trace: list[AgentTraceStep] = Field(default_factory=list)`
- `tool_calls: list[ToolCallRecord] = Field(default_factory=list)`

### `AgentExtractorConfig` *(new)*
- Same validation semantics as `RAGExtractorConfig` (`extra="forbid"`, `arbitrary_types_allowed=True`, non-empty trimmed path strings or callables):
  - `output`, `tool_calls`, `trace`, `tokens`, `errors`, `tool_id`, `tool_name`, `tool_arguments`, `tool_result`, `tool_status`, `tool_error`, `step_kind`, `step_content`

### `ResolvedTargetConfig` (CLI Config Extension)
- Adds `agent_extractors: dict[str, str] = Field(default_factory=dict)` mapped from TOML `[target.agent_extractors]` and passed into `AgentExtractorConfig(**t_cfg.agent_extractors)` for `--target-type agent`.
