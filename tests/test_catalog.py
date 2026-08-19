"""Frozen catalog and source registry conformance (SPECIFICATION §6, §7, §24)."""

from __future__ import annotations

import pytest

from eo_workflow_lint import catalog
from eo_workflow_lint.models import Severity
from eo_workflow_lint.rules import RULES

LANDSAT_C2_L2_COLLECTIONS = [
    "LANDSAT/LT04/C02/T1_L2",
    "LANDSAT/LT04/C02/T2_L2",
    "LANDSAT/LT05/C02/T1_L2",
    "LANDSAT/LT05/C02/T2_L2",
    "LANDSAT/LE07/C02/T1_L2",
    "LANDSAT/LE07/C02/T2_L2",
    "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT/LC08/C02/T2_L2",
    "LANDSAT/LC09/C02/T1_L2",
    "LANDSAT/LC09/C02/T2_L2",
]


def test_catalog_version() -> None:
    assert catalog.CATALOG_VERSION == "2026-08-19.1"


@pytest.mark.parametrize("dataset_id", LANDSAT_C2_L2_COLLECTIONS)
def test_all_landsat_collection_2_level_2_ids_are_recognised(dataset_id: str) -> None:
    info = catalog.recognize_dataset(dataset_id)
    assert info is not None
    assert info.family == "LANDSAT_C2_L2"


@pytest.mark.parametrize("dataset_id", LANDSAT_C2_L2_COLLECTIONS)
def test_concrete_assets_under_recognised_collections(dataset_id: str) -> None:
    info = catalog.recognize_dataset(dataset_id + "/SOME_SCENE_ID")
    assert info is not None
    assert info.dataset_id == dataset_id


def test_landsat_scale_and_offset_constants() -> None:
    constants = catalog.landsat_constants()
    assert constants.sr_scale == 0.0000275
    assert constants.sr_offset == -0.2
    assert constants.st_scale == 0.00341802
    assert constants.st_offset == 149.0


@pytest.mark.parametrize(
    ("platform", "band"),
    [
        ("LT04", "ST_B6"),
        ("LT05", "ST_B6"),
        ("LE07", "ST_B6"),
        ("LC08", "ST_B10"),
        ("LC09", "ST_B10"),
    ],
)
def test_platform_appropriate_thermal_bands(platform: str, band: str) -> None:
    assert catalog.landsat_st_band_for_platform(platform) == band


@pytest.mark.parametrize("band", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"])
def test_surface_reflectance_band_family(band: str) -> None:
    assert catalog.landsat_sr_band(band)


@pytest.mark.parametrize("band", ["SR_B0", "SR_B8", "ST_B10", "QA_PIXEL", "B5", "SR_B"])
def test_non_surface_reflectance_bands(band: str) -> None:
    assert not catalog.landsat_sr_band(band)


def test_sentinel1_domains() -> None:
    assert catalog.recognize_dataset("COPERNICUS/S1_GRD").domain == "DB"
    assert catalog.recognize_dataset("COPERNICUS/S1_GRD_FLOAT").domain == "LINEAR_POWER"


def test_sentinel1_backscatter_bands() -> None:
    assert set(catalog.S1_BACKSCATTER_BANDS) == {"VV", "VH", "HH", "HV"}


@pytest.mark.parametrize(
    "dataset_id",
    [
        "COPERNICUS/S2",
        "COPERNICUS/S2_HARMONIZED",
        "COPERNICUS/S2_SR",
        "COPERNICUS/S2_SR_HARMONIZED",
    ],
)
def test_sentinel2_collections(dataset_id: str) -> None:
    info = catalog.recognize_dataset(dataset_id)
    assert info is not None
    assert info.family == "SENTINEL2"


def test_qa60_gap_constants() -> None:
    start, end = catalog.qa60_gap()
    assert start.isoformat() == "2022-01-26T00:00:00"
    assert end.isoformat() == "2024-02-28T00:00:00"


def test_unsupported_datasets_are_not_recognised() -> None:
    for dataset_id in (
        "LANDSAT/LC08/C01/T1_SR",
        "LANDSAT/LC08/C02/T1_TOA",
        "COPERNICUS/S3/OLCI",
        "MODIS/006/MOD13Q1",
        "",
    ):
        assert catalog.recognize_dataset(dataset_id) is None


def test_source_registry_ids_and_order() -> None:
    ids = [source.id for source in catalog.sources()]
    assert ids == sorted(ids)
    assert set(ids) == {
        "SRC-GEE-LANDSAT-C1-C2",
        "SRC-GEE-NORMALIZED-DIFFERENCE",
        "SRC-GEE-REDUCE-REGION",
        "SRC-GEE-REDUCE-REGIONS",
        "SRC-GEE-S1-GRD",
        "SRC-GEE-S2-HARMONIZED",
        "SRC-GEE-S2-SR-HARMONIZED",
        "SRC-USGS-LANDSAT-C2-SCALE",
    }


def test_every_source_has_a_title_url_and_facts() -> None:
    for source in catalog.sources():
        assert source.title
        assert source.url.startswith("https://")
        assert source.facts


def test_registry_severities_match_the_specification() -> None:
    expected = {
        "EWL201": Severity.FAIL,
        "EWL202": Severity.FAIL,
        "EWL203": Severity.CONDITIONAL,
        "EWL301": Severity.FAIL,
        "EWL401": Severity.CONDITIONAL,
        "EWL501": Severity.FAIL,
        "EWL502": Severity.CONDITIONAL,
    }
    assert {meta.code: meta.severity for meta in RULES} == expected


def test_registry_names_match_the_specification() -> None:
    expected = {
        "EWL201": "LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE",
        "EWL202": "LANDSAT_C2_BAND_SCALE_MISMATCH",
        "EWL203": "NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK",
        "EWL301": "SENTINEL1_GRD_REDUNDANT_DB_CONVERSION",
        "EWL401": "ANALYSIS_SCALE_UNSPECIFIED",
        "EWL501": "SENTINEL2_QA60_UNAVAILABLE",
        "EWL502": "SENTINEL2_QA60_GAP_OVERLAP",
    }
    assert {meta.code: meta.name for meta in RULES} == expected


def test_every_rule_references_only_registered_sources() -> None:
    known = {source.id for source in catalog.sources()}
    for meta in RULES:
        assert meta.source_ids
        assert set(meta.source_ids) <= known


def test_catalog_is_not_refreshed_at_runtime() -> None:
    """The catalog is bundled package data, loaded from disk, never fetched."""
    import inspect

    source = inspect.getsource(catalog)
    for forbidden in ("http", "urlopen", "requests", "socket"):
        assert forbidden not in source.replace("https://", "").replace("http_", "")
