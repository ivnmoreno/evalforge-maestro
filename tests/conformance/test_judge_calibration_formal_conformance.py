"""Dual-mode Python-to-Lean conformance suite for Judge Calibration & Threshold Optimization.

Default mode validates Python's `calibrate_judge`, `acalibrate_judge`, and
`_optimize_pass_threshold` offline against the checked-in Lean oracle golden fixture
(`tests/conformance/golden/judge_calibration_oracle.json`).

Live mode (`--lean-live-oracle`) additionally executes the compiled Lean binary
(`evalforge-calibration-oracle`) fail-closed to verify byte-for-byte golden parity,
evaluate all canonical and sweep vectors via stdin/stdout, and confirm malformed
requests fail closed.
"""

from __future__ import annotations

import asyncio
import copy
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import round_delta, round_percentage, round_score
from evalforge_maestro.judges.calibration import (
    _optimize_pass_threshold,
    acalibrate_judge,
    calibrate_judge,
)
from evalforge_maestro.types import (
    EvaluationCase,
    ExecutionResult,
    HumanCalibrationSample,
    JudgeConfig,
    MetricMetadata,
    MetricResult,
    MetricStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CALIBRATION_PATH = (
    Path(__file__).resolve().parent / "golden" / "judge_calibration_oracle.json"
)
EXPECTED_DISAGREEMENT_TYPES = [
    "too_generous",
    "too_harsh",
    "score_divergence",
    "inconclusive",
]


def _rat_to_fraction(payload: dict[str, int]) -> Fraction:
    return Fraction(int(payload["num"]), int(payload["den"]))


def _opt_rat_to_fraction(payload: dict[str, int] | None) -> Fraction | None:
    if payload is None:
        return None
    return _rat_to_fraction(payload)


def _float_to_rat_json(value: float) -> dict[str, int]:
    frac = Fraction(str(value))
    return {"num": frac.numerator, "den": frac.denominator}


def _resolve_oracle_bin(request: pytest.FixtureRequest) -> Path:
    raw = str(request.config.getoption("--lean-calibration-oracle-bin"))
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def _run_live_oracle(
    oracle_bin: Path,
    args: list[str],
    *,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if not oracle_bin.is_file():
        raise FileNotFoundError(f"Lean calibration oracle binary not found at: {oracle_bin}")
    return subprocess.run(
        [str(oracle_bin), *args],
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _eval_live_oracle(oracle_bin: Path, payload: dict[str, Any]) -> dict[str, Any]:
    proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=json.dumps(payload))
    assert proc.returncode == 0, (
        f"evalforge-calibration-oracle eval-stdin failed (exit={proc.returncode}): {proc.stderr}"
    )
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed


class _DeterministicCalibrationJudge:
    """Offline stub metric returning exact `(score, status)` outcomes per case ID."""

    def __init__(
        self,
        *,
        pass_threshold: float,
        outcomes: dict[str, tuple[float | None, MetricStatus]],
    ) -> None:
        self.judge_config = JudgeConfig(
            model="formal-conformance-stub",
            mock_mode=True,
            pass_threshold=pass_threshold,
        )
        self._outcomes = outcomes

    @property
    def metadata(self) -> MetricMetadata:
        return MetricMetadata(
            metric_id="formal_conformance_judge",
            metric_version="1.0.0",
            what_it_measures="Deterministic conformance judge stub",
            required_case_fields=("input",),
            required_execution_fields=("output",),
            calculation_method="Lookup table for formal conformance",
            known_limitations="Test-only stub",
        )

    def evaluate(self, case: EvaluationCase, execution: ExecutionResult) -> MetricResult:
        del execution
        score, status = self._outcomes[case.id]
        return MetricResult(
            metric_id=self.metadata.metric_id,
            metric_version=self.metadata.metric_version,
            score=score,
            status=status,
            explanation=f"Deterministic outcome for {case.id}",
        )


def _assert_python_matches_oracle(
    vector_input: dict[str, Any],
    oracle_expected: dict[str, Any],
) -> None:
    """Run real Python calibration and verify full parity with Lean oracle output."""
    pass_threshold = round_score(float(_rat_to_fraction(vector_input["pass_threshold"])))
    human_threshold = round_score(float(_rat_to_fraction(vector_input["human_threshold"])))
    div_threshold = round_score(float(_rat_to_fraction(vector_input["score_divergence_threshold"])))

    samples: list[HumanCalibrationSample] = []
    outcomes: dict[str, tuple[float | None, MetricStatus]] = {}
    valid_rows_for_opt: list[tuple[float, float, bool]] = []

    for s_raw in vector_input["samples"]:
        case_id = str(s_raw["case_id"])
        h_score_frac = _opt_rat_to_fraction(s_raw["human_score"])
        h_score = None if h_score_frac is None else round_score(float(h_score_frac))
        h_passed: bool | None = s_raw["human_passed"]
        j_score_frac = _opt_rat_to_fraction(s_raw["judge_score"])
        j_score = None if j_score_frac is None else round_score(float(j_score_frac))
        j_status = MetricStatus(str(s_raw["judge_status"]))

        samples.append(
            HumanCalibrationSample(
                case_id=case_id,
                input=f"question-{case_id}",
                output=f"answer-{case_id}",
                human_score=h_score,
                human_passed=h_passed,
            )
        )
        outcomes[case_id] = (j_score, j_status)

        resolved_hp = (
            h_passed
            if h_passed is not None
            else (h_score is not None and h_score >= human_threshold - 1e-9)
        )
        resolved_hn = float(h_score) if h_score is not None else (1.0 if resolved_hp else 0.0)
        if j_score is not None and j_status not in (
            MetricStatus.INCONCLUSIVE,
            MetricStatus.NOT_APPLICABLE,
        ):
            valid_rows_for_opt.append((resolved_hn, j_score, resolved_hp))

    judge = _DeterministicCalibrationJudge(pass_threshold=pass_threshold, outcomes=outcomes)
    sync_report = calibrate_judge(
        judge,
        samples,
        human_threshold=human_threshold,
        score_divergence_threshold=div_threshold,
    )
    async_report = asyncio.run(
        acalibrate_judge(
            judge,
            samples,
            human_threshold=human_threshold,
            score_divergence_threshold=div_threshold,
        )
    )
    assert sync_report == async_report, "Sync and async calibration reports diverged"

    assert sync_report.total_cases == oracle_expected["total_cases"]
    assert sync_report.valid_cases == oracle_expected["valid_cases"]
    assert sync_report.inconclusive_cases == oracle_expected["inconclusive_cases"]
    assert sync_report.valid_cases + sync_report.inconclusive_cases == sync_report.total_cases

    expected_disagreements: list[dict[str, Any]] = oracle_expected["disagreements"]
    assert len(sync_report.disagreements) == len(expected_disagreements)
    for py_d, lean_d in zip(sync_report.disagreements, expected_disagreements, strict=True):
        assert py_d.case_id == lean_d["case_id"]
        assert py_d.disagreement_type.value == lean_d["disagreement_type"]
        assert py_d.human_passed == lean_d["human_passed"]
        assert py_d.judge_passed == lean_d["judge_passed"]
        assert py_d.judge_status.value == lean_d["judge_status"]
        lean_delta = _opt_rat_to_fraction(lean_d["score_delta_exact"])
        if lean_delta is None:
            assert py_d.score_delta is None
        else:
            assert py_d.score_delta == round_delta(float(lean_delta))

    if oracle_expected["valid_cases"] == 0:
        assert sync_report.exact_agreement_rate is None
        assert sync_report.too_generous_rate is None
        assert sync_report.too_harsh_rate is None
        assert sync_report.mean_human_score is None
        assert sync_report.mean_judge_score is None
        assert sync_report.mean_score_delta is None
    else:
        exp_ag = _rat_to_fraction(oracle_expected["exact_agreement_rate_exact"])
        exp_gen = _rat_to_fraction(oracle_expected["too_generous_rate_exact"])
        exp_har = _rat_to_fraction(oracle_expected["too_harsh_rate_exact"])
        exp_mh = _rat_to_fraction(oracle_expected["mean_human_score_exact"])
        exp_mj = _rat_to_fraction(oracle_expected["mean_judge_score_exact"])
        exp_md = _rat_to_fraction(oracle_expected["mean_score_delta_exact"])

        assert sync_report.exact_agreement_rate == round_percentage(float(exp_ag))
        assert sync_report.too_generous_rate == round_score(float(exp_gen))
        assert sync_report.too_harsh_rate == round_score(float(exp_har))
        assert sync_report.mean_human_score == round_score(float(exp_mh))
        assert sync_report.mean_judge_score == round_score(float(exp_mj))
        assert sync_report.mean_score_delta == round_delta(float(exp_md))

    exp_rec = round_score(
        float(_rat_to_fraction(oracle_expected["recommended_pass_threshold_exact"]))
    )
    assert sync_report.recommended_pass_threshold == exp_rec

    direct_opt = _optimize_pass_threshold(valid_rows_for_opt, active_threshold=pass_threshold)
    assert direct_opt == exp_rec


def test_calibration_golden_schema_and_live_oracle_parity(request: pytest.FixtureRequest) -> None:
    """Validate golden schema and (in live mode) byte-for-byte parity with the Lean binary."""
    raw_golden = GOLDEN_CALIBRATION_PATH.read_text(encoding="utf-8")
    golden: dict[str, Any] = json.loads(raw_golden)

    assert golden["schema_version"] == "1.0"
    assert golden["lean_toolchain"] == "leanprover/lean4:v4.36.0"
    assert golden["disagreement_types"] == EXPECTED_DISAGREEMENT_TYPES
    assert len(golden["canonical_vectors"]) == 16

    if bool(request.config.getoption("--lean-live-oracle")):
        oracle_bin = _resolve_oracle_bin(request)
        proc = _run_live_oracle(oracle_bin, ["export-golden"])
        assert proc.returncode == 0, f"export-golden failed: {proc.stderr}"
        assert proc.stdout == raw_golden, (
            "Live evalforge-calibration-oracle export-golden diverged from checked-in golden JSON"
        )


def test_calibration_canonical_vectors_python_conformance(request: pytest.FixtureRequest) -> None:
    """Check all 16 canonical calibration vectors against Python (and live Lean when enabled)."""
    golden: dict[str, Any] = json.loads(GOLDEN_CALIBRATION_PATH.read_text(encoding="utf-8"))
    live_mode = bool(request.config.getoption("--lean-live-oracle"))
    oracle_bin = _resolve_oracle_bin(request) if live_mode else None

    for vector in golden["canonical_vectors"]:
        vector_input: dict[str, Any] = vector["input"]
        golden_expected: dict[str, Any] = vector["expected"]
        _assert_python_matches_oracle(vector_input, golden_expected)

        if live_mode and oracle_bin is not None:
            live_expected = _eval_live_oracle(oracle_bin, vector_input)
            assert live_expected == golden_expected, (
                f"Live oracle disagreed with golden on {vector_input['case_id']}"
            )


def test_calibration_permutation_invariance_conformance(request: pytest.FixtureRequest) -> None:
    """Verify scalar calibration metrics and recommended threshold are permutation-invariant."""
    golden: dict[str, Any] = json.loads(GOLDEN_CALIBRATION_PATH.read_text(encoding="utf-8"))
    live_mode = bool(request.config.getoption("--lean-live-oracle"))
    oracle_bin = _resolve_oracle_bin(request) if live_mode else None

    target_ids = {
        "cal_too_generous_midpoint_raise",
        "cal_too_harsh_threshold_lower",
        "cal_mixed_inconclusive_not_applicable_and_none_score",
        "cal_equidistant_two_winners_fallback_to_last",
        "cal_balanced_bias_skew_tiebreak",
    }
    scalar_keys = (
        "total_cases",
        "valid_cases",
        "inconclusive_cases",
        "agreed_count",
        "too_generous_count",
        "too_harsh_count",
        "exact_agreement_rate_exact",
        "too_generous_rate_exact",
        "too_harsh_rate_exact",
        "mean_human_score_exact",
        "mean_judge_score_exact",
        "mean_score_delta_exact",
        "recommended_pass_threshold_exact",
    )

    for vector in golden["canonical_vectors"]:
        v_in: dict[str, Any] = vector["input"]
        if v_in["case_id"] not in target_ids:
            continue
        base_exp: dict[str, Any] = vector["expected"]
        samples: list[dict[str, Any]] = list(v_in["samples"])
        permutations = [
            list(reversed(samples)),
            samples[1:] + samples[:1],
        ]
        for idx, perm in enumerate(permutations):
            perm_input = copy.deepcopy(v_in)
            perm_input["case_id"] = f"{v_in['case_id']}_perm_{idx}"
            perm_input["samples"] = perm

            if live_mode and oracle_bin is not None:
                perm_exp = _eval_live_oracle(oracle_bin, perm_input)
                for key in scalar_keys:
                    assert perm_exp[key] == base_exp[key], (
                        f"Permutation {idx} changed {key} for {v_in['case_id']}"
                    )
                _assert_python_matches_oracle(perm_input, perm_exp)
            else:
                # Reorder expected disagreements to match permuted sample order and check Python
                dis_by_id = {d["case_id"]: d for d in base_exp["disagreements"]}
                perm_exp = copy.deepcopy(base_exp)
                perm_exp["disagreements"] = [
                    dis_by_id[s["case_id"]] for s in perm if s["case_id"] in dis_by_id
                ]
                _assert_python_matches_oracle(perm_input, perm_exp)


def test_calibration_threshold_monotonicity_and_tiebreak_sweeps(
    request: pytest.FixtureRequest,
) -> None:
    """Verify threshold monotonicity (`generous` antitone, `harsh` monotone) and live parity."""
    live_mode = bool(request.config.getoption("--lean-live-oracle"))
    oracle_bin = _resolve_oracle_bin(request) if live_mode else None

    base_samples: list[dict[str, Any]] = [
        {
            "case_id": "sw1",
            "human_score": _float_to_rat_json(0.1),
            "human_passed": False,
            "judge_score": _float_to_rat_json(0.2),
            "judge_status": "FAIL",
        },
        {
            "case_id": "sw2",
            "human_score": _float_to_rat_json(0.3),
            "human_passed": False,
            "judge_score": _float_to_rat_json(0.5),
            "judge_status": "PASS",
        },
        {
            "case_id": "sw3",
            "human_score": _float_to_rat_json(0.8),
            "human_passed": True,
            "judge_score": _float_to_rat_json(0.6),
            "judge_status": "PASS",
        },
        {
            "case_id": "sw4",
            "human_score": _float_to_rat_json(0.95),
            "human_passed": True,
            "judge_score": _float_to_rat_json(0.9),
            "judge_status": "PASS",
        },
    ]

    sweep_thresholds = [0.0, 0.25, 0.5, 0.6, 0.75, 1.0]
    generous_rates: list[float] = []
    harsh_rates: list[float] = []

    for th in sweep_thresholds:
        req_payload: dict[str, Any] = {
            "case_id": f"sweep_{th}",
            "pass_threshold": _float_to_rat_json(th),
            "human_threshold": _float_to_rat_json(0.5),
            "score_divergence_threshold": _float_to_rat_json(0.25),
            "samples": base_samples,
        }
        samples = [
            HumanCalibrationSample(
                case_id=str(s["case_id"]),
                input="q",
                output="a",
                human_score=round_score(float(_rat_to_fraction(s["human_score"]))),
                human_passed=s["human_passed"],
            )
            for s in base_samples
        ]
        outcomes: dict[str, tuple[float | None, MetricStatus]] = {
            str(s["case_id"]): (
                round_score(float(_rat_to_fraction(s["judge_score"]))),
                MetricStatus(str(s["judge_status"])),
            )
            for s in base_samples
        }
        judge = _DeterministicCalibrationJudge(pass_threshold=th, outcomes=outcomes)
        rep = calibrate_judge(judge, samples, human_threshold=0.5, score_divergence_threshold=0.25)
        assert rep.too_generous_rate is not None
        assert rep.too_harsh_rate is not None
        assert 0.0 <= rep.recommended_pass_threshold <= 1.0
        generous_rates.append(rep.too_generous_rate)
        harsh_rates.append(rep.too_harsh_rate)

        if live_mode and oracle_bin is not None:
            live_exp = _eval_live_oracle(oracle_bin, req_payload)
            _assert_python_matches_oracle(req_payload, live_exp)

    # Monotonicity across increasing thresholds: generous non-increasing, harsh non-decreasing
    for idx in range(len(sweep_thresholds) - 1):
        assert generous_rates[idx + 1] <= generous_rates[idx]
        assert harsh_rates[idx] <= harsh_rates[idx + 1]

    # Empty valid_rows fallback in Python matches Theorem 21
    assert _optimize_pass_threshold([], active_threshold=0.73) == 0.73


def test_calibration_negative_fault_detection_and_fail_closed_checks(
    request: pytest.FixtureRequest,
) -> None:
    """Confirm conformance catches drift, tampered golden data, and malformed/missing oracle."""
    golden: dict[str, Any] = json.loads(GOLDEN_CALIBRATION_PATH.read_text(encoding="utf-8"))
    first_vector = golden["canonical_vectors"][0]

    # 1. Simulated threshold drift must fail conformance loudly
    tampered_threshold = copy.deepcopy(first_vector["expected"])
    tampered_threshold["recommended_pass_threshold_exact"] = {"num": 1, "den": 2}
    with pytest.raises(AssertionError):
        _assert_python_matches_oracle(first_vector["input"], tampered_threshold)

    # 2. Simulated disagreement classification drift must fail loudly
    tampered_disagreement = copy.deepcopy(first_vector["expected"])
    tampered_disagreement["disagreements"][0]["disagreement_type"] = "too_harsh"
    with pytest.raises(AssertionError):
        _assert_python_matches_oracle(first_vector["input"], tampered_disagreement)

    # 3. Missing oracle binary must fail closed
    missing_bin = REPO_ROOT / "formal" / ".lake" / "build" / "bin" / "nonexistent-cal-oracle"
    with pytest.raises(FileNotFoundError):
        _run_live_oracle(missing_bin, ["export-golden"])

    # 4. In live mode, malformed eval-stdin payloads must exit non-zero
    if bool(request.config.getoption("--lean-live-oracle")):
        oracle_bin = _resolve_oracle_bin(request)
        bad_payloads = [
            "not valid json",
            json.dumps(
                {
                    "case_id": "empty-samples",
                    "pass_threshold": {"num": 1, "den": 2},
                    "human_threshold": {"num": 1, "den": 2},
                    "score_divergence_threshold": {"num": 1, "den": 4},
                    "samples": [],
                }
            ),
            json.dumps(
                {
                    "case_id": "zero-div-threshold",
                    "pass_threshold": {"num": 1, "den": 2},
                    "human_threshold": {"num": 1, "den": 2},
                    "score_divergence_threshold": {"num": 0, "den": 1},
                    "samples": [
                        {
                            "case_id": "s1",
                            "human_score": {"num": 1, "den": 2},
                            "human_passed": True,
                            "judge_score": {"num": 1, "den": 2},
                            "judge_status": "PASS",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "case_id": "pass-threshold-gt-one",
                    "pass_threshold": {"num": 3, "den": 2},
                    "human_threshold": {"num": 1, "den": 2},
                    "score_divergence_threshold": {"num": 1, "den": 4},
                    "samples": [
                        {
                            "case_id": "s1",
                            "human_score": {"num": 1, "den": 2},
                            "human_passed": True,
                            "judge_score": {"num": 1, "den": 2},
                            "judge_status": "PASS",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "case_id": "missing-human-label",
                    "pass_threshold": {"num": 1, "den": 2},
                    "human_threshold": {"num": 1, "den": 2},
                    "score_divergence_threshold": {"num": 1, "den": 4},
                    "samples": [
                        {
                            "case_id": "s1",
                            "human_score": None,
                            "human_passed": None,
                            "judge_score": {"num": 1, "den": 2},
                            "judge_status": "PASS",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "case_id": "dup-sample-id",
                    "pass_threshold": {"num": 1, "den": 2},
                    "human_threshold": {"num": 1, "den": 2},
                    "score_divergence_threshold": {"num": 1, "den": 4},
                    "samples": [
                        {
                            "case_id": "dup",
                            "human_score": {"num": 1, "den": 2},
                            "human_passed": True,
                            "judge_score": {"num": 1, "den": 2},
                            "judge_status": "PASS",
                        },
                        {
                            "case_id": "dup",
                            "human_score": {"num": 1, "den": 2},
                            "human_passed": True,
                            "judge_score": {"num": 1, "den": 2},
                            "judge_status": "PASS",
                        },
                    ],
                }
            ),
        ]
        for raw_bad in bad_payloads:
            proc = _run_live_oracle(oracle_bin, ["eval-stdin"], stdin_text=raw_bad)
            assert proc.returncode != 0, f"Expected live oracle rejection for payload: {raw_bad}"
