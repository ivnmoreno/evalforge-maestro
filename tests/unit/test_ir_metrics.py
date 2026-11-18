"""Unit tests achieving 100% branch coverage on deterministic IR retrieval metrics."""

from __future__ import annotations

import math
from typing import Any

import pytest

from evalforge_maestro._canonical import round_score
from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.metrics import (
    HitRateAtKMetric,
    MRRMetric,
    NDCGAtKMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from evalforge_maestro.types import (
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    ExpectedContextItem,
    Metric,
    MetricStatus,
    RetrievedChunk,
)


def _make_exec(
    chunks: list[RetrievedChunk],
    *,
    errors: list[str] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        case_id="c1",
        input="query",
        retrieved_chunks=chunks,
        elapsed_seconds=0.05,
        errors=errors or [],
    )


def test_ir_metric_init_validation_and_protocol_conformance() -> None:
    for cls in (PrecisionAtKMetric, RecallAtKMetric, NDCGAtKMetric, HitRateAtKMetric):
        for bad_k in (0, -3, True):
            with pytest.raises(MetricError):
                cls(k=bad_k)
        for bad_threshold in (-0.1, 1.1, True, float("nan")):
            with pytest.raises(MetricError):
                cls(threshold=bad_threshold)

    with pytest.raises(MetricError):
        MRRMetric(threshold=1.5)

    for metric in (precision_at_k, recall_at_k, mrr, ndcg_at_k, hit_rate_at_k):
        assert isinstance(metric, Metric)
        assert metric.metadata.metric_version == "1.0.0"
        assert metric.metadata.what_it_measures
        assert metric.metadata.calculation_method
        assert metric.metadata.known_limitations


def test_ir_metrics_binary_exact_formulas_and_cutoffs() -> None:
    case = EvaluationCase(
        id="c1",
        input="q",
        expected_context=["d1", "d3", "d4"],
    )
    chunks = [
        RetrievedChunk(id="d2", text="t2", rank=1),
        RetrievedChunk(id="d1", text="t1", rank=2),
        RetrievedChunk(id="d5", text="t5", rank=3),
        RetrievedChunk(id="d3", text="t3", rank=4),
        RetrievedChunk(id="d4", text="t4", rank=5),
    ]
    execution = _make_exec(chunks)

    p3 = PrecisionAtKMetric(k=3).evaluate(case, execution)
    r3 = RecallAtKMetric(k=3).evaluate(case, execution)
    h3 = HitRateAtKMetric(k=3).evaluate(case, execution)
    mrr_res = mrr.evaluate(case, execution)
    n3 = NDCGAtKMetric(k=3).evaluate(case, execution)

    assert p3.score == round_score(1 / 3)
    assert p3.status == MetricStatus.FAIL  # 0.333333 < default 0.5
    assert r3.score == round_score(1 / 3)
    assert r3.status == MetricStatus.FAIL
    assert h3.score == 1.0
    assert h3.status == MetricStatus.PASS  # default threshold 1.0
    assert mrr_res.score == 0.5
    assert mrr_res.status == MetricStatus.PASS  # default threshold 0.5

    expected_dcg3 = 1.0 / math.log2(2 + 1)
    expected_idcg3 = sum(1.0 / math.log2(pos + 1) for pos in (1, 2, 3))
    assert n3.score == round_score(expected_dcg3 / expected_idcg3)

    # Under-retrieval: |R| < K preserves K as Precision@K denominator
    under_exec = _make_exec([RetrievedChunk(id="d1", text="t1")])
    p5_under = PrecisionAtKMetric(k=5).evaluate(case, under_exec)
    assert p5_under.score == 0.2

    # Empty retrieval with |G_pos| > 0 yields 0.0 / FAIL across all 5 metrics
    empty_exec = _make_exec([])
    for metric in (precision_at_k, recall_at_k, hit_rate_at_k, mrr, ndcg_at_k):
        res = metric.evaluate(case, empty_exec)
        assert res.score == 0.0
        assert res.status == MetricStatus.FAIL


def test_ir_metrics_graded_ndcg_and_threshold_precedence() -> None:
    case = EvaluationCase(
        id="c-graded",
        input="q",
        expected_context=[
            ExpectedContextItem(id="d1", relevance=3),
            ExpectedContextItem(id="d2", relevance=2),
            ExpectedContextItem(id="d0", relevance=0),
            "d3",
        ],
        criteria=CaseCriteria(
            pass_threshold=0.8,
            metric_thresholds={"precision_at_k": 0.4},
        ),
    )
    execution = _make_exec(
        [
            RetrievedChunk(id="d3", text="t3", rank=1),  # rel=1
            RetrievedChunk(id="d1", text="t1", rank=2),  # rel=3
            RetrievedChunk(id="d0", text="t0", rank=3),  # rel=0
            RetrievedChunk(id="d2", text="t2", rank=4),  # rel=2
        ]
    )

    ndcg3 = NDCGAtKMetric(k=3).evaluate(case, execution)
    dcg3 = ((2**1 - 1) / math.log2(2)) + ((2**3 - 1) / math.log2(3))
    idcg3 = ((2**3 - 1) / math.log2(2)) + ((2**2 - 1) / math.log2(3)) + ((2**1 - 1) / math.log2(4))
    assert ndcg3.score == round_score(dcg3 / idcg3)
    # Uses CaseCriteria.pass_threshold (0.8) since ndcg_at_k not in metric_thresholds
    assert ndcg3.config_snapshot["threshold"] == 0.8
    assert ndcg3.status == MetricStatus.FAIL

    # precision_at_k honors metric_thresholds["precision_at_k"] == 0.4 > pass_threshold 0.8
    p3 = PrecisionAtKMetric(k=3, threshold=0.9).evaluate(case, execution)
    assert p3.score == round_score(2 / 3)  # d3 and d1 have positive relevance; d0 is rel=0
    assert p3.config_snapshot["threshold"] == 0.4
    assert p3.status == MetricStatus.PASS

    # hit_rate_at_k default threshold when criteria has neither override
    plain_case = EvaluationCase(id="c-plain", input="q", expected_context=["d1"])
    hr_miss = HitRateAtKMetric(k=1).evaluate(
        plain_case, _make_exec([RetrievedChunk(id="d9", text="x")])
    )
    assert hr_miss.score == 0.0
    assert hr_miss.status == MetricStatus.FAIL
    assert hr_miss.config_snapshot["threshold"] == 1.0


def test_ir_metrics_rank_sorting_parent_id_and_deduplication() -> None:
    # Out-of-order explicit ranks & missing rank fallback (idx + 1)
    chunks = [
        RetrievedChunk(id="c-pos0-no-rank", text="t", parent_id="doc-late"),  # key=(1, 0)
        RetrievedChunk(id="c-rank2", text="t", parent_id="doc-b", rank=2),  # key=(2, 1)
        RetrievedChunk(id="c-rank1", text="t", parent_id="doc-a", rank=1),  # key=(1, 2)
        RetrievedChunk(id="c-rank1", text="dup", parent_id="doc-a", rank=5),
        RetrievedChunk(id="c-sibling", text="t", parent_id="doc-a", rank=3),
    ]
    # Sorted order: c-pos0-no-rank (doc-late), c-rank1 (doc-a), c-rank2 (doc-b), c-sibling (doc-a)
    case_chunk = EvaluationCase(id="c-chunk", input="q", expected_context=["c-rank1"])
    execution = _make_exec(chunks)

    # Deduplicating on chunk.id keeps c-rank1 at position 2 (1-based)
    assert PrecisionAtKMetric(k=2).evaluate(case_chunk, execution).score == 0.5
    assert RecallAtKMetric(k=5).evaluate(case_chunk, execution).score == 1.0  # dup didn't inflate
    assert MRRMetric().evaluate(case_chunk, execution).score == 0.5

    # match_parent_id=True resolves (chunk.parent_id or chunk.id) and deduplicates siblings
    case_parent = EvaluationCase(id="c-parent", input="q", expected_context=["doc-a"])
    p_parent = PrecisionAtKMetric(k=4, match_parent_id=True).evaluate(case_parent, execution)
    assert p_parent.score == 0.25  # doc-a counted once despite c-rank1 + c-sibling
    assert p_parent.config_snapshot["match_parent_id"] is True

    # Fallback to chunk.id when parent_id is None under match_parent_id=True
    case_fallback = EvaluationCase(id="c-fb", input="q", expected_context=["only-id"])
    res_fb = HitRateAtKMetric(k=1, match_parent_id=True).evaluate(
        case_fallback,
        _make_exec([RetrievedChunk(id="only-id", text="t", parent_id=None)]),
    )
    assert res_fb.score == 1.0


def test_ir_metrics_inconclusive_and_not_applicable_guards() -> None:
    empty_gt_case = EvaluationCase(id="c-none", input="q", expected_context=None)
    empty_list_case = EvaluationCase(id="c-empty", input="q", expected_context=[])
    all_zero_case = EvaluationCase(
        id="c-zero",
        input="q",
        expected_context=[ExpectedContextItem(id="d1", relevance=0)],
    )
    valid_case = EvaluationCase(id="c-valid", input="q", expected_context=["d1"])

    ok_exec = _make_exec([RetrievedChunk(id="d1", text="t1")])
    err_exec = _make_exec([RetrievedChunk(id="d1", text="t1")], errors=["timeout"])

    # Empty / absent / all-zero relevance -> NOT_APPLICABLE across all 5 IR metrics
    for case in (empty_gt_case, empty_list_case, all_zero_case):
        for metric in (precision_at_k, recall_at_k, hit_rate_at_k, mrr, ndcg_at_k):
            res = metric.evaluate(case, ok_exec)
            assert res.score is None
            assert res.status == MetricStatus.NOT_APPLICABLE

    # ExecutionResult.errors -> INCONCLUSIVE (takes precedence even when |G_pos| == 0)
    for case in (valid_case, empty_gt_case, all_zero_case):
        for metric in (precision_at_k, recall_at_k, hit_rate_at_k, mrr, ndcg_at_k):
            res = metric.evaluate(case, err_exec)
            assert res.score is None
            assert res.status == MetricStatus.INCONCLUSIVE
            assert res.evidence == ["timeout"]


def test_default_singletons_cover_config_typing() -> None:
    case = EvaluationCase(id="c1", input="q", expected_context=["x"])
    ex: Any = _make_exec([RetrievedChunk(id="x", text="ctx")])
    assert precision_at_k.evaluate(case, ex).score == round_score(1 / 5)
    assert recall_at_k.evaluate(case, ex).score == 1.0
    assert hit_rate_at_k.evaluate(case, ex).score == 1.0
    assert mrr.evaluate(case, ex).score == 1.0
    assert ndcg_at_k.evaluate(case, ex).score == 1.0
