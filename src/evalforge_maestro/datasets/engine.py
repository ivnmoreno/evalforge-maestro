"""Streaming JSONL dataset intake, validation, duplicate detection, and canonical fingerprinting."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from evalforge_maestro._canonical import StreamingCanonicalHasher
from evalforge_maestro.exceptions import (
    DatasetError,
    DuplicateCaseIdError,
    EmptyDatasetError,
)
from evalforge_maestro.types import EvaluationCase


class DatasetStreamResult(BaseModel):
    """Canonical metadata and SHA-256 fingerprint emitted at completion of dataset streaming."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    dataset_version: str | None
    dataset_fingerprint: str
    evaluated_case_count: int
    dataset_capped: bool
    max_dataset_cases: int | None


class DatasetEngine:
    """Lazy streaming dataset loader enforcing schema contracts and canonical SHA-256 hashing."""

    def __init__(
        self,
        source: Path | str | Iterable[EvaluationCase | Mapping[str, Any]],
        *,
        dataset_id: str | None = None,
        dataset_version: str | None = None,
    ) -> None:
        if dataset_id is not None:
            cleaned_id = dataset_id.strip()
            if not cleaned_id:
                raise DatasetError("dataset_id must be a non-empty string", field="dataset_id")
            resolved_id = cleaned_id
        elif isinstance(source, (Path, str)):
            stem = Path(source).stem.strip()
            resolved_id = stem or "dataset"
        else:
            resolved_id = "in-memory"

        self._source: Path | str | Iterable[EvaluationCase | Mapping[str, Any]] = source
        self._dataset_id = resolved_id
        self._dataset_version = dataset_version

    @property
    def dataset_id(self) -> str:
        """Return resolved logical dataset identifier."""
        return self._dataset_id

    @property
    def dataset_version(self) -> str | None:
        """Return optional dataset version string."""
        return self._dataset_version

    def _iter_source_items(self) -> Iterator[tuple[int, Any, bool]]:
        """Yield (line_or_index, raw_item, is_unparsed_json_str) lazily."""
        if isinstance(self._source, (Path, str)):
            path = Path(self._source)
            if not path.is_file():
                raise DatasetError(f"Dataset file not found: {path}")
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line_no, raw_line in enumerate(handle, start=1):
                        stripped = raw_line.strip()
                        if not stripped:
                            continue
                        yield line_no, stripped, True
            except OSError as exc:
                raise DatasetError(f"Failed reading dataset file {path}: {exc}") from exc
            return

        for idx, item in enumerate(self._source, start=1):
            yield idx, item, False

    @staticmethod
    def _validate_item(line_no: int, raw_item: Any, *, is_json_line: bool) -> EvaluationCase:
        if is_json_line:
            try:
                parsed = json.loads(raw_item)
            except json.JSONDecodeError as exc:
                raise DatasetError(
                    f"Invalid JSON at line {line_no}: {exc.msg}",
                    line_number=line_no,
                ) from exc
            if not isinstance(parsed, dict):
                raise DatasetError(
                    f"Dataset line {line_no} must decode to a JSON object",
                    line_number=line_no,
                )
            raw_obj: Any = parsed
        elif isinstance(raw_item, EvaluationCase):
            # Re-validate via model_validate only if needed; preserve strictness cheaply
            return raw_item
        elif isinstance(raw_item, Mapping):
            raw_obj = dict(raw_item)
        else:
            raise DatasetError(
                f"Dataset record {line_no} must be EvaluationCase or Mapping",
                line_number=line_no,
            )

        raw_id = raw_obj.get("id")
        candidate_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None
        try:
            return EvaluationCase.model_validate(raw_obj)
        except ValidationError as exc:
            first_error = exc.errors()[0]
            loc = ".".join(str(part) for part in first_error.get("loc", ())) or None
            raise DatasetError(
                f"Schema validation failed at record {line_no}"
                f"{f' (case {candidate_id!r})' if candidate_id else ''}: {first_error['msg']}",
                line_number=line_no,
                case_id=candidate_id,
                field=loc,
            ) from exc

    def iter_cases(
        self,
        *,
        max_cases: int | None = None,
        on_complete: Callable[[DatasetStreamResult], None] | None = None,
    ) -> Iterator[EvaluationCase]:
        """Stream validated EvaluationCase objects with uniqueness and SHA-256 hashing."""
        if max_cases is not None and max_cases < 1:
            raise DatasetError("max_cases must be >= 1", field="max_cases")

        seen_ids: set[str] = set()
        hasher = StreamingCanonicalHasher()
        capped = False

        for line_no, raw_item, is_json_line in self._iter_source_items():
            if max_cases is not None and hasher.count >= max_cases:
                # 1-line non-blank lookahead confirmed additional unread records exist before EOF
                capped = True
                break

            case = self._validate_item(line_no, raw_item, is_json_line=is_json_line)
            if case.id in seen_ids:
                raise DuplicateCaseIdError(
                    f"Duplicate EvaluationCase.id {case.id!r} at record {line_no}",
                    line_number=line_no,
                    case_id=case.id,
                    field="id",
                )
            seen_ids.add(case.id)
            hasher.update(case.model_dump(mode="json"))
            yield case

        if hasher.count == 0:
            raise EmptyDatasetError("Dataset contains zero valid EvaluationCase records")

        result = DatasetStreamResult(
            dataset_id=self._dataset_id,
            dataset_version=self._dataset_version,
            dataset_fingerprint=hasher.hexdigest(),
            evaluated_case_count=hasher.count,
            dataset_capped=capped,
            max_dataset_cases=max_cases,
        )
        if on_complete is not None:
            on_complete(result)

    def fingerprint(self, *, max_cases: int | None = None) -> DatasetStreamResult:
        """Stream through the dataset and return canonical DatasetStreamResult metadata."""
        captured: list[DatasetStreamResult] = []
        for _ in self.iter_cases(max_cases=max_cases, on_complete=captured.append):
            pass
        return captured[0]

    @classmethod
    def from_docpipe_fixture(
        cls,
        source: Path | str | Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        dataset_id: str | None = None,
        dataset_version: str | None = None,
    ) -> DatasetEngine:
        """Import a docpipe-maestro JSON/JSONL fixture without docpipe installed."""
        from evalforge_maestro.datasets.docpipe_fixture import load_docpipe_fixture

        return load_docpipe_fixture(
            source,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
