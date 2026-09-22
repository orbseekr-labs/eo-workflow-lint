"""v0.2.0 coverage hardening (SPECIFICATION v0.2.0 §8.3, §8.5, §8.7, §8.9, §8.10, §9.4).

Each recovered real-world structure is reproduced as a minimal synthetic fixture
(no external source is copied) and tested in three states:

A. correctly scaled SR  -> EWL203
B. raw / unscaled SR    -> EWL201
C. unresolved state     -> no EWL201 and no EWL203

The conservative rule (§8.1) is unchanged: a fact that cannot be proven never
produces a scientific finding.
"""

from __future__ import annotations

import pytest

from support import LC08_ASSET, LC08_COLLECTION, analyze, codes

LT05_COLLECTION = "LANDSAT/LT05/C02/T1_L2"
LC09_COLLECTION = "LANDSAT/LC09/C02/T1_L2"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

#: The documented SR pair; the "unknown" variant is off by one digit, so the
#: transform is no longer the documented one and the scale state stays UNKNOWN.
SR_SCALE = "0.0000275"
NOT_SR_SCALE = "0.0000276"


def _module_helper(scale: str = SR_SCALE, thermal: str = "ST_B.*") -> str:
    return f'''def apply_scale_factors(image):
    optical = image.select("SR_B.").multiply({scale}).add(-0.2)
    thermal = image.select("{thermal}").multiply(0.00341802).add(149.0)
    return image.addBands(optical, None, True).addBands(thermal, None, True)
'''


# ---------------------------------------------------------------- ST_B.* + §9.4


def _thermal_overwrite_source(scale: str = SR_SCALE, thermal: str = "ST_B.*") -> str:
    return f'''import ee
{_module_helper(scale, thermal)}col = ee.ImageCollection("{LC08_COLLECTION}").map(apply_scale_factors)
ndvi = col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''


@pytest.mark.parametrize("thermal", ["ST_B.*", "ST_B10"])
def test_thermal_overwrite_keeps_proven_sr_scale(thermal: str) -> None:
    """A proven non-SR overwrite must not erase the SR scale state (§9.4)."""
    report = analyze(_thermal_overwrite_source(thermal=thermal))
    assert codes(report) == ["EWL203"]


def test_thermal_overwrite_raw_state_reports_ewl201() -> None:
    source = _thermal_overwrite_source().replace(".map(apply_scale_factors)", "")
    assert codes(analyze(source)) == ["EWL201"]


def test_thermal_overwrite_unknown_scale_reports_nothing() -> None:
    assert codes(analyze(_thermal_overwrite_source(scale=NOT_SR_SCALE))) == []


def test_unknown_family_overwrite_still_resets_sr_scale() -> None:
    """Only a *proven* non-SR family is safe; UNKNOWN still resets (§9.4)."""
    report = analyze(
        f'''import ee
def prep(image):
    optical = image.select("SR_B.").multiply({SR_SCALE}).add(-0.2)
    other = image.select("FOO_B1").multiply(2).add(1)
    return image.addBands(optical, None, True).addBands(other, None, True)
col = ee.ImageCollection("{LC08_COLLECTION}").map(prep)
ndvi = col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''
    )
    assert codes(report) == []


def test_optical_regex_selector_is_still_unproven() -> None:
    """``SR_B.*`` is deliberately not recognised in v0.2.0."""
    source = _thermal_overwrite_source().replace('select("SR_B.")', 'select("SR_B.*")')
    assert codes(analyze(source)) == []


def test_st_regex_selection_does_not_prove_a_scaled_st_band() -> None:
    """``ST_B.*`` proves the family, never a CORRECTLY_SCALED ST state (§9.2)."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B.*").multiply(0.00341802).add(149.0)
'''
    )
    assert codes(report) == []


def test_sr_transform_on_a_proven_st_regex_selection_is_ewl202() -> None:
    """The newly proven ST family makes this cross-family misuse detectable."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
thermal = img.select("ST_B.*").multiply({SR_SCALE}).add(-0.2)
'''
    )
    assert codes(report) == ["EWL202"]


# --------------------------------------------------- module-scope visibility


def _helper_visibility_source(scale: str = SR_SCALE) -> str:
    return f'''import ee
{_module_helper(scale)}
def process_year(year, bbox):
    col = (ee.ImageCollection("{LC08_COLLECTION}")
           .filterBounds(bbox)
           .map(apply_scale_factors))
    return col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''


def test_module_helper_is_visible_inside_a_swept_function() -> None:
    report = analyze(_helper_visibility_source())
    assert codes(report) == ["EWL203"]
    assert report.findings[0].line == 11


def test_module_helper_visibility_raw_state_reports_ewl201() -> None:
    source = _helper_visibility_source().replace("\n           .map(apply_scale_factors)", "")
    assert codes(analyze(source)) == ["EWL201"]


def test_module_helper_visibility_unknown_scale_reports_nothing() -> None:
    assert codes(analyze(_helper_visibility_source(scale=NOT_SR_SCALE))) == []


