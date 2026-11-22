# EvalForge Maestro — Architecture & Draft Review Evaluation (`v0.3.0`)

**Evaluated Ref:** `v0.3.0` (`main` at `cae3610`)  
**Verification Run:** `.venv/bin/pytest -q` (`193 passed in 18.38s`), `.venv/bin/ruff check .` (`All checks passed!`), `.venv/bin/mypy --strict src tests` (`Success: no issues found in 115 source files`)

---

## Executive Verdict

The existing `evalforge-maestro` codebase (`v0.3.0`) is **architecturally stronger and operationally cleaner than the draft evaluation report implies**, and **no structural redesign or feature expansion is necessary**. Where the draft identifies real gaps, they are primarily **documentation/claim accuracy and operational boundary clarification**, rather than architectural defects. Conversely, several of the draft's proposed remediations would **over-engineer a local evaluation engine** (cryptographic hash chains/signing), **misread already-updated repository docs** ([`docs/future-features.md`](docs/future-features.md)), or **introduce dangerous behavioral regressions** (silent text-mutating PII redaction over evaluation evidence).

The draft's strategic recommendation is spot-on: **preserve EvalForge's core positioning as an independent evaluation and regression verification engine**, rather than expanding into an LLM runtime, hosted observability SaaS, or vector store.

---

## 1. Comparison: Codebase (`v0.3.0`) vs. Draft Report

