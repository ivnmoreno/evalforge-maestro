"""Internal shared helpers for target adapters."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from evalforge_maestro._canonical import canonical_sha256, redact_secrets
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    RetrievedChunk,
    TokenUsage,
)


def redact_adapter_config(
    config: Mapping[str, Any] | None,
) -> tuple[str | None, dict[str, Any]]:
    """Redact credentials in adapter config and return (config_fingerprint, adapter_metadata)."""
    if config is None:
        return None, {}
    redacted = redact_secrets(dict(config))
    return canonical_sha256(redacted), {"config": redacted}


def validate_callable_target_options(
    fn: Any,
    *,
    adapter_name: str,
    pass_case: bool,
    input_mapper: Callable[[EvaluationCase], Any] | None,
) -> bool:
    """Validate callable adapter arguments and return True if target is a coroutine function."""
    if not callable(fn):
        raise AdapterError(f"{adapter_name} requires a callable target")
    if pass_case and input_mapper is not None:
        raise AdapterError("Cannot specify both pass_case=True and input_mapper")
    return inspect.iscoroutinefunction(fn)


def build_target_arg(
    case: EvaluationCase,
    *,
    pass_case: bool,
    input_mapper: Callable[[EvaluationCase], Any] | None,
) -> Any:
    """Resolve argument passed to a wrapped callable from an EvaluationCase."""
    if input_mapper is not None:
        return input_mapper(case)
    if pass_case:
        return case
    return case.input


async def invoke_callable(
    fn: Callable[..., Any],
    arg: Any,
    *,
    is_coro_fn: bool,
) -> Any:
    """Invoke a sync, async, or awaitable-returning target without blocking the event loop."""
    if is_coro_fn:
        return await fn(arg)
    raw = await asyncio.to_thread(fn, arg)
    if inspect.isawaitable(raw):
        return await raw
    return raw


async def invoke_function(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke an arbitrary sync/async callable cleanly inside async execution."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    raw = await asyncio.to_thread(fn, *args, **kwargs)
    if inspect.isawaitable(raw):
        return await raw
    return raw


def normalize_token_usage(raw: Any) -> TokenUsage | None:
    """Normalize dict, object, or TokenUsage payload into a validated TokenUsage contract."""
    if raw is None:
        return None
    if isinstance(raw, TokenUsage):
        return raw

    def _pick(obj: Any, *keys: str) -> Any:
        for key in keys:
            if isinstance(obj, Mapping):
                if key in obj:
                    return obj[key]
            elif hasattr(obj, key):
                return getattr(obj, key)
        return None

    if isinstance(raw, (str, bytes)):
        raise AdapterError(f"Expected mapping or object for TokenUsage, got {type(raw).__name__}")

    has_known_field = any(
        (key in raw if isinstance(raw, Mapping) else hasattr(raw, key))
        for key in (
            "prompt_tokens",
            "input_tokens",
            "completion_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        )
    )
    if isinstance(raw, Mapping) and not raw:
        return TokenUsage()
    if not has_known_field:
        raise AdapterError(f"Payload {raw!r} exposes no recognized TokenUsage fields")

    return TokenUsage(
        prompt_tokens=_pick(raw, "prompt_tokens", "input_tokens"),
        completion_tokens=_pick(raw, "completion_tokens", "output_tokens"),
        reasoning_tokens=_pick(raw, "reasoning_tokens"),
        total_tokens=_pick(raw, "total_tokens"),
    )


def build_validated_execution_result(
    *,
    case: EvaluationCase,
    output: Any,
    retrieved_chunks: Sequence[RetrievedChunk],
    tokens: TokenUsage | None,
    elapsed_seconds: float,
    truncated: bool,
    errors: list[str],
    warnings: list[str],
    system_version: str | None,
    model_id: str | None,
    config_fingerprint: str | None,
    adapter_metadata: Mapping[str, Any],
) -> ExecutionResult:
    """Build a validated ExecutionResult, converting ValidationError into case errors."""
    metadata_copy = dict(adapter_metadata)
    try:
        return ExecutionResult(
            case_id=case.id,
            input=case.input,
            output=output,
            retrieved_chunks=list(retrieved_chunks),
            tokens=tokens,
            elapsed_seconds=elapsed_seconds,
            truncated=truncated,
            errors=list(errors),
            warnings=list(warnings),
            system_version=system_version,
            model_id=model_id,
            config_fingerprint=config_fingerprint,
            adapter_metadata=metadata_copy,
        )
    except ValidationError as exc:
        return ExecutionResult(
            case_id=case.id,
            input=case.input,
            output=None,
            elapsed_seconds=elapsed_seconds,
            errors=[f"SerializationError: target output failed validation ({exc})"],
            system_version=system_version,
            model_id=model_id,
            config_fingerprint=config_fingerprint,
            adapter_metadata=metadata_copy,
        )
