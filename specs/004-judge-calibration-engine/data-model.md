# Phase 1 Data Model: Milestone 4 — Model-Based Judge & Calibration Engine

**Feature**: `004-judge-calibration-engine` | **Date**: 2026-11-18 | **Schema Location**: `src/evalforge_maestro/types.py`

All contracts inherit `ConfigDict(extra="forbid")`, reject non-finite numbers (`NaN`, `Inf`), reject boolean values passed to integer or numeric fields, normalize timestamps to UTC, round bounded metric scores via `_canonical.round_score` (6 decimals), round signed deltas via `_canonical.round_delta` (`abs(v) <= 1e-9` and `-0.0` → `0.0`), and enforce `"1.0"` `schema_version` on top-level interchange artifacts.

---

## 1. Enumerations

| Enum | Values | Description |
|---|---|---|
| `CalibrationDisagreementType(str, Enum)` | `too_generous`, `too_harsh`, `score_divergence`, `inconclusive` | Classifies each discrepancy recorded in `CalibrationReport.disagreements` for SME triage (`too_generous`: judge passed human-failed case; `too_harsh`: judge failed human-passed case; `score_divergence`: binary verdicts matched while numeric gap exceeded `score_divergence_threshold`; `inconclusive`: judge returned `INCONCLUSIVE`/`NOT_APPLICABLE` or `None` score). |

*(Existing reused enumerations from `types.py`: `MetricStatus`.)*

---

## 2. Core Judge & Calibration Models (`src/evalforge_maestro/types.py`)

### `JudgeConfig`
Declarative, secret-free specification of a model-based judge instance. Credentials (such as provider API keys) NEVER reside on `JudgeConfig`.

| Field | Type | Default | Constraints & Validation |
|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | `"1.0"` | Canonical contract version. |
| `model` | `str` | `"mock-judge"` | Stripped non-empty model/provider identifier (`min_length=1`). |
| `api_base` | `str \| None` | `None` | Optional HTTP/HTTPS base URL (`scheme in {"http", "https"}`, non-empty host; rejects embedded URL userinfo credentials `username`/`password`, URL query parameters/fragments/params, and strips/rejects empty strings). |
| `temperature` | `float` | `0.0` | Finite float in `[0.0, 2.0]` (`_reject_bool_number`). |
| `pass_threshold` | `float` | `0.5` | Finite float in `[0.0, 1.0]` (`_reject_bool_number`, rounded via `round_score`). |
| `max_retries` | `int` | `2` | Strict integer in `[0, 10]` (`_reject_strict_int`; in `mock_mode=True`, heuristics and single-payload overrides execute single-pass cleanly while multi-attempt scripted mock sequences honor up to `max_retries`). |
| `retry_backoff_seconds` | `float` | `0.5` | Finite float in `[0.0, 60.0]` (`_reject_bool_number`; `mock_mode=True` forces zero sleep backoff cleanly). |
| `timeout_seconds` | `float` | `30.0` | Finite float in `(0.0, 600.0]` (`_reject_bool_number`). |
| `local_only` | `bool` | `False` | When `True` and `mock_mode=False`, blocks remote providers and non-loopback hosts pre-network (`LocalOnlyPolicyError`). |
| `mock_mode` | `bool` | `False` | When `True`, executes offline deterministically without API keys or network calls. |
| `seed` | `int \| None` | `None` | Optional strict integer seed (`_reject_strict_int`). |
| `prompt_version` | `str` | `"1.0"` | Stripped non-empty prompt template version string (`min_length=1`). |
| `extra_params` | `dict[str, Any]` | `{}` | JSON-serializable provider parameters, recursively redacted via `_canonical.redact_secrets` on validation. |

Computed properties & helpers on `JudgeConfig`:
- `fingerprint -> str`: Deterministic 64-char hex SHA-256 over canonical redacted JSON of `JudgeConfig`.

---

