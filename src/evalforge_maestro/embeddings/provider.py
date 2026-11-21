"""Lazy embedding backend resolution, retries, clamped cosine math, and PII guards."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from evalforge_maestro._canonical import round_score, scrub_secret_text
from evalforge_maestro._locality import (
    PIIGuardedAsyncBatchMetric,
    case_egress_payload,
    ensure_airgap_cost_map,
    is_remote_endpoint,
    validate_local_only_endpoint,
)
from evalforge_maestro.embeddings.mock import embed_texts_mock
from evalforge_maestro.exceptions import MetricError, MissingExtraError
from evalforge_maestro.types import EmbeddingConfig, EvaluationCase, ExecutionResult

EmbeddingFn = Callable[
    [list[str]],
    Awaitable[Sequence[Sequence[float]]] | Sequence[Sequence[float]],
]

_NORM_EPSILON = 1e-12


def resolve_numpy() -> Any:
    """Lazily import numpy or raise MissingExtraError instructing '[embeddings]' install."""
    try:
        return importlib.import_module("numpy")
    except ImportError as exc:
        raise MissingExtraError(extra="embeddings", package="numpy") from exc


def resolve_litellm(*, local_only: bool) -> Any:
    """Enforce air-gap cost map setting and lazily import litellm."""
    ensure_airgap_cost_map(local_only=local_only)
    try:
        mod: Any = importlib.import_module("litellm")
    except ImportError as exc:
        raise MissingExtraError(extra="embeddings", package="litellm") from exc

    mod.telemetry = False
    mod.suppress_debug_info = True
    return mod


def validate_embedding_local_only(config: EmbeddingConfig) -> str | None:
    """Enforce pre-network endpoint locality when local_only=True and mock_mode=False."""
    return validate_local_only_endpoint(
        model=config.model,
        api_base=config.api_base,
        local_only=config.local_only,
        mock_mode=config.mock_mode,
        label="embedding",
    )


def is_remote_embedding_endpoint(config: EmbeddingConfig) -> bool:
    """Return True iff non-mock embedding calls target a non-loopback endpoint."""
    return is_remote_endpoint(
        model=config.model,
        api_base=config.api_base,
        mock_mode=config.mock_mode,
    )


def truncate_for_embedding(text: str, *, max_input_chars: int | None) -> str:
    """Deterministically bound oversized inputs prior to embedding requests."""
    if max_input_chars is not None and len(text) > max_input_chars:
        return text[:max_input_chars]
    return text


def to_valid_vector(raw_vec: Any, *, np_mod: Any) -> Any:
    """Validate and convert an embedding vector into a finite 1D non-zero float64 array."""
    vec = np_mod.asarray(raw_vec, dtype=np_mod.float64)
    if getattr(vec, "ndim", 1) != 1 or len(vec) == 0:
        raise ValueError("Embedding vector must be a non-empty 1D sequence")
    if not bool(np_mod.isfinite(vec).all()):
        raise ValueError("Embedding vector contains non-finite values (NaN or Inf)")
    norm = float(np_mod.linalg.norm(vec))
    if not (norm > _NORM_EPSILON):
        raise ValueError("Embedding vector has zero L2 norm")
    return vec


def clamped_cosine_similarity(vec_a: Any, vec_b: Any, *, np_mod: Any) -> float:
    """Compute max(0.0, cos(u, v)) in [0.0, 1.0] across two validated unit/non-zero vectors."""
    a = to_valid_vector(vec_a, np_mod=np_mod)
    b = to_valid_vector(vec_b, np_mod=np_mod)
    if a.shape != b.shape:
        raise ValueError(f"Embedding dimension mismatch: {a.shape} vs {b.shape}")
    denom = float(np_mod.linalg.norm(a)) * float(np_mod.linalg.norm(b))
    cos = float(np_mod.dot(a, b)) / denom
    clamped = max(0.0, min(1.0, cos))
    return round_score(clamped)


def _extract_litellm_vectors(response: Any) -> list[Sequence[float]]:
    data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        raise MetricError("Embedding provider response missing 'data' sequence")
    vectors: list[Sequence[float]] = []
    for item in data:
        emb = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
        if emb is None:
            raise MetricError("Embedding provider item missing 'embedding' vector")
        vectors.append(emb)
    return vectors


async def _call_embed_once(
    texts: list[str],
    *,
    config: EmbeddingConfig,
    resolved_api_base: str | None,
    api_key: str | None,
    embed_fn: EmbeddingFn | None,
) -> Sequence[Sequence[float]]:
    if embed_fn is not None:
        raw = embed_fn(texts)
        if inspect.isawaitable(raw):
            return await asyncio.wait_for(raw, timeout=config.timeout_seconds)
        return raw

    litellm_mod = resolve_litellm(local_only=config.local_only)
    kwargs: dict[str, Any] = {
        "model": config.model,
        "input": texts,
        "timeout": config.timeout_seconds,
    }
    if resolved_api_base is not None:
        kwargs["api_base"] = resolved_api_base
    if api_key is not None:
        kwargs["api_key"] = api_key
    response = await litellm_mod.aembedding(**kwargs)
    return _extract_litellm_vectors(response)


async def invoke_embedding_provider(
    texts: Sequence[str],
    *,
    config: EmbeddingConfig,
    api_key: str | None = None,
    embed_fn: EmbeddingFn | None = None,
) -> list[Any]:
    """Resolve numpy lazily and compute vectors via --mock, custom callable, or LiteLLM."""
    np_mod = resolve_numpy()
    bounded = [truncate_for_embedding(t, max_input_chars=config.max_input_chars) for t in texts]
    if not bounded:
        return []

    if config.mock_mode:
        return embed_texts_mock(bounded, np_mod)

    resolved_api_base = (
        validate_embedding_local_only(config) if embed_fn is None else config.api_base
    )
    last_exc: Exception | None = None
    attempts = config.max_retries + 1

    for attempt in range(attempts):
        try:
            raw_vectors = await _call_embed_once(
                bounded,
                config=config,
                resolved_api_base=resolved_api_base,
                api_key=api_key,
                embed_fn=embed_fn,
            )
            if len(raw_vectors) != len(bounded):
                raise ValueError(
                    f"Embedding provider returned {len(raw_vectors)} vector(s) for "
                    f"{len(bounded)} input text(s)"
                )
            return [to_valid_vector(vec, np_mod=np_mod) for vec in raw_vectors]
        except MissingExtraError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts and config.retry_backoff_seconds > 0.0:
                await asyncio.sleep(config.retry_backoff_seconds * (2**attempt))

    safe_err = scrub_secret_text(f"{type(last_exc).__name__}: {last_exc}")
    raise MetricError(f"Embedding retrieval failed after {attempts} attempt(s): {safe_err}")


def _case_embedding_payload(case: EvaluationCase, execution: ExecutionResult) -> dict[str, Any]:
    return case_egress_payload(case, execution, include_input=False)


def wrap_pii_guarded_embedding_metric(metric: Any, *, block_pii: bool) -> Any:
    """Wrap remote non-mock embedding metrics with pre-network PII screening."""
    if not block_pii:
        return metric
    emb_cfg = getattr(metric, "embedding_config", None)
    if not isinstance(emb_cfg, EmbeddingConfig):
        return metric
    if not is_remote_embedding_endpoint(emb_cfg):
        return metric
    return PIIGuardedAsyncBatchMetric(
        metric,
        label_prefix="embedding",
        payload_builder=_case_embedding_payload,
    )
