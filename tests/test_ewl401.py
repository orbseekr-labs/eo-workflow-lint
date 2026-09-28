"""EWL401 — ANALYSIS_SCALE_UNSPECIFIED (SPECIFICATION §10.5, §21.6)."""

from __future__ import annotations

from support import LC08_ASSET, analyze, codes, run_cli

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


# ---------------------------------------------------------------------------
# v0.2.1 regression: argument unpacking (real-world benchmark false positive).
#
# Open-ET/openet-ssebop, openet-ptjpl, openet-sims and openet-geesebal build a
# parameter dict containing 'scale' and call ``reduceRegion(**rr_params)``; the
# official Earth Engine Python API samples use ``reduceRegions(**{...,
# 'scale': 5000})``. v0.2.0 ignored ``**`` unpacking and reported EWL401 although
# scale was supplied. When arguments are unpacked the analyzer cannot prove that
# scale and crsTransform are absent, so per SPECIFICATION §8.1 / §10.5 EWL401
# must not fire. Minimal shapes only; no third-party source is copied.
# ---------------------------------------------------------------------------


def test_dict_literal_unpacking_with_scale_is_not_flagged() -> None:
    report = analyze(
        PREAMBLE + "stats = img.reduceRegion(**{'reducer': ee.Reducer.first(), 'geometry': aoi,"
        " 'scale': 30})\n"
    )
    assert codes(report) == []
    assert report.coverage.supported_operation_check_count == 1


def test_named_dict_unpacking_with_scale_is_not_flagged() -> None:
    report = analyze(
        PREAMBLE
        + "def point_image_value(image, xy, scale=1):\n"
        + "    rr_params = {\n"
        + "        'reducer': ee.Reducer.first(),\n"
        + "        'geometry': ee.Geometry.Point(xy),\n"
        + "        'scale': scale,\n"
        + "    }\n"
        + "    return ee.Image(image).reduceRegion(**rr_params)\n"
    )
    assert codes(report) == []


def test_reduce_regions_dict_unpacking_is_not_flagged() -> None:
    report = analyze(
        PREAMBLE + "out = img.reduceRegions(**{'collection': aoi, 'reducer': ee.Reducer.mean(),"
        " 'scale': 5000, 'crs': 'EPSG:4326'})\n"
    )
    assert codes(report) == []


def test_unresolvable_keyword_unpacking_is_not_flagged() -> None:
    """Absence of scale cannot be proven through an opaque mapping (§8.1)."""
    report = analyze(PREAMBLE + "stats = img.reduceRegion(reducer=ee.Reducer.mean(), **options)\n")
    assert codes(report) == []


def test_positional_unpacking_is_not_flagged() -> None:
    report = analyze(PREAMBLE + "stats = img.reduceRegion(ee.Reducer.mean(), *rest)\n")
    assert codes(report) == []


def test_without_unpacking_missing_scale_is_still_flagged() -> None:
    """Twin of the unpacking cases: the ordinary trigger is unchanged."""
    report = analyze(
        PREAMBLE + "stats = img.reduceRegion(reducer=ee.Reducer.first(), geometry=aoi)\n"
    )
    assert codes(report) == ["EWL401"]


def test_explain_lists_argument_unpacking_as_a_non_trigger() -> None:
    """`explain` must reflect SPECIFICATION v0.2.1 §10.5 (release gate §22.7)."""
    exit_code, out, _ = run_cli(["explain", "EWL401"])
    assert exit_code == 0
    assert "*/** argument unpacking" in out
