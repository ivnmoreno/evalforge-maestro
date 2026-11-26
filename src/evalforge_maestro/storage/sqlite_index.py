"""Rebuildable local SQLite read and query index derived from canonical .evalforge JSON."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalforge_maestro._canonical import canonical_sha256, scrub_secret_text
from evalforge_maestro.exceptions import StorageError
from evalforge_maestro.storage.local import (
    LocalRunStore,
    _ensure_private_dir,
    _validate_safe_identifier,
)
from evalforge_maestro.types import (
    BaselineRegistry,
    CaseQueryFilter,
    IndexedCaseMetricRow,
    IndexedMetricPoint,
    IndexedRunSummary,
    MetricStatus,
    RunQueryFilter,
    RunRecord,
    RunSortOrder,
    SQLiteIndexStatus,
)

_INDEX_SCHEMA_VERSION = "1"
_REQUIRED_TABLES = frozenset({"index_meta", "runs", "run_metrics", "case_results", "baselines"})

_DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS index_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        timestamp_iso TEXT NOT NULL,
        timestamp_epoch REAL NOT NULL,
        dataset_id TEXT NOT NULL,
        dataset_version TEXT,
        dataset_fingerprint TEXT NOT NULL,
        evaluated_case_count INTEGER NOT NULL,
        dataset_capped INTEGER NOT NULL,
        system_version TEXT,
        model_id TEXT,
        config_fingerprint TEXT,
        has_mandatory_failures INTEGER NOT NULL,
        mandatory_failed_case_ids_json TEXT NOT NULL,
        status_counts_json TEXT NOT NULL,
        package_version TEXT NOT NULL,
        run_sha256 TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_metrics (
        run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        metric_id TEXT NOT NULL,
        metric_version TEXT NOT NULL,
        mean_score REAL,
        applicable_count INTEGER NOT NULL,
        pass_count INTEGER NOT NULL,
        fail_count INTEGER NOT NULL,
        warning_count INTEGER NOT NULL,
        inconclusive_count INTEGER NOT NULL,
        not_applicable_count INTEGER NOT NULL,
        PRIMARY KEY (run_id, metric_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS case_results (
        run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        case_id TEXT NOT NULL,
        metric_id TEXT NOT NULL,
        metric_version TEXT NOT NULL,
        status TEXT NOT NULL,
        score REAL,
        mandatory INTEGER NOT NULL,
        elapsed_seconds REAL NOT NULL,
        has_errors INTEGER NOT NULL,
        anomaly_count INTEGER NOT NULL,
        explanation TEXT NOT NULL,
        PRIMARY KEY (run_id, case_id, metric_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baselines (
        baseline_name TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        pinned_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_dataset_ts ON runs(dataset_id, timestamp_epoch DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model_id)",
    "CREATE INDEX IF NOT EXISTS idx_run_metrics_metric_score ON run_metrics(metric_id, mean_score)",
    "CREATE INDEX IF NOT EXISTS idx_case_results_metric_status ON case_results(metric_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_case_results_case ON case_results(case_id, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_baselines_run_id ON baselines(run_id)",
)

_RUN_WHERE_SQL = """
WHERE (? IS NULL OR r.dataset_id = ?)
  AND (? IS NULL OR r.dataset_version = ?)
  AND (? IS NULL OR r.run_id IN (SELECT value FROM json_each(?)))
  AND (? IS NULL OR r.model_id = ?)
  AND (? IS NULL OR r.system_version = ?)
  AND (? IS NULL OR EXISTS (
        SELECT 1 FROM baselines b
        WHERE b.run_id = r.run_id AND b.baseline_name = ?
      ))
  AND (? IS NULL OR EXISTS (
        SELECT 1 FROM run_metrics rm
        WHERE rm.run_id = r.run_id
          AND rm.metric_id = ?
          AND (? IS NULL OR rm.mean_score >= ?)
          AND (? IS NULL OR rm.mean_score <= ?)
      ))
  AND (? IS NULL OR r.has_mandatory_failures = ?)
  AND (? IS NULL OR r.timestamp_epoch >= ?)
  AND (? IS NULL OR r.timestamp_epoch <= ?)
