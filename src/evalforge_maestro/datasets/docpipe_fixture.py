"""Dependency-free importer converting docpipe-maestro fixtures into DatasetEngine."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalforge_maestro.datasets.engine import DatasetEngine
from evalforge_maestro.exceptions import (
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
)
from evalforge_maestro.types import CaseMetadata, EvaluationCase, ExpectedContextItem


def _strip_optional_str(value: Any, *, field_name: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DatasetError(
            f"Fixture field {field_name!r} at record {line_number} must be a string",
            line_number=line_number,
            field=field_name,
        )
    cleaned = value.strip()
    return cleaned or None


def _parse_json_or_jsonl(raw_text: str, path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stripped = raw_text.strip()
    if not stripped:
        raise EmptyDatasetError(f"Docpipe fixture file {path} contains zero cases")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as whole_exc:
        records: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as line_exc:
                raise DatasetError(
                    f"Invalid JSONL at line {line_no} in {path}: {line_exc.msg}",
                    line_number=line_no,
                ) from (line_exc if line_no > 1 else whole_exc)
            if not isinstance(decoded, dict):
                raise DatasetError(
                    f"Fixture line {line_no} in {path} must decode to a JSON object",
                    line_number=line_no,
                ) from whole_exc
            records.append(decoded)
        return records, {}

    return _unwrap_parsed_container(parsed)


def _unwrap_parsed_container(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(payload, Mapping):
        envelope_meta: dict[str, Any] = {
            "collection": payload.get("collection"),
            "profile": payload.get("profile"),
        }
        for key in ("queries", "cases", "items"):
            if key in payload:
                entries = payload[key]
                if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, Mapping)):
                    raise DatasetError(
                        f"Fixture key {key!r} must contain a sequence of case objects",
                        field=key,
                    )
                return _coerce_mapping_sequence(entries), envelope_meta

        # Allow a single JSONL line object if it directly carries a query/case payload
        if any(k in payload for k in ("question", "query", "input")):
            return [dict(payload)], {}

        raise DatasetError(
            "Docpipe fixture mapping must contain 'queries', 'cases', or 'items'",
        )

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return _coerce_mapping_sequence(payload), {}

    raise DatasetError(
        f"Unsupported docpipe fixture payload type: {type(payload).__name__}",
    )


def _coerce_mapping_sequence(items: Sequence[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx, entry in enumerate(items, start=1):
        if not isinstance(entry, Mapping):
            raise DatasetError(
                f"Fixture entry {idx} must be a mapping, got {type(entry).__name__}",
                line_number=idx,
            )
        records.append(dict(entry))
    return records


def _extract_expected_context(
    entry: Mapping[str, Any],
    *,
    line_number: int,
    case_id: str,
) -> list[str | ExpectedContextItem] | None:
    raw_expected: Any = None
    for key in ("expected_context", "relevant_ids", "expected_ids"):
        if key in entry and entry[key] is not None:
            raw_expected = entry[key]
            break

    if raw_expected is None:
        return None
    if isinstance(raw_expected, (str, bytes, Mapping)) or not isinstance(raw_expected, Sequence):
        raise DatasetError(
            f"Expected context at record {line_number} must be a sequence",
            line_number=line_number,
            case_id=case_id,
            field="expected_context",
        )

    rel_weights = entry.get("relevance")
    if rel_weights is not None and not isinstance(rel_weights, (Mapping, Sequence)):
        raise DatasetError(
            f"Fixture field 'relevance' at record {line_number} must be a mapping or sequence",
            line_number=line_number,
            case_id=case_id,
            field="relevance",
        )
    if (
        isinstance(rel_weights, Sequence)
        and not isinstance(rel_weights, (str, bytes))
        and len(rel_weights) != len(raw_expected)
    ):
        raise DatasetError(
            f"Fixture 'relevance' sequence length must match expected IDs at record {line_number}",
            line_number=line_number,
            case_id=case_id,
            field="relevance",
        )

    items: list[str | ExpectedContextItem] = []
    for pos, raw_item in enumerate(raw_expected):
        if isinstance(raw_item, str):
            weight: Any = None
            if isinstance(rel_weights, Mapping) and raw_item in rel_weights:
                weight = rel_weights[raw_item]
            elif isinstance(rel_weights, Sequence) and not isinstance(rel_weights, (str, bytes)):
                weight = rel_weights[pos]

            if weight is not None:
                try:
                    items.append(ExpectedContextItem(id=raw_item, relevance=weight))
                except ValidationError as exc:
                    msg = exc.errors()[0]["msg"]
                    raise DatasetError(
                        f"Invalid relevance weight at record {line_number}: {msg}",
                        line_number=line_number,
                        case_id=case_id,
                        field="expected_context",
                    ) from exc
            else:
                items.append(raw_item)
        else:
            items.append(raw_item)

    return items


def _build_case(
    entry: Mapping[str, Any],
    *,
    index: int,
    envelope_meta: Mapping[str, Any],
) -> EvaluationCase:
    if "id" in entry and entry["id"] is not None:
        raw_id = entry["id"]
    elif "case_id" in entry and entry["case_id"] is not None:
        raw_id = entry["case_id"]
    else:
        raw_id = f"case-{index}"

    if not isinstance(raw_id, str) or not raw_id.strip():
        raise DatasetError(
            f"Fixture record {index} has invalid empty identifier",
            line_number=index,
            field="id",
        )
    case_id = raw_id.strip()

    raw_input: Any = None
    for key in ("input", "question", "query"):
        if key in entry and entry[key] is not None:
            raw_input = entry[key]
            break
    if raw_input is None or (isinstance(raw_input, str) and not raw_input.strip()):
        raise DatasetError(
            f"Fixture record {index} ({case_id!r}) missing input/question/query",
            line_number=index,
            case_id=case_id,
            field="input",
        )

    expected_context = _extract_expected_context(entry, line_number=index, case_id=case_id)

    reference: Any = None
    for ref_key in ("reference", "expected_answer", "answer"):
        if ref_key in entry and entry[ref_key] is not None:
            reference = entry[ref_key]
            break

    raw_meta = entry.get("metadata")
    if raw_meta is not None and not isinstance(raw_meta, Mapping):
        raise DatasetError(
            f"Fixture metadata at record {index} must be a mapping",
            line_number=index,
            case_id=case_id,
            field="metadata",
        )
    meta_dict = dict(raw_meta or {})
    extra_dict = (
        dict(meta_dict.get("extra", {})) if isinstance(meta_dict.get("extra"), Mapping) else {}
    )

    collection = _strip_optional_str(
        entry.get("collection") or envelope_meta.get("collection"),
        field_name="collection",
        line_number=index,
    )
    profile = _strip_optional_str(
        entry.get("profile") or envelope_meta.get("profile"),
        field_name="profile",
        line_number=index,
    )
    if collection is not None:
        extra_dict.setdefault("collection", collection)
    if profile is not None:
        extra_dict.setdefault("profile", profile)
    if entry.get("notes") is not None:
        extra_dict.setdefault("notes", entry["notes"])

    meta_dict["source"] = meta_dict.get("source") or collection or "docpipe_fixture"
    meta_dict["extra"] = extra_dict

    payload: dict[str, Any] = {
        "id": case_id,
        "input": raw_input.strip() if isinstance(raw_input, str) else raw_input,
        "reference": reference,
        "expected_context": expected_context,
        "metadata": CaseMetadata.model_validate(meta_dict),
    }
    if "criteria" in entry and entry["criteria"] is not None:
        payload["criteria"] = entry["criteria"]

    try:
        return EvaluationCase.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        loc = ".".join(str(part) for part in first_error.get("loc", ())) or None
        raise DatasetError(
            f"Docpipe fixture validation failed at record {index} ({case_id!r}): "
            f"{first_error['msg']}",
            line_number=index,
            case_id=case_id,
            field=loc,
        ) from exc


def load_docpipe_fixture(
    source: Path | str | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
) -> DatasetEngine:
    """Convert docpipe-maestro JSON/JSONL evaluation fixtures into DatasetEngine."""
    envelope_meta: dict[str, Any] = {}
    if isinstance(source, (Path, str)):
        path = Path(source)
        if not path.is_file():
            raise DatasetError(f"Docpipe fixture file not found: {path}")
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DatasetError(f"Failed reading docpipe fixture {path}: {exc}") from exc
        records, envelope_meta = _parse_json_or_jsonl(raw_text, path)
        inferred_id = path.stem.strip() or (
            str(envelope_meta.get("collection")).strip()
            if envelope_meta.get("collection")
            else "docpipe-fixture"
        )
    else:
        records, envelope_meta = _unwrap_parsed_container(source)
        raw_collection = envelope_meta.get("collection")
        inferred_id = (
            raw_collection.strip()
            if isinstance(raw_collection, str) and raw_collection.strip()
            else "docpipe-fixture"
        )

    if not records:
        raise EmptyDatasetError("Docpipe fixture contains zero evaluation cases")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for idx, entry in enumerate(records, start=1):
        case = _build_case(entry, index=idx, envelope_meta=envelope_meta)
        if case.id in seen_ids:
            raise DuplicateCaseIdError(
                f"Duplicate EvaluationCase.id {case.id!r} at fixture record {idx}",
                line_number=idx,
                case_id=case.id,
                field="id",
            )
        seen_ids.add(case.id)
        cases.append(case)

    resolved_id = dataset_id if dataset_id is not None else inferred_id
    return DatasetEngine(cases, dataset_id=resolved_id, dataset_version=dataset_version)
