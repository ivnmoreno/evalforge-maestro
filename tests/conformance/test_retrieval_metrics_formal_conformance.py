"""Dual-mode Python-to-Lean 4 conformance suite for deterministic IR retrieval metrics.

Modes:
- Default (offline): validates `PrecisionAtKMetric`, `RecallAtKMetric`, `HitRateAtKMetric`,
  `MRRMetric`, `NDCGAtKMetric`, and `_prepare_retrieval_inputs` deterministically against the
  CI-verified golden retrieval oracle artifact
  (`tests/conformance/golden/retrieval_metrics_oracle.json`) without requiring Lean.
- Live (`pytest --lean-live-oracle`): fail-closed mode that requires the compiled Lean oracle
  executable (`formal/.lake/build/bin/evalforge-retrieval-oracle`), verifies byte-for-byte
  parity with `retrieval_metrics_oracle.json` via `export-golden`, and cross-checks every
  exercised Python scenario directly against `evalforge-retrieval-oracle eval-stdin`.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from evalforge_maestro._canonical import round_score
from evalforge_maestro.metrics import (
    HitRateAtKMetric,
    MRRMetric,
    NDCGAtKMetric,
    PrecisionAtKMetric,
    RecallAtKMetric,
)
from evalforge_maestro.metrics.retrieval import _prepare_retrieval_inputs
from evalforge_maestro.types import (
    CaseCriteria,
    EvaluationCase,
    ExecutionResult,
    ExpectedContextItem,
    Metric,
    MetricResult,
    MetricStatus,
    RetrievedChunk,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_RETRIEVAL_ORACLE_PATH = (
    Path(__file__).resolve().parent / "golden" / "retrieval_metrics_oracle.json"
)
LEAN_TOOLCHAIN_PATH = REPO_ROOT / "formal" / "lean-toolchain"
EXPECTED_SCHEMA_VERSION = "1.0"
EXPECTED_TOOLCHAIN = "leanprover/lean4:v4.36.0"
EXPECTED_GUARD_PRECEDENCE = ["INCONCLUSIVE", "NOT_APPLICABLE", "NUMERIC"]
EXPECTED_METRIC_IDS = ["precision_at_k", "recall_at_k", "hit_rate_at_k", "mrr", "ndcg_at_k"]
EXPECTED_HARMONIC_SCHEDULE = "1/(rank+1)"
VALID_IR_STATUSES = frozenset({"INCONCLUSIVE", "NOT_APPLICABLE", "PASS", "FAIL"})
VALID_PREP_STATUSES = frozenset({"INCONCLUSIVE", "NOT_APPLICABLE", "READY"})


def _validate_exact_rat(raw: Any, *, label: str, unit_bounded: bool = False) -> None:
    assert isinstance(raw, dict), f"{label} must be dict, got {type(raw)}"
    num = raw.get("num")
    den = raw.get("den")
    assert isinstance(num, int) and not isinstance(num, bool) and num >= 0, (
        f"{label}.num must be non-negative int, got {num!r}"
    )
    assert isinstance(den, int) and not isinstance(den, bool) and den >= 1, (
        f"{label}.den must be int >= 1, got {den!r}"
    )
    if unit_bounded:
        assert num <= den, f"{label} must lie in [0, 1], got {num}/{den}"


def _exact_rat_to_float(raw: dict[str, Any]) -> float:
    return float(raw["num"]) / float(raw["den"])


def _exact_rat_to_rounded_score(raw: dict[str, Any] | None) -> float | None:
    if raw is None:
        return None
    return round_score(_exact_rat_to_float(raw))


def _threshold_to_exact_rat(threshold: float) -> dict[str, int]:
    frac = Fraction(str(threshold))
    return {"den": frac.denominator, "num": frac.numerator}


def _validate_metric_eval_json(entry: Any, *, label: str) -> None:
    assert isinstance(entry, dict), f"{label} must be dict"
    status = entry.get("status")
    assert isinstance(status, str) and status in VALID_IR_STATUSES, (
        f"{label}.status invalid: {status!r}"
    )
    score_exact = entry.get("score_exact")
    if status in {"INCONCLUSIVE", "NOT_APPLICABLE"}:
        assert score_exact is None, f"{label}.score_exact must be null for {status}"
    else:
        _validate_exact_rat(score_exact, label=f"{label}.score_exact", unit_bounded=True)
    evidence = entry.get("evidence")
    assert isinstance(evidence, list) and all(isinstance(x, str) for x in evidence), (
        f"{label}.evidence must be list[str]"
    )


def validate_retrieval_golden_artifact(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate `RetrievalGoldenOracleArtifact` structure and return canonical vectors."""
    assert payload.get("schema_version") == EXPECTED_SCHEMA_VERSION, (
        f"Unexpected retrieval golden schema_version: {payload.get('schema_version')!r}"
    )
    toolchain = payload.get("lean_toolchain")
    assert toolchain == EXPECTED_TOOLCHAIN, (
        f"Unexpected retrieval golden lean_toolchain: {toolchain!r}"
    )
    if LEAN_TOOLCHAIN_PATH.exists():
        pinned = LEAN_TOOLCHAIN_PATH.read_text(encoding="utf-8").strip()
        assert toolchain == pinned, (
            f"Golden lean_toolchain {toolchain!r} diverges from formal/lean-toolchain {pinned!r}"
        )

    assert payload.get("guard_precedence_order") == EXPECTED_GUARD_PRECEDENCE
    assert payload.get("metric_ids") == EXPECTED_METRIC_IDS
    assert payload.get("harmonic_discount_schedule") == EXPECTED_HARMONIC_SCHEDULE

    vectors = payload.get("canonical_vectors")
    assert isinstance(vectors, list) and len(vectors) >= 16, (
        f"Expected >= 16 canonical retrieval vectors, got {type(vectors)}"
    )

    seen_ids: set[str] = set()
    for vec in vectors:
        assert isinstance(vec, dict)
        vid = vec.get("vector_id")
        assert isinstance(vid, str) and vid and vid not in seen_ids, f"Bad vector_id: {vid!r}"
        seen_ids.add(vid)

        inp = vec.get("input")
        exp = vec.get("expected")
        assert isinstance(inp, dict) and isinstance(exp, dict)
        assert exp.get("case_id") == vid, (
            f"Vector {vid}: expected.case_id={exp.get('case_id')!r} != vector_id"
        )
        k_val = inp.get("k")
        assert isinstance(k_val, int) and not isinstance(k_val, bool) and k_val >= 1
        assert isinstance(inp.get("match_parent_id"), bool)
        thresholds = inp.get("thresholds")
        assert isinstance(thresholds, dict)
        for m_id in EXPECTED_METRIC_IDS:
            _validate_exact_rat(
                thresholds.get(m_id),
                label=f"{vid}.input.thresholds.{m_id}",
                unit_bounded=True,
            )

        prep_status = exp.get("prep_status")
        assert isinstance(prep_status, str) and prep_status in VALID_PREP_STATUSES
        for m_id in ("precision_at_k", "recall_at_k", "hit_rate_at_k", "mrr"):
            _validate_metric_eval_json(exp.get(m_id), label=f"{vid}.expected.{m_id}")

        ndcg = exp.get("ndcg_at_k")
        assert isinstance(ndcg, dict)
        assert ndcg.get("guard_status") == prep_status
        assert isinstance(ndcg.get("actual_gains"), list)
        assert isinstance(ndcg.get("ideal_gains"), list)
        assert isinstance(ndcg.get("evidence"), list)
        if prep_status == "READY":
            _validate_exact_rat(
                ndcg.get("harmonic_ndcg_exact"),
                label=f"{vid}.expected.ndcg_at_k.harmonic_ndcg_exact",
                unit_bounded=True,
            )
            assert ndcg.get("harmonic_status") in {"PASS", "FAIL"}
        else:
            assert ndcg.get("harmonic_ndcg_exact") is None
            assert ndcg.get("harmonic_status") == prep_status

    return vectors


