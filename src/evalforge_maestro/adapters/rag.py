"""Protocol-based RAG target adapter with configurable mapping, path, and callable extractors."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from evalforge_maestro._canonical import redact_secrets, round_score
from evalforge_maestro.adapters._shared import (
    build_target_arg,
    build_validated_execution_result,
    invoke_callable,
    normalize_token_usage,
    redact_adapter_config,
    validate_callable_target_options,
)
from evalforge_maestro.exceptions import AdapterError
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    RAGExtractorConfig,
    RetrievedChunk,
    TokenUsage,
)

_MISSING = object()


def _resolve_dotted_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return _MISSING
    return current


def _extract_field(
    payload: Any,
    rule: str | Callable[[Any], Any] | None,
    fallbacks: tuple[str, ...],
    *,
    required: bool,
    default: Any = None,
    field_label: str,
) -> Any:
    """Resolve one target field via explicit rule (strict) or fallback lookup paths."""
    if rule is not None:
        if callable(rule):
            return rule(payload)
        resolved = _resolve_dotted_path(payload, rule)
        if resolved is _MISSING:
            raise AdapterError(f"Extractor path {rule!r} for {field_label} was not found")
        return resolved

    for candidate in fallbacks:
        resolved = _resolve_dotted_path(payload, candidate)
        if resolved is not _MISSING:
            return resolved

    if required:
        raise AdapterError(
            f"Missing required RAG field {field_label!r} (tried {', '.join(fallbacks)})"
        )
    return default


def _normalize_chunk(
    raw_chunk: Any,
    *,
    index: int,
    extractors: RAGExtractorConfig,
) -> RetrievedChunk:
    chunk_id = _extract_field(
        raw_chunk,
        extractors.chunk_id,
        ("id", "chunk_id", "doc_id"),
        required=True,
        field_label=f"chunk[{index}].id",
    )
    chunk_text = _extract_field(
        raw_chunk,
        extractors.chunk_text,
        ("text", "content", "page_content"),
        required=True,
        field_label=f"chunk[{index}].text",
    )
    parent_id = _extract_field(
        raw_chunk,
        extractors.chunk_parent_id,
        ("parent_id", "metadata.parent_id"),
        required=False,
        default=None,
        field_label=f"chunk[{index}].parent_id",
    )
    raw_rank = _extract_field(
        raw_chunk,
        extractors.chunk_rank,
        ("rank",),
        required=False,
        default=None,
        field_label=f"chunk[{index}].rank",
    )
    rank = raw_rank if raw_rank is not None else index

    score = _extract_field(
        raw_chunk,
        extractors.chunk_score,
        ("score",),
        required=False,
        default=None,
        field_label=f"chunk[{index}].score",
    )
    raw_meta = _extract_field(
        raw_chunk,
        extractors.chunk_metadata,
        ("metadata",),
        required=False,
        default={},
        field_label=f"chunk[{index}].metadata",
    )
    if raw_meta is None:
        metadata: dict[str, Any] = {}
    elif isinstance(raw_meta, Mapping):
        metadata = redact_secrets(dict(raw_meta))
    else:
        raise AdapterError(
            f"Chunk metadata at index {index} must be a mapping, got {type(raw_meta).__name__}"
        )

    return RetrievedChunk(
        id=chunk_id,
        text=chunk_text,
        parent_id=parent_id,
        rank=rank,
        score=score,
        metadata=metadata,
    )


def _extract_rag_payload(
    raw_out: Any,
    extractors: RAGExtractorConfig,
) -> tuple[Any, list[RetrievedChunk], TokenUsage | None]:
    output = _extract_field(
        raw_out,
        extractors.output,
        ("output", "answer", "response"),
        required=False,
        default=None,
        field_label="output",
    )
    raw_chunks = _extract_field(
        raw_out,
        extractors.chunks,
        ("retrieved_chunks", "chunks", "contexts", "documents"),
        required=True,
        field_label="chunks",
    )
    if raw_chunks is None:
        chunk_seq: list[Any] = []
    elif isinstance(raw_chunks, (str, bytes, Mapping)) or not isinstance(raw_chunks, Sequence):
        raise AdapterError(f"Extracted chunks must be a sequence, got {type(raw_chunks).__name__}")
    else:
        chunk_seq = list(raw_chunks)

    normalized_chunks = [
        _normalize_chunk(raw_chunk, index=idx, extractors=extractors)
        for idx, raw_chunk in enumerate(chunk_seq, start=1)
    ]

    raw_tokens = _extract_field(
        raw_out,
        extractors.tokens,
        ("tokens", "usage", "token_usage"),
        required=False,
        default=None,
        field_label="tokens",
    )
    tokens = normalize_token_usage(raw_tokens)
    return output, normalized_chunks, tokens


class RAGAdapter:
    """Protocol-based RAG target adapter normalizing answers, chunks, and tokens."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        extractors: RAGExtractorConfig | None = None,
        system_version: str | None = None,
        model_id: str | None = None,
        config: Mapping[str, Any] | None = None,
        pass_case: bool = False,
        input_mapper: Callable[[EvaluationCase], Any] | None = None,
    ) -> None:
        self._is_coro_fn = validate_callable_target_options(
            fn,
            adapter_name="RAGAdapter",
            pass_case=pass_case,
            input_mapper=input_mapper,
        )
        self._fn = fn
        self._extractors = extractors or RAGExtractorConfig()
        self._system_version = system_version
        self._model_id = model_id
        self._pass_case = pass_case
        self._input_mapper = input_mapper
        self._config_fingerprint, self._adapter_metadata = redact_adapter_config(config)

    @property
    def system_version(self) -> str | None:
        """Return declared target RAG system version."""
        return self._system_version

    @property
    def model_id(self) -> str | None:
        """Return declared generator model identifier."""
        return self._model_id

    @property
    def config_fingerprint(self) -> str | None:
        """Return canonical SHA-256 fingerprint of redacted adapter configuration."""
        return self._config_fingerprint

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Invoke wrapped RAG pipeline and normalize output, chunks, and token usage."""
        arg = build_target_arg(case, pass_case=self._pass_case, input_mapper=self._input_mapper)
        errors: list[str] = []
        output: Any = None
        chunks: list[RetrievedChunk] = []
        tokens: TokenUsage | None = None
        start = time.perf_counter()

        try:
            raw_out = await invoke_callable(self._fn, arg, is_coro_fn=self._is_coro_fn)
            output, chunks, tokens = _extract_rag_payload(raw_out, self._extractors)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        elapsed = round_score(max(0.0, time.perf_counter() - start))
        return build_validated_execution_result(
            case=case,
            output=output,
            retrieved_chunks=chunks,
            tokens=tokens,
            elapsed_seconds=elapsed,
            truncated=False,
            errors=errors,
            warnings=[],
            system_version=self._system_version,
            model_id=self._model_id,
            config_fingerprint=self._config_fingerprint,
            adapter_metadata=self._adapter_metadata,
        )
