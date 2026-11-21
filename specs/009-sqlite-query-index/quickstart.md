# Quickstart & Validation Scenarios: Feature 009 (`009-sqlite-query-index`)

## 1. Python SDK: Rebuild, Delete/Corrupt Recovery & Multi-Criteria Queries

```python
from pathlib import Path
from evalforge_maestro import (
    CaseQueryFilter,
    LocalRunStore,
    MetricStatus,
    RunQueryFilter,
    SQLiteRunIndex,
)

store = LocalRunStore(".evalforge")
index = SQLiteRunIndex(store)

# Atomic initial build from canonical .evalforge/runs/*.json + manifest.jsonl
status = index.rebuild()
assert status.in_sync and status.indexed_run_count == status.canonical_run_count

# Filter failing mandatory cases across runs
failed_cases = index.query_cases(
    CaseQueryFilter(metric_id="precision_at_k", status=MetricStatus.FAIL, mandatory_only=True)
)

# Delete or corrupt SQLite file; canonical JSON restores identical query results cleanly
Path(status.db_path).write_bytes(b"corrupted-header")
rebuilt = index.rebuild()
assert rebuilt.in_sync and not rebuilt.corrupt
assert (
    index.query_cases(
        CaseQueryFilter(metric_id="precision_at_k", status=MetricStatus.FAIL, mandatory_only=True)
    )
    == failed_cases
)
```

## 2. CLI: Index Lifecycle & Query Triage

```bash
# Inspect sync health before/after committed runs
evalforge-maestro index status --storage-dir .evalforge --json

# Rebuild index atomically from canonical artifacts
evalforge-maestro index rebuild --storage-dir .evalforge --json

# Query runs filtered by dataset, model, and metric score threshold
evalforge-maestro query runs --storage-dir .evalforge --dataset-id ci-ds --metric exact_match --min-score 0.8 --json

# Triage failing or anomalous cases across runs
evalforge-maestro query cases --storage-dir .evalforge --status FAIL --mandatory-only --json
```
