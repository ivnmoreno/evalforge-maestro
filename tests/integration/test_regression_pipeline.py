"""End-to-end M1+M2+M3 integration pipeline for baselines, compare, trend, and QualityGate."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro import (
    DatasetEngine,
    EvaluationOrchestrator,
    ExactMatchMetric,
    GateDecision,
    LocalRunStore,
    OrchestratorConfig,
    PrecisionAtKMetric,
    QualityGate,
    QualityGatePolicy,
    RAGAdapter,
    analyze_trend,
    compare_runs,
)
from evalforge_maestro._canonical import canonical_json_bytes
from evalforge_maestro.types import AnomalyType, Metric, TrendDirection


@pytest.mark.gate_determinism
@pytest.mark.gate_immutability
def test_end_to_end_evaluation_baseline_compare_trend_and_quality_gate(tmp_path: Path) -> None:
    storage_root = tmp_path / ".evalforge"
    dataset = DatasetEngine(
        [
            {
                "id": "case-1",
                "input": "What is EvalForge?",
                "reference": "Independent eval engine",
                "expected_context": ["doc-1"],
                "criteria": {"mandatory": True},
            },
            {
                "id": "case-2",
                "input": "What is RAG?",
                "reference": "Retrieval augmented generation",
                "expected_context": ["doc-2"],
            },
        ],
        dataset_id="rag-suite",
        dataset_version="1.0",
    )
    metrics: list[Metric] = [ExactMatchMetric(), PrecisionAtKMetric(1)]
    orch = EvaluationOrchestrator(
        config=OrchestratorConfig(judge_config_fingerprint="judge-v1"),
        storage_root=storage_root,
    )

    def _make_adapter(
        *,
        version: str,
        retrieval_hits: dict[str, list[dict[str, Any]]],
    ) -> RAGAdapter:
        def _target(query: str) -> dict[str, Any]:
            if query == "What is EvalForge?":
                return {
                    "answer": "Independent eval engine",
                    "chunks": retrieval_hits["case-1"],
                }
            return {
                "answer": "Retrieval augmented generation",
                "chunks": retrieval_hits["case-2"],
            }

        return RAGAdapter(_target, system_version=version, model_id=f"model-{version}")

    # Run 1 (baseline): both answer and retrieval pass cleanly
    orch.run(
        dataset,
        _make_adapter(
            version="v1",
            retrieval_hits={
                "case-1": [{"id": "doc-1", "text": "ev"}],
                "case-2": [{"id": "doc-2", "text": "rag"}],
            },
        ),
        metrics,
        run_id="run-v1",
    )
    store = LocalRunStore(storage_root)
    run_v1_sha = hashlib.sha256(store.run_path("run-v1").read_bytes()).hexdigest()
    store.pin_baseline("run-v1", note="release baseline")
    assert hashlib.sha256(store.run_path("run-v1").read_bytes()).hexdigest() == run_v1_sha

    # Run 2: retrieval degrades on non-mandatory case-2 while mandatory case-1 remains green
    orch.run(
        dataset,
        _make_adapter(
            version="v2",
            retrieval_hits={
                "case-1": [{"id": "doc-1", "text": "ev"}],
                "case-2": [{"id": "wrong-chunk", "text": "noise"}],
            },
        ),
        metrics,
        run_id="run-v2",
    )

    # Run 3: mandatory case-1 keeps exact_match=1.0 but retrieves wrong chunk (failing evidence)
    run_v3 = orch.run(
        dataset,
        _make_adapter(
            version="v3",
            retrieval_hits={
                "case-1": [{"id": "wrong-chunk", "text": "noise"}],
                "case-2": [{"id": "wrong-chunk", "text": "noise"}],
            },
        ),
        metrics,
        run_id="run-v3",
    )

    baseline = store.load_baseline_run("default")
    comp = compare_runs(baseline, run_v3, baseline_name="default")
    trend = analyze_trend(store.read_manifest(), window=3)
    gate = QualityGate(QualityGatePolicy(min_metric_scores={"exact_match": 0.9}))

    gate_res_1 = gate.evaluate(run_v3, comparison=comp, trend=trend)
    gate_res_2 = gate.evaluate(run_v3, comparison=comp, trend=trend)

    # Identical byte-for-byte deterministic gate outputs
    assert canonical_json_bytes(gate_res_1.model_dump(mode="json")) == canonical_json_bytes(
        gate_res_2.model_dump(mode="json")
    )
    assert comp.baseline_name == "default"
    assert comp.target_changes.system_version_changed is True
    assert comp.drift_warnings == []  # target upgrade without dataset/metric/judge drift
    assert comp.metric_comparisons["exact_match"].delta == 0.0
    assert comp.metric_comparisons["precision_at_k"].delta == -1.0
    assert trend.metrics["precision_at_k"].direction == TrendDirection.DEGRADING
    assert trend.metrics["precision_at_k"].slope == -0.5

    # Exact answer + broken mandatory retrieval -> mandatory case failure blocks release (FAIL)
    assert run_v3.has_mandatory_failures is True
    assert gate_res_1.decision == GateDecision.FAIL
    assert gate_res_1.blocking is True
    assert any(a.anomaly_type == AnomalyType.METRIC_DISAGREEMENT for a in gate_res_1.anomalies)
    assert hashlib.sha256(store.run_path("run-v1").read_bytes()).hexdigest() == run_v1_sha
