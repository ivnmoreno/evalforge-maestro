# Contract: Public Python Library API — Milestone 4 Extensions (`evalforge_maestro`)

**Feature**: `004-judge-calibration-engine` | **Version**: `0.4.0` (M4)

All Milestone 001, 002, and 003 public signatures and exports remain backwards-compatible. Milestone 004 adds judge contracts & exceptions, five provider-independent model-based judge metrics under `evalforge_maestro.judges`, context-grouped async batch execution integration via `AsyncBatchMetric`, and human calibration diagnostics (`calibrate_judge` / `acalibrate_judge`).

---

## 0. Canonical M4 Contracts & Exceptions (`evalforge_maestro.types` / `evalforge_maestro.exceptions` / `evalforge_maestro`)

- **New Exceptions** (subclasses of `EvalforgeError`):
  - `JudgeError(EvalforgeError)`: Raised when live judge transport or judge configuration setup fails unrecoverably (note: individual case parse/transient faults degrade to `MetricStatus.INCONCLUSIVE` rather than aborting batch evaluation unless fatal/fail-fast).
  - `LocalOnlyPolicyError(EvalforgeError)`: Raised *prior* to any network socket or lazy provider import when `local_only=True` and `mock_mode=False` targets a cloud model or non-loopback endpoint (`hostname` neither `"localhost"` nor loopback IP `127.0.0.0/8` / `::1`).
- **New Enum & Pydantic Models** (exported from `evalforge_maestro.types` and `evalforge_maestro`):
  - `CalibrationDisagreementType`
  - `JudgeConfig`
  - `JudgeResponse`
  - `HumanCalibrationSample`
  - `CalibrationDisagreement`
  - `CalibrationReport`
- **New Protocol**:
  - `AsyncBatchMetric` in `evalforge_maestro.types`

*(Field schemas, numeric bounds, and validators match `specs/004-judge-calibration-engine/data-model.md` and `specs/004-judge-calibration-engine/contracts/schemas-v1.json`.)*

---

## 1. Model-Based Judge & Calibration Subsystem (`evalforge_maestro.judges`)

`evalforge_maestro.judges.__all__` exports:
`["AnswerCorrectnessMetric", "AnswerRelevanceMetric", "BaseJudgeMetric", "ContextRelevanceMetric", "CustomRubricJudgeMetric", "GroundednessMetric", "acalibrate_judge", "answer_correctness", "answer_relevance", "calibrate_judge", "context_relevance", "custom_rubric_judge", "groundedness"]`

```python
CompletionFn = Callable[
    ..., Awaitable[str]
]  # Internal/test dependency-injected async callable returning raw judge text


class BaseJudgeMetric:
    """Base implementation of Metric and AsyncBatchMetric for model-based judges."""

    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        """Initialize base judge metric without importing optional provider packages."""

    @property
    def metadata(self) -> MetricMetadata: ...

    @property
    def judge_config(self) -> JudgeConfig: ...

    @property
    def judge_config_fingerprint(self) -> str:
        """Return canonical SHA-256 over redacted JudgeConfig, metric_id, metric_version, and prompt/rubric digest."""

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Synchronously evaluate one case/execution pair."""

    async def aevaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult:
        """Asynchronously evaluate one case/execution pair with injection isolation & retries."""

    async def aevaluate_batch(
        self,
        items: Sequence[tuple[EvaluationCase, ExecutionResult]],
        *,
        max_concurrency: int = 4,
    ) -> list[MetricResult]:
        """Schedule per-case evaluations grouped by retrieved context digest under max_concurrency."""
```

### Built-In Judge Metrics & Functional Factories

