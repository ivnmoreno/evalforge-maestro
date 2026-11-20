"""Integration and release-gate tests for M6 end-to-end agent trace evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.adapters import AgentAdapter, ReplayAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import (
    argument_correctness,
    exact_match,
    execution_sequence,
    failure_recovery,
    policy_compliance,
    tool_efficiency,
    tool_selection,
)
from evalforge_maestro.regression import QualityGate, compare_runs
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import GateDecision, Metric, QualityGatePolicy


def _agent_fn(prompt: str) -> dict[str, Any]:
    if "refund" in prompt.lower():
        return {
            "output": "Eligible for 14-day refund",
            "tool_calls": [
                {
                    "id": "tc-1",
                    "name": "lookup_policy",
                    "arguments": {"topic": "refund"},
                    "status": "success",
                },
                {
                    "id": "tc-2",
                    "name": "calc_refund",
                    "arguments": {"days": 5},
                    "status": "error",
                    "error": "transient timeout",
                },
                {
                    "id": "tc-3",
                    "name": "calc_refund",
                    "arguments": {"days": 5},
                    "status": "success",
                    "result": {"eligible": True},
                },
            ],
            "trace": [
                {"kind": "reasoning", "content": "Check policy before computing refund"},
                {"kind": "final_output", "content": "Eligible for 14-day refund"},
            ],
        }
    return {
        "output": "Ticket resolved",
        "tool_calls": [
            {"id": "tc-4", "name": "fetch_ticket", "arguments": {"id": 99}, "status": "success"}
        ],
    }


@pytest.mark.gate_determinism
def test_agent_evaluation_pipeline_and_replay_are_deterministic(tmp_path: Path) -> None:
    ds = DatasetEngine(
        [
            {
                "id": "ag-1",
                "input": "Check refund policy and calculate refund",
                "reference": "Eligible for 14-day refund",
                "expected_tools": [
                    {"name": "lookup_policy", "arguments": {"topic": "refund"}},
                    {"name": "calc_refund", "arguments": {"days": 5}},
                ],
                "criteria": {
                    "mandatory": True,
                    "forbidden_tools": ["delete_account"],
                    "max_steps": 6,
                },
            },
            {
                "id": "ag-2",
                "input": "Check ticket 99",
                "reference": "Ticket resolved",
                "expected_tools": [{"name": "fetch_ticket", "arguments": {"id": 99}}],
            },
        ]
    )
    metrics: list[Metric] = [
        exact_match,
        tool_selection,
        argument_correctness,
        execution_sequence,
        tool_efficiency,
        policy_compliance,
        failure_recovery,
    ]
    run1 = EvaluationOrchestrator(storage_root=tmp_path / ".s1").run(
        ds,
        AgentAdapter(_agent_fn, system_version="agent-v1", model_id="m-1"),
        metrics,
        run_id="run-ag-1",
    )
    run2 = EvaluationOrchestrator(storage_root=tmp_path / ".s2").run(
        ds,
        AgentAdapter(_agent_fn, system_version="agent-v1", model_id="m-1"),
        metrics,
        run_id="run-ag-2",
    )

    assert run1.has_mandatory_failures is False
    for m_id in (
        "exact_match",
        "tool_selection",
        "argument_correctness",
        "execution_sequence",
        "tool_efficiency",
        "policy_compliance",
        "failure_recovery",
    ):
        assert run1.aggregates[m_id].mean_score == run2.aggregates[m_id].mean_score == 1.0

    # Offline ReplayAdapter seeded from persisted run1.json matches live evaluation identically
    run1_path = tmp_path / ".s1" / "runs" / "run-ag-1.json"
    replay = ReplayAdapter.from_file(run1_path)
    run3 = EvaluationOrchestrator(storage_root=tmp_path / ".s3").run(
        ds,
        replay,
        metrics,
        run_id="run-ag-3",
    )
    comp = compare_runs(run1, run3)
    gate = QualityGate(QualityGatePolicy(min_score=0.95)).evaluate(run3, comparison=comp)
    assert gate.decision == GateDecision.PASS


@pytest.mark.gate_immutability
def test_agent_policy_breach_and_immutable_baseline_comparison(tmp_path: Path) -> None:
    ds = DatasetEngine(
        [
            {
                "id": "ag-policy",
                "input": "Run clean task",
                "reference": "done",
                "expected_tools": [{"name": "read_only"}],
                "criteria": {"mandatory": True, "forbidden_tools": ["drop_db"]},
            }
        ]
    )
    store = LocalRunStore(tmp_path / ".evalforge")
    good_run = EvaluationOrchestrator(storage_root=store.root).run(
        ds,
        AgentAdapter(lambda _: {"output": "done", "tool_calls": [{"name": "read_only"}]}),
        [exact_match, tool_selection, policy_compliance],
        run_id="ag-baseline",
    )
    store.pin_baseline("ag-baseline", name="prod-agent")

    bad_run = EvaluationOrchestrator(storage_root=store.root).run(
        ds,
        AgentAdapter(
            lambda _: {
                "output": "done",
                "tool_calls": [{"name": "read_only"}, {"name": "drop_db"}],
            }
        ),
        [exact_match, tool_selection, policy_compliance],
        run_id="ag-candidate",
    )
    reloaded_base = store.load_run("ag-baseline")
    assert reloaded_base.model_dump(mode="json") == good_run.model_dump(mode="json")
    comp = compare_runs(reloaded_base, bad_run)
    gate = QualityGate(QualityGatePolicy(fail_on_anomaly=True)).evaluate(bad_run, comparison=comp)
    assert gate.decision == GateDecision.FAIL
    assert "ag-policy" in bad_run.mandatory_failed_case_ids
