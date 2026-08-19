"""Text and JSON output contracts (SPECIFICATION §14, §15, §16)."""

from __future__ import annotations

import json

from eo_workflow_lint.serialization import to_json, to_text
from support import LC08_ASSET, S1_GRD, analyze

MULTI = f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
s1 = ee.ImageCollection("{S1_GRD}")
db = s1.first().log10().multiply(10)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''


def test_json_schema_shape_and_key_order() -> None:
    report = analyze(MULTI)
    payload = json.loads(to_json(report))
    assert list(payload) == [
        "schema_version",
        "tool_version",
        "catalog_version",
        "input",
        "verdict",
        "findings",
        "analysis",
    ]
    assert payload["schema_version"] == "0.1"
    assert payload["tool_version"] == "0.1.0"
    assert payload["catalog_version"] == "2026-08-19.1"
    assert list(payload["input"]) == ["sha256", "byte_length"]
    assert list(payload["findings"][0]) == [
        "code",
        "severity",
        "name",
        "line",
        "column",
        "message",
        "source_ids",
        "evidence",
    ]
    assert list(payload["analysis"]) == [
        "recognized_dataset_count",
        "supported_operation_check_count",
        "unresolved_lineage_count",
        "unresolved_temporal_scope_count",
        "suppressed_finding_count",
    ]


def test_json_contains_no_path_or_timestamp() -> None:
    report = analyze(MULTI)
    text = to_json(report)
    lowered = text.lower()
    for forbidden in ("/users/", "path", "timestamp", "hostname", "generated_at", ".py"):
        assert forbidden not in lowered


def test_json_contains_no_source_snippets() -> None:
    """SPECIFICATION §15 — no excerpt of the analyzed source appears in the report.

    Specified evidence fields such as the operation name are part of the schema,
    not source text.
    """
    report = analyze(MULTI)
    text = to_json(report)
    for line in MULTI.splitlines():
        stripped = line.strip()
        if stripped:
            assert stripped not in text


def test_findings_are_sorted_by_the_specified_tuple() -> None:
    report = analyze(MULTI)
    keys = [finding.sort_key for finding in report.findings]
    assert keys == sorted(keys)
    assert [finding.code for finding in report.findings] == [
        "EWL301",
        "EWL201",
        "EWL401",
    ]


def test_pass_output_states_the_limitation() -> None:
    report = analyze('import ee\nimg = ee.Image("UNKNOWN/PRODUCT")\n')
    text = to_text(report)
    assert text.startswith("PASS\n")
    assert "does not prove" in text
    assert "scientifically correct" in text


def test_conditional_text_output() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=None)
'''
    )
    text = to_text(report, "workflow.py")
    assert text.startswith("CONDITIONAL\n")
    assert "file: workflow.py" in text
    assert "EWL401 ANALYSIS_SCALE_UNSPECIFIED" in text
    assert "source: SRC-GEE-REDUCE-REGION, SRC-GEE-REDUCE-REGIONS" in text
    assert "1 finding: 0 FAIL, 1 CONDITIONAL" in text


def test_fail_text_output_reports_counts_and_coverage() -> None:
    report = analyze(MULTI)
    text = to_text(report)
    assert text.startswith("FAIL\n")
    assert "3 findings: 2 FAIL, 1 CONDITIONAL" in text
    assert "coverage: 2 recognized datasets" in text
    assert "0 unresolved lineage" in text
    assert "0 unresolved temporal scopes" in text


def test_text_output_may_include_the_path_but_json_may_not() -> None:
    report = analyze(MULTI)
    assert "secret-dir/workflow.py" in to_text(report, "secret-dir/workflow.py")
    assert "secret-dir" not in to_json(report)


def test_json_is_utf8_and_newline_terminated() -> None:
    report = analyze('import ee\nLABEL = "植生"\n')
    text = to_json(report)
    assert text.endswith("\n")
    text.encode("utf-8")
