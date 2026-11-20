"""Bounded-concurrency, fault-isolated evaluation orchestrator."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from evalforge_maestro._canonical import canonical_json_str, canonical_sha256, round_score
from evalforge_maestro.datasets import DatasetEngine, DatasetStreamResult
from evalforge_maestro.exceptions import ExecutionError, ImmutabilityError, MemoryLimitExceededError
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    AgentTraceStep,
    AggregateMetricSummary,
    AsyncBatchMetric,
    CaseEvaluationRecord,
    EvaluationCase,
    ExecutionResult,
    Metric,
    MetricResult,
    MetricStatus,
    OrchestratorConfig,
    RetrievedChunk,
    RunRecord,
    TargetAdapter,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)


def _package_version() -> str:
    try:
        return version("evalforge-maestro")
    except PackageNotFoundError:  # pragma: no cover - uninstalled source fallback
        return "0.1.0.dev0"


def _get_resident_memory_mb() -> float | None:
    """Return current process peak RSS in MiB on POSIX, or None if unsupported."""
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows lacks stdlib resource
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":  # pragma: no cover - macOS reports bytes
        return usage / (1024.0 * 1024.0)
    return usage / 1024.0


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _truncate_json_value(value: Any, max_chars: int) -> tuple[Any, bool]:
    if value is None or isinstance(value, (bool, int, float)):
        return value, False
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    if isinstance(value, dict):
        return _truncate_mapping(value, max_chars)
    if isinstance(value, list):
        trimmed_list: list[Any] = []
        changed = False
        for item in value:
            t_item, did_item = _truncate_json_value(item, max_chars)
            trimmed_list.append(t_item)
            changed = changed or did_item
        serialized = canonical_json_str(trimmed_list)
        if len(serialized) > max_chars:
            return serialized[:max_chars], True
        return trimmed_list, changed
    serialized = canonical_json_str(value)
    if len(serialized) > max_chars:
        return serialized[:max_chars], True
    return value, False


def _truncate_mapping(mapping: dict[str, Any], max_chars: int) -> tuple[dict[str, Any], bool]:
    if not mapping:
        return mapping, False
    trimmed: dict[str, Any] = {}
    changed = False
    for key, val in mapping.items():
        t_val, did_val = _truncate_json_value(val, max_chars)
        trimmed[key] = t_val
        changed = changed or did_val
    return trimmed, changed


def _truncate_tool_call_record(call: ToolCallRecord, max_chars: int) -> tuple[ToolCallRecord, bool]:
    updates: dict[str, Any] = {}
    changed = False

    new_args, args_changed = _truncate_mapping(call.arguments, max_chars)
    if args_changed:
        updates["arguments"] = new_args
        changed = True

    if call.raw_arguments is not None:
        new_raw, raw_changed = _truncate_text(call.raw_arguments, max_chars)
        if raw_changed:
            updates["raw_arguments"] = new_raw
            changed = True

    if call.argument_parse_error is not None:
        new_pe, pe_changed = _truncate_text(call.argument_parse_error, max_chars)
        if pe_changed:
            updates["argument_parse_error"] = new_pe
            changed = True

    if call.error is not None:
        new_err, err_changed = _truncate_text(call.error, max_chars)
        if err_changed:
            updates["error"] = new_err
            changed = True

    if call.result is not None:
        new_res, res_changed = _truncate_json_value(call.result, max_chars)
        if res_changed:
            updates["result"] = new_res
            changed = True

    new_meta, meta_changed = _truncate_mapping(call.metadata, max_chars)
    if meta_changed:
        updates["metadata"] = new_meta
        changed = True

    return (call.model_copy(update=updates) if changed else call), changed


def _truncate_trace_step(step: AgentTraceStep, max_chars: int) -> tuple[AgentTraceStep, bool]:
    updates: dict[str, Any] = {}
    changed = False

    if step.content is not None:
        new_content, content_changed = _truncate_json_value(step.content, max_chars)
        if content_changed:
            updates["content"] = new_content
            changed = True

    if step.error is not None:
        new_err, err_changed = _truncate_text(step.error, max_chars)
        if err_changed:
            updates["error"] = new_err
            changed = True

    if step.tool_calls:
        new_nested: list[ToolCallRecord] = []
        nested_changed = False
        for call in step.tool_calls:
            t_call, did_call = _truncate_tool_call_record(call, max_chars)
            new_nested.append(t_call)
            nested_changed = nested_changed or did_call
        if nested_changed:
            updates["tool_calls"] = new_nested
            changed = True

    new_meta, meta_changed = _truncate_mapping(step.metadata, max_chars)
    if meta_changed:
        updates["metadata"] = new_meta
        changed = True

    return (step.model_copy(update=updates) if changed else step), changed


def _cap_sequence_budget(items: list[Any], max_chars: int) -> tuple[list[Any], bool]:
    capped = list(items)
    changed = False
    while (
        len(capped) > 1
        and len(canonical_json_str([entry.model_dump(mode="json") for entry in capped])) > max_chars
    ):
        capped.pop()
        changed = True
    return capped, changed


def _truncate_execution_result(
    execution: ExecutionResult,
    max_chars: int | None,
) -> ExecutionResult:
    """Truncate oversized output/context fields post-scoring without mutating active input."""
    if max_chars is None:
        return execution

    was_truncated = execution.truncated
    updates: dict[str, Any] = {}

    if isinstance(execution.output, str):
        trimmed, did_trim = _truncate_text(execution.output, max_chars)
        if did_trim:
            updates["output"] = trimmed
            was_truncated = True
    elif execution.output is not None:
        serialized = canonical_json_str(execution.output)
        if len(serialized) > max_chars:
            updates["output"] = serialized[:max_chars]
            was_truncated = True

    if execution.retrieved_chunks:
        new_chunks: list[RetrievedChunk] = []
        chunks_changed = False
        for chunk in execution.retrieved_chunks:
            trimmed_chunk_text, did_trim = _truncate_text(chunk.text, max_chars)
            if did_trim:
                chunks_changed = True
                was_truncated = True
                new_chunks.append(chunk.model_copy(update={"text": trimmed_chunk_text}))
            else:
                new_chunks.append(chunk)
        if chunks_changed:
            updates["retrieved_chunks"] = new_chunks

    if execution.tool_calls:
        new_calls: list[ToolCallRecord] = []
        calls_changed = False
        for call in execution.tool_calls:
            t_call, did_call = _truncate_tool_call_record(call, max_chars)
            new_calls.append(t_call)
            if did_call:
                calls_changed = True
                was_truncated = True
        capped_calls, calls_capped = _cap_sequence_budget(new_calls, max_chars)
        if calls_capped:
            calls_changed = True
            was_truncated = True
        if calls_changed:
            updates["tool_calls"] = capped_calls

    if execution.trace:
        new_steps: list[AgentTraceStep] = []
        steps_changed = False
        for step in execution.trace:
            t_step, did_step = _truncate_trace_step(step, max_chars)
            new_steps.append(t_step)
            if did_step:
                steps_changed = True
                was_truncated = True
        capped_steps, steps_capped = _cap_sequence_budget(new_steps, max_chars)
        if steps_capped:
            steps_changed = True
            was_truncated = True
        if steps_changed:
            updates["trace"] = capped_steps

    if execution.errors:
        new_errors = [err[:max_chars] for err in execution.errors]
        if new_errors != execution.errors:
            updates["errors"] = new_errors
            was_truncated = True

    if execution.warnings:
        new_warnings = [warn[:max_chars] for warn in execution.warnings]
        if new_warnings != execution.warnings:
            updates["warnings"] = new_warnings
            was_truncated = True

    if not updates and was_truncated == execution.truncated:
        return execution

    updates["truncated"] = was_truncated
    return execution.model_copy(update=updates)


def _evaluate_metrics_safe(
    case: EvaluationCase,
    execution: ExecutionResult,
    metrics: Sequence[Metric],
) -> dict[str, MetricResult]:
    results: dict[str, MetricResult] = {}
    for metric in metrics:
        meta = metric.metadata
        try:
            outcome = metric.evaluate(case, execution)
        except Exception as exc:
            outcome = MetricResult(
                metric_id=meta.metric_id,
                metric_version=meta.metric_version,
                score=None,
                status=MetricStatus.INCONCLUSIVE,
                explanation=f"Metric evaluation error: {type(exc).__name__}: {exc}",
            )
        results[outcome.metric_id] = outcome
    return results


def _build_aggregates(
    metrics: Sequence[Metric],
    records: Sequence[CaseEvaluationRecord],
) -> tuple[dict[str, AggregateMetricSummary], dict[MetricStatus, int], list[str]]:
    global_counts: dict[MetricStatus, int] = {status: 0 for status in MetricStatus}
    per_metric_scores: dict[str, list[float]] = {m.metadata.metric_id: [] for m in metrics}
    per_metric_counts: dict[str, dict[MetricStatus, int]] = {
        m.metadata.metric_id: {status: 0 for status in MetricStatus} for m in metrics
    }
    metric_versions = {m.metadata.metric_id: m.metadata.metric_version for m in metrics}
    mandatory_failed: list[str] = []

    for rec in records:
        case_failed_or_errored = bool(rec.execution.errors)
        for metric_id, m_res in rec.metrics.items():
            global_counts[m_res.status] += 1
            if metric_id not in per_metric_counts:
                per_metric_counts[metric_id] = {status: 0 for status in MetricStatus}
                per_metric_scores[metric_id] = []
                metric_versions[metric_id] = m_res.metric_version
            per_metric_counts[metric_id][m_res.status] += 1
            if m_res.status != MetricStatus.NOT_APPLICABLE and m_res.score is not None:
                per_metric_scores[metric_id].append(m_res.score)
            if m_res.status in (MetricStatus.FAIL, MetricStatus.INCONCLUSIVE):
                case_failed_or_errored = True
        if rec.mandatory and case_failed_or_errored:
            mandatory_failed.append(rec.case_id)

    aggregates: dict[str, AggregateMetricSummary] = {}
    for metric_id, counts in per_metric_counts.items():
        scores = per_metric_scores[metric_id]
        mean = round_score(sum(scores) / len(scores)) if scores else None
        aggregates[metric_id] = AggregateMetricSummary(
            metric_id=metric_id,
            metric_version=metric_versions[metric_id],
            mean_score=mean,
            applicable_count=len(scores),
            pass_count=counts[MetricStatus.PASS],
            fail_count=counts[MetricStatus.FAIL],
            warning_count=counts[MetricStatus.WARNING],
            inconclusive_count=counts[MetricStatus.INCONCLUSIVE],
            not_applicable_count=counts[MetricStatus.NOT_APPLICABLE],
        )

    return aggregates, global_counts, sorted(mandatory_failed)


def _resolve_judge_config_fingerprint(
    metrics: Sequence[Metric],
    explicit_fingerprint: str | None,
) -> str | None:
    """Resolve explicit or derived canonical judge configuration fingerprint for a run."""
    if explicit_fingerprint is not None:
        return explicit_fingerprint
    judge_fps: list[tuple[str, str]] = []
    for metric in metrics:
        fp = getattr(metric, "judge_config_fingerprint", None)
        if isinstance(fp, str) and fp:
            judge_fps.append((metric.metadata.metric_id, fp))
    if not judge_fps:
        return None
    if len(judge_fps) == 1:
        return judge_fps[0][1]
    return canonical_sha256(
        {"judges": [[mid, fp] for mid, fp in sorted(judge_fps, key=lambda pair: pair)]}
    )


class EvaluationOrchestrator:
    """Coordinates bounded-concurrency target execution, scoring, and run assembly."""

    def __init__(
        self,
        *,
        config: OrchestratorConfig | None = None,
        storage_root: Path | str | None = None,
    ) -> None:
        self._config = config or OrchestratorConfig()
        self._storage_root = Path(storage_root) if storage_root is not None else Path(".evalforge")

    @property
    def config(self) -> OrchestratorConfig:
        """Return active orchestrator configuration."""
        return self._config

    @property
    def storage_root(self) -> Path:
        """Return configured artifact root directory."""
        return self._storage_root

    def _check_memory_guardrail(self) -> None:
        max_mb = self._config.max_memory_mb
        if max_mb is None:
            return
        rss_mb = _get_resident_memory_mb()
        if rss_mb is not None and rss_mb > max_mb:
            logger.warning(
                "Resident memory %.2f MiB exceeded soft-cap %.2f MiB",
                rss_mb,
                max_mb,
            )
            if self._config.memory_limit_action == "abort":
                raise MemoryLimitExceededError(
                    f"Resident memory {rss_mb:.2f} MiB exceeded configured limit {max_mb:.2f} MiB"
                )

    async def _execute_single_case(
        self,
        case: EvaluationCase,
        adapter: TargetAdapter,
    ) -> ExecutionResult:
        timeout = self._config.case_timeout_seconds
        start = time.perf_counter()
        if timeout is None:
            return await adapter.execute(case)
        try:
            return await asyncio.wait_for(adapter.execute(case), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            elapsed = round_score(max(0.0, time.perf_counter() - start))
            return ExecutionResult(
                case_id=case.id,
                input=case.input,
                output=None,
                elapsed_seconds=elapsed,
                errors=[f"TimeoutError: case {case.id!r} exceeded timeout of {timeout}s"],
                system_version=adapter.system_version,
                model_id=adapter.model_id,
                config_fingerprint=adapter.config_fingerprint,
            )

    async def arun(
        self,
        dataset: DatasetEngine,
        adapter: TargetAdapter,
        metrics: Sequence[Metric],
        *,
        run_id: str | None = None,
    ) -> RunRecord:
        """Execute dataset cases asynchronously with bounded concurrency and checkpointing."""
        resolved_run_id = (
            run_id
            if run_id is not None
            else (
                f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
                f"{uuid.uuid4().hex[:8]}"
            )
        )
        store = LocalRunStore(self._storage_root)
        if store.run_path(resolved_run_id).exists():
            raise ImmutabilityError(
                f"RunRecord {resolved_run_id!r} already exists at "
                f"{store.run_path(resolved_run_id)}; historical runs cannot be overwritten."
            )

        sync_metrics = [m for m in metrics if not isinstance(m, AsyncBatchMetric)]
        batch_metrics = [m for m in metrics if isinstance(m, AsyncBatchMetric)]

        stream_info: list[DatasetStreamResult] = []
        case_iter = enumerate(
            dataset.iter_cases(
                max_cases=self._config.max_dataset_cases,
                on_complete=stream_info.append,
            )
        )
        iter_lock = asyncio.Lock()
        ckpt_lock = asyncio.Lock()
        stop_event = asyncio.Event()
        completed_by_index: dict[int, CaseEvaluationRecord] = {}
        raw_batch_inputs: dict[
            int, tuple[EvaluationCase, ExecutionResult, dict[str, MetricResult]]
        ] = {}
        fatal_error: list[BaseException] = []

        async def _worker() -> None:
            while not stop_event.is_set():
                async with iter_lock:
                    if stop_event.is_set():
                        return
                    try:
                        index, case = next(case_iter)
                    except StopIteration:
                        return
                    except Exception as exc:
                        fatal_error.append(exc)
                        stop_event.set()
                        return

                try:
                    self._check_memory_guardrail()
                except Exception as exc:
                    fatal_error.append(exc)
                    stop_event.set()
                    return

                execution = await self._execute_single_case(case, adapter)
                metric_results = _evaluate_metrics_safe(case, execution, sync_metrics)

                if not batch_metrics:
                    persisted_execution = _truncate_execution_result(
                        execution, self._config.max_context_chars
                    )
                    record = CaseEvaluationRecord(
                        case_id=case.id,
                        mandatory=case.criteria.mandatory,
                        execution=persisted_execution,
                        metrics=metric_results,
                    )
                    completed_by_index[index] = record
                    async with ckpt_lock:
                        store.append_checkpoint(resolved_run_id, record)
                    has_case_error = bool(persisted_execution.errors) or any(
                        m.status == MetricStatus.INCONCLUSIVE for m in metric_results.values()
                    )
                else:
                    raw_batch_inputs[index] = (case, execution, metric_results)
                    has_case_error = bool(execution.errors) or any(
                        m.status == MetricStatus.INCONCLUSIVE for m in metric_results.values()
                    )

                if self._config.fail_fast and has_case_error:
                    fatal_error.append(
                        ExecutionError(
                            f"Execution aborted in fail_fast mode on case {case.id!r}: "
                            f"{execution.errors}"
                        )
                    )
                    stop_event.set()
                    return

        workers = [asyncio.create_task(_worker()) for _ in range(self._config.max_concurrency)]
        await asyncio.gather(*workers)

        if fatal_error:
            raise fatal_error[0]

        if batch_metrics:
            ordered_indices = sorted(raw_batch_inputs)
            ordered_pairs = [
                (raw_batch_inputs[idx][0], raw_batch_inputs[idx][1]) for idx in ordered_indices
            ]
            batch_results_by_metric: dict[str, dict[int, MetricResult]] = {
                bm.metadata.metric_id: {} for bm in batch_metrics
            }

            if self._config.fail_fast:
                chunk_size = self._config.max_concurrency
                for start in range(0, len(ordered_pairs), chunk_size):
                    chunk_indices = ordered_indices[start : start + chunk_size]
                    chunk_pairs = ordered_pairs[start : start + chunk_size]
                    for bm in batch_metrics:
                        chunk_res = await bm.aevaluate_batch(
                            chunk_pairs, max_concurrency=self._config.max_concurrency
                        )
                        for idx, m_res in zip(chunk_indices, chunk_res, strict=True):
                            batch_results_by_metric[bm.metadata.metric_id][idx] = m_res
                            if m_res.status == MetricStatus.INCONCLUSIVE:
                                raise ExecutionError(
                                    f"Execution aborted in fail_fast mode on case "
                                    f"{raw_batch_inputs[idx][0].id!r}: {m_res.explanation}"
                                )
            else:
                for bm in batch_metrics:
                    bm_res = await bm.aevaluate_batch(
                        ordered_pairs, max_concurrency=self._config.max_concurrency
                    )
                    for idx, m_res in zip(ordered_indices, bm_res, strict=True):
                        batch_results_by_metric[bm.metadata.metric_id][idx] = m_res

            for idx in ordered_indices:
                case, execution, sync_results = raw_batch_inputs[idx]
                merged_metrics: dict[str, MetricResult] = {}
                for m in metrics:
                    mid = m.metadata.metric_id
                    if mid in sync_results:
                        merged_metrics[mid] = sync_results[mid]
                    elif mid in batch_results_by_metric and idx in batch_results_by_metric[mid]:
                        merged_metrics[mid] = batch_results_by_metric[mid][idx]
                persisted_execution = _truncate_execution_result(
                    execution, self._config.max_context_chars
                )
                record = CaseEvaluationRecord(
                    case_id=case.id,
                    mandatory=case.criteria.mandatory,
                    execution=persisted_execution,
                    metrics=merged_metrics,
                )
                completed_by_index[idx] = record
                store.append_checkpoint(resolved_run_id, record)

        ordered_records = [completed_by_index[idx] for idx in sorted(completed_by_index)]
        meta = stream_info[0]
        aggregates, status_counts, mandatory_failed = _build_aggregates(metrics, ordered_records)
        metric_versions = {m.metadata.metric_id: m.metadata.metric_version for m in metrics}
        resolved_judge_fp = _resolve_judge_config_fingerprint(
            metrics, self._config.judge_config_fingerprint
        )

        run_record = RunRecord(
            run_id=resolved_run_id,
            timestamp=datetime.now(timezone.utc),
            package_version=_package_version(),
            dataset_id=meta.dataset_id,
            dataset_version=meta.dataset_version,
            dataset_fingerprint=meta.dataset_fingerprint,
            evaluated_case_count=meta.evaluated_case_count,
            dataset_capped=meta.dataset_capped,
            max_dataset_cases=meta.max_dataset_cases,
            system_version=adapter.system_version,
            model_id=adapter.model_id,
            config_fingerprint=adapter.config_fingerprint,
            judge_config_fingerprint=resolved_judge_fp,
            metric_versions=metric_versions,
            seed=self._config.seed,
            aggregates=aggregates,
            status_counts=status_counts,
            mandatory_failed_case_ids=mandatory_failed,
            has_mandatory_failures=bool(mandatory_failed),
            case_results=ordered_records,
        )
        store.save_run(run_record)
        if not self._config.retain_checkpoints:
            store.remove_checkpoint(resolved_run_id)
        return run_record

    def run(
        self,
        dataset: DatasetEngine,
        adapter: TargetAdapter,
        metrics: Sequence[Metric],
        *,
        run_id: str | None = None,
    ) -> RunRecord:
        """Synchronously execute an evaluation run outside an active async event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(dataset, adapter, metrics, run_id=run_id))
        raise ExecutionError(
            "EvaluationOrchestrator.run() cannot run inside an active event loop; "
            "await orchestrator.arun(...) instead"
        )
