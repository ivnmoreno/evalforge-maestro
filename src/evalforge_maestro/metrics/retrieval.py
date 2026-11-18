"""Deterministic Information Retrieval (IR) metrics with pinned formula versions."""

from __future__ import annotations

import math
from typing import Any

from evalforge_maestro._canonical import round_score
from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.metrics.deterministic import (
    _inconclusive_result,
    _resolve_threshold,
    _validate_threshold,
)
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)


def _validate_k(k: int) -> int:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise MetricError(f"k must be an integer >= 1, got {k!r}")
    return k


def _prepare_retrieval_inputs(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    match_parent_id: bool,
) -> tuple[dict[str, int], list[str]]:
    """Build positive relevance map G_pos and stably sorted deduplicated chunk IDs R."""
    g_pos: dict[str, int] = {}
    for item in case.expected_context or ():
        if isinstance(item, str):
            g_pos[item] = 1
        elif item.relevance > 0:
            g_pos[item.id] = item.relevance

    ordered = sorted(
        enumerate(execution.retrieved_chunks),
        key=lambda pair: (
            pair[1].rank if pair[1].rank is not None else pair[0] + 1,
            pair[0],
        ),
    )

    seen: set[str] = set()
    ranked_ids: list[str] = []
    for _, chunk in ordered:
        eff_id = (chunk.parent_id or chunk.id) if match_parent_id else chunk.id
        if eff_id not in seen:
            seen.add(eff_id)
            ranked_ids.append(eff_id)

    return g_pos, ranked_ids


def _prepare_ir_evaluation(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    snapshot: dict[str, Any],
    match_parent_id: bool,
) -> tuple[dict[str, int], list[str]] | MetricResult:
    """Enforce INCONCLUSIVE (execution errors) ahead of NOT_APPLICABLE (|G_pos| == 0)."""
    if execution.errors:
        return _inconclusive_result(metadata, execution, snapshot)

    g_pos, ranked_ids = _prepare_retrieval_inputs(
        case,
        execution,
        match_parent_id=match_parent_id,
    )
    if not g_pos:
        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            explanation=(
                f"EvaluationCase.expected_context has zero positively weighted items "
                f"(|G_pos| == 0); {metadata.metric_id} is not applicable."
            ),
            config_snapshot=snapshot,
        )
    return g_pos, ranked_ids


def _finalize_ir_result(
    *,
    metadata: MetricMetadata,
    score: float,
    threshold: float,
    evidence: list[str],
    explanation: str,
    snapshot: dict[str, Any],
) -> MetricResult:
    status = MetricStatus.PASS if score >= threshold else MetricStatus.FAIL
    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=score,
        status=status,
        label="pass" if status == MetricStatus.PASS else "fail",
        explanation=explanation,
        evidence=evidence,
        config_snapshot=snapshot,
    )


def _score_precision_at_k(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    k: int,
    match_parent_id: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for precision_at_k v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "k": k,
        "match_parent_id": match_parent_id,
        "threshold": threshold,
    }
    prepared = _prepare_ir_evaluation(
        case,
        execution,
        metadata=metadata,
        snapshot=snapshot,
        match_parent_id=match_parent_id,
    )
    if isinstance(prepared, MetricResult):
        return prepared
    g_pos, ranked_ids = prepared

    top_k = ranked_ids[:k]
    hits = [cid for cid in top_k if cid in g_pos]
    score = round_score(len(hits) / k)
    return _finalize_ir_result(
        metadata=metadata,
        score=score,
        threshold=threshold,
        evidence=hits,
        explanation=(
            f"Precision@{k} matched {len(hits)} relevant unique item(s) over cutoff K={k}."
        ),
        snapshot=snapshot,
    )


def _score_recall_at_k(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    k: int,
    match_parent_id: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for recall_at_k v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "k": k,
        "match_parent_id": match_parent_id,
        "threshold": threshold,
    }
    prepared = _prepare_ir_evaluation(
        case,
        execution,
        metadata=metadata,
        snapshot=snapshot,
        match_parent_id=match_parent_id,
    )
    if isinstance(prepared, MetricResult):
        return prepared
    g_pos, ranked_ids = prepared

    top_k = ranked_ids[:k]
    hits = [cid for cid in top_k if cid in g_pos]
    score = round_score(len(hits) / len(g_pos))
    return _finalize_ir_result(
        metadata=metadata,
        score=score,
        threshold=threshold,
        evidence=hits,
        explanation=(
            f"Recall@{k} retrieved {len(hits)} of {len(g_pos)} unique positively relevant item(s)."
        ),
        snapshot=snapshot,
    )


