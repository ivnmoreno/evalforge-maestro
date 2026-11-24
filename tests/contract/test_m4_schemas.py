"""Contract tests validating Milestone 4 runtime payloads against Draft 2020-12 schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from evalforge_maestro.types import (
    CalibrationDisagreement,
    CalibrationDisagreementType,
    CalibrationReport,
    HumanCalibrationSample,
    JudgeConfig,
    JudgeResponse,
    MetricStatus,
    RetrievedChunk,
)


def _merged_m4_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    schemas_dir = Path(__file__).resolve().parent / "schemas"
    defs: dict[str, Any] = {}
    m4: dict[str, Any] = {}
    for filename in (
        "m1-schemas-v1.json",
        "m2-schemas-v1.json",
        "m3-schemas-v1.json",
        "m4-schemas-v1.json",
    ):
        doc = json.loads((schemas_dir / filename).read_text(encoding="utf-8"))
        defs.update(doc["$defs"])
        m4 = doc
    merged = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs}
    jsonschema.Draft202012Validator.check_schema(merged)
    return merged, m4


def _validate_def(schema_root: dict[str, Any], def_name: str, instance: Any) -> None:
    validator = jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{def_name}", "$defs": schema_root["$defs"]}
    )
    validator.validate(instance)


def test_m4_schema_contract_is_valid_draft_2020_12() -> None:
    merged, m4 = _merged_m4_schema()
    assert set(m4["$defs"]) == {
        "CalibrationDisagreementType",
        "JudgeConfig",
        "JudgeResponse",
        "HumanCalibrationSample",
        "CalibrationDisagreement",
        "CalibrationReport",
    }
    assert len(merged["$defs"]) >= 42


def test_m4_runtime_models_validate_against_contract_schemas() -> None:
    merged, _ = _merged_m4_schema()

    cfg = JudgeConfig(
        model="ollama_chat/llama3.2",
        api_base="http://localhost:11434",
        temperature=0.0,
        pass_threshold=0.6,
        local_only=True,
        mock_mode=False,
        extra_params={"top_p": 0.9, "api_key": "secret-should-redact"},
    )
    _validate_def(merged, "JudgeConfig", cfg.model_dump(mode="json"))

    resp = JudgeResponse(
        score=0.875,
        rationale="All claims align with cited chunk text.",
        verdict="PASS",
        supported_claims=["SLA uptime is 99.9%."],
        unsupported_claims=[],
    )
    _validate_def(merged, "JudgeResponse", resp.model_dump(mode="json"))

    sample = HumanCalibrationSample(
        case_id="cal-1",
        input="What is the SLA?",
        output="Our SLA guarantees 99.9% uptime.",
        reference="99.9% monthly uptime SLA",
        retrieved_chunks=[RetrievedChunk(id="doc1", text="SLA guarantees 99.9% uptime.")],
        human_score=0.9,
        human_passed=True,
        notes="Clear match",
    )
    _validate_def(merged, "HumanCalibrationSample", sample.model_dump(mode="json"))

    disagreement = CalibrationDisagreement(
        case_id="cal-2",
        disagreement_type=CalibrationDisagreementType.TOO_GENEROUS,
        human_score=0.2,
        human_passed=False,
        judge_score=0.8,
        judge_status=MetricStatus.PASS,
        judge_passed=True,
        score_delta=0.6,
        judge_rationale="Judge accepted unsupported claim.",
        human_notes="Fabricated claim missed by judge.",
    )
    _validate_def(merged, "CalibrationDisagreement", disagreement.model_dump(mode="json"))

    report = CalibrationReport(
        metric_id="groundedness",
        metric_version="1.0.0",
        judge_config=cfg,
        judge_config_fingerprint=cfg.fingerprint,
        total_cases=2,
        valid_cases=2,
        inconclusive_cases=0,
        pass_threshold_evaluated=0.6,
        human_threshold_evaluated=0.6,
        score_divergence_threshold=0.25,
        exact_agreement_rate=50.0,
        too_generous_rate=0.5,
        too_harsh_rate=0.0,
        mean_human_score=0.55,
        mean_judge_score=0.8375,
        mean_score_delta=0.2875,
        disagreements=[disagreement],
        recommended_pass_threshold=0.75,
    )
    _validate_def(merged, "CalibrationReport", report.model_dump(mode="json"))

    with pytest.raises(jsonschema.ValidationError):
        _validate_def(
            merged,
            "JudgeConfig",
            {**cfg.model_dump(mode="json"), "api_base": "http://localhost:11434?api_key=bad"},
        )
    with pytest.raises(jsonschema.ValidationError):
        _validate_def(
            merged,
            "HumanCalibrationSample",
            {"case_id": "cal-bad", "input": "q", "output": "a"},
        )