| Draft Area / Finding | Assessment Against Codebase | Recommended Disposition |
| --- | --- | --- |
| **Core architecture (Evaluation / Regression / Acceptance split & evidence decoupling)** | **Accurate.** Three-way separation and retrieval/trace-vs-answer decoupling are deeply implemented and enforced by contract and 100%-branch-coverage tests ([`.github/workflows/ci.yml`](.github/workflows/ci.yml#L50-L64)). | Preserve as-is |
| **Finding 1 — PII masking overstated in docs** | **Accurate.** [`README.md`](README.md#L16) overclaims PII masking, whereas [`_canonical.py`](src/evalforge_maestro/_canonical.py#L226-L257) implements secret masking + pre-network `--block-pii` detection only. | **Fix documentation**; avoid silent text-mutating PII redaction |
| **Finding 2 — Storage immutability & crash window** | **Half right, half over-engineered.** [`save_run()`](src/evalforge_maestro/storage/local.py#L168-L192) has a two-step crash window, and [`SQLiteRunIndex`](src/evalforge_maestro/storage/sqlite_index.py#L518-L580) stores `run_sha256` without verifying it back; however, unkeyed local hash chains/signing are overkill without external KMS/WORM custody. | Small reconciliation / digest verification only (optional) |
| **Finding 3 — HTTP service deployment boundary** | **Accurate documentation gap; code scope is deliberate.** Stdlib [`ThreadingHTTPServer`](src/evalforge_maestro/service/server.py#L104-L105) is intentionally lightweight and [`ServiceApplication`](src/evalforge_maestro/service/app.py#L181) is transport-agnostic for ASGI/WSGI wrapping ([`docs/remote-service.md`](docs/remote-service.md#L188)). | **Document deployment boundary** clearly; optional minor server hardening |
| **Finding 4 — [`types.py`](src/evalforge_maestro/types.py) monolith (`3,389` lines / `102` classes)** | **Accurate observation, premature refactor.** The draft itself advises against splitting merely for file length. | **No change now** |
| **Finding 5 — Broad public API (`193` symbols in `__all__`)** | **Mostly misread.** All `_` internal helpers (`_canonical`, `_metric_factory`, `_locality`) stay private; [`__init__.py`](src/evalforge_maestro/__init__.py#L1-L426) exports curated Pydantic schemas, enums, metrics, and lazy `ServiceApplication`, pinned by [`tests/test_api_stability.py`](tests/test_api_stability.py#L77-L150). | **No change now** (preserve semver stability) |
| **Finding 6 — Statistical methodology caveats** | **Accurate gap.** Pure-stdlib Student's/Welch's/one-sample $t$ inference and zero-variance $p = 0.0$ rules in [`stats.py`](src/evalforge_maestro/regression/stats.py#L170-L193) lacked a companion methodology guide. | **Add [`docs/statistical-methodology.md`](docs/statistical-methodology.md)** |
| **Finding 7 — Historically stale docs** | **Half right, half misread.** [`docs/intent.md`](docs/intent.md#L5) still states `New Project (Greenfield)` and `M6 deferred`; however, [`docs/future-features.md`](docs/future-features.md#L1-L31) **already** marks M1–M6 + Features `007`–`010` shipped (citing `v0.1.4` only as the historical M1–M5 base). | **Add top status banner to `docs/intent.md` only** |
| **Finding 8 — ZIP contains `.git`/`.venv`/caches** | **Transfer artifact, not a repository bug.** `.gitignore` excludes dev artifacts and CI builds clean wheels/sdists ([`.github/workflows/ci.yml`](.github/workflows/ci.yml#L109-L200)). | None in repo (`git archive` when sharing externally) |
| **Section 4 — 3 cold-start test failures (`numpy`)** | **Confirmed external environment artifact.** All `193` tests pass in clean `.venv`; reviewer's environment pre-loaded `numpy` and subprocesses ran without `-I`/`-E`. | None required (optional `-I`/`-E` isolation hardening in purity tests) |

---

## 2. Detailed Technical Analysis of Draft Findings

### Finding 1 (P1): PII Masking vs. Egress Blocking
- **Verified Reality**: [`README.md`](README.md#L16) previously claimed *"automatic credential/API-key/Bearer/PII masking (`[REDACTED]`)"*. In [`src/evalforge_maestro/_canonical.py`](src/evalforge_maestro/_canonical.py#L226-L257):
  - `redact_secrets()` masks sensitive dictionary keys.
  - `scrub_secret_text()` scrubs URL userinfo, Bearer headers, provider keys (`sk-`, `AIza`, `hf_`, `gsk_`), and `key=val` patterns in strings.
  - `detect_pii_categories()` checks for selected categories (`email_address`, `us_ssn`, `phone_number`, Luhn `payment_card`, `secret_token`) exclusively to enforce pre-network `--block-pii` egress blocking.
- **Disagreement with Draft**: The draft favors building a silent general-purpose PII-redaction layer later. In an evaluation engine, silently rewriting case inputs, model outputs, or tool arguments to `[EMAIL]`/`[PHONE]` invalidates deterministic metrics (`exact_match`, `normalized_match`, `json_schema_validation`, `argument_correctness`) and corrupts reproducible evidence. Keeping `--block-pii` as a strict pre-network circuit breaker while stating security guarantees accurately in `README.md` is the right design.

### Finding 2 (P1): Run Integrity, Crash Consistency, and Split Discovery
- **Verified Reality**:
  - [`RunManifestEntry`](src/evalforge_maestro/types.py#L1026-L1066) tracks `dataset_fingerprint`, `config_fingerprint`, `judge_config_fingerprint`, and `embedding_config_fingerprint`, without a `run_sha256` of `runs/<run_id>.json`.
  - [`LocalRunStore.save_run()`](src/evalforge_maestro/storage/local.py#L168-L192) commits `runs/<run_id>.json` atomically (`os.link`/`os.replace` + `fsync`, `0o600`), then calls `_locked_append_line` on `manifest.jsonl`.
  - **Codebase nuance missed by draft**: [`SQLiteRunIndex`](src/evalforge_maestro/storage/sqlite_index.py#L518-L580) *does* compute and insert `run_sha256` during `rebuild()` and `sync()`, yet **never reads or verifies `run_sha256` back** inside [`status()`](src/evalforge_maestro/storage/sqlite_index.py#L415-L515) or `sync()`. Moreover, [`LocalRunStore.load_runs()`](src/evalforge_maestro/storage/local.py#L338-L343), CLI `trend`, and [`ServiceApplication._handle_reports()`](src/evalforge_maestro/service/app.py#L409) read `manifest.jsonl` only, whereas [`SQLiteRunIndex._discover_canonical()`](src/evalforge_maestro/storage/sqlite_index.py#L253-L277) unions `manifest.jsonl` with `runs/*.json`. Consequently, an orphaned run JSON appears in `query runs` / `GET /v1/runs` while missing `trend`!
- **Disagreement with Draft**: Adding local hash chains or signed manifests without external key custody / WORM storage creates complexity without security value, since any actor able to modify `.evalforge/runs/*.json` can recompute local digests. Optional manifest `run_sha256` + orphan reconciliation + digest comparison in `SQLiteRunIndex.status()` would close the crash/corruption gap cleanly without PKI.

### Findings 4 & 5 (P2): `types.py` Size and Public `__all__` Surface
- [`src/evalforge_maestro/types.py`](src/evalforge_maestro/types.py) (`3,389` lines, `102` top-level classes) and [`src/evalforge_maestro/__init__.py`](src/evalforge_maestro/__init__.py) (`193` items in `__all__`) reflect deliberate single-schema typing and semver-pinned contract exports. Zero internal helper modules are leaked into `__all__`, and breaking or shuffling `193` public re-exports post-`v0.3.0` brings churn with zero user value.

### Finding 6 (P2): Statistical Methodology
- [`src/evalforge_maestro/regression/stats.py`](src/evalforge_maestro/regression/stats.py#L170-L193) assigns `p_value = 0.0` (`SIGNIFICANT_IMPROVEMENT` / `SIGNIFICANT_REGRESSION`) when `standard_error <= FLOAT_EPSILON` and `abs(mean_delta) > FLOAT_EPSILON`. Meanwhile [`QualityGatePolicy`](src/evalforge_maestro/types.py#L1293-L1317) separates magnitude tolerances (`max_regression_drop`, `max_metric_regression_drops`, `soft_regression_warning`) from statistical inference (`confidence_level`, `min_statistical_samples`, `fail_on_significant_regression`). Documenting these mechanics—alongside bounded `[0, 1]` non-normality, small-$n$ caveats, and lack of multiple-metric $p$-value adjustment—directly solves the clarity gap without runtime changes.

---

## 3. Concrete Operational & UX Findings Missed by the Draft

Direct code inspection surfaced four subtle operational edge cases omitted from the draft report:

1. **Missing lock synchronization between `ThreadingHTTPServer` and `SQLiteRunIndex`**:
   - [`create_http_server`](src/evalforge_maestro/service/server.py#L104-L105) serves concurrent requests via daemon threads sharing one [`ServiceApplication`](src/evalforge_maestro/service/app.py#L200-L201) and one `SQLiteRunIndex` instance.
   - `SQLiteRunIndex` uses `PRAGMA journal_mode=DELETE` ([`sqlite_index.py#L291`](src/evalforge_maestro/storage/sqlite_index.py#L291)) with **zero in-process `threading.Lock` / `RLock`**. Concurrent `POST /v1/evaluate` (`persist=True`), `GET /v1/runs` (`auto_sync=True`), and `POST /v1/index/rebuild` (`os.replace`) calls can contend or race over DB state under concurrent traffic.
2. **Unbounded HTTP handler socket waits and negative `Content-Length`**:
   - `_EvalRequestHandler` ([`service/server.py#L33-L106`](src/evalforge_maestro/service/server.py#L33-L106)) defines no `timeout`, allowing idle/slow TCP clients to pin worker threads indefinitely, and converts negative `Content-Length` headers into empty body `b""` (`server.py#L54-L70`) rather than `400 Bad Request`.
3. **CLI `--env-file` variable isolation surprises (`EVALFORGE_SERVICE_TOKEN` & provider keys)**:
   - [`_TierLookup`](src/evalforge_maestro/cli/config.py#L409-L465) loads `--env-file` into an isolated mapping rather than `os.environ` (preserving library purity), meaning non-`EVALFORGE_*` provider keys (`OPENAI_API_KEY`, etc.) or target env vars in `--env-file` are invisible to LiteLLM or `--target`. Even [`_handle_serve`](src/evalforge_maestro/cli/commands.py#L1058) reads `EVALFORGE_SERVICE_TOKEN` strictly from `os.environ`, ignoring `--env-file`.
4. **Missing `--no-mock` override and unguarded target `stdout` under `--json`**:
   - [`cli/parser.py`](src/evalforge_maestro/cli/parser.py#L247) exposes `--mock` (`action="store_true"`) on `run`, `calibrate`, and `serve` without a `--no-mock` flag, preventing CLI override when `evalforge.toml` or `EVALFORGE_MOCK=true` enables mock mode.
   - While [`judges/provider.py#L77`](src/evalforge_maestro/judges/provider.py#L77) suppresses LiteLLM debug logs, CLI `--json` commands ([`commands.py#L124-L134`](src/evalforge_maestro/cli/commands.py#L124-L134)) do not capture `stdout` from user target callables (`CallableAdapter`) that `print()` during evaluation.

---

## 4. Recommended Priorities Going Forward

1. **Immediate (Docs Only — Addressed Now)**:
   - Clarify secret masking vs. `--block-pii` egress blocking in [`README.md`](README.md#L16).
   - Add historical charter banner to [`docs/intent.md`](docs/intent.md#L1-L10) pointing to [`docs/future-features.md`](docs/future-features.md).
   - Explicitly document reverse-proxy / TLS / rate-limit / ASGI deployment boundaries in [`docs/remote-service.md`](docs/remote-service.md).
   - Publish [`docs/statistical-methodology.md`](docs/statistical-methodology.md) covering parametric assumptions, small-$n$ behavior, zero-variance $p = 0.0$, multiple-comparison risk, and `QualityGatePolicy` tolerances.
2. **Optional Hardening (Only When Needed for Multi-Client `serve` or Strict Crash Recovery)**:
   - Add an internal `threading.RLock` in `SQLiteRunIndex`, set handler socket timeouts / `400` on negative `Content-Length` in `service/server.py`, verify `run_sha256` inside `SQLiteRunIndex.status()`, and reconcile orphaned `runs/*.json`.
   - Support `--no-mock` and `EVALFORGE_SERVICE_TOKEN` lookup via `env_file_vars`.
3. **Leave Alone**:
   - Core Evaluation/Regression/Gate architecture, `types.py` structure, `__init__.py` exports, zero-dependency HTTP core, and refusal to mutate persisted evaluation text.