### `JudgeResponse`
Strict Pydantic validation contract parsed from raw judge output JSON. Unparseable or out-of-range outputs never instantiate cleanly and fall back to `MetricStatus.INCONCLUSIVE` (`score = None`).

| Field | Type | Default | Constraints & Validation |
|---|---|---|---|
| `score` | `float` | Required | Finite float in `[0.0, 1.0]` (`_reject_bool_number`, rounded via `round_score`). |
| `rationale` | `str` | Required | Stripped non-empty explanatory rationale (`min_length=1`). |
| `verdict` | `str \| None` | `None` | Optional stripped categorical verdict from model output (informational only; `MetricStatus` always derives strictly from numeric `score >= threshold - 1e-9`). |
| `supported_claims` | `list[str]` | `[]` | Non-empty stripped claim strings supported by evidence. |
| `unsupported_claims` | `list[str]` | `[]` | Non-empty stripped claims lacking supporting evidence. |

---

### `HumanCalibrationSample`
One labeled evaluation case supplied by a domain SME for calibrating an automated judge.

| Field | Type | Default | Constraints & Validation |
|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | `"1.0"` | Canonical contract version. |
| `case_id` | `str` | Required | Stripped non-empty unique identifier within calibration batch (`min_length=1`). |
| `input` | `Any` | Required | JSON-serializable query, prompt, or task payload. |
| `output` | `Any` | Required | JSON-serializable generated answer or output under evaluation. |
| `reference` | `Any` | `None` | Optional JSON-serializable expected ground-truth answer. |
| `retrieved_chunks` | `list[RetrievedChunk]` | `[]` | Optional retrieved context chunks used by context/groundedness judges. |
| `human_score` | `float \| None` | `None` | Optional finite float in `[0.0, 1.0]` (`_reject_bool_number`, rounded via `round_score`). |
| `human_passed` | `bool \| None` | `None` | Optional explicit boolean pass/fail verdict. |
| `notes` | `str \| None` | `None` | Optional SME review comments (`_validate_optional_str` / trimmed). |
| `metadata` | `dict[str, Any]` | `{}` | Optional JSON-serializable sample metadata (sanitized via `redact_secrets`). |

Model invariants on `HumanCalibrationSample`:
- At least one of `human_score` or `human_passed` MUST be non-`None` (otherwise `ValueError`).

---

### `CalibrationDisagreement`
Per-case discrepancy or inconclusive audit record surfaced in `CalibrationReport.disagreements`.

| Field | Type | Default | Constraints & Validation |
|---|---|---|---|
| `case_id` | `str` | Required | Stripped non-empty case identifier (`min_length=1`). |
| `disagreement_type` | `CalibrationDisagreementType` | Required | `too_generous`, `too_harsh`, `score_divergence`, or `inconclusive`. |
| `human_score` | `float \| None` | `None` | Original numeric human score in `[0.0, 1.0]` when supplied (`None` when only boolean `human_passed` was provided). |
| `human_passed` | `bool` | Required | Resolved human pass/fail verdict. |
| `judge_score` | `float \| None` | `None` | Rounded judge score in `[0.0, 1.0]` (`None` when inconclusive). |
| `judge_status` | `MetricStatus` | Required | Emitted judge metric status (`PASS`, `FAIL`, `WARNING`, `INCONCLUSIVE`, `NOT_APPLICABLE`). |
| `judge_passed` | `bool \| None` | `None` | Binary judge pass verdict (`None` when `judge_score is None`). |
| `score_delta` | `float \| None` | `None` | Rounded signed delta `judge_score - human_numeric` (`[-1.0, 1.0]`, `None` when `judge_score is None`). |
| `judge_rationale` | `str` | Required | Stripped non-empty `MetricResult.explanation`. |
| `human_notes` | `str \| None` | `None` | Optional SME notes from `HumanCalibrationSample`. |

---

### `CalibrationReport`
Schema-versioned diagnostic artifact emitted by `calibrate_judge` / `acalibrate_judge`.

