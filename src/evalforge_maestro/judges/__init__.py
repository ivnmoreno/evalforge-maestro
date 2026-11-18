"""Model-based LLM judge metrics, security isolation, offline mocks, and human calibration."""

from __future__ import annotations

import logging

from evalforge_maestro.judges.base import BaseJudgeMetric
from evalforge_maestro.judges.calibration import acalibrate_judge, calibrate_judge
from evalforge_maestro.judges.metrics import (
    AnswerCorrectnessMetric,
    AnswerRelevanceMetric,
    ContextRelevanceMetric,
    CustomRubricJudgeMetric,
    GroundednessMetric,
    answer_correctness,
    answer_relevance,
    context_relevance,
    custom_rubric_judge,
    groundedness,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AnswerCorrectnessMetric",
    "AnswerRelevanceMetric",
    "BaseJudgeMetric",
    "ContextRelevanceMetric",
    "CustomRubricJudgeMetric",
    "GroundednessMetric",
    "acalibrate_judge",
    "answer_correctness",
    "answer_relevance",
    "calibrate_judge",
    "context_relevance",
    "custom_rubric_judge",
    "groundedness",
]