def _score_hit_rate_at_k(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    k: int,
    match_parent_id: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for hit_rate_at_k v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "k": k,
        "match_parent_id": match_parent_id,
        "threshold": threshold,
    }
    prepared = _prepare_ir_evaluation(
        case,
        execution,
        metadata=metadata,
        snapshot=snapshot,
        match_parent_id=match_parent_id,
    )
    if isinstance(prepared, MetricResult):
        return prepared
    g_pos, ranked_ids = prepared

    top_k = ranked_ids[:k]
    hits = [cid for cid in top_k if cid in g_pos]
    score = round_score(1.0 if hits else 0.0)
    return _finalize_ir_result(
        metadata=metadata,
        score=score,
        threshold=threshold,
        evidence=hits,
        explanation=(
            f"Hit Rate@{k} found {len(hits)} relevant item(s) in top {k}."
            if hits
            else f"Hit Rate@{k} found no relevant items in top {k}."
        ),
        snapshot=snapshot,
    )


def _score_mrr(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    match_parent_id: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for mrr v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "match_parent_id": match_parent_id,
        "threshold": threshold,
    }
    prepared = _prepare_ir_evaluation(
        case,
        execution,
        metadata=metadata,
        snapshot=snapshot,
        match_parent_id=match_parent_id,
    )
    if isinstance(prepared, MetricResult):
        return prepared
    g_pos, ranked_ids = prepared

    first_rank: int | None = None
    matched_id: str | None = None
    for idx, cid in enumerate(ranked_ids, start=1):
        if cid in g_pos:
            first_rank = idx
            matched_id = cid
            break

    score = round_score(1.0 / first_rank if first_rank is not None else 0.0)
    return _finalize_ir_result(
        metadata=metadata,
        score=score,
        threshold=threshold,
        evidence=[matched_id] if matched_id is not None else [],
        explanation=(
            f"First relevant chunk {matched_id!r} appeared at rank {first_rank} (MRR={score:.6f})."
            if first_rank is not None
            else "No relevant chunk found in deduplicated retrieval results (MRR=0.000000)."
        ),
        snapshot=snapshot,
    )


def _score_ndcg_at_k(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    metadata: MetricMetadata,
    k: int,
    match_parent_id: bool,
    default_threshold: float,
) -> MetricResult:
    """Pure deterministic scoring logic for ndcg_at_k v1.0.0."""
    threshold = _resolve_threshold(case, metadata.metric_id, default_threshold)
    snapshot: dict[str, Any] = {
        "k": k,
        "match_parent_id": match_parent_id,
        "threshold": threshold,
    }
    prepared = _prepare_ir_evaluation(
        case,
        execution,
        metadata=metadata,
        snapshot=snapshot,
        match_parent_id=match_parent_id,
    )
    if isinstance(prepared, MetricResult):
        return prepared
    g_pos, ranked_ids = prepared

    top_k = ranked_ids[:k]
    dcg = sum(
        ((2 ** g_pos[cid]) - 1) / math.log2(idx + 1)
        for idx, cid in enumerate(top_k, start=1)
        if cid in g_pos
    )
    ideal_rels = sorted(g_pos.values(), reverse=True)[:k]
    idcg = sum(((2**rel) - 1) / math.log2(idx + 1) for idx, rel in enumerate(ideal_rels, start=1))
    score = round_score(dcg / idcg)
    hits = [cid for cid in top_k if cid in g_pos]
    return _finalize_ir_result(
        metadata=metadata,
        score=score,
        threshold=threshold,
        evidence=hits,
        explanation=(
            f"NDCG@{k} scored {score:.6f} (DCG={dcg:.6f}, IDCG={idcg:.6f}) "
            f"across {len(top_k)} deduplicated retrieved chunk(s)."
        ),
        snapshot=snapshot,
    )


class PrecisionAtKMetric:
    """Fraction of top-K deduplicated retrieved chunks matching ground-truth context."""

    _METADATA = MetricMetadata(
        metric_id="precision_at_k",
        metric_version="1.0.0",
        what_it_measures=(
            "Fraction of the top-K unique retrieved chunks present in positively "
            "weighted expected context."
        ),
        required_case_fields=("expected_context",),
        required_execution_fields=("retrieved_chunks", "errors"),
        calculation_method=(
            "Stably sort retrieved_chunks by (rank, index), deduplicate effective IDs "
            "preserving first rank, compute |R[0:K] ∩ G_pos| / K rounded to 6 decimals."
        ),
        known_limitations=(
            "Treats all positive ground-truth weights as binary relevance and penalizes "
            "under-retrieval when |R| < K; does not assess generation groundedness."
        ),
    )

    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None:
        self._k = _validate_k(k)
        self._match_parent_id = bool(match_parent_id)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for precision_at_k."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate Precision@K over retrieved_chunks against expected_context."""
        return _score_precision_at_k(
            case,
            execution,
            metadata=self._METADATA,
            k=self._k,
            match_parent_id=self._match_parent_id,
            default_threshold=self._threshold,
        )


