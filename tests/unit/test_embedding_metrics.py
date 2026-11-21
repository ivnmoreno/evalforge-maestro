"""Unit tests for lazy embedding cosine similarity metrics and fail-fast extra checks."""

from __future__ import annotations

import asyncio
import importlib.util
import math
import sys
import types as py_types
from collections.abc import Sequence
from typing import Any

import pytest

from evalforge_maestro.embeddings import (
    ContextEmbeddingSimilarityMetric,
    EmbeddingSimilarityMetric,
)
from evalforge_maestro.exceptions import MissingExtraError
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.regression import detect_drift
from evalforge_maestro.reporting import detect_decoupled_evidence
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    CaseCriteria,
    CaseEvaluationRecord,
    DriftCategory,
    EmbeddingAggregation,
    EmbeddingConfig,
    EvaluationCase,
    EvidenceDecouplingCategory,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RetrievedChunk,
)


def _ensure_numpy_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a lightweight stdlib numpy shim when [embeddings] is absent in dev CI."""
    if importlib.util.find_spec("numpy") is not None:
        return

    class _Vector:
        def __init__(self, data: Sequence[float]) -> None:
            self._data = [float(x) for x in data]

        @property
        def ndim(self) -> int:
            return 1

        @property
        def shape(self) -> tuple[int, ...]:
            return (len(self._data),)

        def __len__(self) -> int:
            return len(self._data)

        def __iter__(self) -> Any:
            return iter(self._data)

        def __getitem__(self, idx: int) -> float:
            return self._data[idx]

        def __setitem__(self, idx: int, value: float) -> None:
            self._data[idx] = float(value)

        def __truediv__(self, scalar: float) -> _Vector:
            s = float(scalar)
            return _Vector([x / s for x in self._data])

        def tolist(self) -> list[float]:
            return list(self._data)

    class _IsFiniteResult:
        def __init__(self, flags: list[bool]) -> None:
            self._flags = flags

        def all(self) -> bool:
            return all(self._flags)

    fake_np = py_types.ModuleType("numpy")
    fake_np.float64 = float  # type: ignore[attr-defined]
    fake_np.ndarray = _Vector  # type: ignore[attr-defined]

    def _zeros(n: int, dtype: Any = float) -> _Vector:
        _ = dtype
        return _Vector([0.0] * int(n))

    def _asarray(obj: Any, dtype: Any = float) -> _Vector:
        _ = dtype
        if isinstance(obj, _Vector):
            return obj
        if not isinstance(obj, (list, tuple)):
            raise TypeError("Expected 1D sequence")
        for item in obj:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("Vector elements must be numeric")
        return _Vector([float(x) for x in obj])

    def _isfinite(vec: _Vector) -> _IsFiniteResult:
        return _IsFiniteResult([math.isfinite(x) for x in vec])

    def _dot(a: _Vector, b: _Vector) -> float:
        return float(sum(float(x) * float(y) for x, y in zip(a, b, strict=True)))

    linalg_mod = py_types.ModuleType("numpy.linalg")
    linalg_mod.norm = lambda v: math.sqrt(sum(x * x for x in v))  # type: ignore[attr-defined]

    fake_np.zeros = _zeros  # type: ignore[attr-defined]
    fake_np.asarray = _asarray  # type: ignore[attr-defined]
    fake_np.array = _asarray  # type: ignore[attr-defined]
    fake_np.isfinite = _isfinite  # type: ignore[attr-defined]
    fake_np.dot = _dot  # type: ignore[attr-defined]
    fake_np.linalg = linalg_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", fake_np)
    monkeypatch.setitem(sys.modules, "numpy.linalg", linalg_mod)


def _block_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "numpy", None)
    monkeypatch.setitem(sys.modules, "numpy.linalg", None)


def test_fail_fast_missing_extra_error_on_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_numpy(monkeypatch)
    metric = EmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True))
    ctx_metric = ContextEmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True))

    # Fail fast even on missing ground truth or upstream errors (Clarification Q5)
    missing_ref_case = EvaluationCase(id="no-ref", input="hi", reference=None)
    errored_exec = ExecutionResult(
        case_id="no-ref", input="hi", output=None, errors=["boom"], elapsed_seconds=0.0
    )

    for target_metric in (metric, ctx_metric):
        with pytest.raises(MissingExtraError, match=r"evalforge-maestro\[embeddings\]"):
            target_metric.evaluate(missing_ref_case, errored_exec)
        with pytest.raises(MissingExtraError, match=r"evalforge-maestro\[embeddings\]"):
            asyncio.run(target_metric.aevaluate_batch([(missing_ref_case, errored_exec)]))


@pytest.mark.gate_determinism
def test_embedding_similarity_mock_determinism_and_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_numpy_for_test(monkeypatch)
    cfg = EmbeddingConfig(mock_mode=True, pass_threshold=0.5)
    metric = EmbeddingSimilarityMetric(config=cfg)

    case_match = EvaluationCase(
        id="c1",
        input="Explain caching.",
        reference="HTTP response caching improves latency and reduces backend load.",
    )
    exec_paraphrase = ExecutionResult(
        case_id="c1",
        input="Explain caching.",
        output="HTTP response caching reduces backend load and improves latency.",
        elapsed_seconds=0.01,
    )
    exec_unrelated = ExecutionResult(
        case_id="c1",
        input="Explain caching.",
        output="Bananas grow well in humid tropical orchards.",
        elapsed_seconds=0.01,
    )
    exec_punct = ExecutionResult(
        case_id="c1",
        input="Explain caching.",
        output="!!! ??? ---",
        elapsed_seconds=0.01,
    )
    exec_blank = ExecutionResult(
        case_id="c1",
        input="Explain caching.",
        output="   ",
        elapsed_seconds=0.01,
    )

    res1 = metric.evaluate(case_match, exec_paraphrase)
    res2 = metric.evaluate(case_match, exec_paraphrase)
    assert res1 == res2
    assert res1.status == MetricStatus.PASS
    assert res1.score is not None and 0.7 <= res1.score <= 1.0
    assert res1.metric_version == "1.0.0"

    bad = metric.evaluate(case_match, exec_unrelated)
    assert bad.status == MetricStatus.FAIL
    assert bad.score is not None and 0.0 <= bad.score < 0.5

    punct = metric.evaluate(case_match, exec_punct)
    assert punct.status == MetricStatus.FAIL
    assert punct.score is not None and 0.0 <= punct.score < 0.5

    blank = metric.evaluate(case_match, exec_blank)
    assert blank.status == MetricStatus.FAIL
    assert blank.score == 0.0

    # Missing reference -> NOT_APPLICABLE
    no_ref = metric.evaluate(EvaluationCase(id="nr", input="x", reference="  "), exec_paraphrase)
    assert no_ref.status == MetricStatus.NOT_APPLICABLE
    assert no_ref.score is None

    # Upstream execution error -> INCONCLUSIVE with secret redaction
    err_res = metric.evaluate(
        case_match,
        ExecutionResult(
            case_id="c1",
            input="x",
            output=None,
            errors=["upstream token=sk-secret-1234567890abcd failed"],
            elapsed_seconds=0.0,
        ),
    )
    assert err_res.status == MetricStatus.INCONCLUSIVE
    assert err_res.score is None
    assert "sk-secret-1234567890abcd" not in err_res.explanation

    # Case threshold override
    strict_case = case_match.model_copy(
        update={"criteria": CaseCriteria(metric_thresholds={"embedding_similarity": 0.9999})}
    )
    strict_res = metric.evaluate(strict_case, exec_paraphrase)
    assert strict_res.status in {MetricStatus.PASS, MetricStatus.FAIL}
    assert tuple(metric.metadata.required_case_fields) == ("reference",)


def test_clamped_cosine_and_invalid_vector_fault_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_numpy_for_test(monkeypatch)
    seen_texts: list[str] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        seen_texts.extend(texts)
        vectors: dict[str, list[float]] = {
            "opposite": [-1.0, 0.0],
            "ref_ok12": [1.0, 0.0],
            "zero_nor": [0.0, 0.0],
            "bad_dim1": [1.0, 0.0, 0.0],
            "nan_vec1": [float("nan"), 1.0],
        }
        return [vectors[t] for t in texts]

    metric = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(mock_mode=False, pass_threshold=0.5, max_input_chars=8),
        embed_fn=fake_embed,
    )
    batch_items = [
        (
            EvaluationCase(id="opp", input="q", reference="ref_ok12_extra_trimmed"),
            ExecutionResult(case_id="opp", input="q", output="opposite_extra", elapsed_seconds=0.0),
        ),
        (
            EvaluationCase(id="zero", input="q", reference="ref_ok12"),
            ExecutionResult(case_id="zero", input="q", output="zero_nor", elapsed_seconds=0.0),
        ),
        (
            EvaluationCase(id="dim", input="q", reference="ref_ok12"),
            ExecutionResult(case_id="dim", input="q", output="bad_dim1", elapsed_seconds=0.0),
        ),
        (
            EvaluationCase(id="nan", input="q", reference="ref_ok12"),
            ExecutionResult(case_id="nan", input="q", output="nan_vec1", elapsed_seconds=0.0),
        ),
    ]
    results = asyncio.run(metric.aevaluate_batch(batch_items, max_concurrency=2))
    assert results[0].score == 0.0
    assert results[0].status == MetricStatus.FAIL
    assert results[1].status == MetricStatus.INCONCLUSIVE and results[1].score is None
    assert results[2].status == MetricStatus.INCONCLUSIVE and results[2].score is None
    assert results[3].status == MetricStatus.INCONCLUSIVE and results[3].score is None
    assert all(len(t) <= 8 for t in seen_texts)


def test_context_embedding_similarity_aggregation_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_numpy_for_test(monkeypatch)

    def fake_embed(texts: list[str]) -> list[list[float]]:
        mapping = {
            "answer": [1.0, 0.0],
            "chunk match": [1.0, 0.0],
            "chunk orthogonal": [0.0, 1.0],
        }
        return [mapping[t] for t in texts]

    max_metric = ContextEmbeddingSimilarityMetric(
        config=EmbeddingConfig(aggregation=EmbeddingAggregation.MAX, pass_threshold=0.7),
        embed_fn=fake_embed,
    )
    mean_metric = ContextEmbeddingSimilarityMetric(
        config=EmbeddingConfig(aggregation=EmbeddingAggregation.MEAN, pass_threshold=0.7),
        embed_fn=fake_embed,
    )

    case = EvaluationCase(id="ctx-1", input="q")
    exec_res = ExecutionResult(
        case_id="ctx-1",
        input="q",
        output="answer",
        retrieved_chunks=[
            RetrievedChunk(id="c1", text="chunk orthogonal"),
            RetrievedChunk(id="c2", text="   "),
            RetrievedChunk(id="c3", text="chunk match"),
        ],
        elapsed_seconds=0.01,
    )
    res_max = max_metric.evaluate(case, exec_res)
    res_mean = mean_metric.evaluate(case, exec_res)
    assert res_max.score == 1.0 and res_max.status == MetricStatus.PASS
    assert res_mean.score == 0.5 and res_mean.status == MetricStatus.FAIL

    na_res = max_metric.evaluate(
        case,
        ExecutionResult(
            case_id="ctx-1",
            input="q",
            output="answer",
            retrieved_chunks=[RetrievedChunk(id="empty", text="   ")],
            elapsed_seconds=0.0,
        ),
    )
    assert na_res.status == MetricStatus.NOT_APPLICABLE and na_res.score is None


def test_orchestrator_drift_pin_and_decoupled_diagnostics_with_embeddings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    _ensure_numpy_for_test(monkeypatch)
    dataset = [
        {
            "id": "e1",
            "input": "What is the SLA?",
            "reference": "99.9% uptime SLA guarantee",
            "expected_context": ["c-sla"],
        }
    ]
    m1 = EmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True, pass_threshold=0.5))
    m2 = EmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True, pass_threshold=0.8))

    store = LocalRunStore(tmp_path / ".evalforge")
    orch = EvaluationOrchestrator(storage_root=store.root)

    from evalforge_maestro.adapters import RAGAdapter
    from evalforge_maestro.datasets import DatasetEngine

    ds = DatasetEngine(dataset, dataset_id="emb-ds")
    adapter = RAGAdapter(
        lambda q: {
            "answer": "99.9% uptime SLA guarantee",
            "chunks": [{"id": "c-wrong", "text": "irrelevant gardening soil guide"}],
        }
    )
    run_a = orch.run(
        ds,
        adapter,
        [m1, ContextEmbeddingSimilarityMetric(config=EmbeddingConfig(mock_mode=True))],
        run_id="run-a",
    )
    run_b = orch.run(ds, adapter, [m2], run_id="run-b")

    assert run_a.embedding_config_fingerprint is not None
    entry = store.pin_baseline("run-a", name="emb-base")
    assert entry.embedding_config_fingerprint == run_a.embedding_config_fingerprint

    drift = detect_drift(run_a, run_b)
    assert any(w.category == DriftCategory.EMBEDDING_CONFIG for w in drift)

    # Decoupled diagnostics: embedding_similarity PASS + context_embedding_similarity FAIL
    synthetic_run = run_a.model_copy(
        update={
            "case_results": [
                CaseEvaluationRecord(
                    case_id="dec-1",
                    mandatory=False,
                    execution=run_a.case_results[0].execution,
                    metrics={
                        "embedding_similarity": MetricResult(
                            metric_id="embedding_similarity",
                            metric_version="1.0.0",
                            score=0.95,
                            status=MetricStatus.PASS,
                            explanation="ok",
                        ),
                        "context_embedding_similarity": MetricResult(
                            metric_id="context_embedding_similarity",
                            metric_version="1.0.0",
                            score=0.1,
                            status=MetricStatus.FAIL,
                            explanation="unaligned",
                        ),
                    },
                )
            ]
        }
    )
    diags = detect_decoupled_evidence(synthetic_run)
    assert len(diags) == 1
    assert diags[0].category == EvidenceDecouplingCategory.ANSWER_PASSED_RETRIEVAL_FAILED
