# Tasks: Rebuildable Local SQLite Query Index (`009-sqlite-query-index`)

**Input**: Design documents from `/specs/009-sqlite-query-index/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/sqlite-index-and-cli.md`

---

## Phase 1: Setup & Library Purity Guards

**Purpose**: Pin cold-start isolation before adding SQLite storage primitives.

- [X] T001 [P] Add `"sqlite3"` to `_HEAVY_OPTIONAL_MODULES` in `tests/test_library_purity.py` so `import evalforge_maestro` and `evalforge-maestro --help` enforce lazy SQLite loading

---

## Phase 2: Foundational Schemas (`types.py`) — Blocking Prerequisite

**Purpose**: Define all strict Pydantic v2 contracts in `src/evalforge_maestro/types.py` (data-model.md §§1.1–1.4) before index or CLI implementation.

- [X] T002 [P] Write strict contract tests in `tests/contract/test_m9_schemas.py` covering `RunSortOrder`, `RunQueryFilter` (`min_mean_score`/`max_mean_score` bounds `0.0..1.0`, bool/NaN rejection, `metric_id` requirement, `since <= until`, `limit`/`offset` bounds), `CaseQueryFilter` (`min_score`/`max_score` bounds `0.0..1.0`, `min_score <= max_score`, `limit`/`offset`), `IndexedRunSummary`, `IndexedCaseMetricRow`, `IndexedMetricPoint`, `SQLiteIndexStatus`, `RunQueryPayload`, and `CaseQueryPayload`
- [X] T003 Implement `RunSortOrder`, `RunQueryFilter`, `CaseQueryFilter`, `IndexedRunSummary`, `IndexedCaseMetricRow`, `IndexedMetricPoint`, `SQLiteIndexStatus`, `RunQueryPayload`, and `CaseQueryPayload` in `src/evalforge_maestro/types.py` citing constraints in `specs/009-sqlite-query-index/data-model.md` (`RunQueryFilter.{min_mean_score,max_mean_score,metric_id,since,until,limit,offset}`, `CaseQueryFilter.{min_score,max_score,limit,offset}`, `IndexedRunSummary.dataset_fingerprint`, `IndexedCaseMetricRow.{score,elapsed_seconds,explanation}`) (depends on T002)

**Checkpoint**: Schema & contract layer complete and passing (`tests/contract/test_m9_schemas.py`, `tests/test_library_purity.py`, `tests/contract/test_m5_schemas.py`, `tests/contract/test_m6_schemas.py`, `tests/contract/test_m8_schemas.py`).

---

## Phase 3: User Story 1 — Atomic Rebuild & Incremental Sync from Canonical Storage (Priority: P1) 🎯 MVP

