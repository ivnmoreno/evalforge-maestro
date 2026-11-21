"""Contract tests for Feature 007 Embedding & Statistical schemas and legacy compatibility."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from evalforge_maestro.types import (
    BaselineEntry,
    ComparisonDirection,
    DriftCategory,
    EmbeddingAggregation,
    EmbeddingConfig,
    MetricComparison,
    MetricStatus,
    QualityGatePolicy,
    ResolvedEmbeddingSettings,
    RunCohortSummary,
    RunComparisonReport,
    RunManifestEntry,
    RunRecord,
    SignificanceStatus,
    StatisticalMethod,
    StatisticalSummary,
    TargetChangeSummary,
)


def test_embedding_config_validation_redaction_and_determinism() -> None:
    cfg = EmbeddingConfig(
        model="ollama/nomic-embed-text",
        api_base="http://127.0.0.1:11434",
        pass_threshold=0.6543219,
        aggregation=EmbeddingAggregation.MEAN,
        max_input_chars=512,
        local_only=True,
        extra_params={"api_key": "sk-secret-raw-123456", "batch_size": 16},
    )
    redacted = cfg.redacted_dict()
    assert redacted["pass_threshold"] == 0.654322
    assert redacted["extra_params"]["api_key"] != "sk-secret-raw-123456"
    assert redacted["max_input_chars"] == 512

    cfg2 = EmbeddingConfig.model_validate(cfg.model_dump(mode="json"))
    assert cfg2.fingerprint == cfg.fingerprint

    bad_configs: list[dict[str, object]] = [
        {"model": "   "},
        {"api_base": "ftp://example.com"},
        {"api_base": "http://user:pass@localhost:11434"},
        {"pass_threshold": True},
        {"pass_threshold": 1.2},
        {"max_retries": True},
        {"max_input_chars": 0},
        {"max_input_chars": True},
    ]
    for bad_kwargs in bad_configs:
        with pytest.raises(ValueError):
            EmbeddingConfig.model_validate(bad_kwargs)

    resolved = ResolvedEmbeddingSettings(api_key_configured=True, max_input_chars=256)
    assert "api_key" not in ResolvedEmbeddingSettings.model_fields
    assert resolved.api_key_configured is True
    assert resolved.model == "mock-embedding"


def test_embedding_provenance_drift_category_and_legacy_1_0_compat() -> None:
    assert DriftCategory.EMBEDDING_CONFIG.value == "EMBEDDING_CONFIG"

    legacy_run_payload = {
        "schema_version": "1.0",
        "run_id": "legacy-r1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_version": "0.2.0",
        "dataset_id": "ds-1",
        "dataset_fingerprint": "a" * 64,
        "evaluated_case_count": 1,
        "metric_versions": {"exact_match": "1.0.0"},
        "aggregates": {
            "exact_match": {
                "metric_id": "exact_match",
                "metric_version": "1.0.0",
                "mean_score": 1.0,
                "applicable_count": 1,
                "pass_count": 1,
            }
        },
        "status_counts": {
            status.value: (1 if status == MetricStatus.PASS else 0) for status in MetricStatus
        },
        "case_results": [],
    }
    run_rec = RunRecord.model_validate(legacy_run_payload)
    assert run_rec.embedding_config_fingerprint is None

    manifest_entry = RunManifestEntry.from_run_record(run_rec)
    assert manifest_entry.embedding_config_fingerprint is None

    baseline_entry = BaselineEntry.model_validate(
        {
            "schema_version": "1.0",
            "name": "legacy-base",
            "run_id": "legacy-r1",
            "pinned_at": datetime.now(timezone.utc).isoformat(),
            "dataset_id": "ds-1",
            "dataset_fingerprint": "a" * 64,
            "metric_versions": {"exact_match": "1.0.0"},
            "aggregate_scores": {"exact_match": 1.0},
        }
    )
    assert baseline_entry.embedding_config_fingerprint is None


def test_statistical_summary_cohort_and_legacy_comparison_compat() -> None:
    stat = StatisticalSummary(
        method=StatisticalMethod.PAIRED_T_CASE,
        confidence_level=0.95,
        sample_size=5,
        baseline_sample_size=5,
        candidate_sample_size=5,
        mean_delta=-0.1234567,
        delta_std=0.05,
        standard_error=0.0223606,
        baseline_std=0.1,
        candidate_std=0.12,
        ci_low=-0.1855,
        ci_high=-0.0614,
        p_value=0.0052,
        effect_size=-2.469134,
        degrees_of_freedom=4.0,
        significance=SignificanceStatus.SIGNIFICANT_REGRESSION,
        statistically_significant=True,
        explanation="Significant regression detected across 5 paired cases.",
    )
    assert stat.mean_delta == -0.123457
    assert stat.ci_low is not None and -1.0 <= stat.ci_low <= stat.ci_high <= 1.0  # type: ignore[operator]

    cohort = RunCohortSummary(
        baseline_run_ids=["b1", "b2"],
        candidate_run_ids=["c1", "c2", "c3"],
        baseline_run_count=2,
        candidate_run_count=3,
        baseline_names=["rel-1"],
    )
    mc = MetricComparison(
        metric_id="exact_match",
        baseline_score=0.9,
        candidate_score=0.78,
        delta=-0.12,
        direction=ComparisonDirection.REGRESSED,
        statistics=stat,
    )
    report = RunComparisonReport(
        baseline_run_id="b2",
        candidate_run_id="c3",
        target_changes=TargetChangeSummary(),
        metric_comparisons={"exact_match": mc},
        case_comparisons=[],
        matched_case_count=5,
        cohort=cohort,
    )
    assert report.cohort is not None and report.cohort.candidate_run_count == 3

    # Legacy 1.0 comparison report without statistics / cohort fields deserializes cleanly
    legacy_comp = RunComparisonReport.model_validate(
        {
            "schema_version": "1.0",
            "baseline_run_id": "b1",
            "candidate_run_id": "c1",
            "target_changes": {},
            "metric_comparisons": {
                "exact_match": {
                    "metric_id": "exact_match",
                    "baseline_score": 0.9,
                    "candidate_score": 0.8,
                    "delta": -0.1,
                    "direction": "REGRESSED",
                }
            },
            "case_comparisons": [],
            "matched_case_count": 1,
        }
    )
    assert legacy_comp.cohort is None
    assert legacy_comp.metric_comparisons["exact_match"].statistics is None

    for bad_pol in (
        {"confidence_level": 1.0},
        {"confidence_level": 0.0},
        {"confidence_level": True},
        {"min_statistical_samples": 1},
        {"min_statistical_samples": True},
    ):
        with pytest.raises(ValueError):
            QualityGatePolicy.model_validate(bad_pol)
