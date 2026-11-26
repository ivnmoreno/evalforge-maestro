"""CLI-boundary configuration discovery, 5-tier precedence resolution, and secret masking."""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from evalforge_maestro._canonical import (
    REDACTED_VALUE,
    is_sensitive_key,
    redact_secrets,
    scrub_secret_text,
)
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.types import (
    CLIResolvedConfig,
    ConfigSettingProvenance,
    ConfigSourceTier,
    EmbeddingAggregation,
    MetricSpecConfig,
    OrchestratorConfig,
    OtelExtractorConfig,
    OtelTimestampUnit,
    QualityGatePolicy,
    ResolvedEmbeddingSettings,
    ResolvedJudgeSettings,
    ResolvedLoggingConfig,
    ResolvedSecurityConfig,
    ResolvedTargetConfig,
    TargetType,
)

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})


class _TomlStrictSection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _TomlRunSection(_TomlStrictSection):
    storage_dir: str | None = None
    dataset: str | None = None
    dataset_id: str | None = None
    dataset_version: str | None = None
    executions: str | None = None
    otel_traces: str | None = None
    run_id: str | None = None
    repeats: int | None = None
    baseline: str | None = None
    baseline_runs: list[str] | None = None
    trend_window: int | None = None
    strict: bool | None = None
    max_concurrency: int | None = None
    max_dataset_cases: int | None = None
    max_context_chars: int | None = None
    case_timeout_seconds: float | None = None
    max_memory_mb: float | None = None
    memory_limit_action: str | None = None
    fail_fast: bool | None = None
    retain_checkpoints: bool | None = None
    seed: int | None = None


class _TomlTargetSection(_TomlStrictSection):
    type: str | None = None
    entrypoint: str | None = None
    system_version: str | None = None
    model_id: str | None = None
    arg_mode: str | None = None
    rag_extractors: dict[str, str] | None = None
    agent_extractors: dict[str, str] | None = None
    docpipe_mode: str | None = None
    docpipe_collection: str | None = None
    docpipe_persist_dir: str | None = None
    docpipe_top_k: int | None = None
    docpipe_embed_model: str | None = None
    docpipe_answer_model: str | None = None
    docpipe_api_base: str | None = None
    docpipe_searcher: str | None = None
    docpipe_rerank: bool | None = None


class _TomlJudgeSection(_TomlStrictSection):
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    pass_threshold: float | None = None
    max_retries: int | None = None
    retry_backoff_seconds: float | None = None
    timeout_seconds: float | None = None
    prompt_version: str | None = None
    mock_mode: bool | None = None
    local_only: bool | None = None
    seed: int | None = None
    min_agreement: float | None = None


class _TomlEmbeddingSection(_TomlStrictSection):
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    pass_threshold: float | None = None
    aggregation: str | None = None
    max_retries: int | None = None
    retry_backoff_seconds: float | None = None
    timeout_seconds: float | None = None
    max_input_chars: int | None = None
    mock_mode: bool | None = None
    local_only: bool | None = None


class _TomlSecuritySection(_TomlStrictSection):
    local_only: bool | None = None
    block_pii: bool | None = None


class _TomlGateSection(_TomlStrictSection):
    min_score: float | None = None
    min_metric_scores: dict[str, float] | None = None
    max_regression_drop: float | None = None
    max_metric_regression_drops: dict[str, float] | None = None
    max_regressed_cases: int | None = None
    disagreement_threshold: float | None = None
    case_drop_warning_threshold: float | None = None
    trend_slope_threshold: float | None = None
    max_inconclusive_rate: float | None = None
    require_baseline: bool | None = None
    require_trend: bool | None = None
    min_trend_runs: int | None = None
    soft_regression_warning: bool | None = None
    fail_on_drift: bool | None = None
    fail_on_anomaly: bool | None = None
    fail_on_degrading_trend: bool | None = None
    fail_on_mandatory_regression: bool | None = None
    confidence_level: float | None = None
    min_statistical_samples: int | None = None
    fail_on_significant_regression: bool | None = None


class _TomlLoggingSection(_TomlStrictSection):
    log_level: str | None = None
    log_json: bool | None = None


class _TomlOtelSection(_TomlStrictSection):
    case_id_attribute: str | None = None
    input_attribute: str | None = None
    output_attribute: str | None = None
    model_attribute: str | None = None
    service_version_attribute: str | None = None
    step_kind_attribute: str | None = None
    tool_name_attribute: str | None = None
    tool_arguments_attribute: str | None = None
    tool_result_attribute: str | None = None
    retrieval_documents_attribute: str | None = None
    timestamp_unit: str | None = None
    match_dataset_by_input: bool | None = None


class _TomlRootConfig(_TomlStrictSection):
    run: _TomlRunSection | None = None
    target: _TomlTargetSection | None = None
    metrics: dict[str, Any] | None = None
    judge: _TomlJudgeSection | None = None
    embedding: _TomlEmbeddingSection | None = None
    security: _TomlSecuritySection | None = None
    gate: _TomlGateSection | None = None
    logging: _TomlLoggingSection | None = None
    otel: _TomlOtelSection | None = None