def load_retrieval_golden_artifact() -> tuple[bytes, dict[str, Any], list[dict[str, Any]]]:
    """Load and validate the checked-in `RetrievalGoldenOracleArtifact`."""
    raw_bytes = GOLDEN_RETRIEVAL_ORACLE_PATH.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))
    assert isinstance(payload, dict)
    vectors = validate_retrieval_golden_artifact(payload)
    return raw_bytes, payload, vectors


def assert_retrieval_golden_parity(expected_bytes: bytes, actual_bytes: bytes) -> None:
    """Assert byte-for-byte deterministic parity between live Lean output and golden JSON."""
    if expected_bytes != actual_bytes:
        raise AssertionError(
            "Retrieval golden oracle artifact drift detected: checked-in "
            f"{GOLDEN_RETRIEVAL_ORACLE_PATH.name} does not match compiled Lean oracle output."
        )


def require_live_retrieval_oracle_binary(raw_path: str | Path) -> Path:
    """Resolve and verify the compiled Lean retrieval oracle binary fail-closed."""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if not candidate.exists() or not candidate.is_file():
        raise AssertionError(
            "Live Lean retrieval oracle mode (--lean-live-oracle) failed closed: binary not "
            f"found at {candidate}. Build it first with `cd formal && lake build`."
        )
    if not os.access(candidate, os.X_OK):
        raise AssertionError(
            "Live Lean retrieval oracle mode (--lean-live-oracle) failed closed: "
            f"{candidate} is not executable."
        )
    return candidate