"""

_RUN_SELECT_COLUMNS = """
SELECT r.run_id,
       r.timestamp_iso,
       r.dataset_id,
       r.dataset_version,
       r.dataset_fingerprint,
       r.evaluated_case_count,
       r.dataset_capped,
       r.system_version,
       r.model_id,
       r.config_fingerprint,
       r.has_mandatory_failures,
       r.mandatory_failed_case_ids_json,
       r.status_counts_json
FROM runs r
"""

_RUN_QUERIES: dict[RunSortOrder, str] = {
    RunSortOrder.TIMESTAMP_DESC: (
        _RUN_SELECT_COLUMNS
        + _RUN_WHERE_SQL
        + "ORDER BY r.timestamp_epoch DESC, r.run_id ASC LIMIT ? OFFSET ?"
    ),
    RunSortOrder.TIMESTAMP_ASC: (
        _RUN_SELECT_COLUMNS
        + _RUN_WHERE_SQL
        + "ORDER BY r.timestamp_epoch ASC, r.run_id ASC LIMIT ? OFFSET ?"
    ),
    RunSortOrder.RUN_ID_ASC: (
        _RUN_SELECT_COLUMNS + _RUN_WHERE_SQL + "ORDER BY r.run_id ASC LIMIT ? OFFSET ?"
    ),
}

_CASE_QUERY_SQL = """
SELECT cr.run_id,
       r.timestamp_iso,
       r.dataset_id,
       r.model_id,
       r.system_version,
       cr.case_id,
       cr.metric_id,
       cr.metric_version,
       cr.status,
       cr.score,
       cr.mandatory,
       cr.elapsed_seconds,
       cr.has_errors,
       cr.anomaly_count,
       cr.explanation
FROM case_results cr
JOIN runs r ON r.run_id = cr.run_id
WHERE (? IS NULL OR cr.run_id = ?)
  AND (? IS NULL OR r.dataset_id = ?)
  AND (? IS NULL OR cr.case_id = ?)
  AND (? IS NULL OR cr.metric_id = ?)
  AND (? IS NULL OR cr.status = ?)
  AND (? = 0 OR cr.mandatory = 1)
  AND (? IS NULL OR cr.score >= ?)
  AND (? IS NULL OR cr.score <= ?)
  AND (? IS NULL OR cr.has_errors = ?)
  AND (? IS NULL OR (CASE WHEN cr.anomaly_count > 0 THEN 1 ELSE 0 END) = ?)
ORDER BY r.timestamp_epoch DESC, cr.run_id ASC, cr.case_id ASC, cr.metric_id ASC
LIMIT ? OFFSET ?
"""

_METRIC_HISTORY_SQL = """
SELECT rm.metric_id,
       r.run_id,
       r.timestamp_iso,
       r.dataset_id,
       r.model_id,
       r.system_version,
       rm.mean_score,
       rm.applicable_count,
       rm.pass_count,
       rm.fail_count
FROM run_metrics rm
JOIN runs r ON r.run_id = rm.run_id
WHERE rm.metric_id = ?
  AND (? IS NULL OR r.dataset_id = ?)
  AND (? IS NULL OR r.model_id = ?)
  AND (? IS NULL OR r.system_version = ?)
