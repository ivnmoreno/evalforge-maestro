"""Shared library-pure metric instantiation and security preflight helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from evalforge_maestro._locality import is_remote_endpoint, validate_local_only_endpoint
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.embeddings import (
    ContextEmbeddingSimilarityMetric,
    EmbeddingSimilarityMetric,
)
from evalforge_maestro.embeddings.provider import wrap_pii_guarded_embedding_metric
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.judges.base import BaseJudgeMetric
from evalforge_maestro.judges.metrics import (
    AnswerCorrectnessMetric,
    AnswerRelevanceMetric,
    ContextRelevanceMetric,
    CustomRubricJudgeMetric,
    GroundednessMetric,
)
from evalforge_maestro.judges.security import (
    is_remote_judge_endpoint,
    validate_local_only_target,
    validate_pii_egress,
    wrap_pii_guarded_metric,
)
from evalforge_maestro.metrics import (
    ArgumentCorrectnessMetric,
    ExactMatchMetric,
    ExecutionSequenceMetric,
    FailureRecoveryMetric,
    HitRateAtKMetric,
    JsonSchemaValidationMetric,
    MRRMetric,
    NDCGAtKMetric,
    NormalizedMatchMetric,
    PolicyComplianceMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
)
from evalforge_maestro.types import (
    EmbeddingAggregation,
    EmbeddingConfig,
    JudgeConfig,
    Metric,
    MetricSpecConfig,
    ResolvedEmbeddingSettings,
    ResolvedJudgeSettings,
)

_EMBEDDING_METRIC_IDS = frozenset({"embedding_similarity", "context_embedding_similarity"})

_SIMPLE_JUDGE_FACTORIES: dict[str, Callable[..., BaseJudgeMetric]] = {
    "groundedness": GroundednessMetric,
    "answer_relevance": AnswerRelevanceMetric,
    "context_relevance": ContextRelevanceMetric,
    "answer_correctness": AnswerCorrectnessMetric,
}
_DIRECT_DETERMINISTIC_FACTORIES: dict[str, Callable[..., Metric]] = {
    "exact_match": ExactMatchMetric,
    "normalized_match": NormalizedMatchMetric,
    "json_schema_validation": JsonSchemaValidationMetric,
    "mrr": MRRMetric,
    "tool_selection": ToolSelectionMetric,
    "argument_correctness": ArgumentCorrectnessMetric,
    "execution_sequence": ExecutionSequenceMetric,
    "tool_efficiency": ToolEfficiencyMetric,
    "policy_compliance": PolicyComplianceMetric,
    "failure_recovery": FailureRecoveryMetric,
}
_TOPK_RETRIEVAL_FACTORIES: dict[str, Callable[..., Metric]] = {
    "precision_at_k": PrecisionAtKMetric,
    "recall_at_k": RecallAtKMetric,
    "ndcg_at_k": NDCGAtKMetric,
    "hit_rate_at_k": HitRateAtKMetric,
}

SIMPLE_JUDGE_METRIC_IDS: frozenset[str] = frozenset(_SIMPLE_JUDGE_FACTORIES)


def _normalized_threshold_params(params: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    if "pass_threshold" in normalized and "threshold" not in normalized:
        normalized["threshold"] = normalized.pop("pass_threshold")
    return normalized


def _build_judge_config(
    spec: MetricSpecConfig,
    base: ResolvedJudgeSettings | JudgeConfig,
    *,
    local_only: bool,
) -> JudgeConfig:
    pass_threshold = spec.params.get(
        "pass_threshold",
        spec.params.get("threshold", base.pass_threshold),
    )
    temperature = spec.params.get("temperature", base.temperature)
    prompt_version = spec.params.get("prompt_version", base.prompt_version)
    return JudgeConfig(
        model=str(spec.params.get("model", base.model)),
        api_base=spec.params.get("api_base", base.api_base),
        temperature=temperature,
        pass_threshold=pass_threshold,
        max_retries=base.max_retries,
        retry_backoff_seconds=base.retry_backoff_seconds,
        timeout_seconds=base.timeout_seconds,
        local_only=local_only or base.local_only,
        mock_mode=base.mock_mode,
        seed=base.seed,
        prompt_version=str(prompt_version),
    )


def _build_embedding_config(
    spec: MetricSpecConfig,
    base: ResolvedEmbeddingSettings | EmbeddingConfig,
    *,
    local_only: bool,
    default_max_context_chars: int | None,
) -> EmbeddingConfig:
    allowed_keys = {
        "model",
        "api_base",
        "pass_threshold",
        "threshold",
        "max_input_chars",
    }
    if spec.metric_id == "context_embedding_similarity":
        allowed_keys.add("aggregation")
    unknown = set(spec.params) - allowed_keys
    if unknown:
        raise ConfigurationError(
            f"Unsupported parameter(s) for embedding metric {spec.metric_id!r}: {sorted(unknown)}"
        )
    pass_threshold = spec.params.get(
        "pass_threshold",
        spec.params.get("threshold", base.pass_threshold),
    )
    raw_agg = spec.params.get("aggregation", base.aggregation)
    aggregation = (
        raw_agg
        if isinstance(raw_agg, EmbeddingAggregation)
        else EmbeddingAggregation(str(raw_agg).strip().lower())
    )
    default_max_chars = (
        base.max_input_chars if base.max_input_chars is not None else default_max_context_chars
    )
    max_input_chars = spec.params.get("max_input_chars", default_max_chars)
    return EmbeddingConfig(
        model=str(spec.params.get("model", base.model)),
        api_base=spec.params.get("api_base", base.api_base),
        pass_threshold=pass_threshold,
        aggregation=aggregation,
        max_retries=base.max_retries,
        retry_backoff_seconds=base.retry_backoff_seconds,
        timeout_seconds=base.timeout_seconds,
        max_input_chars=max_input_chars,
        local_only=local_only or base.local_only,
        mock_mode=base.mock_mode,
    )


def construct_single_metric(
    spec: MetricSpecConfig,
    *,
    judge_settings: ResolvedJudgeSettings | JudgeConfig | None = None,
    embedding_settings: ResolvedEmbeddingSettings | EmbeddingConfig | None = None,
    local_only: bool = True,
    block_pii: bool = False,
    default_max_context_chars: int | None = None,
    raw_api_key: str | None = None,
    raw_embedding_api_key: str | None = None,
) -> Metric:
    """Instantiate one Metric contract from a typed MetricSpecConfig."""
    mid = spec.metric_id
    params = _normalized_threshold_params(spec.params)
    j_base = judge_settings or JudgeConfig(local_only=local_only, mock_mode=True)
    e_base = embedding_settings or EmbeddingConfig(local_only=local_only, mock_mode=True)

    try:
        direct_factory = _DIRECT_DETERMINISTIC_FACTORIES.get(mid)
        if direct_factory is not None:
            return direct_factory(**params)
        topk_factory = _TOPK_RETRIEVAL_FACTORIES.get(mid)
        if topk_factory is not None:
            k_val = params.pop("k", 5)
            return topk_factory(k_val, **params)
        if mid in _EMBEDDING_METRIC_IDS:
            emb_cfg = _build_embedding_config(
                spec,
                e_base,
                local_only=local_only,
                default_max_context_chars=default_max_context_chars,
            )
            emb_metric: Any = (
                EmbeddingSimilarityMetric(config=emb_cfg, api_key=raw_embedding_api_key)
                if mid == "embedding_similarity"
                else ContextEmbeddingSimilarityMetric(config=emb_cfg, api_key=raw_embedding_api_key)
            )
            return cast(Metric, wrap_pii_guarded_embedding_metric(emb_metric, block_pii=block_pii))
        if mid in _SIMPLE_JUDGE_FACTORIES:
            allowed_judge_keys = {
                "model",
                "api_base",
                "temperature",
                "pass_threshold",
                "threshold",
                "prompt_version",
            }
            unknown = set(spec.params) - allowed_judge_keys
            if unknown:
                raise ConfigurationError(
                    f"Unsupported parameter(s) for judge metric {mid!r}: {sorted(unknown)}"
                )
            cfg = _build_judge_config(spec, j_base, local_only=local_only)
            metric = _SIMPLE_JUDGE_FACTORIES[mid](config=cfg, api_key=raw_api_key)
            return cast(Metric, wrap_pii_guarded_metric(metric, block_pii=block_pii))
        if mid == "custom_rubric":
            rubric = spec.params.get("rubric")
            if not isinstance(rubric, str) or not rubric.strip():
                raise ConfigurationError(
                    "Metric 'custom_rubric' requires a non-empty 'rubric' parameter"
                )
            cfg = _build_judge_config(spec, j_base, local_only=local_only)
            metric = CustomRubricJudgeMetric(
                rubric,
                metric_id=str(spec.params.get("metric_id", "custom_rubric")),
                metric_version=str(spec.params.get("metric_version", "1.0.0")),
                what_it_measures=str(
                    spec.params.get(
                        "what_it_measures",
                        "Evaluates target outputs against a caller-defined rubric.",
                    )
                ),
                require_reference=bool(spec.params.get("require_reference", False)),
                require_context=bool(spec.params.get("require_context", False)),
                config=cfg,
                api_key=raw_api_key,
            )
            return cast(Metric, wrap_pii_guarded_metric(metric, block_pii=block_pii))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Invalid configuration parameters for metric {mid!r}: {exc}"
        ) from exc

    raise ConfigurationError(f"Unknown metric identifier: {mid!r}")


def build_metrics_from_specs(
    specs: Sequence[MetricSpecConfig],
    *,
    judge_settings: ResolvedJudgeSettings | JudgeConfig | None = None,
    embedding_settings: ResolvedEmbeddingSettings | EmbeddingConfig | None = None,
    local_only: bool = True,
    block_pii: bool = False,
    default_max_context_chars: int | None = None,
    raw_api_key: str | None = None,
    raw_embedding_api_key: str | None = None,
) -> list[Metric]:
    """Instantiate a non-empty metric list from typed MetricSpecConfig specs."""
    if not specs:
        raise ConfigurationError(
            "No metrics configured. Specify --metric, EVALFORGE_METRICS, or [metrics] in config."
        )
    return [
        construct_single_metric(
            spec,
            judge_settings=judge_settings,
            embedding_settings=embedding_settings,
            local_only=local_only,
            block_pii=block_pii,
            default_max_context_chars=default_max_context_chars,
            raw_api_key=raw_api_key,
            raw_embedding_api_key=raw_embedding_api_key,
        )
        for spec in specs
    ]


def check_metrics_locality_and_remote_flags(metrics: Sequence[Metric]) -> tuple[bool, bool]:
    """Enforce judge/embedding locality rules and report remote endpoint flags."""
    any_remote_judge = False
    any_remote_embedding = False
    for metric in metrics:
        judge_cfg = getattr(metric, "judge_config", None)
        if isinstance(judge_cfg, JudgeConfig):
            validate_local_only_target(judge_cfg)
            if is_remote_judge_endpoint(judge_cfg):
                any_remote_judge = True
        emb_cfg = getattr(metric, "embedding_config", None)
        if isinstance(emb_cfg, EmbeddingConfig):
            validate_local_only_endpoint(
                local_only=emb_cfg.local_only,
                mock_mode=emb_cfg.mock_mode,
                model=emb_cfg.model,
                api_base=emb_cfg.api_base,
                label="embedding",
            )
            if is_remote_endpoint(
                model=emb_cfg.model,
                api_base=emb_cfg.api_base,
                mock_mode=emb_cfg.mock_mode,
            ):
                any_remote_embedding = True
    return any_remote_judge, any_remote_embedding


def validate_dataset_pii_egress(
    dataset: DatasetEngine,
    *,
    max_cases: int | None = None,
) -> None:
    """Scan streaming dataset cases for PII prior to any remote network call."""
    for case in dataset.iter_cases(max_cases=max_cases):
        validate_pii_egress(
            {
                "input": case.input,
                "reference": case.reference,
                "expected_context": case.expected_context,
            },
            enabled=True,
            context_label=f"dataset case {case.id!r}",
        )
