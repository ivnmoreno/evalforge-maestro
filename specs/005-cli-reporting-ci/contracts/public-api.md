# Contract: Public Python Library API — Milestone 5 Extensions (`evalforge_maestro`)

**Feature**: `005-cli-reporting-ci` | **Version**: `0.5.0` (M5)

All Milestone 001, 002, 003, and 004 public signatures, Pydantic schemas, exceptions, and exports remain backwards-compatible. Milestone 005 adds:
- Pure security/PII egress helper contracts (`detect_pii_categories`, `validate_pii_egress`)
- Replay adapter (`ReplayAdapter` in `evalforge_maestro.adapters`)
- Pure library reporting contracts and functions (`evalforge_maestro.reporting`)
- Centralized Milestone 5 Pydantic schemas in `evalforge_maestro.types` (zero `cli`, `tomllib`, `tomli`, or `dotenv` leakage into any library module)

---

## 0. Canonical M5 Schemas (`evalforge_maestro.types` / `evalforge_maestro`)

- **New Enums**:
  - `ConfigSourceTier` (`"cli"`, `"env"`, `"env_file"`, `"file"`, `"default"`)
  - `TargetType` (`"callable"`, `"rag"`, `"docpipe"`, `"replay"`)
  - `ReportKind` (`"run"`, `"compare"`, `"trend"`, `"calibrate"`)
  - `EvidenceDecouplingCategory` (`"answer_passed_retrieval_or_grounding_failed"`, `"retrieval_passed_answer_or_grounding_failed"`)
- **New Strict Models**:
  - `MetricSpecConfig`
  - `ResolvedSecurityConfig`
  - `ResolvedTargetConfig`
  - `ResolvedJudgeSettings`
  - `ResolvedLoggingConfig`
  - `ConfigSettingProvenance`
  - `CLIResolvedConfig` (`schema_version = "1.0"`)
  - `DecoupledEvidenceDiagnostic`
  - `ReportDiagnosticsSummary`
  - `CalibrationGateSummary`
  - `ReportDocument` (`schema_version = "1.0"`)
  - `BaselineCommandPayload` (`schema_version = "1.0"`)
  - `ConfigValidationPayload` (`schema_version = "1.0"`)
  - `CLIErrorPayload` (`schema_version = "1.0"`)

*(All models carry `extra="forbid"`, finite/non-bool numeric checks, secret redaction guarantees on `CLIResolvedConfig` and `CLIErrorPayload`, and Draft 2020-12 contract definitions in `contracts/schemas-v1.json`.)*

---

## 1. Security & PII Egress Helper (`evalforge_maestro._canonical` & `evalforge_maestro.judges.security`)

```python
def detect_pii_categories(value: Any) -> list[str]:
    """Deterministically detect matched PII/credential categories without returning raw secret text.

    Categories: 'email_address', 'phone_number', 'us_ssn', 'payment_card' (Luhn-checked), 'secret_token'.
    """


def validate_pii_egress(
    value: Any,
    *,
    enabled: bool = True,
    context_label: str = "outbound payload",
) -> None:
    """Raise LocalOnlyPolicyError (without echoing matched raw PII) when enabled and PII/secrets match."""
```

---

## 2. Offline Replay Target Adapter (`evalforge_maestro.adapters`)

`evalforge_maestro.adapters.__all__` exports `["CallableAdapter", "DocpipeAdapter", "RAGAdapter", "ReplayAdapter"]`.

```python
class ReplayAdapter:
    """TargetAdapter serving pre-captured ExecutionResult records deterministically by case_id."""

    def __init__(
        self,
        executions: Sequence[ExecutionResult] | Mapping[str, ExecutionResult],
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config_fingerprint: str | None = None,
    ) -> None: ...

    @classmethod
    def from_file(
        cls,
        path: Path | str,
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config_fingerprint: str | None = None,
    ) -> ReplayAdapter:
        """Load pre-captured ExecutionResult JSONL or RunRecord/list JSON file, rejecting duplicates."""

    @property
    def case_ids(self) -> frozenset[str]: ...

    @property
    def system_version(self) -> str | None: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def config_fingerprint(self) -> str | None: ...

    async def execute(self, case: EvaluationCase) -> ExecutionResult:
        """Return pre-captured ExecutionResult for case.id or raise AdapterError if missing."""
```

---

## 3. Pure Reporting Subsystem (`evalforge_maestro.reporting`)

`evalforge_maestro.reporting` is strictly library-pure: ZERO imports from `cli`, `tomllib`, `tomli`, `dotenv`, `adapters`, `datasets`, or `execution`, ZERO root logger mutation, and ZERO file/config side effects (aside from caller-explicit `write_report_files` only when exporting files via explicit path arguments).

`evalforge_maestro.reporting.__all__` exports:
`["build_calibration_report", "build_comparison_report", "build_run_report", "build_trend_report", "detect_decoupled_evidence", "render_markdown", "render_report_json"]`

```python
def detect_decoupled_evidence(run: RunRecord) -> list[DecoupledEvidenceDiagnostic]:
    """Inspect per-case retrieval and answer/groundedness metrics to surface decoupled failures."""


def build_run_report(
    run: RunRecord,
    *,
    comparison: RunComparisonReport | None = None,
    trend: TrendReport | None = None,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a three-way-separated, secret-scrubbed ReportDocument for a RunRecord."""


def build_comparison_report(
    comparison: RunComparisonReport,
    *,
    candidate_run: RunRecord | None = None,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed pairwise comparison ReportDocument."""


def build_trend_report(
    trend: TrendReport,
    *,
    gate: QualityGateResult | None = None,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed sliding-window trend ReportDocument."""


def build_calibration_report(
    calibration: CalibrationReport,
    *,
    min_agreement: float | None = None,
    strict: bool = False,
    title: str | None = None,
) -> ReportDocument:
    """Build a secret-scrubbed judge calibration ReportDocument with optional threshold gate summary."""


def render_report_json(document: ReportDocument, *, pretty: bool = False) -> str:
    """Render canonical, secret-redacted schema-validated JSON string for ReportDocument."""


def render_markdown(document: ReportDocument) -> str:
    """Render deterministic, secret-scrubbed Markdown with Evaluation, Regression, and Gate sections."""
```

---

## 4. Top-Level Façade (`evalforge_maestro`)

`evalforge_maestro.__init__` re-exports:
- `ReplayAdapter`
- `build_run_report`, `build_comparison_report`, `build_trend_report`, `build_calibration_report`, `detect_decoupled_evidence`, `render_markdown`, `render_report_json`
- All new M5 types (`CLIResolvedConfig`, `ConfigSourceTier`, `TargetType`, `ReportKind`, `EvidenceDecouplingCategory`, `MetricSpecConfig`, `ResolvedSecurityConfig`, `ResolvedTargetConfig`, `ResolvedJudgeSettings`, `ResolvedLoggingConfig`, `ConfigSettingProvenance`, `DecoupledEvidenceDiagnostic`, `ReportDiagnosticsSummary`, `CalibrationGateSummary`, `ReportDocument`, `BaselineCommandPayload`, `ConfigValidationPayload`, `CLIErrorPayload`)
- `detect_pii_categories`, `validate_pii_egress`

*(Note: `evalforge_maestro.cli` is NEVER auto-imported by `evalforge_maestro.__init__`, preserving clean library isolation and cold-start speed.)*
