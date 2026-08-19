"""The bundled examples must keep matching their documented verdicts."""

from __future__ import annotations

from pathlib import Path

import pytest

from eo_workflow_lint.analyzer import analyze_source
from support import codes, run_cli

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

EXPECTED = {
    "clean_workflow.py": (0, "PASS", []),
    "landsat_ndvi_unscaled.py": (1, "FAIL", ["EWL201"]),
    "landsat_scale_mismatch.py": (1, "FAIL", ["EWL202"]),
    "reduce_region_no_scale.py": (0, "CONDITIONAL", ["EWL401"]),
    "sentinel1_double_db.py": (1, "FAIL", ["EWL301"]),
    "sentinel2_qa60_gap.py": (1, "FAIL", ["EWL501"]),
}


def test_every_example_is_covered() -> None:
    assert {path.name for path in EXAMPLES.glob("*.py")} == set(EXPECTED)


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED.items()))
def test_example_verdicts(name: str, expected: tuple[int, str, list[str]]) -> None:
    exit_code, verdict, expected_codes = expected
    path = EXAMPLES / name

    report = analyze_source(path.read_bytes())
    assert report.verdict.value == verdict
    assert codes(report) == expected_codes

    actual_exit, out, _ = run_cli(["check", str(path)])
    assert actual_exit == exit_code
    assert out.startswith(verdict + "\n")


def test_readme_sentinel1_example_matches_actual_output() -> None:
    """The README shows a concrete report; keep it truthful."""
    readme = (EXAMPLES.parent / "README.md").read_text(encoding="utf-8")
    report = analyze_source((EXAMPLES / "sentinel1_double_db.py").read_bytes())
    finding = report.findings[0]
    assert f"line {finding.line}: {finding.message}" in readme
    assert f'"line": {finding.line},' in readme
    assert f'"column": {finding.column},' in readme
