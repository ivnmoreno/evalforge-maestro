"""Unit tests for PII detection and pre-network egress blocking."""

from __future__ import annotations

import pytest

from evalforge_maestro._canonical import detect_pii_categories
from evalforge_maestro.exceptions import LocalOnlyPolicyError
from evalforge_maestro.judges.metrics import GroundednessMetric
from evalforge_maestro.judges.security import (
    is_remote_judge_endpoint,
    validate_pii_egress,
    wrap_pii_guarded_metric,
)
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
    RetrievedChunk,
)


def test_detect_pii_categories_covers_email_phone_ssn_card_and_secrets() -> None:
    payload = {
        "email": "Contact alice.smith@example.org for details.",
        "phone": "Call +1-555-234-5678 or (415) 555-0199.",
        "ssn": "TIN/SSN is 123-45-6789.",
        "card": "Visa 4111-1111-1111-1111 charged.",
        "auth": "Authorization: Bearer super_secret_token_999",
    }
    cats = detect_pii_categories(payload)
    assert cats == ["email_address", "payment_card", "phone_number", "secret_token", "us_ssn"]


def test_detect_pii_categories_ignores_non_luhn_ids_and_dates() -> None:
    clean = {
        "date": "2026-11-19",
        "trace_id": "1234567890123456",  # 16 digits failing Luhn (total = 62 mod 10 != 0)
        "all_same": "0000-0000-0000-0000",
        "score": 0.912345,
        "text": "Paris is the capital of France with 99.9% uptime SLA.",
        "api_key": "[REDACTED]",
    }
    assert detect_pii_categories(clean) == []


def test_validate_pii_egress_never_echoes_raw_pii() -> None:
    secret_email = "private.customer@secretcorp.com"
    secret_ssn = "123-45-6789"
    with pytest.raises(LocalOnlyPolicyError) as exc_info:
        validate_pii_egress(
            {"query": f"Reset password for {secret_email} ({secret_ssn})"},
            enabled=True,
            context_label="unit-test",
        )
    msg = str(exc_info.value)
    assert "email_address" in msg
    assert "us_ssn" in msg
    assert secret_email not in msg
    assert secret_ssn not in msg

    # Disabled policy permits text cleanly
    validate_pii_egress(secret_email, enabled=False, context_label="disabled")


def test_wrap_pii_guarded_metric_blocks_remote_before_completion_fn() -> None:
    called = False

    async def _should_not_run(*args: object, **kwargs: object) -> str:
        nonlocal called
        called = True
        return '{"score": 1.0, "rationale": "ok"}'

    remote_metric = GroundednessMetric(
        config=JudgeConfig(model="openai/gpt-4o-mini", mock_mode=False, local_only=False),
        completion_fn=_should_not_run,
    )
    assert is_remote_judge_endpoint(remote_metric.judge_config) is True

    guarded = wrap_pii_guarded_metric(remote_metric, block_pii=True)
    case = EvaluationCase(id="pii-1", input="Who owns account?")
    exec_res = ExecutionResult(
        case_id="pii-1",
        input="Who owns account?",
        output="Reach bob@example.org at 555-867-5309.",
        retrieved_chunks=[RetrievedChunk(id="c1", text="Support record")],
        elapsed_seconds=0.01,
    )
    with pytest.raises(LocalOnlyPolicyError):
        guarded.evaluate(case, exec_res)
    assert called is False


def test_wrap_pii_guarded_metric_leaves_mock_and_loopback_unblocked() -> None:
    mock_metric = GroundednessMetric(
        config=JudgeConfig(model="openai/gpt-4o-mini", mock_mode=True, local_only=False)
    )
    assert is_remote_judge_endpoint(mock_metric.judge_config) is False
    assert wrap_pii_guarded_metric(mock_metric, block_pii=True) is mock_metric

    ollama_local = JudgeConfig(model="ollama/llama3.2", mock_mode=False, local_only=False)
    assert is_remote_judge_endpoint(ollama_local) is False

    custom_remote = JudgeConfig(
        model="custom/model",
        api_base="https://judge.internal.example.com",
        mock_mode=False,
        local_only=False,
    )
    assert is_remote_judge_endpoint(custom_remote) is True
