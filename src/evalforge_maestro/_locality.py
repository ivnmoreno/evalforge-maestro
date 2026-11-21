"""Shared leaf-safe pre-network locality, air-gap, and PII egress security helpers."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlparse

from evalforge_maestro._canonical import detect_pii_categories, scrub_secret_text
from evalforge_maestro.exceptions import LocalOnlyPolicyError
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
)

_OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")


def is_loopback_host(hostname: str) -> bool:
    """Return True iff hostname resolves syntactically to localhost or a loopback IP."""
    normalized = hostname.strip().lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return addr.is_loopback


def validate_local_only_endpoint(
    *,
    model: str,
    api_base: str | None,
    local_only: bool,
    mock_mode: bool,
    label: str = "judge",
) -> str | None:
    """Validate pre-network endpoint locality when local_only=True and mock_mode=False.

    Returns resolved target api_base URL (or api_base unchanged when permitted).
    Raises LocalOnlyPolicyError prior to any optional dependency import or network operation.
    """
    if not local_only or mock_mode:
        return api_base

    model_lower = model.lower()
    if api_base is not None:
        target_url = api_base
    elif model_lower.startswith(_OLLAMA_PREFIXES):
        env_ollama_base = os.environ.get("OLLAMA_API_BASE", "").strip()
        target_url = env_ollama_base or "http://localhost:11434"
    else:
        raise LocalOnlyPolicyError(
            f"local_only policy blocked remote {label} model {model!r}: "
            "configure mock_mode=True or an explicit loopback api_base "
            "(localhost, 127.0.0.1, ::1)."
        )

    parsed = urlparse(target_url)
    host = parsed.hostname
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or not is_loopback_host(host)
    ):
        raise LocalOnlyPolicyError(
            f"local_only policy blocked non-loopback endpoint {scrub_secret_text(target_url)!r}: "
            "only localhost, 127.0.0.1, and ::1 are permitted."
        )
    return target_url


def is_remote_endpoint(
    *,
    model: str,
    api_base: str | None,
    mock_mode: bool,
) -> bool:
    """Return True iff non-mock endpoint configuration targets a non-loopback host."""
    if mock_mode:
        return False
    model_lower = model.lower()
    if api_base is not None:
        target_url = api_base
    elif model_lower.startswith(_OLLAMA_PREFIXES):
        target_url = os.environ.get("OLLAMA_API_BASE", "").strip() or "http://localhost:11434"
    else:
        return True

    parsed = urlparse(target_url)
    host = parsed.hostname
    return not host or not is_loopback_host(host)


def ensure_airgap_cost_map(*, local_only: bool) -> None:
    """Force LiteLLM offline bundled model cost-map lookup prior to importing litellm."""
    if local_only:
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    else:
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


def validate_pii_egress(
    value: Any,
    *,
    enabled: bool = True,
    context_label: str = "outbound payload",
) -> None:
    """Block sensitive PII or credential egress before transmission without logging raw values."""
    if not enabled:
        return
    categories = detect_pii_categories(value)
    if categories:
        raise LocalOnlyPolicyError(
            f"Outbound PII/credential egress blocked on {context_label} "
            f"(detected categories: {', '.join(categories)}; raw matched text omitted)."
        )


def case_egress_payload(
    case: EvaluationCase,
    execution: ExecutionResult,
    *,
    include_input: bool = True,
) -> dict[str, Any]:
    """Build sanitized payload mapping inspected by pre-network PII egress checks."""
    payload: dict[str, Any] = {
        "output": execution.output,
        "reference": case.reference,
        "retrieved_chunks": [chunk.text for chunk in execution.retrieved_chunks],
    }
    if include_input:
        payload["input"] = case.input
    return payload


class PIIGuardedAsyncBatchMetric:
    """Generic delegating metric wrapper enforcing pre-network PII screening before scoring."""

    def __init__(
        self,
        inner: Any,
        *,
        label_prefix: str,
        payload_builder: Callable[[EvaluationCase, ExecutionResult], dict[str, Any]],
    ) -> None:
        self._inner = inner
        self._label_prefix = label_prefix
        self._payload_builder = payload_builder

    @property
    def metadata(self) -> MetricMetadata:
        return self._inner.metadata  # type: ignore[no-any-return]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        validate_pii_egress(
            self._payload_builder(case, execution),
            enabled=True,
            context_label=f"{self._label_prefix} {self.metadata.metric_id!r} case {case.id!r}",
        )
        return self._inner.evaluate(case, execution)  # type: ignore[no-any-return]

    async def aevaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        validate_pii_egress(
            self._payload_builder(case, execution),
            enabled=True,
            context_label=f"{self._label_prefix} {self.metadata.metric_id!r} case {case.id!r}",
        )
        return await self._inner.aevaluate(case, execution)  # type: ignore[no-any-return]

    async def aevaluate_batch(
        self,
        items: Sequence[tuple[EvaluationCase, ExecutionResult]],
        *,
        max_concurrency: int = 4,
    ) -> list[MetricResult]:
        for case, execution in items:
            validate_pii_egress(
                self._payload_builder(case, execution),
                enabled=True,
                context_label=f"{self._label_prefix} {self.metadata.metric_id!r} case {case.id!r}",
            )
        return await self._inner.aevaluate_batch(items, max_concurrency=max_concurrency)  # type: ignore[no-any-return]
