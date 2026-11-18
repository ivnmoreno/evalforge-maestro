# Research & Architecture Decisions: Milestone 1 — Evaluation Foundation

**Feature**: `001-evaluation-foundation` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## 1. JSON Schema Validation Dependency & Core Footprint

- **Decision**: Declare `jsonschema>=4.23,<5` alongside `pydantic>=2.7,<3` in core runtime dependencies, and lazy-import `jsonschema` inside `json_schema_validation` execution rather than at package import time.
- **Rationale**: `json_schema_validation` is a mandatory Milestone 001 deterministic baseline metric (`FR-013`, `FR-016`) that MUST work out of the box in an isolated `--no-dev` core installation. Using `jsonschema` (Draft 2020-12 / Draft-07 compliant) eliminates edge-case divergence across keywords (`required`, `additionalProperties`, `anyOf`, `oneOf`, `allOf`, `enum`, numeric bounds, `$defs`) while lazy-importing keeps `import evalforge_maestro` cold-start lightweight with zero extra modules loaded until schema validation runs.
- **Alternatives Considered**:
  - *Hand-rolled subset validator using `pydantic` / `isinstance` checks*: Rejected because implementing Draft 2020-12 / Draft-07 semantics manually introduces subtle spec violations and maintenance burden.
  - *Optional extra `[schema]`*: Rejected because `json_schema_validation` is part of the M1 baseline metric suite expected in core installs without extra flags.

## 2. Unidirectional Dependency Inversion Between `execution` and `adapters`

- **Decision**: Define `TargetAdapter` (`Protocol`), `Metric` (`Protocol`), and `CheckpointWriter` (`Protocol`) directly inside `src/evalforge_maestro/types.py`, alongside a leaf `src/evalforge_maestro/exceptions.py` defining the `EvalforgeError` hierarchy. Place `CallableAdapter` under `src/evalforge_maestro/adapters/callable.py`.
- **Rationale**: Constitution Principle II prohibits `core` (`types`, `datasets`, `execution`, `storage`), `metrics`, `judges`, and `regression` from importing `cli`, config loaders, or concrete target `adapters`. Anchoring `TargetAdapter` as a `typing.Protocol` in `types.py` lets `EvaluationOrchestrator` (`execution/`) execute any adapter passed by callers while having zero AST import edges to `adapters/`. Every library subsystem imports strictly downward toward `types.py` and `exceptions.py`.
- **Alternatives Considered**:
  - *Putting `TargetAdapter` protocol inside `adapters/base.py` and importing it in `execution/`*: Rejected because any AST boundary rule checking `execution` does not import `adapters` would fail or require brittle submodule allowlists.
  - *Passing raw callables directly to `EvaluationOrchestrator`*: Rejected because adapters encapsulate uniform evidence capture (`elapsed_seconds`, `errors`, `system_version`, `config_fingerprint`) needed across M1 (`CallableAdapter`) and M2 (`RAGAdapter`, `DocpipeAdapter`).

## 3. Streaming Intake, Canonical SHA-256 Fingerprinting & Bounded Memory

- **Decision**: Implement `DatasetEngine` as a lazy generator (`iter_cases`) reading UTF-8 JSONL line-by-line, validating each line immediately into `EvaluationCase`, tracking seen IDs via a compact `set[str]`, and updating an incremental `hashlib.sha256()` digest per yielded case over canonicalized JSON (`json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"`).
- **Rationale**: Satisfies `FR-005`–`FR-008` and `SC-001`–`SC-003` with `O(1)` line-buffering RAM (plus compact seen-ID set) rather than materializing thousands of full `EvaluationCase` objects upfront. When `max_dataset_cases` stops iteration early (Clarification Q1), the incremental SHA-256 hash reflects strictly the evaluated case slice without scanning unread tail records, and `RunRecord` records both `evaluated_case_count` and `dataset_capped = True` / `max_dataset_cases`.
- **Alternatives Considered**:
  - *Hashing raw file bytes*: Rejected because JSON key reordering or whitespace changes would break fingerprint equivalence (`SC-003`), and partial `max_dataset_cases` slices would still require scanning or hashing unrelated tail lines.
  - *Loading all cases into a `list[EvaluationCase]` before running*: Rejected because 10,000+ cases with large contexts would defeat workstation memory protection (`FR-005`, `FR-021`).

## 4. Sync/Async `CallableAdapter`, Bounded Concurrency & Per-Case Timeouts

- **Decision**: Support both synchronous and asynchronous target callables in `CallableAdapter` (`inspect.iscoroutinefunction` plus `inspect.isawaitable` fallback on call return). Run synchronous callables via `asyncio.to_thread` inside an `asyncio.Semaphore(max_concurrency)`-bounded orchestrator worker loop consuming the dataset iterator lazily (so at most `max_concurrency` tasks are in flight at any instant). Wrap each target call in `asyncio.wait_for(..., timeout=case_timeout_seconds)` when `case_timeout_seconds` is configured (Clarification Q5). Expose both `arun(...)` (async) and `run(...)` (sync convenience wrapper).
- **Rationale**: Offloading sync callables to `asyncio.to_thread` enables real concurrency up to `max_concurrency` (default `4`) without blocking the event loop, while a bounded pull-based worker pool avoids spawning 10,000 pending `Task` coroutines in memory at once. Catching `TimeoutError` and target exceptions inside `CallableAdapter` / `EvaluationOrchestrator` maps faults cleanly to `ExecutionResult.errors` and downstream `MetricStatus.INCONCLUSIVE` (`FR-018`, `FR-020`).
- **Known Limitation Documented**: In Python, `asyncio.wait_for` around `asyncio.to_thread` unblocks the orchestrator and records the timeout cleanly, but cannot forcibly terminate an underlying OS thread blocked in non-interruptible C/I/O code.
- **Alternatives Considered**:
  - *`ThreadPoolExecutor` only*: Rejected because async callables (`async def`) would require spinning up a new event loop per worker thread, breaking shared async clients and adding overhead.
  - *`asyncio.gather` over the full dataset*: Rejected because eager coroutine instantiation buffers the entire dataset in RAM simultaneously.