def test_a_parameter_shadows_a_module_binding() -> None:
    source = _helper_visibility_source().replace(
        "def process_year(year, bbox):", "def process_year(apply_scale_factors, bbox):"
    )
    assert codes(analyze(source)) == []


def test_a_local_assignment_overrides_a_module_binding() -> None:
    source = _helper_visibility_source().replace(
        "def process_year(year, bbox):\n",
        "def process_year(year, bbox):\n    apply_scale_factors = build_it()\n",
    )
    assert codes(analyze(source)) == []


def test_a_rebound_module_name_is_not_seeded() -> None:
    """Choosing between two module-level bindings would be a guess (§8.1)."""
    source = _helper_visibility_source().replace(
        "\ndef process_year(",
        "\ndef apply_scale_factors(image):\n    return image\n\n\ndef process_year(",
    )
    assert codes(analyze(source)) == []


def test_a_module_level_image_is_not_seeded() -> None:
    """Lineage-carrying module bindings are excluded on purpose (§8.3)."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")

def process():
    return img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


# ------------------------------------------------------------------- median()


def _median_source(reducer: str = ".median()", scale: str = SR_SCALE) -> str:
    return f'''import ee
{_module_helper(scale)}
def composite(region):
    col = (ee.ImageCollection("{LC08_COLLECTION}")
           .filterBounds(region)
           .map(apply_scale_factors))
    image = col{reducer}.clip(region)
    return image.normalizedDifference(["SR_B5", "SR_B4"])
'''


def test_median_preserves_the_proven_scale_state() -> None:
    report = analyze(_median_source())
    assert codes(report) == ["EWL203"]
    assert report.findings[0].line == 12


def test_median_raw_state_reports_ewl201() -> None:
    source = _median_source().replace("\n           .map(apply_scale_factors)", "")
    assert codes(analyze(source)) == ["EWL201"]


def test_median_unknown_scale_reports_nothing() -> None:
    assert codes(analyze(_median_source(scale=NOT_SR_SCALE))) == []


@pytest.mark.parametrize(
    "reducer",
    [".reduce(ee.Reducer.median())", ".mean()", ".min()", ".max()", ".qualityMosaic('NDVI')"],
)
def test_other_reducers_remain_unknown_producing(reducer: str) -> None:
    """Only ``ImageCollection.median()`` is recognised; ``reduce()`` also renames bands."""
    assert codes(analyze(_median_source(reducer=reducer))) == []


def test_median_on_a_non_collection_is_not_recognised() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply({SR_SCALE}).add(-0.2)
img = img.addBands(sr, overwrite=True).median()
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


# -------------------------------------------------------------------- merge()


def _merge_source(
    second: str = f'ee.ImageCollection("{LC09_COLLECTION}")', scale: str = SR_SCALE
) -> str:
    return f'''import ee
{_module_helper(scale)}
def add_ndvi(image):
    return image.addBands(image.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI"))


def build(region):
    first = ee.ImageCollection("{LC08_COLLECTION}").filterBounds(region)
    second = {second}.filterBounds(region)
    col = first.merge(second)
    col = col.map(apply_scale_factors)
    return col.map(add_ndvi)
'''


def test_merge_of_the_same_family_preserves_state() -> None:
    report = analyze(_merge_source())
    assert codes(report) == ["EWL203"]
    evidence = report.findings[0].evidence_dict()
    # The platforms differ, so the concrete dataset is no longer proven.
    assert evidence["dataset_id"] is None
    assert evidence["bands"] == ["SR_B5", "SR_B4"]


def test_merge_raw_state_reports_ewl201() -> None:
    source = _merge_source().replace("    col = col.map(apply_scale_factors)\n", "")
    assert codes(analyze(source)) == ["EWL201"]


def test_merge_unknown_scale_reports_nothing() -> None:
    assert codes(analyze(_merge_source(scale=NOT_SR_SCALE))) == []


def test_merge_across_product_families_is_unknown() -> None:
    assert codes(analyze(_merge_source(second=f'ee.ImageCollection("{S2_COLLECTION}")'))) == []


def test_merge_with_an_unproven_collection_is_unknown() -> None:
    assert codes(analyze(_merge_source(second="ee.ImageCollection(dynamic_id())"))) == []


def test_merge_without_an_argument_is_unknown() -> None:
    source = _merge_source().replace("first.merge(second)", "first.merge()")
    assert codes(analyze(source)) == []


# -------------------------------------------------- branch band alternatives


def _branch_source(
    nir_else: str = '"SR_B4"', red_else: str = '"SR_B3"', scale: str = SR_SCALE
) -> str:
    return f'''import ee


def process(start_date, roi):
    start_year = int(start_date[:4])
    if start_year >= 2013:
        collection = ee.ImageCollection("{LC08_COLLECTION}")
    else:
        collection = ee.ImageCollection("{LT05_COLLECTION}")

    def apply_scale_factors(image):
        optical = image.select("SR_B.").multiply({scale}).add(-0.2)
        return image.addBands(optical, None, True)

    def calculate_ndvi(image):
        if start_year >= 2013:
            nir = "SR_B5"
            red = "SR_B4"
        else:
            nir = {nir_else}
            red = {red_else}
        return image.addBands(image.normalizedDifference([nir, red]).rename("ndvi"))

    return collection.map(apply_scale_factors).map(calculate_ndvi)
'''


def test_branch_selected_band_names_stay_provable() -> None:
    report = analyze(_branch_source())
    assert codes(report) == ["EWL203"]
    evidence = report.findings[0].evidence_dict()
    assert "bands" not in evidence
    # Possibilities per argument, never pairs the analyzer cannot prove reachable.
    assert evidence["band_argument_alternatives"] == [["SR_B4", "SR_B5"], ["SR_B3", "SR_B4"]]
    assert evidence["sr_scale_state"] == "CORRECTLY_SCALED"


def test_branch_alternatives_raw_state_reports_ewl201() -> None:
    source = _branch_source().replace("collection.map(apply_scale_factors).map", "collection.map")
    report = analyze(source)
    assert codes(report) == ["EWL201"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["sr_scale_state"] == "RAW"
    assert evidence["band_argument_alternatives"] == [["SR_B4", "SR_B5"], ["SR_B3", "SR_B4"]]


def test_evidence_never_carries_both_band_keys() -> None:
    """Exactly one of the two band keys, for every EWL201/EWL203 finding."""
    for source in (
        _branch_source(),
        _branch_source().replace("collection.map(apply_scale_factors).map", "collection.map"),
        _thermal_overwrite_source(),
        _median_source(),
    ):
        for finding in analyze(source).findings:
            evidence = finding.evidence_dict()
            assert ("bands" in evidence) ^ ("band_argument_alternatives" in evidence)


def test_single_proven_pair_uses_the_bands_key() -> None:
    evidence = analyze(_thermal_overwrite_source()).findings[0].evidence_dict()
    assert evidence["bands"] == ["SR_B5", "SR_B4"]
    assert "band_argument_alternatives" not in evidence


def test_branch_alternatives_are_deterministic() -> None:
    """Sorted per argument, so repeated runs render identical JSON."""
    from eo_workflow_lint.serialization import to_json

    first = to_json(analyze(_branch_source()))
    assert all(to_json(analyze(_branch_source())) == first for _ in range(5))
    assert '"band_argument_alternatives"' in first


def test_branch_alternatives_unknown_scale_reports_nothing() -> None:
    assert codes(analyze(_branch_source(scale=NOT_SR_SCALE))) == []


def test_one_non_sr_alternative_blocks_the_finding() -> None:
    assert codes(analyze(_branch_source(nir_else='"B4"'))) == []


def test_one_unknown_alternative_blocks_the_finding() -> None:
    assert codes(analyze(_branch_source(nir_else="resolve_band()"))) == []


def test_more_alternatives_than_the_cap_block_the_finding() -> None:
    """3x3 candidate pairs exceed the four-alternative cap (§8.10)."""
    source = _branch_source().replace(
        '        else:\n            nir = "SR_B4"\n            red = "SR_B3"\n',
        '        elif start_year >= 1999:\n            nir = "SR_B4"\n            red = "SR_B3"\n'
        '        else:\n            nir = "SR_B7"\n            red = "SR_B6"\n',
    )
    assert codes(analyze(source)) == []


def test_one_of_values_never_reach_numeric_arithmetic() -> None:
    """``OneOfValue`` is string-only and must not resolve a scale constant."""
    report = analyze(
        f'''import ee
if flag:
    factor = "{SR_SCALE}"
else:
    factor = "other"
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(factor).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_one_of_values_do_not_resolve_a_dataset_identity() -> None:
    report = analyze(
        f'''import ee
if flag:
    dataset = "{LC08_COLLECTION}"
else:
    dataset = "{LT05_COLLECTION}"
col = ee.ImageCollection(dataset)
ndvi = col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''
    )
    assert codes(report) == []


# ------------------------------------------------- out-of-scope gaps (pinned)


def test_dataset_identity_from_an_attribute_is_still_unproven() -> None:
    report = analyze(
        f"""import ee
{_module_helper()}
def build(region):
    col = ee.ImageCollection(CFG.landsat).map(apply_scale_factors)
    return col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
"""
    )
    assert codes(report) == []


def test_a_plain_call_result_is_still_unproven() -> None:
    report = analyze(
        f'''import ee
{_module_helper()}
def load():
    return ee.ImageCollection("{LC08_COLLECTION}").map(apply_scale_factors)


def c_factor(landsat):
    return landsat.median().normalizedDifference(["SR_B5", "SR_B4"])


out = c_factor(load())
'''
    )
    assert codes(report) == []


def test_a_cross_module_helper_is_still_unproven() -> None:
    report = analyze(
        f'''import ee
from helpers import apply_scale_factors
col = ee.ImageCollection("{LC08_COLLECTION}").map(apply_scale_factors)
ndvi = col.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''
    )
    assert codes(report) == []