def _load_toml_file(path: Path) -> tuple[dict[str, Any], _TomlRootConfig]:
    import tomllib

    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise ConfigurationError(f"Failed reading configuration file {path}: {exc}") from exc

    try:
        parsed = tomllib.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Invalid TOML syntax in {path}: {exc}") from exc

    if not isinstance(parsed, dict):  # pragma: no cover - TOML root is always dict
        raise ConfigurationError(f"Configuration file {path} must decode to a TOML table")

    try:
        validated = _TomlRootConfig.model_validate(parsed)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid configuration structure in {path}: {scrub_secret_text(str(exc))}"
        ) from exc

    return parsed, validated


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse an explicit opt-in .env file using strict stdlib KEY=VALUE rules."""
    if not path.is_file():
        raise ConfigurationError(f"Environment file not found: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigurationError(f"Failed reading environment file {path}: {exc}") from exc

    parsed: dict[str, str] = {}
    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" not in stripped:
            raise ConfigurationError(
                f"Malformed line {line_no} in environment file {path}: expected KEY=VALUE"
            )
        key_part, val_part = stripped.split("=", 1)
        key = key_part.strip()
        if not _ENV_KEY_RE.match(key):
            raise ConfigurationError(
                f"Invalid environment variable name {key!r} at {path}:{line_no}"
            )
        val_raw = val_part.strip()
        if not val_raw:
            parsed[key] = ""
            continue
        if val_raw[0] in {"'", '"'}:
            try:
                tokens = shlex.split(val_raw, posix=True)
            except ValueError as exc:
                raise ConfigurationError(
                    f"Malformed quoted value at {path}:{line_no}: {exc}"
                ) from exc
            if len(tokens) != 1:
                raise ConfigurationError(
                    f"Unexpected trailing tokens after quoted value at {path}:{line_no}"
                )
            parsed[key] = tokens[0]
        else:
            if " #" in val_raw:
                val_raw = val_raw.split(" #", 1)[0].rstrip()
            parsed[key] = val_raw
    return parsed


def _parse_bool_env(raw: str, *, var_name: str) -> bool:
    cleaned = raw.strip().lower()
    if cleaned in _BOOL_TRUE:
        return True
    if cleaned in _BOOL_FALSE:
        return False
    raise ConfigurationError(f"Invalid boolean for {var_name}: {raw!r}")


def _parse_int_env(raw: str, *, var_name: str) -> int:
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Invalid integer for {var_name}: {raw!r}") from exc


def _parse_float_env(raw: str, *, var_name: str) -> float:
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Invalid number for {var_name}: {raw!r}") from exc


def _parse_scalar_token(raw: str) -> Any:
    cleaned = raw.strip()
    lower = cleaned.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    if (cleaned.startswith("{") and cleaned.endswith("}")) or (
        cleaned.startswith("[") and cleaned.endswith("]")
    ):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
    try:
        if "." in cleaned or "e" in lower:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return cleaned


def parse_metric_spec_text(raw: str) -> MetricSpecConfig:
    """Parse one metric spec string (`metric_id`, `metric_id:k=5`, or `metric_id:{json}`)."""
    cleaned = raw.strip()
    if not cleaned:
        raise ConfigurationError("Metric specification must not be empty")
    if ":" not in cleaned:
        return MetricSpecConfig(metric_id=cleaned)

    metric_id, raw_params = cleaned.split(":", 1)
    metric_id = metric_id.strip()
    params_str = raw_params.strip()
    if not metric_id:
        raise ConfigurationError(f"Invalid metric specification {raw!r}: missing metric_id")
    if not params_str:
        return MetricSpecConfig(metric_id=metric_id)
    if params_str.startswith("{"):
        try:
            decoded = json.loads(params_str)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Invalid JSON parameters for metric {metric_id!r}: {exc.msg}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ConfigurationError(
                f"Metric {metric_id!r} parameters JSON must decode to an object"
            )
        return MetricSpecConfig(metric_id=metric_id, params=decoded)

    params: dict[str, Any] = {}
    for pair in params_str.split(","):
        item = pair.strip()
        if not item:
            continue
        if "=" not in item:
            raise ConfigurationError(
                f"Invalid metric parameter {item!r} in {raw!r}: expected key=value"
            )
        p_key, p_val = item.split("=", 1)
        clean_key = p_key.strip()
        if not clean_key:
            raise ConfigurationError(f"Empty metric parameter key in {raw!r}")
        params[clean_key] = _parse_scalar_token(p_val)
    return MetricSpecConfig(metric_id=metric_id, params=params)


def _parse_metrics_env(raw: str) -> list[MetricSpecConfig]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    if cleaned.startswith("["):
        try:
            loaded = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Invalid JSON in EVALFORGE_METRICS: {exc.msg}") from exc
        if not isinstance(loaded, list):
            raise ConfigurationError("EVALFORGE_METRICS JSON value must be a list")
        specs: list[MetricSpecConfig] = []
        for item in loaded:
            if isinstance(item, str):
                specs.append(parse_metric_spec_text(item))
            elif isinstance(item, Mapping):
                specs.append(MetricSpecConfig.model_validate(dict(item)))
            else:
                raise ConfigurationError("EVALFORGE_METRICS list items must be strings or objects")
        return specs
    return [parse_metric_spec_text(part) for part in cleaned.split(",") if part.strip()]


def _parse_toml_metrics(metrics_tbl: Mapping[str, Any] | None) -> list[MetricSpecConfig]:
    if not metrics_tbl:
        return []
    raw_enabled = metrics_tbl.get("enabled")
    per_metric_params: dict[str, dict[str, Any]] = {}
    for key, val in metrics_tbl.items():
        if key == "enabled":
            continue
        if not isinstance(val, Mapping):
            raise ConfigurationError(
                f"Invalid [metrics.{key}] configuration in TOML: expected table or 'enabled' list"
            )
        per_metric_params[key] = dict(val)

    specs: list[MetricSpecConfig] = []
    if raw_enabled is not None:
        if not isinstance(raw_enabled, list) or not all(isinstance(x, str) for x in raw_enabled):
            raise ConfigurationError("[metrics].enabled in TOML must be a list of metric strings")
        seen: set[str] = set()
        for m_name in raw_enabled:
            clean_name = m_name.strip()
            params = per_metric_params.get(clean_name, {})
            specs.append(MetricSpecConfig(metric_id=clean_name, params=params))
            seen.add(clean_name)
        for m_name, params in per_metric_params.items():
            if m_name not in seen:
                specs.append(MetricSpecConfig(metric_id=m_name, params=params))
    else:
        for m_name, params in per_metric_params.items():
            specs.append(MetricSpecConfig(metric_id=m_name, params=params))
    return specs


class _TierLookup:
    def __init__(
        self,
        *,
        cli_overrides: Mapping[str, Any],
        os_env: Mapping[str, str],
        env_file_vars: Mapping[str, str],
    ) -> None:
        self.cli_overrides = cli_overrides
        self.os_env = os_env
        self.env_file_vars = env_file_vars
        self.provenance: list[ConfigSettingProvenance] = []

    def resolve(
        self,
        key: str,
        *,
        cli_key: str | None = None,
        env_var: str | None = None,
        env_parser: str = "str",
        toml_val: Any = None,
        default: Any = None,
    ) -> Any:
        cli_name = cli_key if cli_key is not None else key.split(".")[-1]
        cli_val = self.cli_overrides.get(cli_name)
        if cli_val is not None:
            source = ConfigSourceTier.CLI
            chosen = cli_val
        elif env_var is not None and env_var in self.os_env and self.os_env[env_var] != "":
            source = ConfigSourceTier.ENV
            chosen = self._decode_env(self.os_env[env_var], env_parser, env_var)
        elif (
            env_var is not None
            and env_var in self.env_file_vars
            and self.env_file_vars[env_var] != ""
        ):
            source = ConfigSourceTier.ENV_FILE
            chosen = self._decode_env(self.env_file_vars[env_var], env_parser, env_var)
        elif toml_val is not None:
            source = ConfigSourceTier.FILE
            chosen = toml_val
        else:
            source = ConfigSourceTier.DEFAULT
            chosen = default

        leaf = key.rsplit(".", 1)[-1]
        masked = is_sensitive_key(leaf) and chosen is not None and str(chosen).strip() != ""
        self.provenance.append(
            ConfigSettingProvenance(
                key=key,
                value=REDACTED_VALUE if masked else redact_secrets(chosen),
                source=source,
                masked=masked,
            )
        )
        return chosen

    @staticmethod
    def _decode_env(raw: str, kind: str, var_name: str) -> Any:
        if kind == "bool":
            return _parse_bool_env(raw, var_name=var_name)
        if kind == "int":
            return _parse_int_env(raw, var_name=var_name)
        if kind == "float":
            return _parse_float_env(raw, var_name=var_name)
        if kind == "str_list":
            return [token.strip() for token in raw.split(",") if token.strip()]
        if kind == "json_float_map":
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"Invalid JSON in {var_name}: {exc.msg}") from exc
            if not isinstance(loaded, dict):
                raise ConfigurationError(f"{var_name} must decode to a JSON object")
            return loaded
        return raw.strip()


def _resolve_optional_files(
    *,
    cli_map: Mapping[str, Any],
    os_env: Mapping[str, str],
    config_path: str | Path | None,
    env_file: str | Path | None,
    active_cwd: Path,
) -> tuple[dict[str, str], str | None, _TomlRootConfig, str | None]:
    raw_env_arg = cli_map.get("env_file")
    if raw_env_arg is not None:
        env_path: Path | None = Path(str(raw_env_arg))
    elif env_file is not None:
        env_path = Path(env_file)
    elif os_env.get("EVALFORGE_ENV_FILE", "").strip():
        env_path = Path(os_env["EVALFORGE_ENV_FILE"].strip())
    else:
        env_path = None

    env_file_vars: dict[str, str] = {}
    env_str: str | None = None
    if env_path is not None:
        env_file_vars = parse_env_file(env_path)
        env_str = str(env_path)

    explicit_cfg = (
        cli_map.get("config") or config_path or os_env.get("EVALFORGE_CONFIG", "").strip()
    )
    if not explicit_cfg and "EVALFORGE_CONFIG" in env_file_vars:
        explicit_cfg = env_file_vars["EVALFORGE_CONFIG"].strip() or None

    cfg_path: Path | None = None
    if explicit_cfg:
        candidate = Path(str(explicit_cfg))
        if not candidate.is_file():
            raise ConfigurationError(f"Configuration file not found: {candidate}")
        cfg_path = candidate
    else:
        default_cwd_cfg = active_cwd / "evalforge.toml"
        if default_cwd_cfg.is_file():
            cfg_path = default_cwd_cfg

    toml_model = _TomlRootConfig()
    cfg_str: str | None = None
    if cfg_path is not None:
        _, toml_model = _load_toml_file(cfg_path)
        cfg_str = str(cfg_path)
    return env_file_vars, env_str, toml_model, cfg_str


def _resolve_metrics_specs(
    lookup: _TierLookup,
    *,
    cli_map: Mapping[str, Any],
    os_env: Mapping[str, str],
    env_file_vars: Mapping[str, str],
    toml_metrics_tbl: Mapping[str, Any] | None,
) -> list[MetricSpecConfig]:
    cli_metrics_raw = cli_map.get("metric")
    toml_metrics = _parse_toml_metrics(toml_metrics_tbl)
    if cli_metrics_raw:
        specs = [parse_metric_spec_text(str(item)) for item in cli_metrics_raw]
        source = ConfigSourceTier.CLI
    elif os_env.get("EVALFORGE_METRICS", "").strip():
        specs = _parse_metrics_env(os_env["EVALFORGE_METRICS"])
        source = ConfigSourceTier.ENV
    elif env_file_vars.get("EVALFORGE_METRICS", "").strip():
        specs = _parse_metrics_env(env_file_vars["EVALFORGE_METRICS"])
        source = ConfigSourceTier.ENV_FILE
    elif toml_metrics:
        specs = toml_metrics
        source = ConfigSourceTier.FILE
    else:
        specs = []
        source = ConfigSourceTier.DEFAULT
    lookup.provenance.append(
        ConfigSettingProvenance(
            key="metrics",
            value=[m.model_dump(mode="json") for m in specs],
            source=source,
            masked=False,
        )
    )
    return specs


def _resolve_target_section(
    lookup: _TierLookup,
    target_sec: _TomlTargetSection,
    *,
    executions_path: str | None,
    otel_traces_path: str | None = None,
) -> ResolvedTargetConfig:
    target_type_raw = lookup.resolve(
        "target.type",
        cli_key="target_type",
        env_var="EVALFORGE_TARGET_TYPE",
        toml_val=target_sec.type,
    )
    target_entrypoint = lookup.resolve(
        "target.entrypoint",
        cli_key="target",
        env_var="EVALFORGE_TARGET",
        toml_val=target_sec.entrypoint,
    )
    system_version = lookup.resolve(
        "target.system_version",
        env_var="EVALFORGE_SYSTEM_VERSION",
        toml_val=target_sec.system_version,
    )
    model_id = lookup.resolve(
        "target.model_id", env_var="EVALFORGE_MODEL_ID", toml_val=target_sec.model_id
    )
    arg_mode = lookup.resolve(
        "target.arg_mode",
        cli_key="target_arg_mode",
        env_var="EVALFORGE_TARGET_ARG_MODE",
        toml_val=target_sec.arg_mode,
        default="input",
    )
    docpipe_mode = lookup.resolve(
        "target.docpipe_mode",
        cli_key="docpipe_mode",
        env_var="EVALFORGE_DOCPIPE_MODE",
        toml_val=target_sec.docpipe_mode,
        default="answer_detailed",
    )
    docpipe_collection = lookup.resolve(
        "target.docpipe_collection",
        cli_key="docpipe_collection",
        env_var="EVALFORGE_DOCPIPE_COLLECTION",
        toml_val=target_sec.docpipe_collection,
    )
    docpipe_persist_dir = lookup.resolve(
        "target.docpipe_persist_dir",
        cli_key="docpipe_persist_dir",
        env_var="EVALFORGE_DOCPIPE_PERSIST_DIR",
        toml_val=target_sec.docpipe_persist_dir,
    )
    docpipe_top_k = lookup.resolve(
        "target.docpipe_top_k",
        cli_key="docpipe_top_k",
        env_var="EVALFORGE_DOCPIPE_TOP_K",
        env_parser="int",
        toml_val=target_sec.docpipe_top_k,
    )
    docpipe_embed_model = lookup.resolve(
        "target.docpipe_embed_model",
        cli_key="docpipe_embed_model",
        env_var="EVALFORGE_DOCPIPE_EMBED_MODEL",
        toml_val=target_sec.docpipe_embed_model,
    )
    docpipe_answer_model = lookup.resolve(
        "target.docpipe_answer_model",
        cli_key="docpipe_answer_model",
        env_var="EVALFORGE_DOCPIPE_ANSWER_MODEL",
        toml_val=target_sec.docpipe_answer_model,
    )
    docpipe_api_base = lookup.resolve(
        "target.docpipe_api_base",
        cli_key="docpipe_api_base",
        env_var="EVALFORGE_DOCPIPE_API_BASE",
        toml_val=target_sec.docpipe_api_base,
    )
    docpipe_searcher = lookup.resolve(
        "target.docpipe_searcher",
        cli_key="docpipe_searcher",
        env_var="EVALFORGE_DOCPIPE_SEARCHER",
        toml_val=target_sec.docpipe_searcher,
    )
    docpipe_rerank = bool(
        lookup.resolve(
            "target.docpipe_rerank",
            cli_key="docpipe_rerank",
            env_var="EVALFORGE_DOCPIPE_RERANK",
            env_parser="bool",
            toml_val=target_sec.docpipe_rerank,
            default=False,
        )
    )
    if (
        target_type_raw is None
        and (executions_path is not None or otel_traces_path is not None)
        and not target_entrypoint
    ):
        target_type_raw = TargetType.REPLAY.value

    return ResolvedTargetConfig(
        target_type=TargetType(target_type_raw) if target_type_raw is not None else None,
        entrypoint=target_entrypoint,
        system_version=system_version,
        model_id=model_id,
        arg_mode=arg_mode,
        rag_extractors=dict(target_sec.rag_extractors or {}),
        agent_extractors=dict(target_sec.agent_extractors or {}),
        docpipe_mode=docpipe_mode,
        docpipe_collection=docpipe_collection,
        docpipe_persist_dir=docpipe_persist_dir,
        docpipe_top_k=docpipe_top_k,
        docpipe_embed_model=docpipe_embed_model,
        docpipe_answer_model=docpipe_answer_model,
        docpipe_api_base=docpipe_api_base,
        docpipe_searcher=docpipe_searcher,
        docpipe_rerank=docpipe_rerank,
    )


def _resolve_execution_section(lookup: _TierLookup, run_sec: _TomlRunSection) -> OrchestratorConfig:
    return OrchestratorConfig(
        max_concurrency=lookup.resolve(
            "execution.max_concurrency",
            env_var="EVALFORGE_MAX_CONCURRENCY",
            env_parser="int",
            toml_val=run_sec.max_concurrency,
            default=4,
        ),
        max_dataset_cases=lookup.resolve(
            "execution.max_dataset_cases",
            env_var="EVALFORGE_MAX_DATASET_CASES",
            env_parser="int",
            toml_val=run_sec.max_dataset_cases,
        ),
        max_context_chars=lookup.resolve(
            "execution.max_context_chars",
            env_var="EVALFORGE_MAX_CONTEXT_CHARS",
            env_parser="int",
            toml_val=run_sec.max_context_chars,
        ),
        case_timeout_seconds=lookup.resolve(
            "execution.case_timeout_seconds",
            cli_key="case_timeout",
            env_var="EVALFORGE_CASE_TIMEOUT_SECONDS",
            env_parser="float",
            toml_val=run_sec.case_timeout_seconds,
        ),
        max_memory_mb=lookup.resolve(
            "execution.max_memory_mb",
            env_var="EVALFORGE_MAX_MEMORY_MB",
            env_parser="float",
            toml_val=run_sec.max_memory_mb,
        ),
        memory_limit_action=lookup.resolve(
            "execution.memory_limit_action",
            env_var="EVALFORGE_MEMORY_LIMIT_ACTION",
            toml_val=run_sec.memory_limit_action,
            default="warn",
        ),
        fail_fast=bool(
            lookup.resolve(
                "execution.fail_fast",
                env_var="EVALFORGE_FAIL_FAST",
                env_parser="bool",
                toml_val=run_sec.fail_fast,
                default=False,
            )
        ),
        retain_checkpoints=bool(run_sec.retain_checkpoints or False),
        seed=lookup.resolve(
            "execution.seed",
            env_var="EVALFORGE_SEED",
            env_parser="int",
            toml_val=run_sec.seed,
        ),
    )


def _resolve_judge_and_security(
    lookup: _TierLookup,
    judge_sec: _TomlJudgeSection,
    sec_sec: _TomlSecuritySection,
    *,
    exec_seed: int | None,
) -> tuple[ResolvedJudgeSettings, ResolvedSecurityConfig, str | None]:
    local_only = bool(
        lookup.resolve(
            "security.local_only",
            cli_key="local_only",
            env_var="EVALFORGE_LOCAL_ONLY",
            env_parser="bool",
            toml_val=sec_sec.local_only if sec_sec.local_only is not None else judge_sec.local_only,
            default=False,
        )
    )
    block_pii = bool(
        lookup.resolve(
            "security.block_pii",
            cli_key="block_pii",
            env_var="EVALFORGE_BLOCK_PII",
            env_parser="bool",
            toml_val=sec_sec.block_pii,
            default=False,
        )
    )
    raw_api_key = lookup.resolve(
        "judge.api_key",
        cli_key="judge_api_key",
        env_var="EVALFORGE_JUDGE_API_KEY",
        toml_val=judge_sec.api_key,
    )
    judge_settings = ResolvedJudgeSettings(
        model=str(
            lookup.resolve(
                "judge.model",
                cli_key="judge_model",
                env_var="EVALFORGE_JUDGE_MODEL",
                toml_val=judge_sec.model,
                default="mock-judge",
            )
        ),
        api_base=lookup.resolve(
            "judge.api_base",
            cli_key="judge_api_base",
            env_var="EVALFORGE_JUDGE_API_BASE",
            toml_val=judge_sec.api_base,
        ),
        api_key=REDACTED_VALUE if raw_api_key else None,
        temperature=lookup.resolve(
            "judge.temperature",
            cli_key="judge_temperature",
            env_var="EVALFORGE_JUDGE_TEMPERATURE",
            env_parser="float",
            toml_val=judge_sec.temperature,
            default=0.0,
        ),
        pass_threshold=lookup.resolve(
            "judge.pass_threshold",
            cli_key="judge_pass_threshold",
            env_var="EVALFORGE_JUDGE_PASS_THRESHOLD",
            env_parser="float",
            toml_val=judge_sec.pass_threshold,
            default=0.5,
        ),
        max_retries=lookup.resolve(
            "judge.max_retries",
            cli_key="judge_max_retries",
            env_var="EVALFORGE_JUDGE_MAX_RETRIES",
            env_parser="int",
            toml_val=judge_sec.max_retries,
            default=2,
        ),
        retry_backoff_seconds=(
            judge_sec.retry_backoff_seconds if judge_sec.retry_backoff_seconds is not None else 0.5
        ),
        timeout_seconds=lookup.resolve(
            "judge.timeout_seconds",
            cli_key="judge_timeout",
            env_var="EVALFORGE_JUDGE_TIMEOUT_SECONDS",
            env_parser="float",
            toml_val=judge_sec.timeout_seconds,
            default=30.0,
        ),
        prompt_version=judge_sec.prompt_version or "1.0",
        mock_mode=bool(
            lookup.resolve(
                "judge.mock_mode",
                cli_key="mock",
                env_var="EVALFORGE_MOCK",
                env_parser="bool",
                toml_val=judge_sec.mock_mode,
                default=False,
            )
        ),
        local_only=local_only,
        seed=judge_sec.seed if judge_sec.seed is not None else exec_seed,
        min_agreement=lookup.resolve(
            "judge.min_agreement",
            cli_key="min_agreement",
            env_var="EVALFORGE_CALIBRATE_MIN_AGREEMENT",
            env_parser="float",
            toml_val=judge_sec.min_agreement,
        ),
    )
    security_cfg = ResolvedSecurityConfig(local_only=local_only, block_pii=block_pii)
    raw_key_str = str(raw_api_key) if raw_api_key else None
    return judge_settings, security_cfg, raw_key_str


def _resolve_embedding_section(
    lookup: _TierLookup,
    emb_sec: _TomlEmbeddingSection,
    *,
    security_local_only: bool,
) -> tuple[ResolvedEmbeddingSettings, str | None]:
    raw_emb_key = lookup.resolve(
        "embedding.api_key",
        cli_key="embedding_api_key",
        env_var="EVALFORGE_EMBEDDING_API_KEY",
        toml_val=emb_sec.api_key,
    )
    raw_emb_key_str = str(raw_emb_key).strip() if raw_emb_key else None
    if raw_emb_key_str == "":
        raw_emb_key_str = None

    raw_agg = lookup.resolve(
        "embedding.aggregation",
        cli_key="embedding_aggregation",
        env_var="EVALFORGE_EMBEDDING_AGGREGATION",
        toml_val=emb_sec.aggregation,
        default=EmbeddingAggregation.MAX.value,
    )
    aggregation = (
        raw_agg
        if isinstance(raw_agg, EmbeddingAggregation)
        else EmbeddingAggregation(str(raw_agg).strip().lower())
    )
    emb_local_only = bool(
        lookup.resolve(
            "embedding.local_only",
            cli_key="embedding_local_only",
            env_var="EVALFORGE_EMBEDDING_LOCAL_ONLY",
            env_parser="bool",
            toml_val=emb_sec.local_only,
            default=False,
        )
    )
    settings = ResolvedEmbeddingSettings(
        model=str(
            lookup.resolve(
                "embedding.model",
                cli_key="embedding_model",
                env_var="EVALFORGE_EMBEDDING_MODEL",
                toml_val=emb_sec.model,
                default="mock-embedding",
            )
        ),
        api_base=lookup.resolve(
            "embedding.api_base",
            cli_key="embedding_api_base",
            env_var="EVALFORGE_EMBEDDING_API_BASE",
            toml_val=emb_sec.api_base,
        ),
        api_key_configured=raw_emb_key_str is not None,
        pass_threshold=lookup.resolve(
            "embedding.pass_threshold",
            cli_key="embedding_pass_threshold",
            env_var="EVALFORGE_EMBEDDING_PASS_THRESHOLD",
            env_parser="float",
            toml_val=emb_sec.pass_threshold,
            default=0.5,
        ),
        aggregation=aggregation,
        max_retries=lookup.resolve(
            "embedding.max_retries",
            cli_key="embedding_max_retries",
            env_var="EVALFORGE_EMBEDDING_MAX_RETRIES",
            env_parser="int",
            toml_val=emb_sec.max_retries,
            default=2,
        ),
        retry_backoff_seconds=(
            emb_sec.retry_backoff_seconds if emb_sec.retry_backoff_seconds is not None else 0.5
        ),
        timeout_seconds=lookup.resolve(
            "embedding.timeout_seconds",
            cli_key="embedding_timeout",
            env_var="EVALFORGE_EMBEDDING_TIMEOUT_SECONDS",
            env_parser="float",
            toml_val=emb_sec.timeout_seconds,
            default=30.0,
        ),
        max_input_chars=lookup.resolve(
            "embedding.max_input_chars",
            cli_key="embedding_max_input_chars",
            env_var="EVALFORGE_EMBEDDING_MAX_INPUT_CHARS",
            env_parser="int",
            toml_val=emb_sec.max_input_chars,
        ),
        mock_mode=bool(
            lookup.resolve(
                "embedding.mock_mode",
                cli_key="mock",
                env_var="EVALFORGE_MOCK",
                env_parser="bool",
                toml_val=emb_sec.mock_mode,
                default=False,
            )
        ),
        local_only=security_local_only or emb_local_only,
    )
    return settings, raw_emb_key_str


def _resolve_gate_section(lookup: _TierLookup, gate_sec: _TomlGateSection) -> QualityGatePolicy:
    return QualityGatePolicy(
        min_score=lookup.resolve(
            "gate.min_score",
            cli_key="min_score",
            env_var="EVALFORGE_GATE_MIN_SCORE",
            env_parser="float",
            toml_val=gate_sec.min_score,
        ),
        min_metric_scores=dict(gate_sec.min_metric_scores or {}),
        max_regression_drop=lookup.resolve(
            "gate.max_regression_drop",
            cli_key="max_regression_drop",
            env_var="EVALFORGE_GATE_MAX_REGRESSION_DROP",
            env_parser="float",
            toml_val=gate_sec.max_regression_drop,
            default=0.05,
        ),
        max_metric_regression_drops=dict(gate_sec.max_metric_regression_drops or {}),
        max_regressed_cases=lookup.resolve(
            "gate.max_regressed_cases",
            cli_key="max_regressed_cases",
            env_var="EVALFORGE_GATE_MAX_REGRESSED_CASES",
            env_parser="int",
            toml_val=gate_sec.max_regressed_cases,
        ),
        disagreement_threshold=(
            gate_sec.disagreement_threshold if gate_sec.disagreement_threshold is not None else 0.3
        ),
        case_drop_warning_threshold=(
            gate_sec.case_drop_warning_threshold
            if gate_sec.case_drop_warning_threshold is not None
            else 0.25
        ),
        trend_slope_threshold=(
            gate_sec.trend_slope_threshold if gate_sec.trend_slope_threshold is not None else 0.01
        ),
        max_inconclusive_rate=lookup.resolve(
            "gate.max_inconclusive_rate",
            cli_key="max_inconclusive_rate",
            env_var="EVALFORGE_GATE_MAX_INCONCLUSIVE_RATE",
            env_parser="float",
            toml_val=gate_sec.max_inconclusive_rate,
            default=0.10,
        ),
        require_baseline=bool(gate_sec.require_baseline or False),
        require_trend=bool(gate_sec.require_trend or False),
        min_trend_runs=gate_sec.min_trend_runs if gate_sec.min_trend_runs is not None else 2,
        soft_regression_warning=bool(gate_sec.soft_regression_warning or False),
        fail_on_drift=bool(
            lookup.resolve(
                "gate.fail_on_drift",
                cli_key="fail_on_drift",
                env_var="EVALFORGE_GATE_FAIL_ON_DRIFT",
                env_parser="bool",
                toml_val=gate_sec.fail_on_drift,
                default=False,
            )
        ),
        fail_on_anomaly=bool(
            lookup.resolve(
                "gate.fail_on_anomaly",
                cli_key="fail_on_anomaly",
                env_var="EVALFORGE_GATE_FAIL_ON_ANOMALY",
                env_parser="bool",
                toml_val=gate_sec.fail_on_anomaly,
                default=False,
            )
        ),
        fail_on_degrading_trend=bool(
            lookup.resolve(
                "gate.fail_on_degrading_trend",
                cli_key="fail_on_degrading_trend",
                env_var="EVALFORGE_GATE_FAIL_ON_DEGRADING_TREND",
                env_parser="bool",
                toml_val=gate_sec.fail_on_degrading_trend,
                default=False,
            )
        ),
        fail_on_mandatory_regression=(
            gate_sec.fail_on_mandatory_regression
            if gate_sec.fail_on_mandatory_regression is not None
            else True
        ),
        confidence_level=lookup.resolve(
            "gate.confidence_level",
            cli_key="confidence_level",
            env_var="EVALFORGE_CONFIDENCE_LEVEL",
            env_parser="float",
            toml_val=gate_sec.confidence_level,
            default=0.95,
        ),
        min_statistical_samples=lookup.resolve(
            "gate.min_statistical_samples",
            cli_key="min_statistical_samples",
            env_var="EVALFORGE_MIN_STATISTICAL_SAMPLES",
            env_parser="int",
            toml_val=gate_sec.min_statistical_samples,
            default=2,
        ),
        fail_on_significant_regression=bool(
            lookup.resolve(
                "gate.fail_on_significant_regression",
                cli_key="fail_on_significant_regression",
                env_var="EVALFORGE_FAIL_ON_SIGNIFICANT_REGRESSION",
                env_parser="bool",
                toml_val=gate_sec.fail_on_significant_regression,
                default=False,
            )
        ),
    )


_OTEL_ATTR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("case_id_attribute", "otel_case_id_attr", "EVALFORGE_OTEL_CASE_ID_ATTR"),
    ("input_attribute", "otel_input_attr", "EVALFORGE_OTEL_INPUT_ATTR"),
    ("output_attribute", "otel_output_attr", "EVALFORGE_OTEL_OUTPUT_ATTR"),
    ("model_attribute", "otel_model_attr", "EVALFORGE_OTEL_MODEL_ATTR"),
    (
        "service_version_attribute",
        "otel_service_version_attr",
        "EVALFORGE_OTEL_SERVICE_VERSION_ATTR",
    ),
    ("step_kind_attribute", "otel_step_kind_attr", "EVALFORGE_OTEL_STEP_KIND_ATTR"),
    ("tool_name_attribute", "otel_tool_name_attr", "EVALFORGE_OTEL_TOOL_NAME_ATTR"),
    ("tool_arguments_attribute", "otel_tool_args_attr", "EVALFORGE_OTEL_TOOL_ARGS_ATTR"),
    ("tool_result_attribute", "otel_tool_result_attr", "EVALFORGE_OTEL_TOOL_RESULT_ATTR"),
    ("retrieval_documents_attribute", "otel_retrieval_attr", "EVALFORGE_OTEL_RETRIEVAL_ATTR"),
)


def _resolve_otel_section(lookup: _TierLookup, otel_sec: _TomlOtelSection) -> OtelExtractorConfig:
    resolved_attrs: dict[str, Any] = {}
    for field_name, cli_key, env_var in _OTEL_ATTR_SPECS:
        resolved_attrs[field_name] = lookup.resolve(
            f"otel.{field_name}",
            cli_key=cli_key,
            env_var=env_var,
            toml_val=getattr(otel_sec, field_name),
        )
    raw_unit = lookup.resolve(
        "otel.timestamp_unit",
        cli_key="otel_timestamp_unit",
        env_var="EVALFORGE_OTEL_TIMESTAMP_UNIT",
        toml_val=otel_sec.timestamp_unit,
        default=OtelTimestampUnit.AUTO.value,
    )
    try:
        unit = OtelTimestampUnit(str(raw_unit).strip().lower())
    except ValueError as exc:
        raise ConfigurationError(
            f"Invalid otel timestamp_unit {raw_unit!r}; expected auto, ns, us, ms, or s"
        ) from exc

    match_input = bool(
        lookup.resolve(
            "otel.match_dataset_by_input",
            cli_key="otel_match_input",
            env_var="EVALFORGE_OTEL_MATCH_INPUT",
            env_parser="bool",
            toml_val=otel_sec.match_dataset_by_input,
            default=False,
        )
    )
    return OtelExtractorConfig(
        **resolved_attrs,
        timestamp_unit=unit,
        match_dataset_by_input=match_input,
    )


def resolve_cli_config_with_secrets(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[CLIResolvedConfig, str | None, str | None, list[str]]:
    """Resolve configuration strictly across CLI > OS env > --env-file > TOML > defaults.

    Returns `(resolved_config, raw_judge_api_key, raw_embedding_api_key, warnings)` with zero
    secrets retained inside `resolved_config`.
    """
    active_cwd = cwd if cwd is not None else Path.cwd()
    os_env = environ if environ is not None else os.environ
    cli_map = dict(cli_overrides or {})
    warnings: list[str] = []

    env_file_vars, resolved_env_str, toml_model, resolved_cfg_str = _resolve_optional_files(
        cli_map=cli_map,
        os_env=os_env,
        config_path=config_path,
        env_file=env_file,
        active_cwd=active_cwd,
    )

    run_sec = toml_model.run or _TomlRunSection()
    target_sec = toml_model.target or _TomlTargetSection()
    judge_sec = toml_model.judge or _TomlJudgeSection()
    emb_sec = toml_model.embedding or _TomlEmbeddingSection()
    sec_sec = toml_model.security or _TomlSecuritySection()
    gate_sec = toml_model.gate or _TomlGateSection()
    log_sec = toml_model.logging or _TomlLoggingSection()
    otel_sec = toml_model.otel or _TomlOtelSection()

    if judge_sec.api_key and judge_sec.api_key.strip():
        warnings.append(
            "Plaintext judge.api_key found in TOML config; prefer EVALFORGE_JUDGE_API_KEY env var."
        )
    if emb_sec.api_key and emb_sec.api_key.strip():
        warnings.append(
            "Plaintext embedding.api_key found in TOML config; prefer "
            "EVALFORGE_EMBEDDING_API_KEY env var."
        )

    lookup = _TierLookup(cli_overrides=cli_map, os_env=os_env, env_file_vars=env_file_vars)

    storage_dir = lookup.resolve(
        "storage_dir",
        env_var="EVALFORGE_STORAGE_DIR",
        toml_val=run_sec.storage_dir,
        default=".evalforge",
    )
    dataset = lookup.resolve("dataset", env_var="EVALFORGE_DATASET", toml_val=run_sec.dataset)
    dataset_id = lookup.resolve(
        "dataset_id", env_var="EVALFORGE_DATASET_ID", toml_val=run_sec.dataset_id
    )
    dataset_version = lookup.resolve(
        "dataset_version", env_var="EVALFORGE_DATASET_VERSION", toml_val=run_sec.dataset_version
    )
    executions_path = lookup.resolve(
        "executions_path",
        cli_key="executions",
        env_var="EVALFORGE_EXECUTIONS",
        toml_val=run_sec.executions,
    )
    otel_traces_path = lookup.resolve(
        "otel_traces",
        cli_key="otel_traces",
        env_var="EVALFORGE_OTEL_TRACES",
        toml_val=run_sec.otel_traces,
    )
    run_id = lookup.resolve("run_id", env_var="EVALFORGE_RUN_ID", toml_val=run_sec.run_id)
    repeats = lookup.resolve(
        "repeats",
        cli_key="repeats",
        env_var="EVALFORGE_REPEATS",
        env_parser="int",
        toml_val=run_sec.repeats,
        default=1,
    )
    baseline = lookup.resolve("baseline", env_var="EVALFORGE_BASELINE", toml_val=run_sec.baseline)
    baseline_runs = lookup.resolve(
        "baseline_runs",
        cli_key="baseline_run",
        env_var="EVALFORGE_BASELINE_RUNS",
        env_parser="str_list",
        toml_val=run_sec.baseline_runs,
        default=[],
    )
    trend_window = lookup.resolve(
        "trend_window",
        cli_key="trend_window",
        env_var="EVALFORGE_TREND_WINDOW",
        env_parser="int",
        toml_val=run_sec.trend_window,
    )
    strict = lookup.resolve(
        "strict",
        env_var="EVALFORGE_STRICT",
        env_parser="bool",
        toml_val=run_sec.strict,
        default=False,
    )

    try:
        target_cfg = _resolve_target_section(
            lookup,
            target_sec,
            executions_path=str(executions_path) if executions_path is not None else None,
            otel_traces_path=str(otel_traces_path) if otel_traces_path is not None else None,
        )
        otel_cfg = _resolve_otel_section(lookup, otel_sec)
        resolved_metrics = _resolve_metrics_specs(
            lookup,
            cli_map=cli_map,
            os_env=os_env,
            env_file_vars=env_file_vars,
            toml_metrics_tbl=toml_model.metrics,
        )
        exec_cfg = _resolve_execution_section(lookup, run_sec)
        judge_cfg, sec_cfg, raw_key_str = _resolve_judge_and_security(
            lookup, judge_sec, sec_sec, exec_seed=exec_cfg.seed
        )
        emb_cfg, raw_emb_key_str = _resolve_embedding_section(
            lookup,
            emb_sec,
            security_local_only=sec_cfg.local_only,
        )
        gate_cfg = _resolve_gate_section(lookup, gate_sec)

        log_level = lookup.resolve(
            "logging.log_level",
            cli_key="log_level",
            env_var="EVALFORGE_LOG_LEVEL",
            toml_val=log_sec.log_level,
            default="WARNING",
        )
        log_json = lookup.resolve(
            "logging.log_json",
            cli_key="log_json",
            env_var="EVALFORGE_LOG_JSON",
            env_parser="bool",
            toml_val=log_sec.log_json,
            default=False,
        )

        resolved = CLIResolvedConfig(
            config_path=resolved_cfg_str,
            env_file_path=resolved_env_str,
            storage_dir=str(storage_dir),
            dataset=str(dataset) if dataset is not None else None,
            dataset_id=str(dataset_id) if dataset_id is not None else None,
            dataset_version=str(dataset_version) if dataset_version is not None else None,
            executions_path=str(executions_path) if executions_path is not None else None,
            otel_traces=str(otel_traces_path) if otel_traces_path is not None else None,
            otel=otel_cfg,
            run_id=str(run_id) if run_id is not None else None,
            repeats=repeats,
            baseline=str(baseline) if baseline is not None else None,
            baseline_runs=list(baseline_runs),
            trend_window=trend_window,
            strict=bool(strict),
            target=target_cfg,
            metrics=resolved_metrics,
            execution=exec_cfg,
            judge=judge_cfg,
            embedding=emb_cfg,
            security=sec_cfg,
            gate=gate_cfg,
            logging=ResolvedLoggingConfig(
                log_level=str(log_level).upper(),  # type: ignore[arg-type]
                log_json=bool(log_json),
            ),
            provenance=lookup.provenance,
        )
    except ConfigurationError:
        raise
    except (ValidationError, ValueError) as exc:
        raise ConfigurationError(
            f"Resolved configuration failed validation: {scrub_secret_text(str(exc))}"
        ) from exc

    return resolved, raw_key_str, raw_emb_key_str, warnings


def resolve_cli_config(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[CLIResolvedConfig, str | None, list[str]]:
    """Backward-compatible wrapper returning `(resolved_config, raw_judge_api_key, warnings)`."""
    resolved, raw_judge_key, _, warnings = resolve_cli_config_with_secrets(
        cli_overrides=cli_overrides,
        config_path=config_path,
        env_file=env_file,
        cwd=cwd,
        environ=environ,
    )
    return resolved, raw_judge_key, warnings


def format_resolved_config_text(resolved: CLIResolvedConfig) -> str:
    """Render deterministic, secret-masked human-readable resolved config table."""
    lines = [
        "# EvalForge Maestro Resolved Configuration",
        f"config_path = {resolved.config_path or '<none>'}",
        f"env_file_path = {resolved.env_file_path or '<none>'}",
        "",
        "| Setting | Value | Source | Masked |",
        "| --- | --- | --- | --- |",
    ]
    for item in resolved.provenance:
        rendered_val = (
            json.dumps(item.value, ensure_ascii=False)
            if not isinstance(item.value, str)
            else item.value
        )
        lines.append(
            f"| `{item.key}` | `{rendered_val}` | `{item.source.value}` | `{item.masked}` |"
        )
    return "\n".join(lines) + "\n"
