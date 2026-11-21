"""Pure experiment comparison, provenance drift, anti-masking, trend, and gate verification."""

from __future__ import annotations

from evalforge_maestro.regression.anomaly import detect_anomalies
from evalforge_maestro.regression.compare import (
    build_pooled_cohort_run,
    compare_run_cohorts,
    compare_runs,
)
from evalforge_maestro.regression.drift import detect_cohort_drift, detect_drift
from evalforge_maestro.regression.gate import QualityGate
from evalforge_maestro.regression.trend import analyze_trend

__all__ = [
    "QualityGate",
    "analyze_trend",
    "build_pooled_cohort_run",
    "compare_run_cohorts",
    "compare_runs",
    "detect_anomalies",
    "detect_cohort_drift",
    "detect_drift",
]
