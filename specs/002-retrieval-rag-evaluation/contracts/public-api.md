# Contract: Public Python Library API — Milestone 2 Extensions (`evalforge_maestro`)

**Feature**: `002-retrieval-rag-evaluation` | **Version**: `0.2.0` (M2)

All Milestone 001 signatures remain backwards-compatible; Milestone 002 adds `ExpectedContextItem`, `RAGExtractorConfig`, IR metrics, `RAGAdapter`, `DocpipeAdapter`, and `docpipe` fixture loading pinned in `tests/test_api_stability.py`.

## 0. Canonical M2 Data Contracts (`evalforge_maestro.types`)

```python
class ExpectedContextItem(BaseModel):
    id: str
    text: str | None = None
    relevance: int = 1


class RAGExtractorConfig(BaseModel):
    output: str | Callable[[Any], Any] | None = None
    chunks: str | Callable[[Any], Any] | None = None
    chunk_id: str | Callable[[Any], Any] | None = None
    chunk_text: str | Callable[[Any], Any] | None = None
    chunk_parent_id: str | Callable[[Any], Any] | None = None
    chunk_rank: str | Callable[[Any], Any] | None = None
    chunk_score: str | Callable[[Any], Any] | None = None
    chunk_metadata: str | Callable[[Any], Any] | None = None
    tokens: str | Callable[[Any], Any] | None = None
```

*(Field constraints, defaults, and validators match `specs/002-retrieval-rag-evaluation/data-model.md` and `specs/002-retrieval-rag-evaluation/contracts/schemas-v1.json`.)*

## 1. IR Retrieval Metrics (`evalforge_maestro.metrics`)

```python
class PrecisionAtKMetric:
    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class RecallAtKMetric:
    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class MRRMetric:
    def __init__(
        self,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class NDCGAtKMetric:
    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 0.5,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...


class HitRateAtKMetric:
    def __init__(
        self,
        k: int = 5,
        *,
        match_parent_id: bool = False,
        threshold: float = 1.0,
    ) -> None: ...
    @property
    def metadata(self) -> MetricMetadata: ...
    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult: ...
```

- Convenience singleton exports: `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`, `hit_rate_at_k`.

## 2. Protocol-Based `RAGAdapter` (`evalforge_maestro.adapters`)

```python
class RAGAdapter:
    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        extractors: RAGExtractorConfig | None = None,
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

## 3. Optional `DocpipeAdapter` (`evalforge_maestro.adapters`)

```python
class DocpipeAdapter:
    def __init__(
        self,
        *,
        mode: Literal["answer_detailed", "retrieve"] = "answer_detailed",
        collection: str | None = None,
        persist_dir: Path | str | None = None,
        retrieve_kwargs: Mapping[str, Any] | None = None,
        answer_kwargs: Mapping[str, Any] | None = None,
        system_version: str | None = None,
        model_id: str | None = None,
        client: Any | None = None,
    ) -> None: ...

    @property
    def system_version(self) -> str | None: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def config_fingerprint(self) -> str | None: ...

    async def execute(self, case: EvaluationCase) -> ExecutionResult: ...
```

- Raises `AdapterError` in `__init__` if `mode` is not `"answer_detailed"` or `"retrieve"`.
- When `client is None`, `__init__` lazy-imports `docpipe_maestro` and raises `MissingExtraError(extra="docpipe", package="docpipe-maestro")` if missing.
- Injected `client` must expose `retrieve(...)` (plus `answer_detailed(...)`, and optionally `build_chat_messages(...)` or `build_prompt(...)`, when `mode="answer_detailed"`).
- `case.input` query extraction accepts a non-empty `str` or mapping keys `"question"` -> `"query"` -> `"input"`; invalid/empty inputs capture diagnostics into `ExecutionResult.errors`.
- Option merge & fingerprinting: explicit non-`None` `collection` and `persist_dir` override keys of the same name inside `retrieve_kwargs`; redacted `{mode, collection, persist_dir, retrieve_kwargs, answer_kwargs}` hashes into `config_fingerprint` and `adapter_metadata["config"]`.
- `"retrieve"` mode sets `ExecutionResult.output = None`; `"answer_detailed"` mode maps `GenerationResult.text` -> `output`, token counts -> `TokenUsage`, `truncated` -> `ExecutionResult.truncated`, and `finish_reason` -> `adapter_metadata` / `warnings`.
- Importing `evalforge_maestro` or `evalforge_maestro.adapters` never imports `docpipe_maestro`.

## 4. `docpipe-maestro` Fixture Importer (`evalforge_maestro.datasets`)

```python
def load_docpipe_fixture(
    source: Path | str | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
) -> DatasetEngine: ...
```

- Also exposed via `DatasetEngine.from_docpipe_fixture(source, *, dataset_id=None, dataset_version=None) -> DatasetEngine`.
- Dependency-free JSON/JSONL parsing supporting `docpipe-maestro` `EvalFixture` (`{"collection": ..., "profile": ..., "queries": [{"question": ..., "relevant_ids": [...], "notes": ...}]}`), `{"cases": [...]}`, `{"items": [...]}`, JSON arrays, and JSONL streams.
- Field normalization: `id`/`case_id` -> `EvaluationCase.id` (synthesizing 1-based `f"case-{index}"` when absent/null); `question`/`query`/`input` -> `EvaluationCase.input`; `relevant_ids`/`expected_ids`/`expected_context` -> `EvaluationCase.expected_context`; explicit `reference`/`expected_answer`/`answer` -> `EvaluationCase.reference`; `collection`/`profile`/`notes` stored cleanly in `CaseMetadata` (`source` / `extra`).
