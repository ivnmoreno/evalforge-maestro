"""Unit tests for OpenTelemetry span ingestion, correlation, and ReplayAdapter integration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.adapters import (
    ReplayAdapter,
    ingest_otel_spans,
    load_otel_executions,
)
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import AdapterError, DatasetError
from evalforge_maestro.metrics import (
    ArgumentCorrectnessMetric,
    ExactMatchMetric,
    ExecutionSequenceMetric,
    PrecisionAtKMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
)
from evalforge_maestro.types import (
    CaseCriteria,
    EvaluationCase,
    ExpectedToolCall,
    MetricStatus,
    OtelExtractorConfig,
    OtelTimestampUnit,
    ToolCallStatus,
    TraceStepKind,
)


def _kv(key: str, val: Any) -> dict[str, Any]:
    if isinstance(val, bool):
        return {"key": key, "value": {"boolValue": val}}
    if isinstance(val, int):
        return {"key": key, "value": {"intValue": str(val)}}
    if isinstance(val, float):
        return {"key": key, "value": {"doubleValue": val}}
    if isinstance(val, dict):
        return {
            "key": key,
            "value": {"kvlistValue": {"values": [_kv(k, v) for k, v in val.items()]}},
        }
    if isinstance(val, list):
        return {
            "key": key,
            "value": {"arrayValue": {"values": [_kv("item", item)["value"] for item in val]}},
        }
    return {"key": key, "value": {"stringValue": str(val)}}


def test_us1_otlp_span_normalization_dedup_and_downstream_metrics() -> None:
    secret_tok = "sk-live-secret-token-8888"
    bearer_tok = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    otlp_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _kv("service.name", "invoice-agent"),
                        _kv("service.version", "agent-v2.4.0"),
                        _kv("service.api_key", secret_tok),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "openinference.instrumentation"},
                        "spans": [
                            {
                                "traceId": "0102030405060708090a0b0c0d0e0f10",
                                "spanId": "1111111111111111",
                                "name": "agent.run",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000001500000000",
                                "attributes": [
                                    _kv("evalforge.case_id", "case-inv-1"),
                                    _kv("input.value", "Check invoice 42"),
                                    _kv(
                                        "output.value",
                                        f"Invoice 42 is paid Authorization: Bearer {bearer_tok}",
                                    ),
                                    _kv("openinference.span.kind", "AGENT"),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "0102030405060708090a0b0c0d0e0f10",
                                "spanId": "2222222222222222",
                                "parentSpanId": "1111111111111111",
                                "name": "retriever.search",
                                "startTimeUnixNano": "1700000000100000000",
                                "endTimeUnixNano": "1700000000300000000",
                                "attributes": [
                                    _kv("openinference.span.kind", "RETRIEVER"),
                                    _kv(
                                        "retrieval.documents",
                                        [
                                            {
                                                "document.id": "doc-inv-42",
                                                "document.content": "Invoice 42 paid 2026-10",
                                                "document.score": 0.94,
                                            }
                                        ],
                                    ),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "0102030405060708090a0b0c0d0e0f10",
                                "spanId": "3333333333333333",
                                "parentSpanId": "1111111111111111",
                                "name": "llm.chat",
                                "startTimeUnixNano": "1700000000400000000",
                                "endTimeUnixNano": "1700000000800000000",
                                "attributes": [
                                    _kv("gen_ai.operation.name", "chat"),
                                    _kv("gen_ai.response.model", "glm-5.3"),
                                    _kv("gen_ai.usage.input_tokens", 120),
                                    _kv("gen_ai.usage.output_tokens", 45),
                                    _kv("llm.token_count.completion_details.reasoning", 10),
                                    _kv(
                                        "llm.output_messages",
                                        json.dumps(
                                            [
                                                {
                                                    "role": "assistant",
                                                    "content": "Calling lookup_invoice",
                                                    "tool_calls": [
                                                        {
                                                            "id": "call_abc",
                                                            "function": {
                                                                "name": "lookup_invoice",
                                                                "arguments": '{"invoice_id": "42"}',
                                                            },
                                                        }
                                                    ],
                                                }
                                            ]
                                        ),
                                    ),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "0102030405060708090a0b0c0d0e0f10",
                                "spanId": "4444444444444444",
                                "parentSpanId": "3333333333333333",
                                "name": "tool.lookup_invoice",
                                "startTimeUnixNano": "1700000000900000000",
                                "endTimeUnixNano": "1700000001200000000",
                                "attributes": [
                                    _kv("gen_ai.operation.name", "execute_tool"),
                                    _kv("gen_ai.tool.name", "lookup_invoice"),
                                    _kv("gen_ai.tool.call.id", "call_abc"),
                                    _kv(
                                        "gen_ai.tool.call.arguments",
                                        json.dumps({"invoice_id": "42", "api_key": secret_tok}),
                                    ),
                                    _kv("gen_ai.tool.call.result", '{"paid": true}'),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "0102030405060708090a0b0c0d0e0f10",
                                "spanId": "5555555555555555",
                                "parentSpanId": "3333333333333333",
                                "name": "tool.audit_log",
                                "startTimeUnixNano": "1700000001300000000",
                                "endTimeUnixNano": "1700000001400000000",
                                "attributes": [
                                    _kv("tool.name", "audit_log"),
                                    _kv("tool.call.id", "call_bad"),
                                    _kv("tool.parameters", "{not-valid-json"),
                                ],
                                "status": {"code": 2, "message": "TimeoutError: vendor timeout"},
                            },
                        ],
                    }
                ],
            }
        ]
    }

    results = ingest_otel_spans(otlp_payload)
    assert len(results) == 1
    exec_res = results[0]
    assert exec_res.case_id == "case-inv-1"
    assert exec_res.system_version == "agent-v2.4.0"
    assert exec_res.model_id == "glm-5.3"
    assert exec_res.elapsed_seconds == pytest.approx(1.5, abs=1e-6)
    assert exec_res.tokens is not None
    assert exec_res.tokens.prompt_tokens == 120
    assert exec_res.tokens.completion_tokens == 45
    assert exec_res.tokens.reasoning_tokens == 10
    assert exec_res.tokens.total_tokens == 165
    assert [c.id for c in exec_res.retrieved_chunks] == ["doc-inv-42"]
    assert exec_res.retrieved_chunks[0].score == 0.94

    # Tool call 'call_abc' merged once rather than duplicated across LLM intent + tool span
    assert [c.name for c in exec_res.tool_calls] == ["lookup_invoice", "audit_log"]
    assert exec_res.tool_calls[0].id == "call_abc"
    assert exec_res.tool_calls[0].status == ToolCallStatus.SUCCESS
    assert exec_res.tool_calls[0].result == {"paid": True}
    assert exec_res.tool_calls[1].status == ToolCallStatus.TIMEOUT
    assert exec_res.tool_calls[1].argument_parse_error is not None
    assert exec_res.tool_calls[1].raw_arguments == "{not-valid-json"

    # Secrets scrubbed across outputs, arguments, and metadata
    dumped = json.dumps(exec_res.model_dump(mode="json"))
    assert secret_tok not in dumped
    assert bearer_tok not in dumped
    assert exec_res.trace[0].kind == TraceStepKind.OTHER
    assert any(s.kind == TraceStepKind.LLM_RESPONSE for s in exec_res.trace)

    # Evaluate ingested trace seamlessly using M2 IR & M6 agent metrics
    case = EvaluationCase(
        id="case-inv-1",
        input="Check invoice 42",
        reference=exec_res.output,
        expected_context=["doc-inv-42"],
        expected_tools=[
            ExpectedToolCall(name="lookup_invoice", arguments={"invoice_id": "42"}, order=0)
        ],
        criteria=CaseCriteria(forbidden_tools=["drop_table"]),
    )
    assert ExactMatchMetric().evaluate(case, exec_res).status == MetricStatus.PASS
    assert PrecisionAtKMetric(1).evaluate(case, exec_res).score == 1.0
    assert ToolSelectionMetric(mode="recall").evaluate(case, exec_res).score == 1.0
    assert ToolSelectionMetric().evaluate(case, exec_res).score == pytest.approx(2 / 3, abs=1e-4)
    assert ArgumentCorrectnessMetric().evaluate(case, exec_res).score is not None
    assert ExecutionSequenceMetric().evaluate(case, exec_res).score == 1.0
    assert ToolEfficiencyMetric(default_max_tool_calls=3).evaluate(case, exec_res).score == 1.0


def test_us1_duck_typed_sdk_spans_clock_skew_and_orphan_events() -> None:
    @dataclass
    class _Ctx:
        trace_id: int
        span_id: int

    @dataclass
    class _Parent:
        span_id: int

    @dataclass
    class _StatusCode:
        name: str

    @dataclass
    class _Status:
        status_code: _StatusCode
        description: str | None = None

    @dataclass
    class _Event:
        name: str
        timestamp: int
        attributes: dict[str, Any]

    @dataclass
    class _Resource:
        attributes: dict[str, Any]

    @dataclass
    class _DuckSpan:
        context: _Ctx
        parent: _Parent | None
        name: str
        start_time: int
        end_time: int
        attributes: dict[str, Any]
        events: list[_Event]
        status: _Status
        resource: _Resource

    trace_int = int("abcdef" * 5 + "ab", 16)
    spans = [
        _DuckSpan(
            context=_Ctx(trace_id=trace_int, span_id=0x22),
            parent=_Parent(span_id=0x99),  # orphan missing parent
            name="child.llm",
            start_time=1_700_000_000_500_000_000,
            end_time=1_700_000_000_200_000_000,  # negative skew!
            attributes={
                "evalforge.case_id": "duck-1",
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": "ollama/llama3",
                "gen_ai.prompt": "Hello",
                "gen_ai.completion": "World",
            },
            events=[
                _Event(
                    name="exception",
                    timestamp=1_700_000_000_300_000_000,
                    attributes={"exception.message": "Boom Authorization: Bearer tok9999999"},
                )
            ],
            status=_Status(status_code=_StatusCode("ERROR"), description="LLM failed"),
            resource=_Resource(attributes={"service.version": "0.9.0"}),
        )
    ]

    res = ingest_otel_spans(spans)
    assert len(res) == 1
    rec = res[0]
    assert rec.case_id == "duck-1"
    assert rec.elapsed_seconds == 0.0
    assert any("clock skew" in w.lower() for w in rec.warnings)
    assert any("Boom" in err for err in rec.errors)
    assert "tok9999999" not in json.dumps(rec.model_dump(mode="json"))


def test_us2_multi_format_files_correlation_and_replay_adapter(tmp_path: Path) -> None:
    ds = DatasetEngine(
        [
            {"id": "c-alpha", "input": "Explain   SLA  tiers", "reference": "99.9%"},
            {"id": "c-beta", "input": "Who manages keys?", "reference": "Security team"},
        ]
    )

    # 1) Interleaved JSONL span stream with microsecond timestamps and input fallback correlation
    jsonl_path = tmp_path / "interleaved_spans.jsonl"
    rows = [
        {
            "trace_id": "trace-b",
            "span_id": "sb1",
            "name": "agent",
            "start_time": 1_700_000_002_000_000,
            "end_time": 1_700_000_003_000_000,
            "attributes": {
                "app.custom.in": "Who manages keys?",
                "app.custom.out": "Security team",
                "app.custom.tool": "key_lookup",
            },
        },
        {
            "trace_id": "trace-a",
            "span_id": "sa1",
            "name": "agent",
            "start_time": 1_700_000_000_000_000,
            "end_time": 1_700_000_001_500_000,
            "attributes": {
                "app.custom.in": "Explain SLA tiers",
                "app.custom.out": "99.9%",
                "app.custom.docs": [{"id": "d1", "text": "99.9% uptime SLA"}],
            },
        },
    ]
    jsonl_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    ext_cfg = OtelExtractorConfig(
        input_attribute="app.custom.in",
        output_attribute="app.custom.out",
        retrieval_documents_attribute="app.custom.docs",
        timestamp_unit=OtelTimestampUnit.US,
        match_dataset_by_input=True,
    )
    loaded = load_otel_executions(jsonl_path, extractors=ext_cfg, dataset=ds)
    assert [r.case_id for r in loaded] == ["c-beta", "c-alpha"]
    assert loaded[0].elapsed_seconds == pytest.approx(1.0, abs=1e-6)
    alpha = next(r for r in loaded if r.case_id == "c-alpha")
    assert alpha.output == "99.9%"
    assert [c.id for c in alpha.retrieved_chunks] == ["d1"]

    adapter = ReplayAdapter.from_otel_file(
        jsonl_path,
        extractors=ext_cfg,
        dataset=ds,
        system_version="override-sys",
    )
    assert adapter.system_version == "override-sys"
    assert adapter.case_ids == frozenset({"c-alpha", "c-beta"})
    played = asyncio.run(adapter.execute(EvaluationCase(id="c-alpha", input="Explain SLA tiers")))
    assert played.output == "99.9%"

    # 2) Flat JSON array + explicit case_id_map override
    arr_path = tmp_path / "flat_spans.json"
    arr_path.write_text(json.dumps(rows), encoding="utf-8")
    mapped = load_otel_executions(
        arr_path,
        extractors=OtelExtractorConfig(timestamp_unit=OtelTimestampUnit.US),
        case_id_map={"trace-b": "c-beta", "trace-a": "c-alpha"},
    )
    assert {r.case_id for r in mapped} == {"c-alpha", "c-beta"}

    # 3) Explicit failures: missing file, duplicate case_id, missing correlation, corrupt JSON
    with pytest.raises(DatasetError, match="not found"):
        load_otel_executions(tmp_path / "missing.json")

    bad_json = tmp_path / "corrupt.json"
    bad_json.write_text("{broken", encoding="utf-8")
    with pytest.raises(DatasetError):
        load_otel_executions(bad_json)

    dup_payload = [
        {
            "trace_id": "t1",
            "span_id": "s1",
            "name": "a",
            "attributes": {"evalforge.case_id": "dup"},
        },
        {
            "trace_id": "t2",
            "span_id": "s2",
            "name": "a",
            "attributes": {"evalforge.case_id": "dup"},
        },
    ]
    with pytest.raises(AdapterError, match="Duplicate"):
        ingest_otel_spans(dup_payload)

    unlabeled_payload = [
        {"trace_id": "t1", "span_id": "s1", "name": "a", "attributes": {"input.value": "other"}}
    ]
    with pytest.raises(AdapterError, match="case_id"):
        ingest_otel_spans(unlabeled_payload)

    with pytest.raises(AdapterError, match=r"unmatched|ambiguous|case_id"):
        ingest_otel_spans(
            [
                {
                    "trace_id": "t1",
                    "span_id": "s1",
                    "name": "a",
                    "attributes": {"input.value": "unknown question"},
                }
            ],
            extractors=OtelExtractorConfig(match_dataset_by_input=True),
            dataset=ds,
        )
