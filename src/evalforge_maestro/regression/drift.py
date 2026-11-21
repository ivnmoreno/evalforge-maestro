"""Pure cross-version provenance and comparability drift detection helpers."""

from __future__ import annotations

import itertools
from collections.abc import Sequence

from evalforge_maestro.types import DriftCategory, DriftWarning, RunManifestEntry, RunRecord


def _pair_provenance_drift(
    baseline: RunRecord | RunManifestEntry,
    candidate: RunRecord | RunManifestEntry,
) -> list[DriftWarning]:
    """Compare dataset, metric versions/sets, and judge config provenance between two runs."""
    warnings: list[DriftWarning] = []

    if baseline.dataset_fingerprint != candidate.dataset_fingerprint:
        warnings.append(
            DriftWarning(
                category=DriftCategory.DATASET_FINGERPRINT,
                baseline_run_id=baseline.run_id,
                candidate_run_id=candidate.run_id,
                baseline_value=baseline.dataset_fingerprint,
                candidate_value=candidate.dataset_fingerprint,
                explanation=(
                    f"Dataset content fingerprint shifted from {baseline.dataset_fingerprint[:12]} "
                    f"to {candidate.dataset_fingerprint[:12]} between runs "
                    f"{baseline.run_id!r} and {candidate.run_id!r}."
                ),
            )
        )

    for metric_id in sorted(set(baseline.metric_versions) | set(candidate.metric_versions)):
        in_base = metric_id in baseline.metric_versions
        in_cand = metric_id in candidate.metric_versions
        if in_base and not in_cand:
            warnings.append(
                DriftWarning(
                    category=DriftCategory.METRIC_SET,
                    metric_id=metric_id,
                    baseline_run_id=baseline.run_id,
                    candidate_run_id=candidate.run_id,
                    baseline_value=baseline.metric_versions[metric_id],
                    candidate_value=None,
                    explanation=(
                        f"Metric {metric_id!r} (version {baseline.metric_versions[metric_id]!r}) "
                        f"present in {baseline.run_id!r} was removed in {candidate.run_id!r}."
                    ),
                )
            )
        elif in_cand and not in_base:
            warnings.append(
                DriftWarning(
                    category=DriftCategory.METRIC_SET,
                    metric_id=metric_id,
                    baseline_run_id=baseline.run_id,
                    candidate_run_id=candidate.run_id,
                    baseline_value=None,
                    candidate_value=candidate.metric_versions[metric_id],
                    explanation=(
                        f"Metric {metric_id!r} (version {candidate.metric_versions[metric_id]!r}) "
                        f"was added in {candidate.run_id!r} relative to {baseline.run_id!r}."
                    ),
                )
            )
        else:
            base_ver = baseline.metric_versions[metric_id]
            cand_ver = candidate.metric_versions[metric_id]
            if base_ver != cand_ver:
                warnings.append(
                    DriftWarning(
                        category=DriftCategory.METRIC_VERSION,
                        metric_id=metric_id,
                        baseline_run_id=baseline.run_id,
                        candidate_run_id=candidate.run_id,
                        baseline_value=base_ver,
                        candidate_value=cand_ver,
                        explanation=(
                            f"Metric {metric_id!r} version drifted from {base_ver!r} "
                            f"in {baseline.run_id!r} to {cand_ver!r} in {candidate.run_id!r}."
                        ),
                    )
                )

    if baseline.judge_config_fingerprint != candidate.judge_config_fingerprint:
        warnings.append(
            DriftWarning(
                category=DriftCategory.JUDGE_CONFIG,
                baseline_run_id=baseline.run_id,
                candidate_run_id=candidate.run_id,
                baseline_value=baseline.judge_config_fingerprint,
                candidate_value=candidate.judge_config_fingerprint,
                explanation=(
                    f"Judge configuration fingerprint shifted from "
                    f"{baseline.judge_config_fingerprint!r} in {baseline.run_id!r} to "
                    f"{candidate.judge_config_fingerprint!r} in {candidate.run_id!r}."
                ),
            )
        )

    base_emb_fp = getattr(baseline, "embedding_config_fingerprint", None)
    cand_emb_fp = getattr(candidate, "embedding_config_fingerprint", None)
    if base_emb_fp != cand_emb_fp:
        warnings.append(
            DriftWarning(
                category=DriftCategory.EMBEDDING_CONFIG,
                baseline_run_id=baseline.run_id,
                candidate_run_id=candidate.run_id,
                baseline_value=base_emb_fp,
                candidate_value=cand_emb_fp,
                explanation=(
                    f"Embedding configuration fingerprint shifted from "
                    f"{base_emb_fp!r} in {baseline.run_id!r} to "
                    f"{cand_emb_fp!r} in {candidate.run_id!r}."
                ),
            )
        )

    return warnings


