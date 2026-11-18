# Contract: Public Python Library API — Milestone 3 Extensions (`evalforge_maestro`)

**Feature**: `003-experiment-regression-engine` | **Version**: `0.3.0` (M3)

All Milestone 001 and Milestone 002 public signatures and exports remain backwards-compatible; Milestone 003 adds `judge_config_fingerprint` (and `RunManifestEntry.model_id`), baseline registry operations on `LocalRunStore`, and pure regression/drift/anomaly/trend/`QualityGate` contracts under `evalforge_maestro.regression` and top-level `evalforge_maestro`.

## 0. Canonical M3 Data Contracts (`evalforge_maestro.types`)

New Enums & Models exported from `evalforge_maestro.types` and `evalforge_maestro`:

- Enums: `GateDecision`, `ComparisonDirection`, `TrendDirection`, `DriftCategory`, `AnomalyType`, `AnomalySeverity`, `AnomalyScope`
- Baseline models: `BaselineEntry`, `BaselineRegistry`
- Drift & anomaly models: `DriftWarning`, `AnomalyFlag`
- Comparison models: `MetricComparison`, `CaseMetricDelta`, `CaseComparison`, `TargetChangeSummary`, `RunComparisonReport`
- Trend models: `TrendDataPoint`, `MetricTrendSummary`, `TrendReport`
- Quality gate models: `QualityGatePolicy`, `GateRuleCheck`, `QualityGateResult`
- Additive backward-compatible nullable fields:
  - `OrchestratorConfig.judge_config_fingerprint: str | None = None`
  - `RunRecord.judge_config_fingerprint: str | None = None`
  - `RunManifestEntry.model_id: str | None = None`
  - `RunManifestEntry.judge_config_fingerprint: str | None = None`

*(Full field tables, bounds, and validator invariants match `specs/003-experiment-regression-engine/data-model.md` and `specs/003-experiment-regression-engine/contracts/schemas-v1.json`.)*

## 1. Local Baseline Registry Storage (`evalforge_maestro.storage`)

`LocalRunStore.__init__(self, root: Path | str = Path(".evalforge")) -> None` remains unchanged. Additional methods:

```python
class LocalRunStore:
    def baseline_path(self) -> Path:
        """Return path to .evalforge/baselines.json."""

    def load_baselines(self) -> BaselineRegistry:
        """Load validated BaselineRegistry; returns empty registry if baselines.json is absent."""

    def pin_baseline(
        self,
        run_id: str,
        *,
        name: str = "default",
        note: str | None = None,
        tags: Sequence[str] | None = None,
        overwrite: bool = False,
    ) -> BaselineEntry:
        """Validate run_id and pin an immutable baseline pointer atomically.

        Raises StorageError for invalid names or missing/corrupted runs.
        Raises ImmutabilityError if name already exists and overwrite is False.
        Never mutates historical RunRecord files or manifest.jsonl.
        """

    def get_baseline(self, name: str = "default") -> BaselineEntry:
        """Resolve one BaselineEntry by name or raise StorageError if missing."""

    def list_baselines(self) -> list[BaselineEntry]:
        """Return all pinned BaselineEntry items sorted deterministically by name."""

    def unpin_baseline(self, name: str = "default") -> BaselineEntry:
        """Remove a baseline alias from baselines.json without deleting underlying RunRecord files."""

    def load_baseline_run(self, name: str = "default") -> RunRecord:
        """Resolve baseline alias and load its persisted immutable RunRecord."""

    def load_runs(self, run_ids: Sequence[str] | None = None) -> list[RunRecord]:
        """Load persisted RunRecord payloads (manifest order when run_ids is None)."""
```

## 2. Pure Regression, Drift, Anomaly, Trend & Gate Engine (`evalforge_maestro.regression`)

Exports in `evalforge_maestro.regression.__all__`: `["QualityGate", "analyze_trend", "compare_runs", "detect_anomalies", "detect_drift"]`.

```python
def detect_drift(
    baseline: RunRecord,
    candidate: RunRecord,
) -> list[DriftWarning]:
    """Inspect provenance comparability between baseline and candidate runs.

    Flags mismatches in dataset_fingerprint, shared metric_versions, metric sets
    (added/removed), judge_config_fingerprint, dataset_capped, and case set alignment.
    Leaves intentional target changes (system_version, model_id, config_fingerprint)
    unflagged by measurement drift.
    """


def detect_anomalies(
    run: RunRecord,
    *,
    comparison: RunComparisonReport | None = None,
    policy: QualityGatePolicy | None = None,
) -> list[AnomalyFlag]:
    """Detect case/run inter-metric disagreements, masked drops, mandatory failures,
    dataset capping, and inconclusive execution rates.
    """


def compare_runs(
    baseline: RunRecord,
    candidate: RunRecord,
    *,
    baseline_name: str | None = None,
    policy: QualityGatePolicy | None = None,
) -> RunComparisonReport:
    """Compute signed 6-decimal aggregate and per-case deltas, contextual target changes,
    drift warnings, and anomaly flags between two RunRecord artifacts.

    To compare a candidate run against a named pinned baseline without introducing filesystem I/O
    into `evalforge_maestro.regression`, resolve the baseline via `store.load_baseline_run(name)`
    first and pass `baseline_name=name` here.
    """


def analyze_trend(
    runs: Sequence[RunRecord | RunManifestEntry],
    *,
    window: int = 5,
    dataset_id: str | None = None,
    all_datasets: bool = False,
    model_id: str | None = None,
    metric_ids: Sequence[str] | None = None,
    slope_threshold: float = 0.01,
) -> TrendReport:
    """Analyze ordinary least-squares linear trend slopes across up to the latest
    `window` chronological runs, defaulting unfiltered queries to the newest run's
    dataset_id and surfacing within-window adjacent-pair provenance drift transitions.

    Raises ConfigurationError if window < 2 or slope_threshold <= 0.0.
    """


class QualityGate:
    """Pure deterministic policy evaluator enforcing FAIL > INCONCLUSIVE > WARNING > PASS."""

    def __init__(self, policy: QualityGatePolicy | None = None) -> None: ...

    @property
    def policy(self) -> QualityGatePolicy: ...

    def evaluate(
        self,
        run: RunRecord,
        *,
        comparison: RunComparisonReport | None = None,
        trend: TrendReport | None = None,
    ) -> QualityGateResult:
        """Evaluate acceptance policy deterministically with zero wall-clock or disk side effects.

        Raises ConfigurationError if comparison is provided with comparison.candidate_run_id != run.run_id.
        """
```

## 3. Top-Level Re-exports (`evalforge_maestro`)

All new contracts from `evalforge_maestro.types` and all five entrypoints from `evalforge_maestro.regression` MUST be re-exported at top-level `evalforge_maestro.__all__` and pinned cleanly in `tests/test_api_stability.py`.
