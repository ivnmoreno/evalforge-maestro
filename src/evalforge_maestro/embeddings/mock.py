"""Deterministic offline mock embedding vector generation via SHA-256 feature hashing."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DEFAULT_DIM = 64


def _add_hashed_feature(vec: Any, feature: str, weight: float, dim: int) -> None:
    digest = hashlib.sha256(feature.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % dim
    sign = 1.0 if (digest[4] & 1) == 0 else -1.0
    vec[bucket] = float(vec[bucket]) + sign * weight


def generate_mock_embedding(
    text: str,
    np_mod: Any,
    *,
    dim: int = _DEFAULT_DIM,
) -> Any:
    """Return a deterministic L2-normalized mock embedding vector for text."""
    vec = np_mod.zeros(dim, dtype=np_mod.float64)
    stripped = text.strip().lower()
    if not stripped:
        return vec

    tokens = _TOKEN_RE.findall(stripped)
    for token in tokens:
        _add_hashed_feature(vec, f"w:{token}", 1.0, dim)
        if len(token) >= 3:
            for idx in range(len(token) - 2):
                _add_hashed_feature(vec, f"c:{token[idx : idx + 3]}", 0.5, dim)
        else:
            _add_hashed_feature(vec, f"c:{token}", 0.5, dim)

    if not tokens:
        # Fallback for punctuation-only non-blank text so orthogonal symbols score 0.0 cleanly.
        _add_hashed_feature(vec, f"raw:{stripped}", 1.0, dim)

    norm = float(np_mod.linalg.norm(vec))
    if norm <= 1e-12:  # pragma: no cover - hash bucket collision fallback guard
        _add_hashed_feature(vec, f"fallback:{stripped}", 1.0, dim)
        norm = float(np_mod.linalg.norm(vec))
    return vec / norm


def embed_texts_mock(
    texts: Sequence[str],
    np_mod: Any,
    *,
    dim: int = _DEFAULT_DIM,
) -> list[Any]:
    """Generate deterministic unit mock vectors for a sequence of texts."""
    return [generate_mock_embedding(text, np_mod, dim=dim) for text in texts]
