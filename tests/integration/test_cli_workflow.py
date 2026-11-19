"""Integration tests covering CLI subcommands, streams, redaction, and POSIX exit codes 0-4."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro._canonical import REDACTED_VALUE
from evalforge_maestro.cli import main as cli_main
from evalforge_maestro.types import (
    BaselineCommandPayload,
    CLIErrorPayload,
    CLIResolvedConfig,
    ConfigValidationPayload,
    GateDecision,
    ReportDocument,
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _run_cli(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    capsys.readouterr()
    code = cli_main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _seed_sample_dataset(tmp_path: Path) -> tuple[Path, Path]:
    ds_path = tmp_path / "dataset.jsonl"
    exec_path = tmp_path / "executions.jsonl"
    _write_jsonl(
        ds_path,
        [
            {
                "id": "c1",
                "input": "What is our uptime SLA?",
                "reference": "99.9%",
                "expected_context": ["doc-sla"],
                "criteria": {"mandatory": True},
            },
            {
                "id": "c2",
                "input": "What is the support email tier?",
                "reference": "24/7 enterprise",
                "expected_context": ["doc-support"],
                "criteria": {"mandatory": False},
            },
        ],
    )
    _write_jsonl(
        exec_path,
        [
            {
                "case_id": "c1",
                "input": "What is our uptime SLA?",
                "output": "99.9%",
                "retrieved_chunks": [
                    {"id": "doc-sla", "text": "Our uptime SLA is 99.9% monthly.", "rank": 1}
                ],
                "elapsed_seconds": 0.01,
                "system_version": "app-v1",
                "model_id": "mock-rag",
            },
            {
                "case_id": "c2",
                "input": "What is the support email tier?",
                "output": "24/7 enterprise",
                "retrieved_chunks": [
                    {"id": "doc-support", "text": "24/7 enterprise support included.", "rank": 1}
                ],
                "elapsed_seconds": 0.01,
                "system_version": "app-v1",
                "model_id": "mock-rag",
            },
        ],
    )
    return ds_path, exec_path


@pytest.mark.gate_determinism
def test_cli_run_mock_local_only_determinism_and_stream_hygiene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    ds_path, exec_path = _seed_sample_dataset(tmp_path)

    docs: list[ReportDocument] = []
    for idx in (1, 2):
        md_file = tmp_path / f"report-{idx}.md"
        json_file = tmp_path / f"report-{idx}.json"
        code, out, err = _run_cli(
            [
                "run",
                "--dataset",
                str(ds_path),
                "--executions",
                str(exec_path),
                "--metric",
                "exact_match",
                "--metric",
                "precision_at_k:k=1",
                "--metric",
                "groundedness",
                "--mock",
                "--local-only",
                "--strict",
                "--seed",
                "42",
                "--log-level",
                "INFO",
                "--log-json",
                "--json",
                "--json-out",
                str(json_file),
                "--markdown-out",
                str(md_file),
            ],
            capsys,
        )
        assert code == 0, err
        # stdout MUST be solely one schema-validated JSON payload
        doc = ReportDocument.model_validate_json(out.strip())
        docs.append(doc)
        assert doc.gate is not None
        assert doc.gate.decision == GateDecision.PASS
        assert md_file.is_file() and "## Acceptance / Quality Gate" in md_file.read_text()
        assert json_file.is_file()

        # stderr MUST hold valid JSON lines when --log-json + INFO enabled
        err_lines = [line for line in err.splitlines() if line.strip()]
        assert err_lines
        for line in err_lines:
            parsed_log = json.loads(line)
            assert parsed_log["level"] in {"INFO", "WARNING", "DEBUG", "ERROR"}

    # Repeated --mock --local-only CLI runs must match identically modulo volatile timestamps/run_id
    r1, r2 = docs[0].evaluation, docs[1].evaluation
    assert r1 is not None and r2 is not None
    assert r1.run_id != r2.run_id
    assert r1.dataset_fingerprint == r2.dataset_fingerprint
    assert r1.judge_config_fingerprint == r2.judge_config_fingerprint
    assert r1.aggregates == r2.aggregates
    assert r1.status_counts == r2.status_counts
    g1, g2 = docs[0].gate, docs[1].gate
    assert g1 is not None and g2 is not None
    assert g1.decision == g2.decision
    assert g1.passed == g2.passed
    assert g1.blocking == g2.blocking
    assert g1.inconclusive_rate == g2.inconclusive_rate
    assert g1.checks == g2.checks
    assert g1.anomalies == g2.anomalies
    assert g1.drift_warnings == g2.drift_warnings

    # Verify atomic 0o700 / 0o600 permissions inside .evalforge
    if os.name == "posix":
        run_file = tmp_path / ".evalforge" / "runs" / f"{r1.run_id}.json"
        assert stat.S_IMODE((tmp_path / ".evalforge").stat().st_mode) == 0o700
        assert stat.S_IMODE(run_file.stat().st_mode) == 0o600


def test_cli_run_live_callable_rag_and_missing_docpipe_extra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    target_mod = tmp_path / "sample_targets.py"
    target_mod.write_text(
        "def echo_answer(query: str) -> str:\n"
        "    return '99.9%'\n\n"
        "def rag_answer(query: str) -> dict:\n"
        "    return {\n"
        "        'answer': '99.9%',\n"
        "        'chunks': [{'id': 'doc-sla', 'text': '99.9% SLA'}],\n"
        "    }\n",
        encoding="utf-8",
    )
    ds_path = tmp_path / "live_ds.jsonl"
    _write_jsonl(
        ds_path,
        [
            {
                "id": "q1",
                "input": "SLA?",
                "reference": "99.9%",
                "expected_context": ["doc-sla"],
            }
        ],
    )

    code_c, out_c, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--target-type",
            "callable",
            "--target",
            "sample_targets:echo_answer",
            "--metric",
            "exact_match",
            "--json",
        ],
        capsys,
    )
    assert code_c == 0
    assert ReportDocument.model_validate_json(out_c).evaluation is not None

    code_r, out_r, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--target-type",
            "rag",
            "--target",
            "sample_targets:rag_answer",
            "--metric",
            "exact_match",
            "--metric",
            "precision_at_k:k=1",
            "--json",
        ],
        capsys,
    )
    assert code_r == 0
    rep_r = ReportDocument.model_validate_json(out_r)
    assert rep_r.evaluation is not None
    assert rep_r.evaluation.aggregates["precision_at_k"].mean_score == 1.0

    # docpipe optional extra missing -> exit 3 with actionable install hint
    code_dp, out_dp, err_dp = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--target-type",
            "docpipe",
            "--metric",
            "exact_match",
            "--json",
        ],
        capsys,
    )
    assert code_dp == 3
    err_obj = CLIErrorPayload.model_validate_json(out_dp)
    assert err_obj.exit_code == 3
    assert "docpipe" in err_dp


def test_cli_run_exit_codes_1_2_3_4_and_quiet_stream_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    ds_path, exec_path = _seed_sample_dataset(tmp_path)

    # Exit 1: mandatory case breach / threshold fail
    bad_exec = tmp_path / "bad_exec.jsonl"
    _write_jsonl(
        bad_exec,
        [
            {
                "case_id": "c1",
                "input": "SLA?",
                "output": "wrong",
                "retrieved_chunks": [],
                "elapsed_seconds": 0.01,
            },
            {
                "case_id": "c2",
                "input": "Support?",
                "output": "24/7 enterprise",
                "retrieved_chunks": [],
                "elapsed_seconds": 0.01,
            },
        ],
    )
    code1, out1, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--executions",
            str(bad_exec),
            "--metric",
            "exact_match",
            "--quiet",
            "--markdown-out",
            str(tmp_path / "quiet.md"),
        ],
        capsys,
    )
    assert code1 == 1
    assert out1 == ""
    assert (tmp_path / "quiet.md").is_file()

    # Exit 2: zero configured metrics
    code2_nom, out2_nom, _ = _run_cli(
        ["run", "--dataset", str(ds_path), "--executions", str(exec_path), "--json"],
        capsys,
    )
    assert code2_nom == 2
    assert CLIErrorPayload.model_validate_json(out2_nom).exit_code == 2

    # Exit 2: unknown metric, invalid parser arg with --json, missing replay case
    code2_badflag, out2_badflag, err2_badflag = _run_cli(
        ["run", "--unknown-flag", "--json"],
        capsys,
    )
    assert code2_badflag == 2
    assert CLIErrorPayload.model_validate_json(out2_badflag).exit_code == 2
    assert "error:" in err2_badflag

    partial_exec = tmp_path / "partial_exec.jsonl"
    _write_jsonl(
        partial_exec,
        [{"case_id": "c1", "input": "q", "output": "99.9%", "elapsed_seconds": 0.01}],
    )
    code2_miss, _, err2_miss = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--executions",
            str(partial_exec),
            "--metric",
            "exact_match",
        ],
        capsys,
    )
    assert code2_miss == 2
    assert "c2" in err2_miss

    # Extra unused trace records emit warning on stderr while succeeding cleanly
    extra_exec = tmp_path / "extra_exec.jsonl"
    _write_jsonl(
        extra_exec,
        [
            {"case_id": "c1", "input": "q1", "output": "99.9%", "elapsed_seconds": 0.01},
            {"case_id": "c2", "input": "q2", "output": "24/7 enterprise", "elapsed_seconds": 0.01},
            {"case_id": "extra-unused", "input": "q3", "output": "unused", "elapsed_seconds": 0.01},
        ],
    )
    code_extra, _, err_extra = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--executions",
            str(extra_exec),
            "--metric",
            "exact_match",
            "--json",
        ],
        capsys,
    )
    assert code_extra == 0
    assert "unused trace record" in err_extra

    # Exit 3: target failing on all cases (--fail-fast & full run) + missing judges extra
    fail_mod = tmp_path / "failing_targets.py"
    fail_mod.write_text(
        "def always_boom(query: str) -> str:\n    raise RuntimeError('upstream down')\n",
        encoding="utf-8",
    )
    for extra_flag in (["--fail-fast"], []):
        code3, out3, _ = _run_cli(
            [
                "run",
                "--dataset",
                str(ds_path),
                "--target",
                "failing_targets:always_boom",
                "--metric",
                "exact_match",
                "--json",
                *extra_flag,
            ],
            capsys,
        )
        assert code3 == 3
        assert CLIErrorPayload.model_validate_json(out3).exit_code == 3

    code3_judge, out3_judge, err3_judge = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--executions",
            str(exec_path),
            "--metric",
            "groundedness",
            "--judge-model",
            "openai/gpt-4o-mini",
            "--json",
        ],
        capsys,
    )
    assert code3_judge == 3
    assert CLIErrorPayload.model_validate_json(out3_judge).exit_code == 3
    assert "judges" in err3_judge

    # Exit 4: --local-only blocks remote judge model pre-network
    code4_loc, out4_loc, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(ds_path),
            "--executions",
            str(exec_path),
            "--metric",
            "groundedness",
            "--judge-model",
            "openai/gpt-4o-mini",
            "--local-only",
            "--json",
        ],
        capsys,
    )
    assert code4_loc == 4
    assert CLIErrorPayload.model_validate_json(out4_loc).exit_code == 4

    # Exit 4: --block-pii blocks outbound PII before remote judge dispatch without echoing raw PII
    pii_ds = tmp_path / "pii_ds.jsonl"
    pii_exec = tmp_path / "pii_exec.jsonl"
    raw_email = "secret.alice@privatecorp.com"
    _write_jsonl(pii_ds, [{"id": "p1", "input": f"Email {raw_email}", "reference": "ok"}])
    _write_jsonl(
        pii_exec,
        [
            {
                "case_id": "p1",
                "input": f"Email {raw_email}",
                "output": "ok",
                "retrieved_chunks": [{"id": "c1", "text": f"Contact {raw_email}"}],
                "elapsed_seconds": 0.01,
            }
        ],
    )
    code4_pii, out4_pii, err4_pii = _run_cli(
        [
            "run",
            "--dataset",
            str(pii_ds),
            "--executions",
            str(pii_exec),
            "--metric",
            "groundedness",
            "--judge-model",
            "openai/gpt-4o-mini",
            "--block-pii",
            "--json",
        ],
        capsys,
    )
    assert code4_pii == 4
    assert raw_email not in out4_pii
    assert raw_email not in err4_pii
    assert CLIErrorPayload.model_validate_json(out4_pii).exit_code == 4


@pytest.mark.gate_immutability
def test_cli_baseline_compare_trend_and_report_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    ds_path = tmp_path / "ds.jsonl"
    _write_jsonl(
        ds_path,
        [
            {"id": "c1", "input": "Q1", "reference": "good"},
            {"id": "c2", "input": "Q2", "reference": "good"},
        ],
    )

    # Empty store trend returns INSUFFICIENT_DATA (exit 0 normally, exit 1 with --strict)
    code_empty_t, out_empty_t, _ = _run_cli(["trend", "--window", "3", "--json"], capsys)
    assert code_empty_t == 0
    assert ReportDocument.model_validate_json(out_empty_t).trend is not None

    code_empty_strict, _, _ = _run_cli(["trend", "--window", "3", "--strict"], capsys)
    assert code_empty_strict == 1

    # Invalid trend window < 2 -> exit 2
    code_bad_w, _, _ = _run_cli(["trend", "--window", "1"], capsys)
    assert code_bad_w == 2

    # Record 3 runs: 1.0 -> 0.5 -> 0.0
    run_ids: list[str] = []
    for idx, outputs in enumerate((("good", "good"), ("good", "bad"), ("bad", "bad")), start=1):
        ex = tmp_path / f"exec_{idx}.jsonl"
        _write_jsonl(
            ex,
            [
                {"case_id": "c1", "input": "Q1", "output": outputs[0], "elapsed_seconds": 0.01},
                {"case_id": "c2", "input": "Q2", "output": outputs[1], "elapsed_seconds": 0.01},
            ],
        )
        rid = f"run-seq-{idx}"
        code, _, _ = _run_cli(
            [
                "run",
                "--dataset",
                str(ds_path),
                "--executions",
                str(ex),
                "--metric",
                "exact_match",
                "--run-id",
                rid,
                "--quiet",
            ],
            capsys,
        )
        assert code == 0
        run_ids.append(rid)

    run1_file = tmp_path / ".evalforge" / "runs" / f"{run_ids[0]}.json"
    run1_sha_before = hashlib.sha256(run1_file.read_bytes()).hexdigest()

    # Baseline set, list, show, duplicate rejection, overwrite, delete
    c_set, out_set, _ = _run_cli(
        [
            "baseline",
            "set",
            run_ids[0],
            "--name",
            "release",
            "--note",
            "initial golden",
            "--json",
        ],
        capsys,
    )
    assert c_set == 0
    assert BaselineCommandPayload.model_validate_json(out_set).entry is not None

    c_dup, _, _ = _run_cli(
        ["baseline", "set", run_ids[1], "--name", "release"],
        capsys,
    )
    assert c_dup == 2

    c_ow, _, _ = _run_cli(
        ["baseline", "set", run_ids[1], "--name", "release", "--overwrite", "--json"],
        capsys,
    )
    assert c_ow == 0
    # Restore release -> run 0 for regression comparison
    _run_cli(
        ["baseline", "set", run_ids[0], "--name", "release", "--overwrite"],
        capsys,
    )

    c_list, out_list, _ = _run_cli(["baseline", "list", "--json"], capsys)
    assert c_list == 0
    assert len(BaselineCommandPayload.model_validate_json(out_list).baselines) == 1

    c_show, out_show, _ = _run_cli(["baseline", "show", "release", "--json"], capsys)
    assert c_show == 0
    assert BaselineCommandPayload.model_validate_json(out_show).entry is not None

    # Compare run-seq-3 against pinned baseline -> regression FAIL (exit 1)
    cmp_json_file = tmp_path / "cmp-report.json"
    c_cmp, out_cmp, _ = _run_cli(
        [
            "compare",
            run_ids[2],
            "--baseline",
            "release",
            "--max-regression-drop",
            "0.1",
            "--json",
            "--json-out",
            str(cmp_json_file),
        ],
        capsys,
    )
    assert c_cmp == 1
    cmp_doc = ReportDocument.model_validate_json(out_cmp)
    assert cmp_doc.comparison is not None
    assert cmp_doc.gate is not None
    assert cmp_doc.gate.decision == GateDecision.FAIL

    # Compare missing baseline -> exit 2
    c_cmp_miss, _, _ = _run_cli(["compare", run_ids[2], "--baseline", "unknown-alias"], capsys)
    assert c_cmp_miss == 2

    # Trend across 3 runs shows degrading slope (-0.5)
    c_trend, out_trend, _ = _run_cli(["trend", "--window", "3", "--json"], capsys)
    assert c_trend == 0
    trend_doc = ReportDocument.model_validate_json(out_trend)
    assert trend_doc.trend is not None
    assert trend_doc.trend.metrics["exact_match"].slope == -0.5

    # Report subcommand (--run, --compare, --trend, --artifact) does not mutate runs
    for rep_args in (
        ["report", "--run", run_ids[0], "--baseline", "release"],
        ["report", "--compare", run_ids[2], "--baseline", "release"],
        ["report", "--trend", "--window", "3"],
        ["report", "--artifact", str(cmp_json_file)],
    ):
        c_rep, out_rep, _ = _run_cli(rep_args, capsys)
        assert c_rep == 0
        assert "## Evaluation" in out_rep
        assert "## Acceptance / Quality Gate" in out_rep

    # Also test report --artifact with raw RunRecord JSON from storage
    c_raw_rep, out_raw_rep, _ = _run_cli(["report", "--artifact", str(run1_file)], capsys)
    assert c_raw_rep == 0
    assert "## Evaluation" in out_raw_rep

    # Delete baseline alias without touching underlying immutable RunRecord
    c_del, out_del, _ = _run_cli(["baseline", "delete", "release", "--json"], capsys)
    assert c_del == 0
    assert BaselineCommandPayload.model_validate_json(out_del).action == "delete"
    assert hashlib.sha256(run1_file.read_bytes()).hexdigest() == run1_sha_before


def test_cli_calibrate_and_config_precedence_with_secret_masking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    # Calibration samples
    cal_path = tmp_path / "cal.jsonl"
    _write_jsonl(
        cal_path,
        [
            {
                "case_id": "cal-1",
                "input": "What is uptime SLA?",
                "output": "99.9% monthly uptime SLA",
                "retrieved_chunks": [{"id": "d1", "text": "99.9% monthly uptime SLA"}],
                "human_passed": True,
            },
            {
                "case_id": "cal-2",
                "input": "What is refund window?",
                "output": "Instant cryptocurrency refund guaranteed",
                "retrieved_chunks": [{"id": "d2", "text": "Refunds take 14 business days."}],
                "human_passed": False,
            },
        ],
    )

    c_cal, out_cal, _ = _run_cli(
        [
            "calibrate",
            "--samples",
            str(cal_path),
            "--metric",
            "groundedness",
            "--mock",
            "--local-only",
            "--min-agreement",
            "50",
            "--json",
        ],
        capsys,
    )
    assert c_cal == 0
    cal_doc = ReportDocument.model_validate_json(out_cal)
    assert cal_doc.calibration is not None
    assert cal_doc.calibration.exact_agreement_rate is not None

    # Failing min-agreement > 100 boundary (validation exit 2) vs achievable fail (exit 1)
    c_cal_fail, _, _ = _run_cli(
        [
            "calibrate",
            "--samples",
            str(cal_path),
            "--metric",
            "answer_correctness",
            "--mock",
            "--min-agreement",
            "99.9",
        ],
        capsys,
    )
    # answer_correctness with missing references -> INCONCLUSIVE (0 valid) -> exit 1
    assert c_cal_fail == 1

    # Config precedence & secret masking across config show --resolved and config validate
    raw_secret = "sk-live-secret-never-leak-777"
    (tmp_path / "evalforge.toml").write_text(
        '[run]\ndataset = "from-toml.jsonl"\n\n'
        f'[judge]\nmodel = "mock-judge"\napi_key = "{raw_secret}"\n',
        encoding="utf-8",
    )
    env_file = tmp_path / "local.env"
    env_file.write_text("EVALFORGE_MAX_CONCURRENCY=6\n", encoding="utf-8")
    monkeypatch.setenv("EVALFORGE_BASELINE", "env-base")

    c_cfg, out_cfg, err_cfg = _run_cli(
        [
            "config",
            "show",
            "--resolved",
            "--env-file",
            str(env_file),
            "--json",
        ],
        capsys,
    )
    assert c_cfg == 0
    assert raw_secret not in out_cfg
    assert raw_secret not in err_cfg
    resolved = CLIResolvedConfig.model_validate_json(out_cfg)
    assert resolved.judge.api_key == REDACTED_VALUE
    assert resolved.baseline == "env-base"
    assert resolved.execution.max_concurrency == 6
    assert "Plaintext judge.api_key" in err_cfg

    c_val, out_val, err_val = _run_cli(["config", "validate", "--json"], capsys)
    assert c_val == 0
    assert raw_secret not in out_val
    assert raw_secret not in err_val
    val_payload = ConfigValidationPayload.model_validate_json(out_val)
    assert val_payload.valid is True
    assert len(val_payload.warnings) == 1