## 5. Post-Scoring `max_context_chars` Truncation & Resident Memory Soft-Cap

- **Decision**: Execute metrics for a single active case against the untruncated `ExecutionResult` in memory, then apply deterministic `max_context_chars` truncation (marking `ExecutionResult.truncated = True`) immediately before writing the case entry to `.evalforge/tmp/<run_id>.jsonl` and storing it in `RunRecord` (Clarification Q3). Implement optional resident memory monitoring (`max_memory_mb`) using POSIX `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (normalizing KiB on Linux vs bytes on macOS) with graceful cross-OS fallback (`None`/no-op or warning) on Windows where `resource` is unavailable.
- **Rationale**: Post-scoring truncation guarantees valid long JSON outputs and reference matches are scored accurately (`FR-012`) while capping disk and historical `RunRecord` size. Guarding `import resource` avoids crashes on the Windows CI matrix (`ubuntu-latest`, `macos-latest`, `windows-latest`).
- **Alternatives Considered**:
  - *Pre-scoring truncation inside `CallableAdapter`*: Rejected by Clarification Q3 because truncating a valid JSON response mid-payload causes false `json_schema_validation` and `exact_match` failures.

## 6. Atomic Immutable Storage, Non-Overwrite Guarantees & Cross-OS Locking

- **Decision**:
  - **RunRecord Persistence (`.evalforge/runs/<run_id>.json`)**: Write canonical JSON (`sort_keys=True`, `indent=2`, UTF-8, `\n` LF line endings, trailing newline) to a temporary file opened with `os.O_WRONLY | os.O_CREAT | os.O_EXCL` (`0o600`), flush and `os.fsync`, then commit atomically without overwriting using `os.link(tmp_path, target_path)` followed by `os.unlink(tmp_path)` on POSIX (raising `ImmutabilityError` if `FileExistsError` occurs). On Windows (or filesystems without hardlink support), check `target_path.exists()` under a lock and rename cleanly if absent.
  - **Manifest Append (`.evalforge/manifest.jsonl`)**: Append single-line canonical JSON (`separators=(",", ":")`, `sort_keys=True`, `ensure_ascii=False`) + `\n` under an advisory file lock (`fcntl.flock` on POSIX; `msvcrt.locking` / lockfile fallback on Windows) with `0o600` file permissions.
  - **Temp Checkpointing (`.evalforge/tmp/<run_id>.jsonl`)**: Flush each case line incrementally (`0o600`), retain on failure/abort for inspection, and unlink on successful commit by default unless `retain_checkpoints=True` (Clarification Q4).
- **Rationale**: `os.link` fails atomically at the kernel level if the destination `run_id` already exists—eliminating TOCTOU races that `os.replace` would silently overwrite (`FR-025`, `FR-026`, `@pytest.mark.gate_immutability`).
- **Alternatives Considered**:
  - *`exists()` check followed by `os.replace()`*: Rejected on POSIX because a race between two concurrent runs with the same explicit `run_id` could silently overwrite via `os.replace`.

## 7. Secret Hygiene & Config Sanitization

- **Decision**: Implement a recursive key-redaction utility used whenever adapter `config` dictionaries or metadata are fingerprinted or embedded into `ExecutionResult` / `RunRecord`, redacting keys matching sensitive patterns (`api_key`, `apikey`, `secret`, `token`, `password`, `passwd`, `authorization`, `auth`, `credential`, `private_key`) with `"[REDACTED]"` before persistence (and computing `config_fingerprint` cleanly without exposing plaintext secrets).
- **Rationale**: Enforces Constitution Principle VI and `FR-027` even if a caller passes a config dict containing sensitive fields into `CallableAdapter`.
- **Alternatives Considered**:
  - *Allowing raw config dict serialization*: Rejected due to high risk of secret leakage in `.evalforge/` JSON artifacts.

## 8. Metric Formula Determinism & Version Pinning

- **Decision**: Keep all built-in metric calculation functions (`exact_match`, `normalized_match`, `json_schema_validation`) pure and isolated in `src/evalforge_maestro/metrics/deterministic.py` with explicit `metric_version = "1.0.0"` and `MetricMetadata` declarations (`what_it_measures`, `required_case_fields`, `required_execution_fields`, `calculation_method`, `known_limitations`). Compute normalized AST source hashes in contract tests so any modification to scoring logic requires bumping `metric_version`. Round all numeric scores and aggregate means to 6 decimal places (`round(value, 6)`).
- **Rationale**: Satisfies `FR-013`–`FR-018`, Constitution Principle V (`Metric Formula Versioning Guard`), and 100% branch coverage on deterministic metric formulas.
- **Alternatives Considered**:
  - *Manual changelog discipline for metric versions*: Rejected because silent formula drift invalidates historical baseline comparisons in Milestone 003.
