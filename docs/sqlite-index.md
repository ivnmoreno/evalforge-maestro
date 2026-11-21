# Rebuildable Local SQLite Query Index Guide

`evalforge-maestro` includes an optional, zero-dependency local SQLite read and query index (`SQLiteRunIndex`) designed for sub-second filtering, regression triage, and metric history lookups across large `.evalforge/` artifact stores—while strictly preserving canonical `.evalforge/runs/<run_id>.json`, `manifest.jsonl`, and `baselines.json` files as the **immutable single source of truth**.

---

## 1. Architectural Guarantee: Derived Cache, Never System of Record

| Invariant | Behavior in `evalforge-maestro` |
| --- | --- |
| **Canonical Source of Truth** | `.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`, and `.evalforge/baselines.json` remain the sole authoritative artifacts. `SQLiteRunIndex` never creates, edits, or deletes canonical JSON files. |
| **Non-Intrusive Writes** | `LocalRunStore.save_run()` and `evalforge-maestro run` do not touch SQLite. Indexing occurs lazily on demand (`query` with default `auto_sync=True`) or explicitly (`evalforge-maestro index sync` / `rebuild`). |
| **Disaster & Corruption Recovery** | Deleting or corrupting `.evalforge/index.sqlite3` loses **zero** evaluation data. Running `index rebuild` (or `sync()` / any auto-syncing `query`) reconstructs the exact index atomically from canonical JSON. |
| **Single-File Atomic Commit** | Full rebuilds write to a hidden temporary database under `PRAGMA journal_mode=DELETE` (`0o600` file, `0o700` dir) and commit via `os.replace`, leaving no `-wal`/`-shm` sidecars and preventing partial writes on crash. |
| **Cold-Start Purity** | Stdlib `sqlite3` is loaded lazily only when an index connection opens; `import evalforge_maestro` and `evalforge-maestro --help` leave `sqlite3` out of `sys.modules`. |
| **Zero SQL Interpolation** | Every SQL filter query (`query_runs`, `query_cases`, `metric_history`) uses static SQL skeletons and bound `?` / `json_each(?)` parameters evaluated via Pydantic v2 filter models (`RunQueryFilter`, `CaseQueryFilter`). |
| **Secret Hygiene** | Indexed explanations and errors pass through `scrub_secret_text(...)`, preventing credential leakage inside indexed rows. |

---

## 2. Canonical Discovery & Sync Mechanics

1. **Run Discovery (`manifest.jsonl ∪ runs/*.json`)**:
   - Reads `manifest.jsonl` first and verifies every referenced `runs/<run_id>.json` exists (raising `StorageError` rather than silently hiding corrupted/deleted canonical run files).
   - Discovers any additional valid `<run_id>.json` files inside `.evalforge/runs/` (ignoring hidden temp files) in deterministic sorted order.
2. **Baseline Parity (`baselines_sha256`)**:
   - Tracks a canonical SHA-256 digest of `baselines.json` inside `index_meta`.
   - Pinning (`baseline set --overwrite`) or deleting a baseline immediately marks `status().in_sync = False` (`stale_reason = "Canonical baselines.json updated since last sync"`), refreshing cleanly during the next `sync()`.
3. **Corruption & Schema Mismatch Handling**:
   - `index status` performs non-mutating `PRAGMA quick_check(1)`, checks required tables (`index_meta`, `runs`, `run_metrics`, `case_results`, `baselines`), and verifies `index_schema_version == "1"`.
   - If the database file is corrupted or schema-mismatched, `status()` reports `corrupt=True, in_sync=False` without modifying disk, while `rebuild()` or `sync()` atomically replaces it from canonical storage.
4. **Opt-Out Auto-Sync (`--no-auto-sync` / `auto_sync=False`)**:
   - When `auto_sync=True` (default), `query_runs`, `query_cases`, and `metric_history` call `sync()` automatically before opening a read-only SQLite URI (`?mode=ro`).
   - Passing `--no-auto-sync` (or `auto_sync=False`) enforces strict read-only querying and fails loudly with `StorageError` (CLI exit code `2`) if `.evalforge/index.sqlite3` is missing or corrupt.

---

## 3. Relational Index Schema (`index_schema_version = "1"`)

`<storage_dir>/index.sqlite3` maintains five normalized tables:
- **`index_meta(key, value)`**: Stores `index_schema_version`, `baselines_sha256`, and `last_synced_at`.
- **`runs(...)`**: Run-level provenance (`run_id`, `timestamp_iso`, `timestamp_epoch`, `dataset_id`, `dataset_version`, `dataset_fingerprint`, `evaluated_case_count`, `dataset_capped`, `system_version`, `model_id`, `config_fingerprint`, `has_mandatory_failures`, `mandatory_failed_case_ids_json`, `status_counts_json`, `package_version`, `run_sha256`).
- **`run_metrics(run_id, metric_id, ...)`**: Aggregate per-metric summaries (`mean_score`, `applicable_count`, `pass_count`, `fail_count`, `warning_count`, `inconclusive_count`, `not_applicable_count`).
- **`case_results(run_id, case_id, metric_id, ...)`**: Per-case metric evaluations (`status`, `score`, `mandatory`, `elapsed_seconds`, `has_errors`, `anomaly_count`, scrubbed `explanation`). Full execution traces (`ExecutionResult.trace`, retrieved chunks, raw tool arguments) remain solely in canonical `.evalforge/runs/<run_id>.json` and can be fetched via `LocalRunStore.load_run(run_id)` after finding target `run_id`s in the index.
- **`baselines(baseline_name, run_id, pinned_at)`**: Current baseline alias pointers mirrored from `.evalforge/baselines.json`.

