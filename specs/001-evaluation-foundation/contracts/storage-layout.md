# Contract: Local Artifact Storage & Immutability Layout

**Feature**: `001-evaluation-foundation` | **Root Directory**: `.evalforge/`

## 1. Directory & File Layout

```text
.evalforge/                  # Mode 0o700 (owner rwx)
├── manifest.jsonl           # Mode 0o600 (append-only JSONL of RunManifestEntry)
├── runs/                    # Mode 0o700
│   └── <run_id>.json        # Mode 0o600 (immutable canonical RunRecord JSON)
└── tmp/                     # Mode 0o700
    └── <run_id>.jsonl       # Mode 0o600 (incremental CaseEvaluationRecord journal)
```

## 2. Path Safety Rules

- `run_id` MUST match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` (disallowing `/`, `\`, `..`, and leading `.` to prevent path traversal). Invalid `run_id` values raise `StorageError`.

## 3. Canonical Serialization

- **SHA-256 Hashing**: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` encoded in UTF-8 with `\n` LF endings.
- **`runs/<run_id>.json`**: Pretty canonical JSON (`sort_keys=True`, `indent=2`, `ensure_ascii=False`) ending with a single `\n` LF newline.
- **`manifest.jsonl` & `tmp/<run_id>.jsonl`**: Compact single-line canonical JSON (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`) terminated by `\n`.

## 4. Atomicity & Immutability Guarantees

1. **No In-Place Overwrites**: If `.evalforge/runs/<run_id>.json` already exists, `LocalRunStore.save_run` raises `ImmutabilityError` immediately and never modifies the existing file or appends a duplicate entry to `manifest.jsonl`.
2. **Atomic Non-Overwrite Commit**: Write serialized `RunRecord` bytes to a unique temporary file `.evalforge/runs/.<run_id>.<uuid>.tmp` opened with `0o600`, `flush()`, and `os.fsync()`. On POSIX, publish via `os.link(tmp, target)` + `os.unlink(tmp)` so concurrent duplicate `run_id` commits fail atomically (`FileExistsError` -> `ImmutabilityError`). On platforms lacking hardlink semantics, guard with exclusive lock + existence check prior to `os.replace`.
3. **Line-Atomic Manifest Append**: Append `RunManifestEntry` line under advisory file locking (`fcntl.flock` on POSIX, `msvcrt.locking` / lockfile guard on Windows), flush, and close so concurrent runs never interleave partial JSON lines.
4. **Checkpoint Lifecycle**: `.evalforge/tmp/<run_id>.jsonl` receives flushed lines per completed case. Aborted/failed runs retain this file for post-mortem inspection; successful atomic commits remove it by default unless `retain_checkpoints=True`.
