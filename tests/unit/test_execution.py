"""Unit tests for EvaluationOrchestrator concurrency, isolation, timeouts, and guardrails."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import ExecutionError, MemoryLimitExceededError
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
)


class _LengthCheckMetric:
    def __init__(self, expected_min_len: int) -> None:
        self._min_len = expected_min_len

    @property
    def metadata(self) -> MetricMetadata:
        return MetricMetadata(
            metric_id="len_check",
            metric_version="1.0.0",
            what_it_measures="Checks full output length prior to persistence truncation",
            required_case_fields=(),
            required_execution_fields=("output",),
            calculation_method="len(output) >= min_len",
            known_limitations="Test helper",
        )

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        if execution.errors:
            return MetricResult(
                metric_id="len_check",
                metric_version="1.0.0",
                score=None,
                status=MetricStatus.INCONCLUSIVE,
                explanation="Upstream execution error",
            )
        ok = isinstance(execution.output, str) and len(execution.output) >= self._min_len
        return MetricResult(
            metric_id="len_check",
            metric_version="1.0.0",
            score=1.0 if ok else 0.0,
            status=MetricStatus.PASS if ok else MetricStatus.FAIL,
            explanation="Checked output length",
        )


def test_bounded_concurrency_and_deterministic_case_ordering(tmp_path: Path) -> None:
    active = 0
    max_observed = 0

    async def tracked_target(payload: str) -> str:
        nonlocal active, max_observed
        active += 1
        max_observed = max(max_observed, active)
        delay = 0.04 if payload == "0" else 0.01
        await asyncio.sleep(delay)
        active -= 1
        return f"out:{payload}"

    ds = DatasetEngine([{"id": f"c{i}", "input": str(i)} for i in range(8)])
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=2),
        storage_root=tmp_path / ".evalforge",
    )
    run = orch.run(ds, CallableAdapter(tracked_target), [])
    assert max_observed <= 2
    assert [r.case_id for r in run.case_results] == [f"c{i}" for i in range(8)]


def test_timeout_fault_isolation_and_fail_fast(tmp_path: Path) -> None:
    async def flaky_target(payload: str) -> str:
        if payload == "slow":
            await asyncio.sleep(0.5)
        if payload == "boom":
            raise RuntimeError("target crashed")
        return f"ok:{payload}"

    ds = DatasetEngine(
        [
            {"id": "c1", "input": "good"},
            {"id": "c2", "input": "slow"},
            {"id": "c3", "input": "boom"},
            {"id": "c4", "input": "also-good"},
        ]
    )
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=2, case_timeout_seconds=0.05),
        storage_root=tmp_path / ".evalforge",
    )
    run = orch.run(ds, CallableAdapter(flaky_target), [_LengthCheckMetric(1)])
    by_id = {r.case_id: r for r in run.case_results}
    assert by_id["c1"].execution.output == "ok:good"
    assert by_id["c2"].metrics["len_check"].status == MetricStatus.INCONCLUSIVE
    assert "Timeout" in by_id["c2"].execution.errors[0]
    assert by_id["c3"].metrics["len_check"].status == MetricStatus.INCONCLUSIVE
    assert "RuntimeError" in by_id["c3"].execution.errors[0]
    assert by_id["c4"].execution.output == "ok:also-good"

    orch_ff = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=1, fail_fast=True),
        storage_root=tmp_path / ".evalforge2",
    )
    with pytest.raises(ExecutionError):
        orch_ff.run(ds, CallableAdapter(flaky_target), [_LengthCheckMetric(1)])


def test_post_scoring_truncation_and_max_dataset_cases(tmp_path: Path) -> None:
    ds = DatasetEngine([{"id": f"c{i}", "input": str(i)} for i in range(5)])
    adapter = CallableAdapter(lambda x: ("A" * 200) if x == "0" else "short")
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_dataset_cases=3, max_context_chars=50),
        storage_root=tmp_path / ".evalforge",
    )
    run = orch.run(ds, adapter, [_LengthCheckMetric(200)])
    assert run.evaluated_case_count == 3
    assert run.dataset_capped is True
    assert run.max_dataset_cases == 3
    # Full output of length 200 was scored BEFORE persistence truncation
    assert run.case_results[0].metrics["len_check"].status == MetricStatus.PASS
    assert run.case_results[0].execution.truncated is True
    assert len(run.case_results[0].execution.output) == 50
    assert run.case_results[1].execution.truncated is False


def test_resident_memory_guardrail_warn_and_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "evalforge_maestro.execution.orchestrator._get_resident_memory_mb",
        lambda: 512.0,
    )
    ds = DatasetEngine([{"id": "c1", "input": "hi"}])
    adapter = CallableAdapter(lambda x: x)

    with caplog.at_level(logging.WARNING, logger="evalforge_maestro"):
        orch_warn = EvaluationOrchestrator(
            config=OrchestratorConfig(max_memory_mb=256.0, memory_limit_action="warn"),
            storage_root=tmp_path / ".ef1",
        )
        run = orch_warn.run(ds, adapter, [])
        assert run.evaluated_case_count == 1
        assert any("memory" in rec.message.lower() for rec in caplog.records)

    orch_abort = EvaluationOrchestrator(
        config=OrchestratorConfig(max_memory_mb=256.0, memory_limit_action="abort"),
        storage_root=tmp_path / ".ef2",
    )
    with pytest.raises(MemoryLimitExceededError):
        orch_abort.run(ds, adapter, [])


def test_sync_run_inside_active_loop_raises_helpful_error(tmp_path: Path) -> None:
    ds = DatasetEngine([{"id": "c1", "input": "hi"}])
    orch = EvaluationOrchestrator(storage_root=tmp_path / ".evalforge")

    async def _inside() -> None:
        with pytest.raises(ExecutionError, match="arun"):
            orch.run(ds, CallableAdapter(lambda x: x), [])

    asyncio.run(_inside())


def test_metric_exception_isolation_and_structured_truncation(tmp_path: Path) -> None:
    class _CrashingMetric:
        @property
        def metadata(self) -> MetricMetadata:
            return MetricMetadata(
                metric_id="crasher",
                metric_version="1.0.0",
                what_it_measures="raises intentionally",
                required_case_fields=(),
                required_execution_fields=("output",),
                calculation_method="raises",
                known_limitations="test",
            )

        def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
            raise ZeroDivisionError("bad formula")

    ds = DatasetEngine([{"id": "c1", "input": "q"}])
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_context_chars=12),
        storage_root=tmp_path / ".evalforge",
    )
    run = orch.run(
        ds,
        CallableAdapter(lambda _: {"long_key": "value" * 20}),
        [_CrashingMetric()],
    )
    assert run.case_results[0].metrics["crasher"].status == MetricStatus.INCONCLUSIVE
    assert "ZeroDivisionError" in run.case_results[0].metrics["crasher"].explanation
    assert run.case_results[0].execution.truncated is True
    assert len(run.case_results[0].execution.output) == 12
    assert orch.config.max_context_chars == 12
    assert orch.storage_root == tmp_path / ".evalforge"
