"""Lazy-imported DocpipeAdapter integrating docpipe-maestro retrieve() and answer_detailed()."""

from __future__ import annotations

import importlib
import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from evalforge_maestro._canonical import redact_secrets, round_score
from evalforge_maestro.adapters._shared import (
    build_validated_execution_result,
    invoke_function,
    normalize_token_usage,
    redact_adapter_config,
)
from evalforge_maestro.exceptions import AdapterError, MissingExtraError
from evalforge_maestro.types import EvaluationCase, ExecutionResult, RetrievedChunk, TokenUsage


def _accepts_kwarg(fn: Callable[..., Any], name: str) -> bool:
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.kind == inspect.Parameter.VAR_KEYWORD or p.name == name for p in params)


def _read_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_query(case_input: Any) -> str:
    if isinstance(case_input, str):
        cleaned = case_input.strip()
        if not cleaned:
            raise AdapterError("DocpipeAdapter requires a non-empty string query input")
        return cleaned
    if isinstance(case_input, Mapping):
        for key in ("question", "query", "input"):
            val = case_input.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    raise AdapterError(
        "DocpipeAdapter expects str input or a mapping with non-empty "
        "'question', 'query', or 'input'"
    )


def _resolve_docpipe_functions(
    *,
    client: Any | None,
    mode: Literal["answer_detailed", "retrieve"],
) -> tuple[
    Callable[..., Any],
    Callable[..., Any] | None,
    Callable[..., Any] | None,
    Callable[..., Any] | None,
]:
    if client is None:
        try:
            root_mod = importlib.import_module("docpipe_maestro")
        except ImportError as exc:
            raise MissingExtraError(extra="docpipe-maestro", package="docpipe-maestro") from exc

        retrieve_fn = getattr(root_mod, "retrieve", None)
        answer_fn = getattr(root_mod, "answer_detailed", None)
        build_chat_messages_fn = getattr(root_mod, "build_chat_messages", None)
        build_prompt_fn = getattr(root_mod, "build_prompt", None)

        if not callable(retrieve_fn):
            retriever_mod = importlib.import_module("docpipe_maestro.query.retriever")
            retrieve_fn = getattr(retriever_mod, "retrieve", None)

        if mode == "answer_detailed" and not callable(answer_fn):
            answer_mod = importlib.import_module("docpipe_maestro.query.answer")
            answer_fn = getattr(answer_mod, "answer_detailed", None)
            prompts_mod = importlib.import_module("docpipe_maestro.query.prompts")
            if build_chat_messages_fn is None:
                build_chat_messages_fn = getattr(prompts_mod, "build_chat_messages", None)
            if build_prompt_fn is None:
                build_prompt_fn = getattr(prompts_mod, "build_prompt", None)
    else:
        retrieve_fn = getattr(client, "retrieve", None)
        answer_fn = getattr(client, "answer_detailed", None)
        build_chat_messages_fn = getattr(client, "build_chat_messages", None)
        build_prompt_fn = getattr(client, "build_prompt", None)

    if not callable(retrieve_fn):
        raise AdapterError("Docpipe client/module must expose a callable 'retrieve'")
    if mode == "answer_detailed" and not callable(answer_fn):
        raise AdapterError(
            "Docpipe client/module must expose a callable 'answer_detailed' in "
            "'answer_detailed' mode"
        )

    return (
        retrieve_fn,
        answer_fn if callable(answer_fn) else None,
        build_chat_messages_fn if callable(build_chat_messages_fn) else None,
        build_prompt_fn if callable(build_prompt_fn) else None,
    )


def _normalize_docpipe_chunks(raw_sections: Any) -> list[RetrievedChunk]:
    if raw_sections is None:
        return []
    if isinstance(raw_sections, (str, bytes, Mapping)) or not isinstance(raw_sections, Sequence):
        raise AdapterError(
            f"Docpipe retrieve() must return a chunk sequence, got {type(raw_sections).__name__}"
        )

    chunks: list[RetrievedChunk] = []
    for idx, section in enumerate(raw_sections, start=1):
        raw_meta = _read_attr_or_key(section, "metadata", {})
        metadata = redact_secrets(dict(raw_meta or {})) if isinstance(raw_meta, Mapping) else {}
        raw_rank = _read_attr_or_key(section, "rank", None)
        chunks.append(
            RetrievedChunk(
                id=_read_attr_or_key(section, "id"),
                text=_read_attr_or_key(section, "text", ""),
                parent_id=_read_attr_or_key(section, "parent_id", None),
                rank=raw_rank if raw_rank is not None else idx,
                score=_read_attr_or_key(section, "score", None),
                metadata=metadata,
            )
        )
    return chunks


