"""Verbatim conformance with the Appendix A reference examples (SPECIFICATION §A.1-§A.10)."""

from __future__ import annotations

import pytest

from support import analyze, codes

A1 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""

A2 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""

A3 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
nir = img.select("SR_B5")
red = img.select("SR_B4")
ndvi = img.expression(
    "(nir - red) / (nir + red)",
    {"nir": nir, "red": red},
)
"""

A4 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
thermal = img.select("ST_B10").multiply(0.0000275).add(-0.2)
"""

A5 = """import ee

s1 = ee.ImageCollection("COPERNICUS/S1_GRD")


def to_db(image):
    return image.log10().multiply(10)


s1 = s1.map(to_db)
"""

A6 = A5.replace("COPERNICUS/S1_GRD", "COPERNICUS/S1_GRD_FLOAT")

A7 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
aoi = ee.Geometry.Point(0, 0)
stats = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=aoi,
)
"""

A8 = """import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
aoi = ee.Geometry.Point(0, 0)
stats = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=aoi,
    scale=30,
)
"""

A9 = """import ee

s2 = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterDate("2023-01-01", "2024-01-01")
)


def mask_clouds(image):
    qa = image.select("QA60")
    return image.updateMask(qa.eq(0))


clean = s2.map(mask_clouds)
"""

A10 = A9.replace(
    '.filterDate("2023-01-01", "2024-01-01")', '.filterDate("2021-01-01", "2025-01-01")'
)


@pytest.mark.parametrize(
    ("label", "source", "expected_codes", "expected_verdict"),
    [
        ("A.1", A1, ["EWL201"], "FAIL"),
        ("A.2", A2, ["EWL203"], "CONDITIONAL"),
        ("A.3", A3, [], "PASS"),
        ("A.4", A4, ["EWL202"], "FAIL"),
        ("A.5", A5, ["EWL301"], "FAIL"),
        ("A.6", A6, [], "PASS"),
        ("A.7", A7, ["EWL401"], "CONDITIONAL"),
        ("A.8", A8, [], "PASS"),
        ("A.9", A9, ["EWL501"], "FAIL"),
        ("A.10", A10, ["EWL502"], "CONDITIONAL"),
    ],
)
def test_appendix_example(
    label: str, source: str, expected_codes: list[str], expected_verdict: str
) -> None:
    report = analyze(source)
    assert codes(report) == expected_codes, label
    assert report.verdict.value == expected_verdict, label
