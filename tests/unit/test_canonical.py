"""Unit tests for canonical JSON serialization, hashing, rounding, and redaction."""

from __future__ import annotations

import math

import pytest

from evalforge_maestro._canonical import (
    REDACTED_VALUE,
    StreamingCanonicalHasher,
    canonical_json_bytes,
    canonical_json_str,
    canonical_sha256,
    redact_secrets,
    round_delta,
    round_score,
)


def test_round_score_precision_and_epsilon_clamping() -> None:
    assert round_score(0.123456789) == 0.123457
    assert round_score(-1e-12) == 0.0
    assert round_score(1.0 + 1e-12) == 1.0
    assert math.copysign(1.0, round_score(-0.0)) == 1.0

    with pytest.raises(ValueError, match="finite"):
        round_score(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        round_score(float("inf"))


def test_round_delta_precision_signed_and_negative_zero_normalization() -> None:
    assert round_delta(-0.123456789) == -0.123457
    assert round_delta(0.8 - 0.5) == 0.3
    assert round_delta(-0.0) == 0.0
    assert math.copysign(1.0, round_delta(-0.0)) == 1.0
    assert math.copysign(1.0, round_delta(-1e-12)) == 1.0
    assert round_delta(1e-12) == 0.0

    with pytest.raises(ValueError, match="finite"):
        round_delta(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        round_delta(float("-inf"))


def test_canonical_json_and_hashing_are_key_order_invariant() -> None:
    a = {"b": 2, "a": {"y": "héllo", "x": [1, 2]}}
    b = {"a": {"x": [1, 2], "y": "héllo"}, "b": 2}

    assert canonical_json_str(a) == canonical_json_str(b)
    assert canonical_json_bytes(a) == canonical_json_bytes(b)
    assert canonical_sha256(a) == canonical_sha256(b)

    pretty = canonical_json_str(a, pretty=True)
    assert pretty.endswith("\n")
    assert "\r\n" not in pretty

    with pytest.raises(ValueError):
        canonical_json_str({"bad": float("nan")})


def test_streaming_canonical_hasher_matches_expected_stream() -> None:
    stream_a = StreamingCanonicalHasher()
    stream_b = StreamingCanonicalHasher()
    stream_a.update({"id": "1", "val": "x"})
    stream_a.update({"id": "2", "val": "y"})
    stream_b.update({"val": "x", "id": "1"})
    stream_b.update({"val": "y", "id": "2"})

    assert stream_a.count == 2
    assert stream_a.hexdigest() == stream_b.hexdigest()

    stream_c = StreamingCanonicalHasher()
    stream_c.update({"id": "2", "val": "y"})
    stream_c.update({"id": "1", "val": "x"})
    assert stream_a.hexdigest() != stream_c.hexdigest()


def test_redact_secrets_masks_credentials_without_false_positives() -> None:
    payload = {
        "model": "gpt-4o",
        "max_tokens": 512,
        "prompt_tokens": 100,
        "api_key": "sk-secret",
        "openai_api_key": "sk-another",
        "headers": {"Authorization": "Bearer xyz", "X-Custom": "ok"},
        "nested": ({"client_secret": "shh", "password": "pw", "temperature": 0.0},),
        "tokens": {"total_tokens": 200, "auth_token": "tok-123"},
    }
    redacted = redact_secrets(payload)
    assert redacted["model"] == "gpt-4o"
    assert redacted["max_tokens"] == 512
    assert redacted["prompt_tokens"] == 100
    assert redacted["api_key"] == REDACTED_VALUE
    assert redacted["openai_api_key"] == REDACTED_VALUE
    assert redacted["headers"]["Authorization"] == REDACTED_VALUE
    assert redacted["headers"]["X-Custom"] == "ok"
    assert redacted["nested"][0]["client_secret"] == REDACTED_VALUE
    assert redacted["nested"][0]["password"] == REDACTED_VALUE
    assert redacted["nested"][0]["temperature"] == 0.0
    assert redacted["tokens"]["total_tokens"] == 200
    assert redacted["tokens"]["auth_token"] == REDACTED_VALUE
