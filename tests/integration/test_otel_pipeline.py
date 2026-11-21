"""Integration tests for OTel trace CLI ingestion, offline replay runs, and cold-start purity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from evalforge_maestro.adapters import ReplayAdapter
from evalforge_maestro.cli import main as cli_main
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import CLIErrorPayload, ExecutionResult, ReportDocument


def _kv(key: str, val: Any) -> dict[str, Any]:
    if isinstance(val, str):
        return {"key": key, "value": {"stringValue": val}}
    if isinstance(val, int) and not isinstance(val, bool):
        return {"key": key, "value": {"intValue": str(val)}}
    if isinstance(val, float):
        return {"key": key, "value": {"doubleValue": val}}
    if isinstance(val, dict):
        return {
            "key": key,
            "value": {"kvlistValue": {"values": [_kv(k, v) for k, v in val.items()]}},
        }
    if isinstance(val, list):
        return {
            "key": key,
            "value": {"arrayValue": {"values": [_kv("i", x)["value"] for x in val]}},
        }
    return {"key": key, "value": {"stringValue": str(val)}}


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = cli_main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _write_otel_fixtures(tmp_path: Path) -> tuple[Path, Path, str, str]:
    secret_tok = "sk-otel-integration-98765"
    bearer_tok = "eyJFakeBearerSecretTokenForOtel"
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "c-otel-1",
                "input": "Check SLA & billing status",
                "reference": "Invoice paid Bearer [REDACTED]",
                "expected_context": ["doc-sla-1"],
                "expected_tools": [
                    {"name": "fetch_invoice", "arguments": {"account": "acme"}, "order": 0}
                ],
                "criteria": {"forbidden_tools": ["drop_db"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    otlp_path = tmp_path / "traces.otlp.json"
    otlp_payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [_kv("service.version", "otel-agent-1.0")]},
                "scopeSpans": [
                    {
                        "scope": {"name": "evalforge.test"},
                        "spans": [
                            {
                                "traceId": "aaaa" * 8,
                                "spanId": "1111" * 4,
                                "name": "agent.root",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000001000000000",
                                "attributes": [
                                    _kv("evalforge.case_id", "c-otel-1"),
                                    _kv("input.value", "Check SLA & billing status"),
                                    _kv(
                                        "output.value",
                                        f"Invoice paid Bearer {bearer_tok}",
                                    ),
                                    _kv("openinference.span.kind", "AGENT"),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "aaaa" * 8,
                                "spanId": "2222" * 4,
                                "parentSpanId": "1111" * 4,
                                "name": "retriever",
                                "startTimeUnixNano": "1700000000100000000",
                                "endTimeUnixNano": "1700000000250000000",
                                "attributes": [
                                    _kv("openinference.span.kind", "RETRIEVER"),
                                    _kv(
                                        "retrieval.documents",
                                        [
                                            {
                                                "document.id": "doc-sla-1",
                                                "document.content": "X" * 180,
                                                "document.score": 0.91,
                                            }
                                        ],
                                    ),
                                ],
                                "status": {"code": 1},
                            },
                            {
                                "traceId": "aaaa" * 8,
                                "spanId": "3333" * 4,
                                "parentSpanId": "1111" * 4,
                                "name": "tool.fetch_invoice",
                                "startTimeUnixNano": "1700000000300000000",
                                "endTimeUnixNano": "1700000000800000000",
                                "attributes": [
                                    _kv("gen_ai.operation.name", "execute_tool"),
                                    _kv("gen_ai.tool.name", "fetch_invoice"),
                                    _kv("gen_ai.tool.call.id", "call_99"),
                                    _kv(
                                        "gen_ai.tool.call.arguments",
                                        json.dumps({"account": "acme", "api_key": secret_tok}),
                                    ),
                                    _kv("gen_ai.tool.call.result", '{"status": "paid"}'),
                                ],
                                "status": {"code": 1},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    otlp_path.write_text(json.dumps(otlp_payload), encoding="utf-8")
    return dataset_path, otlp_path, secret_tok, bearer_tok


@pytest.mark.gate_determinism
def test_us3_cli_ingest_and_run_otel_determinism_and_purity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Cold-start subprocess check on `evalforge-maestro --help`
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from evalforge_maestro.cli.parser import parse_and_dispatch; "
                "rc = parse_and_dispatch(['--help']); "
                "heavy = [m for m in ('opentelemetry', 'opentelemetry_sdk', 'litellm', "
                "'docpipe_maestro', 'numpy', 'scipy', 'tomllib') if m in sys.modules]; "
                "assert rc == 0 and not heavy, (rc, heavy)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr

    dataset_path, otlp_path, secret_tok, bearer_tok = _write_otel_fixtures(tmp_path)

    # 1) CLI ingest-otel -> JSONL export, JSON export, --json stdout, and --quiet
    exported_jsonl = tmp_path / "replays.jsonl"
    exported_json = tmp_path / "replays.json"

    rc, out_quiet, _ = _run_cli(
        [
            "ingest-otel",
            str(otlp_path),
            "--dataset",
            str(dataset_path),
            "--output",
            str(exported_jsonl),
            "--system-version",
            "cli-otel-v1",
            "--model-id",
            "glm-5.3",
            "--quiet",
        ],
        capsys,
    )
    assert rc == 0
    assert out_quiet == ""
    assert exported_jsonl.is_file()
    raw_jsonl_text = exported_jsonl.read_text(encoding="utf-8")
    assert secret_tok not in raw_jsonl_text
    assert bearer_tok not in raw_jsonl_text
    parsed_line = ExecutionResult.model_validate_json(raw_jsonl_text.strip())
    assert parsed_line.case_id == "c-otel-1"
    assert parsed_line.system_version == "cli-otel-v1"

    # Also verify .json array export & --json stdout
    rc, out_json, _ = _run_cli(
        [
            "ingest-otel",
            str(otlp_path),
            "--output",
            str(exported_json),
            "--json",
        ],
        capsys,
    )
    assert rc == 0
    assert secret_tok not in out_json
    assert bearer_tok not in out_json
    stdout_list = json.loads(out_json)
    assert isinstance(stdout_list, list) and len(stdout_list) == 1
    assert json.loads(exported_json.read_text(encoding="utf-8")) == stdout_list
    assert ReplayAdapter.from_file(exported_jsonl).case_ids == frozenset({"c-otel-1"})

    # Error exit code 2 on missing OTel file and corrupt JSON
    rc, err_json, _ = _run_cli(
        ["ingest-otel", str(tmp_path / "missing.json"), "--json"],
        capsys,
    )
    assert rc == 2
    assert CLIErrorPayload.model_validate_json(err_json).exit_code == 2

    bad_file = tmp_path / "corrupt.json"
    bad_file.write_text("{corrupt", encoding="utf-8")
    rc, _, _ = _run_cli(["ingest-otel", str(bad_file)], capsys)
    assert rc == 2

    # 2) Conflict rejection on run --otel-traces + --executions or --target -> exit code 2
    rc, conflict_json, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--otel-traces",
            str(otlp_path),
            "--executions",
            str(exported_jsonl),
            "--json",
        ],
        capsys,
    )
    assert rc == 2
    assert CLIErrorPayload.model_validate_json(conflict_json).exit_code == 2

    rc, _, _ = _run_cli(
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--otel-traces",
            str(otlp_path),
            "--target",
            "mod:fn",
        ],
        capsys,
    )
    assert rc == 2

    # 3) Two identical deterministic CLI `run --otel-traces` runs (--repeats 2, truncation)
    run_outputs: list[dict[str, Any]] = []
    for label in ("a", "b"):
        storage_dir = tmp_path / f"store_{label}"
        json_out = tmp_path / f"report_{label}.json"
        md_out = tmp_path / f"report_{label}.md"
        rc, _, _ = _run_cli(
            [
                "run",
                "--storage-dir",
                str(storage_dir),
                "--dataset",
                str(dataset_path),
                "--otel-traces",
                str(otlp_path),
                "--run-id",
                "otel-det-run",
                "--repeats",
                "2",
                "--max-context-chars",
                "60",
                "--metric",
                "exact_match",
                "--metric",
                "precision_at_k:k=1",
                "--metric",
                "tool_selection",
                "--metric",
                "argument_correctness",
                "--metric",
                "policy_compliance",
                "--json-out",
                str(json_out),
                "--markdown-out",
                str(md_out),
                "--quiet",
            ],
            capsys,
        )
        assert rc == 0
        json_text = json_out.read_text(encoding="utf-8")
        md_text = md_out.read_text(encoding="utf-8")
        for s in (secret_tok, bearer_tok):
            assert s not in json_text
            assert s not in md_text
        doc = ReportDocument.model_validate_json(json_text)
        assert doc.evaluation is not None
        assert len(doc.cohort_run_ids) == 2
        assert doc.evaluation.case_results[0].execution.truncated is True
        assert len(doc.evaluation.case_results[0].execution.retrieved_chunks[0].text) <= 60
        for mid in (
            "exact_match",
            "precision_at_k",
            "tool_selection",
            "argument_correctness",
            "policy_compliance",
        ):
            assert doc.evaluation.aggregates[mid].mean_score == 1.0
        stored = LocalRunStore(storage_dir).load_run("otel-det-run-r01")
        assert stored.aggregates["tool_selection"].mean_score == 1.0
        payload = json.loads(json_text)
        payload.pop("generated_at", None)
        if isinstance(payload.get("evaluation"), dict):
            payload["evaluation"].pop("timestamp", None)
        run_outputs.append(payload)

    assert run_outputs[0] == run_outputs[1]

    # 4) Parity check: run --executions <exported.jsonl> matches run --otel-traces scores
    replay_store = tmp_path / "store_replay"
    replay_json = tmp_path / "report_replay.json"
    rc, _, _ = _run_cli(
        [
            "run",
            "--storage-dir",
            str(replay_store),
            "--dataset",
            str(dataset_path),
            "--executions",
            str(exported_jsonl),
            "--run-id",
            "replay-parity-run",
            "--metric",
            "exact_match",
            "--metric",
            "precision_at_k:k=1",
            "--metric",
            "tool_selection",
            "--metric",
            "argument_correctness",
            "--metric",
            "policy_compliance",
            "--json-out",
            str(replay_json),
            "--quiet",
        ],
        capsys,
    )
    assert rc == 0
    replay_doc = ReportDocument.model_validate_json(replay_json.read_text(encoding="utf-8"))
    assert replay_doc.evaluation is not None
    assert replay_doc.evaluation.aggregates["tool_selection"].mean_score == 1.0
