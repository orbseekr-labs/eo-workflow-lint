"""EWL201 — LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE (SPECIFICATION §10.1, §21.2)."""

from __future__ import annotations

from support import LC08_ASSET, LC08_COLLECTION, analyze, codes


def test_direct_image_raw_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["dataset_id"] == LC08_COLLECTION
    assert evidence["bands"] == ["SR_B5", "SR_B4"]
    assert evidence["sr_scale_state"] == "RAW"


def test_mapped_function_over_collection() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{LC08_COLLECTION}")

def add_ndvi(image):
    return image.normalizedDifference(["SR_B5", "SR_B4"])

result = collection.map(add_ndvi)
'''
    )
    assert codes(report) == ["EWL201"]


def test_mapped_lambda_over_collection() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{LC08_COLLECTION}")
result = collection.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''
    )
    assert codes(report) == ["EWL201"]


def test_constant_bound_dataset_id() -> None:
    report = analyze(
        f'''import ee
DATASET = "{LC08_COLLECTION}"
collection = ee.ImageCollection(DATASET)
image = collection.first()
ndvi = image.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_alias_and_chained_pass_through_preserve_lineage() -> None:
    report = analyze(
        f'''import ee
a = ee.ImageCollection("{LC08_COLLECTION}")
b = a.filterDate("2021-01-01", "2021-02-01").filterBounds(None).select(["SR_B5", "SR_B4"])
c = b
ndvi = c.first().normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_two_band_selection_with_no_argument_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.select(["SR_B5", "SR_B4"]).normalizedDifference()
'''
    )
    assert codes(report) == ["EWL201"]


def test_negative_correctly_scaled_before_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert "EWL201" not in codes(report)


def test_negative_landsat_toa_is_not_collection_2_level_2() -> None:
    report = analyze(
        """import ee
img = ee.Image("LANDSAT/LC08/C02/T1_TOA/LC08_044034_20210508")
ndvi = img.normalizedDifference(["B5", "B4"])
"""
    )
    assert codes(report) == []


def test_negative_unknown_dataset() -> None:
    report = analyze(
        """import ee
img = ee.Image("SOME/UNKNOWN/PRODUCT")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count == 1


def test_negative_dynamic_dataset_id_is_not_fabricated() -> None:
    report = analyze(
        """import ee
import os
img = ee.Image(os.environ["DATASET"])
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count == 1


def test_negative_non_sr_bands() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
result = img.normalizedDifference(["ST_B10", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_negative_expression_instead_of_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
nir = img.select("SR_B5")
red = img.select("SR_B4")
ndvi = img.expression("(nir - red) / (nir + red)", {{"nir": nir, "red": red}})
'''
    )
    assert codes(report) == []


def test_negative_unprovable_band_identity_reduces_coverage() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
bands = compute_bands()
ndvi = img.normalizedDifference(bands)
'''
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count == 1


def test_negative_unrecognised_custom_scaling_helper_does_not_fail() -> None:
    """SPECIFICATION §9.5 — unrecognised equivalent scaling reduces coverage, never FAILs."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")

def scale_sr(image):
    return image.multiply(0.0000275).add(-0.2)

scaled = scale_sr(img)
ndvi = scaled.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []
