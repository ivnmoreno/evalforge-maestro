"""Pure stdlib CLI argument parser preserving cold-start isolation on --help."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any, NoReturn


class CLIUsageError(Exception):
    """Raised internally when CLI arguments fail syntax or constraint parsing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _StrictArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CLIUsageError(message)


def _package_version() -> str:
    try:
        return version("evalforge-maestro")
    except PackageNotFoundError:  # pragma: no cover - source checkout fallback
        return "0.1.0.dev0"


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="Explicit path to TOML config file (overrides non-recursive ./evalforge.toml).",
    )
    parser.add_argument(
        "--env-file",
        default=argparse.SUPPRESS,
        help="Explicit opt-in .env file loaded strictly below OS environment variables.",
    )
    parser.add_argument(
        "--storage-dir",
        default=argparse.SUPPRESS,
        help="Artifact store directory root (default: .evalforge).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=argparse.SUPPRESS,
        help="Stderr diagnostic verbosity level.",
    )
    parser.add_argument(
        "--log-json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit structured JSON log records strictly to stderr.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit solely a single schema-validated JSON payload to stdout.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suppress default non-JSON human output to stdout (useful with file export flags).",
    )


def _add_export_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json-out",
        default=argparse.SUPPRESS,
        help="Write schema-validated JSON report to file path.",
    )
    parser.add_argument(
        "--markdown-out",
        default=argparse.SUPPRESS,
        help="Write rendered Markdown diagnostic report to file path.",
    )
    parser.add_argument(
        "--output",
        default=argparse.SUPPRESS,
        help="Alias for --markdown-out when exporting Markdown reports to disk.",
    )


def _add_otel_extractor_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--otel-case-id-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key providing EvaluationCase.id.",
    )
    p.add_argument(
        "--otel-input-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding case input extraction.",
    )
    p.add_argument(
        "--otel-output-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding final output extraction.",
    )
    p.add_argument(
        "--otel-model-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding model_id extraction.",
    )
    p.add_argument(
        "--otel-service-version-attr",
        default=argparse.SUPPRESS,
        help="OTel span/resource attribute key overriding system_version extraction.",
    )
    p.add_argument(
        "--otel-step-kind-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding TraceStepKind classification.",
    )
    p.add_argument(
        "--otel-tool-name-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding tool name extraction.",
    )
    p.add_argument(
        "--otel-tool-args-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding tool arguments extraction.",
    )
    p.add_argument(
        "--otel-tool-result-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding tool result extraction.",
    )
    p.add_argument(
        "--otel-retrieval-attr",
        default=argparse.SUPPRESS,
        help="OTel span attribute key overriding retrieved chunk documents extraction.",
    )
    p.add_argument(
        "--otel-timestamp-unit",
        choices=["auto", "ns", "us", "ms", "s"],
        default=argparse.SUPPRESS,
        help="Timestamp unit for numeric OTel span start/end timestamps (default: auto).",
    )
    p.add_argument(
        "--otel-match-input",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Allow unambiguous fallback matching of trace input to EvaluationCase.input.",
    )


