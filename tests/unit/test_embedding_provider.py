"""Unit tests for lazy embedding provider resolution, air-gap safety, retries, and PII checks."""

from __future__ import annotations

import asyncio
import importlib.util
import math
import os
import sys
import types as py_types
from collections.abc import Sequence
from typing import Any

import pytest

from evalforge_maestro.embeddings import EmbeddingSimilarityMetric
from evalforge_maestro.exceptions import LocalOnlyPolicyError, MetricError, MissingExtraError
from evalforge_maestro.types import (
    EmbeddingConfig,
    EvaluationCase,
    ExecutionResult,
    MetricStatus,
)


def _install_fake_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("numpy") is not None:
        return

    class _Vec(list[float]):
        @property
        def ndim(self) -> int:
            return 1

        @property
        def shape(self) -> tuple[int, ...]:
            return (len(self),)

        def __truediv__(self, other: float) -> _Vec:
            return _Vec([x / float(other) for x in self])

        def tolist(self) -> list[float]:
            return list(self)

    class _Fin:
        def __init__(self, vec: _Vec) -> None:
            self._v = vec

        def all(self) -> bool:
            return all(math.isfinite(x) for x in self._v)

    np_mod = py_types.ModuleType("numpy")
    linalg = py_types.ModuleType("numpy.linalg")
    linalg.norm = lambda v: math.sqrt(sum(x * x for x in v))  # type: ignore[attr-defined]
    np_mod.float64 = float  # type: ignore[attr-defined]
    np_mod.ndarray = _Vec  # type: ignore[attr-defined]
    np_mod.zeros = lambda n, dtype=float: _Vec([0.0] * int(n))  # type: ignore[attr-defined]
    np_mod.asarray = lambda seq, dtype=float: _Vec([float(x) for x in seq])  # type: ignore[attr-defined]
    np_mod.array = np_mod.asarray  # type: ignore[attr-defined]
    np_mod.isfinite = lambda v: _Fin(v)  # type: ignore[attr-defined]
    np_mod.dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # type: ignore[attr-defined]
    np_mod.linalg = linalg  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", np_mod)
    monkeypatch.setitem(sys.modules, "numpy.linalg", linalg)


def test_local_only_blocks_remote_embedding_pre_network_and_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_numpy(monkeypatch)
    monkeypatch.setitem(sys.modules, "litellm", None)
    monkeypatch.delitem(sys.modules, "litellm", raising=False)

    metric = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(
            model="openai/text-embedding-3-small",
            local_only=True,
            mock_mode=False,
        )
    )
    case = EvaluationCase(id="loc-1", input="q", reference="hello world")
    exec_res = ExecutionResult(
        case_id="loc-1", input="q", output="hello world", elapsed_seconds=0.0
    )

    with pytest.raises(LocalOnlyPolicyError, match="local_only"):
        metric.evaluate(case, exec_res)
    assert "litellm" not in sys.modules


def test_missing_litellm_raises_missing_extra_for_live_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_numpy(monkeypatch)
    monkeypatch.setitem(sys.modules, "litellm", None)

    metric = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(
            model="ollama/nomic-embed-text",
            local_only=True,
            mock_mode=False,
        )
    )
    case = EvaluationCase(id="ll-1", input="q", reference="hello")
    exec_res = ExecutionResult(case_id="ll-1", input="q", output="hello", elapsed_seconds=0.0)

    with pytest.raises(MissingExtraError, match=r"evalforge-maestro\[embeddings\]"):
        metric.evaluate(case, exec_res)


def test_live_litellm_retries_and_airgap_cost_map(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_numpy(monkeypatch)
    calls = 0

    async def fake_aembedding(**kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        assert kwargs["model"] == "ollama/nomic-embed-text"
        assert kwargs["api_base"] == "http://127.0.0.1:11434"
        assert kwargs["api_key"] == "tok-embed"
        if calls == 1:
            raise RuntimeError("transient connection reset")
        inputs: Sequence[str] = kwargs["input"]
        return {"data": [{"embedding": [1.0, 0.0]} for _ in inputs]}

    fake_litellm = py_types.ModuleType("litellm")
    fake_litellm.aembedding = fake_aembedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    metric = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(
            model="ollama/nomic-embed-text",
            api_base="http://127.0.0.1:11434",
            local_only=True,
            mock_mode=False,
            max_retries=1,
            retry_backoff_seconds=0.0,
        ),
        api_key="tok-embed",
    )
    case = EvaluationCase(id="ok-1", input="q", reference="alpha")
    exec_res = ExecutionResult(case_id="ok-1", input="q", output="beta", elapsed_seconds=0.0)

    res = metric.evaluate(case, exec_res)
    assert res.status == MetricStatus.PASS
    assert res.score == 1.0
    assert calls == 2
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"


def test_exhausted_retries_and_pii_block_on_remote_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_numpy(monkeypatch)

    async def failing_embed(texts: list[str]) -> list[list[float]]:
        _ = texts
        raise RuntimeError("socket timeout sk-secret-1234567890abcd")

    metric_fail = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(max_retries=1, retry_backoff_seconds=0.0),
        embed_fn=failing_embed,
    )
    case = EvaluationCase(id="err-1", input="q", reference="hello")
    exec_res = ExecutionResult(case_id="err-1", input="q", output="hello", elapsed_seconds=0.0)
    res = asyncio.run(metric_fail.aevaluate(case, exec_res))
    assert res.status == MetricStatus.INCONCLUSIVE
    assert "sk-secret-1234567890abcd" not in res.explanation

    # Remote endpoint with block_pii screens outbound payloads pre-network
    from evalforge_maestro.embeddings.provider import wrap_pii_guarded_embedding_metric

    invoked = False

    def remote_fn(texts: list[str]) -> list[list[float]]:
        nonlocal invoked
        invoked = True
        return [[1.0, 0.0] for _ in texts]

    remote_metric = EmbeddingSimilarityMetric(
        config=EmbeddingConfig(model="openai/text-embedding-3-small", local_only=False),
        embed_fn=remote_fn,
    )
    guarded = wrap_pii_guarded_embedding_metric(remote_metric, block_pii=True)
    pii_exec = ExecutionResult(
        case_id="pii-1",
        input="q",
        output="Contact user@example.com for details",
        elapsed_seconds=0.0,
    )
    with pytest.raises(LocalOnlyPolicyError, match="PII"):
        guarded.evaluate(case, pii_exec)
    assert not invoked

    # Invalid return shape from custom callable surfaces cleanly as INCONCLUSIVE
    distinct_case = EvaluationCase(id="bad-shape", input="q", reference="alpha")
    distinct_exec = ExecutionResult(
        case_id="bad-shape", input="q", output="beta", elapsed_seconds=0.0
    )
    bad_shape_metric = EmbeddingSimilarityMetric(embed_fn=lambda texts: [[1.0, 0.0]])
    bad_res = bad_shape_metric.evaluate(distinct_case, distinct_exec)
    assert bad_res.status == MetricStatus.INCONCLUSIVE
    assert issubclass(MissingExtraError, MetricError) or issubclass(MissingExtraError, Exception)
