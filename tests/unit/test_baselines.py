"""Unit and immutability gate tests for pinned baseline registry operations."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from evalforge_maestro.exceptions import ImmutabilityError, StorageError
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    AggregateMetricSummary,
    BaselineEntry,
    BaselineRegistry,
    CaseEvaluationRecord,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    RunRecord,
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_run(run_id: str, *, score: float = 0.9, judge_fp: str | None = None) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
        package_version="0.3.0",
        dataset_id="ds-bench",
        dataset_version="1.0",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=1,
        system_version="sys-1",
        model_id="m-1",
        config_fingerprint="c" * 64,
        judge_config_fingerprint=judge_fp,
        metric_versions={"exact_match": "1.0.0"},
        aggregates={
            "exact_match": AggregateMetricSummary(
                metric_id="exact_match",
                metric_version="1.0.0",
                mean_score=score,
                applicable_count=1,
                pass_count=1 if score >= 0.5 else 0,
                fail_count=0 if score >= 0.5 else 1,
            )
        },
        status_counts={
            s: (
                1
                if (score >= 0.5 and s == MetricStatus.PASS)
                or (score < 0.5 and s == MetricStatus.FAIL)
                else 0
            )
            for s in MetricStatus
        },
        case_results=[
            CaseEvaluationRecord(
                case_id="c1",
                mandatory=False,
                execution=ExecutionResult(
                    case_id="c1", input="q", output="ok", elapsed_seconds=0.01
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=score,
                        status=MetricStatus.PASS if score >= 0.5 else MetricStatus.FAIL,
                        explanation="checked",
                    )
                },
            )
        ],
    )


@pytest.mark.gate_immutability
def test_baseline_pin_resolve_list_overwrite_and_unpin_preserve_run_history(
    tmp_path: Path,
) -> None:
    store = LocalRunStore(tmp_path / ".evalforge")
    assert store.list_baselines() == []

    r1 = _sample_run("run-001", score=1.0, judge_fp="j" * 64)
    r2 = _sample_run("run-002", score=0.8)
    r1_path = store.save_run(r1)
    r2_path = store.save_run(r2)
    r1_sha = _sha256_file(r1_path)
    r2_sha = _sha256_file(r2_path)
    manifest_sha = _sha256_file(store.manifest_path())

    pinned_default = store.pin_baseline(
        "run-001",
        note=" main green anchor ",
        tags=["release", "v1", "release"],
    )
    assert pinned_default.name == "default"
    assert pinned_default.run_id == "run-001"
    assert pinned_default.note == "main green anchor"
    assert pinned_default.tags == ["release", "v1"]
    assert pinned_default.judge_config_fingerprint == "j" * 64
    assert pinned_default.aggregate_scores == {"exact_match": 1.0}

    store.pin_baseline("run-002", name="alpha")
    listed = store.list_baselines()
    assert [entry.name for entry in listed] == ["alpha", "default"]

    assert store.get_baseline().run_id == "run-001"
    assert store.load_baseline_run("alpha").run_id == "run-002"
    assert [r.run_id for r in store.load_runs()] == ["run-001", "run-002"]
    assert [r.run_id for r in store.load_runs(["run-002"])] == ["run-002"]

    if os.name == "posix":
        assert (store.root.stat().st_mode & 0o777) == 0o700
        assert (store.baseline_path().stat().st_mode & 0o777) == 0o600

    # Unforced overwrite must raise ImmutabilityError without altering pointer
    with pytest.raises(ImmutabilityError, match="already pinned"):
        store.pin_baseline("run-002")
    assert store.get_baseline("default").run_id == "run-001"

    # Forced overwrite updates pointer atomically without mutating historical RunRecords
    replaced = store.pin_baseline("run-002", overwrite=True)
    assert replaced.run_id == "run-002"
    assert store.get_baseline("default").run_id == "run-002"

    # Unpin removes only alias entry and leaves RunRecord files untouched
    removed = store.unpin_baseline("alpha")
    assert removed.run_id == "run-002"
    assert [entry.name for entry in store.list_baselines()] == ["default"]
    assert r1_path.exists()
    assert r2_path.exists()
    assert _sha256_file(r1_path) == r1_sha
    assert _sha256_file(r2_path) == r2_sha
    assert _sha256_file(store.manifest_path()) == manifest_sha


def test_baseline_validation_and_storage_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalRunStore(tmp_path / ".evalforge")
    store.save_run(_sample_run("run-valid"))

    for bad_name in ("", "../escape", "bad..alias", "has space"):
        with pytest.raises(StorageError):
            store.pin_baseline("run-valid", name=bad_name)
        with pytest.raises(StorageError):
            store.get_baseline(bad_name)
        with pytest.raises(StorageError):
            store.unpin_baseline(bad_name)

    with pytest.raises(StorageError, match="not found"):
        store.pin_baseline("missing-run")
    with pytest.raises(StorageError, match="not found"):
        store.get_baseline("missing")
    with pytest.raises(StorageError, match="not found"):
        store.unpin_baseline("missing")

    # Corrupted baselines.json fails explicitly
    store.baseline_path().parent.mkdir(parents=True, exist_ok=True)
    store.baseline_path().write_text("{corrupt json", encoding="utf-8")
    with pytest.raises(StorageError, match="Failed loading baseline registry"):
        store.load_baselines()

    # Mismatched registry key vs entry.name fails schema validation
    entry = BaselineEntry(
        name="expected",
        run_id="run-valid",
        pinned_at=datetime(2026, 11, 18, 12, 0),
        dataset_id="ds-bench",
        dataset_fingerprint="a" * 64,
        aggregate_scores={"m1": None, "m2": 0.5},
    )
    assert entry.pinned_at.tzinfo == timezone.utc
    with pytest.raises(ValidationError):
        BaselineRegistry(baselines={"wrong-key": entry})

    for bad_agg in (
        {1: 0.5},
        {"m": True},
        {"m": 1.5},
        {" ": 0.5},
    ):
        with pytest.raises(ValidationError):
            BaselineEntry(
                name="ok",
                run_id="r",
                pinned_at=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
                dataset_id="ds",
                dataset_fingerprint="a" * 64,
                aggregate_scores=bad_agg,  # type: ignore[arg-type]
            )
    with pytest.raises(ValidationError):
        BaselineEntry(
            name="bad..entry",
            run_id="r",
            pinned_at=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
            dataset_id="ds",
            dataset_fingerprint="a" * 64,
        )

    # Atomic write OS error surfaces as StorageError
    store.baseline_path().unlink()
    monkeypatch.setattr(os, "replace", lambda _s, _d: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(StorageError, match="Failed writing"):
        store.pin_baseline("run-valid")
    assert not store.baseline_path().exists()

    # Re-verify canonical JSON serialization stays readable after normal write
    monkeypatch.undo()
    store.pin_baseline("run-valid")
    parsed = json.loads(store.baseline_path().read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "1.0"
    assert "default" in parsed["baselines"]