ORDER BY r.timestamp_epoch DESC, r.run_id DESC
LIMIT ?
"""


def _lazy_sqlite3() -> Any:
    """Import stdlib sqlite3 lazily so CLI `--help` and package import remain sqlite-free."""
    import sqlite3

    return sqlite3


class SQLiteRunIndex:
    """Rebuildable local SQLite read/query index backed strictly by canonical JSON artifacts."""

    def __init__(
        self,
        store: LocalRunStore | Path | str = Path(".evalforge"),
        *,
        db_path: Path | str | None = None,
    ) -> None:
        self._store = store if isinstance(store, LocalRunStore) else LocalRunStore(store)
        self._db_path = (
            Path(db_path) if db_path is not None else (self._store.root / "index.sqlite3")
        )
        if self._db_path.exists() and self._db_path.is_dir():
            raise StorageError(f"SQLite index path cannot be a directory: {self._db_path}")

    @property
    def store(self) -> LocalRunStore:
        """Return underlying canonical LocalRunStore."""
        return self._store

    @property
    def db_path(self) -> Path:
        """Return derived SQLite index file path."""
        return self._db_path

    def _discover_canonical(self) -> tuple[list[str], BaselineRegistry, str]:
        """Collect canonical run IDs (manifest order + extra runs/*.json) and baselines hash."""
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for entry in self._store.read_manifest():
            run_path = self._store.run_path(entry.run_id)
            if not run_path.is_file():
                raise StorageError(
                    f"Canonical RunRecord {entry.run_id!r} referenced in manifest.jsonl "
                    f"was not found at {run_path}"
                )
            if entry.run_id not in seen:
                seen.add(entry.run_id)
                ordered_ids.append(entry.run_id)

        runs_dir = self._store.root / "runs"
        if runs_dir.is_dir():
            for candidate in sorted(runs_dir.glob("*.json")):
                if candidate.name.startswith(".") or not candidate.is_file():
                    continue
                run_id = _validate_safe_identifier(candidate.stem, label="run_id")
                if run_id not in seen:
                    seen.add(run_id)
                    ordered_ids.append(run_id)

        baselines = self._store.load_baselines()
        baselines_sha = canonical_sha256(baselines.model_dump(mode="json"))
        return ordered_ids, baselines, baselines_sha

    @contextmanager
    def _open_conn(self, *, readonly: bool) -> Iterator[Any]:
        sqlite3 = _lazy_sqlite3()
        try:
            if readonly:
                uri = f"file:{self._db_path.resolve()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True)
            else:
                conn = sqlite3.connect(str(self._db_path))
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            raise StorageError(f"Failed opening SQLite index at {self._db_path}: {exc}") from exc

        try:
            yield conn
        finally:
            conn.close()

    def _insert_run_record(self, conn: Any, record: RunRecord, *, run_sha256: str) -> None:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, timestamp_iso, timestamp_epoch, dataset_id, dataset_version,
                dataset_fingerprint, evaluated_case_count, dataset_capped,
                system_version, model_id, config_fingerprint, has_mandatory_failures,
                mandatory_failed_case_ids_json, status_counts_json, package_version, run_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.timestamp.isoformat(),
                record.timestamp.timestamp(),
                record.dataset_id,
                record.dataset_version,
                record.dataset_fingerprint,
                record.evaluated_case_count,
                int(record.dataset_capped),
                record.system_version,
                record.model_id,
                record.config_fingerprint,
                int(record.has_mandatory_failures),
                json.dumps(record.mandatory_failed_case_ids, ensure_ascii=False),
                json.dumps(
                    {k.value: v for k, v in record.status_counts.items()}, ensure_ascii=False
                ),
                record.package_version,
                run_sha256,
            ),
        )
        metric_rows = [
            (
                record.run_id,
                metric_id,
                summary.metric_version,
                summary.mean_score,
                summary.applicable_count,
                summary.pass_count,
                summary.fail_count,
                summary.warning_count,
                summary.inconclusive_count,
                summary.not_applicable_count,
            )
            for metric_id, summary in record.aggregates.items()
        ]
        conn.executemany(
            """
            INSERT INTO run_metrics (
                run_id, metric_id, metric_version, mean_score, applicable_count,
                pass_count, fail_count, warning_count, inconclusive_count, not_applicable_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            metric_rows,
        )
        case_rows = [
            (
                record.run_id,
                case_rec.case_id,
                metric_id,
                metric_res.metric_version,
                metric_res.status.value,
                metric_res.score,
                int(case_rec.mandatory),
                case_rec.execution.elapsed_seconds,
                int(bool(case_rec.execution.errors)),
                len(metric_res.anomaly_flags),
                scrub_secret_text(metric_res.explanation),
            )
            for case_rec in record.case_results
            for metric_id, metric_res in case_rec.metrics.items()
        ]
        conn.executemany(
            """
            INSERT INTO case_results (
                run_id, case_id, metric_id, metric_version, status, score,
                mandatory, elapsed_seconds, has_errors, anomaly_count, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            case_rows,
        )

    def _replace_baselines(
        self,
        conn: Any,
        registry: BaselineRegistry,
        *,
        baselines_sha: str,
    ) -> None:
        conn.execute("DELETE FROM baselines")
        baseline_rows = [
            (name, entry.run_id, entry.pinned_at.isoformat())
            for name, entry in sorted(registry.baselines.items())
        ]
        conn.executemany(
            "INSERT INTO baselines (baseline_name, run_id, pinned_at) VALUES (?, ?, ?)",
            baseline_rows,
        )
        now_iso = datetime.now(UTC).isoformat()
        conn.executemany(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            [
                ("index_schema_version", _INDEX_SCHEMA_VERSION),
                ("baselines_sha256", baselines_sha),
                ("last_synced_at", now_iso),
            ],
        )

    def _load_canonical_run_with_hash(self, run_id: str) -> tuple[RunRecord, str]:
        record = self._store.load_run(run_id)
        raw_bytes = self._store.run_path(run_id).read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        return record, digest

    def status(self) -> SQLiteIndexStatus:
        """Inspect SQLite index health, schema version, and canonical parity without writing."""
        if self._db_path.exists() and self._db_path.is_dir():
            raise StorageError(f"SQLite index path cannot be a directory: {self._db_path}")

        canonical_ids, baselines, baselines_sha = self._discover_canonical()
        canonical_count = len(canonical_ids)
        baseline_count = len(baselines.baselines)

        if not self._db_path.exists():
            return SQLiteIndexStatus(
                db_path=str(self._db_path),
                exists=False,
                corrupt=False,
                in_sync=canonical_count == 0 and baseline_count == 0,
                index_schema_version=_INDEX_SCHEMA_VERSION,
                db_size_bytes=0,
                canonical_run_count=canonical_count,
                indexed_run_count=0,
                baseline_count=baseline_count,
                pending_run_ids=list(canonical_ids),
                stale_reason="Index file does not exist yet" if canonical_ids else None,
            )

        db_size = self._db_path.stat().st_size
        sqlite3 = _lazy_sqlite3()
        try:
            with self._open_conn(readonly=True) as conn:
                check_row = conn.execute("PRAGMA quick_check(1)").fetchone()
                if check_row is None or check_row[0] != "ok":
                    raise sqlite3.DatabaseError("quick_check failed")
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not _REQUIRED_TABLES.issubset(tables):
                    raise sqlite3.DatabaseError("missing required index tables")

                meta = dict(conn.execute("SELECT key, value FROM index_meta").fetchall())
                schema_ver = meta.get("index_schema_version", "")
                if schema_ver != _INDEX_SCHEMA_VERSION:
                    return SQLiteIndexStatus(
                        db_path=str(self._db_path),
                        exists=True,
                        corrupt=False,
                        in_sync=False,
                        index_schema_version=schema_ver or "unknown",
                        db_size_bytes=db_size,
                        canonical_run_count=canonical_count,
                        indexed_run_count=0,
                        baseline_count=baseline_count,
                        pending_run_ids=list(canonical_ids),
                        stale_reason=f"Index schema version mismatch ({schema_ver!r})",
                    )

                indexed_ids = [row[0] for row in conn.execute("SELECT run_id FROM runs").fetchall()]
                indexed_set = set(indexed_ids)
                canonical_set = set(canonical_ids)
                pending = [rid for rid in canonical_ids if rid not in indexed_set]
                extra = sorted(indexed_set - canonical_set)
                recorded_base_sha = meta.get("baselines_sha256")
                baselines_stale = recorded_base_sha != baselines_sha
                in_sync = not pending and not extra and not baselines_stale

                reason: str | None = None
                if pending:
                    reason = f"{len(pending)} canonical run(s) pending indexing"
                elif extra:
                    reason = f"{len(extra)} indexed run(s) absent from canonical store"
                elif baselines_stale:
                    reason = "Canonical baselines.json updated since last sync"

                return SQLiteIndexStatus(
                    db_path=str(self._db_path),
                    exists=True,
                    corrupt=False,
                    in_sync=in_sync,
                    index_schema_version=_INDEX_SCHEMA_VERSION,
                    db_size_bytes=db_size,
                    canonical_run_count=canonical_count,
                    indexed_run_count=len(indexed_ids),
                    baseline_count=baseline_count,
                    pending_run_ids=pending,
                    extra_indexed_run_ids=extra,
                    stale_reason=reason,
                )
        except (sqlite3.Error, StorageError) as exc:
            return SQLiteIndexStatus(
                db_path=str(self._db_path),
                exists=True,
                corrupt=True,
                in_sync=False,
                index_schema_version=_INDEX_SCHEMA_VERSION,
                db_size_bytes=db_size,
                canonical_run_count=canonical_count,
                indexed_run_count=0,
                baseline_count=baseline_count,
                pending_run_ids=list(canonical_ids),
                stale_reason=f"Corrupt or unreadable SQLite index: {exc}",
            )

    def rebuild(self, *, force: bool = True) -> SQLiteIndexStatus:
        """Atomically reconstruct the SQLite index from canonical JSON artifacts only."""
        _ = force  # Explicit API contract compatibility; full rebuild always replaces atomically.
        canonical_ids, baselines, baselines_sha = self._discover_canonical()
        loaded = [self._load_canonical_run_with_hash(rid) for rid in canonical_ids]

        _ensure_private_dir(self._db_path.parent)
        tmp_path = self._db_path.parent / f".{self._db_path.name}.{uuid.uuid4().hex}.tmp"
        sqlite3 = _lazy_sqlite3()

        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            conn = sqlite3.connect(str(tmp_path))
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.execute("PRAGMA foreign_keys=ON")
                for stmt in _DDL_STATEMENTS:
                    conn.execute(stmt)
                for record, digest in loaded:
                    self._insert_run_record(conn, record, run_sha256=digest)
                self._replace_baselines(conn, baselines, baselines_sha=baselines_sha)
                conn.commit()
            finally:
                conn.close()

            if os.name == "posix":
                os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._db_path)
            if os.name == "posix":
                os.chmod(self._db_path, 0o600)
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"Failed rebuilding SQLite index at {self._db_path}: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        return self.status()

    def sync(self) -> SQLiteIndexStatus:
        """Incrementally index pending runs and baseline changes, rebuilding if corrupt."""
        current = self.status()
        if current.in_sync and current.exists and not current.corrupt:
            return current

        if (
            not current.exists
            or current.corrupt
            or current.index_schema_version != _INDEX_SCHEMA_VERSION
            or current.extra_indexed_run_ids
        ):
            return self.rebuild()

        _, baselines, baselines_sha = self._discover_canonical()
        loaded_pending = [
            self._load_canonical_run_with_hash(rid) for rid in current.pending_run_ids
        ]
        sqlite3 = _lazy_sqlite3()
        try:
            with self._open_conn(readonly=False) as conn:
                for record, digest in loaded_pending:
                    self._insert_run_record(conn, record, run_sha256=digest)
                self._replace_baselines(conn, baselines, baselines_sha=baselines_sha)
                conn.commit()
            if os.name == "posix":
                os.chmod(self._db_path, 0o600)
        except sqlite3.Error as exc:
            raise StorageError(f"Failed incremental SQLite sync at {self._db_path}: {exc}") from exc

        return self.status()

    def _ensure_query_ready(self, *, auto_sync: bool) -> None:
        if auto_sync:
            self.sync()
            return
        st = self.status()
        if not st.exists or st.corrupt:
            raise StorageError(
                f"SQLite index at {self._db_path} is missing or corrupt with auto_sync=False; "
                "run `evalforge-maestro index rebuild` first."
            )

    def _hydrate_run_details(
        self, conn: Any, run_ids: Sequence[str]
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, float | None]]]:
        baselines_by_run: dict[str, list[str]] = {rid: [] for rid in run_ids}
        scores_by_run: dict[str, dict[str, float | None]] = {rid: {} for rid in run_ids}
        if not run_ids:
            return baselines_by_run, scores_by_run

        ids_json = json.dumps(list(run_ids), ensure_ascii=False)
        for run_id, b_name in conn.execute(
            "SELECT run_id, baseline_name FROM baselines "
            "WHERE run_id IN (SELECT value FROM json_each(?)) ORDER BY baseline_name ASC",
            (ids_json,),
        ).fetchall():
            baselines_by_run.setdefault(run_id, []).append(str(b_name))

        for run_id, metric_id, mean_score in conn.execute(
            "SELECT run_id, metric_id, mean_score FROM run_metrics "
            "WHERE run_id IN (SELECT value FROM json_each(?)) ORDER BY metric_id ASC",
            (ids_json,),
        ).fetchall():
            scores_by_run.setdefault(run_id, {})[str(metric_id)] = (
                float(mean_score) if mean_score is not None else None
            )

        return baselines_by_run, scores_by_run

    def query_runs(
        self,
        filters: RunQueryFilter | None = None,
        *,
        auto_sync: bool = True,
    ) -> list[IndexedRunSummary]:
        """Query indexed runs matching filters with parameterized SQLite bindings."""
        f = filters or RunQueryFilter()
        self._ensure_query_ready(auto_sync=auto_sync)

        run_ids_json = json.dumps(f.run_ids, ensure_ascii=False) if f.run_ids is not None else None
        since_epoch = f.since.timestamp() if f.since is not None else None
        until_epoch = f.until.timestamp() if f.until is not None else None
        mand_int = int(f.has_mandatory_failures) if f.has_mandatory_failures is not None else None

        params = (
            f.dataset_id,
            f.dataset_id,
            f.dataset_version,
            f.dataset_version,
            run_ids_json,
            run_ids_json,
            f.model_id,
            f.model_id,
            f.system_version,
            f.system_version,
            f.baseline_name,
            f.baseline_name,
            f.metric_id,
            f.metric_id,
            f.min_mean_score,
            f.min_mean_score,
            f.max_mean_score,
            f.max_mean_score,
            mand_int,
            mand_int,
            since_epoch,
            since_epoch,
            until_epoch,
            until_epoch,
            f.limit,
            f.offset,
        )

        sqlite3 = _lazy_sqlite3()
        try:
            with self._open_conn(readonly=True) as conn:
                rows = conn.execute(_RUN_QUERIES[f.order_by], params).fetchall()
                returned_ids = [str(row[0]) for row in rows]
                baselines_map, scores_map = self._hydrate_run_details(conn, returned_ids)
        except sqlite3.Error as exc:
            raise StorageError(f"Failed executing SQLite query_runs: {exc}") from exc

        results: list[IndexedRunSummary] = []
        for row in rows:
            run_id = str(row[0])
            raw_status_counts = json.loads(str(row[12]))
            status_counts = {MetricStatus(k): int(v) for k, v in raw_status_counts.items()}
            results.append(
                IndexedRunSummary(
                    run_id=run_id,
                    timestamp=datetime.fromisoformat(str(row[1])),
                    dataset_id=str(row[2]),
                    dataset_version=str(row[3]) if row[3] is not None else None,
                    dataset_fingerprint=str(row[4]),
                    evaluated_case_count=int(row[5]),
                    dataset_capped=bool(row[6]),
                    system_version=str(row[7]) if row[7] is not None else None,
                    model_id=str(row[8]) if row[8] is not None else None,
                    config_fingerprint=str(row[9]) if row[9] is not None else None,
                    has_mandatory_failures=bool(row[10]),
                    mandatory_failed_case_ids=[str(cid) for cid in json.loads(str(row[11]))],
                    baseline_names=baselines_map.get(run_id, []),
                    aggregate_scores=scores_map.get(run_id, {}),
                    status_counts=status_counts,
                )
            )
        return results

    def query_cases(
        self,
        filters: CaseQueryFilter | None = None,
        *,
        auto_sync: bool = True,
    ) -> list[IndexedCaseMetricRow]:
        """Query indexed per-case metric evaluations matching typed filters."""
        f = filters or CaseQueryFilter()
        self._ensure_query_ready(auto_sync=auto_sync)

        status_str = f.status.value if f.status is not None else None
        mandatory_flag = 1 if f.mandatory_only else 0
        errors_int = int(f.has_errors) if f.has_errors is not None else None
        anomaly_int = int(f.has_anomaly_flags) if f.has_anomaly_flags is not None else None

        params = (
            f.run_id,
            f.run_id,
            f.dataset_id,
            f.dataset_id,
            f.case_id,
            f.case_id,
            f.metric_id,
            f.metric_id,
            status_str,
            status_str,
            mandatory_flag,
            f.min_score,
            f.min_score,
            f.max_score,
            f.max_score,
            errors_int,
            errors_int,
            anomaly_int,
            anomaly_int,
            f.limit,
            f.offset,
        )

        sqlite3 = _lazy_sqlite3()
        try:
            with self._open_conn(readonly=True) as conn:
                rows = conn.execute(_CASE_QUERY_SQL, params).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed executing SQLite query_cases: {exc}") from exc

        return [
            IndexedCaseMetricRow(
                run_id=str(row[0]),
                timestamp=datetime.fromisoformat(str(row[1])),
                dataset_id=str(row[2]),
                model_id=str(row[3]) if row[3] is not None else None,
                system_version=str(row[4]) if row[4] is not None else None,
                case_id=str(row[5]),
                metric_id=str(row[6]),
                metric_version=str(row[7]),
                status=MetricStatus(str(row[8])),
                score=float(row[9]) if row[9] is not None else None,
                mandatory=bool(row[10]),
                elapsed_seconds=float(row[11]),
                has_errors=bool(row[12]),
                anomaly_count=int(row[13]),
                explanation=str(row[14]),
            )
            for row in rows
        ]

    def metric_history(
        self,
        metric_id: str,
        *,
        dataset_id: str | None = None,
        model_id: str | None = None,
        system_version: str | None = None,
        limit: int = 50,
        auto_sync: bool = True,
    ) -> list[IndexedMetricPoint]:
        """Return the latest `limit` chronological metric summary points ordered ascending."""
        cleaned_metric = metric_id.strip()
        if not cleaned_metric:
            raise StorageError("metric_id must be a non-empty string")
        if isinstance(limit, bool) or limit < 1:
            raise StorageError(f"limit must be an integer >= 1, got {limit!r}")

        self._ensure_query_ready(auto_sync=auto_sync)
        params = (
            cleaned_metric,
            dataset_id,
            dataset_id,
            model_id,
            model_id,
            system_version,
            system_version,
            limit,
        )
        sqlite3 = _lazy_sqlite3()
        try:
            with self._open_conn(readonly=True) as conn:
                rows = conn.execute(_METRIC_HISTORY_SQL, params).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed executing SQLite metric_history: {exc}") from exc

        points = [
            IndexedMetricPoint(
                metric_id=str(row[0]),
                run_id=str(row[1]),
                timestamp=datetime.fromisoformat(str(row[2])),
                dataset_id=str(row[3]),
                model_id=str(row[4]) if row[4] is not None else None,
                system_version=str(row[5]) if row[5] is not None else None,
                mean_score=float(row[6]) if row[6] is not None else None,
                applicable_count=int(row[7]),
                pass_count=int(row[8]),
                fail_count=int(row[9]),
            )
            for row in rows
        ]
        points.reverse()
        return points


__all__ = ["SQLiteRunIndex"]
