"""Immutable canonical local storage under .evalforge/ with atomic commits and locking."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from pydantic import ValidationError

from evalforge_maestro._canonical import (
    canonical_json_bytes,
    canonical_json_str,
    redact_secrets,
)
from evalforge_maestro.exceptions import ImmutabilityError, StorageError
from evalforge_maestro.types import CaseEvaluationRecord, RunManifestEntry, RunRecord

_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROCESS_APPEND_LOCK = threading.Lock()


def _validate_run_id(run_id: str) -> str:
    if not _SAFE_RUN_ID_RE.match(run_id) or ".." in run_id:
        raise StorageError(
            f"Invalid run_id {run_id!r}: must match ^[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}$ "
            "and must not contain '..'"
        )
    return run_id


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, 0o700)


@contextmanager
def _locked_file(handle: IO[bytes] | IO[str]) -> Iterator[None]:
    if sys.platform != "win32":
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    else:  # pragma: no cover - Windows fallback
        with _PROCESS_APPEND_LOCK:
            yield


def _locked_append_line(path: Path, line_bytes: bytes) -> None:
    _ensure_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "ab") as handle, _locked_file(handle):
            if os.name == "posix":
                os.chmod(path, 0o600)
            handle.write(line_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StorageError(f"Failed appending to {path}: {exc}") from exc


class LocalRunStore:
    """Persistent store managing checkpoints, immutable run records, and manifest ledger."""

    def __init__(self, root: Path | str = Path(".evalforge")) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        """Return base .evalforge directory path."""
        return self._root

    def checkpoint_path(self, run_id: str) -> Path:
        """Return path to incremental checkpoint journal for run_id."""
        safe_id = _validate_run_id(run_id)
        return self._root / "tmp" / f"{safe_id}.jsonl"

    def run_path(self, run_id: str) -> Path:
        """Return path to immutable RunRecord JSON artifact for run_id."""
        safe_id = _validate_run_id(run_id)
        return self._root / "runs" / f"{safe_id}.json"

    def manifest_path(self) -> Path:
        """Return path to append-only manifest ledger JSONL."""
        return self._root / "manifest.jsonl"

    def append_checkpoint(self, run_id: str, record: CaseEvaluationRecord) -> None:
        """Append one canonical CaseEvaluationRecord line to the incremental temp journal."""
        target = self.checkpoint_path(run_id)
        _ensure_private_dir(self._root)
        payload = redact_secrets(record.model_dump(mode="json"))
        line_bytes = canonical_json_bytes(payload) + b"\n"
        _locked_append_line(target, line_bytes)

    def read_checkpoints(self, run_id: str) -> list[CaseEvaluationRecord]:
        """Read incremental checkpoint records for run_id; returns empty list if none exist."""
        target = self.checkpoint_path(run_id)
        if not target.exists():
            return []
        records: list[CaseEvaluationRecord] = []
        try:
            with target.open("r", encoding="utf-8") as handle:
                for line_no, raw_line in enumerate(handle, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        records.append(CaseEvaluationRecord.model_validate_json(stripped))
                    except (ValidationError, ValueError) as exc:
                        raise StorageError(
                            f"Corrupted checkpoint entry in {target} line {line_no}: {exc}"
                        ) from exc
        except OSError as exc:
            raise StorageError(f"Failed reading checkpoint {target}: {exc}") from exc
        return records

    def remove_checkpoint(self, run_id: str) -> None:
        """Remove incremental checkpoint journal if present."""
        target = self.checkpoint_path(run_id)
        target.unlink(missing_ok=True)

    def save_run(self, record: RunRecord) -> Path:
        """Atomically persist an immutable RunRecord and append its RunManifestEntry."""
        target = self.run_path(record.run_id)
        if target.exists():
            raise ImmutabilityError(
                f"RunRecord {record.run_id!r} already exists at {target}; "
                "historical run artifacts cannot be overwritten."
            )

        _ensure_private_dir(self._root)
        _ensure_private_dir(target.parent)

        sanitized_payload = redact_secrets(record.model_dump(mode="json"))
        raw_bytes = canonical_json_bytes(sanitized_payload, pretty=True)
        tmp_path = target.parent / f".{record.run_id}.{uuid.uuid4().hex}.tmp"

        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name == "posix":
                try:
                    os.link(tmp_path, target)
                except FileExistsError as exc:
                    raise ImmutabilityError(
                        f"RunRecord {record.run_id!r} already exists at {target}"
                    ) from exc
            else:  # pragma: no cover - Windows atomic check-and-rename
                with _PROCESS_APPEND_LOCK:
                    if target.exists():
                        raise ImmutabilityError(
                            f"RunRecord {record.run_id!r} already exists at {target}"
                        )
                    os.replace(tmp_path, target)
        finally:
            tmp_path.unlink(missing_ok=True)

        if os.name == "posix":
            os.chmod(target, 0o600)

        manifest_entry = RunManifestEntry.from_run_record(record)
        manifest_payload = redact_secrets(manifest_entry.model_dump(mode="json"))
        manifest_line = canonical_json_str(manifest_payload).encode("utf-8") + b"\n"
        _locked_append_line(self.manifest_path(), manifest_line)
        return target

    def load_run(self, run_id: str) -> RunRecord:
        """Load and schema-validate a committed RunRecord artifact."""
        target = self.run_path(run_id)
        if not target.is_file():
            raise StorageError(f"RunRecord {run_id!r} not found at {target}")
        try:
            raw = target.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            return RunRecord.model_validate(parsed)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise StorageError(f"Failed loading RunRecord {run_id!r} from {target}: {exc}") from exc

    def read_manifest(self) -> list[RunManifestEntry]:
        """Read all committed RunManifestEntry rows from manifest.jsonl."""
        target = self.manifest_path()
        if not target.exists():
            return []
        entries: list[RunManifestEntry] = []
        try:
            with target.open("r", encoding="utf-8") as handle:
                for line_no, raw_line in enumerate(handle, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        entries.append(RunManifestEntry.model_validate_json(stripped))
                    except (ValidationError, ValueError) as exc:
                        raise StorageError(
                            f"Corrupted manifest entry in {target} line {line_no}: {exc}"
                        ) from exc
        except OSError as exc:
            raise StorageError(f"Failed reading manifest {target}: {exc}") from exc
        return entries
