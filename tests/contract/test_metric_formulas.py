"""Contract tests pinning MetricMetadata and AST source hashes of deterministic metrics."""

from __future__ import annotations

import ast
import hashlib
import inspect
from typing import Any

from evalforge_maestro.metrics import (
    ExactMatchMetric,
    HitRateAtKMetric,
    JsonSchemaValidationMetric,
    MRRMetric,
    NDCGAtKMetric,
    NormalizedMatchMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
)
from evalforge_maestro.metrics.deterministic import (
    _normalize_text,
    _resolve_target_schema,
    _score_exact_match,
    _score_json_schema_validation,
    _score_normalized_match,
)
from evalforge_maestro.metrics.retrieval import (
    _prepare_retrieval_inputs,
    _score_hit_rate_at_k,
    _score_mrr,
    _score_ndcg_at_k,
    _score_precision_at_k,
    _score_recall_at_k,
)
from evalforge_maestro.types import Metric

# Pinned SHA-256 hashes of normalized ASTs (docstrings stripped).
# Any modification to deterministic scoring logic MUST bump the corresponding metric_version.
EXPECTED_FORMULA_AST_HASHES: dict[tuple[str, str], str] = {
    ("exact_match", "1.0.0"): ("4e2c429020bbb49b37ecff19e0480cc869157b71d38bb876fe4e5b3dd4d6df13"),
    ("normalized_match", "1.0.0"): (
        "6d86e05e936affc86a5feaa6d51dafc81bb732e951ee7df189851a6fde43dfc2"
    ),
    ("json_schema_validation", "1.0.0"): (
        "f5d6783a33f29cf6e5a69e72398e784083761f2d5524bb92b43c315a2bdda1a4"
    ),
    ("precision_at_k", "1.0.0"): (
        "647f25c7c4295f8ad13f1bdd20afcf616be7c9cecb0ea94f07dc75186896a343"
    ),
    ("recall_at_k", "1.0.0"): ("a011b2e1fdfda561b510cb6f432915ff74bd48b793026f68d866a1997f66f73f"),
    ("hit_rate_at_k", "1.0.0"): (
        "5323a227b47e373a0d31bf5ee57bf2446d44f466dad31c2bfad813eca839592b"
    ),
    ("mrr", "1.0.0"): "4d43b8d4c02395504ab16eefa85b8a4fc28ff33a3387cfb8f89183de3d585882",
    ("ndcg_at_k", "1.0.0"): ("0337f4383b2f4ed8eaa4b9ee7c72e7f813b0d07d26feece0366d7c4b2dabeccb"),
}
EXPECTED_HELPER_AST_HASHES: dict[str, str] = {
    "_normalize_text": "be318295ed05d16e9d248a4d6f271df644211a4250ad5595a76c985dfc2115de",
    "_resolve_target_schema": "de95ff455f316b1cad65316adff6e6b8d645a713b207df921b6663da18292e12",
    "_prepare_retrieval_inputs": (
        "ad58d96712e502921fd495a9836eb92048ad84a9f3386206e94b87da6dff6fe7"
    ),
}


def _strip_docstrings(node: ast.AST) -> ast.AST:
    for child in ast.walk(node):
        if (
            isinstance(child, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and child.body
            and isinstance(child.body[0], ast.Expr)
            and isinstance(child.body[0].value, ast.Constant)
            and isinstance(child.body[0].value.value, str)
        ):
            child.body = child.body[1:]
    return node


def _normalized_ast_hash(obj: Any) -> str:
    src = inspect.getsource(obj)
    tree = _strip_docstrings(ast.parse(src))
    dumped = ast.dump(tree, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def test_deterministic_metric_metadata_and_formula_ast_hashes() -> None:
    metrics_and_fns: list[tuple[Metric, Any]] = [
        (ExactMatchMetric(), _score_exact_match),
        (NormalizedMatchMetric(), _score_normalized_match),
        (JsonSchemaValidationMetric(), _score_json_schema_validation),
        (PrecisionAtKMetric(), _score_precision_at_k),
        (RecallAtKMetric(), _score_recall_at_k),
        (HitRateAtKMetric(), _score_hit_rate_at_k),
        (MRRMetric(), _score_mrr),
        (NDCGAtKMetric(), _score_ndcg_at_k),
    ]
    for metric, fn in metrics_and_fns:
        meta = metric.metadata
        assert meta.metric_id
        assert meta.metric_version
        assert meta.what_it_measures
        assert meta.calculation_method
        assert meta.known_limitations
        assert isinstance(meta.required_case_fields, tuple)
        assert isinstance(meta.required_execution_fields, tuple)

        key = (meta.metric_id, meta.metric_version)
        assert key in EXPECTED_FORMULA_AST_HASHES
        assert _normalized_ast_hash(fn) == EXPECTED_FORMULA_AST_HASHES[key]

    assert _normalized_ast_hash(_normalize_text) == EXPECTED_HELPER_AST_HASHES["_normalize_text"]
    assert (
        _normalized_ast_hash(_resolve_target_schema)
        == EXPECTED_HELPER_AST_HASHES["_resolve_target_schema"]
    )
    assert (
        _normalized_ast_hash(_prepare_retrieval_inputs)
        == EXPECTED_HELPER_AST_HASHES["_prepare_retrieval_inputs"]
    )
