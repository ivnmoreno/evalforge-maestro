"""Prompt-injection isolation, credential hygiene, and pre-network local-only security guards."""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
from typing import Any
from urllib.parse import urlparse

from evalforge_maestro._canonical import canonical_json_str, scrub_secret_text
from evalforge_maestro.exceptions import LocalOnlyPolicyError
from evalforge_maestro.types import JudgeConfig

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
