"""Canonical JSON serialization, SHA-256 hashing, numeric rounding, and secret redaction."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

SCORE_ROUND_DECIMALS = 6
FLOAT_EPSILON = 1e-9
REDACTED_VALUE = "[REDACTED]"

_EXACT_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "private_key",
        "access_key",
        "secret_key",
        "client_secret",
        "bearer",
    }
)
_SECRET_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_token",
    "_secret",
    "_password",
    "_passwd",
    "_private_key",
    "_access_key",
    "_secret_key",
    "_credential",
    "_credentials",
)
_KEY_NORMALIZE_RE = re.compile(r"[\s\-]+")


def round_score(value: float) -> float:
    """Validate finiteness, clamp IEEE-754 boundary noise, and round to 6 decimals."""
    if not math.isfinite(value):
        raise ValueError(f"Metric score must be finite, got {value!r}")
    if -FLOAT_EPSILON <= value < 0.0:
        value = 0.0
    elif 1.0 < value <= 1.0 + FLOAT_EPSILON:
        value = 1.0
    rounded = round(float(value), SCORE_ROUND_DECIMALS)
    return 0.0 if rounded == 0.0 else rounded


def canonical_json_str(payload: Any, *, pretty: bool = False) -> str:
    """Serialize payload to canonical JSON with sorted keys and LF endings."""
    if pretty:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        return f"{serialized}\n"
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(payload: Any, *, pretty: bool = False) -> bytes:
    """Encode canonical JSON as UTF-8 bytes."""
    return canonical_json_str(payload, pretty=pretty).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    """Compute a lowercase hex SHA-256 digest over canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class StreamingCanonicalHasher:
    """Incremental SHA-256 hasher over newline-delimited canonical JSON records."""

    def __init__(self) -> None:
        self._hasher = hashlib.sha256()
        self._count = 0

    def update(self, payload: Any) -> None:
        """Feed one JSON-serializable record into the canonical SHA-256 stream."""
        self._hasher.update(canonical_json_bytes(payload))
        self._hasher.update(b"\n")
        self._count += 1

    @property
    def count(self) -> int:
        """Return number of hashed records."""
        return self._count

    def hexdigest(self) -> str:
        """Return the cumulative lowercase hex SHA-256 digest."""
        return self._hasher.hexdigest()


def _is_sensitive_key(key: str) -> bool:
    normalized = _KEY_NORMALIZE_RE.sub("_", key.strip().lower())
    if normalized in _EXACT_SECRET_KEYS:
        return True
    if normalized.endswith(_SECRET_SUFFIXES):
        return True
    return "api_key" in normalized or "apikey" in normalized or "client_secret" in normalized


def redact_secrets(value: Any) -> Any:
    """Recursively mask sensitive credential keys inside mappings and sequences."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_val in value.items():
            key_str = str(raw_key)
            if _is_sensitive_key(key_str):
                sanitized[key_str] = REDACTED_VALUE
            else:
                sanitized[key_str] = redact_secrets(raw_val)
        return sanitized
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value
