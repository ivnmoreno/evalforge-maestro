"""Prompt-injection isolation, credential hygiene, and pre-network local-only security guards."""

from __future__ import annotations

import re
import secrets
from typing import Any

from evalforge_maestro._canonical import canonical_json_str
from evalforge_maestro._locality import (
    PIIGuardedAsyncBatchMetric,
    case_egress_payload,
    ensure_airgap_cost_map,
    is_loopback_host,
    is_remote_endpoint,
    validate_local_only_endpoint,
    validate_pii_egress,
)
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
)

_VALID_TAG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

__all__ = [
    "ensure_airgap_cost_map",
    "escape_untrusted_text",
    "generate_nonce",
    "is_loopback_host",
    "is_remote_judge_endpoint",
    "validate_local_only_target",
    "validate_pii_egress",
    "wrap_pii_guarded_metric",
    "wrap_untrusted_block",
]


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


def validate_local_only_target(config: JudgeConfig) -> str | None:
    """Validate pre-network endpoint locality when local_only=True and mock_mode=False."""
    return validate_local_only_endpoint(
        model=config.model,
        api_base=config.api_base,
        local_only=config.local_only,
        mock_mode=config.mock_mode,
        label="judge",
    )


def is_remote_judge_endpoint(config: JudgeConfig) -> bool:
    """Return True iff non-mock judge calls target a non-loopback remote endpoint."""
    return is_remote_endpoint(
        model=config.model,
        api_base=config.api_base,
        mock_mode=config.mock_mode,
    )


def _case_judge_payload(case: EvaluationCase, execution: ExecutionResult) -> dict[str, Any]:
    return case_egress_payload(case, execution, include_input=True)


def wrap_pii_guarded_metric(metric: Any, *, block_pii: bool) -> Any:
    """Wrap remote non-mock judge metrics with pre-network PII screening when block_pii=True."""
    if not block_pii:
        return metric
    judge_cfg = getattr(metric, "judge_config", None)
    if not isinstance(judge_cfg, JudgeConfig):
        return metric
    if not is_remote_judge_endpoint(judge_cfg):
        return metric
    return PIIGuardedAsyncBatchMetric(
        metric,
        label_prefix="judge",
        payload_builder=_case_judge_payload,
    )
