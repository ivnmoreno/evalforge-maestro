"""Target adapter resolution, metric suite construction, and pre-network egress checks."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from evalforge_maestro._locality import is_remote_endpoint, validate_local_only_endpoint
from evalforge_maestro.adapters import (
    AgentAdapter,
    CallableAdapter,
    DocpipeAdapter,
    RAGAdapter,
    ReplayAdapter,
)
from evalforge_maestro.cli.logging_utils import CLIStructuredLogger
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
    AgentExtractorConfig,
    CLIResolvedConfig,
    EmbeddingAggregation,
    EmbeddingConfig,
    JudgeConfig,
    Metric,
    MetricSpecConfig,
    RAGExtractorConfig,
    TargetAdapter,
    TargetType,
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


def _load_python_symbol(entrypoint: str) -> Any:
    if ":" not in entrypoint:
        raise ConfigurationError(
            f"Invalid target entrypoint {entrypoint!r}: expected 'module.path:attribute'"
        )
    module_name, attr_path = entrypoint.split(":", 1)
    module_name = module_name.strip()
    attr_path = attr_path.strip()
    if not module_name or not attr_path:
        raise ConfigurationError(
            f"Invalid target entrypoint {entrypoint!r}: expected non-empty module and attribute"
        )
    cwd_str = str(Path.cwd())
    if cwd_str not in sys.path:
        sys.path.insert(0, cwd_str)
    try:
        current: Any = importlib.import_module(module_name)
    except Exception as exc:
        raise ConfigurationError(f"Failed importing target module {module_name!r}: {exc}") from exc

    for part in attr_path.split("."):
        if not hasattr(current, part):
            raise ConfigurationError(
                f"Target module {module_name!r} has no attribute {attr_path!r}"
            )
        current = getattr(current, part)
    return current


def _normalized_threshold_params(params: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    if "pass_threshold" in normalized and "threshold" not in normalized:
        normalized["threshold"] = normalized.pop("pass_threshold")
    return normalized


def _build_judge_config(
    spec: MetricSpecConfig,
    resolved: CLIResolvedConfig,
) -> JudgeConfig:
    pass_threshold = spec.params.get(
        "pass_threshold",
        spec.params.get("threshold", resolved.judge.pass_threshold),
    )
    temperature = spec.params.get("temperature", resolved.judge.temperature)
    prompt_version = spec.params.get("prompt_version", resolved.judge.prompt_version)
    return JudgeConfig(
        model=str(spec.params.get("model", resolved.judge.model)),
        api_base=spec.params.get("api_base", resolved.judge.api_base),
        temperature=temperature,
        pass_threshold=pass_threshold,
        max_retries=resolved.judge.max_retries,
        retry_backoff_seconds=resolved.judge.retry_backoff_seconds,
        timeout_seconds=resolved.judge.timeout_seconds,
        local_only=resolved.security.local_only or resolved.judge.local_only,
        mock_mode=resolved.judge.mock_mode,
        seed=resolved.judge.seed,
        prompt_version=str(prompt_version),
    )


def _build_embedding_config(
    spec: MetricSpecConfig,
    resolved: CLIResolvedConfig,
) -> EmbeddingConfig:
    emb = resolved.embedding
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
        spec.params.get("threshold", emb.pass_threshold),
    )
    raw_agg = spec.params.get("aggregation", emb.aggregation)
    aggregation = (
        raw_agg
        if isinstance(raw_agg, EmbeddingAggregation)
        else EmbeddingAggregation(str(raw_agg).strip().lower())
    )
    default_max_chars = (
        emb.max_input_chars
        if emb.max_input_chars is not None
        else resolved.execution.max_context_chars
    )
    max_input_chars = spec.params.get("max_input_chars", default_max_chars)
    return EmbeddingConfig(
        model=str(spec.params.get("model", emb.model)),
        api_base=spec.params.get("api_base", emb.api_base),
        pass_threshold=pass_threshold,
        aggregation=aggregation,
        max_retries=emb.max_retries,
        retry_backoff_seconds=emb.retry_backoff_seconds,
        timeout_seconds=emb.timeout_seconds,
        max_input_chars=max_input_chars,
        local_only=resolved.security.local_only or emb.local_only,
        mock_mode=emb.mock_mode,
    )


def _construct_single_metric(
    spec: MetricSpecConfig,
    resolved: CLIResolvedConfig,
    *,
    raw_api_key: str | None,
    raw_embedding_api_key: str | None = None,
) -> Any:
    mid = spec.metric_id
    params = _normalized_threshold_params(spec.params)

    try:
        direct_factory = _DIRECT_DETERMINISTIC_FACTORIES.get(mid)
        if direct_factory is not None:
            return direct_factory(**params)
        topk_factory = _TOPK_RETRIEVAL_FACTORIES.get(mid)
        if topk_factory is not None:
            k_val = params.pop("k", 5)
            return topk_factory(k_val, **params)
        if mid in _EMBEDDING_METRIC_IDS:
            emb_cfg = _build_embedding_config(spec, resolved)
            if mid == "embedding_similarity":
                emb_metric: Any = EmbeddingSimilarityMetric(
                    config=emb_cfg,
                    api_key=raw_embedding_api_key,
                )
            else:
                emb_metric = ContextEmbeddingSimilarityMetric(
                    config=emb_cfg,
                    api_key=raw_embedding_api_key,
                )
            return wrap_pii_guarded_embedding_metric(
                emb_metric,
                block_pii=resolved.security.block_pii,
            )
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
            cfg = _build_judge_config(spec, resolved)
            factory = _SIMPLE_JUDGE_FACTORIES[mid]
            metric = factory(config=cfg, api_key=raw_api_key)
            return wrap_pii_guarded_metric(metric, block_pii=resolved.security.block_pii)
        if mid == "custom_rubric":
            rubric = spec.params.get("rubric")
            if not isinstance(rubric, str) or not rubric.strip():
                raise ConfigurationError(
                    "Metric 'custom_rubric' requires a non-empty 'rubric' parameter"
                )
            cfg = _build_judge_config(spec, resolved)
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
            return wrap_pii_guarded_metric(metric, block_pii=resolved.security.block_pii)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Invalid configuration parameters for metric {mid!r}: {exc}"
        ) from exc

    raise ConfigurationError(f"Unknown metric identifier: {mid!r}")


def build_metrics_from_config(
    resolved: CLIResolvedConfig,
    *,
    raw_api_key: str | None,
    raw_embedding_api_key: str | None = None,
) -> list[Metric]:
    """Instantiate configured metrics for `run`, rejecting empty or unknown definitions."""
    if not resolved.metrics:
        raise ConfigurationError(
            "No metrics configured. Specify --metric, EVALFORGE_METRICS, or [metrics] in config."
        )
    built: list[Metric] = []
    for spec in resolved.metrics:
        built.append(
            _construct_single_metric(
                spec,
                resolved,
                raw_api_key=raw_api_key,
                raw_embedding_api_key=raw_embedding_api_key,
            )
        )
    return built


def build_calibration_judge(
    spec: MetricSpecConfig,
    resolved: CLIResolvedConfig,
    *,
    raw_api_key: str | None,
) -> BaseJudgeMetric:
    """Build one BaseJudgeMetric instance for judge calibration workflows."""
    if spec.metric_id not in _SIMPLE_JUDGE_FACTORIES and spec.metric_id != "custom_rubric":
        raise ConfigurationError(
            f"Metric {spec.metric_id!r} does not support judge calibration "
            f"(choose one of: {sorted((*_SIMPLE_JUDGE_FACTORIES, 'custom_rubric'))})"
        )
    metric = _construct_single_metric(spec, resolved, raw_api_key=raw_api_key)
    return metric  # type: ignore[no-any-return]


def _validate_replay_alignment(
    dataset: DatasetEngine,
    adapter: ReplayAdapter,
    *,
    max_dataset_cases: int | None,
    logger: CLIStructuredLogger,
) -> None:
    selected_ids: set[str] = set()
    missing_ids: list[str] = []
    for case in dataset.iter_cases(max_cases=max_dataset_cases):
        selected_ids.add(case.id)
        if case.id not in adapter.case_ids:
            missing_ids.append(case.id)

    if missing_ids:
        preview = ", ".join(missing_ids[:10])
        suffix = f" (+{len(missing_ids) - 10} more)" if len(missing_ids) > 10 else ""
        raise ConfigurationError(
            f"Execution replay file is missing records for selected dataset case ID(s): "
            f"{preview}{suffix}"
        )

    unused = sorted(adapter.case_ids - selected_ids)
    if unused:
        logger.warning(
            f"Execution replay contains {len(unused)} unused trace record(s) absent from "
            "the active dataset selection."
        )


def build_target_adapter(
    resolved: CLIResolvedConfig,
    *,
    dataset: DatasetEngine,
    logger: CLIStructuredLogger,
) -> TargetAdapter:
    """Resolve live adapter (callable, rag, docpipe) or validated offline ReplayAdapter."""
    t_cfg = resolved.target
    has_executions = resolved.executions_path is not None
    has_live_entrypoint = t_cfg.entrypoint is not None
    explicit_type = t_cfg.target_type

    if has_executions and (
        has_live_entrypoint or (explicit_type is not None and explicit_type != TargetType.REPLAY)
    ):
        raise ConfigurationError(
            "Conflicting target options: --executions replay cannot be combined with a live target"
        )

    effective_type = explicit_type
    if effective_type is None:
        if has_executions:
            effective_type = TargetType.REPLAY
        elif has_live_entrypoint:
            effective_type = TargetType.CALLABLE
        else:
            raise ConfigurationError(
                "No target configured. Pass --executions <path> or --target <module:symbol> "
                "(or configure [target] in evalforge.toml)."
            )

    if effective_type == TargetType.REPLAY:
        if not resolved.executions_path:
            raise ConfigurationError("Replay target mode requires --executions <path>")
        adapter = ReplayAdapter.from_file(
            resolved.executions_path,
            system_version=t_cfg.system_version,
            model_id=t_cfg.model_id,
        )
        _validate_replay_alignment(
            dataset,
            adapter,
            max_dataset_cases=resolved.execution.max_dataset_cases,
            logger=logger,
        )
        return adapter

    if effective_type == TargetType.DOCPIPE:
        if has_executions:
            raise ConfigurationError("Docpipe target cannot be combined with --executions")
        retrieve_kwargs: dict[str, Any] = {}
        if t_cfg.docpipe_top_k is not None:
            retrieve_kwargs["top_k"] = t_cfg.docpipe_top_k
        if t_cfg.docpipe_embed_model is not None:
            retrieve_kwargs["embed_model"] = t_cfg.docpipe_embed_model
        if t_cfg.docpipe_searcher is not None:
            retrieve_kwargs["searcher"] = t_cfg.docpipe_searcher
        if t_cfg.docpipe_rerank:
            retrieve_kwargs["rerank"] = True
        if resolved.security.local_only:
            retrieve_kwargs["local_only"] = True

        answer_kwargs: dict[str, Any] = {}
        if t_cfg.docpipe_mode == "answer_detailed":
            if t_cfg.docpipe_answer_model is not None:
                answer_kwargs["model"] = t_cfg.docpipe_answer_model
            if t_cfg.docpipe_api_base is not None:
                answer_kwargs["api_base"] = t_cfg.docpipe_api_base
            if resolved.security.local_only:
                answer_kwargs["local_only"] = True

        return DocpipeAdapter(
            mode=t_cfg.docpipe_mode,
            collection=t_cfg.docpipe_collection,
            persist_dir=t_cfg.docpipe_persist_dir,
            retrieve_kwargs=retrieve_kwargs or None,
            answer_kwargs=answer_kwargs or None,
            system_version=t_cfg.system_version,
            model_id=t_cfg.model_id,
        )

    if not t_cfg.entrypoint:
        raise ConfigurationError(
            f"Target type {effective_type.value!r} requires --target <module:symbol>"
        )
    target_fn = _load_python_symbol(t_cfg.entrypoint)
    pass_case = t_cfg.arg_mode == "case"

    if effective_type == TargetType.CALLABLE:
        return CallableAdapter(
            target_fn,
            system_version=t_cfg.system_version,
            model_id=t_cfg.model_id,
            pass_case=pass_case,
        )

    if effective_type == TargetType.AGENT:
        try:
            agent_ext = (
                AgentExtractorConfig(**t_cfg.agent_extractors) if t_cfg.agent_extractors else None
            )
        except Exception as exc:
            raise ConfigurationError(f"Invalid [target.agent_extractors] setting: {exc}") from exc
        return AgentAdapter(
            target_fn,
            extractors=agent_ext,
            system_version=t_cfg.system_version,
            model_id=t_cfg.model_id,
            pass_case=pass_case,
        )

    extractors = RAGExtractorConfig(**t_cfg.rag_extractors) if t_cfg.rag_extractors else None
    return RAGAdapter(
        target_fn,
        extractors=extractors,
        system_version=t_cfg.system_version,
        model_id=t_cfg.model_id,
        pass_case=pass_case,
    )


def _docpipe_judge_probe(
    model: str | None,
    *,
    api_base: str | None = None,
    local_only: bool = False,
) -> JudgeConfig | None:
    if model is None and api_base is None:
        return None
    if model is not None and model.strip().lower().startswith("local/"):
        if api_base is None:
            return None
        probe_model = "ollama/local"
    else:
        probe_model = model or "ollama/llama3.2"
    return JudgeConfig(
        model=probe_model,
        api_base=api_base,
        local_only=local_only,
        mock_mode=False,
    )


def _docpipe_endpoint_is_remote(model: str | None, *, api_base: str | None = None) -> bool:
    probe = _docpipe_judge_probe(model, api_base=api_base, local_only=False)
    return False if probe is None else is_remote_judge_endpoint(probe)


def _validate_docpipe_locality(model: str | None, *, api_base: str | None = None) -> None:
    probe = _docpipe_judge_probe(model, api_base=api_base, local_only=True)
    if probe is not None:
        validate_local_only_target(probe)


def preflight_run_security(
    *,
    resolved: CLIResolvedConfig,
    dataset: DatasetEngine,
    metrics: Sequence[Metric],
) -> None:
    """Enforce --local-only endpoint locality and opt-in --block-pii pre-network checks."""
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

    t_cfg = resolved.target
    if resolved.security.local_only and t_cfg.target_type == TargetType.DOCPIPE:
        _validate_docpipe_locality(t_cfg.docpipe_embed_model)
        if t_cfg.docpipe_mode == "answer_detailed":
            _validate_docpipe_locality(t_cfg.docpipe_answer_model, api_base=t_cfg.docpipe_api_base)
        elif t_cfg.docpipe_api_base is not None:
            _validate_docpipe_locality(None, api_base=t_cfg.docpipe_api_base)

    if resolved.security.block_pii:
        is_remote_docpipe = False
        if (
            not resolved.judge.mock_mode
            and not resolved.security.local_only
            and t_cfg.target_type == TargetType.DOCPIPE
        ):
            is_remote_docpipe = _docpipe_endpoint_is_remote(t_cfg.docpipe_embed_model) or (
                t_cfg.docpipe_mode == "answer_detailed"
                and (
                    t_cfg.docpipe_answer_model is None
                    or _docpipe_endpoint_is_remote(
                        t_cfg.docpipe_answer_model,
                        api_base=t_cfg.docpipe_api_base,
                    )
                )
            )
        if (
            (any_remote_judge and not resolved.judge.mock_mode)
            or is_remote_docpipe
            or (any_remote_embedding and not resolved.embedding.mock_mode)
        ):
            for case in dataset.iter_cases(max_cases=resolved.execution.max_dataset_cases):
                validate_pii_egress(
                    {
                        "input": case.input,
                        "reference": case.reference,
                        "expected_context": case.expected_context,
                    },
                    enabled=True,
                    context_label=f"dataset case {case.id!r}",
                )
