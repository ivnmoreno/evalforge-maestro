"""Unit tests for judge calibration diagnostics, directional bias, and threshold sweeps."""

from __future__ import annotations

import asyncio
import json

import pytest

from evalforge_maestro.exceptions import ConfigurationError, DuplicateCaseIdError, EmptyDatasetError
from evalforge_maestro.judges.calibration import acalibrate_judge, calibrate_judge
from evalforge_maestro.judges.metrics import AnswerCorrectnessMetric, GroundednessMetric
from evalforge_maestro.metrics import ExactMatchMetric
from evalforge_maestro.types import (
    CalibrationDisagreementType,
    EvaluationCase,
    ExecutionResult,
    HumanCalibrationSample,
    JudgeConfig,
    MetricMetadata,
    MetricResult,
    MetricStatus,
    RetrievedChunk,
)


def _chunk() -> list[RetrievedChunk]:
    return [RetrievedChunk(id="d1", text="Reference context clause.")]


def test_calibrate_detects_too_generous_bias_and_raises_recommended_threshold() -> None:
    # Judge scores: fails=[0.55, 0.65] (falsely passes at 0.50!), passes=[0.85, 0.90]
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    metric = GroundednessMetric(
        config=cfg,
        mock_responses={
            "c1": json.dumps({"score": 0.55, "rationale": "Slightly generous on flaw."}),
            "c2": json.dumps({"score": 0.65, "rationale": "Passed weak claim."}),
            "c3": json.dumps({"score": 0.85, "rationale": "Strong grounding."}),
            "c4": json.dumps({"score": 0.90, "rationale": "Exact support."}),
        },
    )
    samples = [
        HumanCalibrationSample(
            case_id="c1",
            input="q",
            output="o1",
            retrieved_chunks=_chunk(),
            human_score=0.2,
            human_passed=False,
            notes="Should fail: unsupported claim.",
        ),
        HumanCalibrationSample(
            case_id="c2",
            input="q",
            output="o2",
            retrieved_chunks=_chunk(),
            human_score=0.3,
            human_passed=False,
            notes="Should fail: hallucinated detail.",
        ),
        HumanCalibrationSample(
            case_id="c3",
            input="q",
            output="o3",
            retrieved_chunks=_chunk(),
            human_score=0.9,
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="c4",
            input="q",
            output="o4",
            retrieved_chunks=_chunk(),
            human_score=0.95,
            human_passed=True,
        ),
    ]

    report = calibrate_judge(metric, samples)
    assert report.schema_version == "1.0"
    assert report.metric_id == "groundedness"
    assert report.total_cases == 4
    assert report.valid_cases == 4
    assert report.inconclusive_cases == 0
    assert report.exact_agreement_rate == 50.0
    assert report.too_generous_rate == 0.5
    assert report.too_harsh_rate == 0.0
    assert report.mean_score_delta is not None and report.mean_score_delta > 0.0
    assert [d.case_id for d in report.disagreements] == ["c1", "c2"]
    assert all(
        d.disagreement_type == CalibrationDisagreementType.TOO_GENEROUS
        for d in report.disagreements
    )
    assert report.disagreements[0].human_notes == "Should fail: unsupported claim."
    # Optimal separator between 0.65 (fail) and 0.85 (pass) is midpoint 0.75
    assert report.recommended_pass_threshold == 0.75


