"""Lazy-loaded embedding similarity metrics behind the optional ``[embeddings]`` extra."""

from __future__ import annotations

import logging

from evalforge_maestro.embeddings.metrics import (
    ContextEmbeddingSimilarityMetric,
    EmbeddingSimilarityMetric,
)
from evalforge_maestro.embeddings.provider import EmbeddingFn

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "ContextEmbeddingSimilarityMetric",
    "EmbeddingFn",
    "EmbeddingSimilarityMetric",
]