```python
class GroundednessMetric(BaseJudgeMetric):
    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None: ...


class AnswerRelevanceMetric(BaseJudgeMetric):
    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None: ...


class ContextRelevanceMetric(BaseJudgeMetric):
    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None: ...


class AnswerCorrectnessMetric(BaseJudgeMetric):
    def __init__(
        self,
        *,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None: ...


class CustomRubricJudgeMetric(BaseJudgeMetric):
    """Custom prompt-rubric judge; raises MetricError if rubric, metric_id, or metric_version is blank."""

    def __init__(
        self,
        rubric: str,
        *,
        metric_id: str = "custom_rubric",
        metric_version: str = "1.0.0",
        what_it_measures: str = "Evaluates target outputs against a caller-defined rubric.",
        require_reference: bool = False,
        require_context: bool = False,
        config: JudgeConfig | None = None,
        api_key: str | None = None,
        mock_responses: Mapping[str, str | Sequence[str]] | None = None,
        completion_fn: CompletionFn | None = None,
    ) -> None: ...


# Factory functions matching deterministic/IR metric module ergonomics
def groundedness(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> GroundednessMetric: ...


def answer_relevance(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> AnswerRelevanceMetric: ...


def context_relevance(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> ContextRelevanceMetric: ...


def answer_correctness(
    *,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> AnswerCorrectnessMetric: ...


def custom_rubric_judge(
    rubric: str,
    *,
    metric_id: str = "custom_rubric",
    metric_version: str = "1.0.0",
    what_it_measures: str = "Evaluates target outputs against a caller-defined rubric.",
    require_reference: bool = False,
    require_context: bool = False,
    config: JudgeConfig | None = None,
    api_key: str | None = None,
    mock_responses: Mapping[str, str | Sequence[str]] | None = None,
    completion_fn: CompletionFn | None = None,
) -> CustomRubricJudgeMetric: ...
```

---

## 2. Judge Calibration Entrypoints (`evalforge_maestro.judges.calibration`)

```python
async def acalibrate_judge(
    judge: Metric,
    samples: Sequence[HumanCalibrationSample],
    *,
    human_threshold: float | None = None,
    score_divergence_threshold: float = 0.25,
    max_concurrency: int = 4,
) -> CalibrationReport:
    """Asynchronously calibrate a judge metric against human ground-truth samples."""


def calibrate_judge(
    judge: Metric,
    samples: Sequence[HumanCalibrationSample],
    *,
    human_threshold: float | None = None,
    score_divergence_threshold: float = 0.25,
    max_concurrency: int = 4,
) -> CalibrationReport:
    """Synchronously calibrate a judge metric against human ground-truth samples."""
```

Raises:
- `EmptyDatasetError` if `samples` is empty.
- `DuplicateCaseIdError` if duplicate `HumanCalibrationSample.case_id` values occur.
- `ConfigurationError` if `score_divergence_threshold <= 0.0` or `> 1.0`, `human_threshold` is invalid, or `max_concurrency < 1`.
- `LocalOnlyPolicyError` / `MissingExtraError` propagated immediately when global policy or missing `[judges]` extra prevents live execution.

---

## 3. Orchestrator Integration Behavior (`EvaluationOrchestrator`)

No breaking changes to `EvaluationOrchestrator.__init__`, `arun`, or `run` parameter signatures:
- When `metrics` contains `AsyncBatchMetric` instances, `EvaluationOrchestrator.arun` dispatches them via `await metric.aevaluate_batch(items, max_concurrency=self._config.max_concurrency)` (honoring `fail_fast=True` by checking/aborting on first `INCONCLUSIVE` / failed batch chunk rather than continuing unaffected chunks, alongside truncation after scoring, memory guardrails, and `.evalforge/tmp/<run_id>.jsonl` checkpointing).
- When `self._config.judge_config_fingerprint` is `None` and one or more participating metrics expose a non-null `judge_config_fingerprint`:
  - Single judge metric → `RunRecord.judge_config_fingerprint` and `RunManifestEntry.judge_config_fingerprint` equal that judge's fingerprint.
  - Multiple judge metrics → `RunRecord.judge_config_fingerprint` equals `canonical_sha256({"judges": [[metric_id, fp], ...]})` sorted deterministically by `metric_id`.
- When `self._config.judge_config_fingerprint` is explicitly set, that explicit fingerprint takes precedence cleanly.
