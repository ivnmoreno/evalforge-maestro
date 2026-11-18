"""Generic synchronous and asynchronous Python callable adapter."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from evalforge_maestro._canonical import canonical_sha256, redact_secrets, round_score
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import EvaluationCase, ExecutionResult


class CallableAdapter:
    """Adapter wrapping synchronous or asynchronous Python callables as TargetAdapter."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config: Mapping[str, Any] | None = None,
        pass_case: bool = False,
        input_mapper: Callable[[EvaluationCase], Any] | None = None,
    ) -> None:
        if not callable(fn):
            raise AdapterError("CallableAdapter requires a callable target")
        if pass_case and input_mapper is not None:
            raise AdapterError("Cannot specify both pass_case=True and input_mapper")

        self._fn = fn
        self._system_version = system_version
        self._model_id = model_id
        self._pass_case = pass_case
        self._input_mapper = input_mapper
        self._is_coro_fn = inspect.iscoroutinefunction(fn)

        if config is not None:
            redacted = redact_secrets(dict(config))
            self._config_fingerprint: str | None = canonical_sha256(redacted)
            self._adapter_metadata: dict[str, Any] = {"config": redacted}
        else:
            self._config_fingerprint = None
            self._adapter_metadata = {}

    @property
    def system_version(self) -> str | None:
        """Return declared target system version."""
        return self._system_version

    @property
    def model_id(self) -> str | None:
        """Return declared target model identifier."""
        return self._model_id

    @property
    def config_fingerprint(self) -> str | None:
        """Return canonical SHA-256 fingerprint of redacted adapter configuration."""
        return self._config_fingerprint

    def _build_target_arg(self, case: EvaluationCase) -> Any:
        if self._input_mapper is not None:
            return self._input_mapper(case)
        if self._pass_case:
            return case
        return case.input

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Invoke the wrapped callable and return a validated ExecutionResult."""
        arg = self._build_target_arg(case)
        errors: list[str] = []
        output: Any = None
        start = time.perf_counter()

        try:
            if self._is_coro_fn:
                raw_out = await self._fn(arg)
            else:
                raw_out = await asyncio.to_thread(self._fn, arg)
                if inspect.isawaitable(raw_out):
                    raw_out = await raw_out
            output = raw_out
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        elapsed = round_score(max(0.0, time.perf_counter() - start))

        try:
            return ExecutionResult(
                case_id=case.id,
                input=case.input,
                output=output,
                elapsed_seconds=elapsed,
                errors=errors,
                system_version=self._system_version,
                model_id=self._model_id,
                config_fingerprint=self._config_fingerprint,
                adapter_metadata=dict(self._adapter_metadata),
            )
        except ValidationError as exc:
            return ExecutionResult(
                case_id=case.id,
                input=case.input,
                output=None,
                elapsed_seconds=elapsed,
                errors=[f"SerializationError: target output is not JSON-serializable ({exc})"],
                system_version=self._system_version,
                model_id=self._model_id,
                config_fingerprint=self._config_fingerprint,
                adapter_metadata=dict(self._adapter_metadata),
            )
