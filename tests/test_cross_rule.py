"""Cross-rule interaction requirements (SPECIFICATION §21.8)."""

from __future__ import annotations

from support import LC08_ASSET, S1_GRD, S2_SR, analyze, codes


def test_raw_surface_reflectance_reports_ewl201_not_ewl203() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_correctly_scaled_reports_ewl203_not_ewl201() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]


def test_cross_family_scale_reports_ewl202_regardless_of_later_use() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").multiply(0.0000275).add(-0.2)
celsius = thermal.subtract(273.15)
mean = celsius.reduceRegion(reducer=ee.Reducer.mean(), geometry=None, scale=30)
'''
    )
    assert codes(report) == ["EWL202"]


def test_qa60_fully_in_gap_reports_ewl501_only() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == ["EWL501"]
    assert "EWL502" not in codes(report)


def test_multiple_distinct_findings_have_deterministic_order() -> None:
    report = analyze(
        f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
s1 = ee.ImageCollection("{S1_GRD}")
db = s1.first().log10().multiply(10)
thermal = img.select("ST_B10").multiply(0.0000275).add(-0.2)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    # FAIL findings precede CONDITIONAL findings; within a severity, by line.
    assert codes(report) == ["EWL301", "EWL202", "EWL201", "EWL401"]
    lines = [finding.line for finding in report.findings]
    assert lines == [6, 7, 8, 4]
    ranks = [0, 0, 0, 1]
    assert [0 if f.severity.value == "FAIL" else 1 for f in report.findings] == ranks


def test_verdict_precedence_fail_over_conditional() -> None:
    report = analyze(
        f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert report.verdict.value == "FAIL"