| Field | Type | Default | Constraints & Validation |
|---|---|---|---|
| `schema_version` | `Literal["1.0"]` | `"1.0"` | Canonical contract version. |
| `metric_id` | `str` | Required | Calibrated judge metric identifier (`min_length=1`). |
| `metric_version` | `str` | Required | Calibrated judge metric version (`min_length=1`). |
| `judge_config` | `JudgeConfig` | Required | Redacted judge configuration used during calibration. |
| `judge_config_fingerprint` | `str` | Required | Canonical 64-char hex SHA-256 provenance fingerprint (`^[0-9a-f]{64}$`). |
| `total_cases` | `int` | Required | Strict integer `>= 1`. |
| `valid_cases` | `int` | Required | Strict integer `>= 0` (cases yielding valid numeric score and non-inconclusive status). |
| `inconclusive_cases` | `int` | Required | Strict integer `>= 0`; validator enforces `valid_cases + inconclusive_cases == total_cases`. |
| `pass_threshold_evaluated` | `float` | Required | Active judge pass threshold `[0.0, 1.0]` evaluated during verdict mapping. |
| `human_threshold_evaluated` | `float` | Required | Human threshold `[0.0, 1.0]` used when converting numeric `human_score` without explicit `human_passed`. |
| `score_divergence_threshold` | `float` | `0.25` | Continuous divergence threshold in `(0.0, 1.0]`. |
| `exact_agreement_rate` | `float \| None` | `None` | Rounded percentage `[0.0, 100.0]` of valid cases where `judge_passed == human_passed` (`None` iff `valid_cases == 0`). |
| `too_generous_rate` | `float \| None` | `None` | Fraction `[0.0, 1.0]` of valid cases where `judge_passed and not human_passed` (`None` iff `valid_cases == 0`). |
| `too_harsh_rate` | `float \| None` | `None` | Fraction `[0.0, 1.0]` of valid cases where `not judge_passed and human_passed` (`None` iff `valid_cases == 0`). |
| `mean_human_score` | `float \| None` | `None` | Mean human score across valid cases in `[0.0, 1.0]` (`1.0`/`0.0` used when sample had boolean label only; `None` iff `valid_cases == 0`). |
| `mean_judge_score` | `float \| None` | `None` | Mean judge score across valid cases in `[0.0, 1.0]` (`None` iff `valid_cases == 0`). |
| `mean_score_delta` | `float \| None` | `None` | Signed `mean(judge_score - human_numeric)` in `[-1.0, 1.0]` (`round_delta`; `None` iff `valid_cases == 0`). |
| `disagreements` | `list[CalibrationDisagreement]` | `[]` | Deterministically ordered per-case disagreement and inconclusive inspection records (preserving input sample order). |
| `recommended_pass_threshold` | `float` | Required | Recommended calibrated pass threshold in `[0.0, 1.0]` computed deterministically via agreement-maximizing sweep (or preserved `pass_threshold_evaluated` when `valid_cases == 0`). |

Model invariants on `CalibrationReport`:
- `valid_cases + inconclusive_cases == total_cases`.
- All nullable summary metrics (`exact_agreement_rate`, `too_generous_rate`, `too_harsh_rate`, `mean_human_score`, `mean_judge_score`, `mean_score_delta`) MUST be `None` when `valid_cases == 0` and MUST be non-`None` finite values when `valid_cases > 0`.

---

## 3. Structural Protocols (`src/evalforge_maestro/types.py`)

### `AsyncBatchMetric(Protocol)`
Runtime-checkable protocol (`@runtime_checkable`) enabling `EvaluationOrchestrator` to dispatch context-grouped concurrent batches and auto-derive `judge_config_fingerprint` without importing concrete judge classes from `evalforge_maestro.judges`:

- `@property def metadata(self) -> MetricMetadata`
- `@property def judge_config_fingerprint(self) -> str | None`
- `def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult`
- `async def aevaluate_batch(self, items: Sequence[tuple[EvaluationCase, ExecutionResult]], *, max_concurrency: int = 4) -> list[MetricResult]`
