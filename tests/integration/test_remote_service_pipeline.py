"""Integration tests for CLI `serve`, live loopback HTTP server, and cold-start purity."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from evalforge_maestro.cli import main as cli_main
from evalforge_maestro.types import CLIErrorPayload, ServiceEvaluateResponse


@pytest.mark.gate_determinism
def test_us2_live_loopback_http_and_cli_serve_security(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Cold-start purity check: `--help` must keep http.server and evalforge_maestro.service unloaded
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from evalforge_maestro.cli.parser import parse_and_dispatch; "
                "rc = parse_and_dispatch(['--help']); "
                "bad = [m for m in ('http.server', 'socketserver', 'evalforge_maestro.service') "
                "if any(k == m or k.startswith(m + '.') for k in sys.modules)]; "
                "assert rc == 0 and not bad, (rc, bad)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr

    # CLI `serve --host 0.0.0.0` without auth token MUST fail pre-bind with POSIX exit code 4
    root = tmp_path / ".evalforge"
    capsys.readouterr()
    rc = cli_main(["serve", "--host", "0.0.0.0", "--storage-dir", str(root), "--json"])
    out = capsys.readouterr().out
    assert rc == 4
    err_payload = CLIErrorPayload.model_validate_json(out.strip())
    assert err_payload.exit_code == 4

    # CLI `serve` startup delegates cleanly with stderr-only logging and respects `--local-only`
    capsys.readouterr()
    proc_serve_err = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from evalforge_maestro.cli import main; "
                "sys.exit(main(['serve', '--local-only', '--allow-remote-judges', '--json']))"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_serve_err.returncode == 2, proc_serve_err.stderr

    # Live multi-threaded TCP HTTP roundtrip inside an isolated subprocess (hermetic safe)
    script = f"""
import json, threading, urllib.error, urllib.request
from evalforge_maestro.service import create_http_server
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import ServiceConfig

cfg = ServiceConfig(
    host="127.0.0.1",
    port=0,
    storage_dir={str(root)!r},
    mock_mode=True,
    local_only=True,
    auth_token_configured=True,
)
token = "live-test-token-777"
srv = create_http_server(cfg, auth_token=token)
port = srv.server_address[1]
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
try:
    base = f"http://127.0.0.1:{{port}}"
    # Unauthenticated request must return 401
    try:
        urllib.request.urlopen(f"{{base}}/health")
        raise AssertionError("Expected 401")
    except urllib.error.HTTPError as e:
        assert e.code == 401

    def call(method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"{{base}}{{path}}",
            data=data,
            method=method,
            headers={{
                "Authorization": f"Bearer {{token}}",
                "Content-Type": "application/json",
            }},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    st, health = call("GET", "/health")
    assert st == 200 and health["status"] == "ok"

    st, eval_res = call("POST", "/v1/evaluate", {{
        "cases": [{{"id": "q1", "input": "Hi", "reference": "Paris"}}],
        "executions": [{{
            "case_id": "q1", "input": "Hi", "output": "Paris", "elapsed_seconds": 0.02
        }}],
        "metrics": [{{"metric_id": "exact_match"}}],
        "run_id": "live-run-1",
        "persist": True,
        "include_markdown": True,
    }})
    assert st == 200 and eval_res["persisted"] is True

    LocalRunStore({str(root)!r}).pin_baseline("live-run-1", name="main")
    st, eval_cand = call("POST", "/v1/evaluate", {{
        "cases": [{{"id": "q1", "input": "Hi", "reference": "Paris"}}],
        "executions": [{{
            "case_id": "q1", "input": "Hi", "output": "Paris", "elapsed_seconds": 0.02
        }}],
        "metrics": [{{"metric_id": "exact_match"}}],
        "run_id": "live-run-2",
        "persist": True,
    }})
    assert st == 200

    st, runs_res = call("GET", "/v1/runs")
    assert st == 200 and runs_res["total_returned"] == 2

    st, cmp_res = call("POST", "/v1/compare", {{
        "candidate_run_id": "live-run-2",
        "baseline_ref": "main",
        "include_markdown": True,
    }})
    assert st == 200 and cmp_res["comparison"]["candidate_run_id"] == "live-run-2"

    st, rep_res = call("POST", "/v1/reports", {{
        "run_id": "live-run-2",
        "baseline_ref": "main",
        "include_markdown": True,
    }})
    assert st == 200 and rep_res["markdown"]

    print(json.dumps(eval_res))
finally:
    srv.shutdown()
    srv.server_close()
    t.join(timeout=2)
"""
    live_proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert live_proc.returncode == 0, live_proc.stderr
    parsed_eval = ServiceEvaluateResponse.model_validate_json(live_proc.stdout.strip())
    assert parsed_eval.evaluation.run_id == "live-run-1"
    assert parsed_eval.evaluation.aggregates["exact_match"].mean_score == 1.0
