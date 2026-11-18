"""Contract tests validating Milestone 3 runtime payloads against Draft 2020-12 schemas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from evalforge_maestro.regression import QualityGate, analyze_trend, compare_runs
from evalforge_maestro.types import (
    AggregateMetricSummary,
    AnomalyFlag,
    AnomalyScope,
    AnomalySeverity,
    AnomalyType,
    BaselineEntry,
    BaselineRegistry,
    CaseEvaluationRecord,
    DriftCategory,
    DriftWarning,
    ExecutionResult,
    MetricResult,
    MetricStatus,
    QualityGatePolicy,
    RunManifestEntry,
    RunRecord,
)


def _merged_m3_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    m1 = json.loads(
        Path("specs/001-evaluation-foundation/contracts/schemas-v1.json").read_text(
            encoding="utf-8"
        )
    )
    m2 = json.loads(
        Path("specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json").read_text(
            encoding="utf-8"
        )
    )
    m3 = json.loads(
        Path("specs/003-experiment-regression-engine/contracts/schemas-v1.json").read_text(
            encoding="utf-8"
        )
    )
    defs = {**m1["$defs"], **m2["$defs"], **m3["$defs"]}
    return m3, defs


def _validate(def_name: str, payload: Any) -> None:
    m3, defs = _merged_m3_schema()
    sub = {"$schema": m3["$schema"], "$defs": defs, **defs[def_name]}
    jsonschema.validate(instance=payload, schema=sub)


def _sample_run(run_id: str, score: float, minute: int) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        timestamp=datetime(2026, 11, 18, 12, minute, tzinfo=timezone.utc),
        package_version="0.3.0",
        dataset_id="ds-main",
        dataset_version="1.0",
        dataset_fingerprint="a" * 64,
        evaluated_case_count=1,
        system_version="sys-1",
        model_id="m-1",
        config_fingerprint="b" * 64,
        judge_config_fingerprint="c" * 64,
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
        status_counts={MetricStatus.PASS if score >= 0.5 else MetricStatus.FAIL: 1},
        case_results=[
            CaseEvaluationRecord(
                case_id="c1",
                mandatory=True,
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


def test_m3_foundation_and_baseline_schemas_validate_cleanly() -> None:
    entry = BaselineEntry(
        name="default",
        run_id="run-001",
        pinned_at=datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
        note="release baseline",
        tags=["release", "v1"],
        dataset_id="ds-main",
        dataset_version="1.0",
        dataset_fingerprint="a" * 64,
        system_version="sys-1",
        model_id="m-1",
        config_fingerprint="b" * 64,
        judge_config_fingerprint="c" * 64,
        metric_versions={"exact_match": "1.0.0"},
        aggregate_scores={"exact_match": 1.0, "precision_at_k": None},
    )
    registry = BaselineRegistry(baselines={"default": entry})
    _validate("BaselineEntry", entry.model_dump(mode="json"))
    _validate("BaselineRegistry", registry.model_dump(mode="json"))

    drift = DriftWarning(
        category=DriftCategory.DATASET_FINGERPRINT,
        baseline_run_id="r1",
        candidate_run_id="r2",
        baseline_value="a" * 64,
        candidate_value="b" * 64,
        explanation="Dataset content changed",
    )
    anomaly = AnomalyFlag(
        anomaly_type=AnomalyType.METRIC_DISAGREEMENT,
        severity=AnomalySeverity.WARNING,
        scope=AnomalyScope.CASE,
        case_id="c1",
        metric_ids=["exact_match", "precision_at_k"],
        spread=1.0,
        explanation="Answer pass masked broken retrieval",
    )
    policy = QualityGatePolicy(min_metric_scores={"exact_match": 0.9})
    _validate("DriftWarning", drift.model_dump(mode="json"))
    _validate("AnomalyFlag", anomaly.model_dump(mode="json"))
    _validate("QualityGatePolicy", policy.model_dump(mode="json"))

    with pytest.raises(jsonschema.ValidationError):
        _validate(
            "BaselineEntry",
            {**entry.model_dump(mode="json"), "name": "bad..name"},
        )


def test_m3_comparison_trend_and_gate_runtime_outputs_match_json_schema() -> None:
    r1 = _sample_run("run-001", 1.0, 0)
    r2 = _sample_run("run-002", 0.9, 5)
    manifest_1 = RunManifestEntry.from_run_record(r1)
    manifest_2 = RunManifestEntry.from_run_record(r2)

    _validate("RunRecord", r1.model_dump(mode="json"))
    _validate("RunManifestEntry", manifest_1.model_dump(mode="json"))

    comp = compare_runs(r1, r2, baseline_name="default")
    comp_json = comp.model_dump(mode="json")
    _validate("RunComparisonReport", comp_json)
    _validate("TargetChangeSummary", comp_json["target_changes"])
    _validate("MetricComparison", comp_json["metric_comparisons"]["exact_match"])
    _validate("CaseComparison", comp_json["case_comparisons"][0])
    _validate("CaseMetricDelta", comp_json["case_comparisons"][0]["metrics"]["exact_match"])

    trend = analyze_trend([manifest_1, manifest_2], window=5)
    trend_json = trend.model_dump(mode="json")
    _validate("TrendReport", trend_json)
    _validate("MetricTrendSummary", trend_json["metrics"]["exact_match"])
    _validate("TrendDataPoint", trend_json["metrics"]["exact_match"]["points"][0])

    gate_res = QualityGate(QualityGatePolicy(max_regression_drop=0.05)).evaluate(
        r2, comparison=comp, trend=trend
    )
    gate_json = gate_res.model_dump(mode="json")
    _validate("QualityGateResult", gate_json)
    _validate("GateRuleCheck", gate_json["checks"][0])