def detect_drift(
    baseline: RunRecord,
    candidate: RunRecord,
) -> list[DriftWarning]:
    """Inspect provenance comparability between baseline and candidate runs.

    Flags mismatches in dataset_fingerprint, shared metric_versions, metric sets,
    judge_config_fingerprint, dataset_capped, and case set alignment while keeping
    intentional target changes (system_version, model_id, config_fingerprint) separate.
    """
    warnings = _pair_provenance_drift(baseline, candidate)

    if baseline.dataset_capped or candidate.dataset_capped:
        warnings.append(
            DriftWarning(
                category=DriftCategory.DATASET_CAPPED,
                baseline_run_id=baseline.run_id,
                candidate_run_id=candidate.run_id,
                baseline_value=baseline.dataset_capped,
                candidate_value=candidate.dataset_capped,
                explanation=(
                    f"At least one compared run evaluated a capped subset "
                    f"(baseline={baseline.dataset_capped}, candidate={candidate.dataset_capped})."
                ),
            )
        )

    base_ids = {case.case_id for case in baseline.case_results}
    cand_ids = {case.case_id for case in candidate.case_results}
    added = sorted(cand_ids - base_ids)
    removed = sorted(base_ids - cand_ids)
    if added or removed:
        warnings.append(
            DriftWarning(
                category=DriftCategory.CASE_SET_MISMATCH,
                baseline_run_id=baseline.run_id,
                candidate_run_id=candidate.run_id,
                baseline_value=removed,
                candidate_value=added,
                explanation=(
                    f"Compared runs differ in evaluated case sets: "
                    f"{len(added)} added, {len(removed)} removed."
                ),
            )
        )

    return warnings


def detect_window_drift(
    runs: Sequence[RunRecord | RunManifestEntry],
) -> list[DriftWarning]:
    """Check adjacent chronological pairs and dataset capping across a trend window."""
    warnings: list[DriftWarning] = []
    for earlier, later in itertools.pairwise(runs):
        warnings.extend(_pair_provenance_drift(earlier, later))

    for run in runs:
        if run.dataset_capped:
            warnings.append(
                DriftWarning(
                    category=DriftCategory.DATASET_CAPPED,
                    candidate_run_id=run.run_id,
                    candidate_value=True,
                    explanation=(
                        f"Window run {run.run_id!r} evaluated a capped subset of its dataset."
                    ),
                )
            )
    return warnings


def detect_cohort_drift(
    baseline_runs: Sequence[RunRecord],
    candidate_runs: Sequence[RunRecord],
) -> list[DriftWarning]:
    """Inspect intra-cohort stability and cross-cohort provenance drift."""
    warnings: list[DriftWarning] = []
    if not baseline_runs or not candidate_runs:
        return warnings

    for later in baseline_runs[1:]:
        warnings.extend(_pair_provenance_drift(baseline_runs[0], later))
    for later in candidate_runs[1:]:
        warnings.extend(_pair_provenance_drift(candidate_runs[0], later))

    warnings.extend(detect_drift(baseline_runs[-1], candidate_runs[-1]))

    for run in [*baseline_runs[:-1], *candidate_runs[:-1]]:
        if run.dataset_capped:
            warnings.append(
                DriftWarning(
                    category=DriftCategory.DATASET_CAPPED,
                    candidate_run_id=run.run_id,
                    candidate_value=True,
                    explanation=(
                        f"Cohort run {run.run_id!r} evaluated a capped subset of its dataset."
                    ),
                )
            )

    deduped: list[DriftWarning] = []
    seen: set[tuple[DriftCategory, str | None, str | None, str | None]] = set()
    for warning in warnings:
        key = (
            warning.category,
            warning.metric_id,
            warning.baseline_run_id,
            warning.candidate_run_id,
        )
        if key not in seen:
            seen.add(key)
            deduped.append(warning)
    return deduped
