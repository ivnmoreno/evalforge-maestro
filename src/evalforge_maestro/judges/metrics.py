"""Concrete evidence-aware judge metrics and convenience factories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from evalforge_maestro.exceptions import MetricError
from evalforge_maestro.judges.base import BaseJudgeMetric
from evalforge_maestro.judges.prompts import (
    ANSWER_CORRECTNESS_SPEC,
    ANSWER_RELEVANCE_SPEC,
    CONTEXT_RELEVANCE_SPEC,
    GROUNDEDNESS_SPEC,
    make_custom_rubric_spec,
)
from evalforge_maestro.judges.provider import CompletionFn
from evalforge_maestro.types import JudgeConfig


def _validate_non_empty_metric_arg(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetricError(f"{field_name} must be a non-empty string")
    return value.strip()


class GroundednessMetric(BaseJudgeMetric):
    """Judge metric measuring claim faithfulness strictly against retrieved context."""

    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            spec=GROUNDEDNESS_SPEC,
            config=config,
            api_key=api_key,
            mock_responses=mock_responses,
            completion_fn=completion_fn,
        )


class AnswerRelevanceMetric(BaseJudgeMetric):
    """Judge metric measuring whether target output directly answers user input."""

    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            spec=ANSWER_RELEVANCE_SPEC,
            config=config,
            api_key=api_key,
            mock_responses=mock_responses,
            completion_fn=completion_fn,
        )


class ContextRelevanceMetric(BaseJudgeMetric):
    """Judge metric measuring retrieval relevance relative to the input query."""

    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            spec=CONTEXT_RELEVANCE_SPEC,
            config=config,
            api_key=api_key,
            mock_responses=mock_responses,
            completion_fn=completion_fn,
        )


class AnswerCorrectnessMetric(BaseJudgeMetric):
    """Judge metric measuring semantic correctness compared to ground-truth reference."""

    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(
            spec=ANSWER_CORRECTNESS_SPEC,
            config=config,
            api_key=api_key,
            mock_responses=mock_responses,
            completion_fn=completion_fn,
        )


class CustomRubricJudgeMetric(BaseJudgeMetric):
    """Judge metric evaluating outputs against caller-provided rubric instructions."""

    def __init__(
        self,
        rubric: str,
        *,
        metric_id: str = "custom_rubric",
        metric_version: str = "1.0.0",
        what_it_measures: str = "Evaluates target outputs against a caller-defined rubric.",
        require_reference: bool = False,
        require_context: bool = False,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        cleaned_rubric = _validate_non_empty_metric_arg(
            rubric, field_name="CustomRubricJudgeMetric.rubric"
        )
        cleaned_id = _validate_non_empty_metric_arg(
            metric_id, field_name="CustomRubricJudgeMetric.metric_id"
        )
        cleaned_version = _validate_non_empty_metric_arg(
            metric_version, field_name="CustomRubricJudgeMetric.metric_version"
        )
        cleaned_desc = _validate_non_empty_metric_arg(
            what_it_measures, field_name="CustomRubricJudgeMetric.what_it_measures"
        )
        spec = make_custom_rubric_spec(
            metric_id=cleaned_id,
            metric_version=cleaned_version,
            what_it_measures=cleaned_desc,
            rubric=cleaned_rubric,
            require_reference=require_reference,
            require_context=require_context,
        )
        super().__init__(
            spec=spec,
            config=config,
            rubric_override=cleaned_rubric,
            api_key=api_key,
            mock_responses=mock_responses,
            completion_fn=completion_fn,
        )


def groundedness(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> GroundednessMetric:
    """Create a GroundednessMetric instance."""
    return GroundednessMetric(
        config=config,
        api_key=api_key,
        mock_responses=mock_responses,
        completion_fn=completion_fn,
    )


def answer_relevance(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> AnswerRelevanceMetric:
    """Create an AnswerRelevanceMetric instance."""
    return AnswerRelevanceMetric(
        config=config,
        api_key=api_key,
        mock_responses=mock_responses,
        completion_fn=completion_fn,
    )


def context_relevance(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> ContextRelevanceMetric:
    """Create a ContextRelevanceMetric instance."""
    return ContextRelevanceMetric(
        config=config,
        api_key=api_key,
        mock_responses=mock_responses,
        completion_fn=completion_fn,
    )


def answer_correctness(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> AnswerCorrectnessMetric:
    """Create an AnswerCorrectnessMetric instance."""
    return AnswerCorrectnessMetric(
        config=config,
        api_key=api_key,
        mock_responses=mock_responses,
        completion_fn=completion_fn,
    )


def custom_rubric_judge(
    rubric: str,
    *,
    metric_id: str = "custom_rubric",
    metric_version: str = "1.0.0",
    what_it_measures: str = "Evaluates target outputs against a caller-defined rubric.",
    require_reference: bool = False,
    require_context: bool = False,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> CustomRubricJudgeMetric:
    """Create a CustomRubricJudgeMetric instance."""
    return CustomRubricJudgeMetric(
        rubric,
        metric_id=metric_id,
        metric_version=metric_version,
        what_it_measures=what_it_measures,
        require_reference=require_reference,
        require_context=require_context,
        config=config,
        api_key=api_key,
        mock_responses=mock_responses,
        completion_fn=completion_fn,
    )
