# Contract Specification: Rebuildable SQLite Query Index SDK & CLI

**Feature**: `009-sqlite-query-index`  
**Contract Scope**: Public storage & top-level SDK exports (`evalforge_maestro.storage`, `evalforge_maestro`), typed filter/output schemas (`types.py`), and CLI subcommands (`index`, `query`).

## 1. Python SDK Contract

Exported from `evalforge_maestro.storage` and top-level `evalforge_maestro` (`__all__`):
- `SQLiteRunIndex`
- `RunSortOrder`, `RunQueryFilter`, `CaseQueryFilter`
- `IndexedRunSummary`, `IndexedCaseMetricRow`, `IndexedMetricPoint`
- `SQLiteIndexStatus`, `RunQueryPayload`, `CaseQueryPayload`

### `SQLiteRunIndex` Interface
```python
class SQLiteRunIndex:
    def __init__(
        self,
        store: LocalRunStore | Path | str = Path(".evalforge"),
        *,
        db_path: Path | str | None = None,
    ) -> None: ...

    @property
    def store(self) -> LocalRunStore: ...

    @property
    def db_path(self) -> Path: ...

    def status(self) -> SQLiteIndexStatus: ...
    def rebuild(self, *, force: bool = True) -> SQLiteIndexStatus: ...
    def sync(self) -> SQLiteIndexStatus: ...
    def query_runs(
        self,
        filters: RunQueryFilter | None = None,
        *,
        auto_sync: bool = True,
    ) -> list[IndexedRunSummary]: ...
    def query_cases(
        self,
        filters: CaseQueryFilter | None = None,
        *,
        auto_sync: bool = True,
    ) -> list[IndexedCaseMetricRow]: ...
    def metric_history(
        self,
        metric_id: str,
        *,
        dataset_id: str | None = None,
        model_id: str | None = None,
        system_version: str | None = None,
        limit: int = 50,
        auto_sync: bool = True,
    ) -> list[IndexedMetricPoint]: ...
```

### Library Purity & Invariants
- `SQLiteRunIndex` NEVER writes to `.evalforge/runs/`, `manifest.jsonl`, or `baselines.json`.
- Missing canonical `runs/<run_id>.json` referenced by `manifest.jsonl`, or unreadable/invalid canonical JSON, raises `StorageError` (CLI exit code `2`).
- Calling `query_runs`, `query_cases`, or `metric_history` with `auto_sync=False` (`--no-auto-sync`) against a missing or corrupted DB raises `StorageError` (CLI exit code `2`) without creating or modifying disk files.
- Deleting or corrupting `db_path` never affects canonical artifacts; `rebuild()` or `sync()` recreates the DB atomically (`0o600` POSIX permissions, `PRAGMA journal_mode=DELETE`).
- Passing `min_score` / `max_score` on `evalforge-maestro query runs` without `--metric` fails cleanly with exit code `2`.
- `sqlite3` is imported lazily inside DB connection helpers so `import evalforge_maestro` and `evalforge-maestro --help` leave `sqlite3` unloaded.
- `_args_to_cli_overrides` pops `index` and `query` subcommand flags (`index_action`, `query_target`, `db_path`, `no_auto_sync`, filter flags, etc.) cleanly so `CLIResolvedConfig` stays backward-compatible with M5/M6/M8 frozen schemas.

---

## 2. CLI Contracts

### 2.1 `evalforge-maestro index`
```text
evalforge-maestro index <action>
  rebuild [--storage-dir DIR] [--db-path PATH] [--json] [--quiet]
  sync    [--storage-dir DIR] [--db-path PATH] [--json] [--quiet]
  status  [--storage-dir DIR] [--db-path PATH] [--json] [--quiet]
```
- `rebuild`: Reconstructs index DB atomically from canonical JSON; emits `SQLiteIndexStatus` (`--json`) or human summary; exit code `0` (`2` on canonical corruption / invalid path).
- `sync`: Incrementally syncs pending canonical runs & baselines (auto-rebuilding on missing/corrupt DB); emits `SQLiteIndexStatus`; exit code `0`.
- `status`: Non-mutating health check returning `SQLiteIndexStatus` (`exists`, `corrupt`, `in_sync`, `canonical_run_count`, `indexed_run_count`, `pending_run_ids`); exit code `0`.

### 2.2 `evalforge-maestro query`
```text
evalforge-maestro query runs
  [--storage-dir DIR] [--db-path PATH] [--no-auto-sync]
  [--dataset-id ID] [--dataset-version VER] [--run-id ID]...
  [--model-id MODEL] [--system-version VER] [--baseline NAME]
  [--metric METRIC] [--min-score FLOAT] [--max-score FLOAT]
  [--mandatory-failures-only] [--since ISO] [--until ISO]
  [--order-by {timestamp_desc,timestamp_asc,run_id_asc}]
  [--limit INT] [--offset INT] [--json] [--quiet]

evalforge-maestro query cases
  [--storage-dir DIR] [--db-path PATH] [--no-auto-sync]
  [--run-id ID] [--dataset-id ID] [--case-id ID]
  [--metric METRIC] [--status {PASS,FAIL,WARNING,INCONCLUSIVE,NOT_APPLICABLE}]
  [--mandatory-only] [--min-score FLOAT] [--max-score FLOAT]
  [--errors-only] [--anomalies-only]
  [--limit INT] [--offset INT] [--json] [--quiet]
```
- `--json`: Emits canonical `RunQueryPayload` (`query runs`) or `CaseQueryPayload` (`query cases`) to `stdout`.
- Non-`--json` default: Renders readable Markdown table to `stdout` (suppressed when `--quiet`).
- Exit codes: `0` success (including empty matches), `2` invalid filter combination / invalid ISO date / canonical corruption / `StorageError`.
