"""Dataset lineage and supported AST constructs (SPECIFICATION §8)."""

from __future__ import annotations

from support import LC08_ASSET, LC08_COLLECTION, S1_GRD, S1_GRD_FLOAT, analyze, codes


def test_direct_construction_is_recognised() -> None:
    report = analyze(f'import ee\nimg = ee.Image("{LC08_ASSET}")\n')
    assert report.coverage.recognized_dataset_count == 1


def test_aliases_propagate_state() -> None:
    report = analyze(
        f'''import ee
a = ee.ImageCollection("{S1_GRD}")
b = a.filterDate("2020-01-01", "2020-02-01")
c = b
db = c.first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_aliased_module_import_is_supported() -> None:
    report = analyze(
        f'''import ee as gee
img = gee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_function_argument_propagation_through_map() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")

def convert(image):
    band = image.select("VV")
    return band.log10().multiply(10)

converted = collection.map(convert)
'''
    )
    assert codes(report) == ["EWL301"]


def test_map_callback_with_extra_default_arguments_is_supported() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")

def convert(image, factor=10):
    return image.log10().multiply(10)

converted = collection.map(convert)
'''
    )
    assert codes(report) == ["EWL301"]


def test_map_callback_requiring_two_arguments_is_not_bound() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")

def convert(image, factor):
    return image.log10().multiply(10)

converted = collection.map(convert)
'''
    )
    assert codes(report) == []


def test_recursive_map_callback_terminates_without_findings() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")

def convert(image):
    return convert(image)

converted = collection.map(convert)
'''
    )
    assert codes(report) == []


def test_dynamic_map_callback_reduces_coverage() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")
converted = collection.map(lookup_callback())
'''
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count == 1


def test_map_result_lineage_flows_onward() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{LC08_COLLECTION}")
selected = collection.map(lambda image: image.select(["SR_B5", "SR_B4"]))
ndvi = selected.first().normalizedDifference()
'''
    )
    assert codes(report) == ["EWL201"]


def test_conflicting_branches_merge_to_unknown() -> None:
    """SPECIFICATION §8.10 — incompatible branch states become UNKNOWN."""
    report = analyze(
        f'''import ee
if use_radar:
    source = ee.ImageCollection("{S1_GRD}")
else:
    source = ee.ImageCollection("{S1_GRD_FLOAT}")
db = source.first().log10().multiply(10)
'''
    )
    assert codes(report) == []


def test_identical_branches_preserve_state() -> None:
    report = analyze(
        f'''import ee
if use_iw:
    source = ee.ImageCollection("{S1_GRD}")
else:
    source = ee.ImageCollection("{S1_GRD}")
db = source.first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_reassignment_uses_the_current_lexical_value() -> None:
    """SPECIFICATION §8.3 — lexical statement order proves the current value."""
    report = analyze(
        f'''import ee
DATASET = "{S1_GRD_FLOAT}"
DATASET = "{S1_GRD}"
db = ee.ImageCollection(DATASET).first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_loop_body_findings_are_reported_once() -> None:
    report = analyze(
        f'''import ee
for year in [2020, 2021]:
    collection = ee.ImageCollection("{S1_GRD}")
    db = collection.first().log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_pass_through_operations_preserve_lineage() -> None:
    report = analyze(
        f'''import ee
collection = ee.ImageCollection("{S1_GRD}")
prepared = (
    collection.filter(None)
    .filterBounds(None)
    .filterDate("2020-01-01", "2020-02-01")
    .select("VV")
)
image = prepared.first().clip(None).updateMask(None).copyProperties(None)
db = image.log10().multiply(10)
'''
    )
    assert codes(report) == ["EWL301"]


def test_rename_makes_band_mapping_unknown_but_keeps_lineage() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
renamed = img.select(["SR_B5", "SR_B4"]).rename(["nir", "red"])
ndvi = renamed.normalizedDifference()
'''
    )
    assert codes(report) == []


def test_unresolved_lineage_never_fabricates_a_dataset() -> None:
    report = analyze(
        """import ee
img = ee.Image(build_dataset_id())
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
db = img.log10().multiply(10)
"""
    )
    assert codes(report) == []
    assert report.coverage.unresolved_lineage_count >= 1


def test_dotted_earth_engine_import_binds_the_root_name() -> None:
    report = analyze(
        f'''import ee.batch
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_unrelated_module_ending_in_ee_is_not_earth_engine() -> None:
    report = analyze(
        f'''import coffee
img = coffee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_shadowing_the_ee_name_disables_recognition() -> None:
    report = analyze(
        f'''ee = load_helper()
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []
