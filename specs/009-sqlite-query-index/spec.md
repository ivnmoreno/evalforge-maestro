# Feature Specification: Rebuildable Local SQLite Query Index

**Feature Branch**: `009-sqlite-query-index`  
**Created**: 2026-11-21  
**Status**: Draft  
**Input**: User description: "Rebuildable local SQLite read and query index built strictly from immutable canonical .evalforge/runs/<run_id>.json and manifest.jsonl artifacts, retaining canonical JSON as the single source of truth."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Atomic Rebuild & Incremental Sync from Canonical Storage (Priority: P1)

As an evaluation engineer with dozens or hundreds of committed runs under `.evalforge/runs/*.json`, I want a local SQLite query index (`SQLiteRunIndex`) that can be atomically rebuilt from scratch or incrementally synced strictly from canonical JSON artifacts (`runs/<run_id>.json`, `manifest.jsonl`, `baselines.json`), so that querying historical runs never compromises canonical immutability or treats SQLite as a system of record.

**Why this priority**: Retaining canonical JSON as the single source of truth is a non-negotiable architectural invariant. Before any querying or CLI commands can rely on SQLite, the rebuild/sync engine must prove it derives 100% of its state from canonical files, recovers transparently if `.evalforge/index.sqlite3` is deleted or corrupted, and never mutates `.evalforge/runs/`, `manifest.jsonl`, or `baselines.json`.

**Independent Test**: Run `uv run pytest tests/unit/test_sqlite_index.py -k us1` covering atomic full rebuild (`rebuild()`), incremental `sync()`, identical state after deleting or corrupting the SQLite file and rebuilding, orphan `.evalforge/runs/<run_id>.json` discovery, `0o700`/`0o600` permissions, `StorageError` on tampered/corrupted canonical JSON, and verification that canonical files remain byte-for-byte unchanged (`@pytest.mark.gate_immutability`).

**Acceptance Scenarios**:

1. **Given** an `.evalforge/` directory containing committed `RunRecord` JSON files, `manifest.jsonl`, and pinned baselines in `baselines.json`, **When** a caller invokes `SQLiteRunIndex(root).rebuild()`, **Then** a self-contained SQLite database is constructed in a temporary file under `0o600` permissions and atomically committed via `os.replace` to `.evalforge/index.sqlite3`, returning a `SQLiteIndexStatus` reporting `in_sync=True`, exact `indexed_run_count`, `canonical_run_count`, and zero mutations to canonical JSON files.
2. **Given** an existing `.evalforge/index.sqlite3` that is manually deleted or overwritten with garbage bytes, **When** `rebuild()` or `sync()` runs, **Then** the corrupted/missing index is transparently recovered into an identical queryable index matching every field of the canonical JSON artifacts.
3. **Given** an indexed store to which two new runs are committed via `LocalRunStore.save_run`, **When** `sync()` is invoked, **Then** only newly added runs (plus updated baseline pointers) are indexed without reprocessing unchanged historical runs, while `in_sync` transitions from `False` to `True`.

---

### User Story 2 - Fast Multi-Criteria Querying Across Runs & Per-Case Outcomes (Priority: P1)

As an ML Engineer investigating regressions and failure slices, I want typed query methods (`query_runs`, `query_cases`, `metric_history`) supporting structured filtering by dataset, model version, system version, baseline alias, metric ID, score bounds, evaluation status, mandatory failure flag, anomaly presence, and UTC date ranges, so I can pinpoint regressions and failing test cases across historical runs in milliseconds without deserializing every full `RunRecord` JSON file manually.

**Why this priority**: Fast, structured, multi-dimensional slicing across historical runs and per-case outcomes is the primary user value of indexing `.evalforge/` artifacts.

**Independent Test**: Run `uv run pytest tests/unit/test_sqlite_index.py -k us2` verifying typed Pydantic query filters (`RunQueryFilter`, `CaseQueryFilter`), deterministic ordering/pagination (`limit`, `offset`), parameterized bindings against SQL-injection-like filter strings, secret/PII hygiene, `auto_sync=True` catch-up querying, and 100% result parity against scanning canonical `LocalRunStore.load_runs()` directly (`@pytest.mark.gate_determinism`).

**Acceptance Scenarios**:

1. **Given** multiple indexed runs spanning different `dataset_id`, `model_id`, `system_version`, metrics, and mandatory failures, **When** calling `query_runs(RunQueryFilter(dataset_id=..., model_id=..., metric_id=..., min_mean_score=..., has_mandatory_failures=...))`, **Then** only matching `IndexedRunSummary` records are returned in deterministic order with exact 6-decimal-rounded scores and baseline tag annotations.
2. **Given** indexed per-case metric evaluations and execution errors across multiple runs, **When** calling `query_cases(CaseQueryFilter(metric_id="precision_at_k", status=MetricStatus.FAIL, mandatory_only=True))`, **Then** exact `IndexedCaseMetricRow` entries are returned identifying every affected `(run_id, case_id)` pair, score, status, anomaly flag count, and scrubbed explanation/error summary.
3. **Given** untrusted user strings containing SQL metacharacters (`'; DROP TABLE runs; --`) passed into filter fields, **When** querying runs or cases, **Then** parameterized SQLite bindings treat all inputs strictly as literal values without error or table mutation.

---

### User Story 3 - CLI Index Maintenance & Query Subcommands (`index`, `query`) (Priority: P2)

As a developer or CI operator, I want `evalforge-maestro index` (`rebuild`, `sync`, `status`) and `evalforge-maestro query` (`runs`, `cases`) CLI subcommands supporting `--storage-dir`, filter flags, `--json` canonical JSON output, and clean Markdown/table output on `stdout`, while preserving sub-second cold-start `--help` purity and strict POSIX exit codes.

**Why this priority**: Exposing index lifecycle and run/case querying through the standard `evalforge-maestro` CLI unlocks shell scripting, Makefile targets, and quick local triage without writing Python code.

**Independent Test**: Run `uv run pytest --strict-markers -W error tests/integration/test_sqlite_index_pipeline.py tests/test_api_stability.py tests/test_library_purity.py` verifying CLI `index status` / `rebuild` / `sync`, CLI `query runs` / `cases` (`--json`, Markdown table, `--quiet`, pagination, filter flags, empty-store handling), deleted/corrupted DB recovery via CLI, exit code `2` on invalid filters/missing storage errors, and subprocess `--help` cold-start isolation.

**Acceptance Scenarios**:

1. **Given** an `.evalforge` directory with persisted runs and no SQLite index yet, **When** running `evalforge-maestro query runs --storage-dir ... --dataset-id ... --json`, **Then** the command auto-syncs the rebuildable index cleanly (unless `--no-auto-sync` is passed) and emits a schema-validated `RunQueryPayload` JSON object on `stdout` with exit code `0`.
2. **Given** an operator running `evalforge-maestro index status --json`, **When** a new canonical run has been committed since the last index build, **Then** status reports `exists=True`, `in_sync=False`, `indexed_run_count < canonical_run_count`, and `stale_reason` explaining which run IDs are pending.
3. **Given** `evalforge-maestro index rebuild --json`, **When** executed after `.evalforge/index.sqlite3` was tampered with, **Then** the database is atomically rebuilt from canonical JSON and returns exit code `0` with `in_sync=True`.

---

### Edge Cases

- What happens when `.evalforge/` does not exist yet or contains zero committed runs?
  - `status()` returns `exists=False`, `in_sync=True`, `canonical_run_count=0`, `indexed_run_count=0`; `rebuild()` creates a valid empty indexed schema (`indexed_run_count=0`); `query_runs()` and `query_cases()` return empty result lists cleanly.
- What happens when `.evalforge/runs/<run_id>.json` exists on disk without a matching `manifest.jsonl` entry (or `manifest.jsonl` references a run whose `.json` file is missing)?
  - Missing `runs/<run_id>.json` referenced by `manifest.jsonl` raises `StorageError` during `status()`/`rebuild()`/`sync()` (refusing silent partial corruption); extra valid `<run_id>.json` files in `runs/` are discovered cleanly in deterministic order during `status()`, `sync()`, and `rebuild()` and indexed alongside manifest runs.
- What happens when `query_runs`/`query_cases`/`metric_history` is called with `auto_sync=False` (`--no-auto-sync`) while `.evalforge/index.sqlite3` is missing or corrupted?
  - Raises `StorageError` explicitly (mapping to CLI exit code `2`) rather than silently falling back or creating an index on disk.

## Clarifications

### Session 2026-11-21

