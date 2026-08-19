"""General normative requirements (SPECIFICATION §3, §4, §13, §21.1)."""

from __future__ import annotations

import pytest

from eo_workflow_lint.analyzer import AnalysisError, analyze_source
from support import LC08_ASSET, analyze, codes


def test_utf8_source_is_parsed() -> None:
    report = analyze(
        f'''import ee
# 地表反射率のスケーリング — surface reflectance scaling
LABEL = "植生指数"
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(AnalysisError):
        analyze_source(b'x = "\xff\xfe"\n')


def test_syntax_error_is_rejected() -> None:
    with pytest.raises(AnalysisError) as excinfo:
        analyze_source(b"def broken(:\n")
    assert "syntax error" in str(excinfo.value)


def test_unsupported_dynamic_construct_is_not_a_syntax_error() -> None:
    """SPECIFICATION §3.2 — dynamic code reduces coverage instead of failing."""
    report = analyze(
        """import ee
import importlib
module = importlib.import_module("something")
img = ee.Image(module.DATASET)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count >= 1


def test_sha256_and_byte_length_describe_the_exact_input() -> None:
    import hashlib

    data = b'import ee\nimg = ee.Image("x")\n'
    report = analyze_source(data)
    assert report.input.sha256 == hashlib.sha256(data).hexdigest()
    assert report.input.byte_length == len(data)
    assert len(report.input.sha256) == 64


def test_verdict_pass_when_no_finding() -> None:
    report = analyze('import ee\nimg = ee.Image("UNKNOWN/PRODUCT")\n')
    assert report.verdict.value == "PASS"


def test_verdict_conditional_when_only_conditional_findings() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=None)
'''
    )
    assert report.verdict.value == "CONDITIONAL"


def test_no_unknown_verdict_exists() -> None:
    from eo_workflow_lint.models import Verdict

    assert {member.value for member in Verdict} == {"PASS", "CONDITIONAL", "FAIL"}


def test_coverage_counters_are_reported() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
other = ee.Image(dynamic_id())
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    coverage = report.coverage.to_json_obj()
    assert set(coverage) == {
        "recognized_dataset_count",
        "supported_operation_check_count",
        "unresolved_lineage_count",
        "unresolved_temporal_scope_count",
        "suppressed_finding_count",
    }
    assert coverage["recognized_dataset_count"] == 1
    assert coverage["unresolved_lineage_count"] == 1


def test_coverage_does_not_change_the_verdict() -> None:
    report = analyze("import ee\nimg = ee.Image(dynamic_id())\n")
    assert report.coverage.unresolved_lineage_count == 1
    assert report.verdict.value == "PASS"


def test_duplicate_findings_are_deduplicated() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{LC08_ASSET}")

def add_ndvi(image):
    return image.normalizedDifference(["SR_B5", "SR_B4"])

first = collection.map(add_ndvi)
second = collection.map(add_ndvi)
'''
    )
    assert codes(report) == ["EWL201"]


def test_only_the_seven_registered_reason_codes_exist() -> None:
    from eo_workflow_lint.rules import RULE_CODES

    assert set(RULE_CODES) == {
        "EWL201",
        "EWL202",
        "EWL203",
        "EWL301",
        "EWL401",
        "EWL501",
        "EWL502",
    }


def test_findings_carry_source_provenance() -> None:
    from eo_workflow_lint import catalog

    known = {source.id for source in catalog.sources()}
    report = analyze(
        f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert report.findings
    for finding in report.findings:
        assert finding.source_ids
        assert set(finding.source_ids) <= known
        assert list(finding.source_ids) == sorted(finding.source_ids)


def test_empty_source_passes() -> None:
    report = analyze("")
    assert report.verdict.value == "PASS"
    assert codes(report) == []
