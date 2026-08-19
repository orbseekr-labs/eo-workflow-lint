"""Adversarial review: false-positive guardrails and supported-grammar coverage.

These tests validate the existing FROZEN semantics from the opposite direction:
valid workflows must not be accused, and supported syntactic variants of a
genuine violation must not be missed. They introduce no new rule.
"""

from __future__ import annotations

import pytest

from support import LC08_ASSET, LC08_COLLECTION, S1_GRD, S1_GRD_FLOAT, S2_SR, analyze, codes

# ---------------------------------------------------------------- false positives


def test_qa60_as_a_property_value_is_not_a_band_reference() -> None:
    """SPECIFICATION §10.6 requires a proven *band* reference; §8.1 forbids guessing."""
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
tagged = s2.first().set("cloud_source", "QA60")
'''
    )
    assert codes(report) == []


def test_qa60_as_a_property_name_is_not_a_band_reference() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
value = s2.first().get("QA60")
'''
    )
    assert codes(report) == []


def test_qa60_string_in_an_unrelated_argument_list() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
noted = s2.first().setMulti(["QA60", "note"])
'''
    )
    assert codes(report) == []


def test_non_earth_engine_objects_with_similar_method_names() -> None:
    report = analyze(
        """import pandas as pd

frame = pd.read_csv("x.csv")
subset = frame.select(["SR_B5", "SR_B4"])
mapped = frame.map(lambda row: row)
filtered = frame.filterDate("2023-01-01", "2023-06-01")
"""
    )
    assert codes(report) == []


def test_legitimate_db_conversion_on_non_sentinel1_data() -> None:
    report = analyze(
        """import ee
power = ee.Image("USERS/me/linear_power")
db = power.log10().multiply(10)
"""
    )
    assert codes(report) == []


def test_db_conversion_on_grd_float_is_the_correct_workflow() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD_FLOAT}").select("VV")
db = s1.first().log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_round_trip_to_linear_before_db_conversion() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}").select("VV")
linear = s1.first().divide(10).exp()
db = linear.log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_amplitude_scaling_factor_twenty_is_not_the_db_pattern() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}").select("VV")
amplitude = s1.first().log10().multiply(20)
'''
    )
    assert codes(report) == []


def test_rebinding_the_ee_name_disables_recognition() -> None:
    report = analyze(
        f'''import ee
ee = None
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_image_variable_shadowed_by_an_unresolvable_value() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
img = load_from_config()
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_scale_supplied_indirectly_through_a_subscript() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
cfg = {{"scale": 30}}
stats = img.reduceRegion(reducer=None, geometry=None, scale=cfg["scale"])
'''
    )
    assert codes(report) == []


def test_crs_transform_supplied_by_a_function_call() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=None, geometry=None, crsTransform=build_transform())
'''
    )
    assert codes(report) == []


def test_correct_per_band_surface_reflectance_scaling() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
nir = img.select("SR_B5").multiply(0.0000275).add(-0.2)
red = img.select("SR_B4").multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == []


def test_correct_thermal_scaling_then_kelvin_to_celsius() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
celsius = img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
'''
    )
    assert codes(report) == []


def test_map_callback_that_is_a_class_is_not_analyzed_as_a_function() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")


class Converter:
    pass


out = s1.map(Converter)
'''
    )
    assert codes(report) == []


def test_map_callback_referenced_before_definition() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
out = s1.map(to_db)


def to_db(image):
    return image.log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_alias_chain_that_degrades_to_unknown() -> None:
    report = analyze(
        f'''import ee
a = ee.ImageCollection("{S1_GRD}")
b = a.reduce(None)
c = b
d = c.log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_landsat_routed_through_an_unknown_helper() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
prepped = preprocess(img)
ndvi = prepped.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


