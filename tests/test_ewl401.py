"""EWL401 — ANALYSIS_SCALE_UNSPECIFIED (SPECIFICATION §10.5, §21.6)."""

from __future__ import annotations

from support import LC08_ASSET, analyze, codes

PREAMBLE = f'''import ee
img = ee.Image("{LC08_ASSET}")
aoi = ee.Geometry.Point(0, 0)
transform = [30, 0, 0, 0, -30, 0]
my_scale = 30
'''


def test_reduce_region_without_scale_or_transform() -> None:
    report = analyze(
        PREAMBLE + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)\n"
    )
    assert codes(report) == ["EWL401"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["operation"] == "reduceRegion"
    assert evidence["scale_explicit"] is False
    assert evidence["crs_transform_explicit"] is False


def test_reduce_regions_without_scale_or_transform() -> None:
    report = analyze(
        PREAMBLE + "stats = img.reduceRegions(collection=aoi, reducer=ee.Reducer.mean())\n"
    )
    assert codes(report) == ["EWL401"]
    assert report.findings[0].evidence_dict()["operation"] == "reduceRegions"


def test_keyword_scale_none_does_not_suppress() -> None:
    report = analyze(
        PREAMBLE + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=None)\n"
    )
    assert codes(report) == ["EWL401"]


def test_positional_scale_none_does_not_suppress() -> None:
    report = analyze(PREAMBLE + "stats = img.reduceRegion(ee.Reducer.mean(), aoi, None)\n")
    assert codes(report) == ["EWL401"]


def test_negative_keyword_scale_literal() -> None:
    report = analyze(
        PREAMBLE + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=30)\n"
    )
    assert codes(report) == []


def test_negative_keyword_scale_variable() -> None:
    report = analyze(
        PREAMBLE
        + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=my_scale)\n"
    )
    assert codes(report) == []


def test_negative_keyword_crs_transform() -> None:
    report = analyze(
        PREAMBLE
        + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, crsTransform=transform)\n"
    )
    assert codes(report) == []


def test_negative_positional_scale() -> None:
    report = analyze(PREAMBLE + "stats = img.reduceRegion(ee.Reducer.mean(), aoi, 30)\n")
    assert codes(report) == []


def test_negative_positional_crs_transform() -> None:
    report = analyze(
        PREAMBLE
        + "stats = img.reduceRegion(ee.Reducer.mean(), aoi, None, 'EPSG:4326', transform)\n"
    )
    assert codes(report) == []


def test_reduce_regions_positional_scale_is_third_argument() -> None:
    report = analyze(PREAMBLE + "stats = img.reduceRegions(aoi, ee.Reducer.mean(), 30)\n")
    assert codes(report) == []


def test_rule_does_not_judge_whether_scale_is_appropriate() -> None:
    """SPECIFICATION §10.5 — EWL401 checks explicitness only."""
    report = analyze(
        PREAMBLE
        + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=100000)\n"
    )
    assert codes(report) == []


def test_fires_inside_a_helper_function_never_mapped() -> None:
    report = analyze(
        PREAMBLE
        + """
def summarise(image, region):
    return image.reduceRegion(reducer=ee.Reducer.mean(), geometry=region)
"""
    )
    assert codes(report) == ["EWL401"]
