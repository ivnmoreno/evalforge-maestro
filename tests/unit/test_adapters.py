"""Unit tests for CallableAdapter synchronous and asynchronous target wrapping."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from evalforge_maestro._canonical import REDACTED_VALUE, canonical_sha256
from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import EvaluationCase, TargetAdapter


def test_callable_adapter_sync_async_and_awaitable_targets() -> None:
    case = EvaluationCase(id="c1", input="hello")

    def sync_fn(text: str) -> str:
        return text.upper()

    async def async_fn(text: str) -> str:
        await asyncio.sleep(0.01)
        return f"async:{text}"

    def awaitable_factory(text: str) -> Any:
        async def _inner() -> str:
            return f"awaitable:{text}"

        return _inner()

    async def _run() -> None:
        sync_adapter = CallableAdapter(sync_fn, system_version="v1", model_id="m1")
        assert isinstance(sync_adapter, TargetAdapter)
        sync_res = await sync_adapter.execute(case)
        assert sync_res.case_id == "c1"
        assert sync_res.output == "HELLO"
        assert sync_res.elapsed_seconds >= 0.0
        assert sync_res.system_version == "v1"
        assert sync_res.model_id == "m1"
        assert sync_res.errors == []

        async_res = await CallableAdapter(async_fn).execute(case)
        assert async_res.output == "async:hello"

        awaitable_res = await CallableAdapter(awaitable_factory).execute(case)
        assert awaitable_res.output == "awaitable:hello"

    asyncio.run(_run())


def test_callable_adapter_input_mapping_errors_and_secret_redaction() -> None:
    case = EvaluationCase(id="c2", input="raw", metadata={"domain": "qa"})  # type: ignore[arg-type]

    def fail_fn(_: Any) -> str:
        raise ValueError("boom")

    def non_json_fn(_: Any) -> object:
        return object()

    def mapper_fn(val: str) -> str:
        return val

    async def _run() -> None:
        adapter_err = CallableAdapter(fail_fn)
        err_res = await adapter_err.execute(case)
        assert err_res.output is None
        assert len(err_res.errors) == 1
        assert "ValueError: boom" in err_res.errors[0]

        non_json_res = await CallableAdapter(non_json_fn).execute(case)
        assert non_json_res.output is None
        assert len(non_json_res.errors) == 1

        mapped = await CallableAdapter(
            mapper_fn,
            input_mapper=lambda c: f"{c.metadata.domain}:{c.input}",
        ).execute(case)
        assert mapped.output == "qa:raw"

        pass_case_res = await CallableAdapter(
            lambda c: c.id,
            pass_case=True,
        ).execute(case)
        assert pass_case_res.output == "c2"

        cfg_adapter = CallableAdapter(
            lambda x: x,
            config={"temperature": 0.1, "api_key": "sk-live-secret"},
        )
        cfg_res = await cfg_adapter.execute(case)
        assert cfg_res.config_fingerprint == canonical_sha256(
            {"temperature": 0.1, "api_key": REDACTED_VALUE}
        )
        assert "sk-live-secret" not in str(cfg_res.adapter_metadata)

    asyncio.run(_run())

    with pytest.raises(AdapterError):
        CallableAdapter("not-callable")  # type: ignore[arg-type]
    with pytest.raises(AdapterError):
        CallableAdapter(lambda x: x, pass_case=True, input_mapper=lambda c: c.input)
