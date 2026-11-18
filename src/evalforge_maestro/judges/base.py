"""Base judge metric implementation unifying sync Metric and async AsyncBatchMetric."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from evalforge_maestro._canonical import canonical_sha256, scrub_secret_text
from evalforge_maestro.exceptions import ConfigurationError, LocalOnlyPolicyError, MissingExtraError
from evalforge_maestro.judges.mock import generate_mock_judge_json
from evalforge_maestro.judges.prompts import JudgePromptSpec, build_judge_messages
from evalforge_maestro.judges.provider import (
    CompletionFn,
    evaluate_with_retries,
    invoke_live_completion,
)
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    JudgeConfig,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)


def _resolve_case_threshold(
    case: EvaluationCase,
    metric_id: str,
    default_threshold: float,
) -> float:
    if metric_id in case.criteria.metric_thresholds:
        return case.criteria.metric_thresholds[metric_id]
    if case.criteria.pass_threshold is not None:
        return case.criteria.pass_threshold
    return default_threshold


def _missing_input_reason(
    spec: JudgePromptSpec,
    case: EvaluationCase,
    execution: ExecutionResult,
) -> str | None:
    if spec.require_output and execution.output is None:
        return f"ExecutionResult.output is absent; {spec.metric_id} is not applicable."
    if spec.require_reference and case.reference is None:
        return f"EvaluationCase.reference is absent; {spec.metric_id} is not applicable."
    if spec.require_context and not execution.retrieved_chunks:
        return f"ExecutionResult.retrieved_chunks is empty; {spec.metric_id} is not applicable."
    return None


class BaseJudgeMetric:
    """Provider-independent base judge metric implementing Metric and AsyncBatchMetric."""

    def __init__(
        self,
        *,
        spec: JudgePromptSpec,
        config: JudgeConfig | None = None,
        rubric_override: str | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        self._spec = spec
        self._config = config or JudgeConfig()
        self._rubric_override = rubric_override
        self._api_key = api_key
        self._mock_responses: dict[str, str | tuple[str, ...]] | None = None
        if mock_responses is not None:
            normalized: dict[str, str | tuple[str, ...]] = {}
            for case_id, payload in mock_responses.items():
                if isinstance(payload, str):
                    normalized[case_id] = payload
                else:
                    normalized[case_id] = tuple(payload)
            self._mock_responses = normalized
        self._completion_fn = completion_fn
        self._metadata = MetricMetadata(
            metric_id=spec.metric_id,
            metric_version=spec.metric_version,
            what_it_measures=spec.what_it_measures,
            required_case_fields=spec.required_case_fields,
            required_execution_fields=spec.required_execution_fields,
            calculation_method=spec.calculation_method,
            known_limitations=spec.known_limitations,
        )
        active_rubric = rubric_override if rubric_override is not None else spec.rubric_instructions
        rubric_digest = canonical_sha256(
            {
                "metric_id": spec.metric_id,
                "metric_version": spec.metric_version,
                "rubric": active_rubric,
            }
        )
        self._fingerprint = canonical_sha256(
            {
                "config": self._config.redacted_dict(),
                "metric_id": spec.metric_id,
                "metric_version": spec.metric_version,
                "rubric_digest": rubric_digest,
            }
        )

    @property
    def metadata(self) -> MetricMetadata:
        """Return formal metric capability, input, and limitation declaration."""
        return self._metadata

    @property
    def judge_config(self) -> JudgeConfig:
        """Return redacted JudgeConfig bound to this metric instance."""
        return self._config

    @property
    def judge_config_fingerprint(self) -> str:
        """Return canonical SHA-256 fingerprint combining JudgeConfig and metric rubric."""
        return self._fingerprint

    def _snapshot(self, threshold: float) -> dict[str, Any]:
        redacted = self._config.redacted_dict()
        redacted["threshold"] = threshold
        redacted["judge_config_fingerprint"] = self._fingerprint
        return redacted

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Synchronously evaluate one ExecutionResult against its EvaluationCase contract."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aevaluate(case, execution))

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.aevaluate(case, execution)).result()

    async def aevaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Asynchronously evaluate one case with injection isolation and INCONCLUSIVE fallback."""
        threshold = _resolve_case_threshold(
            case, self._metadata.metric_id, self._config.pass_threshold
        )
        snapshot = self._snapshot(threshold)

        if execution.errors:
            return MetricResult(
                metric_id=self._metadata.metric_id,
                metric_version=self._metadata.metric_version,
                score=None,
                status=MetricStatus.INCONCLUSIVE,
                explanation=scrub_secret_text(f"Upstream execution failed: {execution.errors[0]}"),
                evidence=list(execution.errors),
                config_snapshot=snapshot,
            )

        missing_reason = _missing_input_reason(self._spec, case, execution)
        if missing_reason is not None:
            return MetricResult(
                metric_id=self._metadata.metric_id,
                metric_version=self._metadata.metric_version,
                score=None,
                status=MetricStatus.NOT_APPLICABLE,
                explanation=missing_reason,
                config_snapshot=snapshot,
            )

        messages, _nonce = build_judge_messages(
            self._spec,
            case,
            execution,
            custom_rubric=self._rubric_override,
        )

        if self._config.mock_mode:
            if self._mock_responses is not None and case.id in self._mock_responses:
                scripted = self._mock_responses[case.id]
                if isinstance(scripted, str):

                    async def _mock_single(_attempt: int) -> str:
                        return scripted

                    return await evaluate_with_retries(
                        _mock_single,
                        config=self._config,
                        effective_threshold=threshold,
                        metadata=self._metadata,
                        config_snapshot=snapshot,
                        allow_retries=False,
                    )

                async def _mock_sequence(attempt: int) -> str:
                    if not scripted:
                        raise ValueError(f"Empty mock response sequence for case {case.id!r}")
                    idx = min(attempt, len(scripted) - 1)
                    return scripted[idx]

                return await evaluate_with_retries(
                    _mock_sequence,
                    config=self._config,
                    effective_threshold=threshold,
                    metadata=self._metadata,
                    config_snapshot=snapshot,
                    allow_retries=True,
                )

            async def _mock_heuristic(_attempt: int) -> str:
                return generate_mock_judge_json(
                    self._spec,
                    case,
                    execution,
                    rubric_override=self._rubric_override,
                )

            return await evaluate_with_retries(
                _mock_heuristic,
                config=self._config,
                effective_threshold=threshold,
                metadata=self._metadata,
                config_snapshot=snapshot,
                allow_retries=False,
            )

        async def _call_once(_attempt: int) -> str:
            return await invoke_live_completion(
                messages,
                config=self._config,
                api_key=self._api_key,
                completion_fn=self._completion_fn,
            )

        return await evaluate_with_retries(
            _call_once,
            config=self._config,
            effective_threshold=threshold,
            metadata=self._metadata,
            config_snapshot=snapshot,
            allow_retries=True,
        )

    async def aevaluate_batch(
        self,
        items: Sequence[tuple[EvaluationCase, ExecutionResult]],
        *,
        max_concurrency: int = 4,
    ) -> list[MetricResult]:
        """Schedule per-case evaluations grouped by canonical retrieved context digest."""
        if isinstance(max_concurrency, bool) or max_concurrency < 1:
            raise ConfigurationError(f"max_concurrency must be >= 1, got {max_concurrency!r}")
        if not items:
            return []

        groups: dict[str, list[int]] = {}
        for idx, (_, execution) in enumerate(items):
            if execution.retrieved_chunks:
                ctx_key = canonical_sha256(
                    [(c.id, c.text, c.parent_id) for c in execution.retrieved_chunks]
                )
            else:
                ctx_key = "__no_context__"
            groups.setdefault(ctx_key, []).append(idx)

        grouped_indices = [idx for idxs in groups.values() for idx in idxs]
        results: list[MetricResult | None] = [None] * len(items)
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_indexed(orig_idx: int) -> None:
            case, execution = items[orig_idx]
            async with semaphore:
                try:
                    results[orig_idx] = await self.aevaluate(case, execution)
                except (LocalOnlyPolicyError, MissingExtraError):
                    raise
                except Exception as exc:
                    threshold = _resolve_case_threshold(
                        case, self._metadata.metric_id, self._config.pass_threshold
                    )
                    results[orig_idx] = MetricResult(
                        metric_id=self._metadata.metric_id,
                        metric_version=self._metadata.metric_version,
                        score=None,
                        status=MetricStatus.INCONCLUSIVE,
                        explanation=scrub_secret_text(
                            f"Judge batch item failed: {type(exc).__name__}: {exc}"
                        ),
                        config_snapshot=self._snapshot(threshold),
                    )

        await asyncio.gather(*(_run_indexed(idx) for idx in grouped_indices))
        return [res for res in results if res is not None]
