"""EWL202 — LANDSAT_C2_BAND_SCALE_MISMATCH (SPECIFICATION §10.2, §21.3)."""

from __future__ import annotations

from support import LC08_ASSET, LE07_ASSET, analyze, codes


def test_st_b10_with_surface_reflectance_scale_offset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == ["EWL202"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["band_family"] == "ST"
    assert evidence["applied_scale"] == 0.0000275
    assert evidence["applied_offset"] == -0.2
    assert evidence["expected_family_for_transform"] == "SR"


def test_st_b6_with_surface_reflectance_scale_offset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LE07_ASSET}")
thermal = img.select("ST_B6").multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == ["EWL202"]


def test_sr_band_with_surface_temperature_scale_offset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B5").multiply(0.00341802).add(149.0)
'''
    )
    assert codes(report) == ["EWL202"]
    assert report.findings[0].evidence_dict()["expected_family_for_transform"] == "ST"


def test_sr_regex_selection_with_surface_temperature_scale_offset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.00341802).add(149)
'''
    )
    assert codes(report) == ["EWL202"]


def test_integer_and_float_offset_are_equivalent() -> None:
    integer_form = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.00341802).add(149)
'''
    )
    float_form = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.00341802).add(149.0)
'''
    )
    assert codes(integer_form) == codes(float_form) == ["EWL202"]


def test_scientific_notation_scale_literal_is_equivalent() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").multiply(2.75e-05).add(-0.2)
'''
    )
    assert codes(report) == ["EWL202"]


def test_constants_bound_to_wrong_documented_pair() -> None:
    report = analyze(
        f'''import ee
SR_SCALE = 0.0000275
SR_OFFSET = -0.2
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").multiply(SR_SCALE).add(SR_OFFSET)
'''
    )
    assert codes(report) == ["EWL202"]


def test_negative_correct_surface_reflectance_scaling() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == []


def test_negative_correct_surface_temperature_scaling() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").multiply(0.00341802).add(149.0)
'''
    )
    assert codes(report) == []


def test_negative_arbitrary_arithmetic_is_not_a_scale_mismatch() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
scaled = img.select("ST_B10").multiply(0.0001).add(-0.1)
other = img.select("SR_B5").multiply(2).add(1)
'''
    )
    assert codes(report) == []


def test_negative_unknown_band_selection() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
band = pick_band()
scaled = img.select(band).multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == []


def test_negative_whole_image_scaling_is_not_assumed_correct_or_wrong() -> None:
    """SPECIFICATION §7.1 — SR scaling of an entire Landsat image proves nothing."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
scaled = img.multiply(0.0000275).add(-0.2)
ndvi = scaled.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_negative_add_then_multiply_is_not_the_documented_transform() -> None:
    """SPECIFICATION §9.3 — the order MUST be multiply then add."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B10").add(-0.2).multiply(0.0000275)
'''
    )
    assert codes(report) == []


def test_negative_platform_inappropriate_thermal_band() -> None:
    """ST_B6 is not the LC08 thermal band, so band identity is not proven."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B6").multiply(0.0000275).add(-0.2)
'''
    )
    assert codes(report) == []
