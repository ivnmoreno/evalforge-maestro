"""Integration tests for decoupled retrieval vs. answer evaluation and M2 end-to-end runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.adapters import DocpipeAdapter, RAGAdapter
from evalforge_maestro.datasets import DatasetEngine, load_docpipe_fixture
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import (
    PrecisionAtKMetric,
    RecallAtKMetric,
    exact_match,
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    normalized_match,
)
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import Metric, MetricStatus, OrchestratorConfig


@pytest.mark.gate_determinism
def test_decoupled_retrieval_vs_answer_scoring_mandatory_and_truncation(
    tmp_path: Path,
) -> None:
    dataset = DatasetEngine(
        [
            {
                "id": "right-ans-bad-ctx",
                "input": "q1",
                "reference": "Paris",
                "expected_context": ["doc-paris-1", "doc-paris-2"],
                "criteria": {"mandatory": True},
            },
            {
                "id": "good-ctx-bad-ans",
                "input": "q2",
                "reference": "Berlin",
                "expected_context": ["doc-berlin-1"],
                "criteria": {"mandatory": False},
            },
        ],
        dataset_id="decoupled-rag",
        dataset_version="1.0",
    )

    large_passage = "A" * 250

    def rag_fn(question: str) -> dict[str, Any]:
        if question == "q1":
            return {
                "answer": "Paris",
                "chunks": [
                    {"id": "irrelevant-99", "text": large_passage},
                    {"id": "irrelevant-100", "text": "short"},
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            }
        return {
            "answer": "Wrong City",
            "chunks": [{"id": "doc-berlin-1", "text": large_passage}],
            "usage": {"prompt_tokens": 18, "completion_tokens": 4, "total_tokens": 22},
        }

    adapter = RAGAdapter(
        rag_fn,
        system_version="rag-decouple-v1",
        model_id="stub-rag",
        config={"top_k": 2},
    )
    metrics: list[Metric] = [
        exact_match,
        normalized_match,
        PrecisionAtKMetric(k=2),
        RecallAtKMetric(k=2),
        mrr,
        ndcg_at_k,
        hit_rate_at_k,
    ]
    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=2, max_context_chars=64, seed=7),
        storage_root=store_root,
    )

    run1 = orch.run(dataset, adapter, metrics, run_id="rag-run-1")
    run2 = orch.run(dataset, adapter, metrics, run_id="rag-run-2")

    by_id = {rec.case_id: rec for rec in run1.case_results}

    # Case 1: Correct answer + irrelevant context -> exact_match PASS (1.0), IR FAIL (0.0)
    c1 = by_id["right-ans-bad-ctx"]
    assert c1.metrics["exact_match"].score == 1.0
    assert c1.metrics["exact_match"].status == MetricStatus.PASS
    assert c1.metrics["normalized_match"].score == 1.0
    for ir_id in ("precision_at_k", "recall_at_k", "mrr", "ndcg_at_k", "hit_rate_at_k"):
        assert c1.metrics[ir_id].score == 0.0
        assert c1.metrics[ir_id].status == MetricStatus.FAIL

    # Mandatory retrieval failure MUST surface on RunRecord despite exact_match=1.0
    assert run1.has_mandatory_failures is True
    assert run1.mandatory_failed_case_ids == ["right-ans-bad-ctx"]

    # Case 2: Relevant context + incorrect answer -> retrieval PASS (p@2=0.5), exact_match FAIL
    c2 = by_id["good-ctx-bad-ans"]
    assert c2.metrics["exact_match"].score == 0.0
    assert c2.metrics["exact_match"].status == MetricStatus.FAIL
    assert c2.metrics["precision_at_k"].score == 0.5
    assert c2.metrics["precision_at_k"].status == MetricStatus.PASS
    assert c2.metrics["recall_at_k"].score == 1.0
    assert c2.metrics["recall_at_k"].status == MetricStatus.PASS
    assert c2.metrics["mrr"].score == 1.0
    assert c2.metrics["ndcg_at_k"].score == 1.0
    assert c2.metrics["hit_rate_at_k"].score == 1.0

    # Post-scoring max_context_chars truncation trims stored chunk texts without altering scores
    assert c1.execution.truncated is True
    assert len(c1.execution.retrieved_chunks[0].text) == 64
    assert c2.execution.truncated is True
    assert len(c2.execution.retrieved_chunks[0].text) == 64

    # Determinism across repeated runs & clean persistence reload
    assert run1.aggregates == run2.aggregates
    assert LocalRunStore(store_root).load_run("rag-run-1") == run1


@dataclass
class _StubChunk:
    id: str
    text: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None


@dataclass
class _StubGenResult:
    text: str
    model: str = "stub-dp"
    finish_reason: str = "stop"
    truncated: bool = False
    prompt_tokens: int = 10
    completion_tokens: int = 4
    total_tokens: int = 14


class _StubDocpipePipeline:
    def retrieve(self, question: str, **_: Any) -> list[_StubChunk]:
        if "config" in question:
            return [_StubChunk(id="cfg-1", text="Config precedence", parent_id="doc-cfg")]
        return [_StubChunk(id="other-1", text="Unrelated", parent_id="doc-other")]

    def build_prompt(self, question: str, sections: list[_StubChunk]) -> str:
        return f"Q: {question}\n" + "\n".join(s.text for s in sections)

    def answer_detailed(self, prompt: Any, **_: Any) -> _StubGenResult:
        if "Config precedence" in str(prompt):
            return _StubGenResult(text="CLI > Env > TOML")
        return _StubGenResult(text="Unknown")


def test_docpipe_fixture_and_adapter_end_to_end_persistence(tmp_path: Path) -> None:
    fixture_file = tmp_path / "docpipe_suite.json"
    fixture_file.write_text(
        json.dumps(
            {
                "collection": "handbook",
                "profile": "hybrid",
                "queries": [
                    {
                        "question": "What is the config order?",
                        "relevant_ids": ["cfg-1"],
                        "reference": "CLI > Env > TOML",
                        "notes": "core setting check",
                    },
                    {
                        "question": "Unmatched question",
                        "relevant_ids": ["missing-1"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    dataset = load_docpipe_fixture(fixture_file, dataset_version="0.3")
    pipeline = _StubDocpipePipeline()
    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=2, seed=11),
        storage_root=store_root,
    )

    # 1. retrieve-only run: retrieval metrics score; exact_match is NOT_APPLICABLE when ref=None,
    #    or FAIL (0.0) when case.reference is present and output=None.
    ret_run = orch.run(
        dataset,
        DocpipeAdapter(mode="retrieve", collection="handbook", client=pipeline),
        [exact_match, hit_rate_at_k, RecallAtKMetric(k=1)],
        run_id="dp-retrieve",
    )
    store = LocalRunStore(store_root)
    assert store.load_run("dp-retrieve") == ret_run
    ret_by_id = {r.case_id: r for r in ret_run.case_results}
    assert ret_by_id["case-1"].execution.output is None
    assert ret_by_id["case-1"].metrics["hit_rate_at_k"].score == 1.0
    assert ret_by_id["case-1"].metrics["exact_match"].score == 0.0
    assert ret_by_id["case-2"].metrics["exact_match"].status == MetricStatus.NOT_APPLICABLE

    # 2. answer_detailed full RAG run saved immutably to LocalRunStore
    ans_run = orch.run(
        dataset,
        DocpipeAdapter(mode="answer_detailed", collection="handbook", client=pipeline),
        [exact_match, hit_rate_at_k, mrr],
        run_id="dp-answer",
    )
    reloaded_ans = store.load_run("dp-answer")
    assert reloaded_ans == ans_run
    ans_by_id = {r.case_id: r for r in reloaded_ans.case_results}
    assert ans_by_id["case-1"].execution.output == "CLI > Env > TOML"
    assert ans_by_id["case-1"].execution.tokens is not None
    assert ans_by_id["case-1"].execution.tokens.total_tokens == 14
    assert ans_by_id["case-1"].metrics["exact_match"].score == 1.0
    assert ans_by_id["case-1"].metrics["hit_rate_at_k"].score == 1.0
    assert len(store.read_manifest()) == 2
