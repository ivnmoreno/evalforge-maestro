"""Unit tests for configurable protocol-based RAGAdapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from evalforge_maestro._canonical import REDACTED_VALUE, canonical_sha256
from evalforge_maestro.adapters import RAGAdapter
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import (
    EvaluationCase,
    RAGExtractorConfig,
    RetrievedChunk,
    TargetAdapter,
    TokenUsage,
)


@dataclass
class _ObjChunk:
    doc_id: str
    content: str
    meta: dict[str, Any]
    sim: float
    pos: int | None = None


@dataclass
class _ObjUsage:
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _ObjRagResponse:
    generated: dict[str, Any]
    evidence: list[_ObjChunk]
    stats: _ObjUsage


def test_rag_adapter_sync_async_awaitable_and_default_fallbacks() -> None:
    case = EvaluationCase(id="c1", input="What is EvalForge?")

    def sync_rag(query: str) -> dict[str, Any]:
        return {
            "answer": f"Summary for {query}",
            "chunks": [
                {
                    "id": "ch-1",
                    "text": "EvalForge evaluates RAG pipelines.",
                    "parent_id": "doc-1",
                    "score": 0.92,
                    "metadata": {"source": "readme", "api_key": "secret-123"},
                },
                {
                    "chunk_id": "ch-2",
                    "page_content": "Evidence decoupled from output.",
                    "metadata": {"parent_id": "doc-2", "bearer": "tok-xyz"},
                },
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    async def async_rag(query: str) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        return {
            "response": f"Async:{query}",
            "retrieved_chunks": [RetrievedChunk(id="rc-1", text="body", score=0.5)],
            "tokens": TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        }

    def awaitable_rag(c: EvaluationCase) -> Any:
        async def _inner() -> dict[str, Any]:
            return {
                "output": f"Case:{c.id}",
                "contexts": [{"doc_id": "d-1", "content": "ctx", "rank": 3}],
                "token_usage": {"input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
            }

        return _inner()

    async def _run() -> None:
        adapter = RAGAdapter(
            sync_rag,
            system_version="rag-v1",
            model_id="gpt-test",
            config={"top_k": 2, "api_key": "sk-top-secret"},
        )
        assert isinstance(adapter, TargetAdapter)
        res = await adapter.execute(case)
        assert res.case_id == "c1"
        assert res.output == "Summary for What is EvalForge?"
        assert res.errors == []
        assert res.system_version == "rag-v1"
        assert res.model_id == "gpt-test"
        assert res.config_fingerprint == canonical_sha256({"top_k": 2, "api_key": REDACTED_VALUE})
        assert "sk-top-secret" not in str(res.adapter_metadata)
        assert "secret-123" not in str(res.retrieved_chunks)
        assert "tok-xyz" not in str(res.retrieved_chunks)

        assert len(res.retrieved_chunks) == 2
        assert res.retrieved_chunks[0].id == "ch-1"
        assert res.retrieved_chunks[0].parent_id == "doc-1"
        assert res.retrieved_chunks[0].rank == 1
        assert res.retrieved_chunks[0].score == 0.92
        assert res.retrieved_chunks[0].metadata["api_key"] == REDACTED_VALUE
        assert res.retrieved_chunks[1].id == "ch-2"
        assert res.retrieved_chunks[1].parent_id == "doc-2"
        assert res.retrieved_chunks[1].rank == 2
        assert res.tokens == TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        async_res = await RAGAdapter(async_rag).execute(case)
        assert async_res.output == "Async:What is EvalForge?"
        assert async_res.retrieved_chunks[0].rank == 1
        assert async_res.tokens is not None and async_res.tokens.total_tokens == 5

        awaitable_res = await RAGAdapter(awaitable_rag, pass_case=True).execute(case)
        assert awaitable_res.output == "Case:c1"
        assert awaitable_res.retrieved_chunks[0].rank == 3
        assert awaitable_res.tokens == TokenUsage(
            prompt_tokens=4, completion_tokens=6, total_tokens=10
        )

    asyncio.run(_run())


def test_rag_adapter_nested_paths_callable_extractors_and_error_isolation() -> None:
    case = EvaluationCase(id="c2", input="question", metadata={"domain": "docs"})  # type: ignore[arg-type]

    def object_rag(payload: str) -> _ObjRagResponse:
        assert payload == "docs:question"
        return _ObjRagResponse(
            generated={"text": "Structured object answer"},
            evidence=[
                _ObjChunk(
                    doc_id="obj-1",
                    content="Object text",
                    meta={"parent": "p-9", "token": "secret-tok"},
                    sim=0.88,
                    pos=2,
                ),
                _ObjChunk(
                    doc_id="obj-2",
                    content="Second object text",
                    meta={"parent": "p-9"},
                    sim=0.41,
                    pos=None,
                ),
            ],
            stats=_ObjUsage(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        )

    extractors = RAGExtractorConfig(
        output="generated.text",
        chunks=lambda resp: resp.evidence,
        chunk_id="doc_id",
        chunk_text=lambda ch: ch.content.upper(),
        chunk_parent_id="meta.parent",
        chunk_rank="pos",
        chunk_score="sim",
        chunk_metadata="meta",
        tokens="stats",
    )

    async def _run() -> None:
        adapter = RAGAdapter(
            object_rag,
            extractors=extractors,
            input_mapper=lambda c: f"{c.metadata.domain}:{c.input}",
        )
        res = await adapter.execute(case)
        assert res.errors == []
        assert res.output == "Structured object answer"
        assert len(res.retrieved_chunks) == 2
        assert res.retrieved_chunks[0].id == "obj-1"
        assert res.retrieved_chunks[0].text == "OBJECT TEXT"
        assert res.retrieved_chunks[0].parent_id == "p-9"
        assert res.retrieved_chunks[0].rank == 2
        assert res.retrieved_chunks[0].score == 0.88
        assert res.retrieved_chunks[0].metadata["token"] == REDACTED_VALUE
        # When pos=None on 2nd element, auto 1-based fallback assigns sequential index 2
        assert res.retrieved_chunks[1].rank == 2
        assert res.tokens == TokenUsage(
            prompt_tokens=12, completion_tokens=8, reasoning_tokens=0, total_tokens=20
        )

        # Target exception isolation
        boom = RAGAdapter(lambda _: (_ for _ in ()).throw(RuntimeError("rag down")))
        boom_res = await boom.execute(case)
        assert boom_res.output is None
        assert boom_res.retrieved_chunks == []
        assert len(boom_res.errors) == 1
        assert "RuntimeError: rag down" in boom_res.errors[0]

        # Strict explicit extractor path missing on payload -> error captured cleanly
        bad_path = RAGAdapter(
            lambda _: {"answer": "ok", "chunks": []},
            extractors=RAGExtractorConfig(output="missing.nested.key"),
        )
        bad_path_res = await bad_path.execute(case)
        assert bad_path_res.output is None
        assert len(bad_path_res.errors) == 1
        assert "missing.nested.key" in bad_path_res.errors[0]

        # Non-JSON-serializable output -> error captured cleanly without crashing
        bad_out = RAGAdapter(lambda _: {"output": object(), "chunks": []})
        bad_out_res = await bad_out.execute(case)
        assert bad_out_res.output is None
        assert len(bad_out_res.errors) == 1

    asyncio.run(_run())

    with pytest.raises(AdapterError):
        RAGAdapter("not-callable")  # type: ignore[arg-type]

    with pytest.raises(AdapterError):
        RAGAdapter(lambda x: x, pass_case=True, input_mapper=lambda c: c.input)


def test_rag_adapter_edge_payloads_and_error_branches() -> None:
    case = EvaluationCase(id="edge-1", input="query")

    async def _run() -> None:
        # chunks=None -> empty chunks, metadata=None -> {}, empty dict tokens -> empty TokenUsage
        res_none = await RAGAdapter(
            lambda _: {"answer": "ok", "chunks": None, "tokens": {}},
        ).execute(case)
        assert res_none.errors == []
        assert res_none.retrieved_chunks == []
        assert res_none.tokens == TokenUsage()

        # chunk_metadata=None -> {}, explicit property getters checked
        adapter_meta = RAGAdapter(
            lambda _: {
                "output": "ok",
                "chunks": [{"id": "c1", "text": "body", "metadata": None}],
            },
            system_version="sv",
            model_id="mid",
        )
        assert adapter_meta.system_version == "sv"
        assert adapter_meta.model_id == "mid"
        assert adapter_meta.config_fingerprint is None
        res_meta = await adapter_meta.execute(case)
        assert res_meta.retrieved_chunks[0].metadata == {}

        # Attribute-path property access on nested non-mapping object when path missing -> error
        class _Dummy:
            pass

        missing_attr_res = await RAGAdapter(
            lambda _: _Dummy(),
            extractors=RAGExtractorConfig(chunks="missing.attr"),
        ).execute(case)
        assert len(missing_attr_res.errors) == 1

        # Non-sequence chunks -> error captured
        bad_chunks_res = await RAGAdapter(
            lambda _: {"answer": "ok", "chunks": "not-a-sequence"},
        ).execute(case)
        assert len(bad_chunks_res.errors) == 1

        # Non-mapping chunk metadata -> error captured
        bad_meta_res = await RAGAdapter(
            lambda _: {"chunks": [{"id": "c1", "text": "t", "metadata": "bad"}]},
        ).execute(case)
        assert len(bad_meta_res.errors) == 1

        # Invalid TokenUsage payloads (str or object lacking usage fields) -> error captured
        for bad_tok in ("bad-tokens", object()):
            bad_tok_res = await RAGAdapter(
                lambda _, tok=bad_tok: {"answer": "ok", "chunks": [], "tokens": tok},
            ).execute(case)
            assert len(bad_tok_res.errors) == 1

        # Missing required fallback (chunk missing id) -> error captured
        missing_id_res = await RAGAdapter(
            lambda _: {"chunks": [{"text": "orphan text"}]},
        ).execute(case)
        assert len(missing_id_res.errors) == 1

    asyncio.run(_run())