class RecallAtKMetric:
    """Fraction of ground-truth context items surfaced inside top-K unique retrieved chunks."""

    _METADATA = MetricMetadata(
        metric_id="recall_at_k",
        metric_version="1.0.0",
        what_it_measures=(
            "Fraction of positively weighted expected context items retrieved within "
            "the top-K unique chunks."
        ),
        required_case_fields=("expected_context",),
        required_execution_fields=("retrieved_chunks", "errors"),
        calculation_method=(
            "Stably sort retrieved_chunks by (rank, index), deduplicate effective IDs, "
            "compute |R[0:K] ∩ G_pos| / |G_pos| rounded to 6 decimals."
        ),
        known_limitations=(
            "Ignores rank ordering inside top-K and does not penalize extra irrelevant "
            "chunks beyond cutoff truncation."
        ),
    )

    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None:
        self._k = _validate_k(k)
        self._match_parent_id = bool(match_parent_id)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for recall_at_k."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate Recall@K over retrieved_chunks against expected_context."""
        return _score_recall_at_k(
            case,
            execution,
            metadata=self._METADATA,
            k=self._k,
            match_parent_id=self._match_parent_id,
            default_threshold=self._threshold,
        )


class MRRMetric:
    """Mean Reciprocal Rank of the earliest relevant unique retrieved chunk."""

    _METADATA = MetricMetadata(
        metric_id="mrr",
        metric_version="1.0.0",
        what_it_measures="Reciprocal rank (1 / rank_1) of the first relevant unique chunk.",
        required_case_fields=("expected_context",),
        required_execution_fields=("retrieved_chunks", "errors"),
        calculation_method=(
            "Stably sort retrieved_chunks by (rank, index), deduplicate effective IDs, "
            "and compute 1.0 / rank_1 for the first match in G_pos (or 0.0 if absent)."
        ),
        known_limitations=(
            "Evaluates only the top-ranked relevant hit and ignores additional relevant "
            "chunks at deeper positions."
        ),
    )

    def __init__(
        self,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None:
        self._match_parent_id = bool(match_parent_id)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for mrr."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate reciprocal rank over retrieved_chunks against expected_context."""
        return _score_mrr(
            case,
            execution,
            metadata=self._METADATA,
            match_parent_id=self._match_parent_id,
            default_threshold=self._threshold,
        )


class NDCGAtKMetric:
    """Normalized Discounted Cumulative Gain at K with graded integer relevance support."""

    _METADATA = MetricMetadata(
        metric_id="ndcg_at_k",
        metric_version="1.0.0",
        what_it_measures=(
            "Rank-discounted graded relevance alignment between top-K unique retrieved "
            "chunks and optimal expected context ordering."
        ),
        required_case_fields=("expected_context",),
        required_execution_fields=("retrieved_chunks", "errors"),
        calculation_method=(
            "Compute DCG@K = sum_{i=1..min(K,|R|)} (2^rel_i - 1) / log2(i + 1) over "
            "deduplicated ranks divided by IDCG@K over top-K G_pos sorted descending."
        ),
        known_limitations=(
            "Assumes non-negative integer relevance grades and treats unmentioned chunk IDs "
            "as having relevance 0."
        ),
    )

    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None:
        self._k = _validate_k(k)
        self._match_parent_id = bool(match_parent_id)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for ndcg_at_k."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate NDCG@K over retrieved_chunks against expected_context."""
        return _score_ndcg_at_k(
            case,
            execution,
            metadata=self._METADATA,
            k=self._k,
            match_parent_id=self._match_parent_id,
            default_threshold=self._threshold,
        )


class HitRateAtKMetric:
    """Binary indicator of whether at least one relevant chunk appears in top-K."""

    _METADATA = MetricMetadata(
        metric_id="hit_rate_at_k",
        metric_version="1.0.0",
        what_it_measures=(
            "Binary presence (1.0 vs 0.0) of at least one positively relevant unique "
            "chunk inside top-K retrieved results."
        ),
        required_case_fields=("expected_context",),
        required_execution_fields=("retrieved_chunks", "errors"),
        calculation_method=(
            "Stably sort retrieved_chunks by (rank, index), deduplicate effective IDs, "
            "return 1.0 if |R[0:K] ∩ G_pos| > 0 else 0.0."
        ),
        known_limitations=(
            "Coarse binary signal within top-K; insensitive to exact rank order or recall "
            "completeness across multi-chunk answers."
        ),
    )

    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 1.0,
    ) -> None:
        self._k = _validate_k(k)
        self._match_parent_id = bool(match_parent_id)
        self._threshold = _validate_threshold(threshold)

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metadata descriptor for hit_rate_at_k."""
        return self._METADATA

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        """Evaluate Hit Rate@K over retrieved_chunks against expected_context."""
        return _score_hit_rate_at_k(
            case,
            execution,
            metadata=self._METADATA,
            k=self._k,
            match_parent_id=self._match_parent_id,
            default_threshold=self._threshold,
        )


precision_at_k = PrecisionAtKMetric()
recall_at_k = RecallAtKMetric()
mrr = MRRMetric()
ndcg_at_k = NDCGAtKMetric()
hit_rate_at_k = HitRateAtKMetric()
