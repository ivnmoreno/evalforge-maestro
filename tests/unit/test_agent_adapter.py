"""Unit tests for protocol AgentAdapter, trace normalizers, and ReplayAdapter traces."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.adapters import (
    AgentAdapter,
    ReplayAdapter,
    normalize_agent_trace,
    normalize_tool_calls,
)
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import (
    AgentExtractorConfig,
    EvaluationCase,
    TargetAdapter,
    ToolCallStatus,
    TraceStepKind,
)


def test_normalize_openai_and_anthropic_trace_structures_and_redacts_secrets() -> None:
    openai_messages = [
        {"role": "user", "content": "Find order 42 with token sk-secret-1234567890abcd"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "fetch_order",
                        "arguments": '{"order_id": "42", "api_key": "secret-val"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "fetch_order",
            "content": '{"status": "shipped"}',
        },
        {"role": "assistant", "content": "Order 42 is shipped."},
    ]
    steps = normalize_agent_trace(openai_messages)
    assert [s.kind for s in steps] == [
        TraceStepKind.USER_INPUT,
        TraceStepKind.LLM_RESPONSE,
        TraceStepKind.TOOL_RESULT,
        TraceStepKind.LLM_RESPONSE,
    ]
    assert "[REDACTED]" in str(steps[0].content)
    assert steps[1].tool_calls[0].arguments["api_key"] == "[REDACTED]"

    oai_calls = normalize_tool_calls(openai_messages)
    assert len(oai_calls) == 1
    assert oai_calls[0].name == "fetch_order"
    assert oai_calls[0].arguments == {"order_id": "42", "api_key": "[REDACTED]"}
    assert oai_calls[0].result == '{"status": "shipped"}'
    assert oai_calls[0].status == ToolCallStatus.SUCCESS

    anthropic_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Need to read policy"},
                {"type": "text", "text": "Checking now"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "read_policy",
                    "input": {"topic": "sla", "token": "Bearer abcdef12345"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "is_error": True,
                    "content": "permission denied",
                }
            ],
        },
    ]
    ant_steps = normalize_agent_trace(anthropic_messages)
    assert ant_steps[0].kind == TraceStepKind.LLM_RESPONSE
    assert ant_steps[0].tool_calls[0].name == "read_policy"
    assert ant_steps[0].tool_calls[0].arguments["token"] == "[REDACTED]"
    assert ant_steps[1].kind == TraceStepKind.TOOL_RESULT
    assert ant_steps[1].status == ToolCallStatus.ERROR

    ant_calls = normalize_tool_calls(anthropic_messages)
    assert len(ant_calls) == 1
    assert ant_calls[0].status == ToolCallStatus.ERROR
    assert ant_calls[0].error == "permission denied"

    with pytest.raises(AdapterError):
        normalize_tool_calls("not-a-sequence")
    with pytest.raises(AdapterError):
        normalize_agent_trace("not-a-sequence")


def test_agent_adapter_sync_async_custom_extractors_and_error_isolation() -> None:
    @dataclass
    class CustomAgentResult:
        final_text: str
        invocations: list[dict[str, Any]]
        steps: list[dict[str, Any]]
        usage: dict[str, int]

    def run_agent(case: EvaluationCase) -> CustomAgentResult:
        return CustomAgentResult(
            final_text=f"Handled {case.id}",
            invocations=[
                {
                    "call_id": "tc-1",
                    "tool_name": "lookup",
                    "params": {"q": case.input, "password": "pw"},
                    "response": "found",
                }
            ],
            steps=[
                {"type": "thought", "content": "ok"},
                {"type": "final_output", "content": "done"},
            ],
            usage={"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
        )

    adapter = AgentAdapter(
        run_agent,
        extractors=AgentExtractorConfig(
            output="final_text",
            tool_calls="invocations",
            trace="steps",
            tokens="usage",
            tool_id="call_id",
            tool_name="tool_name",
            tool_arguments="params",
            tool_result="response",
        ),
        system_version="agent-v1",
        model_id="test-model",
        config={"api_key": "sk-secret"},
        pass_case=True,
    )
    assert isinstance(adapter, TargetAdapter)
    assert adapter.system_version == "agent-v1"
    assert adapter.model_id == "test-model"
    assert adapter.config_fingerprint is not None

    case = EvaluationCase(id="c1", input="status")
    res = asyncio.run(adapter.execute(case))
    assert res.output == "Handled c1"
    assert res.errors == []
    assert res.tokens is not None and res.tokens.total_tokens == 17
    assert res.tool_calls[0].id == "tc-1"
    assert res.tool_calls[0].name == "lookup"
    assert res.tool_calls[0].arguments["password"] == "[REDACTED]"
    assert res.trace[0].kind == TraceStepKind.REASONING
    assert res.adapter_metadata["config"]["api_key"] == "[REDACTED]"

    # Async list-of-messages OpenAI payload automatically derives tool_calls, trace & output
    async def async_messages_agent(prompt: str) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": prompt},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "hi"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "search", "content": "42"},
            {"role": "assistant", "content": "The answer is 42."},
        ]

    msg_adapter = AgentAdapter(async_messages_agent)
    msg_res = asyncio.run(msg_adapter.execute(case))
    assert msg_res.output == "The answer is 42."
    assert len(msg_res.tool_calls) == 1
    assert msg_res.tool_calls[0].name == "search"
    assert msg_res.tool_calls[0].result == "42"
    assert len(msg_res.trace) == 4

    # Fault isolation captures exceptions cleanly without aborting batch
    def broken_agent(_: str) -> dict[str, Any]:
        raise RuntimeError("agent crashed with Bearer secret-token-value")

    err_res = asyncio.run(AgentAdapter(broken_agent).execute(case))
    assert err_res.errors
    assert "RuntimeError" in err_res.errors[0]
    assert "secret-token-value" not in err_res.errors[0]


def test_replay_adapter_normalizes_and_redacts_agent_traces(tmp_path: Path) -> None:
    replay_file = tmp_path / "agent_exec.jsonl"
    replay_file.write_text(
        json.dumps(
            {
                "case_id": "c1",
                "input": "q",
                "output": "ok",
                "elapsed_seconds": 0.1,
                "tool_calls": [
                    {
                        "tool": "auth",
                        "args": {"token": "sk-secret-1234567890abcdef"},
                        "output": "Bearer secret-tok",
                    }
                ],
                "trace": [{"role": "assistant", "content": "Authorization: Bearer my-secret-jwt"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    replay = ReplayAdapter.from_file(replay_file)
    rec = asyncio.run(replay.execute(EvaluationCase(id="c1", input="q")))
    assert rec.tool_calls[0].name == "auth"
    assert rec.tool_calls[0].arguments["token"] == "[REDACTED]"
    assert "[REDACTED]" in str(rec.tool_calls[0].result)
    assert "[REDACTED]" in str(rec.trace[0].content)