def _add_run_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "run",
        help="Execute dataset evaluation, optional baseline/trend gating, and report export.",
    )
    _add_global_flags(p)
    _add_export_flags(p)
    p.add_argument("--dataset", default=argparse.SUPPRESS, help="Path to JSONL evaluation dataset.")
    p.add_argument("--dataset-id", default=argparse.SUPPRESS, help="Logical dataset identifier.")
    p.add_argument("--dataset-version", default=argparse.SUPPRESS, help="Dataset version label.")
    p.add_argument(
        "--executions",
        default=argparse.SUPPRESS,
        help="Pre-captured ExecutionResult trace file (JSONL/JSON/RunRecord) for offline replay.",
    )
    p.add_argument(
        "--otel-traces",
        default=argparse.SUPPRESS,
        help="OpenTelemetry span export file (OTLP JSON/array/JSONL) for offline evaluation.",
    )
    _add_otel_extractor_flags(p)
    p.add_argument(
        "--target",
        default=argparse.SUPPRESS,
        help="Live target entrypoint reference formatted as 'module.path:attribute'.",
    )
    p.add_argument(
        "--target-type",
        choices=["callable", "rag", "docpipe", "replay", "agent"],
        default=argparse.SUPPRESS,
        help="Target adapter mode.",
    )
    p.add_argument(
        "--target-arg-mode",
        choices=["input", "case"],
        default=argparse.SUPPRESS,
        help="Argument passed to target callable ('input' or full 'case').",
    )
    p.add_argument("--system-version", default=argparse.SUPPRESS, help="Target system version.")
    p.add_argument("--model-id", default=argparse.SUPPRESS, help="Target model identifier.")
    p.add_argument(
        "--docpipe-mode",
        choices=["answer_detailed", "retrieve"],
        default=argparse.SUPPRESS,
        help="Docpipe integration mode.",
    )
    p.add_argument("--docpipe-collection", default=argparse.SUPPRESS, help="Docpipe collection.")
    p.add_argument(
        "--docpipe-persist-dir",
        default=argparse.SUPPRESS,
        help="Docpipe persistence directory path (default: .docpipe).",
    )
    p.add_argument("--docpipe-top-k", type=int, default=argparse.SUPPRESS, help="Docpipe top_k.")
    p.add_argument(
        "--docpipe-embed-model",
        default=argparse.SUPPRESS,
        help="Docpipe embedding model override passed to retrieve().",
    )
    p.add_argument(
        "--docpipe-answer-model",
        default=argparse.SUPPRESS,
        help="Docpipe generation model override passed to answer_detailed().",
    )
    p.add_argument(
        "--docpipe-api-base",
        default=argparse.SUPPRESS,
        help="Docpipe generation api_base URL override passed to answer_detailed().",
    )
    p.add_argument(
        "--docpipe-searcher",
        default=argparse.SUPPRESS,
        help="Docpipe retrieval searcher strategy (e.g., default, fts5_hybrid).",
    )
    p.add_argument(
        "--docpipe-rerank",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable docpipe second-stage cross-encoder reranking during retrieve().",
    )
    p.add_argument(
        "--metric",
        action="append",
        default=argparse.SUPPRESS,
        help=(
            "Metric spec (e.g., exact_match, precision_at_k:k=5, groundedness, tool_selection). "
            "Repeatable."
        ),
    )
    p.add_argument(
        "--mock",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Run model-based judges deterministically offline without network or API keys.",
    )
    p.add_argument(
        "--local-only",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Block outbound non-loopback network endpoints pre-network (exit code 4).",
    )
    p.add_argument(
        "--block-pii",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Scan outbound non-mock remote payloads for PII/secrets pre-network (exit code 4).",
    )
    p.add_argument("--judge-model", default=argparse.SUPPRESS, help="Judge model identifier.")
    p.add_argument("--judge-api-base", default=argparse.SUPPRESS, help="Judge API base URL.")
    p.add_argument(
        "--judge-temperature", type=float, default=argparse.SUPPRESS, help="Judge temperature."
    )
    p.add_argument(
        "--judge-pass-threshold",
        type=float,
        default=argparse.SUPPRESS,
        help="Judge pass threshold [0.0..1.0].",
    )
    p.add_argument(
        "--judge-max-retries", type=int, default=argparse.SUPPRESS, help="Judge retry limit."
    )
    p.add_argument(
        "--judge-timeout", type=float, default=argparse.SUPPRESS, help="Judge timeout seconds."
    )
    p.add_argument(
        "--embedding-model",
        default=argparse.SUPPRESS,
        help="Embedding model identifier (isolated from [judge]).",
    )
    p.add_argument(
        "--embedding-api-base",
        default=argparse.SUPPRESS,
        help="Embedding API base URL (isolated from [judge]).",
    )
    p.add_argument(
        "--embedding-pass-threshold",
        type=float,
        default=argparse.SUPPRESS,
        help="Embedding metric pass threshold [0.0..1.0].",
    )
    p.add_argument(
        "--embedding-aggregation",
        choices=["max", "mean"],
        default=argparse.SUPPRESS,
        help="Context embedding chunk aggregation ('max' or 'mean').",
    )
    p.add_argument(
        "--embedding-max-retries",
        type=int,
        default=argparse.SUPPRESS,
        help="Embedding provider retry limit.",
    )
    p.add_argument(
        "--embedding-timeout",
        type=float,
        default=argparse.SUPPRESS,
        help="Embedding provider timeout seconds.",
    )
    p.add_argument(
        "--embedding-max-input-chars",
        type=int,
        default=argparse.SUPPRESS,
        help="Pre-provider embedding text truncation limit in characters.",
    )
    p.add_argument("--seed", type=int, default=argparse.SUPPRESS, help="Deterministic seed.")
    p.add_argument(
        "--repeats",
        type=int,
        default=argparse.SUPPRESS,
        help="Number of immutable evaluation repeats to execute (>= 1).",
    )
    p.add_argument(
        "--baseline",
        default=argparse.SUPPRESS,
        help="Explicit baseline run_id or pinned alias to compare against.",
    )
    p.add_argument(
        "--baseline-run",
        action="append",
        default=argparse.SUPPRESS,
        help=(
            "Additional baseline run_id or pinned alias for multi-run cohort comparison. "
            "Repeatable."
        ),
    )
    p.add_argument(
        "--confidence-level",
        type=float,
        default=argparse.SUPPRESS,
        help="Statistical CI confidence level in (0.0, 1.0) (default: 0.95).",
    )
    p.add_argument(
        "--min-statistical-samples",
        type=int,
        default=argparse.SUPPRESS,
        help="Minimum paired cases / runs per cohort for significance testing (>= 2).",
    )
    p.add_argument(
        "--fail-on-significant-regression",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Escalate statistically significant regressions to QualityGate FAIL.",
    )
    p.add_argument(
        "--trend-window",
        type=int,
        default=argparse.SUPPRESS,
        help="Optional sliding trend window size (N >= 2).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Escalate WARNING and INCONCLUSIVE gate determinations to exit code 1.",
    )
    p.add_argument(
        "--fail-fast",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Abort batch execution on first adapter or judge error (exit code 3).",
    )
    p.add_argument(
        "--max-concurrency", type=int, default=argparse.SUPPRESS, help="Bounded async workers."
    )
    p.add_argument(
        "--max-dataset-cases",
        type=int,
        default=argparse.SUPPRESS,
        help="Maximum streamed cases to evaluate.",
    )
    p.add_argument(
        "--max-context-chars",
        type=int,
        default=argparse.SUPPRESS,
        help="Post-scoring trace truncation limit in characters.",
    )
    p.add_argument(
        "--case-timeout",
        type=float,
        default=argparse.SUPPRESS,
        help="Per-case execution timeout seconds.",
    )
    p.add_argument(
        "--max-memory-mb",
        type=float,
        default=argparse.SUPPRESS,
        help="Resident memory soft-cap in MiB.",
    )
    p.add_argument(
        "--memory-limit-action",
        choices=["warn", "abort"],
        default=argparse.SUPPRESS,
        help="Behavior when max-memory-mb is exceeded.",
    )
    p.add_argument("--run-id", default=argparse.SUPPRESS, help="Explicit immutable run identifier.")


