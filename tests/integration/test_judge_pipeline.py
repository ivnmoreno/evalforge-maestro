"""End-to-end integration tests wiring judges into Orchestrator, M3 Regression, and Calibration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro import (
    AnomalyType,
    AnswerCorrectnessMetric,
    ContextRelevanceMetric,
    CustomRubricJudgeMetric,
    DatasetEngine,
    DriftCategory,
    EvaluationOrchestrator,
    ExactMatchMetric,
    GateDecision,
    GroundednessMetric,
    HumanCalibrationSample,
    JudgeConfig,
    LocalRunStore,
    MetricStatus,
    OrchestratorConfig,
    QualityGate,
    QualityGatePolicy,
    RAGAdapter,
    RetrievedChunk,
    analyze_trend,
    calibrate_judge,
    compare_runs,
)
from evalforge_maestro.exceptions import ExecutionError


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _rag_callable(payload: Any) -> dict[str, Any]:
    q = str(payload)
    if "SLA" in q:
        return {
            "output": "Our enterprise SLA provides a 99.9% monthly uptime guarantee.",
            "chunks": [
                {
                    "id": "sla-doc",
                    "text": "Enterprise SLA policy guarantees 99.9% monthly uptime.",
                    "rank": 1,
                    "score": 0.95,
                }
            ],
        }
    return {
        "output": "The capital of France is Paris.",
        "chunks": [
            {
                "id": "wrong-doc",
                "text": "Bananas and citrus fruits thrive in warm climates.",
                "rank": 1,
                "score": 0.88,
            }
        ],
    }


@pytest.mark.gate_determinism
def test_end_to_end_orchestrator_judges_fingerprint_drift_anomalies_and_calibration(
    tmp_path: Path,
) -> None:
    ds_path = _write_jsonl(
        tmp_path / "rag_eval.jsonl",
        [
            {
                "id": "case-sla",
                "input": "What is the SLA monthly uptime guarantee?",
                "reference": "99.9% monthly uptime guarantee",
            },
            {
                "id": "case-france",
                "input": "What is the capital of France?",
                "reference": "Paris",
            },
        ],
    )
    dataset = DatasetEngine(ds_path, dataset_id="rag-suite", dataset_version="1.0")
    adapter = RAGAdapter(_rag_callable, system_version="v1.0", model_id="rag-sys")

    store_root = tmp_path / ".evalforge"
    orch_cfg = OrchestratorConfig(max_concurrency=2, seed=7)
    orchestrator = EvaluationOrchestrator(config=orch_cfg, storage_root=store_root)

    judge_cfg_a = JudgeConfig(
        model="mock-judge",
        mock_mode=True,
        local_only=True,
        pass_threshold=0.5,
    )
    judges_a = [
        GroundednessMetric(config=judge_cfg_a),
        ContextRelevanceMetric(config=judge_cfg_a),
        AnswerCorrectnessMetric(config=judge_cfg_a),
    ]

    run_a = orchestrator.run(dataset, adapter, judges_a, run_id="run-m4-a")
    run_a_repeat = EvaluationOrchestrator(
        config=orch_cfg, storage_root=tmp_path / ".evalforge-repeat"
    ).run(dataset, adapter, judges_a, run_id="run-m4-a")

    # Deterministic @pytest.mark.gate_determinism check
    assert run_a.aggregates == run_a_repeat.aggregates
    assert run_a.judge_config_fingerprint == run_a_repeat.judge_config_fingerprint
    assert run_a.judge_config_fingerprint is not None

    # Auto-stamped fingerprint matches in LocalRunStore manifest too
    store = LocalRunStore(store_root)
    manifest = store.read_manifest()
    assert len(manifest) == 1
    assert manifest[0].judge_config_fingerprint == run_a.judge_config_fingerprint

    # "case-france": answer right (PASS), grounding/context fail (FAIL) -> >0.3 disagreement
    case_france = next(c for c in run_a.case_results if c.case_id == "case-france")
    assert case_france.metrics["answer_correctness"].status == MetricStatus.PASS
    assert case_france.metrics["groundedness"].status == MetricStatus.FAIL
    assert case_france.metrics["context_relevance"].status == MetricStatus.FAIL

    gate = QualityGate(QualityGatePolicy(disagreement_threshold=0.3))
    gate_res = gate.evaluate(run_a)
    assert gate_res.decision == GateDecision.WARNING
    assert any(a.anomaly_type == AnomalyType.METRIC_DISAGREEMENT for a in gate_res.anomalies)

    # Second run changes judge model -> distinct fingerprint -> DriftCategory.JUDGE_CONFIG
    judge_cfg_b = JudgeConfig(
        model="mock-judge-v2", mock_mode=True, local_only=True, pass_threshold=0.5
    )
    judges_b = [
        GroundednessMetric(config=judge_cfg_b),
        ContextRelevanceMetric(config=judge_cfg_b),
        AnswerCorrectnessMetric(config=judge_cfg_b),
    ]
    run_b = orchestrator.run(dataset, adapter, judges_b, run_id="run-m4-b")
    assert run_b.judge_config_fingerprint != run_a.judge_config_fingerprint

    comp = compare_runs(run_a, run_b)
    assert any(w.category == DriftCategory.JUDGE_CONFIG for w in comp.drift_warnings)
    trend = analyze_trend([run_a, run_b], window=2)
    assert any(w.category == DriftCategory.JUDGE_CONFIG for w in trend.drift_warnings)

    # Custom rubric edit alone changes fingerprint too
    cr_1 = CustomRubricJudgeMetric("Check SLA numeric clarity.", config=judge_cfg_a)
    cr_2 = CustomRubricJudgeMetric("Check SLA numeric clarity and brevity.", config=judge_cfg_a)
    assert cr_1.judge_config_fingerprint != cr_2.judge_config_fingerprint

    # Calibrate GroundednessMetric against offline human labels
    cal_samples = [
        HumanCalibrationSample(
            case_id="cal-sla",
            input="What is the SLA monthly uptime guarantee?",
            output="Our enterprise SLA provides a 99.9% monthly uptime guarantee.",
            retrieved_chunks=[
                RetrievedChunk(
                    id="sla-doc",
                    text="Enterprise SLA policy guarantees 99.9% monthly uptime.",
                )
            ],
            human_score=0.95,
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="cal-france",
            input="What is the capital of France?",
            output="The capital of France is Paris.",
            retrieved_chunks=[
                RetrievedChunk(id="wrong-doc", text="Bananas thrive in warm climates.")
            ],
            human_score=0.05,
            human_passed=False,
        ),
    ]
    cal_report = calibrate_judge(judges_a[0], cal_samples)
    assert cal_report.exact_agreement_rate == 100.0
    assert cal_report.too_generous_rate == 0.0
    assert cal_report.too_harsh_rate == 0.0


def test_orchestrator_fail_fast_aborts_on_inconclusive_judge_batch(tmp_path: Path) -> None:
    ds_path = _write_jsonl(
        tmp_path / "ds.jsonl",
        [
            {"id": "c1", "input": "Q1"},
            {"id": "c2", "input": "Q2"},
        ],
    )
    dataset = DatasetEngine(ds_path, dataset_id="ff-suite")
    adapter = RAGAdapter(lambda q: {"output": f"Ans {q}", "chunks": [{"id": "x", "text": "ctx"}]})
    orchestrator = EvaluationOrchestrator(
        config=OrchestratorConfig(fail_fast=True, max_concurrency=2),
        storage_root=tmp_path / ".evalforge",
    )
    bad_judge = GroundednessMetric(
        config=JudgeConfig(model="mock-judge", mock_mode=True, max_retries=0),
        mock_responses={
            "c1": "invalid-non-json",
            "c2": json.dumps({"score": 1.0, "rationale": "ok"}),
        },
    )
    with pytest.raises(ExecutionError, match="fail_fast"):
        orchestrator.run(dataset, adapter, [bad_judge], run_id="run-ff")


def test_orchestrator_mixes_sync_and_single_judge_and_explicit_override(
    tmp_path: Path,
) -> None:
    ds_path = _write_jsonl(
        tmp_path / "mix.jsonl",
        [{"id": "m1", "input": "Capital?", "reference": "Paris"}],
    )
    dataset = DatasetEngine(ds_path, dataset_id="mix-suite")
    adapter = RAGAdapter(lambda q: {"output": "Paris", "chunks": [{"id": "c1", "text": "Paris"}]})
    g = GroundednessMetric(config=JudgeConfig(model="mock-judge", mock_mode=True))

    orch_auto = EvaluationOrchestrator(storage_root=tmp_path / ".store-a")
    run_single = orch_auto.run(dataset, adapter, [ExactMatchMetric(), g], run_id="mix-1")
    assert run_single.judge_config_fingerprint == g.judge_config_fingerprint
    assert list(run_single.case_results[0].metrics) == ["exact_match", "groundedness"]

    orch_fixed = EvaluationOrchestrator(
        config=OrchestratorConfig(judge_config_fingerprint="explicit-override-fp"),
        storage_root=tmp_path / ".store-b",
    )
    run_override = orch_fixed.run(dataset, adapter, [g], run_id="mix-2")
    assert run_override.judge_config_fingerprint == "explicit-override-fp"
