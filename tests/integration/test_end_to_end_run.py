"""End-to-end integration tests for DatasetEngine -> CallableAdapter -> Metrics -> LocalRunStore."""

from __future__ import annotations

import asyncio
from pathlib import Path

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import (
    exact_match,
    json_schema_validation,
    normalized_match,
)
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import OrchestratorConfig


def test_end_to_end_sync_and_async_evaluation_lifecycle(tmp_path: Path) -> None:
    dataset_path = tmp_path / "suite.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                '{"id": "q1", "input": "capital of france", "reference": "Paris"}',
                '{"id": "q2", "input": "json please", '
                '"criteria": {"mandatory": true, "json_schema": '
                '{"type": "object", "required": ["city"], '
                '"properties": {"city": {"type": "string"}}}}}',
                '{"id": "q3", "input": "greeting", "reference": "  hello world  "}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def async_target(query: str) -> str:
        await asyncio.sleep(0.005)
        if query == "capital of france":
            return "Paris"
        if query == "json please":
            return '{"city": "Lyon"}'
        return "HELLO   WORLD"

    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(max_concurrency=2, seed=42),
        storage_root=store_root,
    )
    run = orch.run(
        DatasetEngine(dataset_path, dataset_version="v1"),
        CallableAdapter(
            async_target,
            system_version="app-1.2",
            model_id="stub",
            config={"api_key": "sk-must-not-leak", "temp": 0.0},
        ),
        [exact_match, normalized_match, json_schema_validation],
        run_id="e2e-run-1",
    )

    store = LocalRunStore(store_root)
    persisted_file = store.run_path("e2e-run-1")
    assert persisted_file.is_file()
    assert "sk-must-not-leak" not in persisted_file.read_text(encoding="utf-8")
    assert not store.checkpoint_path("e2e-run-1").exists()

    reloaded = store.load_run("e2e-run-1")
    assert reloaded == run
    assert reloaded.has_mandatory_failures is False
    assert reloaded.aggregates["json_schema_validation"].mean_score == 1.0
    assert reloaded.aggregates["normalized_match"].mean_score == 1.0

    manifest = store.read_manifest()
    assert len(manifest) == 1
    assert manifest[0].run_id == "e2e-run-1"
    assert manifest[0].dataset_id == "suite"