**Goal**: Implement `SQLiteRunIndex` with atomic full `rebuild()`, incremental `sync()`, non-destructive `status()`, canonical JSON single-source-of-truth preservation, and automatic recovery from deleted/corrupted index DBs.

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/unit/test_sqlite_index.py -k us1 tests/test_library_purity.py` verifying atomic rebuild, `0o700`/`0o600` POSIX permissions, single-file `DELETE` journal mode, incremental sync, deleted/corrupted DB recovery, orphan run discovery, canonical JSON immutability (`@pytest.mark.gate_immutability`), and `StorageError` on missing/corrupted canonical run artifacts.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T004 [P] [US1] Write US1 unit tests in `tests/unit/test_sqlite_index.py` (with `@pytest.mark.gate_immutability`) covering empty stores, `rebuild()` from canonical `.evalforge/runs/*.json` + `manifest.jsonl` + `baselines.json`, `0o600` file permissions without stray WAL/SHM sidecars, `status()` health/stale reporting, `sync()` incremental catch-up on newly committed runs and baseline alias updates, automatic recovery after DB deletion or byte-level corruption, discovery of valid `runs/*.json` files absent from manifest, `StorageError` on corrupted canonical JSON or missing manifest-referenced run JSON, and byte-identical canonical file verification

### Implementation for User Story 1

- [X] T005 [US1] Implement `SQLiteRunIndex` core storage lifecycle (`__init__`, lazy `_sqlite3()` loader, DDL `index_meta`/`runs`/`run_metrics`/`case_results`/`baselines`, uniform `manifest.jsonl ∪ runs/*.json` canonical discovery, `baselines_sha256` staleness tracking, `status()`, atomic temp-DB `rebuild()`, incremental `sync()`) in `src/evalforge_maestro/storage/sqlite_index.py` with `scrub_secret_text` redaction and `0o700`/`0o600` permissions (depends on T001, T003, T004)
- [X] T006 [US1] Export `SQLiteRunIndex` in `src/evalforge_maestro/storage/__init__.py` (depends on T005)

**Checkpoint**: User Story 1 (`SQLiteRunIndex` rebuild/sync/status & canonical immutability) passes independently (**MVP complete**).

---

## Phase 4: User Story 2 — Fast Multi-Criteria Querying Across Runs & Per-Case Outcomes (Priority: P1)

**Goal**: Implement parameterized `query_runs`, `query_cases`, and `metric_history` returning typed Pydantic models with deterministic sorting, pagination, `auto_sync=True` catch-up, SQL injection safety, and 100% parity against scanning canonical JSON artifacts directly.

**Independent Test**: Run `uv run pytest --strict-markers -W error --no-cov tests/unit/test_sqlite_index.py -k us2` covering multi-criteria filtering, sort modes (`timestamp_desc`, `timestamp_asc`, `run_id_asc`), pagination (`limit`, `offset`), baseline filtering, case failure triage (`status`, `mandatory_only`, `has_errors`, `has_anomaly_flags`, `min_score`/`max_score`), `metric_history`, parameterized SQL injection resistance, `auto_sync=False` vs `auto_sync=True`, and `@pytest.mark.gate_determinism` parity against `LocalRunStore.load_runs()`.

### Tests for User Story 2 ⚠️

- [X] T007 [P] [US2] Extend `tests/unit/test_sqlite_index.py` with US2 tests (including `@pytest.mark.gate_determinism`) verifying `query_runs`, `query_cases`, `metric_history`, baseline alias joins, sort orders, pagination, SQL-injection payload neutralization via parameterized bindings, `auto_sync=False` read-only (`?mode=ro`) querying vs `auto_sync=True` auto-recovery, and bit-exact parity against canonical `LocalRunStore.load_runs()`

### Implementation for User Story 2

- [X] T008 [US2] Implement parameterized SQL query builders and mappers (`query_runs` with `EXISTS` baseline filter & sorted `baseline_names`, `query_cases` ordered by `timestamp_epoch DESC, run_id ASC, case_id ASC, metric_id ASC`, `metric_history` returning latest-`limit` chronologically ascending points, read-only URI connection helper `_connect_readonly` failing with `StorageError` when `auto_sync=False` & DB missing/corrupt) in `src/evalforge_maestro/storage/sqlite_index.py` ensuring zero SQL interpolation and secret-scrubbed prose projections (depends on T005, T007)

**Checkpoint**: User Stories 1 and 2 deliver complete SDK index lifecycle and fast typed querying.

---

## Phase 5: User Story 3 — CLI Index Maintenance, Query Subcommands & Comprehensive Docs (Priority: P2)

**Goal**: Expose `evalforge-maestro index {rebuild,sync,status}` and `evalforge-maestro query {runs,cases}`, export all M9 contracts at top-level `evalforge_maestro.__init__`, pin them in `tests/test_api_stability.py`, and author comprehensive user-facing documentation.

**Independent Test**: Run `uv run pytest --strict-markers -W error tests/integration/test_sqlite_index_pipeline.py tests/test_api_stability.py tests/test_library_purity.py` verifying CLI `index`/`query` workflows (`--json`, Markdown table, `--quiet`, `--no-auto-sync`, filters, corrupt-DB recovery, exit code `2` on validation/storage errors), subprocess `--help` cold-start purity with zero `sqlite3` import, and pinned API contracts.

### Tests for User Story 3 ⚠️

- [X] T009 [P] [US3] Write end-to-end integration tests in `tests/integration/test_sqlite_index_pipeline.py` (including `@pytest.mark.gate_determinism` and `@pytest.mark.gate_immutability`) verifying CLI `index status` / `rebuild` / `sync`, `query runs` / `cases` (`--json` `RunQueryPayload`/`CaseQueryPayload`, Markdown table, `--quiet`, `--no-auto-sync`, filter combinations, pagination), recovery after corrupting/deleting `.evalforge/index.sqlite3`, exit code `2` on invalid score/date filters or corrupted canonical store, and subprocess `--help` cold-start isolation (no `sqlite3`)

### Implementation for User Story 3

- [X] T010 [P] [US3] Add `index` (`rebuild`, `sync`, `status`) and `query` (`runs`, `cases`) subparsers cleanly in `src/evalforge_maestro/cli/parser.py` preserving cold-start isolation (zero top-level `storage`/`commands` imports) (depends on T009)
- [X] T011 [US3] Implement `_handle_index`, `_handle_query`, Markdown table renderers, `_args_to_cli_overrides` subcommand key filtering (leaving `CLIResolvedConfig` untouched), and `dispatch_command` routing for `cmd in {"index", "query"}` in `src/evalforge_maestro/cli/commands.py` (depends on T008, T009, T010)
- [X] T012 [P] [US3] Export `SQLiteRunIndex`, `RunSortOrder`, `RunQueryFilter`, `CaseQueryFilter`, `IndexedRunSummary`, `IndexedCaseMetricRow`, `IndexedMetricPoint`, `SQLiteIndexStatus`, `RunQueryPayload`, and `CaseQueryPayload` in `src/evalforge_maestro/__init__.py` (depends on T003, T006)
- [X] T013 [US3] Update `tests/test_api_stability.py` to pin all M9 exports, `SQLiteRunIndex` method signatures, and model fields cleanly without modifying prior M1–M8 contracts (depends on T012)

---

## Phase 6: User-Facing Documentation & Release Gate Verification

**Purpose**: Author thorough, high-quality professional user documentation and validate all repository gates cleanly.

- [X] T014 [P] Write comprehensive user guide `docs/sqlite-index.md` covering canonical-JSON single-source-of-truth architecture, disaster/corruption recovery, normalized SQLite DDL tables, full CLI `index`/`query` reference, Python SDK workflows, and security/permissions guarantees; update `README.md` (CLI commands, Python SDK query recipe, documentation links, M9 summary) and `docs/future-features.md` (promote Feature `009`)
- [X] T015 Execute complete Constitution & CI verification (`uv lock --check`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ruff check --select S src/`, `uv run mypy --strict src tests`, `>=85%` global branch coverage, `100%` branch coverage on `evalforge_maestro.metrics` & `regression.gate`, `-m "gate_determinism or gate_immutability"`, `uv run pip-audit --skip-editable`, `uv build && uv run twine check --strict dist/*`, isolated `--no-dev` wheel install & CLI `index`/`query` smoke check) and clean temporary artifacts

---

## Dependencies & Execution Order

- **Phase 1–2 (`T001`–`T003`)**: Schema & purity foundation (`types.py`, `test_library_purity.py`, `test_m9_schemas.py`).
- **Phase 3 (`US1`, `T004`–`T006`)**: Depends on Phase 2; delivers canonical-derived `SQLiteRunIndex` rebuild/sync/status MVP.
- **Phase 4 (`US2`, `T007`–`T008`)**: Depends on `US1` (`T005`); delivers fast parameterized `query_runs`, `query_cases`, `metric_history`.
- **Phase 5 (`US3`, `T009`–`T013`)**: Depends on `US2` (`T008`); delivers CLI `index`/`query`, top-level SDK exports, and API stability pins.
- **Phase 6 (`T014`–`T015`)**: Final extensive documentation & full CI/packaging gates.
