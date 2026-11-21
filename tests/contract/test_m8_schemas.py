"""Contract tests for Feature 008 OTel ingestion configuration and CLI extensions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evalforge_maestro.types import CLIResolvedConfig, OtelExtractorConfig, OtelTimestampUnit


def test_otel_extractor_config_validation_and_defaults() -> None:
    assert {u.value for u in OtelTimestampUnit} == {"auto", "ns", "us", "ms", "s"}

    cfg = OtelExtractorConfig()
    assert cfg.timestamp_unit == OtelTimestampUnit.AUTO
    assert cfg.match_dataset_by_input is False
    assert cfg.case_id_attribute is None

    custom = OtelExtractorConfig(
        case_id_attribute="  app.case_id  ",
        input_attribute="app.input",
        output_attribute="app.output",
        model_attribute="app.model",
        service_version_attribute="app.version",
        step_kind_attribute="app.kind",
        tool_name_attribute="tool.name",
        tool_arguments_attribute="tool.args",
        tool_result_attribute="tool.res",
        retrieval_documents_attribute="rag.docs",
        timestamp_unit=OtelTimestampUnit.US,
        match_dataset_by_input=True,
    )
    assert custom.case_id_attribute == "app.case_id"
    assert custom.timestamp_unit == OtelTimestampUnit.US
    assert custom.match_dataset_by_input is True

    for bad_kwargs in (
        {"case_id_attribute": "   "},
        {"input_attribute": ""},
        {"output_attribute": "\t"},
        {"model_attribute": "  "},
        {"service_version_attribute": " "},
        {"step_kind_attribute": " "},
        {"tool_name_attribute": " "},
        {"tool_arguments_attribute": " "},
        {"tool_result_attribute": " "},
        {"retrieval_documents_attribute": " "},
        {"timestamp_unit": "hours"},
        {"match_dataset_by_input": "invalid_bool_like_maybe"},
        {"unknown_field": "x"},
    ):
        with pytest.raises((ValidationError, ValueError)):
            OtelExtractorConfig.model_validate(bad_kwargs)


def test_cli_resolved_config_otel_fields_and_backward_compat() -> None:
    cfg = CLIResolvedConfig(otel_traces="  traces/export.json  ", otel=OtelExtractorConfig())
    assert cfg.otel_traces == "traces/export.json"
    assert cfg.otel.timestamp_unit == OtelTimestampUnit.AUTO

    with pytest.raises(ValidationError):
        CLIResolvedConfig(otel_traces="   ")

    default_cfg = CLIResolvedConfig.model_validate({})
    assert default_cfg.otel_traces is None
    assert default_cfg.otel.match_dataset_by_input is False
