"""Unit tests for lazy DocpipeAdapter and dependency-free docpipe fixture importer."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import REDACTED_VALUE, canonical_sha256
from evalforge_maestro.adapters import DocpipeAdapter
from evalforge_maestro.datasets import DatasetEngine, load_docpipe_fixture
from evalforge_maestro.exceptions import (
    AdapterError,
    DatasetError,
    EmptyDatasetError,
    MissingExtraError,
)
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import exact_match
from evalforge_maestro.types import (
    EvaluationCase,
    ExpectedContextItem,
    OrchestratorConfig,
    TargetAdapter,
    TokenUsage,
)


@dataclass
class _SimDocpipeChunk:
    id: str
    text: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    vector: list[float] | None = None


@dataclass
class _SimGenerationResult:
    text: str
    model: str = "gpt-4o-mini"
    finish_reason: str = "stop"
    truncated: bool = False
    prompt_tokens: int | None = 30
    completion_tokens: int | None = 12
    reasoning_tokens: int | None = 2
    total_tokens: int | None = 44
    elapsed_seconds: float = 0.08


class _SimDocpipeClient:
    def __init__(self, *, truncate: bool = False, empty_chunks: bool = False) -> None:
        self.retrieve_calls: list[tuple[str, dict[str, Any]]] = []
        self.answer_calls: list[tuple[Any, dict[str, Any]]] = []
        self._truncate = truncate
        self._empty_chunks = empty_chunks

    def retrieve(self, question: str, **kwargs: Any) -> list[_SimDocpipeChunk]:
        self.retrieve_calls.append((question, kwargs))
        if self._empty_chunks:
            return []
        return [
            _SimDocpipeChunk(
                id="sec-1",
                text="Chunk one body",
                parent_id="doc-alpha",
                metadata={"page": 1, "api_key": "leaked-key"},
                score=0.91,
                vector=[0.1, 0.2],
            ),
            _SimDocpipeChunk(
                id="sec-2",
                text="Chunk two body",
                parent_id=None,
                metadata={"page": 2},
                score=0.77,
            ),
        ]

    def build_chat_messages(
        self, question: str, sections: list[_SimDocpipeChunk]
    ) -> list[dict[str, str]]:
        ctx = "\n".join(s.text for s in sections)
        return [{"role": "user", "content": f"{question}\n{ctx}"}]

    def answer_detailed(self, prompt: Any, **kwargs: Any) -> _SimGenerationResult:
        self.answer_calls.append((prompt, kwargs))
        if self._truncate:
            return _SimGenerationResult(
                text="Partial output",
                finish_reason="length",
                truncated=True,
                prompt_tokens=50,
                completion_tokens=20,
                reasoning_tokens=None,
                total_tokens=70,
            )
        return _SimGenerationResult(text="Grounded docpipe answer")


def test_docpipe_adapter_missing_extra_and_validation() -> None:
    assert "docpipe_maestro" not in sys.modules

    with pytest.raises(MissingExtraError) as exc_info:
        DocpipeAdapter()
    assert exc_info.value.extra == "docpipe-maestro"
    assert exc_info.value.package == "docpipe-maestro"
    assert "[docpipe-maestro]" in str(exc_info.value)

    with pytest.raises(AdapterError):
        DocpipeAdapter(mode="invalid", client=_SimDocpipeClient())  # type: ignore[arg-type]

    with pytest.raises(AdapterError):
        DocpipeAdapter(client=object())


def test_docpipe_adapter_retrieve_and_answer_detailed_modes(tmp_path: Path) -> None:
    client = _SimDocpipeClient()
    persist = tmp_path / "chroma"
    case = EvaluationCase(id="c1", input="How does chunking work?")

    async def _run() -> None:
        ret_adapter = DocpipeAdapter(
            mode="retrieve",
            collection="explicit-col",
            persist_dir=persist,
            retrieve_kwargs={"collection": "overridden-col", "k": 3, "token": "secret-tok"},
            client=client,
        )
        assert isinstance(ret_adapter, TargetAdapter)
        ret_res = await ret_adapter.execute(case)
        assert ret_res.output is None
        assert ret_res.tokens is None
        assert ret_res.errors == []
        assert len(ret_res.retrieved_chunks) == 2
        assert ret_res.retrieved_chunks[0].id == "sec-1"
        assert ret_res.retrieved_chunks[0].parent_id == "doc-alpha"
        assert ret_res.retrieved_chunks[0].rank == 1
        assert ret_res.retrieved_chunks[0].metadata["api_key"] == REDACTED_VALUE
        assert "leaked-key" not in str(ret_res.retrieved_chunks)
        assert "secret-tok" not in str(ret_res.adapter_metadata)
        # Explicit collection & persist_dir override retrieve_kwargs keys
        _, call_kwargs = client.retrieve_calls[0]
        assert call_kwargs["collection"] == "explicit-col"
        assert call_kwargs["persist_dir"] == str(persist)
        assert call_kwargs["k"] == 3
        expected_fp_cfg = {
            "mode": "retrieve",
            "collection": "explicit-col",
            "persist_dir": str(persist),
            "retrieve_kwargs": {
                "collection": "explicit-col",
                "k": 3,
                "token": REDACTED_VALUE,
                "persist_dir": str(persist),
            },
            "answer_kwargs": {},
        }
        assert ret_res.config_fingerprint == canonical_sha256(expected_fp_cfg)

        # Full answer_detailed mode
        ans_adapter = DocpipeAdapter(
            mode="answer_detailed",
            collection="docs",
            answer_kwargs={"model": "gpt-4o-mini", "api_key": "sk-secret"},
            system_version="dp-0.3",
            client=client,
        )
        ans_res = await ans_adapter.execute(EvaluationCase(id="c2", input={"question": "Explain?"}))
        assert ans_res.output == "Grounded docpipe answer"
        assert ans_res.tokens == TokenUsage(
            prompt_tokens=30,
            completion_tokens=12,
            reasoning_tokens=2,
            total_tokens=44,
        )
        assert ans_res.model_id == "gpt-4o-mini"
        assert ans_res.system_version == "dp-0.3"
        assert ans_res.truncated is False
        assert client.answer_calls[0][1]["has_context"] is True
        assert "sk-secret" not in str(ans_res.adapter_metadata)

        # Truncation warning & dict input / bad input isolation
        trunc_client = _SimDocpipeClient(truncate=True, empty_chunks=True)
        trunc_adapter = DocpipeAdapter(client=trunc_client)
        trunc_res = await trunc_adapter.execute(EvaluationCase(id="c3", input={"query": "Q"}))
        assert trunc_res.truncated is True
        assert trunc_res.warnings
        assert trunc_client.answer_calls[0][1]["has_context"] is False

        bad_input_res = await trunc_adapter.execute(EvaluationCase(id="c4", input={"bad": 123}))
        assert bad_input_res.output is None
        assert len(bad_input_res.errors) == 1

    asyncio.run(_run())


def test_load_docpipe_fixture_shapes_synthetic_ids_metadata_and_errors(tmp_path: Path) -> None:
    assert "docpipe_maestro" not in sys.modules

    # 1. docpipe-maestro EvalFixture JSON ("queries" envelope without explicit id)
    eval_fixture = tmp_path / "docpipe_eval.json"
    eval_fixture.write_text(
        json.dumps(
            {
                "collection": "company-docs",
                "profile": "hybrid",
                "queries": [
                    {
                        "question": "How is config validated?",
                        "relevant_ids": ["chunk-1", "chunk-2"],
                        "notes": "core onboarding question",
                    },
                    {
                        "id": "custom-q2",
                        "question": "Where are metrics defined?",
                        "relevant_ids": ["chunk-3"],
                        "relevance": {"chunk-3": 3},
                        "reference": "metrics/retrieval.py",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    ds_eval = load_docpipe_fixture(eval_fixture, dataset_version="0.3")
    cases = list(ds_eval.iter_cases())
    assert [c.id for c in cases] == ["case-1", "custom-q2"]
    assert cases[0].input == "How is config validated?"
    assert cases[0].reference is None
    assert cases[0].expected_context == ["chunk-1", "chunk-2"]
    assert cases[0].metadata.source == "company-docs"
    assert cases[0].metadata.extra == {
        "collection": "company-docs",
        "profile": "hybrid",
        "notes": "core onboarding question",
    }
    assert cases[1].expected_context == [ExpectedContextItem(id="chunk-3", relevance=3)]
    assert cases[1].reference == "metrics/retrieval.py"

    # Deterministic SHA-256 fingerprint via DatasetEngine.from_docpipe_fixture
    ds_eval_again = DatasetEngine.from_docpipe_fixture(eval_fixture, dataset_version="0.3")
    assert (
        ds_eval.fingerprint().dataset_fingerprint == ds_eval_again.fingerprint().dataset_fingerprint
    )

    # 2. JSON array file, "cases" / "items" envelopes, and JSONL file
    arr_path = tmp_path / "arr.json"
    arr_path.write_text(
        json.dumps(
            [{"query": "Q1", "expected_ids": ["e1"]}, {"input": "Q2", "expected_context": ["e2"]}]
        ),
        encoding="utf-8",
    )
    assert [c.id for c in load_docpipe_fixture(arr_path).iter_cases()] == ["case-1", "case-2"]

    assert (
        len(
            list(
                load_docpipe_fixture(
                    {"items": [{"case_id": "it-1", "question": "Hi", "relevant_ids": ["c9"]}]}
                ).iter_cases()
            )
        )
        == 1
    )
    cases_engine = load_docpipe_fixture(
        {"cases": [{"id": "cs-1", "input": "Hello", "expected_context": ["c1"]}]}
    )
    assert next(cases_engine.iter_cases()).id == "cs-1"

    jsonl_path = tmp_path / "stream.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps({"question": "Line 1", "relevant_ids": ["a"]}),
                json.dumps({"question": "Line 2", "relevant_ids": ["b"]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert len(list(load_docpipe_fixture(jsonl_path).iter_cases())) == 2

    # 3. Error cases & defensive parsing branches
    empty_path = tmp_path / "empty.json"
    empty_path.write_text("[]", encoding="utf-8")
    with pytest.raises(EmptyDatasetError):
        load_docpipe_fixture(empty_path)

    whitespace_path = tmp_path / "blank.jsonl"
    whitespace_path.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(EmptyDatasetError):
        load_docpipe_fixture(whitespace_path)

    with pytest.raises(DatasetError):
        load_docpipe_fixture(tmp_path / "does_not_exist.json")

    with pytest.raises(DatasetError):
        load_docpipe_fixture(tmp_path)  # directory triggers OSError

    bad_jsonl1 = tmp_path / "bad1.jsonl"
    bad_jsonl1.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(DatasetError):
        load_docpipe_fixture(bad_jsonl1)

    bad_jsonl2 = tmp_path / "bad2.jsonl"
    bad_jsonl2.write_text('{"question": "ok"}\n123\n', encoding="utf-8")
    with pytest.raises(DatasetError):
        load_docpipe_fixture(bad_jsonl2)

    single_jsonl = tmp_path / "single.jsonl"
    single_jsonl.write_text(
        '\n{"question": "Single row?", "relevant_ids": ["s1"], "relevance": [2], '
        '"criteria": {"mandatory": true}, "metadata": {"domain": "rag"}}\n',
        encoding="utf-8",
    )
    single_cases = list(load_docpipe_fixture(single_jsonl).iter_cases())
    assert single_cases[0].expected_context == [ExpectedContextItem(id="s1", relevance=2)]
    assert single_cases[0].criteria.mandatory is True
    assert single_cases[0].metadata.domain == "rag"

    scalar_path = tmp_path / "scalar.json"
    scalar_path.write_text('"not-a-container"', encoding="utf-8")
    with pytest.raises(DatasetError):
        load_docpipe_fixture(scalar_path)

    with pytest.raises(DatasetError):
        load_docpipe_fixture({"unexpected_key": []})

    with pytest.raises(DatasetError):
        load_docpipe_fixture({"queries": "not-a-list"})

    with pytest.raises(DatasetError):
        load_docpipe_fixture(["not-a-mapping"])  # type: ignore[list-item]

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"relevant_ids": ["missing-question"]}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"id": "", "question": "Q"}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "collection": 123}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "relevant_ids": "bad-str"}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "relevant_ids": ["a"], "relevance": 99}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "relevant_ids": ["a"], "relevance": [1, 2]}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "relevant_ids": ["a"], "relevance": {"a": -1}}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "metadata": "not-dict"}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q", "expected_context": ["a", "a"]}])

    from evalforge_maestro.exceptions import DuplicateCaseIdError

    with pytest.raises(DuplicateCaseIdError):
        load_docpipe_fixture([{"id": "dup", "question": "Q1"}, {"id": "dup", "question": "Q2"}])

    with pytest.raises(DatasetError):
        load_docpipe_fixture([{"question": "Q"}], dataset_id="   ")


def test_docpipe_adapter_lazy_module_resolution_and_edge_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    sim_client = _SimDocpipeClient()
    fake_pkg = types.ModuleType("docpipe_maestro")
    fake_query = types.ModuleType("docpipe_maestro.query")
    fake_ret = types.ModuleType("docpipe_maestro.query.retriever")
    fake_ans = types.ModuleType("docpipe_maestro.query.answer")
    fake_prm = types.ModuleType("docpipe_maestro.query.prompts")
    fake_ret.retrieve = sim_client.retrieve  # type: ignore[attr-defined]
    fake_ans.answer_detailed = sim_client.answer_detailed  # type: ignore[attr-defined]
    fake_prm.build_chat_messages = sim_client.build_chat_messages  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "docpipe_maestro", fake_pkg)
    monkeypatch.setitem(sys.modules, "docpipe_maestro.query", fake_query)
    monkeypatch.setitem(sys.modules, "docpipe_maestro.query.retriever", fake_ret)
    monkeypatch.setitem(sys.modules, "docpipe_maestro.query.answer", fake_ans)
    monkeypatch.setitem(sys.modules, "docpipe_maestro.query.prompts", fake_prm)

    adapter = DocpipeAdapter(mode="answer_detailed", collection="mod-col", model_id="m-top")
    assert adapter.model_id == "m-top"
    assert adapter.system_version is None
    assert adapter.config_fingerprint is not None

    # Client missing answer_detailed fails in answer_detailed mode
    class _RetrieveOnlyClient:
        def retrieve(self, question: str, **_: Any) -> list[dict[str, Any]]:
            return [{"id": "r1", "text": question}]

    with pytest.raises(AdapterError):
        DocpipeAdapter(mode="answer_detailed", client=_RetrieveOnlyClient())

    # Top-level module export fallback (retrieve/build_prompt directly on docpipe_maestro)
    top_pkg = types.ModuleType("docpipe_maestro")
    top_pkg.retrieve = sim_client.retrieve  # type: ignore[attr-defined]
    top_pkg.answer_detailed = sim_client.answer_detailed  # type: ignore[attr-defined]
    top_pkg.build_prompt = lambda q, secs: f"{q}:{len(secs)}"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docpipe_maestro", top_pkg)
    top_adapter = DocpipeAdapter(mode="answer_detailed")

    async def _run() -> None:
        res = await adapter.execute(EvaluationCase(id="lazy-1", input="Test lazy submodule bridge"))
        assert res.output == "Grounded docpipe answer"
        assert res.model_id == "m-top"
        assert sim_client.retrieve_calls[0][1]["collection"] == "mod-col"

        top_res = await top_adapter.execute(EvaluationCase(id="top-1", input="Top level"))
        assert top_res.output == "Grounded docpipe answer"

        # Client with build_prompt fallback, retrieve=None, retrieve="bad", and empty str input
        class _MinClient:
            async def retrieve(self, question: str, **_: Any) -> Any:
                if question == "none":
                    return None
                if question == "bad-seq":
                    return "not-a-sequence"
                return [{"id": "m1", "text": question}]

            def build_prompt(self, question: str, sections: Any) -> str:
                return f"prompt:{question}:{len(sections or [])}"

            async def answer_detailed(self, prompt: Any, **_: Any) -> dict[str, Any]:
                return {"text": f"dict:{prompt}", "prompt_tokens": 2, "completion_tokens": 1}

        min_res = await DocpipeAdapter(client=_MinClient()).execute(
            EvaluationCase(id="lazy-2", input="direct")
        )
        assert min_res.output == "dict:prompt:direct:1"
        assert min_res.tokens == TokenUsage(prompt_tokens=2, completion_tokens=1)

        none_res = await DocpipeAdapter(mode="retrieve", client=_MinClient()).execute(
            EvaluationCase(id="lazy-none", input="none")
        )
        assert none_res.retrieved_chunks == []

        bad_seq_res = await DocpipeAdapter(mode="retrieve", client=_MinClient()).execute(
            EvaluationCase(id="lazy-bad-seq", input="bad-seq")
        )
        assert len(bad_seq_res.errors) == 1

        empty_in_res = await DocpipeAdapter(mode="retrieve", client=_MinClient()).execute(
            EvaluationCase(id="lazy-empty-in", input="   ")
        )
        assert len(empty_in_res.errors) == 1

    asyncio.run(_run())


def test_docpipe_adapter_runs_concurrent_live_retrieve_and_guards_local_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = threading.Barrier(4, timeout=2.0)

    def fake_retrieve(question: str, **_: Any) -> list[_SimDocpipeChunk]:
        barrier.wait()
        return [_SimDocpipeChunk(id="c1", text=f"ctx:{question}")]

    fake_retrieve.__module__ = "docpipe_maestro.query.retriever"

    def fake_build_chat(q: str, sections: Any) -> list[dict[str, str]]:
        return [{"role": "user", "content": f"{q}:{len(sections)}"}]

    def fake_answer(prompt: Any, **_: Any) -> _SimGenerationResult:
        return _SimGenerationResult(text=f"ok:{prompt[0]['content']}")

    fake_pkg = types.ModuleType("docpipe_maestro")
    fake_pkg.retrieve = fake_retrieve  # type: ignore[attr-defined]
    fake_pkg.build_chat_messages = fake_build_chat  # type: ignore[attr-defined]
    fake_pkg.answer_detailed = fake_answer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docpipe_maestro", fake_pkg)

    adapter = DocpipeAdapter(mode="answer_detailed", collection="smoke")
    ds = DatasetEngine(
        [{"id": f"c{i}", "input": f"q{i}", "reference": f"ok:q{i}:1"} for i in range(4)]
    )
    run = EvaluationOrchestrator(config=OrchestratorConfig(max_concurrency=4)).run(
        ds, adapter, [exact_match]
    )
    assert run.aggregates["exact_match"].pass_count == 4

    # Restricted signature without local_only parameter drops local_only safely
    def legacy_retrieve(question: str, *, collection: str = "default") -> list[_SimDocpipeChunk]:
        return [_SimDocpipeChunk(id=collection, text=question)]

    legacy_retrieve.__module__ = "docpipe_maestro.query.retriever"

    def legacy_answer(prompt: Any, *, has_context: bool = True) -> _SimGenerationResult:
        del prompt, has_context
        return _SimGenerationResult(text="legacy-ok")

    legacy_pkg = types.ModuleType("docpipe_maestro")
    legacy_pkg.retrieve = legacy_retrieve  # type: ignore[attr-defined]
    legacy_pkg.build_chat_messages = fake_build_chat  # type: ignore[attr-defined]
    legacy_pkg.answer_detailed = legacy_answer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docpipe_maestro", legacy_pkg)

    legacy_adapter = DocpipeAdapter(
        mode="answer_detailed",
        collection="legacy",
        retrieve_kwargs={"local_only": True},
        answer_kwargs={"local_only": True},
    )
    legacy_res = asyncio.run(legacy_adapter.execute(EvaluationCase(id="leg-1", input="hello")))
    assert legacy_res.errors == []
    assert legacy_res.output == "legacy-ok"


def test_docpipe_adapter_0_5_0_hybrid_rerank_and_answer_detailed_contract(
    tmp_path: Path,
) -> None:
    """Verify DocpipeAdapter contract for docpipe-maestro>=0.5.0 hybrid+rerank options."""
    client = _SimDocpipeClient()
    persist_dir = tmp_path / "docpipe-chroma"
    adapter = DocpipeAdapter(
        mode="answer_detailed",
        collection="docs",
        persist_dir=persist_dir,
        retrieve_kwargs={
            "top_k": 4,
            "searcher": "fts5_hybrid",
            "rerank": True,
            "api_key": "dp-secret-token",
        },
        answer_kwargs={"model": "gpt-4o-mini", "api_key": "ans-secret-token"},
        system_version="docpipe-maestro-0.5.0",
        client=client,
    )
    res = asyncio.run(
        adapter.execute(EvaluationCase(id="dp-050", input="How does hybrid reranking work?"))
    )
    assert res.errors == []
    assert res.output == "Grounded docpipe answer"
    assert res.system_version == "docpipe-maestro-0.5.0"
    assert res.model_id == "gpt-4o-mini"
    assert len(res.retrieved_chunks) == 2
    assert res.tokens == TokenUsage(
        prompt_tokens=30,
        completion_tokens=12,
        reasoning_tokens=2,
        total_tokens=44,
    )
    _, ret_kwargs = client.retrieve_calls[0]
    assert ret_kwargs["collection"] == "docs"
    assert ret_kwargs["persist_dir"] == str(persist_dir)
    assert ret_kwargs["top_k"] == 4
    assert ret_kwargs["searcher"] == "fts5_hybrid"
    assert ret_kwargs["rerank"] is True
    assert "dp-secret-token" not in str(res.adapter_metadata)
    assert "ans-secret-token" not in str(res.adapter_metadata)
    assert "leaked-key" not in str(res.retrieved_chunks)
