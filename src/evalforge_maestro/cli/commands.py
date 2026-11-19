"""CLI command handlers, artifact loading, stream/file export, and POSIX exit mapping."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalforge_maestro._canonical import canonical_json_str, redact_secrets, scrub_secret_text
from evalforge_maestro.cli.config import (
    format_resolved_config_text,
    parse_metric_spec_text,
    resolve_cli_config,
)
from evalforge_maestro.cli.logging_utils import CLIStructuredLogger
from evalforge_maestro.cli.targets import (
    build_calibration_judge,
    build_metrics_from_config,
    build_target_adapter,
    preflight_run_security,
)
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import (
    AdapterError,
    ConfigurationError,
    DatasetError,
    EvalforgeError,
    ExecutionError,
    JudgeError,
    LocalOnlyPolicyError,
    MetricError,
    MissingExtraError,
    StorageError,
)
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.judges import calibrate_judge
from evalforge_maestro.judges.security import (
    is_remote_judge_endpoint,
    validate_local_only_target,
    validate_pii_egress,
)
from evalforge_maestro.regression import QualityGate, analyze_trend, compare_runs
from evalforge_maestro.reporting import (
    build_calibration_report,
    build_comparison_report,
    build_run_report,
    build_trend_report,
    render_markdown,
    render_report_json,
)
from evalforge_maestro.storage import LocalRunStore
from evalforge_maestro.types import (
    BaselineCommandPayload,
    BaselineEntry,
    CalibrationReport,
    CLIErrorPayload,
    CLIResolvedConfig,
    ConfigValidationPayload,
    GateDecision,
    GateRuleCheck,
    HumanCalibrationSample,
    MetricStatus,
    QualityGatePolicy,
    QualityGateResult,
    ReportDocument,
    RunComparisonReport,
    RunRecord,
    TrendReport,
)

_EXIT_CODE_2_TYPES = (
    ConfigurationError,
    DatasetError,
    MetricError,
    StorageError,
)
_EXIT_CODE_3_TYPES = (
    AdapterError,
    ExecutionError,
    JudgeError,
    MissingExtraError,
)


def _write_text_file(path_str: str, content: str) -> None:
    path = Path(path_str)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Failed writing output artifact to {path}: {exc}") from exc


def _emit_report(
    document: ReportDocument,
    args: argparse.Namespace,
) -> None:
    json_out = getattr(args, "json_out", None)
    markdown_out = getattr(args, "markdown_out", None) or getattr(args, "output", None)
    wants_json = bool(getattr(args, "json", False))
    quiet = bool(getattr(args, "quiet", False))

    if json_out is not None:
        _write_text_file(str(json_out), render_report_json(document, pretty=True) + "\n")
    if markdown_out is not None:
        _write_text_file(str(markdown_out), render_markdown(document))

    if wants_json:
        sys.stdout.write(render_report_json(document) + "\n")
        sys.stdout.flush()
    elif not quiet:
        sys.stdout.write(render_markdown(document))
        sys.stdout.flush()


def _emit_json_model(payload: Any) -> None:
    redacted = redact_secrets(payload.model_dump(mode="json"))
    sys.stdout.write(canonical_json_str(redacted) + "\n")
    sys.stdout.flush()


def _gate_to_exit_code(gate: QualityGateResult, *, strict: bool) -> int:
    if gate.decision == GateDecision.FAIL:
        return 1
    if strict and gate.decision in {GateDecision.WARNING, GateDecision.INCONCLUSIVE}:
        return 1
    return 0


def _resolve_baseline_run(store: LocalRunStore, ref: str) -> tuple[RunRecord, str | None]:
    baselines = {entry.name for entry in store.list_baselines()}
    if ref in baselines:
        return store.load_baseline_run(ref), ref
    return store.load_run(ref), None


def _args_to_cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    raw = dict(vars(args))
    for meta_key in (
        "command",
        "baseline_action",
        "config_action",
        "json",
        "quiet",
        "json_out",
        "markdown_out",
        "output",
        "candidate_run_id",
        "samples",
        "human_threshold",
        "score_divergence_threshold",
        "name",
        "note",
        "tag",
        "overwrite",
        "report_run_id",
        "report_compare_id",
        "report_trend",
        "report_artifact",
        "title",
        "resolved",
        "all_datasets",
    ):
        raw.pop(meta_key, None)

    cmd = getattr(args, "command", None)
    if cmd == "calibrate" and isinstance(raw.get("metric"), str):
        raw["metric"] = [raw["metric"]]
    elif cmd in {"trend", "report"}:
        raw.pop("metric", None)

    if cmd == "run" and raw.get("trend_window") is not None:
        val = int(raw["trend_window"])
        if val < 2:
            raise ConfigurationError(f"Trend window must be >= 2, got {val}")
    return raw


def _build_zero_run_trend_gate(policy: QualityGatePolicy) -> QualityGateResult:
    summary_msg = (
        f"Trend check requires baseline trend history (min_trend_runs={policy.min_trend_runs}); "
        "store has 0 matching runs (INSUFFICIENT_DATA)."
    )
    if policy.require_trend:
        return QualityGateResult(
            decision=GateDecision.FAIL,
            candidate_run_id="none",
            passed=False,
            blocking=True,
            inconclusive_rate=1.0,
            checks=[
                GateRuleCheck(
                    rule_id="trend_history",
                    status=GateDecision.FAIL,
                    message=summary_msg,
                    observed=0,
                    threshold=policy.min_trend_runs,
                )
            ],
            failure_reasons=[summary_msg],
            summary=summary_msg,
        )
    return QualityGateResult(
        decision=GateDecision.INCONCLUSIVE,
        candidate_run_id="none",
        passed=False,
        blocking=False,
        inconclusive_rate=1.0,
        checks=[
            GateRuleCheck(
                rule_id="trend_history",
                status=GateDecision.INCONCLUSIVE,
                message=summary_msg,
                observed=0,
                threshold=policy.min_trend_runs,
            )
        ],
        inconclusive_reasons=[summary_msg],
        summary=summary_msg,
    )


def _load_calibration_samples(path_str: str) -> list[HumanCalibrationSample]:
    target = Path(path_str)
    if not target.is_file():
        raise DatasetError(f"Calibration samples file not found: {target}")
    try:
        raw_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetError(f"Failed reading calibration file {target}: {exc}") from exc

    stripped = raw_text.strip()
    if not stripped:
        raise DatasetError(f"Calibration samples file {target} is empty")

    samples: list[HumanCalibrationSample] = []
    if stripped.startswith("["):
        try:
            items: Any = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Invalid JSON in calibration file {target}: {exc.msg}") from exc
        if not isinstance(items, list):
            raise DatasetError(f"Calibration JSON file {target} must contain an array")
        for idx, item in enumerate(items, start=1):
            try:
                samples.append(HumanCalibrationSample.model_validate(item))
            except (ValidationError, ValueError) as exc:
                raise DatasetError(
                    f"Invalid HumanCalibrationSample at index {idx} in {target}: {exc}",
                    line_number=idx,
                ) from exc
    else:
        for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(
                    f"Invalid JSON at line {line_no} in {target}: {exc.msg}",
                    line_number=line_no,
                ) from exc
            try:
                samples.append(HumanCalibrationSample.model_validate(parsed))
            except (ValidationError, ValueError) as exc:
                raise DatasetError(
                    f"Invalid HumanCalibrationSample at line {line_no} in {target}: {exc}",
                    line_number=line_no,
                ) from exc

    if not samples:
        raise DatasetError(f"Calibration samples file {target} contains zero valid samples")
    return samples


def _handle_run(
    args: argparse.Namespace,
    resolved: CLIResolvedConfig,
    raw_api_key: str | None,
    logger: CLIStructuredLogger,
) -> int:
    if not resolved.dataset:
        raise ConfigurationError(
            "Dataset path is required. Pass --dataset <path> or set [run].dataset in "
            "evalforge.toml."
        )
    dataset = DatasetEngine(
        resolved.dataset,
        dataset_id=resolved.dataset_id,
        dataset_version=resolved.dataset_version,
    )
    metrics = build_metrics_from_config(resolved, raw_api_key=raw_api_key)
    adapter = build_target_adapter(resolved, dataset=dataset, logger=logger)
    preflight_run_security(resolved=resolved, dataset=dataset, metrics=metrics)

    store = LocalRunStore(resolved.storage_dir)
    baseline_run: RunRecord | None = None
    baseline_alias: str | None = None
    if resolved.baseline is not None:
        baseline_run, baseline_alias = _resolve_baseline_run(store, resolved.baseline)

    logger.info(f"Starting evaluation run over dataset {dataset.dataset_id!r}.")
    orchestrator = EvaluationOrchestrator(
        config=resolved.execution,
        storage_root=resolved.storage_dir,
    )
    run_record = orchestrator.run(dataset, adapter, metrics, run_id=resolved.run_id)

    if run_record.evaluated_case_count == 0 or all(
        bool(case_rec.execution.errors) for case_rec in run_record.case_results
    ):
        raise ExecutionError(
            f"Zero evaluation cases completed without execution errors out of "
            f"{run_record.evaluated_case_count} total case(s)."
        )

    if run_record.case_results and all(
        case_rec.metrics
        and all(
            m.status == MetricStatus.INCONCLUSIVE and "JudgeError:" in m.explanation
            for m in case_rec.metrics.values()
        )
        for case_rec in run_record.case_results
    ):
        raise JudgeError(
            "Zero evaluation cases completed judge scoring due to external judge runtime failures."
        )

    comparison: RunComparisonReport | None = None
    if baseline_run is not None:
        comparison = compare_runs(
            baseline_run,
            run_record,
            baseline_name=baseline_alias,
            policy=resolved.gate,
        )

    trend: TrendReport | None = None
    if resolved.trend_window is not None:
        trend = analyze_trend(
            store.read_manifest(),
            window=resolved.trend_window,
            dataset_id=run_record.dataset_id,
            slope_threshold=resolved.gate.trend_slope_threshold,
        )

    gate_result = QualityGate(resolved.gate).evaluate(
        run_record,
        comparison=comparison,
        trend=trend,
    )
    doc = build_run_report(
        run_record,
        comparison=comparison,
        trend=trend,
        gate=gate_result,
    )
    _emit_report(doc, args)
    return _gate_to_exit_code(gate_result, strict=resolved.strict)


def _handle_compare(
    args: argparse.Namespace,
    resolved: CLIResolvedConfig,
    logger: CLIStructuredLogger,
) -> int:
    baseline_ref = resolved.baseline
    if not baseline_ref:
        raise ConfigurationError(
            "Comparison requires a baseline reference via --baseline, EVALFORGE_BASELINE, "
            "or evalforge.toml."
        )
    store = LocalRunStore(resolved.storage_dir)
    candidate_run = store.load_run(str(args.candidate_run_id))
    baseline_run, baseline_alias = _resolve_baseline_run(store, baseline_ref)
    logger.info(f"Comparing run {candidate_run.run_id!r} against baseline {baseline_run.run_id!r}.")
    comparison = compare_runs(
        baseline_run,
        candidate_run,
        baseline_name=baseline_alias,
        policy=resolved.gate,
    )
    gate_result = QualityGate(resolved.gate).evaluate(candidate_run, comparison=comparison)
    doc = build_comparison_report(
        comparison,
        candidate_run=candidate_run,
        gate=gate_result,
    )
    _emit_report(doc, args)
    return _gate_to_exit_code(gate_result, strict=resolved.strict)


def _handle_trend(
    args: argparse.Namespace,
    resolved: CLIResolvedConfig,
    logger: CLIStructuredLogger,
) -> int:
    window = getattr(args, "window", None)
    if window is None:
        window = resolved.trend_window if resolved.trend_window is not None else 5
    if window < 2:
        raise ConfigurationError(f"Trend window must be >= 2, got {window}")

    slope_threshold = getattr(args, "slope_threshold", None)
    if slope_threshold is None:
        slope_threshold = resolved.gate.trend_slope_threshold

    metric_filter = getattr(args, "metric", None)
    all_datasets = bool(getattr(args, "all_datasets", False))
    dataset_filter = getattr(args, "dataset_id", None) or resolved.dataset_id
    model_filter = getattr(args, "model_id", None) or resolved.target.model_id

    store = LocalRunStore(resolved.storage_dir)
    manifest = store.read_manifest()
    trend = analyze_trend(
        manifest,
        window=window,
        dataset_id=dataset_filter,
        all_datasets=all_datasets,
        model_id=model_filter,
        metric_ids=metric_filter,
        slope_threshold=slope_threshold,
    )
    logger.info(f"Analyzed trend across {len(trend.inspected_run_ids)} historical run(s).")

    if trend.inspected_run_ids:
        latest_run = store.load_run(trend.inspected_run_ids[-1])
        gate_result = QualityGate(resolved.gate).evaluate(latest_run, trend=trend)
    else:
        gate_result = _build_zero_run_trend_gate(resolved.gate)

    doc = build_trend_report(trend, gate=gate_result)
    _emit_report(doc, args)
    return _gate_to_exit_code(gate_result, strict=resolved.strict)


def _handle_calibrate(
    args: argparse.Namespace,
    resolved: CLIResolvedConfig,
    raw_api_key: str | None,
    logger: CLIStructuredLogger,
) -> int:
    samples = _load_calibration_samples(str(args.samples))
    cal_spec = parse_metric_spec_text(str(args.metric))
    toml_match = next(
        (m for m in resolved.metrics if m.metric_id == cal_spec.metric_id),
        None,
    )
    if toml_match is not None and not cal_spec.params:
        cal_spec = toml_match
    judge_metric = build_calibration_judge(
        cal_spec,
        resolved,
        raw_api_key=raw_api_key,
    )
    validate_local_only_target(judge_metric.judge_config)
    if resolved.security.block_pii and is_remote_judge_endpoint(judge_metric.judge_config):
        for sample in samples:
            validate_pii_egress(
                {
                    "input": sample.input,
                    "output": sample.output,
                    "reference": sample.reference,
                    "retrieved_chunks": [c.text for c in sample.retrieved_chunks],
                },
                enabled=True,
                context_label=f"calibration sample {sample.case_id!r}",
            )

    logger.info(f"Calibrating judge {args.metric!r} over {len(samples)} human-labeled sample(s).")
    cal_report = calibrate_judge(
        judge_metric,
        samples,
        human_threshold=float(args.human_threshold),
        score_divergence_threshold=float(args.score_divergence_threshold),
        max_concurrency=resolved.execution.max_concurrency,
    )
    doc = build_calibration_report(
        cal_report,
        min_agreement=resolved.judge.min_agreement,
        strict=resolved.strict,
    )
    _emit_report(doc, args)
    if doc.calibration_gate is not None and not doc.calibration_gate.passed:
        return 1
    return 0


def _format_baseline_text(payload: BaselineCommandPayload) -> str:
    if payload.action == "list":
        if not payload.baselines:
            return "No pinned baselines found.\n"
        lines = ["| Name | Run ID | Dataset | Note |", "| --- | --- | --- | --- |"]
        for entry in payload.baselines:
            lines.append(
                f"| `{entry.name}` | `{entry.run_id}` | `{entry.dataset_id}` | "
                f"{entry.note or '-'} |"
            )
        return "\n".join(lines) + "\n"
    if payload.entry is None:
        raise StorageError(f"Missing baseline entry for action {payload.action!r}")
    entry = payload.entry
    return (
        f"Baseline `{entry.name}` ({payload.action}): run_id=`{entry.run_id}`, "
        f"dataset=`{entry.dataset_id}`\n"
    )


def _handle_baseline(args: argparse.Namespace, resolved: CLIResolvedConfig) -> int:
    store = LocalRunStore(resolved.storage_dir)
    action = str(args.baseline_action)
    if action == "set":
        entry: BaselineEntry = store.pin_baseline(
            str(args.run_id),
            name=str(args.name),
            note=args.note,
            tags=args.tag,
            overwrite=bool(args.overwrite),
        )
        payload = BaselineCommandPayload(action="set", entry=entry, baselines=[entry])
    elif action == "list":
        entries = store.list_baselines()
        payload = BaselineCommandPayload(action="list", entry=None, baselines=entries)
    elif action == "show":
        entry = store.get_baseline(str(args.name))
        payload = BaselineCommandPayload(action="show", entry=entry, baselines=[entry])
    else:
        removed = store.unpin_baseline(str(args.name))
        payload = BaselineCommandPayload(action="delete", entry=removed, baselines=[])

    if bool(getattr(args, "json", False)):
        _emit_json_model(payload)
    elif not bool(getattr(args, "quiet", False)):
        sys.stdout.write(_format_baseline_text(payload))
        sys.stdout.flush()
    return 0


_ARTIFACT_SCHEMA_DISPATCH: tuple[
    tuple[tuple[str, ...], type[Any], Any],
    ...,
] = (
    (
        ("report_kind",),
        ReportDocument,
        lambda doc, title: doc.model_copy(update={"title": title}) if title else doc,
    ),
    (("case_results",), RunRecord, lambda rec, title: build_run_report(rec, title=title)),
    (
        ("baseline_run_id", "candidate_run_id"),
        RunComparisonReport,
        lambda cmp_rec, title: build_comparison_report(cmp_rec, title=title),
    ),
    (
        ("inspected_run_ids", "window"),
        TrendReport,
        lambda tr_rec, title: build_trend_report(tr_rec, title=title),
    ),
    (
        ("exact_agreement_rate", "recommended_pass_threshold"),
        CalibrationReport,
        lambda cal_rec, title: build_calibration_report(cal_rec, title=title),
    ),
)


def _load_artifact_report(path_str: str, *, title: str | None) -> ReportDocument:
    path = Path(path_str)
    if not path.is_file():
        raise DatasetError(f"Artifact file not found: {path}")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Failed reading artifact JSON {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DatasetError(f"Artifact file {path} must decode to a JSON object")

    for required_keys, model_cls, builder in _ARTIFACT_SCHEMA_DISPATCH:
        if all(key in parsed for key in required_keys):
            try:
                validated = model_cls.model_validate(parsed)
            except ValidationError as exc:
                raise DatasetError(f"Invalid {model_cls.__name__} JSON in {path}: {exc}") from exc
            doc: ReportDocument = builder(validated, title)
            return doc

    raise DatasetError(f"Unrecognized evalforge-maestro artifact JSON schema in {path}")


def _handle_report(args: argparse.Namespace, resolved: CLIResolvedConfig) -> int:
    store = LocalRunStore(resolved.storage_dir)
    custom_title: str | None = getattr(args, "title", None)

    if getattr(args, "report_artifact", None):
        doc = _load_artifact_report(str(args.report_artifact), title=custom_title)
    elif getattr(args, "report_run_id", None):
        run_rec = store.load_run(str(args.report_run_id))
        comparison: RunComparisonReport | None = None
        if resolved.baseline:
            base_run, base_alias = _resolve_baseline_run(store, resolved.baseline)
            comparison = compare_runs(
                base_run, run_rec, baseline_name=base_alias, policy=resolved.gate
            )
        trend: TrendReport | None = None
        window = getattr(args, "window", None)
        if window is not None:
            trend = analyze_trend(
                store.read_manifest(),
                window=int(window),
                dataset_id=run_rec.dataset_id,
                slope_threshold=resolved.gate.trend_slope_threshold,
            )
        gate = QualityGate(resolved.gate).evaluate(run_rec, comparison=comparison, trend=trend)
        doc = build_run_report(
            run_rec, comparison=comparison, trend=trend, gate=gate, title=custom_title
        )
    elif getattr(args, "report_compare_id", None):
        if not resolved.baseline:
            raise ConfigurationError("`report --compare` requires --baseline <run_id_or_alias>.")
        cand_run = store.load_run(str(args.report_compare_id))
        base_run, base_alias = _resolve_baseline_run(store, resolved.baseline)
        comparison = compare_runs(
            base_run, cand_run, baseline_name=base_alias, policy=resolved.gate
        )
        gate = QualityGate(resolved.gate).evaluate(cand_run, comparison=comparison)
        doc = build_comparison_report(
            comparison, candidate_run=cand_run, gate=gate, title=custom_title
        )
    else:
        window = getattr(args, "window", None)
        resolved_win = int(window) if window is not None else (resolved.trend_window or 5)
        trend = analyze_trend(
            store.read_manifest(),
            window=resolved_win,
            dataset_id=getattr(args, "dataset_id", None) or resolved.dataset_id,
            all_datasets=bool(getattr(args, "all_datasets", False)),
            model_id=getattr(args, "model_id", None) or resolved.target.model_id,
            slope_threshold=resolved.gate.trend_slope_threshold,
        )
        gate = (
            QualityGate(resolved.gate).evaluate(
                store.load_run(trend.inspected_run_ids[-1]), trend=trend
            )
            if trend.inspected_run_ids
            else _build_zero_run_trend_gate(resolved.gate)
        )
        doc = build_trend_report(trend, gate=gate, title=custom_title)

    _emit_report(doc, args)
    return 0


def _handle_config(
    args: argparse.Namespace,
    resolved: CLIResolvedConfig,
    warnings: Sequence[str],
) -> int:
    action = str(args.config_action)
    wants_json = bool(getattr(args, "json", False))
    quiet = bool(getattr(args, "quiet", False))
    if action == "show":
        if wants_json:
            _emit_json_model(resolved)
        elif not quiet:
            sys.stdout.write(format_resolved_config_text(resolved))
            sys.stdout.flush()
    else:
        payload = ConfigValidationPayload(
            valid=True,
            config_path=resolved.config_path,
            env_file_path=resolved.env_file_path,
            warnings=list(warnings),
        )
        if wants_json:
            _emit_json_model(payload)
        elif not quiet:
            sys.stdout.write(
                f"Configuration valid (config={resolved.config_path or '<defaults>'}, "
                f"env_file={resolved.env_file_path or '<none>'}).\n"
            )
            sys.stdout.flush()
    return 0


def _map_exception_to_exit_code(exc: BaseException) -> tuple[int, str | None]:
    if isinstance(exc, LocalOnlyPolicyError):
        return 4, "Review --local-only / --block-pii settings and remove remote endpoints or PII."
    if isinstance(exc, MissingExtraError):
        return 3, f"Install optional extra '[{exc.extra}]' or run with --mock if applicable."
    if isinstance(exc, _EXIT_CODE_3_TYPES):
        return 3, "Inspect adapter/judge availability or rerun without --fail-fast for isolation."
    if isinstance(exc, _EXIT_CODE_2_TYPES):
        return 2, "Verify CLI flags, dataset/artifact paths, metrics, and evalforge.toml syntax."
    if isinstance(exc, EvalforgeError):
        return 2, None
    return 3, None


def dispatch_command(args: argparse.Namespace) -> int:
    """Resolve configuration, run selected subcommand, and enforce POSIX exit codes 0-4."""
    wants_json = bool(getattr(args, "json", False))
    logger = CLIStructuredLogger(
        level=str(getattr(args, "log_level", "WARNING")),
        log_json=bool(getattr(args, "log_json", False)),
    )
    try:
        cli_overrides = _args_to_cli_overrides(args)
        resolved, raw_api_key, warnings = resolve_cli_config(cli_overrides=cli_overrides)
        logger.configure(level=resolved.logging.log_level, log_json=resolved.logging.log_json)
        for warning_msg in warnings:
            logger.warning(warning_msg)

        cmd = str(args.command)
        if cmd == "run":
            return _handle_run(args, resolved, raw_api_key, logger)
        if cmd == "compare":
            return _handle_compare(args, resolved, logger)
        if cmd == "trend":
            return _handle_trend(args, resolved, logger)
        if cmd == "calibrate":
            return _handle_calibrate(args, resolved, raw_api_key, logger)
        if cmd == "baseline":
            return _handle_baseline(args, resolved)
        if cmd == "report":
            return _handle_report(args, resolved)
        if cmd == "config":
            return _handle_config(args, resolved, warnings)
        raise ConfigurationError(f"Unsupported CLI subcommand: {cmd!r}")
    except EvalforgeError as exc:
        code, hint = _map_exception_to_exit_code(exc)
        safe_msg = scrub_secret_text(str(exc))
        logger.error(safe_msg)
        if wants_json:
            _emit_json_model(
                CLIErrorPayload(
                    exit_code=code,  # type: ignore[arg-type]
                    error_type=type(exc).__name__,
                    message=safe_msg,
                    hint=hint,
                )
            )
        return code
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        safe_msg = scrub_secret_text(f"{type(exc).__name__}: {exc}")
        logger.error(safe_msg)
        if wants_json:
            _emit_json_model(
                CLIErrorPayload(
                    exit_code=3,
                    error_type=type(exc).__name__,
                    message=safe_msg,
                    hint="Unexpected runtime failure.",
                )
            )
        return 3
