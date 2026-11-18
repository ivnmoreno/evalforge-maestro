"""Provider-independent LiteLLM completion wrapper, strict parser, and retry engine."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn

from pydantic import ValidationError

from evalforge_maestro._canonical import FLOAT_EPSILON, round_score, scrub_secret_text
from evalforge_maestro.exceptions import JudgeError, LocalOnlyPolicyError, MissingExtraError
from evalforge_maestro.judges.security import (
    ensure_airgap_cost_map,
    validate_local_only_target,
)
from evalforge_maestro.types import (
    JudgeConfig,
    JudgeResponse,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)

logger = logging.getLogger(__name__)

CompletionFn = Callable[..., Awaitable[str]]
_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Non-finite JSON constant is not allowed in JudgeResponse: {value!r}")


def parse_judge_response(raw_text: str) -> JudgeResponse:
    """Strictly parse raw judge output text into a bounded JudgeResponse schema."""
    if not isinstance(raw_text, str):
        raise ValueError(f"Judge output must be a string, got {type(raw_text).__name__}")
    cleaned = raw_text.strip()
    if not cleaned:
        raise ValueError("Judge output is empty")

    fenced = _CODE_FENCE_RE.match(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        parsed = json.loads(cleaned, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Judge output is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Judge JSON payload must be an object, got {type(parsed).__name__}")

    try:
        return JudgeResponse.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(f"JudgeResponse validation failed: {exc}") from exc


def _resolve_litellm(*, local_only: bool) -> Any:
    """Enforce air-gap cost map setting and lazily import optional litellm package."""
    ensure_airgap_cost_map(local_only=local_only)
    try:
        litellm_mod: Any = importlib.import_module("litellm")
    except ImportError as exc:
        raise MissingExtraError(extra="judges", package="litellm") from exc

    litellm_mod.telemetry = False
    litellm_mod.suppress_debug_info = True
    return litellm_mod


def _extract_choice_content(response: Any) -> str:
    choices = (
        response.get("choices")
        if isinstance(response, dict)
        else getattr(response, "choices", None)
    )
    if not choices:
        raise JudgeError("Judge provider returned empty choices list")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
    if message is None:
        raise JudgeError("Judge provider choice missing message payload")
    content = (
        message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    )
    if not isinstance(content, str) or not content.strip():
        raise JudgeError("Judge provider returned empty message content")
    return content


async def invoke_live_completion(
    messages: list[dict[str, str]],
    *,
    config: JudgeConfig,
    api_key: str | None = None,
    completion_fn: CompletionFn | None = None,
) -> str:
    """Execute one model completion under pre-network local_only and secret hygiene."""
    resolved_api_base = validate_local_only_target(config)

    if completion_fn is not None:
        return await completion_fn(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            api_base=resolved_api_base,
            timeout=config.timeout_seconds,
            seed=config.seed,
        )

    litellm = _resolve_litellm(local_only=config.local_only)
    call_kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "timeout": config.timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    if resolved_api_base is not None:
        call_kwargs["api_base"] = resolved_api_base
    if config.seed is not None:
        call_kwargs["seed"] = config.seed
    if api_key is not None and api_key.strip():
        call_kwargs["api_key"] = api_key
    for key, val in config.extra_params.items():
        if key not in call_kwargs:
            call_kwargs[key] = val

    try:
        response = await litellm.acompletion(**call_kwargs)
    except Exception as exc:
        msg = scrub_secret_text(f"Provider call failed: {type(exc).__name__}: {exc}")
        raise JudgeError(msg) from exc
    return _extract_choice_content(response)


async def evaluate_with_retries(
    call_once: Callable[[int], Awaitable[str]],
    *,
    config: JudgeConfig,
    effective_threshold: float,
    metadata: MetricMetadata,
    config_snapshot: dict[str, Any],
    allow_retries: bool = True,
) -> MetricResult:
    """Invoke judge evaluation with bounded retries and mandatory INCONCLUSIVE fallback."""
    max_attempts = (config.max_retries + 1) if allow_retries else 1
    last_error = "No attempts executed"

    for attempt in range(max_attempts):
        try:
            raw_text = await asyncio.wait_for(
                call_once(attempt),
                timeout=config.timeout_seconds,
            )
            parsed = parse_judge_response(raw_text)
        except (LocalOnlyPolicyError, MissingExtraError):
            raise
        except Exception as exc:
            last_error = scrub_secret_text(f"{type(exc).__name__}: {exc}")
            logger.debug(
                "Judge %s attempt %d/%d failed: %s",
                metadata.metric_id,
                attempt + 1,
                max_attempts,
                last_error,
            )
            if attempt + 1 < max_attempts:
                delay = 0.0 if config.mock_mode else config.retry_backoff_seconds * (2**attempt)
                if delay > 0.0:
                    await asyncio.sleep(delay)
            continue

        score = round_score(parsed.score)
        passed = score >= effective_threshold - FLOAT_EPSILON
        status = MetricStatus.PASS if passed else MetricStatus.FAIL
        evidence = list(parsed.supported_claims) + [
            f"UNSUPPORTED: {claim}" for claim in parsed.unsupported_claims
        ]
        anomaly_flags: list[str] = []
        if passed and parsed.unsupported_claims:
            anomaly_flags.append("unsupported_claims_present")

        return MetricResult(
            metric_id=metadata.metric_id,
            metric_version=metadata.metric_version,
            score=score,
            status=status,
            label=parsed.verdict or ("pass" if passed else "fail"),
            explanation=scrub_secret_text(parsed.rationale),
            evidence=evidence,
            anomaly_flags=anomaly_flags,
            config_snapshot=config_snapshot,
        )

    return MetricResult(
        metric_id=metadata.metric_id,
        metric_version=metadata.metric_version,
        score=None,
        status=MetricStatus.INCONCLUSIVE,
        explanation=f"INCONCLUSIVE after {max_attempts} attempt(s): {last_error}",
        config_snapshot=config_snapshot,
    )
