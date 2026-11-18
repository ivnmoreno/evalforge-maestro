# Contract: Public Python Library API (`evalforge_maestro`)

**Feature**: `001-evaluation-foundation` | **Version**: `0.1.0` (M1)

All public symbols exported by `evalforge_maestro` and its M1 submodules MUST preserve stable signatures verified by `tests/test_api_stability.py`.

## 1. Exception Hierarchy (`evalforge_maestro.exceptions`)

```text
Exception
└── EvalforgeError(Exception)
    ├── ConfigurationError(EvalforgeError)
    ├── MissingExtraError(EvalforgeError)
    ├── DatasetError(EvalforgeError)
    │   ├── EmptyDatasetError(DatasetError)
    │   └── DuplicateCaseIdError(DatasetError)
    ├── AdapterError(EvalforgeError)
    ├── MetricError(EvalforgeError)
    ├── ExecutionError(EvalforgeError)
    │   └── MemoryLimitExceededError(ExecutionError)
    └── StorageError(EvalforgeError)
        └── ImmutabilityError(StorageError)
```

## 2. Protocols (`evalforge_maestro.types`)

### `TargetAdapter`

```python
class TargetAdapter(Protocol):
    @property
    def system_version(self) -> str | None: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def config_fingerprint(self) -> str | None: ...

    async def execute(self, case: EvaluationCase) -> ExecutionResult: ...
```

### `Metric`

```python
class Metric(Protocol):
    @property
    def metadata(self) -> MetricMetadata: ...

    def evaluate(
        self,
        case: EvaluationCase,
        execution: ExecutionResult,
    ) -> MetricResult: ...
```

## 3. Dataset Engine (`evalforge_maestro.datasets`)

```python
class DatasetStreamResult(BaseModel):
    dataset_id: str
    dataset_version: str | None
    dataset_fingerprint: str
    evaluated_case_count: int
    dataset_capped: bool
    max_dataset_cases: int | None


class DatasetEngine:
    def __init__(
        self,
        source: Path | str | Iterable[EvaluationCase | Mapping[str, Any]],
        *,
        dataset_id: str | None = None,
        dataset_version: str | None = None,
    ) -> None: ...

    def iter_cases(
        self,
        *,
        max_cases: int | None = None,
        on_complete: Callable[[DatasetStreamResult], None] | None = None,
    ) -> Iterator[EvaluationCase]: ...

    def fingerprint(self, *, max_cases: int | None = None) -> DatasetStreamResult: ...
```

- `iter_cases` yields validated `EvaluationCase` instances lazily, raises `DuplicateCaseIdError` immediately on repeat `id`, raises `DatasetError` (including line number / case ID / field) on malformed JSON or invalid schema, and raises `EmptyDatasetError` if zero valid cases are read.
- `dataset_id` defaults to `Path(source).stem` (if non-empty) for filesystem sources or `"in-memory"` for arbitrary `Iterable` sources when omitted; explicit empty/whitespace `dataset_id` raises `DatasetError`.
- When `max_cases` is reached, `iter_cases` peeks at most one subsequent non-blank line without parsing or scanning unread tail records so `dataset_capped` is `True` if and only if unread cases remain before EOF.

## 4. Target Adapter (`evalforge_maestro.adapters`)

```python
class CallableAdapter:
    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        system_version: str | None = None,
        model_id: str | None = None,
        config: Mapping[str, Any] | None = None,
        pass_case: bool = False,
        input_mapper: Callable[[EvaluationCase], Any] | None = None,
    ) -> None: ...

    @property
    def system_version(self) -> str | None: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def config_fingerprint(self) -> str | None: ...

    async def execute(self, case: EvaluationCase) -> ExecutionResult: ...
```

- Supports both sync callables (offloaded via `asyncio.to_thread`) and async callables (`async def` or return-value awaitables).
- Sensitive config keys (`api_key`, `token`, `secret`, `password`, `authorization`, `credential`, etc.) are redacted before `config_fingerprint` calculation and metadata embedding.

## 5. Deterministic Baseline Metrics (`evalforge_maestro.metrics`)

```python
class ExactMatchMetric:
    def __init__(self, *, threshold: float = 1.0) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class NormalizedMatchMetric:
    def __init__(
        self,
        *,
        case_sensitive: bool = False,
        strip_punctuation: bool = False,
        threshold: float = 1.0,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class JsonSchemaValidationMetric:
    def __init__(
        self,
        *,
        schema: Mapping[str, Any] | None = None,
        threshold: float = 1.0,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...
```

- Convenience functional aliases / factory exports: `exact_match`, `normalized_match`, `json_schema_validation`.
- Threshold resolution precedence inside `evaluate(case, execution)`: `case.criteria.metric_thresholds.get(metric_id)` > `case.criteria.pass_threshold` > metric `threshold` (`1.0`).

## 6. Evaluation Orchestrator (`evalforge_maestro.execution`)

```python
class EvaluationOrchestrator:
    def __init__(
        self,
        *,
        config: OrchestratorConfig | None = None,
        storage_root: Path | str | None = None,
    ) -> None: ...

    async def arun(
        self,
        dataset: DatasetEngine,
        adapter: TargetAdapter,
        metrics: Sequence[Metric],
        *,
        run_id: str | None = None,
    ) -> RunRecord: ...

    def run(
        self,
        dataset: DatasetEngine,
        adapter: TargetAdapter,
        metrics: Sequence[Metric],
        *,
        run_id: str | None = None,
    ) -> RunRecord: ...
```

- `storage_root` defaults to `Path.cwd() / ".evalforge"` when omitted.
- Passing `storage_root` explicitly enables isolated tests (`tmp_path / ".evalforge"`).

## 7. Immutable Local Storage (`evalforge_maestro.storage`)

```python
class LocalRunStore:
    def __init__(self, root: Path | str = Path(".evalforge")) -> None: ...

    def checkpoint_path(self, run_id: str) -> Path: ...
    def run_path(self, run_id: str) -> Path: ...
    def manifest_path(self) -> Path: ...

    def append_checkpoint(self, run_id: str, record: CaseEvaluationRecord) -> None: ...
    def read_checkpoints(self, run_id: str) -> list[CaseEvaluationRecord]: ...
    def remove_checkpoint(self, run_id: str) -> None: ...

    def save_run(self, record: RunRecord) -> Path: ...
    def load_run(self, run_id: str) -> RunRecord: ...
    def read_manifest(self) -> list[RunManifestEntry]: ...
```

- `save_run` commits `.evalforge/runs/<run_id>.json` atomically without overwrite (raising `ImmutabilityError` if `run_id` exists) and appends `RunManifestEntry` to `.evalforge/manifest.jsonl`.