def test_calibrate_detects_too_harsh_bias_and_lowers_threshold() -> None:
    # Judge scores: fails=[0.15], passes=[0.35, 0.45, 0.80] at threshold=0.6
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.6)
    metric = GroundednessMetric(
        config=cfg,
        mock_responses={
            "h1": json.dumps({"score": 0.15, "rationale": "Bad."}),
            "h2": json.dumps({"score": 0.35, "rationale": "Strict."}),
            "h3": json.dumps({"score": 0.45, "rationale": "Harsh."}),
            "h4": json.dumps({"score": 0.80, "rationale": "Good."}),
        },
    )
    samples = [
        HumanCalibrationSample(
            case_id="h1",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_passed=False,
        ),
        HumanCalibrationSample(
            case_id="h2",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="h3",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="h4",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_passed=True,
        ),
    ]

    report = asyncio.run(acalibrate_judge(metric, samples))
    assert report.exact_agreement_rate == 50.0
    assert report.too_harsh_rate == 0.5
    assert report.too_generous_rate == 0.0
    assert report.mean_score_delta is not None and report.mean_score_delta < 0.0
    assert [d.disagreement_type for d in report.disagreements] == [
        CalibrationDisagreementType.TOO_HARSH,
        CalibrationDisagreementType.TOO_HARSH,
    ]
    # Optimal separator between 0.15 (fail) and 0.35 (pass) -> 0.25 or 0.35 (0.35 closer to 0.6)
    assert report.recommended_pass_threshold == 0.35


def test_calibrate_flags_same_verdict_score_divergence_without_lowering_agreement() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    metric = GroundednessMetric(
        config=cfg,
        mock_responses={
            "s1": json.dumps({"score": 0.55, "rationale": "Barely pass."}),
            "s2": json.dumps({"score": 0.90, "rationale": "Clean match."}),
        },
    )
    samples = [
        HumanCalibrationSample(
            case_id="s1",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_score=0.95,
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="s2",
            input="q",
            output="a",
            retrieved_chunks=_chunk(),
            human_score=0.90,
            human_passed=True,
        ),
    ]
    report = calibrate_judge(metric, samples, score_divergence_threshold=0.25)
    # Q4 clarified rule: pass/fail agreed -> 100.0% agreement & 0 bias, yet score_divergence logged
    assert report.exact_agreement_rate == 100.0
    assert report.too_generous_rate == 0.0
    assert report.too_harsh_rate == 0.0
    assert len(report.disagreements) == 1
    assert report.disagreements[0].case_id == "s1"
    assert report.disagreements[0].disagreement_type == CalibrationDisagreementType.SCORE_DIVERGENCE
    assert report.disagreements[0].score_delta == -0.4
    assert report.recommended_pass_threshold == 0.5


def test_calibrate_tracks_inconclusive_not_applicable_and_all_inconclusive() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    metric = AnswerCorrectnessMetric(
        config=cfg,
        mock_responses={
            "bad-json": "not json!",
            "valid": json.dumps({"score": 0.8, "rationale": "Correct."}),
        },
    )
    mixed_samples = [
        HumanCalibrationSample(
            case_id="bad-json",
            input="q",
            output="a",
            reference="ref",
            human_passed=True,
        ),
        HumanCalibrationSample(
            case_id="no-ref",
            input="q",
            output="a",
            reference=None,
            human_passed=False,
        ),
        HumanCalibrationSample(
            case_id="valid",
            input="q",
            output="a",
            reference="ref",
            human_passed=True,
        ),
    ]
    report = calibrate_judge(metric, mixed_samples)
    assert report.total_cases == 3
    assert report.valid_cases == 1
    assert report.inconclusive_cases == 2
    assert report.exact_agreement_rate == 100.0
    assert len(report.disagreements) == 2
    assert [d.judge_status for d in report.disagreements] == [
        MetricStatus.INCONCLUSIVE,
        MetricStatus.NOT_APPLICABLE,
    ]
    assert all(
        d.disagreement_type == CalibrationDisagreementType.INCONCLUSIVE
        for d in report.disagreements
    )

    all_inc_report = calibrate_judge(metric, [mixed_samples[0], mixed_samples[1]])
    assert all_inc_report.valid_cases == 0
    assert all_inc_report.inconclusive_cases == 2
    assert all_inc_report.exact_agreement_rate is None
    assert all_inc_report.too_generous_rate is None
    assert all_inc_report.too_harsh_rate is None
    assert all_inc_report.mean_human_score is None
    assert all_inc_report.mean_judge_score is None
    assert all_inc_report.mean_score_delta is None
    assert all_inc_report.recommended_pass_threshold == 0.5