def _add_compare_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "compare",
        help="Compare candidate run(s) against baseline run ID(s) or pinned alias(es).",
    )
    _add_global_flags(p)
    _add_export_flags(p)
    p.add_argument(
        "candidate_run_ids",
        nargs="+",
        metavar="candidate_run_id",
        help="One or more candidate RunRecord IDs.",
    )
    p.add_argument(
        "--baseline",
        default=argparse.SUPPRESS,
        help="Baseline run ID or pinned baseline alias.",
    )
    p.add_argument(
        "--baseline-run",
        action="append",
        default=argparse.SUPPRESS,
        help="Additional baseline run ID or pinned alias for multi-run cohort comparison.",
    )
    p.add_argument(
        "--confidence-level",
        type=float,
        default=argparse.SUPPRESS,
        help="Statistical CI confidence level in (0.0, 1.0) (default: 0.95).",
    )
    p.add_argument(
        "--min-statistical-samples",
        type=int,
        default=argparse.SUPPRESS,
        help="Minimum paired cases / runs per cohort for significance testing (>= 2).",
    )
    p.add_argument(
        "--fail-on-significant-regression",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Escalate statistically significant regressions to QualityGate FAIL.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Escalate WARNING and INCONCLUSIVE gate determinations to exit code 1.",
    )
    p.add_argument("--min-score", type=float, default=argparse.SUPPRESS, help="Global score floor.")
    p.add_argument(
        "--max-regression-drop",
        type=float,
        default=argparse.SUPPRESS,
        help="Maximum allowed regression drop.",
    )