---

## 4. CLI Reference (`index` & `query`)

### 4.1 Index Maintenance (`evalforge-maestro index`)

```bash
# Inspect health and sync parity without writing to disk
evalforge-maestro index status --storage-dir .evalforge --json

# Rebuild SQLite index atomically from canonical JSON artifacts
evalforge-maestro index rebuild --storage-dir .evalforge --json

# Incrementally sync only new runs and updated baselines (auto-rebuilds if corrupt)
evalforge-maestro index sync --storage-dir .evalforge --json
```

Options shared across `rebuild`, `sync`, and `status`:
- `--storage-dir DIR`: Root directory containing `runs/`, `manifest.jsonl`, and `baselines.json` (default: `.evalforge`).
- `--db-path PATH`: Optional override path for the SQLite index file (default: `<storage_dir>/index.sqlite3`).
- `--json`: Emit schema-validated `SQLiteIndexStatus` JSON to `stdout`.
- `--quiet`: Suppress default text status output.

### 4.2 Querying Runs (`evalforge-maestro query runs`)

Filter and paginate `IndexedRunSummary` records across datasets, models, baselines, metric score bounds, and ISO-8601 UTC date windows:

```bash
evalforge-maestro query runs \
  --storage-dir .evalforge \
  --dataset-id support-qa \
  --model-id glm-5.3 \
  --metric exact_match \
  --min-score 0.80 \
  --order-by timestamp_desc \
  --limit 20 \
  --json
```

Available flags:
- `--dataset-id ID`, `--dataset-version VER`, `--run-id ID` *(repeatable)*, `--model-id MODEL`, `--system-version VER`, `--baseline NAME`
- `--metric METRIC`, `--min-score FLOAT`, `--max-score FLOAT` *(requires `--metric`)*
- `--mandatory-failures-only`
- `--since ISO-8601`, `--until ISO-8601`
- `--order-by {timestamp_desc,timestamp_asc,run_id_asc}`
- `--limit INT` (`1..1000`, default `50`), `--offset INT` (`>= 0`, default `0`)
- `--no-auto-sync`, `--db-path PATH`, `--json`, `--quiet`

### 4.3 Triaging Per-Case Evaluations (`evalforge-maestro query cases`)

Pinpoint failing, errored, or anomalous case evaluations across historical runs:

```bash
evalforge-maestro query cases \
  --storage-dir .evalforge \
  --dataset-id support-qa \
  --metric precision_at_k \
  --status FAIL \
  --mandatory-only \
  --anomalies-only \
  --json
```

Available flags:
- `--run-id ID`, `--dataset-id ID`, `--case-id ID`, `--metric METRIC`
- `--status {PASS,FAIL,WARNING,INCONCLUSIVE,NOT_APPLICABLE}`
- `--mandatory-only`, `--errors-only`, `--anomalies-only`
- `--min-score FLOAT`, `--max-score FLOAT`
- `--limit INT` (`1..5000`, default `100`), `--offset INT` (`>= 0`, default `0`)
- `--no-auto-sync`, `--db-path PATH`, `--json`, `--quiet`

Both `query runs` and `query cases` exit with `0` on valid queries (including zero matches) and `2` on invalid filter combinations, invalid ISO timestamps, missing index under `--no-auto-sync`, or corrupted canonical JSON.

---

## 5. Python SDK Workflows

```python
from datetime import datetime, timezone
from evalforge_maestro import (
    CaseQueryFilter,
    LocalRunStore,
    MetricStatus,
    RunQueryFilter,
    RunSortOrder,
    SQLiteRunIndex,
)

store = LocalRunStore(".evalforge")
index = SQLiteRunIndex(store)

# 1. Explicit rebuild or status check
status = index.rebuild()
print(f"Indexed {status.indexed_run_count} canonical runs -> {status.db_path}")

# 2. Query runs matching model, score floor, and date range
recent_runs = index.query_runs(
    RunQueryFilter(
        dataset_id="support-qa",
        model_id="glm-5.3",
        metric_id="exact_match",
        min_mean_score=0.75,
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
        order_by=RunSortOrder.TIMESTAMP_DESC,
        limit=25,
    )
)

# 3. Triage failing mandatory cases and inspect full canonical trace when needed
failures = index.query_cases(
    CaseQueryFilter(
        dataset_id="support-qa",
        status=MetricStatus.FAIL,
        mandatory_only=True,
        has_errors=True,
    )
)
for row in failures:
    full_run = store.load_run(row.run_id)
    case_rec = next(c for c in full_run.case_results if c.case_id == row.case_id)
    print(row.run_id, row.case_id, row.explanation, case_rec.execution.errors)

# 4. Extract chronological metric trend series directly from the index
history = index.metric_history("exact_match", dataset_id="support-qa", limit=30)
for pt in history:
    print(pt.timestamp.isoformat(), pt.run_id, pt.mean_score)
```
