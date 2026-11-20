# Quickstart Validation Guide: Agent Trace Evaluation (Milestone M6)

**Prerequisites**: Editable install with dev extras (`uv sync --extra dev`), verified working tree.

## 1. Python SDK End-to-End Agent Evaluation

Run deterministic agent metrics directly against a Python agent function wrapped in `AgentAdapter`:

```python
from evalforge_maestro import (
    AgentAdapter,
    ArgumentCorrectnessMetric,
    DatasetEngine,
    EvaluationOrchestrator,
    ExecutionSequenceMetric,
    FailureRecoveryMetric,
    PolicyComplianceMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
)

dataset = DatasetEngine(
    [
        {
            "id": "agent-1",
            "input": "Check refund policy and calculate refund",
            "reference": "Eligible for 14-day refund",
            "expected_tools": [
                {"name": "lookup_policy", "arguments": {"topic": "refund"}},
                {"name": "calc_refund", "arguments": {"days": 5}},
            ],
            "criteria": {
                "mandatory": True,
                "forbidden_tools": ["delete_account"],
                "max_steps": 6,
            },
        }
    ]
)


def fake_agent(prompt: str) -> dict[str, object]:
    return {
        "output": "Eligible for 14-day refund",
        "tool_calls": [
            {
                "id": "tc-1",
                "name": "lookup_policy",
                "arguments": {"topic": "refund"},
                "status": "success",
            },
            {
                "id": "tc-2",
                "name": "calc_refund",
                "arguments": {"days": 5},
                "status": "error",
                "error": "transient",
            },
            {
                "id": "tc-3",
                "name": "calc_refund",
                "arguments": {"days": 5},
                "status": "success",
                "result": {"eligible": True},
            },
        ],
    }


metrics = [
    ToolSelectionMetric(),
    ArgumentCorrectnessMetric(),
    ExecutionSequenceMetric(),
    ToolEfficiencyMetric(),
    PolicyComplianceMetric(),
    FailureRecoveryMetric(),
]

run = EvaluationOrchestrator().run(dataset, AgentAdapter(fake_agent), metrics)
assert run.has_mandatory_failures is False
```

## 2. Offline Replay CLI Gate & Decoupled Diagnostics

Validate `evalforge.toml` / CLI runs targeting `--target-type agent` or `--executions` replay traces:

```bash
evalforge-maestro config validate --config evalforge.toml --json
evalforge-maestro run \
  --dataset golden-agent.jsonl \
  --executions executions-agent.jsonl \
  --metric exact_match \
  --metric tool_selection \
  --metric argument_correctness \
  --metric execution_sequence \
  --metric tool_efficiency \
  --metric policy_compliance \
  --metric failure_recovery \
  --max-context-chars 500 \
  --strict \
  --json
```

Confirm:
- Decoupled cases (`answer_passed_agent_trace_failed` / `agent_trace_passed_answer_failed`) populate `diagnostics.decoupled_evidence_cases` in `--json` and render inside the diagnostics section of Markdown reports.
- Persisted `.evalforge/runs/<run_id>.json` preserves valid schema structures under `max_context_chars` truncation with `truncated = true`.

## 3. Contract & Quality Gates

```bash
uv run pytest --strict-markers -W error --cov=evalforge_maestro.metrics --cov-branch --cov-fail-under=100 tests/unit/test_metrics.py tests/unit/test_ir_metrics.py tests/unit/test_agent_metrics.py tests/contract/test_metric_formulas.py
uv run pytest --strict-markers -W error tests/contract/test_m6_schemas.py tests/test_library_purity.py tests/test_api_stability.py
uv run ruff format --check . && uv run ruff check . && uv run mypy --strict src tests
```