def test_calibrate_validation_errors_and_authoritative_human_passed() -> None:
    cfg = JudgeConfig(model="mock-judge", mock_mode=True, pass_threshold=0.5)
    metric = GroundednessMetric(config=cfg)

    with pytest.raises(EmptyDatasetError):
        calibrate_judge(metric, [])

    dup_sample = HumanCalibrationSample(
        case_id="dup-1",
        input="q",
        output="a",
        retrieved_chunks=_chunk(),
        human_passed=True,
    )
    with pytest.raises(DuplicateCaseIdError):
        calibrate_judge(metric, [dup_sample, dup_sample])

    for bad_kw in (
        {"human_threshold": True},
        {"human_threshold": 1.2},
        {"score_divergence_threshold": 0.0},
        {"score_divergence_threshold": True},
        {"max_concurrency": 0},
        {"max_concurrency": True},
    ):
        with pytest.raises(ConfigurationError):
            calibrate_judge(metric, [dup_sample], **bad_kw)

    # When both human_score and human_passed are set, human_passed governs verdict
    m_auth = GroundednessMetric(
        config=cfg,
        mock_responses={"auth-1": json.dumps({"score": 0.85, "rationale": "High."})},
    )
    sample_auth = HumanCalibrationSample(
        case_id="auth-1",
        input="q",
        output="a",
        retrieved_chunks=_chunk(),
        human_score=0.7,
        human_passed=False,
    )
    rep_auth = calibrate_judge(m_auth, [sample_auth])
    assert rep_auth.too_generous_rate == 1.0
    assert rep_auth.exact_agreement_rate == 0.0


def test_calibrate_supports_sync_and_custom_async_metrics_and_running_loop() -> None:
    em = ExactMatchMetric()
    samples = [
        HumanCalibrationSample(
            case_id="e1", input="q", output="Paris", reference="Paris", human_passed=True
        ),
        HumanCalibrationSample(
            case_id="e2", input="q", output="Lyon", reference="Paris", human_passed=False
        ),
    ]
    em_report = calibrate_judge(em, samples, human_threshold=0.5)
    assert em_report.metric_id == "exact_match"
    assert em_report.exact_agreement_rate == 100.0

    class _FaultySyncMetric:
        @property
        def metadata(self) -> MetricMetadata:
            return MetricMetadata(
                metric_id="faulty_sync",
                metric_version="1.0",
                what_it_measures="test",
                required_case_fields=("input",),
                required_execution_fields=("output",),
                calculation_method="sync",
                known_limitations="none",
            )

        def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
            if case.id == "e1":
                raise RuntimeError("sync boom")
            return MetricResult(
                metric_id="faulty_sync",
                metric_version="1.0",
                score=0.2,
                status=MetricStatus.FAIL,
                explanation="low",
            )

    fault_rep = calibrate_judge(_FaultySyncMetric(), samples)
    assert fault_rep.inconclusive_cases == 1
    assert fault_rep.valid_cases == 1

    class _AsyncMetric:
        @property
        def metadata(self) -> MetricMetadata:
            return MetricMetadata(
                metric_id="async_custom",
                metric_version="1.0",
                what_it_measures="test",
                required_case_fields=("input",),
                required_execution_fields=("output",),
                calculation_method="async",
                known_limitations="none",
            )

        def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
            raise AssertionError("aevaluate should be preferred")

        async def aevaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
            if case.id == "e1":
                raise RuntimeError("async boom")
            return MetricResult(
                metric_id="async_custom",
                metric_version="1.0",
                score=0.9,
                status=MetricStatus.PASS,
                explanation="high",
            )

    async def _run_inside_loop() -> float | None:
        inner = calibrate_judge(_AsyncMetric(), samples)
        return inner.exact_agreement_rate

    assert asyncio.run(_run_inside_loop()) == 0.0
