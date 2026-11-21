# Implementation Plan: Rebuildable Local SQLite Query Index

**Branch**: `009-sqlite-query-index` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/009-sqlite-query-index/spec.md`

## Summary

Implement `SQLiteRunIndex` in `src/evalforge_maestro/storage/sqlite_index.py` plus Pydantic v2 query/status contracts in `src/evalforge_maestro/types.py`, exposing atomic full rebuild (`rebuild()`), incremental catch-up sync (`sync()`), non-destructive diagnostics (`status()`), parameterized indexed queries (`query_runs`, `query_cases`, `metric_history`), and CLI `index` / `query` subcommands while strictly keeping `.evalforge/runs/<run_id>.json`, `manifest.jsonl`, and `baselines.json` as the immutable single source of truth.

## Technical Context

**Language/Version**: Python 3.10+ (`3.13` local runtime, `mypy --strict`, `from __future__ import annotations`)  
**Primary Dependencies**: Stdlib `sqlite3` (lazy import on DB operations), `pydantic>=2.0` (existing core dep)  
**Storage**: Derived local SQLite index at `<storage_dir>/index.sqlite3` (`0o600` file, `0o700` dir, `PRAGMA journal_mode=DELETE`, atomic `os.replace` swap) built solely from canonical JSON artifacts  
**Testing**: `pytest --strict-markers -W error --cov-branch`, `tests/contract/test_m9_schemas.py`, `tests/unit/test_sqlite_index.py`, `tests/integration/test_sqlite_index_pipeline.py`, `tests/test_api_stability.py`, `tests/test_library_purity.py`  
**Target Platform**: Linux / macOS / Windows cross-OS (`os.replace`, platform-safe perms)  
**Project Type**: Library + CLI (`evalforge_maestro` / `evalforge-maestro`)  
**Performance Goals**: Sub-50ms SQL queries over indexed runs/cases without full `RunRecord` deserialization; sub-second `--help` cold-start with zero `sqlite3` import  
**Constraints**: Zero mutations to canonical `.evalforge/` JSON artifacts, zero SQL string interpolation, zero new external runtime dependencies, `>=85%` global branch coverage (`100%` preserved on `metrics` and `regression.gate`)  
**Scale/Scope**: Workstation & CI `.evalforge/` stores with tens to thousands of runs and tens of thousands of case evaluations

## Constitution Check

*GATE: Passed pre-research and post-design against `.specify/memory/constitution.md` Principles I–VII.*

- **Principle I (Scope Tiebreaker)**: Passes. EvalForge never runs a primary system-of-record database; `.evalforge/runs/*.json`, `manifest.jsonl`, and `baselines.json` stay authoritative, and SQLite is a strictly derived, deletable/rebuildable read/query cache.
- **Principle II (Library Purity & Unidirectional Dependencies)**: Passes. `storage/sqlite_index.py` imports only `types`, `exceptions`, `_canonical`, `storage.local`, and stdlib (`sqlite3` imported lazily inside DB connection methods). Zero imports from `cli`, `adapters`, `metrics`, `judges`, `regression`, `execution`, or heavy optional modules. `cli/parser.py` imports zero `cli/commands.py` / `storage` at module top level. `"sqlite3"` added to `_HEAVY_OPTIONAL_MODULES` in `test_library_purity.py`.
- **Principle III (Single Schema Source of Truth)**: Passes. All filter, result, point, status, and CLI payload contracts live in `src/evalforge_maestro/types.py` with `SCHEMA_VERSION`. Zero untyped dict cross-boundary returns.
- **Principle IV (Evidence-Aware & Anomaly-Safe)**: Passes. `IndexedCaseMetricRow` and `CaseQueryFilter` preserve `mandatory`, `anomaly_count`, `has_errors`, and explanations cleanly across case-level queries.
- **Principle V (Immutable Artifacts & Determinism)**: Passes. Atomic rebuild via temp DB + `os.replace`; read-only queries use `?mode=ro`; deterministic sort orders (`timestamp_desc`, `timestamp_asc`, `run_id_asc`) and parity verified under `@pytest.mark.gate_immutability` and `@pytest.mark.gate_determinism`.
- **Principle VI (Stream & Secret Hygiene)**: Passes. All persisted run artifacts are already scrubbed, explanations/errors pass through `scrub_secret_text` on index build/read, CLI `--json` writes one schema-validated JSON payload to `stdout`, and logs emit only to `stderr` (`NullHandler` in library).
- **Principle VII (Automated Quality Gates)**: Passes. Enforces `ruff`, Bandit `S` checks, `mypy --strict`, `>=85%` global branch coverage, `100%` branch coverage on `metrics` and `regression.gate`, `pip-audit`, `uv build && twine check --strict`, and isolated `--no-dev` wheel checks.

## Project Structure

### Documentation (this feature)

```text
specs/009-sqlite-query-index/
├── spec.md                              # Feature specification (US1-US3)
├── checklists/requirements.md           # Spec quality validation checklist
├── plan.md                              # This implementation plan
├── research.md                          # SQLite journal mode, recovery, & lazy-import decisions
├── data-model.md                        # Pydantic contracts & normalized SQLite DDL schema
├── quickstart.md                        # SDK & CLI verification quickstart
└── contracts/
    └── sqlite-index-and-cli.md          # SDK signatures, CLI flags & invariants
```

### Source Code & Documentation Targets

```text
src/evalforge_maestro/
├── types.py                             # RunSortOrder, RunQueryFilter, CaseQueryFilter, IndexedRunSummary, IndexedCaseMetricRow, IndexedMetricPoint, SQLiteIndexStatus, RunQueryPayload, CaseQueryPayload
├── storage/
│   ├── __init__.py                      # Export SQLiteRunIndex alongside LocalRunStore
│   └── sqlite_index.py                  # Rebuildable SQLiteRunIndex implementation (lazy sqlite3)
├── cli/
│   ├── parser.py                        # `index {rebuild,sync,status}` & `query {runs,cases}` subparsers
│   └── commands.py                      # `_handle_index`, `_handle_query`, `dispatch_command` routing
└── __init__.py                          # Top-level SDK re-exports & sorted __all__

docs/
├── sqlite-index.md                      # Detailed SQLite query index guide (architecture, recovery, DDL, CLI, SDK)
├── future-features.md                   # Update shipped status for Feature 009
README.md                                # Document `index`/`query` CLI commands, SDK recipes, & docs link

tests/
├── contract/test_m9_schemas.py          # Strict schema, filter, rounding, & JSON validation contracts
├── test_library_purity.py               # Guard cold-start sqlite3 absence & storage AST boundaries
├── test_api_stability.py                # Pin M9 exports, SQLiteRunIndex methods, & model fields
├── unit/test_sqlite_index.py            # US1+US2 rebuild/sync, corruption recovery, filters, parity, SQLi safety
└── integration/test_sqlite_index_pipeline.py # US3 CLI `index` & `query` E2E + cold-start subprocess check
```

## Complexity Tracking

No Constitution violations or structural exceptions required.
