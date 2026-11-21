"""Target adapter resolution, metric suite construction, and pre-network egress checks."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evalforge_maestro._metric_factory import (
    SIMPLE_JUDGE_METRIC_IDS,
    build_metrics_from_specs,
    check_metrics_locality_and_remote_flags,
    construct_single_metric,
    validate_dataset_pii_egress,
)
from evalforge_maestro.adapters import (
    AgentAdapter,
    CallableAdapter,
    DocpipeAdapter,
    RAGAdapter,
    ReplayAdapter,
)
from evalforge_maestro.cli.logging_utils import CLIStructuredLogger
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.judges.base import BaseJudgeMetric
from evalforge_maestro.judges.security import (
    is_remote_judge_endpoint,
    validate_local_only_target,
)
from evalforge_maestro.types import (
    AgentExtractorConfig,
    CLIResolvedConfig,
    JudgeConfig,
    Metric,
    MetricSpecConfig,
    RAGExtractorConfig,
    TargetAdapter,
    TargetType,
)


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


def build_metrics_from_config(
    resolved: CLIResolvedConfig,
    *,
    raw_api_key: str | None,
    raw_embedding_api_key: str | None = None,
) -> list[Metric]:
    """Instantiate configured metrics for `run`, rejecting empty or unknown definitions."""
    return build_metrics_from_specs(
        resolved.metrics,
        judge_settings=resolved.judge,
        embedding_settings=resolved.embedding,
        local_only=resolved.security.local_only,
        block_pii=resolved.security.block_pii,
        default_max_context_chars=resolved.execution.max_context_chars,
        raw_api_key=raw_api_key,
        raw_embedding_api_key=raw_embedding_api_key,
    )


def build_calibration_judge(
    spec: MetricSpecConfig,
    resolved: CLIResolvedConfig,
    *,
    raw_api_key: str | None,
) -> BaseJudgeMetric:
    """Build one BaseJudgeMetric instance for judge calibration workflows."""
    if spec.metric_id not in SIMPLE_JUDGE_METRIC_IDS and spec.metric_id != "custom_rubric":
        raise ConfigurationError(
            f"Metric {spec.metric_id!r} does not support judge calibration "
            f"(choose one of: {sorted((*SIMPLE_JUDGE_METRIC_IDS, 'custom_rubric'))})"
        )
    metric = construct_single_metric(
        spec,
        judge_settings=resolved.judge,
        embedding_settings=resolved.embedding,
        local_only=resolved.security.local_only,
        block_pii=resolved.security.block_pii,
        default_max_context_chars=resolved.execution.max_context_chars,
        raw_api_key=raw_api_key,
    )
    return metric  # type: ignore[return-value]


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
    has_otel = resolved.otel_traces is not None
    has_live_entrypoint = t_cfg.entrypoint is not None
    explicit_type = t_cfg.target_type

    if has_executions and has_otel:
        raise ConfigurationError(
            "Conflicting target options: --otel-traces cannot be combined with --executions"
        )

    if (has_executions or has_otel) and (
        has_live_entrypoint or (explicit_type is not None and explicit_type != TargetType.REPLAY)
    ):
        raise ConfigurationError(
            "Conflicting target options: offline replay (--executions / --otel-traces) "
            "cannot be combined with a live target"
        )

    effective_type = explicit_type
    if effective_type is None:
        if has_executions or has_otel:
            effective_type = TargetType.REPLAY
        elif has_live_entrypoint:
            effective_type = TargetType.CALLABLE
        else:
            raise ConfigurationError(
                "No target configured. Pass --executions <path>, --otel-traces <path>, "
                "or --target <module:symbol> (or configure [target] in evalforge.toml)."
            )

    if effective_type == TargetType.REPLAY:
        if has_otel:
            adapter = ReplayAdapter.from_otel_file(
                resolved.otel_traces or "",
                extractors=resolved.otel,
                dataset=dataset,
                system_version=t_cfg.system_version,
                model_id=t_cfg.model_id,
            )
        elif resolved.executions_path:
            adapter = ReplayAdapter.from_file(
                resolved.executions_path,
                system_version=t_cfg.system_version,
                model_id=t_cfg.model_id,
            )
        else:
            raise ConfigurationError(
                "Replay target mode requires --executions <path> or --otel-traces <path>"
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
    any_remote_judge, any_remote_embedding = check_metrics_locality_and_remote_flags(metrics)

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
            validate_dataset_pii_egress(dataset, max_cases=resolved.execution.max_dataset_cases)
