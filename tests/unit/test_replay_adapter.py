"""Unit tests for offline ReplayAdapter loading and validation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evalforge_maestro.adapters import ReplayAdapter
from evalforge_maestro.exceptions import AdapterError, DatasetError
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    EvaluationCase,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RunRecord,
    TargetAdapter,
)


def _exec(case_id: str, output: str = "Paris") -> ExecutionResult:
    return ExecutionResult(
        case_id=case_id,
        input="Capital?",
        output=output,
        elapsed_seconds=0.01,
        system_version="sys-v1",
        model_id="mdl-v1",
    )


def test_replay_adapter_from_jsonl_and_target_protocol(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "executions.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                _exec("c1", "Paris").model_dump_json(),
                _exec("c2", "London").model_dump_json(),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = ReplayAdapter.from_file(jsonl_path)
    assert isinstance(adapter, TargetAdapter)
    assert adapter.case_ids == frozenset({"c1", "c2"})
    assert adapter.system_version == "sys-v1"
    assert adapter.model_id == "mdl-v1"
    assert adapter.config_fingerprint is not None

    res1 = asyncio.run(adapter.execute(EvaluationCase(id="c1", input="q1")))
    assert res1.output == "Paris"

    with pytest.raises(AdapterError, match="missing-id"):
        asyncio.run(adapter.execute(EvaluationCase(id="missing-id", input="q3")))


def test_replay_adapter_supports_json_array_and_run_record(tmp_path: Path) -> None:
    arr_path = tmp_path / "arr.json"
    arr_path.write_text(
        json.dumps([_exec("a1", "Alpha").model_dump(mode="json")]),
        encoding="utf-8",
    )
    arr_adapter = ReplayAdapter.from_file(arr_path)
    assert arr_adapter.case_ids == frozenset({"a1"})

    run_rec = RunRecord(
        run_id="run-replay-src",
        timestamp=datetime(2026, 11, 19, tzinfo=timezone.utc),
        package_version="0.1.0",
        dataset_id="ds-1",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=1,
        system_version="sys-r",
        model_id="mdl-r",
        metric_versions={"exact_match": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=1.0,
                applicable_count=1,
                pass_count=1,
            )
        },
        status_counts={MetricStatus.PASS: 1},
        case_results=[
            CaseEvaluationRecord(
                case_id="r1",
                execution=_exec("r1", "Beta"),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="exact",
                    )
                },
            )
        ],
    )
    run_path = tmp_path / "run.json"
    run_path.write_text(run_rec.model_dump_json(), encoding="utf-8")
    run_adapter = ReplayAdapter.from_file(run_path)
    assert run_adapter.case_ids == frozenset({"r1"})
    assert run_adapter.system_version == "sys-r"
    assert run_adapter.model_id == "mdl-r"


def test_replay_adapter_rejects_duplicates_empty_and_bad_records(tmp_path: Path) -> None:
    dup_path = tmp_path / "dup.jsonl"
    dup_path.write_text(
        _exec("c1").model_dump_json() + "\n" + _exec("c1").model_dump_json() + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetError, match="Duplicate case_id"):
        ReplayAdapter.from_file(dup_path)

    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="zero execution records"):
        ReplayAdapter.from_file(empty_path)

    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text('{"case_id": ""}\n', encoding="utf-8")
    with pytest.raises(DatasetError, match="Invalid ExecutionResult"):
        ReplayAdapter.from_file(bad_path)

    with pytest.raises(DatasetError, match="not found"):
        ReplayAdapter.from_file(tmp_path / "absent.jsonl")
