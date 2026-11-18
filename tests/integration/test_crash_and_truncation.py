"""Integration tests for crash checkpoint retention, commit cleanup, and truncation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import ExecutionError
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import json_schema_validation
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import OrchestratorConfig


def test_aborted_run_retains_checkpoints_without_committing_run_record(tmp_path: Path) -> None:
    ds = DatasetEngine(
        [
            {"id": "c1", "input": "ok", "reference": "OK"},
            {"id": "c2", "input": "fail", "reference": "FAIL"},
        ]
    )

    def target(val: str) -> str:
        if val == "fail":
            raise RuntimeError("mid-run failure")
        return "OK"

    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=1, fail_fast=True),
        storage_root=store_root,
    )
    with pytest.raises(ExecutionError):
        orch.run(ds, CallableAdapter(target), [], run_id="aborted-run")

    store = LocalRunStore(store_root)
    assert not store.run_path("aborted-run").exists()
    assert store.read_manifest() == []
    checkpoints = store.read_checkpoints("aborted-run")
    assert len(checkpoints) == 2
    assert [c.case_id for c in checkpoints] == ["c1", "c2"]


def test_post_scoring_truncation_and_optional_checkpoint_retention(tmp_path: Path) -> None:
    large_json = json.dumps({"answer": "A" * 300})
    ds = DatasetEngine(
        [
            {
                "id": "c1",
                "input": "make json",
                "criteria": {
                    "json_schema": {
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                },
            }
        ]
    )

    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_context_chars=64, retain_checkpoints=True),
        storage_root=store_root,
    )
    run = orch.run(
        ds,
        CallableAdapter(lambda _: large_json),
        [json_schema_validation],
        run_id="retain-run",
    )

    # Full JSON was validated BEFORE truncation
    assert run.case_results[0].metrics["json_schema_validation"].score == 1.0
    assert run.case_results[0].execution.truncated is True
    assert len(run.case_results[0].execution.output) == 64

    store = LocalRunStore(store_root)
    assert store.checkpoint_path("retain-run").is_file()
    assert len(store.read_checkpoints("retain-run")) == 1
