"""Unit tests for pre-network local_only security policy, air-gap cost map, and secret hygiene."""

from __future__ import annotations

import logging
import os
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from evalforge_maestro.exceptions import LocalOnlyPolicyError, MissingExtraError
from evalforge_maestro.judges.metrics import AnswerRelevanceMetric, GroundednessMetric
from evalforge_maestro.judges.security import validate_local_only_target
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
    MetricStatus,
    RetrievedChunk,
)


def _make_fake_litellm(acompletion_fn: Any) -> Any:
    return SimpleNamespace(
        acompletion=acompletion_fn,
        telemetry=True,
        suppress_debug_info=False,
    )


def _sample_case_and_exec(case_id: str = "sec-1") -> tuple[EvaluationCase, ExecutionResult]:
    case = EvaluationCase(id=case_id, input="What is the SLA?", reference="99.9%")
    execution = ExecutionResult(
        case_id=case_id,
        input=case.input,
        output="Our SLA is 99.9%.",
        retrieved_chunks=[RetrievedChunk(id="c1", text="SLA guarantees 99.9% uptime.")],
        elapsed_seconds=0.01,
    )
    return case, execution


def test_local_only_blocks_cloud_lan_and_unspecified_hosts_pre_network() -> None:
    called = False

    async def should_never_run(**kwargs: Any) -> str:
        nonlocal called
        called = True
        return '{"score": 1.0, "rationale": "should fail earlier"}'

    blocked_configs = (
        JudgeConfig(model="openai/gpt-4o-mini", local_only=True, mock_mode=False),
        JudgeConfig(model="anthropic/claude-3-5-sonnet", local_only=True, mock_mode=False),
        JudgeConfig(
            model="openai/local-model",
            api_base="https://api.openai.com/v1",
            local_only=True,
            mock_mode=False,
        ),
        JudgeConfig(
            model="openai/local-model",
            api_base="http://192.168.1.42:8000/v1",
            local_only=True,
            mock_mode=False,
        ),
        JudgeConfig(
            model="openai/local-model",
            api_base="http://gpu-server.internal:8000",
            local_only=True,
            mock_mode=False,
        ),
        JudgeConfig(
            model="openai/local-model",
            api_base="http://0.0.0.0:8000",
            local_only=True,
            mock_mode=False,
        ),
    )

    case, execution = _sample_case_and_exec()
    for cfg in blocked_configs:
        metric = GroundednessMetric(config=cfg, completion_fn=should_never_run)
        with pytest.raises(LocalOnlyPolicyError):
            metric.evaluate(case, execution)

    assert not called


def test_local_only_respects_ollama_api_base_override_and_allows_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_BASE", "http://10.0.0.99:11434")
    with pytest.raises(LocalOnlyPolicyError):
        validate_local_only_target(
            JudgeConfig(model="ollama_chat/llama3.2", local_only=True, mock_mode=False)
        )

    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    assert (
        validate_local_only_target(
            JudgeConfig(model="ollama_chat/llama3.2", local_only=True, mock_mode=False)
        )
        == "http://localhost:11434"
    )

    for loopback_url in (
        "http://localhost:11434",
        "http://127.0.0.1:8000/v1",
        "http://[::1]:8080/v1",
        "https://localhost:8443",
    ):
        cfg = JudgeConfig(
            model="openai/local-vllm",
            api_base=loopback_url,
            local_only=True,
            mock_mode=False,
        )
        assert validate_local_only_target(cfg) == loopback_url


def test_airgap_cost_map_env_set_prior_to_litellm_import_and_missing_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP", raising=False)
    monkeypatch.delitem(sys.modules, "litellm", raising=False)

    observed_cost_map_at_call: list[str | None] = []
    captured_kwargs: dict[str, Any] = {}

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        observed_cost_map_at_call.append(os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP"))
        captured_kwargs.update(kwargs)
        return {
            "choices": [
                {"message": {"content": '{"score": 0.92, "rationale": "Loopback response valid."}'}}
            ]
        }

    fake_litellm = _make_fake_litellm(fake_acompletion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = JudgeConfig(
        model="ollama_chat/llama3.2",
        api_base="http://127.0.0.1:11434",
        local_only=True,
        mock_mode=False,
        extra_params={"top_p": 0.85},
    )
    metric = AnswerRelevanceMetric(config=cfg, api_key="sk-live-secret-token-999999")
    case, execution = _sample_case_and_exec()
    res = metric.evaluate(case, execution)

    assert res.status == MetricStatus.PASS
    assert res.score == 0.92
    assert observed_cost_map_at_call == ["True"]
    assert fake_litellm.telemetry is False
    assert captured_kwargs["api_base"] == "http://127.0.0.1:11434"
    assert captured_kwargs["top_p"] == 0.85

    # Missing litellm raises MissingExtraError with clear install hint
    monkeypatch.setitem(sys.modules, "litellm", None)
    with pytest.raises(MissingExtraError) as exc_info:
        metric.evaluate(case, execution)
    assert "evalforge-maestro[judges]" in str(exc_info.value)


def test_credentials_never_leak_into_snapshots_errors_fingerprints_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_key = "sk-proj-supersecretkeyvalue12345"

    async def failing_acompletion(**kwargs: Any) -> Any:
        raise RuntimeError(
            f"Upstream rejected Authorization: Bearer {secret_key} and api_key={secret_key}"
        )

    fake_litellm = _make_fake_litellm(failing_acompletion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    cfg = JudgeConfig(
        model="openai/gpt-4o-mini",
        max_retries=0,
        retry_backoff_seconds=0.0,
        local_only=False,
        extra_params={"api_key": secret_key},
    )
    metric_with_key = AnswerRelevanceMetric(config=cfg, api_key=secret_key)
    metric_diff_key = AnswerRelevanceMetric(config=cfg, api_key="sk-different-99999999")
    assert metric_with_key.judge_config_fingerprint == metric_diff_key.judge_config_fingerprint
    assert secret_key not in repr(cfg)
    assert secret_key not in str(cfg.redacted_dict())

    case, execution = _sample_case_and_exec()
    with caplog.at_level(logging.DEBUG, logger="evalforge_maestro"):
        res = metric_with_key.evaluate(case, execution)

    assert res.status == MetricStatus.INCONCLUSIVE
    assert res.score is None
    assert secret_key not in res.explanation
    assert secret_key not in str(res.config_snapshot)
    assert "[REDACTED]" in res.explanation
    for rec in caplog.records:
        assert secret_key not in rec.getMessage()
