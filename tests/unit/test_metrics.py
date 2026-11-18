"""Unit tests covering 100% branch behavior of deterministic baseline metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalforge_maestro.adapters import CallableAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.metrics import (
    ExactMatchMetric,
    JsonSchemaValidationMetric,
    NormalizedMatchMetric,
    exact_match,
    json_schema_validation,
    normalized_match,
)
from evalforge_maestro.types import (
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    Metric,
    MetricStatus,
)


def _exec(
    output: object = None,
    *,
    errors: list[str] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        case_id="c1",
        input="q",
        output=output,
        elapsed_seconds=0.01,
        errors=errors or [],
    )


def test_exact_match_all_branches() -> None:
    assert isinstance(exact_match, Metric)
    assert exact_match.metadata.metric_id == "exact_match"
    assert exact_match.metadata.metric_version == "1.0.0"

    # Upstream error -> INCONCLUSIVE
    err_res = exact_match.evaluate(
        EvaluationCase(id="c1", input="q", reference="a"),
        _exec("a", errors=["TimeoutError: timed out"]),
    )
    assert err_res.status == MetricStatus.INCONCLUSIVE
    assert err_res.score is None

    # Missing reference -> NOT_APPLICABLE
    na_res = exact_match.evaluate(EvaluationCase(id="c1", input="q"), _exec("a"))
    assert na_res.status == MetricStatus.NOT_APPLICABLE
    assert na_res.score is None

    # Exact string match vs mismatch
    pass_res = exact_match.evaluate(EvaluationCase(id="c1", input="q", reference="Ok"), _exec("Ok"))
    assert pass_res.status == MetricStatus.PASS
    assert pass_res.score == 1.0

    fail_res = exact_match.evaluate(EvaluationCase(id="c1", input="q", reference="Ok"), _exec("ok"))
    assert fail_res.status == MetricStatus.FAIL
    assert fail_res.score == 0.0

    # Non-string output against string reference -> 0.0 FAIL with type mismatch (no str() coercion)
    type_fail = exact_match.evaluate(
        EvaluationCase(id="c1", input="q", reference="123"), _exec(123)
    )
    assert type_fail.status == MetricStatus.FAIL
    assert type_fail.score == 0.0
    assert "Type mismatch" in type_fail.explanation

    none_fail = exact_match.evaluate(
        EvaluationCase(id="c1", input="q", reference="123"), _exec(None)
    )
    assert none_fail.status == MetricStatus.FAIL
    assert none_fail.score == 0.0

    # Structured / non-string reference (strict type + value equality)
    struct_pass = exact_match.evaluate(
        EvaluationCase(id="c1", input="q", reference={"k": 1}), _exec({"k": 1})
    )
    assert struct_pass.status == MetricStatus.PASS
    struct_bool_fail = exact_match.evaluate(
        EvaluationCase(id="c1", input="q", reference=1), _exec(True)
    )
    assert struct_bool_fail.status == MetricStatus.FAIL

    # Threshold precedence: metric_thresholds > pass_threshold > metric threshold
    custom = ExactMatchMetric(threshold=0.5)
    case_thresh = EvaluationCase(
        id="c1",
        input="q",
        reference="a",
        criteria=CaseCriteria(pass_threshold=0.8, metric_thresholds={"exact_match": 0.0}),
    )
    override_pass = custom.evaluate(case_thresh, _exec("b"))
    assert override_pass.status == MetricStatus.PASS
    assert override_pass.score == 0.0

    case_pass_thresh = EvaluationCase(
        id="c1",
        input="q",
        reference="a",
        criteria=CaseCriteria(pass_threshold=0.0),
    )
    assert custom.evaluate(case_pass_thresh, _exec("b")).status == MetricStatus.PASS

    with pytest.raises(MetricError):
        ExactMatchMetric(threshold=1.5)
    with pytest.raises(MetricError):
        ExactMatchMetric(threshold=True)


def test_normalized_match_all_branches() -> None:
    assert isinstance(normalized_match, Metric)
    assert normalized_match.metadata.metric_id == "normalized_match"

    # Error -> INCONCLUSIVE
    assert (
        normalized_match.evaluate(
            EvaluationCase(id="c1", input="q", reference="hi"),
            _exec("hi", errors=["boom"]),
        ).status
        == MetricStatus.INCONCLUSIVE
    )

    # Absent or non-string reference -> NOT_APPLICABLE
    assert (
        normalized_match.evaluate(EvaluationCase(id="c1", input="q"), _exec("hi")).status
        == MetricStatus.NOT_APPLICABLE
    )
    assert (
        normalized_match.evaluate(
            EvaluationCase(id="c1", input="q", reference={"k": 1}), _exec("hi")
        ).status
        == MetricStatus.NOT_APPLICABLE
    )

    # Non-string output -> 0.0 FAIL
    bad_out = normalized_match.evaluate(
        EvaluationCase(id="c1", input="q", reference="hi"), _exec({"hi": 1})
    )
    assert bad_out.status == MetricStatus.FAIL
    assert bad_out.score == 0.0

    # NFC + whitespace collapse + case-insensitive default
    nfc = "\u00e9"
    nfd = "e\u0301"
    res = normalized_match.evaluate(
        EvaluationCase(id="c1", input="q", reference=f"  Caf{nfc}   Au  Lait "),
        _exec(f"caf{nfd} au lait"),
    )
    assert res.status == MetricStatus.PASS
    assert res.score == 1.0

    # Case-sensitive & punctuation options
    cs_metric = NormalizedMatchMetric(case_sensitive=True)
    assert (
        cs_metric.evaluate(
            EvaluationCase(id="c1", input="q", reference="Hello"),
            _exec("hello"),
        ).status
        == MetricStatus.FAIL
    )

    punct_metric = NormalizedMatchMetric(strip_punctuation=True)
    assert (
        punct_metric.evaluate(
            EvaluationCase(id="c1", input="q", reference="Hello, world!"),
            _exec("hello world"),
        ).status
        == MetricStatus.PASS
    )

    with pytest.raises(MetricError):
        NormalizedMatchMetric(threshold=-0.1)


def test_json_schema_validation_all_branches() -> None:
    assert isinstance(json_schema_validation, Metric)
    assert json_schema_validation.metadata.metric_id == "json_schema_validation"

    schema_obj = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "additionalProperties": False,
    }

    # Upstream error -> INCONCLUSIVE
    assert (
        json_schema_validation.evaluate(
            EvaluationCase(
                id="c1",
                input="q",
                criteria=CaseCriteria(json_schema=schema_obj),
            ),
            _exec("{}", errors=["err"]),
        ).status
        == MetricStatus.INCONCLUSIVE
    )

    # Absent schema -> NOT_APPLICABLE (even if reference is a non-schema dict)
    assert (
        json_schema_validation.evaluate(
            EvaluationCase(id="c1", input="q", reference={"name": "Alice"}),
            _exec('{"name": "Alice"}'),
        ).status
        == MetricStatus.NOT_APPLICABLE
    )

    # Precedence 1: criteria.json_schema overrides schema-like reference
    case_criteria_wins = EvaluationCase(
        id="c1",
        input="q",
        reference={"type": "string"},
        criteria=CaseCriteria(json_schema=schema_obj),
    )
    assert (
        json_schema_validation.evaluate(
            case_criteria_wins, _exec('{"name": "Alice", "age": 30}')
        ).status
        == MetricStatus.PASS
    )

    # Precedence 2: schema-like reference mapping
    case_ref_schema = EvaluationCase(id="c1", input="q", reference=schema_obj)
    assert (
        json_schema_validation.evaluate(case_ref_schema, _exec({"name": "Bob", "age": 22})).status
        == MetricStatus.PASS
    )

    # Precedence 3: metric-level default schema fallback
    metric_with_default = JsonSchemaValidationMetric(schema=schema_obj)
    assert (
        metric_with_default.evaluate(
            EvaluationCase(id="c1", input="q", reference={"answer": "ignored"}),
            _exec('{"name": "Eve", "age": 40}'),
        ).status
        == MetricStatus.PASS
    )

    # Output failures: None, invalid JSON string, schema violation
    assert json_schema_validation.evaluate(case_ref_schema, _exec(None)).status == MetricStatus.FAIL
    bad_json = json_schema_validation.evaluate(case_ref_schema, _exec("{not valid"))
    assert bad_json.status == MetricStatus.FAIL
    assert "Invalid JSON" in bad_json.explanation

    bad_schema_out = json_schema_validation.evaluate(
        case_ref_schema, _exec('{"name": "Bob", "age": "wrong", "extra": 1}')
    )
    assert bad_schema_out.status == MetricStatus.FAIL
    assert len(bad_schema_out.evidence) >= 1

    # Invalid reference schema mapping triggers MetricError cleanly (isolated if via orchestrator)
    bad_ref_case = EvaluationCase(id="c1", input="q", reference={"type": 123})
    with pytest.raises(MetricError):
        json_schema_validation.evaluate(bad_ref_case, _exec("{}"))

    with pytest.raises(MetricError):
        JsonSchemaValidationMetric(schema={"type": 123})
    with pytest.raises(MetricError):
        JsonSchemaValidationMetric(threshold=2.0)


def test_orchestrator_aggregates_exclude_na_and_surface_mandatory_failures(
    tmp_path: Path,
) -> None:
    ds = DatasetEngine(
        [
            {"id": "c1", "input": "ok", "reference": "OK", "criteria": {"mandatory": False}},
            {"id": "c2", "input": "no-ref", "criteria": {"mandatory": True}},
            {"id": "c3", "input": "bad", "reference": "EXPECTED", "criteria": {"mandatory": True}},
            {"id": "c4", "input": "boom", "reference": "OK", "criteria": {"mandatory": True}},
        ]
    )

    def target(val: str) -> str:
        if val == "boom":
            raise RuntimeError("crash")
        return val

    orch = EvaluationOrchestrator(storage_root=tmp_path / ".evalforge")
    run = orch.run(ds, CallableAdapter(target), [normalized_match])

    agg = run.aggregates["normalized_match"]
    # c1 PASS (1.0), c2 NOT_APPLICABLE (excluded!), c3 FAIL (0.0), c4 INCONCLUSIVE (excluded)
    assert agg.applicable_count == 2
    assert agg.mean_score == 0.5
    assert agg.pass_count == 1
    assert agg.fail_count == 1
    assert agg.not_applicable_count == 1
    assert agg.inconclusive_count == 1

    assert run.status_counts[MetricStatus.PASS] == 1
    assert run.status_counts[MetricStatus.FAIL] == 1
    assert run.status_counts[MetricStatus.NOT_APPLICABLE] == 1
    assert run.status_counts[MetricStatus.INCONCLUSIVE] == 1
    assert run.status_counts[MetricStatus.WARNING] == 0

    # c2 was NOT_APPLICABLE (did not fail); c3 failed and c4 errored -> mandatory failures
    assert run.has_mandatory_failures is True
    assert run.mandatory_failed_case_ids == ["c3", "c4"]
