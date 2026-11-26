"""Contract tests validating Milestone 5 schemas against merged M1-M5 Draft 2020-12."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from evalforge_maestro.reporting import build_run_report
from evalforge_maestro.types import (
    AggregateMetricSummary,
    BaselineCommandPayload,
    BaselineEntry,
    CaseEvaluationRecord,
    CLIErrorPayload,
    CLIResolvedConfig,
    ConfigSettingProvenance,
    ConfigSourceTier,
    ConfigValidationPayload,
    ExecutionResult,
    MetricResult,
    MetricSpecConfig,
    MetricStatus,
    RunRecord,
)


def _merged_m5_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    schemas_dir = Path(__file__).resolve().parent / "schemas"
    defs: dict[str, Any] = {}
    m5: dict[str, Any] = {}
    for filename in (
        "m1-schemas-v1.json",
        "m2-schemas-v1.json",
        "m3-schemas-v1.json",
        "m4-schemas-v1.json",
        "m5-schemas-v1.json",
    ):
        doc = json.loads((schemas_dir / filename).read_text(encoding="utf-8"))
        defs.update(doc["$defs"])
        m5 = doc
    merged = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs}
    jsonschema.Draft202012Validator.check_schema(merged)
    return merged, m5


def _validate_def(schema_root: dict[str, Any], def_name: str, instance: Any) -> None:
    validator = jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": schema_root["$defs"]}
    )
    validator.validate(instance)


def test_m5_schema_contract_is_valid_draft_2020_12() -> None:
    merged, m5 = _merged_m5_schema()
    assert {
        "ConfigSourceTier",
        "TargetType",
        "ReportKind",
        "EvidenceDecouplingCategory",
        "MetricSpecConfig",
        "CLIResolvedConfig",
        "ReportDocument",
        "BaselineCommandPayload",
        "ConfigValidationPayload",
        "CLIErrorPayload",
    } <= set(m5["$defs"])
    assert len(merged["$defs"]) >= 61


def test_m5_runtime_models_validate_against_contract_schemas() -> None:
    merged, _ = _merged_m5_schema()

    cfg = CLIResolvedConfig(
        dataset="eval.jsonl",
        metrics=[MetricSpecConfig(metric_id="exact_match")],
        provenance=[
            ConfigSettingProvenance(
                key="judge.api_key",
                value="sk-should-redact",
                source=ConfigSourceTier.ENV,
            )
        ],
    )
    m5_cfg = cfg.model_dump(mode="json")
    m5_cfg["target"].pop("agent_extractors", None)
    for k in ("repeats", "baseline_runs", "embedding", "otel_traces", "otel"):
        m5_cfg.pop(k, None)
    m5_cfg["execution"].pop("embedding_config_fingerprint", None)
    for k in ("confidence_level", "min_statistical_samples", "fail_on_significant_regression"):
        m5_cfg["gate"].pop(k, None)
    _validate_def(merged, "CLIResolvedConfig", m5_cfg)

    run = RunRecord(
        run_id="run-schema-1",
        timestamp=datetime(2026, 11, 19, tzinfo=UTC),
        package_version="0.5.0",
        dataset_id="ds-1",
        dataset_fingerprint="a" * 64,
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
        status_counts={MetricStatus.PASS: 1},
        case_results=[
            CaseEvaluationRecord(
                case_id="c1",
                execution=ExecutionResult(
                    case_id="c1", input="q", output="a", elapsed_seconds=0.01
                ),
                metrics={
                    "exact_match": MetricResult(
                        metric_id="exact_match",
                        metric_version="1.0.0",
                        score=1.0,
                        status=MetricStatus.PASS,
                        explanation="ok",
                    )
                },
            )
        ],
    )
    report_doc = build_run_report(run)
    m5_report = report_doc.model_dump(mode="json")
    for k in ("cohort_run_ids", "cohort_aggregates"):
        m5_report.pop(k, None)
    m5_report["evaluation"].pop("embedding_config_fingerprint", None)
    _validate_def(merged, "ReportDocument", m5_report)

    entry = BaselineEntry(
        name="prod",
        run_id="run-schema-1",
        pinned_at=datetime(2026, 11, 19, tzinfo=UTC),
        dataset_id="ds-1",
        dataset_fingerprint="a" * 64,
        metric_versions={"exact_match": "1.0.0"},
        aggregate_scores={"exact_match": 1.0},
    )
    base_payload = BaselineCommandPayload(action="set", entry=entry, baselines=[entry])
    m5_base = base_payload.model_dump(mode="json")
    if m5_base.get("entry"):
        m5_base["entry"].pop("embedding_config_fingerprint", None)
    for b in m5_base.get("baselines", []):
        b.pop("embedding_config_fingerprint", None)
    _validate_def(merged, "BaselineCommandPayload", m5_base)

    val_payload = ConfigValidationPayload(
        valid=True,
        config_path="evalforge.toml",
        warnings=["Plaintext key detected"],
    )
    _validate_def(merged, "ConfigValidationPayload", val_payload.model_dump(mode="json"))

    err_payload = CLIErrorPayload(
        exit_code=4,
        error_type="LocalOnlyPolicyError",
        message="Blocked remote endpoint",
        hint="Use --mock",
    )
    _validate_def(merged, "CLIErrorPayload", err_payload.model_dump(mode="json"))
