"""Library-pure reporting subsystem generating JSON and Markdown diagnostics."""

from __future__ import annotations

import logging

from evalforge_maestro.reporting.builder import (
    build_calibration_report,
    build_comparison_report,
    build_run_report,
    build_trend_report,
    detect_decoupled_evidence,
    render_report_json,
)
from evalforge_maestro.reporting.markdown import render_markdown

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "build_calibration_report",
    "build_comparison_report",
    "build_run_report",
    "build_trend_report",
    "detect_decoupled_evidence",
    "render_markdown",
    "render_report_json",
]