def resolve_optional_live_retrieval_oracle(request: pytest.FixtureRequest) -> Path | None:
    """Return verified retrieval oracle binary when `--lean-live-oracle` is set, else `None`."""
    if not bool(request.config.getoption("--lean-live-oracle")):
        return None
    bin_opt = str(request.config.getoption("--lean-retrieval-oracle-bin"))
    return require_live_retrieval_oracle_binary(bin_opt)


def run_live_retrieval_oracle_export_golden(oracle_bin: Path) -> bytes:
    """Invoke `evalforge-retrieval-oracle export-golden` fail-closed."""
    proc = subprocess.run(
        [str(oracle_bin), "export-golden"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"evalforge-retrieval-oracle export-golden failed (exit={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout


def run_live_retrieval_oracle_eval_stdin(
    oracle_bin: Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Invoke `evalforge-retrieval-oracle eval-stdin` fail-closed with a batched JSON request."""
    proc = subprocess.run(
        [str(oracle_bin), "eval-stdin"],
        input=json.dumps(request_payload).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"evalforge-retrieval-oracle eval-stdin failed (exit={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    response = json.loads(proc.stdout.decode("utf-8"))
    assert isinstance(response, dict)
    assert response.get("schema_version") == EXPECTED_SCHEMA_VERSION
    return response


def assert_ir_metric_conforms(
    result: MetricResult,
    expected_entry: dict[str, Any],
    *,
    metric_id: str,
    context: str,
) -> None:
    """Compare Python `MetricResult` against exact Lean formal oracle expectation."""
    expected_status = expected_entry["status"]
    expected_score = _exact_rat_to_rounded_score(expected_entry["score_exact"])
    expected_evidence = expected_entry["evidence"]

    if (
        result.status.value != expected_status
        or result.score != expected_score
        or result.evidence != expected_evidence
    ):
        raise AssertionError(
            f"Python-to-Lean retrieval conformance mismatch in {context} ({metric_id}): "
            f"python=(status={result.status.value}, score={result.score!r}, "
            f"evidence={result.evidence!r}), "
            f"formal=(status={expected_status}, score={expected_score!r}, "
            f"evidence={expected_evidence!r})."
        )


def assert_ndcg_conforms(
    result: MetricResult,
    expected_ndcg: dict[str, Any],
    *,
    threshold: float,
    context: str,
) -> None:
    """Compare Python `NDCGAtKMetric` against Lean formal guards, gains, and log2 scoring."""
    guard_status = expected_ndcg["guard_status"]
    expected_evidence = expected_ndcg["evidence"]

    if guard_status in {"INCONCLUSIVE", "NOT_APPLICABLE"}:
        if (
            result.status.value != guard_status
            or result.score is not None
            or result.evidence != expected_evidence
        ):
            raise AssertionError(
                f"Python-to-Lean NDCG guard mismatch in {context}: "
                f"python=(status={result.status.value}, score={result.score!r}, "
                f"evidence={result.evidence!r}), "
                f"formal=(guard={guard_status}, evidence={expected_evidence!r})."
            )
        return

    actual_gains: list[int] = expected_ndcg["actual_gains"]
    ideal_gains: list[int] = expected_ndcg["ideal_gains"]
    dcg = sum(g / math.log2(idx + 1) for idx, g in enumerate(actual_gains, start=1))
    idcg = sum(g / math.log2(idx + 1) for idx, g in enumerate(ideal_gains, start=1))
    assert idcg > 0.0
    expected_score = round_score(dcg / idcg)
    expected_status = MetricStatus.PASS if expected_score >= threshold else MetricStatus.FAIL

    assert result.score is not None and 0.0 <= result.score <= 1.0
    if (
        result.score != expected_score
        or result.status != expected_status
        or result.evidence != expected_evidence
    ):
        raise AssertionError(
            f"Python-to-Lean NDCG mismatch in {context}: "
            f"python=(status={result.status.value}, score={result.score!r}, "
            f"evidence={result.evidence!r}), "
            f"formal_log2=(status={expected_status.value}, score={expected_score!r}, "
            f"evidence={expected_evidence!r}, actual_gains={actual_gains}, "
            f"ideal_gains={ideal_gains})."
        )


def _build_execution_from_input(case_id: str, inp: dict[str, Any]) -> ExecutionResult:
    chunks = [
        RetrievedChunk(
            id=c["id"],
            text=f"text-{c['id']}",
            parent_id=c["parent_id"],
            rank=c["rank"],
        )
        for c in inp["retrieved_chunks"]
    ]
    return ExecutionResult(
        case_id=case_id,
        input="conformance-query",
        retrieved_chunks=chunks,
        elapsed_seconds=0.01,
        errors=list(inp["errors"]),
    )


def _evaluate_python_suite_for_vector(
    case_id: str,
    inp: dict[str, Any],
) -> tuple[dict[str, int], list[str], dict[str, MetricResult]]:
    expected_items: list[str | ExpectedContextItem] = [
        ExpectedContextItem(id=e["id"], relevance=e["relevance"]) for e in inp["expected_context"]
    ]
    case = EvaluationCase(
        id=case_id,
        input="conformance-query",
        expected_context=expected_items,
    )
    execution = _build_execution_from_input(case_id, inp)
    k = int(inp["k"])
    match_parent_id = bool(inp["match_parent_id"])
    thresholds = inp["thresholds"]

    g_pos, ranked_ids = _prepare_retrieval_inputs(
        case,
        execution,
        match_parent_id=match_parent_id,
    )
    metrics: dict[str, Metric] = {
        "precision_at_k": PrecisionAtKMetric(
            k=k,
            match_parent_id=match_parent_id,
            threshold=_exact_rat_to_float(thresholds["precision_at_k"]),
        ),
        "recall_at_k": RecallAtKMetric(
            k=k,
            match_parent_id=match_parent_id,
            threshold=_exact_rat_to_float(thresholds["recall_at_k"]),
        ),
        "hit_rate_at_k": HitRateAtKMetric(
            k=k,
            match_parent_id=match_parent_id,
            threshold=_exact_rat_to_float(thresholds["hit_rate_at_k"]),
        ),
        "mrr": MRRMetric(
            match_parent_id=match_parent_id,
            threshold=_exact_rat_to_float(thresholds["mrr"]),
        ),
        "ndcg_at_k": NDCGAtKMetric(
            k=k,
            match_parent_id=match_parent_id,
            threshold=_exact_rat_to_float(thresholds["ndcg_at_k"]),
        ),
    }
    results = {m_id: metric.evaluate(case, execution) for m_id, metric in metrics.items()}
    return g_pos, ranked_ids, results


def _assert_vector_matches_oracle(
    case_id: str,
    inp: dict[str, Any],
    expected: dict[str, Any],
    *,
    context: str,
) -> None:
    expected_ids = [e["id"] for e in inp["expected_context"]]
    has_dup_expected = len(expected_ids) != len(set(expected_ids))

    if has_dup_expected:
        # Pydantic EvaluationCase rejects duplicate expected_context IDs at schema boundary.
        with pytest.raises(ValidationError, match="Duplicate identifier"):
            EvaluationCase(
                id=case_id,
                input="conformance-query",
                expected_context=[
                    ExpectedContextItem(id=e["id"], relevance=e["relevance"])
                    for e in inp["expected_context"]
                ],
            )
        # Verify _prepare_retrieval_inputs directly matches Lean buildRelevanceMap semantics
        # (last positive overwrites earlier positive; later relevance=0 does not delete).
        stub_case = SimpleNamespace(
            expected_context=[
                ExpectedContextItem(id=e["id"], relevance=e["relevance"])
                for e in inp["expected_context"]
            ]
        )
        execution = _build_execution_from_input(case_id, inp)
        g_pos, ranked_ids = _prepare_retrieval_inputs(
            cast(EvaluationCase, stub_case),
            execution,
            match_parent_id=bool(inp["match_parent_id"]),
        )
        assert g_pos == {entry["id"]: entry["relevance"] for entry in expected["g_pos"]}
        assert ranked_ids == expected["ranked_ids"]
        return

    g_pos, ranked_ids, results = _evaluate_python_suite_for_vector(case_id, inp)
    if expected["prep_status"] == "READY":
        assert g_pos == {entry["id"]: entry["relevance"] for entry in expected["g_pos"]}
        assert ranked_ids == expected["ranked_ids"]
    elif expected["prep_status"] == "NOT_APPLICABLE":
        assert g_pos == {}
        assert ranked_ids == expected["ranked_ids"]

    for m_id in ("precision_at_k", "recall_at_k", "hit_rate_at_k", "mrr"):
        assert_ir_metric_conforms(
            results[m_id],
            expected[m_id],
            metric_id=m_id,
            context=context,
        )
    assert_ndcg_conforms(
        results["ndcg_at_k"],
        expected["ndcg_at_k"],
        threshold=_exact_rat_to_float(inp["thresholds"]["ndcg_at_k"]),
        context=context,
    )


def test_retrieval_golden_artifact_schema_and_live_parity(
    request: pytest.FixtureRequest,
) -> None:
    """Validate checked-in retrieval golden JSON and live `export-golden` byte parity."""
    raw_bytes, _, vectors = load_retrieval_golden_artifact()
    assert len(vectors) >= 16

    oracle_bin = resolve_optional_live_retrieval_oracle(request)
    if oracle_bin is not None:
        live_bytes = run_live_retrieval_oracle_export_golden(oracle_bin)
        assert_retrieval_golden_parity(live_bytes, raw_bytes)


def test_canonical_retrieval_vectors_conformance(request: pytest.FixtureRequest) -> None:
    """Verify all canonical retrieval vectors offline and via live `eval-stdin` when enabled."""
    _, _, vectors = load_retrieval_golden_artifact()

    live_cases: list[dict[str, Any]] = []
    for vec in vectors:
        vid = vec["vector_id"]
        inp = vec["input"]
        _assert_vector_matches_oracle(
            vid,
            inp,
            vec["expected"],
            context=f"golden vector {vid}",
        )
        live_cases.append({"case_id": vid, **inp})

    oracle_bin = resolve_optional_live_retrieval_oracle(request)
    if oracle_bin is not None:
        response = run_live_retrieval_oracle_eval_stdin(
            oracle_bin,
            {"schema_version": EXPECTED_SCHEMA_VERSION, "cases": live_cases},
        )
        by_id = {entry["case_id"]: entry for entry in response["results"]}
        for vec in vectors:
            vid = vec["vector_id"]
            assert by_id[vid] == vec["expected"]
            _assert_vector_matches_oracle(
                vid,
                vec["input"],
                by_id[vid],
                context=f"live-oracle vector {vid}",
            )


def test_cutoff_sweep_monotonicity_and_cross_metric_identities(
    request: pytest.FixtureRequest,
) -> None:
    """Verify cutoff monotonicity (`k=1,2,3,5`), `MRR` independence, and cross-metric laws."""
    expected_ctx_items = [
        ExpectedContextItem(id="d1", relevance=3),
        ExpectedContextItem(id="d2", relevance=2),
        ExpectedContextItem(id="d0", relevance=0),
        ExpectedContextItem(id="d3", relevance=1),
    ]
    expected_ctx: list[str | ExpectedContextItem] = list(expected_ctx_items)
    chunks = [
        RetrievedChunk(id="d9", text="t9", rank=1),
        RetrievedChunk(id="d3", text="t3", rank=2),
        RetrievedChunk(id="d1", text="t1", rank=3),
        RetrievedChunk(id="d0", text="t0", rank=4),
        RetrievedChunk(id="d2", text="t2", rank=5),
    ]
    case = EvaluationCase(id="sweep-case", input="q", expected_context=expected_ctx)
    execution = ExecutionResult(
        case_id="sweep-case",
        input="q",
        retrieved_chunks=chunks,
        elapsed_seconds=0.01,
    )

    cutoffs = (1, 2, 3, 5)
    recalls: list[float] = []
    hit_rates: list[float] = []
    mrr_scores: list[float] = []
    ndcg_scores: list[float] = []
    live_cases: list[dict[str, Any]] = []
    observed_by_k: dict[int, dict[str, MetricResult]] = {}

    for k in cutoffs:
        p = PrecisionAtKMetric(k=k).evaluate(case, execution)
        r = RecallAtKMetric(k=k).evaluate(case, execution)
        hr = HitRateAtKMetric(k=k).evaluate(case, execution)
        m = MRRMetric().evaluate(case, execution)
        n = NDCGAtKMetric(k=k).evaluate(case, execution)
        observed_by_k[k] = {
            "precision_at_k": p,
            "recall_at_k": r,
            "hit_rate_at_k": hr,
            "mrr": m,
            "ndcg_at_k": n,
        }

        assert p.score is not None and 0.0 <= p.score <= 1.0
        assert r.score is not None and 0.0 <= r.score <= 1.0
        assert hr.score in (0.0, 1.0)
        assert m.score is not None and 0.0 <= m.score <= 1.0
        assert n.score is not None and 0.0 <= n.score <= 1.0

        # Cross-metric laws
        assert (hr.score == 1.0) == (p.score > 0.0) == (r.score > 0.0)
        if hr.score == 1.0:
            assert m.score >= round_score(1.0 / k)

        recalls.append(r.score)
        hit_rates.append(hr.score)
        mrr_scores.append(m.score)
        ndcg_scores.append(n.score)

        live_cases.append(
            {
                "case_id": f"sweep_k{k}",
                "errors": [],
                "expected_context": [
                    {"id": e.id, "relevance": e.relevance} for e in expected_ctx_items
                ],
                "retrieved_chunks": [
                    {"id": c.id, "parent_id": c.parent_id, "rank": c.rank} for c in chunks
                ],
                "k": k,
                "match_parent_id": False,
                "thresholds": {
                    "precision_at_k": _threshold_to_exact_rat(0.5),
                    "recall_at_k": _threshold_to_exact_rat(0.5),
                    "hit_rate_at_k": _threshold_to_exact_rat(1.0),
                    "mrr": _threshold_to_exact_rat(0.5),
                    "ndcg_at_k": _threshold_to_exact_rat(0.5),
                },
            }
        )

    # Monotonicity in K and MRR independence from K
    assert recalls == sorted(recalls)
    assert hit_rates == sorted(hit_rates)
    assert len(set(mrr_scores)) == 1 and mrr_scores[0] == 0.5  # first relevant hit at rank 2
    assert hit_rates[0] == 0.0 and mrr_scores[0] == 0.5  # k=1 misses rank-2 hit, MRR unaffected

    oracle_bin = resolve_optional_live_retrieval_oracle(request)
    if oracle_bin is not None:
        resp = run_live_retrieval_oracle_eval_stdin(
            oracle_bin,
            {"schema_version": EXPECTED_SCHEMA_VERSION, "cases": live_cases},
        )
        by_id = {entry["case_id"]: entry for entry in resp["results"]}
        for k in cutoffs:
            expected = by_id[f"sweep_k{k}"]
            for m_id in ("precision_at_k", "recall_at_k", "hit_rate_at_k", "mrr"):
                assert_ir_metric_conforms(
                    observed_by_k[k][m_id],
                    expected[m_id],
                    metric_id=m_id,
                    context=f"live sweep k={k}",
                )
            assert_ndcg_conforms(
                observed_by_k[k]["ndcg_at_k"],
                expected["ndcg_at_k"],
                threshold=0.5,
                context=f"live sweep k={k}",
            )


def test_threshold_precedence_and_string_none_expected_context(
    request: pytest.FixtureRequest,
) -> None:
    """Verify threshold precedence, `threshold=0.0` pass on `score=0.0`, `str` & `None` context."""
    case_override = EvaluationCase(
        id="thresh-override",
        input="q",
        expected_context=["d1", ExpectedContextItem(id="d2", relevance=2)],
        criteria=CaseCriteria(
            pass_threshold=0.8,
            metric_thresholds={"precision_at_k": 0.4, "recall_at_k": 0.5},
        ),
    )
    exec_hit = ExecutionResult(
        case_id="thresh-override",
        input="q",
        retrieved_chunks=[
            RetrievedChunk(id="d1", text="t1", rank=1),
            RetrievedChunk(id="d9", text="t9", rank=2),
        ],
        elapsed_seconds=0.01,
    )
    p_res = PrecisionAtKMetric(k=2, threshold=0.9).evaluate(case_override, exec_hit)
    r_res = RecallAtKMetric(k=2, threshold=0.9).evaluate(case_override, exec_hit)
    hr_res = HitRateAtKMetric(k=2, threshold=1.0).evaluate(case_override, exec_hit)
    m_res = MRRMetric(threshold=0.5).evaluate(case_override, exec_hit)
    n_res = NDCGAtKMetric(k=2, threshold=0.5).evaluate(case_override, exec_hit)

    assert p_res.config_snapshot["threshold"] == 0.4 and p_res.status == MetricStatus.PASS
    assert r_res.config_snapshot["threshold"] == 0.5 and r_res.status == MetricStatus.PASS
    assert hr_res.config_snapshot["threshold"] == 0.8 and hr_res.status == MetricStatus.PASS
    assert m_res.config_snapshot["threshold"] == 0.8 and m_res.status == MetricStatus.PASS
    assert n_res.config_snapshot["threshold"] == 0.8 and n_res.status == MetricStatus.FAIL

    # expected_context=None -> NOT_APPLICABLE across all 5 metrics
    none_case = EvaluationCase(id="none-gt", input="q", expected_context=None)
    for metric in (
        PrecisionAtKMetric(k=3),
        RecallAtKMetric(k=3),
        HitRateAtKMetric(k=3),
        MRRMetric(),
        NDCGAtKMetric(k=3),
    ):
        res = metric.evaluate(none_case, exec_hit)
        assert res.status == MetricStatus.NOT_APPLICABLE
        assert res.score is None

    # Zero threshold with zero hits -> PASS (0.0 >= 0.0)
    zero_case = EvaluationCase(
        id="zero-thresh",
        input="q",
        expected_context=["d1"],
        criteria=CaseCriteria(pass_threshold=0.0),
    )
    empty_exec = ExecutionResult(case_id="zero-thresh", input="q", elapsed_seconds=0.01)
    for metric in (
        PrecisionAtKMetric(k=3),
        RecallAtKMetric(k=3),
        HitRateAtKMetric(k=3),
        MRRMetric(),
        NDCGAtKMetric(k=3),
    ):
        res = metric.evaluate(zero_case, empty_exec)
        assert res.score == 0.0
        assert res.status == MetricStatus.PASS

    oracle_bin = resolve_optional_live_retrieval_oracle(request)
    if oracle_bin is not None:
        resp = run_live_retrieval_oracle_eval_stdin(
            oracle_bin,
            {
                "schema_version": EXPECTED_SCHEMA_VERSION,
                "cases": [
                    {
                        "case_id": "thresh-override",
                        "errors": [],
                        "expected_context": [
                            {"id": "d1", "relevance": 1},
                            {"id": "d2", "relevance": 2},
                        ],
                        "retrieved_chunks": [
                            {"id": "d1", "parent_id": None, "rank": 1},
                            {"id": "d9", "parent_id": None, "rank": 2},
                        ],
                        "k": 2,
                        "match_parent_id": False,
                        "thresholds": {
                            "precision_at_k": _threshold_to_exact_rat(0.4),
                            "recall_at_k": _threshold_to_exact_rat(0.5),
                            "hit_rate_at_k": _threshold_to_exact_rat(0.8),
                            "mrr": _threshold_to_exact_rat(0.8),
                            "ndcg_at_k": _threshold_to_exact_rat(0.8),
                        },
                    },
                    {
                        "case_id": "none-gt",
                        "errors": [],
                        "expected_context": [],
                        "retrieved_chunks": [
                            {"id": "d1", "parent_id": None, "rank": 1},
                            {"id": "d9", "parent_id": None, "rank": 2},
                        ],
                        "k": 3,
                        "match_parent_id": False,
                        "thresholds": {
                            "precision_at_k": _threshold_to_exact_rat(0.5),
                            "recall_at_k": _threshold_to_exact_rat(0.5),
                            "hit_rate_at_k": _threshold_to_exact_rat(1.0),
                            "mrr": _threshold_to_exact_rat(0.5),
                            "ndcg_at_k": _threshold_to_exact_rat(0.5),
                        },
                    },
                ],
            },
        )
        by_id = {entry["case_id"]: entry for entry in resp["results"]}
        assert_ir_metric_conforms(
            p_res,
            by_id["thresh-override"]["precision_at_k"],
            metric_id="precision_at_k",
            context="live",
        )
        assert_ir_metric_conforms(
            r_res, by_id["thresh-override"]["recall_at_k"], metric_id="recall_at_k", context="live"
        )
        assert_ir_metric_conforms(
            hr_res,
            by_id["thresh-override"]["hit_rate_at_k"],
            metric_id="hit_rate_at_k",
            context="live",
        )
        assert_ir_metric_conforms(
            m_res, by_id["thresh-override"]["mrr"], metric_id="mrr", context="live"
        )
        assert_ndcg_conforms(
            n_res, by_id["thresh-override"]["ndcg_at_k"], threshold=0.8, context="live"
        )
        assert by_id["none-gt"]["prep_status"] == "NOT_APPLICABLE"


def test_negative_drift_tampered_golden_and_fail_closed_oracle(
    request: pytest.FixtureRequest,
) -> None:
    """Confirm conformance catches Python drift, tampered golden JSON, and missing binary."""
    raw_bytes, payload, vectors = load_retrieval_golden_artifact()

    # 1. Simulated Python discrepancy (skipping deduplication inflates Precision@3 to 1.0 != 1/3)
    dup_vec = next(v for v in vectors if v["vector_id"] == "duplicate_chunk_ids_anti_inflation")
    drifted_result = MetricResult(
        metric_id="precision_at_k",
        metric_version="1.0.0",
        score=1.0,
        status=MetricStatus.PASS,
        explanation="simulated missing deduplication bug",
        evidence=["d1", "d1", "d1"],
    )
    with pytest.raises(AssertionError, match="Python-to-Lean retrieval conformance mismatch"):
        assert_ir_metric_conforms(
            drifted_result,
            dup_vec["expected"]["precision_at_k"],
            metric_id="precision_at_k",
            context="negative_drift_dedup_probe",
        )

    # 2. Simulated wrong guard precedence (NOT_APPLICABLE instead of INCONCLUSIVE)
    err_vec = next(v for v in vectors if v["vector_id"] == "guard_errors_with_empty_gt")
    wrong_guard = MetricResult(
        metric_id="ndcg_at_k",
        metric_version="1.0.0",
        score=None,
        status=MetricStatus.NOT_APPLICABLE,
        explanation="simulated inverted guard bug",
        evidence=[],
    )
    with pytest.raises(AssertionError, match="Python-to-Lean NDCG guard mismatch"):
        assert_ndcg_conforms(
            wrong_guard,
            err_vec["expected"]["ndcg_at_k"],
            threshold=0.5,
            context="negative_drift_guard_probe",
        )

    # 3. Tampered golden artifact schema & byte parity rejection
    tampered_schema = copy.deepcopy(payload)
    tampered_schema["schema_version"] = "9.9"
    with pytest.raises(AssertionError, match="Unexpected retrieval golden schema_version"):
        validate_retrieval_golden_artifact(tampered_schema)

    tampered_bound = copy.deepcopy(payload)
    tampered_bound["canonical_vectors"][0]["input"]["thresholds"]["precision_at_k"] = {
        "den": 1,
        "num": 2,
    }
    with pytest.raises(AssertionError, match="must lie in \\[0, 1\\]"):
        validate_retrieval_golden_artifact(tampered_bound)

    tampered_bytes = raw_bytes.replace(b'"INCONCLUSIVE"', b'"PASS"', 1)
    with pytest.raises(AssertionError, match="Retrieval golden oracle artifact drift detected"):
        assert_retrieval_golden_parity(raw_bytes, tampered_bytes)

    # 4. Fail-closed missing binary check (never silently falls back)
    with pytest.raises(AssertionError, match="failed closed"):
        require_live_retrieval_oracle_binary("/nonexistent/path/evalforge-retrieval-oracle")

    # 5. Live oracle error handling & parity under --lean-live-oracle
    oracle_bin = resolve_optional_live_retrieval_oracle(request)
    if oracle_bin is not None:
        live_bytes = run_live_retrieval_oracle_export_golden(oracle_bin)
        with pytest.raises(AssertionError, match="Retrieval golden oracle artifact drift detected"):
            assert_retrieval_golden_parity(live_bytes, tampered_bytes)

        # Malformed k = 0 must exit non-zero
        bad_req = {
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "cases": [
                {
                    "case_id": "bad-k",
                    "errors": [],
                    "expected_context": [{"id": "d1", "relevance": 1}],
                    "retrieved_chunks": [],
                    "k": 0,
                    "match_parent_id": False,
                    "thresholds": {
                        "precision_at_k": {"den": 2, "num": 1},
                        "recall_at_k": {"den": 2, "num": 1},
                        "hit_rate_at_k": {"den": 1, "num": 1},
                        "mrr": {"den": 2, "num": 1},
                        "ndcg_at_k": {"den": 2, "num": 1},
                    },
                }
            ],
        }
        with pytest.raises(AssertionError, match="eval-stdin failed"):
            run_live_retrieval_oracle_eval_stdin(oracle_bin, bad_req)
