"""Mandatory release gate tests verifying artifact and fingerprint immutability."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import ImmutabilityError, StorageError
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import exact_match
from evalforge_maestro.storage import LocalRunStore


@pytest.mark.gate_immutability
def test_committed_run_record_and_fingerprints_cannot_be_silently_overwritten(
    tmp_path: Path,
) -> None:
    ds_file = tmp_path / "ds.jsonl"
    ds_file.write_text('{"id": "1", "input": "x", "reference": "x"}\n', encoding="utf-8")

    store_root = tmp_path / ".evalforge"
    orch = EvaluationOrchestrator(storage_root=store_root)
    first_run = orch.run(
        DatasetEngine(ds_file),
        CallableAdapter(lambda x: x),
        [exact_match],
        run_id="immutable-run",
    )

    store = LocalRunStore(store_root)
    original_bytes = store.run_path("immutable-run").read_bytes()

    # Re-running with the same explicit run_id MUST fail cleanly without altering disk artifact
    ds_file.write_text('{"id": "1", "input": "x", "reference": "MODIFIED"}\n', encoding="utf-8")
    with pytest.raises(ImmutabilityError):
        orch.run(
            DatasetEngine(ds_file),
            CallableAdapter(lambda _: "WRONG"),
            [exact_match],
            run_id="immutable-run",
        )

    assert store.run_path("immutable-run").read_bytes() == original_bytes
    assert len(store.read_manifest()) == 1

    # Dataset modification produces a distinct canonical fingerprint on a new run_id
    second_run = orch.run(
        DatasetEngine(ds_file),
        CallableAdapter(lambda x: x),
        [exact_match],
        run_id="immutable-run-v2",
    )
    assert second_run.dataset_fingerprint != first_run.dataset_fingerprint

    # Tampering detection: corrupting persisted run file fails schema load cleanly
    run_file = store.run_path("immutable-run")
    run_file.chmod(0o600)
    run_file.write_text('{"corrupted": true}', encoding="utf-8")
    with pytest.raises(StorageError):
        store.load_run("immutable-run")
