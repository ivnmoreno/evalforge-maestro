"""Mandatory release gate tests verifying deterministic evaluation behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import exact_match, json_schema_validation, normalized_match
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import Metric, OrchestratorConfig


@pytest.mark.gate_determinism
def test_identical_inputs_yield_identical_scores_fingerprints_and_canonical_payload(
    tmp_path: Path,
) -> None:
    ds_a = tmp_path / "ds_a.jsonl"
    ds_b = tmp_path / "ds_b.jsonl"
    ds_a.write_text(
        '{"id": "1", "input": "a", "reference": "Alpha"}\n'
        '{"id": "2", "input": "b", "reference": {"type": "object", "required": ["ok"]}}\n',
        encoding="utf-8",
    )
    ds_b.write_text(
        '{"reference": "Alpha", "input": "a", "id": "1"}\n'
        '{"reference": {"required": ["ok"], "type": "object"}, "id": "2", "input": "b"}\n',
        encoding="utf-8",
    )

    def deterministic_target(val: str) -> str:
        return " alpha " if val == "a" else '{"ok": true}'

    metrics: list[Metric] = [exact_match, normalized_match, json_schema_validation]
    cfg = OrchestratorConfig(max_concurrency=4, seed=123)
    adapter = CallableAdapter(deterministic_target, system_version="1.0", config={"k": 1})

    run1 = EvaluationOrchestrator(config=cfg, storage_root=tmp_path / ".ef1").run(
        DatasetEngine(ds_a, dataset_id="gate"),
        adapter,
        metrics,
        run_id="det-run-1",
    )
    run2 = EvaluationOrchestrator(config=cfg, storage_root=tmp_path / ".ef2").run(
        DatasetEngine(ds_b, dataset_id="gate"),
        adapter,
        metrics,
        run_id="det-run-2",
    )

    assert run1.dataset_fingerprint == run2.dataset_fingerprint
    assert run1.config_fingerprint == run2.config_fingerprint
    assert run1.aggregates == run2.aggregates
    assert run1.status_counts == run2.status_counts
    assert run1.mandatory_failed_case_ids == run2.mandatory_failed_case_ids
    assert [{k: (m.score, m.status) for k, m in r.metrics.items()} for r in run1.case_results] == [
        {k: (m.score, m.status) for k, m in r.metrics.items()} for r in run2.case_results
    ]

    store1 = LocalRunStore(tmp_path / ".ef1")
    store2 = LocalRunStore(tmp_path / ".ef2")
    assert store1.load_run("det-run-1").aggregates == store2.load_run("det-run-2").aggregates