- **Canonical Discovery Across `status`, `sync`, and `rebuild`**: All three operations MUST discover canonical runs identically as the ordered union of `manifest.jsonl` entries plus any extra `runs/*.json` files (excluding hidden/temp files), raising `StorageError` if any manifest-referenced `runs/<run_id>.json` is missing.
- **Baseline Staleness Detection**: `SQLiteRunIndex` tracks `baselines_sha256` alongside indexed run IDs in `index_meta` so `pin_baseline(..., overwrite=True)` or `unpin_baseline(...)` immediately marks `status().in_sync = False` and refreshes on `sync()`.
- **Deterministic Query Ordering**: `query_cases` MUST order rows deterministically by `(timestamp_epoch DESC, run_id ASC, case_id ASC, metric_id ASC)`. `metric_history` returns the latest `limit` matching runs ordered chronologically ascending `(timestamp_epoch ASC, run_id ASC)`.
- **Non-Intrusive Canonical Writes**: `LocalRunStore.save_run` and `evalforge-maestro run` remain decoupled from SQLite so canonical persistence performance and M1–M8 immutability invariants stay untouched; index population occurs via `rebuild()`, `sync()`, CLI `index`, or default `auto_sync=True` on queries.
- What happens when `.evalforge/baselines.json` is added, updated (`overwrite=True`), or deleted?
  - Baseline names pinned to each `run_id` are derived dynamically from canonical `baselines.json` and refreshed on every `sync()` or `rebuild()`, so unpinned/re-pinned aliases are always accurate without recreating run rows.
- What happens when `evalforge-maestro --help` or `import evalforge_maestro` runs?
  - Neither triggers SQLite connections, filesystem I/O, or heavy optional imports (`litellm`, `docpipe_maestro`, `numpy`, `scipy`, `opentelemetry`).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define strict Pydantic v2 models in `src/evalforge_maestro/types.py` for index status (`SQLiteIndexStatus`), run query filters (`RunQueryFilter`), case query filters (`CaseQueryFilter`), indexed run summaries (`IndexedRunSummary`), indexed case metric rows (`IndexedCaseMetricRow`), metric time-series points (`IndexedMetricPoint`), and CLI JSON query responses (`RunQueryPayload`, `CaseQueryPayload`), all carrying explicit `schema_version` where persisted/interchanged.
- **FR-002**: System MUST implement `SQLiteRunIndex` in `src/evalforge_maestro/storage/sqlite_index.py` (exported from `evalforge_maestro.storage` and `evalforge_maestro`) backed strictly by Python's stdlib `sqlite3` with zero external DB/ORM dependencies.
- **FR-003**: System MUST treat `.evalforge/runs/<run_id>.json`, `.evalforge/manifest.jsonl`, and `.evalforge/baselines.json` as the sole canonical source of truth; `SQLiteRunIndex` MUST NEVER modify or delete canonical JSON files and MUST commit index builds atomically via a temporary database file under `0o600` POSIX permissions (`0o700` parent directory) with `os.replace`.
- **FR-004**: `SQLiteRunIndex.rebuild()` MUST reconstruct the SQLite database completely from canonical storage even if `.evalforge/index.sqlite3` is missing, stale, schema-mismatched, or corrupted, without requiring prior index state.
- **FR-005**: `SQLiteRunIndex.sync()` MUST incrementally index newly committed canonical runs and update baseline alias mappings, falling back automatically to an atomic full rebuild if the database is missing, unreadable, corrupted, or uses an incompatible index schema version.
- **FR-006**: `SQLiteRunIndex.query_runs(filters=...)` MUST support filtering by `dataset_id`, `dataset_version`, `run_ids`, `model_id`, `system_version`, `baseline_name`, `metric_id` with optional `min_mean_score` / `max_mean_score`, `has_mandatory_failures`, `since`, `until`, `order_by` (`timestamp_desc`, `timestamp_asc`, `run_id_asc`), `limit`, and `offset`.
- **FR-007**: `SQLiteRunIndex.query_cases(filters=...)` MUST support filtering by `run_id`, `dataset_id`, `case_id`, `metric_id`, `status` (`MetricStatus`), `mandatory_only`, `min_score` / `max_score`, `has_errors`, `has_anomaly_flags`, `limit`, and `offset`, returning deterministic sorted `IndexedCaseMetricRow` results.
- **FR-008**: `SQLiteRunIndex.metric_history(...)` MUST return chronological `IndexedMetricPoint` series for a given `metric_id` filtered optionally by `dataset_id`, `model_id`, `system_version`, and `limit`.
- **FR-009**: All SQL statements MUST use parameterized placeholders; filter inputs MUST be validated through Pydantic models and NEVER interpolated into SQL strings. Any indexed prose (explanations, error messages) MUST remain secret-redacted (`redact_secrets` / `scrub_secret_text`).
- **FR-010**: CLI MUST expose `evalforge-maestro index {rebuild,sync,status}` and `evalforge-maestro query {runs,cases}` subcommands in `cli/parser.py` and `cli/commands.py` with `--json`, `--quiet`, `--storage-dir`, and typed filters, preserving exit codes (`0` success, `2` storage/config/filter validation fault) and cold-start `--help` isolation.
- **FR-011**: System MUST document the SQLite query index, rebuildability guarantees, schema design, CLI commands, and SDK usage thoroughly in user-facing documentation (`docs/sqlite-index.md`, `README.md`, and `docs/future-features.md`).

