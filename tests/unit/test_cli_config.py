"""Unit tests for 5-tier CLI configuration precedence and secret masking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalforge_maestro._canonical import REDACTED_VALUE
from evalforge_maestro.cli.config import (
    format_resolved_config_text,
    parse_env_file,
    parse_metric_spec_text,
    resolve_cli_config,
)
from evalforge_maestro.exceptions import ConfigurationError
from evalforge_maestro.types import ConfigSourceTier


def test_five_tier_precedence_and_non_recursive_cwd(tmp_path: Path) -> None:
    parent = tmp_path / "workspace"
    subdir = parent / "subproject"
    subdir.mkdir(parents=True)

    # Parent evalforge.toml MUST be ignored under non-recursive CWD discovery
    (parent / "evalforge.toml").write_text(
        '[run]\ndataset = "parent-ignored.jsonl"\nmax_concurrency = 99\n',
        encoding="utf-8",
    )

    # CWD evalforge.toml + explicit --env-file + OS env + CLI overrides
    (subdir / "evalforge.toml").write_text(
        '[run]\ndataset = "file-ds.jsonl"\nmax_concurrency = 3\n'
        'baseline = "file-base"\n\n'
        '[metrics]\nenabled = ["exact_match", "precision_at_k"]\n'
        "[metrics.precision_at_k]\nk = 3\n\n"
        "[security]\nblock_pii = true\n",
        encoding="utf-8",
    )

    # CWD .env MUST NOT be auto-loaded unless --env-file is explicitly passed
    (subdir / ".env").write_text("EVALFORGE_RUN_ID=implicit-should-ignore\n", encoding="utf-8")

    opt_env = subdir / "custom.env"
    opt_env.write_text(
        "# comment\n"
        "EVALFORGE_DATASET=envfile-ds.jsonl\n"
        "export EVALFORGE_MAX_CONCURRENCY=6\n"
        "EVALFORGE_JUDGE_API_KEY='sk-from-env-file-secret-123'\n"
        "EVALFORGE_STRICT=true # trailing comment\n",
        encoding="utf-8",
    )

    os_env = {
        "EVALFORGE_MAX_CONCURRENCY": "8",
        "EVALFORGE_BASELINE": "env-base",
    }
    cli_overrides = {
        "env_file": str(opt_env),
        "baseline": "cli-base",
    }

    resolved, raw_key, warnings = resolve_cli_config(
        cli_overrides=cli_overrides,
        cwd=subdir,
        environ=os_env,
    )
    assert warnings == []
    assert resolved.dataset == "envfile-ds.jsonl"  # env_file > file
    assert resolved.execution.max_concurrency == 8  # env > env_file > file
    assert resolved.baseline == "cli-base"  # cli > env > file
    assert resolved.strict is True
    assert resolved.security.block_pii is True
    assert resolved.run_id is None  # implicit CWD .env was ignored
    assert [m.metric_id for m in resolved.metrics] == ["exact_match", "precision_at_k"]
    assert resolved.metrics[1].params["k"] == 3
    assert raw_key == "sk-from-env-file-secret-123"
    assert resolved.judge.api_key == REDACTED_VALUE

    by_key = {p.key: p for p in resolved.provenance}
    assert by_key["baseline"].source == ConfigSourceTier.CLI
    assert by_key["execution.max_concurrency"].source == ConfigSourceTier.ENV
    assert by_key["dataset"].source == ConfigSourceTier.ENV_FILE
    assert by_key["security.block_pii"].source == ConfigSourceTier.FILE
    assert by_key["storage_dir"].source == ConfigSourceTier.DEFAULT
    assert by_key["judge.api_key"].masked is True
    assert by_key["judge.api_key"].value == REDACTED_VALUE

    rendered = format_resolved_config_text(resolved)
    assert "sk-from-env-file-secret-123" not in rendered
    assert REDACTED_VALUE in rendered
    assert "sk-from-env-file-secret-123" not in json.dumps(resolved.model_dump(mode="json"))

    # Without CWD evalforge.toml in parent, subdir file shouldn't inherit parent values
    isolated = parent / "clean_child"
    isolated.mkdir()
    clean_cfg, _, _ = resolve_cli_config(cwd=isolated, environ={})
    assert clean_cfg.dataset is None
    assert clean_cfg.execution.max_concurrency == 4


def test_toml_hygiene_warning_and_validation_errors(tmp_path: Path) -> None:
    secret_toml = tmp_path / "secret.toml"
    secret_toml.write_text(
        '[judge]\nmodel = "gpt-4o"\napi_key = "sk-plain-toml-secret"\n',
        encoding="utf-8",
    )
    resolved, raw_key, warnings = resolve_cli_config(config_path=secret_toml, environ={})
    assert raw_key == "sk-plain-toml-secret"
    assert resolved.judge.api_key == REDACTED_VALUE
    assert len(warnings) == 1
    assert "Plaintext judge.api_key" in warnings[0]
    assert "sk-plain-toml-secret" not in warnings[0]

    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[unknown_section]\nx = 1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid configuration structure"):
        resolve_cli_config(config_path=bad_toml, environ={})

    syntax_toml = tmp_path / "syntax.toml"
    syntax_toml.write_text("[run\ndataset = 'broken'\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid TOML syntax"):
        resolve_cli_config(config_path=syntax_toml, environ={})

    with pytest.raises(ConfigurationError, match="not found"):
        resolve_cli_config(config_path=tmp_path / "absent.toml", environ={})

    bad_env = tmp_path / "bad.env"
    bad_env.write_text("NOT_A_KEY_VALUE_LINE\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Malformed line 1"):
        parse_env_file(bad_env)

    bad_quotes = tmp_path / "quotes.env"
    bad_quotes.write_text('EVALFORGE_DATASET="unterminated\n', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Malformed quoted value"):
        parse_env_file(bad_quotes)


def test_parse_metric_spec_and_env_errors(tmp_path: Path) -> None:
    s1 = parse_metric_spec_text("precision_at_k:k=3,match_parent_id=true")
    assert s1.metric_id == "precision_at_k"
    assert s1.params == {"k": 3, "match_parent_id": True}

    s2 = parse_metric_spec_text('custom_rubric:{"rubric":"Grade clarity","require_context":true}')
    assert s2.params["rubric"] == "Grade clarity"

    with pytest.raises(ConfigurationError):
        parse_metric_spec_text("   ")
    with pytest.raises(ConfigurationError):
        parse_metric_spec_text("precision_at_k:badparam")
    with pytest.raises(ConfigurationError):
        parse_metric_spec_text("precision_at_k:{badjson}")

    with pytest.raises(ConfigurationError, match="EVALFORGE_MAX_CONCURRENCY"):
        resolve_cli_config(cwd=tmp_path, environ={"EVALFORGE_MAX_CONCURRENCY": "abc"})
    with pytest.raises(ConfigurationError, match="EVALFORGE_STRICT"):
        resolve_cli_config(cwd=tmp_path, environ={"EVALFORGE_STRICT": "maybe"})


def test_docpipe_target_config_precedence_and_validation(tmp_path: Path) -> None:
    (tmp_path / "evalforge.toml").write_text(
        "[target]\n"
        'type = "docpipe"\n'
        'docpipe_mode = "answer_detailed"\n'
        'docpipe_collection = "toml-col"\n'
        'docpipe_persist_dir = "./toml-store"\n'
        "docpipe_top_k = 4\n"
        'docpipe_embed_model = "ollama/nomic-embed-text"\n'
        'docpipe_answer_model = "ollama/llama3.2"\n'
        'docpipe_searcher = "default"\n'
        "docpipe_rerank = false\n",
        encoding="utf-8",
    )
    resolved, _, warnings = resolve_cli_config(
        cli_overrides={
            "docpipe_answer_model": "ollama_chat/qwen2.5:1.5b-instruct",
            "docpipe_rerank": True,
        },
        cwd=tmp_path,
        environ={
            "EVALFORGE_DOCPIPE_SEARCHER": "fts5_hybrid",
            "EVALFORGE_DOCPIPE_API_BASE": "http://127.0.0.1:11434",
        },
    )
    assert warnings == []
    t = resolved.target
    assert t.docpipe_collection == "toml-col"
    assert t.docpipe_persist_dir == "./toml-store"
    assert t.docpipe_top_k == 4
    assert t.docpipe_embed_model == "ollama/nomic-embed-text"
    assert t.docpipe_answer_model == "ollama_chat/qwen2.5:1.5b-instruct"
    assert t.docpipe_api_base == "http://127.0.0.1:11434"
    assert t.docpipe_searcher == "fts5_hybrid"
    assert t.docpipe_rerank is True

    with pytest.raises(ConfigurationError, match="docpipe_api_base"):
        resolve_cli_config(
            cwd=tmp_path,
            environ={"EVALFORGE_DOCPIPE_API_BASE": "ftp://invalid.example.com"},
        )


def test_agent_target_config_with_agent_extractors(tmp_path: Path) -> None:
    (tmp_path / "evalforge.toml").write_text(
        "[target]\n"
        'type = "agent"\n'
        'entrypoint = "my_agent:run"\n'
        "[target.agent_extractors]\n"
        'tool_calls = "invocations"\n'
        'trace = "steps"\n',
        encoding="utf-8",
    )
    resolved, _, warnings = resolve_cli_config(cwd=tmp_path)
    assert warnings == []
    assert resolved.target.target_type is not None
    assert resolved.target.target_type.value == "agent"
    assert resolved.target.agent_extractors == {
        "tool_calls": "invocations",
        "trace": "steps",
    }