class DocpipeAdapter:
    """Lazy-imported adapter wrapping docpipe-maestro retrieve() and answer_detailed()."""

    def __init__(
        self,
        *,
        mode: Literal["answer_detailed", "retrieve"] = "answer_detailed",
        collection: str | None = None,
        persist_dir: Path | str | None = None,
        retrieve_kwargs: Mapping[str, Any] | None = None,
        answer_kwargs: Mapping[str, Any] | None = None,
        system_version: str | None = None,
        model_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        if mode not in ("answer_detailed", "retrieve"):
            raise AdapterError(
                f"Unsupported DocpipeAdapter mode {mode!r}; "
                "expected 'answer_detailed' or 'retrieve'"
            )

        (
            self._retrieve_fn,
            self._answer_fn,
            self._build_chat_messages_fn,
            self._build_prompt_fn,
        ) = _resolve_docpipe_functions(client=client, mode=mode)

        self._owns_global_docpipe = client is None or getattr(
            self._retrieve_fn, "__module__", ""
        ).startswith("docpipe_maestro")

        self._mode = mode
        self._system_version = system_version
        self._model_id = model_id

        merged_retrieve = dict(retrieve_kwargs or {})
        if collection is not None:
            merged_retrieve["collection"] = collection
        if persist_dir is not None:
            merged_retrieve["persist_dir"] = str(persist_dir)
        self._retrieve_kwargs = merged_retrieve
        self._answer_kwargs = dict(answer_kwargs or {})

        cfg_payload: dict[str, Any] = {
            "mode": mode,
            "collection": collection,
            "persist_dir": str(persist_dir) if persist_dir is not None else None,
            "retrieve_kwargs": merged_retrieve,
            "answer_kwargs": self._answer_kwargs,
        }
        self._config_fingerprint, self._adapter_metadata = redact_adapter_config(cfg_payload)

    @property
    def system_version(self) -> str | None:
        """Return declared docpipe system version."""
        return self._system_version

    @property
    def model_id(self) -> str | None:
        """Return declared generator model identifier."""
        return self._model_id

    @property
    def config_fingerprint(self) -> str | None:
        """Return canonical SHA-256 fingerprint of redacted docpipe configuration."""
        return self._config_fingerprint

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Execute docpipe-maestro retrieve()/answer_detailed() and return ExecutionResult."""
        errors: list[str] = []
        warnings: list[str] = []
        output: Any = None
        chunks: list[RetrievedChunk] = []
        tokens: TokenUsage | None = None
        truncated = False
        resolved_model_id = self._model_id
        metadata_copy = dict(self._adapter_metadata)
        start = time.perf_counter()

        try:
            query = _extract_query(case.input)
            ret_opts = dict(self._retrieve_kwargs)
            if (
                self._owns_global_docpipe
                and "local_only" in ret_opts
                and not _accepts_kwarg(self._retrieve_fn, "local_only")
            ):
                ret_opts.pop("local_only")
            raw_sections = await invoke_function(self._retrieve_fn, query, **ret_opts)
            chunks = _normalize_docpipe_chunks(raw_sections)

            if self._mode == "answer_detailed" and self._answer_fn is not None:
                if self._build_chat_messages_fn is not None:
                    prompt_payload = self._build_chat_messages_fn(query, raw_sections)
                elif self._build_prompt_fn is not None:
                    prompt_payload = self._build_prompt_fn(query, raw_sections)
                else:
                    prompt_payload = query

                ans_opts = dict(self._answer_kwargs)
                if (
                    self._owns_global_docpipe
                    and "local_only" in ans_opts
                    and not _accepts_kwarg(self._answer_fn, "local_only")
                ):
                    ans_opts.pop("local_only")
                ans_opts.setdefault("has_context", bool(raw_sections))
                gen = await invoke_function(self._answer_fn, prompt_payload, **ans_opts)

                if isinstance(gen, str):
                    output = gen
                else:
                    output = _read_attr_or_key(gen, "text", None)
                    gen_model = _read_attr_or_key(gen, "model", None)
                    if resolved_model_id is None and isinstance(gen_model, str):
                        resolved_model_id = gen_model
                    finish_reason = _read_attr_or_key(gen, "finish_reason", None)
                    truncated = bool(_read_attr_or_key(gen, "truncated", False))
                    if finish_reason is not None:
                        metadata_copy["finish_reason"] = finish_reason
                    if truncated or finish_reason == "length":
                        warnings.append(
                            "Docpipe generation output truncated "
                            f"(finish_reason={finish_reason!r})."
                        )
                    has_usage = any(
                        _read_attr_or_key(gen, k, None) is not None
                        for k in (
                            "prompt_tokens",
                            "completion_tokens",
                            "reasoning_tokens",
                            "total_tokens",
                        )
                    )
                    if has_usage:
                        tokens = normalize_token_usage(gen)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        elapsed = round_score(max(0.0, time.perf_counter() - start))
        return build_validated_execution_result(
            case=case,
            output=output,
            retrieved_chunks=chunks,
            tokens=tokens,
            elapsed_seconds=elapsed,
            truncated=truncated,
            errors=errors,
            warnings=warnings,
            system_version=self._system_version,
            model_id=resolved_model_id,
            config_fingerprint=self._config_fingerprint,
            adapter_metadata=metadata_copy,
        )
