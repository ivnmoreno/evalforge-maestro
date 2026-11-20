"""Contract tests pinning MetricMetadata and AST source hashes of deterministic metrics."""

from __future__ import annotations

import ast
import hashlib
import inspect
from typing import Any

from evalforge_maestro.metrics import (
    ArgumentCorrectnessMetric,
    ExactMatchMetric,
    ExecutionSequenceMetric,
    FailureRecoveryMetric,
    HitRateAtKMetric,
    JsonSchemaValidationMetric,
    MRRMetric,
    NDCGAtKMetric,
    NormalizedMatchMetric,
    PolicyComplianceMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
    ToolEfficiencyMetric,
    ToolSelectionMetric,
)
from evalforge_maestro.metrics.agent import (
    _ordered_expected_tools,
    _prepare_agent_inputs,
    _score_argument_correctness,
    _score_execution_sequence,
    _score_failure_recovery,
    _score_policy_compliance,
    _score_single_call_args,
    _score_tool_efficiency,
    _score_tool_selection,
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

# Pinned SHA-256 hashes of normalized ASTs (docstrings stripped, Python 3.10-3.13 invariant).
# Any modification to deterministic scoring logic MUST bump the corresponding metric_version.
EXPECTED_FORMULA_AST_HASHES: dict[tuple[str, str], str] = {
    ("exact_match", "1.0.0"): ("4fdac336567ac2a403c118070b97aa43917798e5fda6ca1b7005de8ed6ab92ea"),
    ("normalized_match", "1.0.0"): (
        "45dd7845ee5e3fa9031b54017e2620f9c2abe60233ab921819a6521b04266fc5"
    ),
    ("json_schema_validation", "1.0.0"): (
        "539c55a5b0f16ee8eaacae97003221a784ce73781d66413949874e64f8e0f727"
    ),
    ("precision_at_k", "1.0.0"): (
        "7e42229f53cc3a008066caa1f2efe05067bdf7cab109b0492a121dc1d5f84bc2"
    ),
    ("recall_at_k", "1.0.0"): ("fa32c7ba71d5b0258bcdcd9dd1141a95a381eb4606643ad7d43e1df1ca6e89ce"),
    ("hit_rate_at_k", "1.0.0"): (
        "a64f08aee9a2805fa970e881a19e9d265f695166c9998d92ab2c68deb9543e13"
    ),
    ("mrr", "1.0.0"): "ae08798fe2bebf8c77e1829c701ef14d3dc7cd4bb603f96ae1043b9f6b34e06d",
    ("ndcg_at_k", "1.0.0"): ("baeb50d3cd6caa6df1da49a69c87825507b39d31ac5c09216f61547d745fc72d"),
    ("tool_selection", "1.0.0"): (
        "d072c1bb422fa12a6760fc77ea53e950d857ee42aaefa13215c1f2e874103fcf"
    ),
    ("argument_correctness", "1.0.0"): (
        "909e1e038bbc81a7e9583ad78530b8a5df4dfa5e4e535f7da055683e4ecf6cc3"
    ),
    ("execution_sequence", "1.0.0"): (
        "ccce1917b51a1fb6e05e7eb5791c6385c7e52b1cda93b890807511c2150a0bf5"
    ),
    ("tool_efficiency", "1.0.0"): (
        "eb758982365a75ce62e52cd9e3e9e5d35d6e04f7491124552b622cbe83ecb925"
    ),
    ("policy_compliance", "1.0.0"): (
        "79a9eaf3f49aa7fb94ee78d932b167bde1439ca6685b173006c9ced587d48197"
    ),
    ("failure_recovery", "1.0.0"): (
        "4df4e5ec3e4c9fa5e232edba07bb5a84571e3f91668c66fd6c1a166d4f3f8dbb"
    ),
}
EXPECTED_HELPER_AST_HASHES: dict[str, str] = {
    "_normalize_text": "4f43cd1a8b68d4f56128c79deb226d67e0e8848539574af47634f665624458e0",
    "_resolve_target_schema": "7c71a769e183e610a23b6c83917f2e46c9b05f7e3c6584d0f32611a10cdda4d2",
    "_prepare_retrieval_inputs": (
        "1442a4c60f3622560cfeb440fd18dbbad2c795f91de1eb2ad5031333cb783e00"
    ),
    "_prepare_agent_inputs": ("8d2c5a05bafbb1a85c1d4909450d9a6399b43fc9f65bf728ee5ea8a0269dad93"),
    "_ordered_expected_tools": ("4553a10e73a1ee9c92e8d1f9de6d2fcf9360e027aa8fefd10181929c8338efd9"),
    "_score_single_call_args": ("52594bd8d5c3a2b64902e919fb9ea25b2f6c559f2765d25a148c5f7aadb5b76d"),
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


def _canonical_ast(node: object) -> str:
    if isinstance(node, ast.AST):
        parts: list[str] = []
        for field, val in ast.iter_fields(node):
            # Ignore empty version-specific AST fields added in Python 3.12+ (e.g. type_params).
            if field == "type_params" and val == []:
                continue
            parts.append(f"{field}={_canonical_ast(val)}")
        return f"{type(node).__name__}({', '.join(parts)})"
    if isinstance(node, list):
        return "[" + ", ".join(_canonical_ast(item) for item in node) + "]"
    return repr(node)


def _normalized_ast_hash(obj: Any) -> str:
    src = inspect.getsource(obj)
    tree = _strip_docstrings(ast.parse(src))
    dumped = _canonical_ast(tree)
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
        (ToolSelectionMetric(), _score_tool_selection),
        (ArgumentCorrectnessMetric(), _score_argument_correctness),
        (ExecutionSequenceMetric(), _score_execution_sequence),
        (ToolEfficiencyMetric(), _score_tool_efficiency),
        (PolicyComplianceMetric(), _score_policy_compliance),
        (FailureRecoveryMetric(), _score_failure_recovery),
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
    assert (
        _normalized_ast_hash(_prepare_agent_inputs)
        == EXPECTED_HELPER_AST_HASHES["_prepare_agent_inputs"]
    )
    assert (
        _normalized_ast_hash(_ordered_expected_tools)
        == EXPECTED_HELPER_AST_HASHES["_ordered_expected_tools"]
    )
    assert (
        _normalized_ast_hash(_score_single_call_args)
        == EXPECTED_HELPER_AST_HASHES["_score_single_call_args"]
    )
