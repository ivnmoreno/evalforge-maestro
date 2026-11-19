"""Prompt-injection isolation, credential hygiene, and pre-network local-only security guards."""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from evalforge_maestro._canonical import (
    canonical_json_str,
    detect_pii_categories,
    scrub_secret_text,
)
from evalforge_maestro.exceptions import LocalOnlyPolicyError
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
    MetricMetadata,
    MetricResult,
)

_VALID_TAG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")


def generate_nonce() -> str:
    """Return a cryptographically random 16-char hex delimiter nonce."""
    return secrets.token_hex(8)


def escape_untrusted_text(text: str, *, nonce: str | None = None) -> str:
    """Neutralize XML tag breakouts and accidental nonce collisions in untrusted payloads."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if nonce and nonce in escaped:
        escaped = escaped.replace(nonce, "[NONCE_REDACTED]")
    return escaped


def wrap_untrusted_block(tag_name: str, content: Any, *, nonce: str) -> str:
    """Wrap untrusted content in randomized nonce-tagged XML boundaries."""
    if not _VALID_TAG_RE.match(tag_name):
        raise ValueError(f"Invalid untrusted XML delimiter tag name: {tag_name!r}")
    if not nonce or not nonce.strip():
        raise ValueError("Delimiter nonce must be a non-empty string")
    raw = (
        content
        if isinstance(content, str)
        else canonical_json_str(content, pretty=True).rstrip("\n")
    )
    safe_body = escape_untrusted_text(raw, nonce=nonce)
    return f'<{tag_name} nonce="{nonce}">\n{safe_body}\n</{tag_name}>'


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


def validate_local_only_target(config: JudgeConfig) -> str | None:
    """Validate pre-network endpoint locality when local_only=True and mock_mode=False.

    Returns resolved target api_base URL (or config.api_base unchanged when allowed).
    Raises LocalOnlyPolicyError prior to any network import or socket operation.
    """
    if not config.local_only or config.mock_mode:
        return config.api_base

    model_lower = config.model.lower()
    if config.api_base is not None:
        target_url = config.api_base
    elif model_lower.startswith(_OLLAMA_PREFIXES):
        env_ollama_base = os.environ.get("OLLAMA_API_BASE", "").strip()
        target_url = env_ollama_base or "http://localhost:11434"
    else:
        raise LocalOnlyPolicyError(
            f"local_only policy blocked remote judge model {config.model!r}: "
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


def ensure_airgap_cost_map(*, local_only: bool) -> None:
    """Force LiteLLM offline bundled model cost-map lookup prior to importing litellm."""
    if local_only:
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    else:
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


def is_remote_judge_endpoint(config: JudgeConfig) -> bool:
    """Return True iff non-mock judge calls target a non-loopback remote endpoint."""
    if config.mock_mode:
        return False
    model_lower = config.model.lower()
    if config.api_base is not None:
        target_url = config.api_base
    elif model_lower.startswith(_OLLAMA_PREFIXES):
        target_url = os.environ.get("OLLAMA_API_BASE", "").strip() or "http://localhost:11434"
    else:
        return True

    parsed = urlparse(target_url)
    host = parsed.hostname
    return not host or not is_loopback_host(host)


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


def _case_judge_payload(case: EvaluationCase, execution: ExecutionResult) -> dict[str, Any]:
    return {
        "input": case.input,
        "output": execution.output,
        "reference": case.reference,
        "retrieved_chunks": [chunk.text for chunk in execution.retrieved_chunks],
    }


class _PIIGuardedJudgeMetric:
    """Delegating judge metric wrapper enforcing pre-network PII screening on remote judges."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def metadata(self) -> MetricMetadata:
        return self._inner.metadata  # type: ignore[no-any-return]

    @property
    def judge_config(self) -> JudgeConfig:
        return self._inner.judge_config  # type: ignore[no-any-return]

    @property
    def judge_config_fingerprint(self) -> str | None:
        return self._inner.judge_config_fingerprint  # type: ignore[no-any-return]

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        validate_pii_egress(
            _case_judge_payload(case, execution),
            enabled=True,
            context_label=f"judge {self.metadata.metric_id!r} case {case.id!r}",
        )
        return self._inner.evaluate(case, execution)  # type: ignore[no-any-return]

    async def aevaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        validate_pii_egress(
            _case_judge_payload(case, execution),
            enabled=True,
            context_label=f"judge {self.metadata.metric_id!r} case {case.id!r}",
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
                _case_judge_payload(case, execution),
                enabled=True,
                context_label=f"judge {self.metadata.metric_id!r} case {case.id!r}",
            )
        return await self._inner.aevaluate_batch(items, max_concurrency=max_concurrency)  # type: ignore[no-any-return]


def wrap_pii_guarded_metric(metric: Any, *, block_pii: bool) -> Any:
    """Wrap remote non-mock judge metrics with pre-network PII screening when block_pii=True."""
    if not block_pii:
        return metric
    judge_cfg = getattr(metric, "judge_config", None)
    if not isinstance(judge_cfg, JudgeConfig):
        return metric
    if not is_remote_judge_endpoint(judge_cfg):
        return metric
    return _PIIGuardedJudgeMetric(metric)
