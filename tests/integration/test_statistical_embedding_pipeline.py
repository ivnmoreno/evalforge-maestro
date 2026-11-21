"""Integration tests for embedding metrics, security exits, --repeats cohorts, and compare."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.cli import main as cli_main
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    CLIErrorPayload,
    GateDecision,
    ReportDocument,
    SignificanceStatus,
    StatisticalMethod,
)


def _run_cli(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    capsys.readouterr()
    code = cli_main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _ensure_numpy_for_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("numpy") is not None:
        return

    class _Vector:
        def __init__(self, data: Sequence[float]) -> None:
            self._data = [float(x) for x in data]

        @property
        def ndim(self) -> int:
            return 1

        @property
        def shape(self) -> tuple[int, ...]:
            return (len(self._data),)

        def __len__(self) -> int:
            return len(self._data)

        def __iter__(self) -> Any:
            return iter(self._data)

        def __getitem__(self, idx: int) -> float:
            return self._data[idx]

        def __setitem__(self, idx: int, value: float) -> None:
            self._data[idx] = float(value)

        def __truediv__(self, scalar: float) -> _Vector:
            s = float(scalar)
            return _Vector([x / s for x in self._data])

    class _IsFiniteResult:
        def __init__(self, flags: list[bool]) -> None:
            self._flags = flags

        def all(self) -> bool:
            return all(self._flags)

    fake_np = types.ModuleType("numpy")
    fake_np.float64 = float  # type: ignore[attr-defined]
    fake_np.ndarray = _Vector  # type: ignore[attr-defined]

    def _zeros(n: int, dtype: Any = float) -> _Vector:
        _ = dtype
        return _Vector([0.0] * int(n))

    def _asarray(obj: Any, dtype: Any = float) -> _Vector:
        _ = dtype
        if isinstance(obj, _Vector):
            return obj
        return _Vector([float(x) for x in obj])

    def _isfinite(vec: _Vector) -> _IsFiniteResult:
        return _IsFiniteResult([math.isfinite(x) for x in vec])

    def _dot(a: _Vector, b: _Vector) -> float:
        return float(sum(float(x) * float(y) for x, y in zip(a, b, strict=True)))

    linalg_mod = types.ModuleType("numpy.linalg")
    linalg_mod.norm = lambda v: math.sqrt(sum(x * x for x in v))  # type: ignore[attr-defined]

    fake_np.zeros = _zeros  # type: ignore[attr-defined]
    fake_np.asarray = _asarray  # type: ignore[attr-defined]
    fake_np.array = _asarray  # type: ignore[attr-defined]
    fake_np.isfinite = _isfinite  # type: ignore[attr-defined]
    fake_np.dot = _dot  # type: ignore[attr-defined]
    fake_np.linalg = linalg_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", fake_np)
    monkeypatch.setitem(sys.modules, "numpy.linalg", linalg_mod)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_cli_embedding_mock_and_security_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ds_path = tmp_path / "embed_ds.jsonl"
    exec_path = tmp_path / "embed_exec.jsonl"
    _write_jsonl(
        ds_path,
        [
            {
                "id": "e1",
                "input": "Explain uptime SLA",
                "reference": "99.9% uptime monthly SLA guarantee",
                "criteria": {"mandatory": True},
            },
            {
                "id": "e2",
                "input": "Customer contact?",
                "reference": "Contact support portal",
                "criteria": {"mandatory": False},
            },
        ],
    )
    _write_jsonl(
        exec_path,
        [
            {
                "case_id": "e1",
                "input": "Explain uptime SLA",
                "output": "99.9% uptime monthly SLA guarantee",
                "retrieved_chunks": [
                    {"id": "c1", "text": "99.9% uptime monthly SLA guarantee", "rank": 1}
                ],
                "elapsed_seconds": 0.01,
            },
            {
                "case_id": "e2",
                "input": "Customer contact?",
                "output": "Contact support portal alice@example.com",
                "retrieved_chunks": [{"id": "c2", "text": "Contact support portal", "rank": 1}],
                "elapsed_seconds": 0.01,
            },
        ],
    )

    # Missing [embeddings] in --mock still fails fast with exit code 3 when numpy unavailable
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "numpy", None)
        miss_code, miss_out, _ = _run_cli(
            [
                "run",
                "--storage-dir",
                str(tmp_path / "store_miss"),
                "--dataset",
                str(ds_path),
                "--executions",
                str(exec_path),
                "--metric",
                "embedding_similarity",
                "--mock",
                "--json",
            ],
            capsys,
        )
        assert miss_code == 3
        miss_err = CLIErrorPayload.model_validate_json(miss_out)
        assert "embeddings" in miss_err.message

        # --local-only remote --embedding-api-base exits with code 4 before scoring
        loc_code, loc_out, _ = _run_cli(
            [
                "run",
                "--storage-dir",
                str(tmp_path / "store_loc"),
                "--dataset",
                str(ds_path),
                "--executions",
                str(exec_path),
                "--metric",
                "embedding_similarity",
                "--embedding-model",
                "openai/text-embedding-3-small",
                "--embedding-api-base",
                "https://api.openai.com/v1",
                "--local-only",
                "--json",
            ],
            capsys,
        )
        assert loc_code == 4
        assert CLIErrorPayload.model_validate_json(loc_out).exit_code == 4

        # --block-pii remote --embedding-api-base exits with code 4 on PII
        pii_code, pii_out, _ = _run_cli(
            [
                "run",
                "--storage-dir",
                str(tmp_path / "store_pii"),
                "--dataset",
                str(ds_path),
                "--executions",
                str(exec_path),
                "--metric",
                "embedding_similarity",
                "--embedding-model",
                "openai/text-embedding-3-small",
                "--embedding-api-base",
                "https://api.openai.com/v1",
                "--block-pii",
                "--json",
            ],
            capsys,
        )
        assert pii_code == 4
        assert CLIErrorPayload.model_validate_json(pii_out).exit_code == 4

    # Offline mock embedding pipeline with numpy present
    _ensure_numpy_for_integration(monkeypatch)
    ok_code, ok_out, ok_err = _run_cli(
        [
            "run",
            "--storage-dir",
            str(tmp_path / "store_ok"),
            "--dataset",
            str(ds_path),
            "--executions",
            str(exec_path),
            "--metric",
            "embedding_similarity:pass_threshold=0.5",
            "--metric",
            "context_embedding_similarity:aggregation=mean,pass_threshold=0.5",
            "--mock",
            "--local-only",
            "--embedding-max-input-chars",
            "200",
            "--run-id",
            "emb-mock-run",
            "--json",
        ],
        capsys,
    )
    assert ok_code == 0, f"{ok_err}\n{ok_out}"
    doc = ReportDocument.model_validate_json(ok_out)
    assert doc.evaluation is not None
    assert doc.evaluation.embedding_config_fingerprint is not None
    assert doc.evaluation.case_results[0].metrics["embedding_similarity"].score == 1.0
    mean_emb = doc.evaluation.aggregates["embedding_similarity"].mean_score
    assert mean_emb is not None and mean_emb >= 0.7
    assert doc.evaluation.aggregates["context_embedding_similarity"].mean_score is not None
    assert doc.gate is not None and doc.gate.decision == GateDecision.PASS


@pytest.mark.gate_immutability
def test_cli_repeats_cohort_immutability_and_compare_cohorts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_mod = tmp_path / "cohort_target.py"
    target_mod.write_text(
        "def good_target(prompt: str) -> str:\n"
        "    return '99.9%' if 'uptime' in prompt.lower() else '24/7 enterprise'\n"
        "\n"
        "def weak_target(prompt: str) -> str:\n"
        "    return 'unknown'\n"
        "\n"
        "_CALL_COUNT = 0\n"
        "\n"
        "def flaky_mandatory_target(prompt: str) -> str:\n"
        "    global _CALL_COUNT\n"
        "    _CALL_COUNT += 1\n"
        "    if _CALL_COUNT == 1:\n"
        "        return 'flaky-miss'\n"
        "    return '99.9%' if 'uptime' in prompt.lower() else '24/7 enterprise'\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    ds_path = tmp_path / "cohort_ds.jsonl"
    _write_jsonl(
        ds_path,
        [
            {
                "id": f"q{i}",
                "input": "What is uptime SLA?",
                "reference": "99.9%",
                "criteria": {"mandatory": i == 1},
            }
            for i in range(1, 5)
        ],
    )
    storage = tmp_path / "store"

    # Baseline cohort: 2 immutable runs (base-r1 pinned as "v1", base-r2 passed via --baseline-run)
    for b_id in ("base-r1", "base-r2"):
        b_code, _, b_err = _run_cli(
            [
                "run",
                "--storage-dir",
                str(storage),
                "--dataset",
                str(ds_path),
                "--target",
                "cohort_target:good_target",
                "--metric",
                "exact_match",
                "--run-id",
                b_id,
                "--json",
            ],
            capsys,
        )
        assert b_code == 0, b_err

    pin_code, _, pin_err = _run_cli(
        [
            "baseline",
            "set",
            "base-r1",
            "--name",
            "v1",
            "--storage-dir",
            str(storage),
        ],
        capsys,
    )
    assert pin_code == 0, pin_err

    # Candidate repeated run cohort with --repeats 3 --seed 10
    md_out = tmp_path / "cohort_report.md"
    rep_code, rep_out, rep_err = _run_cli(
        [
            "run",
            "--storage-dir",
            str(storage),
            "--dataset",
            str(ds_path),
            "--target",
            "cohort_target:weak_target",
            "--metric",
            "exact_match",
            "--run-id",
            "cand-trial",
            "--repeats",
            "3",
            "--seed",
            "10",
            "--baseline",
            "v1",
            "--baseline-run",
            "base-r2",
            "--confidence-level",
            "0.95",
            "--min-statistical-samples",
            "2",
            "--fail-on-significant-regression",
            "--markdown-out",
            str(md_out),
            "--json",
        ],
        capsys,
    )
    assert rep_code == 1, rep_err
    rep_doc = ReportDocument.model_validate_json(rep_out)
    assert rep_doc.cohort_run_ids == ["cand-trial-r01", "cand-trial-r02", "cand-trial-r03"]
    assert "exact_match" in rep_doc.cohort_aggregates
    assert rep_doc.evaluation is not None
    assert rep_doc.evaluation.run_id == "cand-trial-r03"
    assert rep_doc.evaluation.seed == 12
    assert rep_doc.comparison is not None
    assert rep_doc.comparison.cohort is not None
    assert rep_doc.comparison.cohort.baseline_run_count == 2
    assert rep_doc.comparison.cohort.candidate_run_count == 3
    mc = rep_doc.comparison.metric_comparisons["exact_match"]
    assert mc.statistics is not None
    assert mc.statistics.method == StatisticalMethod.WELCH_T_RUN
    assert mc.statistics.significance == SignificanceStatus.SIGNIFICANT_REGRESSION
    assert rep_doc.gate is not None
    assert rep_doc.gate.decision == GateDecision.FAIL

    store = LocalRunStore(storage)
    for idx, expected_seed in enumerate((10, 11, 12), start=1):
        rec = store.load_run(f"cand-trial-r0{idx}")
        assert rec.seed == expected_seed

    md_text = md_out.read_text(encoding="utf-8")
    assert "Cohort" in md_text
    assert "cand-trial-r01" in md_text

    # Standalone multi-run compare subcommand + --baseline-run without --baseline
    cmp_code, cmp_out, cmp_err = _run_cli(
        [
            "compare",
            "cand-trial-r01",
            "cand-trial-r02",
            "cand-trial-r03",
            "--storage-dir",
            str(storage),
            "--baseline-run",
            "v1",
            "--baseline-run",
            "base-r2",
            "--fail-on-significant-regression",
            "--json",
        ],
        capsys,
    )
    assert cmp_code == 1, cmp_err
    cmp_doc = ReportDocument.model_validate_json(cmp_out)
    assert cmp_doc.comparison is not None
    assert cmp_doc.comparison.cohort is not None
    assert cmp_doc.comparison.cohort.candidate_run_ids == [
        "cand-trial-r01",
        "cand-trial-r02",
        "cand-trial-r03",
    ]
    assert cmp_doc.gate is not None and cmp_doc.gate.decision == GateDecision.FAIL

    # Any-repeat mandatory failure in repeat #1 fails cohort gate even if later repeats pass
    flaky_code, flaky_out, _ = _run_cli(
        [
            "run",
            "--storage-dir",
            str(storage),
            "--dataset",
            str(ds_path),
            "--target",
            "cohort_target:flaky_mandatory_target",
            "--metric",
            "exact_match",
            "--run-id",
            "flaky-coh",
            "--repeats",
            "3",
            "--max-concurrency",
            "1",
            "--json",
        ],
        capsys,
    )
    assert flaky_code == 1
    flaky_doc = ReportDocument.model_validate_json(flaky_out)
    assert flaky_doc.evaluation is not None
    assert not flaky_doc.evaluation.has_mandatory_failures  # final repeat passed
    assert flaky_doc.gate is not None
    assert flaky_doc.gate.decision == GateDecision.FAIL
    assert any(
        c.rule_id == "mandatory_cases" and c.status == GateDecision.FAIL
        for c in flaky_doc.gate.checks
    )
