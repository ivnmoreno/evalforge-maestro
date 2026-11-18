"""Unit tests for exception hierarchy, core contracts, and JSON Schema parity."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from evalforge_maestro.exceptions import (
    AdapterError,
    ConfigurationError,
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
    EvalforgeError,
    ExecutionError,
    ImmutabilityError,
    MemoryLimitExceededError,
    MetricError,
    MissingExtraError,
    StorageError,
)
from evalforge_maestro.types import (
    AggregateMetricSummary,
    CaseCriteria,
    CaseEvaluationRecord,
    CaseMetadata,
    CaseSplit,
    EvaluationCase,
    ExecutionResult,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    RetrievedChunk,
    RunManifestEntry,
    RunRecord,
    TokenUsage,
)


def test_exception_hierarchy_and_missing_extra_messages() -> None:
    assert issubclass(ConfigurationError, EvalforgeError)
    assert issubclass(MissingExtraError, EvalforgeError)
    assert issubclass(EmptyDatasetError, DatasetError)
    assert issubclass(DuplicateCaseIdError, DatasetError)
    assert issubclass(DatasetError, EvalforgeError)
    assert issubclass(AdapterError, EvalforgeError)
    assert issubclass(MetricError, EvalforgeError)
    assert issubclass(MemoryLimitExceededError, ExecutionError)
    assert issubclass(ExecutionError, EvalforgeError)
    assert issubclass(ImmutabilityError, StorageError)
    assert issubclass(StorageError, EvalforgeError)

    err_extra = MissingExtraError(extra="judges", package="litellm")
    assert "evalforge-maestro[judges]" in str(err_extra)
    assert err_extra.extra == "judges"
    assert err_extra.package == "litellm"

    err_plain = MissingExtraError()
    assert "not installed" in str(err_plain)

    ds_err = DatasetError("bad row", line_number=3, case_id="c3", field="input")
    assert ds_err.line_number == 3
    assert ds_err.case_id == "c3"
    assert ds_err.field == "input"


def test_evaluation_case_strict_validation() -> None:
    case = EvaluationCase(
        id="  case-1 ",
        input={"q": "hi"},
        reference="hello",
        metadata=CaseMetadata(tags=["smoke"], split=CaseSplit.EVAL, extra={"k": 1}),
        criteria=CaseCriteria(
            mandatory=True,
            json_schema={"type": "string"},
            pass_threshold=0.8,
            metric_thresholds={"exact_match": 1.0},
        ),
    )
    assert case.id == "case-1"
    assert case.schema_version == "1.0"

    with pytest.raises(ValidationError):
        EvaluationCase(id="   ", input="ok")

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({"id": "c1", "input": "ok", "unknown": 1})

    with pytest.raises(ValidationError):
        EvaluationCase(id="c1", input=float("nan"))

    with pytest.raises(ValidationError):
        CaseMetadata(tags=["   "])

    with pytest.raises(ValidationError):
        CaseCriteria(json_schema={"type": 123})

    with pytest.raises(ValidationError):
        CaseCriteria(pass_threshold=True)

    with pytest.raises(ValidationError):
        CaseCriteria(metric_thresholds={"": 0.5})


def test_execution_and_metric_result_constraints() -> None:
    res = ExecutionResult(
        case_id="c1",
        input="hi",
        output="ok",
        elapsed_seconds=0.05,
        tokens=TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        retrieved_chunks=[RetrievedChunk(id="ch1", text="ctx", rank=1, score=0.9)],
    )
    assert res.elapsed_seconds == 0.05

    with pytest.raises(ValidationError):
        ExecutionResult(case_id="c1", input="hi", elapsed_seconds=-0.1)

    with pytest.raises(ValidationError):
        ExecutionResult(case_id="c1", input="hi", elapsed_seconds=True)

    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=True)

    metric = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=0.1234567,
        status=MetricStatus.PASS,
        explanation="Matched.",
    )
    assert metric.score == 0.123457

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=float("nan"),
            status=MetricStatus.PASS,
            explanation="Invalid",
        )

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=None,
            status=MetricStatus.PASS,
            explanation="Missing score",
        )

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="exact_match",
            metric_version="1.0.0",
            score=0.5,
            status=MetricStatus.NOT_APPLICABLE,
            explanation="Unexpected score",
        )


def test_run_record_manifest_orchestrator_config_and_schema_parity() -> None:
    tz_plus2 = timezone(timedelta(hours=2))
    ts = datetime(2026, 11, 18, 12, 0, 0, tzinfo=tz_plus2)
    exec_res = ExecutionResult(case_id="c1", input="q", output="a", elapsed_seconds=0.1)
    metric_res = MetricResult(
        metric_id="exact_match",
        metric_version="1.0.0",
        score=1.0,
        status=MetricStatus.PASS,
        explanation="Exact match.",
    )
    case_rec = CaseEvaluationRecord(
        case_id="c1",
        mandatory=True,
        execution=exec_res,
        metrics={"exact_match": metric_res},
    )
    run = RunRecord(
        run_id="run-001",
        timestamp=ts,
        package_version="0.1.0",
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
        status_counts={
            status: (1 if status == MetricStatus.PASS else 0) for status in MetricStatus
        },
        case_results=[case_rec],
    )
    assert run.timestamp.utcoffset() == timedelta(0)
    manifest = RunManifestEntry.from_run_record(run)
    assert manifest.aggregate_scores == {"exact_match": 1.0}

    cfg = OrchestratorConfig()
    assert cfg.max_concurrency == 4
    with pytest.raises(ValidationError):
        OrchestratorConfig(max_concurrency=True)

    meta = MetricMetadata(
        metric_id="exact_match",
        metric_version="1.0.0",
        what_it_measures="exact",
        required_case_fields=("reference",),
        required_execution_fields=("output",),
        calculation_method="eq",
        known_limitations="lexical",
    )
    assert meta.metric_id == "exact_match"

    # Parity check against specs/001-evaluation-foundation/contracts/schemas-v1.json
    schema_path = Path("specs/001-evaluation-foundation/contracts/schemas-v1.json")
    contract_schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))
    defs = contract_schema["$defs"]

    def _validate_def(def_name: str, payload: dict[str, Any]) -> None:
        sub_schema = {"$schema": contract_schema["$schema"], "$defs": defs, **defs[def_name]}
        jsonschema.validate(instance=payload, schema=sub_schema)

    case = EvaluationCase(id="c1", input="q", reference="a")
    _validate_def("EvaluationCase", case.model_dump(mode="json"))
    _validate_def("ExecutionResult", exec_res.model_dump(mode="json"))
    _validate_def("MetricResult", metric_res.model_dump(mode="json"))
    _validate_def("CaseEvaluationRecord", case_rec.model_dump(mode="json"))
    _validate_def("RunRecord", run.model_dump(mode="json"))
    _validate_def("RunManifestEntry", manifest.model_dump(mode="json"))