### Key Entities *(include if feature involves data)*

- **`SQLiteRunIndex`**: Rebuildable read/query index bound to a `LocalRunStore` (or `.evalforge` root path) and optional custom DB path (defaulting to `<root>/index.sqlite3`).
- **`SQLiteIndexStatus`**: Schema-versioned health/sync snapshot reporting `db_path`, `exists`, `corrupt`, `in_sync`, `index_schema_version`, `canonical_run_count`, `indexed_run_count`, `pending_run_ids`, `missing_canonical_run_ids`, and `baseline_count`.
- **`RunQueryFilter` & `IndexedRunSummary`**: Typed run filter and summary contract projecting canonical `RunRecord` metadata, dataset fingerprint, config fingerprints, aggregate metric scores, status counts, mandatory failure count, and pinned baseline names.
- **`CaseQueryFilter` & `IndexedCaseMetricRow`**: Typed per-case metric filter and row contract projecting `(run_id, case_id, metric_id, status, score, mandatory, elapsed_seconds, has_errors, anomaly_count, explanation)`.
- **`IndexedMetricPoint`**: Typed chronological metric trend point (`run_id`, `timestamp`, `dataset_id`, `model_id`, `system_version`, `mean_score`, `applicable_count`, `pass_count`, `fail_count`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Deleting or corrupting `.evalforge/index.sqlite3` and invoking `SQLiteRunIndex.rebuild()` (or `evalforge-maestro index rebuild`) restores 100% identical query outputs across `query_runs`, `query_cases`, and `metric_history` compared to the pre-deletion index while canonical `runs/*.json`, `manifest.jsonl`, and `baselines.json` hashes remain bit-identical.
- **SC-002**: Query results returned by `SQLiteRunIndex.query_runs` and `SQLiteRunIndex.query_cases` match direct in-memory filtering of canonical `LocalRunStore.load_runs()` 100% across multi-run, multi-metric, multi-dataset fixtures.
- **SC-003**: `evalforge-maestro --help` and `import evalforge_maestro` keep all optional heavy modules unloaded (`sys.modules`) and complete cleanly without opening or creating `.evalforge/index.sqlite3`.
- **SC-004**: All automated repository gates pass cleanly (`uv lock --check`, `ruff format --check`, `ruff check`, Bandit `S`, `mypy --strict src tests`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` and `regression.gate`, determinism/immutability markers, `pip-audit`, `uv build && twine check --strict`, and isolated wheel smoke test).

## Assumptions

- `SQLiteRunIndex` defaults its database file path to `<storage_dir>/index.sqlite3` unless an explicit `db_path` override is supplied, keeping canonical `.evalforge/` layout predictable and isolated.
- Indexed tables store materialized summary columns needed for fast SQL filtering/sorting rather than duplicating entire multi-megabyte trace payloads; full `ExecutionResult.trace` remains in canonical `.evalforge/runs/<run_id>.json` loadable via `LocalRunStore.load_run(run_id)`.
- Because the index is strictly derived and rebuildable, `EvalForgeError` / `StorageError` cleanly covers unreadable/corrupt canonical JSON or invalid custom DB paths (mapping to CLI exit code `2`).
