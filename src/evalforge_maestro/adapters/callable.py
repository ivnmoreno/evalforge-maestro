"""Generic synchronous and asynchronous Python callable adapter."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from evalforge_maestro._canonical import round_score
from evalforge_maestro.adapters._shared import (
    build_target_arg,
    build_validated_execution_result,
    invoke_callable,
    redact_adapter_config,
    validate_callable_target_options,
)
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
        self._is_coro_fn = validate_callable_target_options(
            fn,
            adapter_name="CallableAdapter",
            pass_case=pass_case,
            input_mapper=input_mapper,
        )
        self._fn = fn
        self._system_version = system_version
        self._model_id = model_id
        self._pass_case = pass_case
        self._input_mapper = input_mapper
        self._config_fingerprint, self._adapter_metadata = redact_adapter_config(config)

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

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Invoke the wrapped callable and return a validated ExecutionResult."""
        arg = build_target_arg(case, pass_case=self._pass_case, input_mapper=self._input_mapper)
        errors: list[str] = []
        output: Any = None
        start = time.perf_counter()

        try:
            output = await invoke_callable(self._fn, arg, is_coro_fn=self._is_coro_fn)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        elapsed = round_score(max(0.0, time.perf_counter() - start))
        return build_validated_execution_result(
            case=case,
            output=output,
            retrieved_chunks=(),
            tokens=None,
            elapsed_seconds=elapsed,
            truncated=False,
            errors=errors,
            warnings=[],
            system_version=self._system_version,
            model_id=self._model_id,
            config_fingerprint=self._config_fingerprint,
            adapter_metadata=self._adapter_metadata,
        )
