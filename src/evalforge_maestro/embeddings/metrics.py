"""Embedding similarity Metric and AsyncBatchMetric implementations."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from evalforge_maestro._canonical import (
    FLOAT_EPSILON,
    canonical_sha256,
    round_score,
    scrub_secret_text,
)
from evalforge_maestro.embeddings.provider import (
    EmbeddingFn,
    clamped_cosine_similarity,
    invoke_embedding_provider,
    resolve_numpy,
    truncate_for_embedding,
)
from evalforge_maestro.exceptions import ConfigurationError, LocalOnlyPolicyError, MissingExtraError
from evalforge_maestro.types import (
    EmbeddingAggregation,
    EmbeddingConfig,
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)


def _resolve_threshold(case: EvaluationCase, metric_id: str, default: float) -> float:
    if metric_id in case.criteria.metric_thresholds:
        return case.criteria.metric_thresholds[metric_id]
    if case.criteria.pass_threshold is not None:
        return case.criteria.pass_threshold
    return default


class _BaseEmbeddingSimilarityMetric:
    """Shared async/sync execution, fail-fast extra guard, and caching for embedding metrics."""

    def __init__(
        self,
        *,
        metadata: MetricMetadata,
        config: EmbeddingConfig | None = None,
        api_key: str | None = None,
        embed_fn: EmbeddingFn | None = None,
    ) -> None:
        self._metadata = metadata
        self._config = config or EmbeddingConfig()
        self._api_key = api_key
        self._embed_fn = embed_fn
        self._fingerprint = canonical_sha256(
            {
                "config": self._config.redacted_dict(),
                "metric_id": metadata.metric_id,
                "metric_version": metadata.metric_version,
            }
        )

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metric capability, input, and limitation declaration."""
        return self._metadata

    @property
    def embedding_config(self) -> EmbeddingConfig:
        """Return redacted EmbeddingConfig bound to this metric."""
        return self._config

    @property
    def embedding_config_fingerprint(self) -> str:
        """Return canonical SHA-256 fingerprint of the bound EmbeddingConfig and metric version."""
        return self._fingerprint

    def _snapshot(self, threshold: float) -> dict[str, Any]:
        payload = self._config.redacted_dict()
        payload["threshold"] = threshold
        payload["embedding_config_fingerprint"] = self._fingerprint
        return payload

    def _extract_texts_for_case(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> tuple[str, list[str]]:
        raise NotImplementedError  # pragma: no cover

    def _missing_ground_truth_reason(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> str | None:
        raise NotImplementedError  # pragma: no cover

    def _score_from_vectors(
        self,
        output_vec: Any,
        target_vecs: list[Any],
        *,
        np_mod: Any,
    ) -> tuple[float, list[str]]:
        raise NotImplementedError  # pragma: no cover

    def _result_from_status(
        self,
        *,
        status: MetricStatus,
        score: float | None,
        explanation: str,
        snapshot: dict[str, Any],
        evidence: list[str] | None = None,
    ) -> MetricResult:
        return MetricResult(
            metric_id=self._metadata.metric_id,
            metric_version=self._metadata.metric_version,
            score=score,
            status=status,
            explanation=scrub_secret_text(explanation),
            evidence=[scrub_secret_text(e) for e in (evidence or [])],
            config_snapshot=snapshot,
        )

    def _score_single_vectors(
        self,
        *,
        case: EvaluationCase,
        execution: ExecutionResult,
        threshold: float,
        snapshot: dict[str, Any],
        vec_cache: dict[str, Any],
        np_mod: Any,
    ) -> MetricResult:
        out_raw, targets = self._extract_texts_for_case(case, execution)
        out_key = truncate_for_embedding(out_raw, max_input_chars=self._config.max_input_chars)
        target_keys = [
            truncate_for_embedding(t, max_input_chars=self._config.max_input_chars) for t in targets
        ]
        try:
            out_vec = vec_cache[out_key]
            t_vecs = [vec_cache[k] for k in target_keys]
            score, evidence = self._score_from_vectors(out_vec, t_vecs, np_mod=np_mod)
        except Exception as exc:
            return self._result_from_status(
                status=MetricStatus.INCONCLUSIVE,
                score=None,
                explanation=f"Invalid embedding vector comparison: {type(exc).__name__}: {exc}",
                snapshot=snapshot,
            )

        passed = score + FLOAT_EPSILON >= threshold
        status = MetricStatus.PASS if passed else MetricStatus.FAIL
        return self._result_from_status(
            status=status,
            score=score,
            explanation=(
                f"{self._metadata.metric_id} clamped cosine score {score:.6g} "
                f"{'>=' if passed else '<'} threshold {threshold:.6g}."
            ),
            snapshot=snapshot,
            evidence=evidence,
        )

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Synchronously evaluate embedding similarity for one case."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aevaluate(case, execution))

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.aevaluate(case, execution)).result()

    async def aevaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Asynchronously evaluate one case with fail-fast '[embeddings]' verification."""
        resolve_numpy()
        results = await self.aevaluate_batch([(case, execution)], max_concurrency=1)
        return results[0]

    async def aevaluate_batch(
        self,
        items: Sequence[tuple[EvaluationCase, ExecutionResult]],
        *,
        max_concurrency: int = 4,
    ) -> list[MetricResult]:
        """Batch-embed deduplicated non-blank texts and score cases with fault isolation."""
        if isinstance(max_concurrency, bool) or max_concurrency < 1:
            raise ConfigurationError(f"max_concurrency must be >= 1, got {max_concurrency!r}")
        # Q5: Fail fast whenever [embeddings] (numpy) is absent, before input short-circuits.
        np_mod = resolve_numpy()
        if not items:
            return []

        final_results: list[MetricResult | None] = [None] * len(items)
        pending_indices: list[int] = []
        unique_texts: list[str] = []
        seen_texts: set[str] = set()

        for idx, (case, execution) in enumerate(items):
            threshold = _resolve_threshold(
                case, self._metadata.metric_id, self._config.pass_threshold
            )
            snapshot = self._snapshot(threshold)
            if execution.errors:
                final_results[idx] = self._result_from_status(
                    status=MetricStatus.INCONCLUSIVE,
                    score=None,
                    explanation=f"Upstream execution failed: {execution.errors[0]}",
                    evidence=list(execution.errors),
                    snapshot=snapshot,
                )
                continue

            na_reason = self._missing_ground_truth_reason(case, execution)
            if na_reason is not None:
                final_results[idx] = self._result_from_status(
                    status=MetricStatus.NOT_APPLICABLE,
                    score=None,
                    explanation=na_reason,
                    snapshot=snapshot,
                )
                continue

            if execution.output is None or not execution.output.strip():
                passed = threshold <= FLOAT_EPSILON
                final_results[idx] = self._result_from_status(
                    status=MetricStatus.PASS if passed else MetricStatus.FAIL,
                    score=0.0,
                    explanation="Target output is empty; cosine similarity scored as 0.0.",
                    snapshot=snapshot,
                )
                continue

            out_raw, targets = self._extract_texts_for_case(case, execution)
            for raw in (out_raw, *targets):
                bounded = truncate_for_embedding(raw, max_input_chars=self._config.max_input_chars)
                if bounded not in seen_texts:
                    seen_texts.add(bounded)
                    unique_texts.append(bounded)
            pending_indices.append(idx)

        if not pending_indices:
            return [r for r in final_results if r is not None]

        # Batch-embed unique strings, isolating per case if any vector rejects in a batch.
        vec_cache: dict[str, Any] = {}
        try:
            batch_vecs = await invoke_embedding_provider(
                unique_texts,
                config=self._config,
                api_key=self._api_key,
                embed_fn=self._embed_fn,
            )
            for text, vec in zip(unique_texts, batch_vecs, strict=True):
                vec_cache[text] = vec
        except (LocalOnlyPolicyError, MissingExtraError):
            raise
        except Exception as batch_exc:
            # Retry pending cases individually so one bad vector never poisons siblings.
            sem = asyncio.Semaphore(max_concurrency)

            async def _score_one(item_idx: int) -> None:
                case, execution = items[item_idx]
                threshold = _resolve_threshold(
                    case, self._metadata.metric_id, self._config.pass_threshold
                )
                snapshot = self._snapshot(threshold)
                out_raw, targets = self._extract_texts_for_case(case, execution)
                case_texts = list(
                    dict.fromkeys(
                        truncate_for_embedding(t, max_input_chars=self._config.max_input_chars)
                        for t in (out_raw, *targets)
                    )
                )
                async with sem:
                    try:
                        vecs = await invoke_embedding_provider(
                            case_texts,
                            config=self._config,
                            api_key=self._api_key,
                            embed_fn=self._embed_fn,
                        )
                        local_cache = dict(zip(case_texts, vecs, strict=True))
                        final_results[item_idx] = self._score_single_vectors(
                            case=case,
                            execution=execution,
                            threshold=threshold,
                            snapshot=snapshot,
                            vec_cache=local_cache,
                            np_mod=np_mod,
                        )
                    except (LocalOnlyPolicyError, MissingExtraError):
                        raise
                    except Exception as exc:
                        final_results[item_idx] = self._result_from_status(
                            status=MetricStatus.INCONCLUSIVE,
                            score=None,
                            explanation=f"Embedding error: {type(exc).__name__}: {exc}",
                            snapshot=snapshot,
                        )

            _ = batch_exc
            await asyncio.gather(*(_score_one(i) for i in pending_indices))
            return [r for r in final_results if r is not None]

        for idx in pending_indices:
            case, execution = items[idx]
            threshold = _resolve_threshold(
                case, self._metadata.metric_id, self._config.pass_threshold
            )
            snapshot = self._snapshot(threshold)
            final_results[idx] = self._score_single_vectors(
                case=case,
                execution=execution,
                threshold=threshold,
                snapshot=snapshot,
                vec_cache=vec_cache,
                np_mod=np_mod,
            )

        return [r for r in final_results if r is not None]


class EmbeddingSimilarityMetric(_BaseEmbeddingSimilarityMetric):
    """Clamped cosine similarity between target output and reference answer."""

    def __init__(
        self,
        *,
        config: EmbeddingConfig | None = None,
        api_key: str | None = None,
        embed_fn: EmbeddingFn | None = None,
    ) -> None:
        meta = MetricMetadata(
            metric_id="embedding_similarity",
            metric_version="1.0.0",
            what_it_measures=(
                "Clamped cosine similarity max(0.0, cos(u, v)) between dense embeddings of "
                "ExecutionResult.output and EvaluationCase.reference."
            ),
            required_case_fields=("reference",),
            required_execution_fields=("output",),
            calculation_method=(
                "Embed target output and reference text, compute dot(u, v) / (||u|| * ||v||), "
                "and clamp negative values to [0.0, 1.0]."
            ),
            known_limitations=(
                "Captures topical and paraphrase similarity, not exact numeric accuracy, negation, "
                "or structured schema compliance."
            ),
        )
        super().__init__(metadata=meta, config=config, api_key=api_key, embed_fn=embed_fn)

    def _missing_ground_truth_reason(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> str | None:
        _ = execution
        if case.reference is None or not case.reference.strip():
            return "EvaluationCase.reference is absent; embedding_similarity is not applicable."
        return None

    def _extract_texts_for_case(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> tuple[str, list[str]]:
        return execution.output or "", [case.reference or ""]

    def _score_from_vectors(
        self,
        output_vec: Any,
        target_vecs: list[Any],
        *,
        np_mod: Any,
    ) -> tuple[float, list[str]]:
        score = clamped_cosine_similarity(output_vec, target_vecs[0], np_mod=np_mod)
        return score, [f"reference_cosine={score:.6f}"]


class ContextEmbeddingSimilarityMetric(_BaseEmbeddingSimilarityMetric):
    """Clamped cosine similarity between target output and retrieved context chunks."""

    def __init__(
        self,
        *,
        config: EmbeddingConfig | None = None,
        api_key: str | None = None,
        embed_fn: EmbeddingFn | None = None,
    ) -> None:
        meta = MetricMetadata(
            metric_id="context_embedding_similarity",
            metric_version="1.0.0",
            what_it_measures=(
                "Clamped cosine similarity max(0.0, cos(u, v)) between ExecutionResult.output "
                "and non-blank ExecutionResult.retrieved_chunks using max or mean aggregation."
            ),
            required_case_fields=(),
            required_execution_fields=("output", "retrieved_chunks"),
            calculation_method=(
                "Compute max(0.0, cos(output, chunk_i)) for each non-blank retrieved chunk and "
                "aggregate via max (default) or mean."
            ),
            known_limitations=(
                "Measures semantic overlap with retrieved chunks rather than factual entailment "
                "or claim-level groundedness."
            ),
        )
        super().__init__(metadata=meta, config=config, api_key=api_key, embed_fn=embed_fn)

    def _non_blank_chunks(self, execution: ExecutionResult) -> list[tuple[str, str]]:
        return [(c.id, c.text) for c in execution.retrieved_chunks if c.text.strip()]

    def _missing_ground_truth_reason(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> str | None:
        _ = case
        if not self._non_blank_chunks(execution):
            return (
                "ExecutionResult.retrieved_chunks has no non-blank text; "
                "context_embedding_similarity is not applicable."
            )
        return None

    def _extract_texts_for_case(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> tuple[str, list[str]]:
        _ = case
        return execution.output or "", [text for _, text in self._non_blank_chunks(execution)]

    def _score_from_vectors(
        self,
        output_vec: Any,
        target_vecs: list[Any],
        *,
        np_mod: Any,
    ) -> tuple[float, list[str]]:
        chunk_scores = [
            clamped_cosine_similarity(output_vec, cvec, np_mod=np_mod) for cvec in target_vecs
        ]
        if self._config.aggregation == EmbeddingAggregation.MEAN:
            agg = round_score(sum(chunk_scores) / len(chunk_scores))
        else:
            agg = round_score(max(chunk_scores))
        evidence = [f"aggregation={self._config.aggregation.value}", f"chunks={len(chunk_scores)}"]
        return agg, evidence
