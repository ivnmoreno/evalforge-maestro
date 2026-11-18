"""Human ground-truth calibration diagnostics and threshold optimization engine."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from evalforge_maestro._canonical import (
    FLOAT_EPSILON,
    canonical_sha256,
    round_delta,
    round_percentage,
    round_score,
    scrub_secret_text,
)
from evalforge_maestro.exceptions import (
    ConfigurationError,
    DuplicateCaseIdError,
    EmptyDatasetError,
    LocalOnlyPolicyError,
    MissingExtraError,
)
from evalforge_maestro.types import (
    AsyncBatchMetric,
    CalibrationDisagreement,
    CalibrationDisagreementType,
    CalibrationReport,
    CaseMetadata,
    EvaluationCase,
    ExecutionResult,
    HumanCalibrationSample,
    JudgeConfig,
    Metric,
    MetricResult,
    MetricStatus,
)


def _validate_unit_float(value: float, *, name: str, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be numeric, not {type(value).__name__}")
    num = float(value)
    if not math.isfinite(num):
        raise ConfigurationError(f"{name} must be finite, got {value!r}")
    if allow_zero:
        if not (0.0 <= num <= 1.0):
            raise ConfigurationError(f"{name} must be in [0.0, 1.0], got {num}")
    elif not (0.0 < num <= 1.0):
        raise ConfigurationError(f"{name} must be in (0.0, 1.0], got {num}")
    return round_score(num)


def _resolve_judge_provenance(judge: Metric) -> tuple[JudgeConfig, str]:
    raw_cfg = getattr(judge, "judge_config", None)
    if isinstance(raw_cfg, JudgeConfig):
        resolved_cfg = raw_cfg
    else:
        resolved_cfg = JudgeConfig(
            model=judge.metadata.metric_id,
            prompt_version=judge.metadata.metric_version,
            mock_mode=True,
        )

    raw_fp = getattr(judge, "judge_config_fingerprint", None)
    if isinstance(raw_fp, str) and len(raw_fp) == 64:
        return resolved_cfg, raw_fp

    derived_fp = canonical_sha256(
        {
            "metric_id": judge.metadata.metric_id,
            "metric_version": judge.metadata.metric_version,
            "config": resolved_cfg.redacted_dict(),
        }
    )
    return resolved_cfg, derived_fp


def _optimize_pass_threshold(
    valid_rows: list[tuple[float, float, bool]],
    *,
    active_threshold: float,
) -> float:
    if not valid_rows:
        return active_threshold

    unique_scores = sorted({round_score(judge_score) for _, judge_score, _ in valid_rows})
    candidate_set: set[float] = {0.0, round_score(active_threshold), 1.0}
    candidate_set.update(unique_scores)
    for idx in range(len(unique_scores) - 1):
        candidate_set.add(round_score((unique_scores[idx] + unique_scores[idx + 1]) / 2.0))
    candidates = sorted(candidate_set)

    def _score_candidate(threshold: float) -> tuple[int, int, float]:
        agree = 0
        generous = 0
        harsh = 0
        for _, judge_score, human_passed in valid_rows:
            judge_passed = judge_score >= threshold - FLOAT_EPSILON
            if judge_passed == human_passed:
                agree += 1
            elif judge_passed:
                generous += 1
            else:
                harsh += 1
        bias_skew = abs(generous - harsh)
        dist = round_score(abs(threshold - active_threshold))
        return agree, bias_skew, dist

    scored = [(t, _score_candidate(t)) for t in candidates]
    max_agree = max(m[0] for _, m in scored)
    best_agree = [(t, m) for t, m in scored if m[0] == max_agree]
    min_bias_skew = min(m[1] for _, m in best_agree)
    best_bias = [(t, m) for t, m in best_agree if m[1] == min_bias_skew]
    min_dist = min(m[2] for _, m in best_bias)
    winners = sorted(t for t, m in best_bias if m[2] == min_dist)

    if len(winners) == 1:
        return winners[0]

    midpoint = round_score((winners[0] + winners[-1]) / 2.0)
    mid_agree, mid_skew, _ = _score_candidate(midpoint)
    if mid_agree == max_agree and mid_skew == min_bias_skew:
        return midpoint
    return winners[-1]


async def _evaluate_samples(
    judge: Metric,
    pairs: list[tuple[EvaluationCase, ExecutionResult]],
    *,
    max_concurrency: int,
) -> list[MetricResult]:
    if isinstance(judge, AsyncBatchMetric):
        return list(await judge.aevaluate_batch(pairs, max_concurrency=max_concurrency))

    aevaluate = getattr(judge, "aevaluate", None)
    if callable(aevaluate):
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_async(case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
            async with semaphore:
                try:
                    result: Any = await aevaluate(case, execution)
                    if isinstance(result, MetricResult):
                        return result
                except (LocalOnlyPolicyError, MissingExtraError):
                    raise
                except Exception as exc:
                    return MetricResult(
                        metric_id=judge.metadata.metric_id,
                        metric_version=judge.metadata.metric_version,
                        score=None,
                        status=MetricStatus.INCONCLUSIVE,
                        explanation=scrub_secret_text(
                            f"Calibration evaluation failed: {type(exc).__name__}: {exc}"
                        ),
                    )
                return MetricResult(
                    metric_id=judge.metadata.metric_id,
                    metric_version=judge.metadata.metric_version,
                    score=None,
                    status=MetricStatus.INCONCLUSIVE,
                    explanation="Calibration metric returned non-MetricResult output.",
                )

        return list(await asyncio.gather(*(_run_async(c, e) for c, e in pairs)))

    results: list[MetricResult] = []
    for case, execution in pairs:
        try:
            results.append(judge.evaluate(case, execution))
        except (LocalOnlyPolicyError, MissingExtraError):
            raise
        except Exception as exc:
            results.append(
                MetricResult(
                    metric_id=judge.metadata.metric_id,
                    metric_version=judge.metadata.metric_version,
                    score=None,
                    status=MetricStatus.INCONCLUSIVE,
                    explanation=scrub_secret_text(
                        f"Calibration evaluation failed: {type(exc).__name__}: {exc}"
                    ),
                )
            )
    return results


async def acalibrate_judge(
    judge: Metric,
    samples: Sequence[HumanCalibrationSample],
    *,
    human_threshold: float | None = None,
    score_divergence_threshold: float = 0.25,
    max_concurrency: int = 4,
) -> CalibrationReport:
    """Asynchronously calibrate a judge metric against human ground-truth samples."""
    if not samples:
        raise EmptyDatasetError("Calibration requires at least one HumanCalibrationSample")

    seen_ids: set[str] = set()
    for sample in samples:
        if sample.case_id in seen_ids:
            raise DuplicateCaseIdError(
                f"Duplicate HumanCalibrationSample case_id: {sample.case_id!r}",
                case_id=sample.case_id,
            )
        seen_ids.add(sample.case_id)

    is_invalid_concurrency = (
        isinstance(max_concurrency, bool)
        or not isinstance(max_concurrency, int)
        or max_concurrency < 1
    )
    if is_invalid_concurrency:
        raise ConfigurationError(f"max_concurrency must be >= 1, got {max_concurrency!r}")

    resolved_cfg, fingerprint = _resolve_judge_provenance(judge)
    pass_threshold = resolved_cfg.pass_threshold
    resolved_human_threshold = (
        pass_threshold
        if human_threshold is None
        else _validate_unit_float(human_threshold, name="human_threshold")
    )
    divergence_threshold = _validate_unit_float(
        score_divergence_threshold,
        name="score_divergence_threshold",
        allow_zero=False,
    )

    pairs: list[tuple[EvaluationCase, ExecutionResult]] = [
        (
            EvaluationCase(
                id=sample.case_id,
                input=sample.input,
                reference=sample.reference,
                metadata=CaseMetadata(extra=sample.metadata),
            ),
            ExecutionResult(
                case_id=sample.case_id,
                input=sample.input,
                output=sample.output,
                retrieved_chunks=list(sample.retrieved_chunks),
                elapsed_seconds=0.0,
            ),
        )
        for sample in samples
    ]

    metric_results = await _evaluate_samples(judge, pairs, max_concurrency=max_concurrency)

    valid_rows: list[tuple[float, float, bool]] = []
    disagreements: list[CalibrationDisagreement] = []
    agreed_count = 0
    too_generous_count = 0
    too_harsh_count = 0
    inconclusive_count = 0

    for sample, m_res in zip(samples, metric_results, strict=True):
        human_passed = (
            sample.human_passed
            if sample.human_passed is not None
            else (
                sample.human_score is not None
                and sample.human_score >= resolved_human_threshold - FLOAT_EPSILON
            )
        )
        human_numeric = (
            float(sample.human_score)
            if sample.human_score is not None
            else (1.0 if human_passed else 0.0)
        )

        if m_res.score is None or m_res.status in (
            MetricStatus.INCONCLUSIVE,
            MetricStatus.NOT_APPLICABLE,
        ):
            inconclusive_count += 1
            disagreements.append(
                CalibrationDisagreement(
                    case_id=sample.case_id,
                    disagreement_type=CalibrationDisagreementType.INCONCLUSIVE,
                    human_score=sample.human_score,
                    human_passed=human_passed,
                    judge_score=None,
                    judge_status=m_res.status,
                    judge_passed=None,
                    score_delta=None,
                    judge_rationale=m_res.explanation,
                    human_notes=sample.notes,
                )
            )
            continue

        judge_score = float(m_res.score)
        judge_passed = judge_score >= pass_threshold - FLOAT_EPSILON
        score_delta = round_delta(judge_score - human_numeric)
        valid_rows.append((human_numeric, judge_score, human_passed))

        disagreement_type: CalibrationDisagreementType | None = None
        if judge_passed and not human_passed:
            too_generous_count += 1
            disagreement_type = CalibrationDisagreementType.TOO_GENEROUS
        elif not judge_passed and human_passed:
            too_harsh_count += 1
            disagreement_type = CalibrationDisagreementType.TOO_HARSH
        else:
            agreed_count += 1
            if (
                sample.human_score is not None
                and abs(judge_score - sample.human_score) > divergence_threshold + FLOAT_EPSILON
            ):
                disagreement_type = CalibrationDisagreementType.SCORE_DIVERGENCE

        if disagreement_type is not None:
            disagreements.append(
                CalibrationDisagreement(
                    case_id=sample.case_id,
                    disagreement_type=disagreement_type,
                    human_score=sample.human_score,
                    human_passed=human_passed,
                    judge_score=judge_score,
                    judge_status=m_res.status,
                    judge_passed=judge_passed,
                    score_delta=score_delta,
                    judge_rationale=m_res.explanation,
                    human_notes=sample.notes,
                )
            )

    valid_count = len(valid_rows)
    total_count = len(samples)

    if valid_count == 0:
        return CalibrationReport(
            metric_id=judge.metadata.metric_id,
            metric_version=judge.metadata.metric_version,
            judge_config=resolved_cfg,
            judge_config_fingerprint=fingerprint,
            total_cases=total_count,
            valid_cases=0,
            inconclusive_cases=inconclusive_count,
            pass_threshold_evaluated=pass_threshold,
            human_threshold_evaluated=resolved_human_threshold,
            score_divergence_threshold=divergence_threshold,
            exact_agreement_rate=None,
            too_generous_rate=None,
            too_harsh_rate=None,
            mean_human_score=None,
            mean_judge_score=None,
            mean_score_delta=None,
            disagreements=disagreements,
            recommended_pass_threshold=pass_threshold,
        )

    sum_human = sum(h for h, _, _ in valid_rows)
    sum_judge = sum(j for _, j, _ in valid_rows)
    return CalibrationReport(
        metric_id=judge.metadata.metric_id,
        metric_version=judge.metadata.metric_version,
        judge_config=resolved_cfg,
        judge_config_fingerprint=fingerprint,
        total_cases=total_count,
        valid_cases=valid_count,
        inconclusive_cases=inconclusive_count,
        pass_threshold_evaluated=pass_threshold,
        human_threshold_evaluated=resolved_human_threshold,
        score_divergence_threshold=divergence_threshold,
        exact_agreement_rate=round_percentage((agreed_count / valid_count) * 100.0),
        too_generous_rate=round_score(too_generous_count / valid_count),
        too_harsh_rate=round_score(too_harsh_count / valid_count),
        mean_human_score=round_score(sum_human / valid_count),
        mean_judge_score=round_score(sum_judge / valid_count),
        mean_score_delta=round_delta((sum_judge - sum_human) / valid_count),
        disagreements=disagreements,
        recommended_pass_threshold=_optimize_pass_threshold(
            valid_rows, active_threshold=pass_threshold
        ),
    )


def calibrate_judge(
    judge: Metric,
    samples: Sequence[HumanCalibrationSample],
    *,
    human_threshold: float | None = None,
    score_divergence_threshold: float = 0.25,
    max_concurrency: int = 4,
) -> CalibrationReport:
    """Synchronously calibrate a judge metric against human ground-truth samples."""
    coro = acalibrate_judge(
        judge,
        samples,
        human_threshold=human_threshold,
        score_divergence_threshold=score_divergence_threshold,
        max_concurrency=max_concurrency,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
