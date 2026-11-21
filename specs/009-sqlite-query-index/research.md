# Research & Architectural Decisions: Feature 009 (`009-sqlite-query-index`)

**Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

## Decisions Resolved

1. **Journal Mode & Atomic Single-File Replacement (`DELETE` vs `WAL`)**
   - **Decision**: Use `PRAGMA journal_mode=DELETE` during temporary index construction, close the temporary connection cleanly, verify permissions (`0o600`), and swap atomically via `os.replace(tmp_db, db_path)`. For read-only queries (`auto_sync=False`), open with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` when `path` is a normal file.
   - **Rationale**: `WAL` creates auxiliary `-wal` and `-shm` sidecar files whose POSIX permissions can drift from `0o600` or fail on read-only mounts. `DELETE` mode + atomic temp-file swap produces one single self-contained `.evalforge/index.sqlite3` file with deterministic `0o600` permissions and zero partial-write states on crash.

2. **Lazy Stdlib `sqlite3` Loading for Cold-Start Purity**
   - **Decision**: Import `sqlite3` inside `SQLiteRunIndex` connection helpers rather than at module top level in `storage/sqlite_index.py`, and add `"sqlite3"` to `_HEAVY_OPTIONAL_MODULES` in `tests/test_library_purity.py`.
   - **Rationale**: `evalforge_maestro.__init__` re-exports `SQLiteRunIndex` cleanly without opening `sqlite3` C extensions on every `import evalforge_maestro` or `evalforge-maestro --help` invocation.

3. **Canonical Source Discovery (`manifest.jsonl` + `runs/*.json` + `baselines.json`)**
   - **Decision**: Treat canonical `runs/<run_id>.json`, `manifest.jsonl`, and `baselines.json` via `LocalRunStore` as the sole source of truth:
     - Read `manifest.jsonl` order first; validate every manifest `run_id` has its corresponding canonical `runs/<run_id>.json` (raising `StorageError` rather than silently hiding corrupted/deleted canonical run files).
     - During `rebuild()`, also scan `runs/*.json` (ignoring hidden `.*.tmp` files) sorted lexicographically for any valid committed `RunRecord` not yet reflected in `manifest.jsonl`, ensuring full disaster recovery.
     - Refresh `baselines` table cleanly from `baselines.json` on every `rebuild()` and `sync()`.
   - **Rationale**: Guarantees bit-exact parity with canonical storage and allows deleting or corrupting `.evalforge/index.sqlite3` with full recovery via `rebuild()`.

4. **Automatic Corruption / Schema-Mismatch Recovery**
   - **Decision**: Maintain an `index_meta` key/value table storing `index_schema_version = "1"` and canonical sync metadata. When `sync()` sees missing DB, unreadable/corrupt SQLite (`sqlite3.DatabaseError`), missing tables, or mismatched `index_schema_version`, it automatically falls back to atomic `rebuild()`, while `status()` reports `corrupt=True` / `in_sync=False` non-destructively!
   - **Rationale**: Operators inspecting `index status` see exact diagnostic state (`corrupt=True`, `missing_canonical_run_ids`, `pending_run_ids`) without silent mutation, while `index rebuild` or `sync()` restores health cleanly.

5. **Zero Auto-Write Coupled into `LocalRunStore.save_run`**
   - **Decision**: Leave `LocalRunStore.save_run` focused strictly on immutable JSON/manifest persistence (`runs/*.json`, `manifest.jsonl`). Indexing runs via explicit `SQLiteRunIndex.rebuild()`/`sync()`, CLI `evalforge-maestro index ...`, or automatic read-through sync (`auto_sync=True` on `SQLiteRunIndex` query methods).
   - **Rationale**: Preserves zero overhead and zero side effects on `LocalRunStore` / `EvaluationOrchestrator` and ensures all existing immutability & storage invariants remain untouched.
