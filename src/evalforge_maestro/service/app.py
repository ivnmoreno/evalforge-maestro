"""Transport-agnostic HTTP application router delegating strictly to EvalForge SDK/storage."""

from __future__ import annotations

import hmac
import json
import logging
import tempfile
from collections.abc import Mapping
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from pydantic import ValidationError

from evalforge_maestro._canonical import canonical_json_bytes, redact_secrets, scrub_secret_text
from evalforge_maestro._metric_factory import (
    build_metrics_from_specs,
    check_metrics_locality_and_remote_flags,
    validate_dataset_pii_egress,
)
from evalforge_maestro.adapters.otel import ingest_otel_spans
from evalforge_maestro.adapters.replay import ReplayAdapter
from evalforge_maestro.datasets import DatasetEngine
from evalforge_maestro.exceptions import (
    AdapterError,
    ConfigurationError,
    DatasetError,
    EvalforgeError,
    ExecutionError,
    ImmutabilityError,
    JudgeError,
    LocalOnlyPolicyError,
    MetricError,
    MissingExtraError,
    StorageError,
)
from evalforge_maestro.execution import EvaluationOrchestrator
from evalforge_maestro.regression import (
    QualityGate,
    analyze_trend,
    compare_run_cohorts,
    compare_runs,
)
from evalforge_maestro.reporting import (
    build_comparison_report,
    build_run_report,
    build_trend_report,
    render_markdown,
)
from evalforge_maestro.storage import LocalRunStore, SQLiteRunIndex
from evalforge_maestro.storage.local import _validate_safe_identifier
from evalforge_maestro.types import (
    CaseQueryFilter,
    CaseQueryPayload,
    EmbeddingConfig,
    JudgeConfig,
    MetricSpecConfig,
    MetricStatus,
    OrchestratorConfig,
    RunQueryFilter,
    RunQueryPayload,
    RunRecord,
    RunSortOrder,
    ServiceCompareRequest,
    ServiceCompareResponse,
    ServiceConfig,
    ServiceErrorResponse,
    ServiceEvaluateRequest,
    ServiceEvaluateResponse,
    ServiceHealthResponse,
    ServiceOtelIngestRequest,
    ServiceOtelIngestResponse,
    ServiceReportRequest,
    ServiceReportResponse,
)

_LOGGER = logging.getLogger(__name__)
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def _package_version() -> str:
    try:
        return version("evalforge-maestro")
    except PackageNotFoundError:  # pragma: no cover - source fallback
        return "0.1.0.dev0"


def validate_service_bind_policy(
    config: ServiceConfig,
    *,
    auth_token: str | None = None,
) -> None:
    """Block non-loopback HTTP binding unless an explicit non-empty auth_token is supplied."""
    host_norm = config.host.strip().lower()
    has_token = bool(auth_token and auth_token.strip())
    if host_norm not in _LOOPBACK_HOSTS and not has_token:
        raise LocalOnlyPolicyError(
            f"Refusing to bind EvalForge HTTP service to non-loopback host {config.host!r} "
            "without auth_token / EVALFORGE_SERVICE_TOKEN."
        )