def _add_trend_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "trend",
        help="Analyze OLS linear trend slopes across a sliding window of historical runs.",
    )
    _add_global_flags(p)
    _add_export_flags(p)
    p.add_argument("--window", type=int, default=argparse.SUPPRESS, help="Window size (N >= 2).")
    p.add_argument("--dataset-id", default=argparse.SUPPRESS, help="Filter runs to dataset_id.")
    p.add_argument(
        "--all-datasets",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Analyze runs across all dataset IDs instead of scoping to latest.",
    )
    p.add_argument("--model-id", default=argparse.SUPPRESS, help="Filter runs to model_id.")
    p.add_argument(
        "--metric",
        action="append",
        default=argparse.SUPPRESS,
        help="Metric identifier(s) to summarize. Repeatable.",
    )
    p.add_argument(
        "--slope-threshold",
        type=float,
        default=argparse.SUPPRESS,
        help="Slope classification threshold.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Escalate WARNING and INCONCLUSIVE gate determinations to exit code 1.",
    )


def _add_calibrate_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "calibrate",
        help="Calibrate a model-based judge against human ground-truth samples.",
    )
    _add_global_flags(p)
    _add_export_flags(p)
    p.add_argument(
        "--samples", required=True, help="Path to JSONL/JSON HumanCalibrationSample file."
    )
    p.add_argument(
        "--metric",
        required=True,
        help="Judge metric identifier (e.g., groundedness, answer_relevance, custom_rubric).",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Run calibration deterministically offline in mock mode.",
    )
    p.add_argument(
        "--local-only",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Block non-loopback judge endpoints pre-network (exit code 4).",
    )
    p.add_argument(
        "--block-pii",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Scan outbound non-mock remote calibration samples for PII/secrets (exit code 4).",
    )
    p.add_argument("--judge-model", default=argparse.SUPPRESS, help="Judge model identifier.")
    p.add_argument("--judge-api-base", default=argparse.SUPPRESS, help="Judge API base URL.")
    p.add_argument(
        "--judge-pass-threshold",
        type=float,
        default=argparse.SUPPRESS,
        help="Active judge pass threshold [0.0..1.0].",
    )
    p.add_argument(
        "--human-threshold",
        type=float,
        default=0.5,
        help="Human score threshold converting continuous human labels to pass/fail.",
    )
    p.add_argument(
        "--score-divergence-threshold",
        type=float,
        default=0.25,
        help="Divergence threshold flagging large same-verdict numeric score gaps.",
    )
    p.add_argument(
        "--min-agreement",
        type=float,
        default=argparse.SUPPRESS,
        help="Optional minimum exact agreement percentage [0..100] (exits 1 if missed).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Exit with code 1 when zero valid samples or inconclusive judgments occur.",
    )
    p.add_argument(
        "--max-concurrency",
        type=int,
        default=argparse.SUPPRESS,
        help="Maximum concurrent calibration judge calls.",
    )


def _add_baseline_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "baseline",
        help="Pin, list, inspect, or delete named baselines without mutating runs.",
    )
    _add_global_flags(p)
    b_sub = p.add_subparsers(dest="baseline_action", required=True, metavar="<action>")

    p_set = b_sub.add_parser("set", help="Pin a persisted RunRecord as a named baseline.")
    _add_global_flags(p_set)
    p_set.add_argument("run_id", help="Persisted RunRecord ID to pin.")
    p_set.add_argument(
        "--name", default="default", help="Baseline alias name (default: 'default')."
    )
    p_set.add_argument("--note", default=None, help="Optional annotation note.")
    p_set.add_argument("--tag", action="append", default=None, help="Optional tag (repeatable).")
    p_set.add_argument("--overwrite", action="store_true", help="Overwrite existing alias pointer.")

    p_list = b_sub.add_parser("list", help="List all pinned baselines sorted by name.")
    _add_global_flags(p_list)

    p_show = b_sub.add_parser("show", help="Inspect details of one pinned baseline.")
    _add_global_flags(p_show)
    p_show.add_argument("name", nargs="?", default="default", help="Baseline alias name.")

    p_del = b_sub.add_parser("delete", aliases=["remove"], help="Unpin a baseline alias.")
    _add_global_flags(p_del)
    p_del.add_argument("name", help="Baseline alias name to remove.")


