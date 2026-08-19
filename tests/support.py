"""Shared helpers for the conformance test suite."""

from __future__ import annotations

import io

from eo_workflow_lint.analyzer import analyze_source
from eo_workflow_lint.cli import main
from eo_workflow_lint.models import Report

LC08_ASSET = "LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508"
LC08_COLLECTION = "LANDSAT/LC08/C02/T1_L2"
LE07_ASSET = "LANDSAT/LE07/C02/T1_L2/LE07_044034_20010508"
S1_GRD = "COPERNICUS/S1_GRD"
S1_GRD_FLOAT = "COPERNICUS/S1_GRD_FLOAT"
S2_SR = "COPERNICUS/S2_SR_HARMONIZED"


def analyze(code: str) -> Report:
    """Analyze a source snippet."""
    return analyze_source(code.encode("utf-8"))


def codes(report: Report) -> list[str]:
    """Reason codes in deterministic report order."""
    return [finding.code for finding in report.findings]


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process, returning ``(exit_code, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    exit_code = main(argv, stdout=out, stderr=err)
    return exit_code, out.getvalue(), err.getvalue()