def _json_response(status: int, payload: Any) -> tuple[int, dict[str, str], bytes]:
    if hasattr(payload, "model_dump"):
        raw_obj = redact_secrets(payload.model_dump(mode="json"))
    elif isinstance(payload, list):
        raw_obj = [
            redact_secrets(item.model_dump(mode="json")) if hasattr(item, "model_dump") else item
            for item in payload
        ]
    else:
        raw_obj = redact_secrets(payload) if isinstance(payload, dict) else payload
    body = canonical_json_bytes(raw_obj)
    return (
        status,
        {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        body,
    )


def _error_response(
    status_code: int,
    error_type: str,
    message: str,
    *,
    hint: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    model = ServiceErrorResponse(
        status_code=status_code,
        error_type=error_type,
        message=message,
        hint=hint,
    )
    return _json_response(status_code, model)


def _parse_bool_qs(raw: str | None) -> bool | None:
    if raw is None:
        return None
    norm = raw.strip().lower()
    if norm in {"1", "true", "yes"}:
        return True
    if norm in {"0", "false", "no"}:
        return False
    raise ConfigurationError(f"Invalid boolean query parameter: {raw!r}")


def _parse_float_qs(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"Invalid float query parameter: {raw!r}") from exc


def _parse_int_qs(raw: str | None, *, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"Invalid integer query parameter: {raw!r}") from exc


def _parse_dt_qs(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError(f"Invalid ISO-8601 timestamp query parameter: {raw!r}") from exc


class ServiceApplication:
    """Library-pure HTTP request dispatcher wrapping EvalForge Maestro SDK and storage."""

    def __init__(
        self,
        config: ServiceConfig | None = None,
        *,
        auth_token: str | None = None,
        judge_api_key: str | None = None,
        embedding_api_key: str | None = None,
    ) -> None:
        base_cfg = config or ServiceConfig()
        cleaned_token = auth_token.strip() if auth_token and auth_token.strip() else None
        self._config = base_cfg.model_copy(
            update={"auth_token_configured": cleaned_token is not None}
        )
        self._auth_token = cleaned_token
        self._judge_api_key = judge_api_key
        self._embedding_api_key = embedding_api_key
        self._store = LocalRunStore(self._config.storage_dir)
        self._index = SQLiteRunIndex(self._store)

    @property
    def config(self) -> ServiceConfig:
        """Return redacted service configuration."""
        return self._config

    def _is_authorized(self, headers: Mapping[str, str] | None) -> bool:
        if self._auth_token is None:
            return True
        if not headers:
            return False
        auth_val: str | None = None
        for k, v in headers.items():
            if k.lower() == "authorization":
                auth_val = v
                break
        if auth_val is None or not auth_val.startswith("Bearer "):
            return False
        presented = auth_val[len("Bearer ") :].strip()
        return hmac.compare_digest(presented.encode("utf-8"), self._auth_token.encode("utf-8"))

    def _parse_json_body(self, body: bytes) -> dict[str, Any]:
        if not body:
            return {}
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Malformed JSON request body: {exc}") from exc
        if not isinstance(decoded, dict):
            raise ConfigurationError("JSON request body must decode to an object")
        return decoded

    def _resolve_baseline_cohort(
        self,
        *,
        baseline_ref: str | None,
        baseline_run_ids: list[str] | None,
    ) -> tuple[list[RunRecord], str | None]:
        runs: list[RunRecord] = []
        alias: str | None = None
        if baseline_ref:
            known_baselines = {b.name for b in self._store.list_baselines()}
            if baseline_ref in known_baselines:
                alias = baseline_ref
                runs.append(self._store.load_baseline_run(baseline_ref))
            else:
                runs.append(self._store.load_run(baseline_ref))
        for rid in baseline_run_ids or ():
            runs.append(self._store.load_run(rid))
        return runs, alias

    def _handle_evaluate(self, body_dict: dict[str, Any]) -> ServiceEvaluateResponse:
        req = ServiceEvaluateRequest.model_validate(body_dict)
        metrics_specs = req.metrics or [MetricSpecConfig(metric_id="exact_match")]

        local_only = self._config.local_only or (req.judge.local_only if req.judge else False)
        req_mock = req.judge.mock_mode if req.judge is not None else self._config.mock_mode
        judge_cfg = (
            req.judge.model_copy(update={"local_only": local_only})
            if req.judge is not None
            else JudgeConfig(local_only=local_only, mock_mode=req_mock)
        )
        emb_local = self._config.local_only or (
            req.embedding.local_only if req.embedding is not None else False
        )
        emb_mock = req.embedding.mock_mode if req.embedding is not None else self._config.mock_mode
        emb_cfg = (
            req.embedding.model_copy(update={"local_only": emb_local})
            if req.embedding is not None
            else EmbeddingConfig(local_only=emb_local, mock_mode=emb_mock)
        )

        metrics = build_metrics_from_specs(
            metrics_specs,
            judge_settings=judge_cfg,
            embedding_settings=emb_cfg,
            local_only=local_only,
            block_pii=self._config.block_pii,
            default_max_context_chars=req.max_context_chars,
            raw_api_key=self._judge_api_key,
            raw_embedding_api_key=self._embedding_api_key,
        )
        any_remote_j, any_remote_e = check_metrics_locality_and_remote_flags(metrics)

        dataset = DatasetEngine(
            req.cases,
            dataset_id=req.dataset_id,
            dataset_version=req.dataset_version,
        )
        if self._config.block_pii and (
            (any_remote_j and not judge_cfg.mock_mode) or (any_remote_e and not emb_cfg.mock_mode)
        ):
            validate_dataset_pii_egress(dataset)

        if req.executions is not None:
            executions = req.executions
        else:
            executions = ingest_otel_spans(
                req.otel_payload,
                extractors=req.otel_extractors,
                dataset=dataset,
                case_id_map=req.case_id_map,
                system_version=req.system_version,
                model_id=req.model_id,
            )

        adapter = ReplayAdapter(
            executions,
            system_version=req.system_version,
            model_id=req.model_id,
        )
        orch_cfg = OrchestratorConfig(
            max_concurrency=req.max_concurrency,
            max_context_chars=req.max_context_chars,
            seed=req.seed,
        )

        resolved_run_id = req.run_id or f"svc-{uuid4().hex[:12]}"
        if req.persist:
            _validate_safe_identifier(resolved_run_id, label="run_id")
            if self._store.run_path(resolved_run_id).exists():
                raise ImmutabilityError(
                    f"RunRecord {resolved_run_id!r} already exists in store; "
                    "historical runs are immutable."
                )
            orchestrator = EvaluationOrchestrator(
                config=orch_cfg,
                storage_root=self._config.storage_dir,
            )
            run_record = orchestrator.run(dataset, adapter, metrics, run_id=resolved_run_id)
            if self._index.db_path.exists():
                self._index.sync()
        else:
            with tempfile.TemporaryDirectory() as tmp_store:
                orchestrator = EvaluationOrchestrator(config=orch_cfg, storage_root=tmp_store)
                run_record = orchestrator.run(dataset, adapter, metrics, run_id=resolved_run_id)

        gate_res = QualityGate(req.gate).evaluate(run_record)
        report_doc = build_run_report(run_record, gate=gate_res)
        md_text = render_markdown(report_doc) if req.include_markdown else None
        return ServiceEvaluateResponse(
            persisted=req.persist,
            evaluation=run_record,
            gate=gate_res,
            report=report_doc,
            markdown=md_text,
        )

    def _handle_compare(self, body_dict: dict[str, Any]) -> ServiceCompareResponse:
        req = ServiceCompareRequest.model_validate(body_dict)
        base_runs, base_alias = self._resolve_baseline_cohort(
            baseline_ref=req.baseline_ref,
            baseline_run_ids=req.baseline_run_ids,
        )
        cand_ids = (
            list(req.candidate_run_ids) if req.candidate_run_ids else [req.candidate_run_id or ""]
        )
        cand_runs = [self._store.load_run(cid) for cid in cand_ids]

        if len(base_runs) == 1 and len(cand_runs) == 1:
            comparison = compare_runs(
                base_runs[0],
                cand_runs[0],
                baseline_name=base_alias,
                policy=req.policy,
            )
            gate_res = QualityGate(req.policy).evaluate(cand_runs[0], comparison=comparison)
        else:
            comparison = compare_run_cohorts(
                base_runs,
                cand_runs,
                baseline_name=base_alias,
                policy=req.policy,
            )
            gate_res = QualityGate(req.policy).evaluate_cohort(cand_runs, comparison=comparison)

        report_doc = build_comparison_report(comparison, candidate_run=cand_runs[0], gate=gate_res)
        md_text = render_markdown(report_doc) if req.include_markdown else None
        return ServiceCompareResponse(
            comparison=comparison,
            gate=gate_res,
            report=report_doc,
            markdown=md_text,
        )

    def _handle_reports(self, body_dict: dict[str, Any]) -> ServiceReportResponse:
        req = ServiceReportRequest.model_validate(body_dict)
        if req.run_id is not None:
            run_rec = self._store.load_run(req.run_id)
            cmp_rep = None
            if req.baseline_ref is not None:
                base_runs, alias = self._resolve_baseline_cohort(
                    baseline_ref=req.baseline_ref,
                    baseline_run_ids=None,
                )
                cmp_rep = compare_runs(base_runs[0], run_rec, baseline_name=alias)
            doc = build_run_report(run_rec, comparison=cmp_rep, title=req.title)
        elif req.compare_run_id is not None:
            cand_rec = self._store.load_run(req.compare_run_id)
            base_runs, alias = self._resolve_baseline_cohort(
                baseline_ref=req.baseline_ref or "default",
                baseline_run_ids=None,
            )
            cmp_rep = compare_runs(base_runs[0], cand_rec, baseline_name=alias)
            doc = build_comparison_report(cmp_rep, candidate_run=cand_rec, title=req.title)
        else:
            trend_rep = analyze_trend(
                self._store.read_manifest(),
                window=req.trend_window or 2,
                dataset_id=req.dataset_id,
                model_id=req.model_id,
            )
            doc = build_trend_report(trend_rep, title=req.title)

        md_text = render_markdown(doc) if req.include_markdown else None
        return ServiceReportResponse(report=doc, markdown=md_text)

    def _route_get(
        self,
        segments: list[str],
        qs: dict[str, list[str]],
    ) -> tuple[int, dict[str, str], bytes]:
        def _q1(name: str) -> str | None:
            vals = qs.get(name)
            return vals[0] if vals else None

        if segments == ["health"]:
            idx_stat = self._index.status()
            return _json_response(
                200,
                ServiceHealthResponse(
                    package_version=_package_version(),
                    storage_dir=self._config.storage_dir,
                    local_only=self._config.local_only,
                    mock_mode=self._config.mock_mode,
                    indexed_run_count=idx_stat.indexed_run_count,
                    canonical_run_count=idx_stat.canonical_run_count,
                ),
            )
        if segments == ["v1", "index", "status"]:
            return _json_response(200, self._index.status())
        if segments == ["v1", "baselines"]:
            return _json_response(200, self._store.load_baselines())
        if segments == ["v1", "runs"]:
            auto_sync_val = _parse_bool_qs(_q1("auto_sync"))
            rf = RunQueryFilter(
                dataset_id=_q1("dataset_id"),
                dataset_version=_q1("dataset_version"),
                run_ids=qs.get("run_id") or None,
                model_id=_q1("model_id"),
                system_version=_q1("system_version"),
                baseline_name=_q1("baseline"),
                metric_id=_q1("metric_id"),
                min_mean_score=_parse_float_qs(_q1("min_score")),
                max_mean_score=_parse_float_qs(_q1("max_score")),
                has_mandatory_failures=_parse_bool_qs(_q1("has_mandatory_failures")),
                since=_parse_dt_qs(_q1("since")),
                until=_parse_dt_qs(_q1("until")),
                order_by=RunSortOrder(_q1("order_by") or RunSortOrder.TIMESTAMP_DESC.value),
                limit=_parse_int_qs(_q1("limit"), default=50),
                offset=_parse_int_qs(_q1("offset"), default=0),
            )
            runs = self._index.query_runs(
                rf, auto_sync=True if auto_sync_val is None else auto_sync_val
            )
            return _json_response(
                200,
                RunQueryPayload(
                    storage_dir=self._config.storage_dir,
                    total_returned=len(runs),
                    runs=runs,
                ),
            )
        if len(segments) == 3 and segments[:2] == ["v1", "runs"]:
            run_id = _validate_safe_identifier(segments[2], label="run_id")
            return _json_response(200, self._store.load_run(run_id))
        if segments == ["v1", "cases"]:
            raw_status = _q1("status")
            cf = CaseQueryFilter(
                run_id=_q1("run_id"),
                dataset_id=_q1("dataset_id"),
                case_id=_q1("case_id"),
                metric_id=_q1("metric_id"),
                status=MetricStatus(raw_status) if raw_status is not None else None,
                mandatory_only=bool(_parse_bool_qs(_q1("mandatory_only")) or False),
                min_score=_parse_float_qs(_q1("min_score")),
                max_score=_parse_float_qs(_q1("max_score")),
                has_errors=_parse_bool_qs(_q1("has_errors")),
                has_anomaly_flags=_parse_bool_qs(_q1("has_anomaly_flags")),
                limit=_parse_int_qs(_q1("limit"), default=100),
                offset=_parse_int_qs(_q1("offset"), default=0),
            )
            auto_sync_val = _parse_bool_qs(_q1("auto_sync"))
            cases = self._index.query_cases(
                cf, auto_sync=True if auto_sync_val is None else auto_sync_val
            )
            return _json_response(
                200,
                CaseQueryPayload(
                    storage_dir=self._config.storage_dir,
                    total_returned=len(cases),
                    cases=cases,
                ),
            )
        if len(segments) == 4 and segments[:2] == ["v1", "metrics"] and segments[3] == "history":
            points = self._index.metric_history(
                segments[2],
                dataset_id=_q1("dataset_id"),
                model_id=_q1("model_id"),
                system_version=_q1("system_version"),
                limit=_parse_int_qs(_q1("limit"), default=50),
            )
            return _json_response(200, points)

        if segments in (
            ["v1", "index", "rebuild"],
            ["v1", "index", "sync"],
            ["v1", "otel", "ingest"],
            ["v1", "evaluate"],
            ["v1", "compare"],
            ["v1", "reports"],
        ):
            return _error_response(405, "MethodNotAllowed", "GET is not supported on this endpoint")
        return _error_response(404, "NotFoundError", f"Unknown endpoint: /{'/'.join(segments)}")

    def _route_post(
        self,
        segments: list[str],
        body: bytes,
    ) -> tuple[int, dict[str, str], bytes]:
        if segments in (
            ["health"],
            ["v1", "index", "status"],
            ["v1", "runs"],
            ["v1", "cases"],
            ["v1", "baselines"],
        ) or (len(segments) == 3 and segments[:2] == ["v1", "runs"]):
            return _error_response(
                405, "MethodNotAllowed", "POST is not supported on this endpoint"
            )

        body_dict = self._parse_json_body(body)
        if segments == ["v1", "index", "rebuild"]:
            return _json_response(200, self._index.rebuild())
        if segments == ["v1", "index", "sync"]:
            return _json_response(200, self._index.sync())
        if segments == ["v1", "otel", "ingest"]:
            req = ServiceOtelIngestRequest.model_validate(body_dict)
            executions = ingest_otel_spans(
                req.payload,
                extractors=req.extractors,
                dataset=req.dataset,
                case_id_map=req.case_id_map,
                system_version=req.system_version,
                model_id=req.model_id,
            )
            return _json_response(
                200,
                ServiceOtelIngestResponse(count=len(executions), executions=executions),
            )
        if segments == ["v1", "evaluate"]:
            return _json_response(200, self._handle_evaluate(body_dict))
        if segments == ["v1", "compare"]:
            return _json_response(200, self._handle_compare(body_dict))
        if segments == ["v1", "reports"]:
            return _json_response(200, self._handle_reports(body_dict))

        return _error_response(404, "NotFoundError", f"Unknown endpoint: /{'/'.join(segments)}")

    def handle_request(
        self,
        method: str,
        raw_path: str,
        *,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Dispatch one HTTP request synchronously into strict typed EvalForge SDK calls."""
        if not self._is_authorized(headers):
            return _error_response(
                401,
                "UnauthorizedError",
                "Missing or invalid Bearer authentication token.",
                hint="Pass Authorization: Bearer <token> matching server credentials.",
            )
        if len(body) > self._config.max_request_bytes:
            return _error_response(
                413,
                "PayloadTooLargeError",
                f"Request body exceeds max_request_bytes={self._config.max_request_bytes}",
            )

        try:
            parsed_url = urlsplit(raw_path)
            raw_segments = [unquote(s) for s in parsed_url.path.strip("/").split("/") if s != ""]
            qs = parse_qs(parsed_url.query, keep_blank_values=False)
            norm_method = method.strip().upper()

            if norm_method == "GET":
                return self._route_get(raw_segments, qs)
            if norm_method == "POST":
                return self._route_post(raw_segments, body)
            return _error_response(
                405, "MethodNotAllowed", f"HTTP method {norm_method!r} is not supported"
            )
        except LocalOnlyPolicyError as exc:
            return _error_response(403, type(exc).__name__, str(exc))
        except ImmutabilityError as exc:
            return _error_response(409, type(exc).__name__, str(exc))
        except MissingExtraError as exc:
            return _error_response(503, type(exc).__name__, str(exc))
        except StorageError as exc:
            msg_low = str(exc).lower()
            status_code = 404 if "not found" in msg_low else 400
            return _error_response(status_code, type(exc).__name__, str(exc))
        except (
            ValidationError,
            ValueError,
            ConfigurationError,
            DatasetError,
            AdapterError,
            MetricError,
        ) as exc:
            return _error_response(400, type(exc).__name__, str(exc))
        except (ExecutionError, JudgeError, EvalforgeError) as exc:
            return _error_response(500, type(exc).__name__, str(exc))
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            _LOGGER.warning("Unhandled service error: %s", scrub_secret_text(str(exc)))
            return _error_response(500, "InternalServerError", "Unexpected service error.")


__all__ = ["ServiceApplication", "validate_service_bind_policy"]
