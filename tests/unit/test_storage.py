"""Unit tests for LocalRunStore atomic persistence, permissions, checkpoints, and immutability."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evalforge_maestro.exceptions import ImmutabilityError, StorageError
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseEvaluationRecord,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RunRecord,
)


def _sample_run(run_id: str = "run-001") -> RunRecord:
    case_rec = CaseEvaluationRecord(
        case_id="c1",
        mandatory=False,
        execution=ExecutionResult(case_id="c1", input="q", output="a", elapsed_seconds=0.02),
        metrics={
            "exact_match": MetricResult(
                metric_id="exact_match",
                metric_version="1.0.0",
                score=1.0,
                status=MetricStatus.PASS,
                explanation="Matched.",
            )
        },
    )
    return RunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 18, 9, 0, 0, tzinfo=UTC),
        package_version="0.1.0",
        dataset_id="ds-test",
        dataset_fingerprint="b" * 64,
        evaluated_case_count=1,
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
        status_counts={
            status: (1 if status == MetricStatus.PASS else 0) for status in MetricStatus
        },
        case_results=[case_rec],
    )


def test_run_id_path_traversal_rejection_and_missing_reads(tmp_path: Path) -> None:
    store = LocalRunStore(tmp_path / ".evalforge")
    for bad_id in ("", "../escape", "sub/dir", ".hidden", "bad\\id", "a" * 129):
        with pytest.raises(StorageError):
            store.run_path(bad_id)
        with pytest.raises(StorageError):
            store.checkpoint_path(bad_id)

    assert store.read_checkpoints("missing-run") == []
    assert store.read_manifest() == []
    with pytest.raises(StorageError):
        store.load_run("missing-run")


def test_checkpoints_atomic_commit_permissions_and_immutability(tmp_path: Path) -> None:
    root = tmp_path / ".evalforge"
    store = LocalRunStore(root)
    run = _sample_run("run-xyz")

    store.append_checkpoint("run-xyz", run.case_results[0])
    loaded_ckpt = store.read_checkpoints("run-xyz")
    assert len(loaded_ckpt) == 1
    assert loaded_ckpt[0].case_id == "c1"

    saved_path = store.save_run(run)
    assert saved_path == store.run_path("run-xyz")
    raw_text = saved_path.read_text(encoding="utf-8")
    assert "\r\n" not in raw_text
    assert raw_text.endswith("\n")

    if os.name == "posix":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE((root / "runs").stat().st_mode) == 0o700
        assert stat.S_IMODE((root / "tmp").stat().st_mode) == 0o700
        assert stat.S_IMODE(saved_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(store.manifest_path().stat().st_mode) == 0o600
        assert stat.S_IMODE(store.checkpoint_path("run-xyz").stat().st_mode) == 0o600

    loaded_run = store.load_run("run-xyz")
    assert loaded_run == run

    manifest = store.read_manifest()
    assert len(manifest) == 1
    assert manifest[0].run_id == "run-xyz"
    assert manifest[0].aggregate_scores == {"exact_match": 1.0}

    with pytest.raises(ImmutabilityError):
        store.save_run(run)
    assert len(store.read_manifest()) == 1

    store.remove_checkpoint("run-xyz")
    assert not store.checkpoint_path("run-xyz").exists()


def test_corrupted_run_or_checkpoint_raises_storage_error(tmp_path: Path) -> None:
    store = LocalRunStore(tmp_path / ".evalforge")
    ckpt_path = store.checkpoint_path("bad-ckpt")
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    ckpt_path.write_text("{corrupt\n", encoding="utf-8")
    with pytest.raises(StorageError):
        store.read_checkpoints("bad-ckpt")

    run_path = store.run_path("bad-run")
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(StorageError):
        store.load_run("bad-run")
