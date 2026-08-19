"""EWL203 — NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK (SPECIFICATION §10.3, §21.4)."""

from __future__ import annotations

from support import LC08_ASSET, S1_GRD, analyze, codes


def test_correctly_scaled_and_overwritten_then_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]
    assert report.findings[0].evidence_dict()["sr_scale_state"] == "CORRECTLY_SCALED"


def test_positional_overwrite_form_is_recognised() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(optical, None, True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]


def test_correctly_scaled_two_band_selection_then_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
scaled = img.select(["SR_B5", "SR_B4"]).multiply(0.0000275).add(-0.2)
ndvi = scaled.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]


def test_negative_raw_surface_reflectance_reports_ewl201_only() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_negative_expression_form() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
nir = img.select("SR_B5")
red = img.select("SR_B4")
ndvi = img.expression("(nir - red) / (nir + red)", {{"nir": nir, "red": red}})
'''
    )
    assert codes(report) == []


def test_negative_unknown_scale_state() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
transformed = img.pow(2)
ndvi = transformed.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_negative_overwrite_not_proven_leaves_original_state() -> None:
    """SPECIFICATION §9.4 — without proven overwrite the original state is not replaced."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_negative_non_landsat_product() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
ndvi = s1.first().normalizedDifference(["VV", "VH"])
'''
    )
    assert codes(report) == []
