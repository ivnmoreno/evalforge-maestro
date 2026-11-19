"""Offline ReplayAdapter serving pre-captured ExecutionResult traces by case_id."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalforge_maestro.adapters._shared import redact_adapter_config
from evalforge_maestro.exceptions import AdapterError, DatasetError
from evalforge_maestro.types import EvaluationCase, ExecutionResult, RunRecord


class ReplayAdapter:
    """TargetAdapter serving pre-captured ExecutionResult objects deterministically."""

    def __init__(
        self,
        executions: Sequence[ExecutionResult] | Mapping[str, ExecutionResult],
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config_fingerprint: str | None = None,
    ) -> None:
        mapping: dict[str, ExecutionResult] = {}
        if isinstance(executions, Mapping):
            for key, item in executions.items():
                if not isinstance(item, ExecutionResult):
                    raise AdapterError(
                        "ReplayAdapter mapping values must be ExecutionResult instances"
                    )
                if key != item.case_id:
                    raise AdapterError(
                        f"ReplayAdapter key {key!r} does not match ExecutionResult.case_id "
                        f"{item.case_id!r}"
                    )
                mapping[key] = item
        else:
            for idx, item in enumerate(executions, start=1):
                if not isinstance(item, ExecutionResult):
                    raise AdapterError(
                        f"ReplayAdapter entry {idx} must be an ExecutionResult instance"
                    )
                if item.case_id in mapping:
                    raise AdapterError(
                        f"Duplicate case_id {item.case_id!r} in ReplayAdapter executions"
                    )
                mapping[item.case_id] = item

        if not mapping:
            raise AdapterError("ReplayAdapter requires at least one captured ExecutionResult")

        self._executions = mapping
        first = next(iter(mapping.values()))
        self._system_version = (
            system_version if system_version is not None else first.system_version
        )
        self._model_id = model_id if model_id is not None else first.model_id
        if config_fingerprint is not None:
            self._config_fingerprint: str | None = config_fingerprint
        elif first.config_fingerprint is not None:
            self._config_fingerprint = first.config_fingerprint
        else:
            fp, _ = redact_adapter_config({"replay_case_count": len(mapping)})
            self._config_fingerprint = fp

    @classmethod
    def from_file(
        cls,
        path: Path | str,
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config_fingerprint: str | None = None,
    ) -> ReplayAdapter:
        """Load pre-captured ExecutionResult traces from JSONL, JSON array, or RunRecord JSON."""
        target = Path(path)
        if not target.is_file():
            raise DatasetError(f"Execution replay file not found: {target}")
        try:
            raw_text = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise DatasetError(f"Failed reading execution replay file {target}: {exc}") from exc

        stripped_all = raw_text.strip()
        if not stripped_all:
            raise DatasetError(f"Execution replay file {target} contains zero execution records")

        results: list[ExecutionResult] = []
        if stripped_all.startswith("["):
            try:
                parsed_list: Any = json.loads(stripped_all)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"Invalid JSON in execution file {target}: {exc.msg}") from exc
            if not isinstance(parsed_list, list):
                raise DatasetError(f"Expected JSON array in {target}")
            for idx, item in enumerate(parsed_list, start=1):
                try:
                    results.append(ExecutionResult.model_validate(item))
                except (ValidationError, ValueError) as exc:
                    raise DatasetError(
                        f"Invalid ExecutionResult at index {idx} in {target}: {exc}",
                        line_number=idx,
                    ) from exc
        else:
            is_single_run_record = False
            try:
                single_obj: Any = json.loads(stripped_all)
                if isinstance(single_obj, dict) and "case_results" in single_obj:
                    is_single_run_record = True
            except json.JSONDecodeError:
                is_single_run_record = False

            if is_single_run_record:
                try:
                    run_record = RunRecord.model_validate(single_obj)
                except (ValidationError, ValueError) as exc:
                    raise DatasetError(f"Invalid RunRecord JSON in {target}: {exc}") from exc
                results = [case_rec.execution for case_rec in run_record.case_results]
                if system_version is None:
                    system_version = run_record.system_version
                if model_id is None:
                    model_id = run_record.model_id
                if config_fingerprint is None:
                    config_fingerprint = run_record.config_fingerprint
            else:
                for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise DatasetError(
                            f"Invalid JSON in {target} line {line_no}: {exc.msg}",
                            line_number=line_no,
                        ) from exc
                    try:
                        results.append(ExecutionResult.model_validate(parsed))
                    except (ValidationError, ValueError) as exc:
                        raise DatasetError(
                            f"Invalid ExecutionResult in {target} line {line_no}: {exc}",
                            line_number=line_no,
                        ) from exc

        if not results:
            raise DatasetError(f"Execution replay file {target} contains zero execution records")

        try:
            return cls(
                results,
                system_version=system_version,
                model_id=model_id,
                config_fingerprint=config_fingerprint,
            )
        except AdapterError as exc:
            raise DatasetError(str(exc)) from exc

    @property
    def case_ids(self) -> frozenset[str]:
        """Return set of available pre-captured case identifiers."""
        return frozenset(self._executions)

    @property
    def system_version(self) -> str | None:
        """Return optional target system version."""
        return self._system_version

    @property
    def model_id(self) -> str | None:
        """Return optional target model identifier."""
        return self._model_id

    @property
    def config_fingerprint(self) -> str | None:
        """Return redacted target configuration fingerprint."""
        return self._config_fingerprint

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Serve pre-captured ExecutionResult for case.id or fail explicitly if absent."""
        record = self._executions.get(case.id)
        if record is None:
            raise AdapterError(
                f"ReplayAdapter has no pre-captured ExecutionResult for case_id {case.id!r}"
            )
        return record