@pytest.mark.parametrize(
    ("start", "end"),
    [("2021-01-01", "2022-01-26"), ("2024-02-28", "2025-01-01")],
)
def test_qa60_intervals_immediately_outside_the_gap(start: str, end: str) -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("{start}", "{end}")
qa = s2.first().select("QA60")
'''
    )
    assert codes(report) == []


# ---------------------------------------------------------------- false negatives


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "tuple band argument",
            f'import ee\nimg = ee.Image("{LC08_ASSET}")\n'
            'ndvi = img.normalizedDifference(("SR_B5", "SR_B4"))\n',
            ["EWL201"],
        ),
        (
            "constant-bound band list",
            'import ee\nBANDS = ["SR_B5", "SR_B4"]\n'
            f'img = ee.Image("{LC08_ASSET}")\nndvi = img.normalizedDifference(BANDS)\n',
            ["EWL201"],
        ),
        (
            "tier-2 collection",
            'import ee\nc = ee.ImageCollection("LANDSAT/LC09/C02/T2_L2")\n'
            'ndvi = c.first().normalizedDifference(["SR_B5", "SR_B4"])\n',
            ["EWL201"],
        ),
        (
            "legacy LT04 platform",
            'import ee\nc = ee.ImageCollection("LANDSAT/LT04/C02/T1_L2")\n'
            'ndvi = c.first().normalizedDifference(["SR_B3", "SR_B2"])\n',
            ["EWL201"],
        ),
        (
            "after clip and updateMask",
            f'import ee\nimg = ee.Image("{LC08_ASSET}").clip(None).updateMask(None)\n'
            'ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])\n',
            ["EWL201"],
        ),
        (
            "inside a conditional branch",
            f'import ee\nimg = ee.Image("{LC08_ASSET}")\nif flag:\n'
            '    ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])\n',
            ["EWL201"],
        ),
        (
            "EWL202 on a collection element",
            f'import ee\nc = ee.ImageCollection("{LC08_COLLECTION}")\n'
            't = c.first().select("ST_B10").multiply(0.0000275).add(-0.2)\n',
            ["EWL202"],
        ),
        (
            "EWL202 inside a mapped function",
            f'import ee\nc = ee.ImageCollection("{LC08_COLLECTION}")\n\n'
            'def scale(image):\n    return image.select("ST_B10").multiply(0.0000275).add(-0.2)\n\n'
            "out = c.map(scale)\n",
            ["EWL202"],
        ),
        (
            "EWL301 via mapped lambda",
            f'import ee\ns1 = ee.ImageCollection("{S1_GRD}")\n'
            "out = s1.map(lambda image: image.log10().multiply(10))\n",
            ["EWL301"],
        ),
        (
            "EWL301 with float ten in a BinOp",
            f'import ee\ns1 = ee.ImageCollection("{S1_GRD}")\ndb = 10.0 * s1.first().log10()\n',
            ["EWL301"],
        ),
        (
            "EWL301 with a constant-bound factor",
            f'import ee\nFACTOR = 10\ns1 = ee.ImageCollection("{S1_GRD}")\n'
            "db = s1.first().log10().multiply(FACTOR)\n",
            ["EWL301"],
        ),
        (
            "EWL401 on reduceRegions with two positional arguments",
            f'import ee\nimg = ee.Image("{LC08_ASSET}")\nr = img.reduceRegions(None, None)\n',
            ["EWL401"],
        ),
        (
            "EWL401 inside a mapped lambda",
            f'import ee\nc = ee.ImageCollection("{LC08_COLLECTION}")\n'
            "out = c.map(lambda image: image.reduceRegion(reducer=None, geometry=None))\n",
            ["EWL401"],
        ),
        (
            "EWL501 with a constant-bound band name",
            'import ee\nQA = "QA60"\n'
            's2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterDate("2022-06-01", "2023-06-01")\n'
            "q = s2.first().select(QA)\n",
            ["EWL501"],
        ),
        (
            "EWL502 with datetime bounds straddling the gap end",
            'import ee\ns2 = ee.ImageCollection("COPERNICUS/S2_SR")'
            '.filterDate("2024-01-01T00:00:00Z", "2024-06-01T00:00:00Z")\n'
            'q = s2.first().select("QA60")\n',
            ["EWL502"],
        ),
        (
            "EWL203 with constant-bound scale and offset",
            "import ee\nSCALE = 0.0000275\nOFFSET = -0.2\n"
            f'img = ee.Image("{LC08_ASSET}")\n'
            'sr = img.select("SR_B.").multiply(SCALE).add(OFFSET)\n'
            "img = img.addBands(sr, overwrite=True)\n"
            'ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])\n',
            ["EWL203"],
        ),
    ],
)
def test_supported_grammar_variants_still_fire(
    label: str, source: str, expected: list[str]
) -> None:
    assert codes(analyze(source)) == expected, label
