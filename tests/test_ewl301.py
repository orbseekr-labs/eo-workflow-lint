"""EWL301 — SENTINEL1_GRD_REDUNDANT_DB_CONVERSION (SPECIFICATION §10.4, §21.5)."""

from __future__ import annotations

from support import LC08_ASSET, S1_GRD, S1_GRD_FLOAT, analyze, codes


def test_method_chain_log10_multiply_10() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
db = s1.first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["dataset_id"] == S1_GRD
    assert evidence["numeric_domain"] == "DB"
    assert evidence["conversion_pattern"] == "log10().multiply(10)"


def test_binop_10_times_log10() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}").select("VV")
db = 10 * s1.first().log10()
'''
    )
    assert codes(report) == ["EWL301"]
    assert report.findings[0].evidence_dict()["conversion_pattern"] == "10 * log10()"


def test_float_literal_ten_is_equivalent() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
db = s1.first().log10().multiply(10.0)
'''
    )
    assert codes(report) == ["EWL301"]


def test_mapped_named_function() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")

def to_db(image):
    return image.log10().multiply(10)

s1 = s1.map(to_db)
'''
    )
    assert codes(report) == ["EWL301"]


def test_constant_bound_dataset_id() -> None:
    report = analyze(
        f'''import ee
DATASET = "{S1_GRD}"
s1 = ee.ImageCollection(DATASET).filterDate("2020-01-01", "2020-02-01").select("VV")
db = s1.first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_negative_grd_float_never_triggers() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD_FLOAT}")

def to_db(image):
    return image.log10().multiply(10)

s1 = s1.map(to_db)
'''
    )
    assert codes(report) == []


def test_negative_standalone_log10() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
result = s1.first().log10()
'''
    )
    assert codes(report) == []


def test_negative_unsupported_transform_makes_domain_unknown() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
result = s1.first().pow(2).log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_negative_linear_conversion_before_db_conversion() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
linear = s1.first().divide(10).exp()
db = linear.log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_negative_multiply_by_other_factor() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
result = s1.first().log10().multiply(20)
'''
    )
    assert codes(report) == []


def test_negative_non_sentinel_dataset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
result = img.log10().multiply(10)
'''
    )
    assert codes(report) == []