def _add_report_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "report",
        help="Render JSON and/or Markdown reports from stored runs, trends, or artifact files.",
    )
    _add_global_flags(p)
    _add_export_flags(p)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--run", dest="report_run_id", help="Generate report for stored RunRecord ID.")
    src.add_argument(
        "--compare",
        dest="report_compare_id",
        help="Generate pairwise comparison report for candidate RunRecord ID.",
    )
    src.add_argument(
        "--trend",
        dest="report_trend",
        action="store_true",
        help="Generate sliding-window trend report across stored runs.",
    )
    src.add_argument(
        "--artifact",
        dest="report_artifact",
        help=(
            "Render report from saved JSON file (ReportDocument/Run/Comparison/Trend/Calibration)."
        ),
    )
    p.add_argument("--baseline", default=argparse.SUPPRESS, help="Baseline run ID or pinned alias.")
    p.add_argument("--window", type=int, default=argparse.SUPPRESS, help="Trend window (N >= 2).")
    p.add_argument("--dataset-id", default=argparse.SUPPRESS, help="Filter trend runs by dataset.")
    p.add_argument("--all-datasets", action="store_true", default=argparse.SUPPRESS)
    p.add_argument("--model-id", default=argparse.SUPPRESS, help="Filter trend runs by model.")
    p.add_argument("--title", default=None, help="Optional custom report title.")


def _add_config_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "config",
        help="Inspect effective resolved configuration (with secrets masked) or validate config.",
    )
    _add_global_flags(p)
    c_sub = p.add_subparsers(dest="config_action", required=True, metavar="<action>")

    p_show = c_sub.add_parser("show", help="Display effective resolved configuration and sources.")
    _add_global_flags(p_show)
    p_show.add_argument(
        "--resolved",
        action="store_true",
        default=True,
        help="Show final merged values with origin tier and masked secrets (default).",
    )

    p_val = c_sub.add_parser("validate", help="Validate TOML syntax, env vars, and schema rules.")
    _add_global_flags(p_val)


def _add_ingest_otel_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "ingest-otel",
        help="Normalize OTel trace exports into replayable ExecutionResult JSON/JSONL records.",
    )
    p.add_argument(
        "otel_path",
        help="Path to OTLP JSON, flat span array JSON, or JSONL span export file.",
    )
    _add_global_flags(p)
    p.add_argument("--dataset", default=argparse.SUPPRESS, help="Optional dataset JSONL path.")
    p.add_argument("--dataset-id", default=argparse.SUPPRESS, help="Logical dataset identifier.")
    p.add_argument("--dataset-version", default=argparse.SUPPRESS, help="Dataset version label.")
    p.add_argument(
        "--output",
        dest="otel_output",
        default=None,
        help="Write ExecutionResult records to .json (array) or .jsonl file.",
    )
    p.add_argument("--system-version", default=argparse.SUPPRESS, help="Target system version.")
    p.add_argument("--model-id", default=argparse.SUPPRESS, help="Target model identifier.")
    _add_otel_extractor_flags(p)


def _add_index_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "index",
        help="Manage the rebuildable local SQLite query index (.evalforge/index.sqlite3).",
    )
    _add_global_flags(p)
    sub = p.add_subparsers(dest="index_action", required=True, metavar="<action>")
    for action, help_text in (
        ("rebuild", "Atomically rebuild the SQLite index strictly from canonical JSON artifacts."),
        ("sync", "Incrementally index newly committed canonical runs and baseline changes."),
        ("status", "Inspect SQLite index health, schema version, and canonical sync parity."),
    ):
        sp = sub.add_parser(action, help=help_text)
        _add_global_flags(sp)
        sp.add_argument(
            "--db-path",
            default=None,
            help="Optional custom SQLite index file path (default: <storage_dir>/index.sqlite3).",
        )


def _add_query_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    p = subparsers.add_parser(
        "query",
        help="Query indexed evaluation runs and per-case outcomes from local SQLite cache.",
    )
    _add_global_flags(p)
    sub = p.add_subparsers(dest="query_target", required=True, metavar="<target>")

    p_runs = sub.add_parser("runs", help="Query indexed RunRecord summaries with typed filters.")
    _add_global_flags(p_runs)
    p_runs.add_argument("--db-path", default=None, help="Optional custom SQLite index file path.")
    p_runs.add_argument(
        "--no-auto-sync",
        action="store_true",
        default=False,
        help="Require an already built index and fail instead of syncing before querying.",
    )
    p_runs.add_argument("--dataset-id", dest="q_dataset_id", default=None)
    p_runs.add_argument("--dataset-version", dest="q_dataset_version", default=None)
    p_runs.add_argument("--run-id", dest="q_run_ids", action="append", default=None)
    p_runs.add_argument("--model-id", dest="q_model_id", default=None)
    p_runs.add_argument("--system-version", dest="q_system_version", default=None)
    p_runs.add_argument("--baseline", dest="q_baseline", default=None)
    p_runs.add_argument("--metric", dest="q_metric_id", default=None)
    p_runs.add_argument("--min-score", dest="q_min_score", type=float, default=None)
    p_runs.add_argument("--max-score", dest="q_max_score", type=float, default=None)
    p_runs.add_argument("--mandatory-failures-only", action="store_true", default=False)
    p_runs.add_argument("--since", default=None, help="Lower UTC ISO-8601 timestamp bound.")
    p_runs.add_argument("--until", default=None, help="Upper UTC ISO-8601 timestamp bound.")
    p_runs.add_argument(
        "--order-by",
        choices=["timestamp_desc", "timestamp_asc", "run_id_asc"],
        default="timestamp_desc",
    )
    p_runs.add_argument("--limit", type=int, default=50)
    p_runs.add_argument("--offset", type=int, default=0)

    p_cases = sub.add_parser("cases", help="Query indexed per-case metric evaluations.")
    _add_global_flags(p_cases)
    p_cases.add_argument("--db-path", default=None, help="Optional custom SQLite index file path.")
    p_cases.add_argument(
        "--no-auto-sync",
        action="store_true",
        default=False,
        help="Require an already built index and fail instead of syncing before querying.",
    )
    p_cases.add_argument("--run-id", dest="q_run_id", default=None)
    p_cases.add_argument("--dataset-id", dest="q_dataset_id", default=None)
    p_cases.add_argument("--case-id", dest="q_case_id", default=None)
    p_cases.add_argument("--metric", dest="q_metric_id", default=None)
    p_cases.add_argument(
        "--status",
        dest="q_status",
        choices=["PASS", "FAIL", "WARNING", "INCONCLUSIVE", "NOT_APPLICABLE"],
        default=None,
    )
    p_cases.add_argument("--mandatory-only", action="store_true", default=False)
    p_cases.add_argument("--min-score", dest="q_min_score", type=float, default=None)
    p_cases.add_argument("--max-score", dest="q_max_score", type=float, default=None)
    p_cases.add_argument("--errors-only", action="store_true", default=False)
    p_cases.add_argument("--anomalies-only", action="store_true", default=False)
    p_cases.add_argument("--limit", type=int, default=100)
    p_cases.add_argument("--offset", type=int, default=0)


def build_parser() -> _StrictArgumentParser:
    """Build top-level CLI parser with zero heavy or config-file imports."""
    parser = _StrictArgumentParser(
        prog="evalforge-maestro",
        description=(
            "EvalForge Maestro — Independent LLM evaluation and regression verification CLI."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"evalforge-maestro {_package_version()}",
    )
    _add_global_flags(parser)
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<subcommand>")
    _add_run_parser(subparsers)
    _add_compare_parser(subparsers)
    _add_trend_parser(subparsers)
    _add_calibrate_parser(subparsers)
    _add_baseline_parser(subparsers)
    _add_report_parser(subparsers)
    _add_config_parser(subparsers)
    _add_ingest_otel_parser(subparsers)
    _add_index_parser(subparsers)
    _add_query_parser(subparsers)
    return parser


def parse_and_dispatch(argv: Sequence[str] | None = None) -> int:
    """Parse CLI argv cleanly, preserving cold-start isolation before executing commands."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    wants_json = "--json" in raw_argv
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        return code
    except CLIUsageError as exc:
        sys.stderr.write(f"error: {exc.message}\n")
        if wants_json:
            from evalforge_maestro._canonical import canonical_json_str
            from evalforge_maestro.types import CLIErrorPayload

            err = CLIErrorPayload(
                exit_code=2,
                error_type="CLIUsageError",
                message=exc.message,
                hint="Run 'evalforge-maestro --help' for valid syntax.",
            )
            sys.stdout.write(canonical_json_str(err.model_dump(mode="json")) + "\n")
        return 2

    from evalforge_maestro.cli.commands import dispatch_command

    return dispatch_command(args)
