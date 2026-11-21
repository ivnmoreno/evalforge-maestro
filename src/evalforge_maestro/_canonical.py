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
_BEARER_TOKEN_RE = re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._\-+/=]+")
_PROVIDER_TOKEN_RE = re.compile(
    r"\b(?:sk-(?:proj-|live-|test-|svcacct-|ant-)?[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{20,}|hf_[A-Za-z0-9]{10,}|gsk_[A-Za-z0-9]{10,})\b"
)
_KV_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|passphrase|access[_-]?key|secret[_-]?key|client[_-]?secret|authorization)\b(\s*[=:]\s*)([^\s&'\",;]+)"
)
_URL_USERINFO_RE = re.compile(r"(https?://)([^:@/\s]+):([^@/\s]+)@")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_US_SSN_RE = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3}[\s.-])\s*\d{3}[\s.-]\d{4}\b|"
    r"\+[1-9]\d{0,2}[\s.-](?:\d[\s.-]?){7,12}\d\b"
)
_PAYMENT_CARD_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


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


def round_percentage(value: float) -> float:
    """Validate finiteness in [0.0, 100.0] with epsilon clamp and round to 6 decimals."""
    if not math.isfinite(value):
        raise ValueError(f"Percentage value must be finite, got {value!r}")
    if -FLOAT_EPSILON <= value < 0.0:
        value = 0.0
    elif 100.0 < value <= 100.0 + FLOAT_EPSILON:
        value = 100.0
    if not (0.0 <= value <= 100.0):
        raise ValueError(f"Percentage value must be within [0.0, 100.0], got {value!r}")
    rounded = round(float(value), SCORE_ROUND_DECIMALS)
    return 0.0 if rounded == 0.0 else rounded


def round_delta(value: float) -> float:
    """Validate finiteness, zero near-zero noise, and round signed values to 6 decimals."""
    if not math.isfinite(value):
        raise ValueError(f"Regression delta or slope must be finite, got {value!r}")
    if abs(value) <= FLOAT_EPSILON:
        return 0.0
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


def is_sensitive_key(key: str) -> bool:
    """Return True if mapping/config key name denotes a credential or secret."""
    normalized = _KEY_NORMALIZE_RE.sub("_", key.strip().lower())
    if normalized.endswith("_configured"):
        return False
    if normalized in _EXACT_SECRET_KEYS:
        return True
    if normalized.endswith(_SECRET_SUFFIXES):
        return True
    return "api_key" in normalized or "apikey" in normalized or "client_secret" in normalized


def _is_luhn_valid(digits: str) -> bool:
    if not (13 <= len(digits) <= 19) or not digits.isdigit():
        return False
    if len(set(digits)) == 1:
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        num = int(ch)
        if idx % 2 == 1:
            num *= 2
            if num > 9:
                num -= 9
        total += num
    return total % 10 == 0


def _collect_pii_categories(value: Any, categories: set[str]) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if hasattr(value, "model_dump") and callable(value.model_dump):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        for raw_key, raw_val in value.items():
            key_str = str(raw_key)
            if (
                is_sensitive_key(key_str)
                and isinstance(raw_val, str)
                and raw_val.strip()
                and raw_val.strip() != REDACTED_VALUE
            ):
                categories.add("secret_token")
            _collect_pii_categories(raw_val, categories)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_pii_categories(item, categories)
        return
    text = str(value)
    if _EMAIL_RE.search(text):
        categories.add("email_address")
    if _US_SSN_RE.search(text):
        categories.add("us_ssn")
    if _PHONE_RE.search(text):
        categories.add("phone_number")
    for match in _PAYMENT_CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if _is_luhn_valid(digits):
            categories.add("payment_card")
            break
    if (
        _PROVIDER_TOKEN_RE.search(text)
        or _BEARER_TOKEN_RE.search(text)
        or _URL_USERINFO_RE.search(text)
        or _KV_SECRET_RE.search(text)
    ):
        categories.add("secret_token")


def detect_pii_categories(value: Any) -> list[str]:
    """Return sorted PII and secret category names found in value without returning raw matches."""
    found: set[str] = set()
    _collect_pii_categories(value, found)
    return sorted(found)


def redact_secrets(value: Any) -> Any:
    """Recursively mask sensitive credential keys inside mappings and sequences."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_val in value.items():
            key_str = str(raw_key)
            if is_sensitive_key(key_str):
                sanitized[key_str] = REDACTED_VALUE
            else:
                sanitized[key_str] = redact_secrets(raw_val)
        return sanitized
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value


def scrub_secret_text(text: str) -> str:
    """Scrub embedded provider keys, bearer tokens, and URL credentials from text."""
    cleaned = _URL_USERINFO_RE.sub(rf"\1{REDACTED_VALUE}:{REDACTED_VALUE}@", text)
    cleaned = _BEARER_TOKEN_RE.sub(rf"\1 {REDACTED_VALUE}", cleaned)
    cleaned = _PROVIDER_TOKEN_RE.sub(REDACTED_VALUE, cleaned)
    cleaned = _KV_SECRET_RE.sub(rf"\1\2{REDACTED_VALUE}", cleaned)
    return cleaned
