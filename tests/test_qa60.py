"""EWL501 / EWL502 — Sentinel-2 QA60 temporal rules (SPECIFICATION §10.6, §10.7, §21.7)."""

from __future__ import annotations

import pytest

from support import LC08_ASSET, S2_SR, analyze, codes

SUPPORTED_S2 = [
    "COPERNICUS/S2",
    "COPERNICUS/S2_HARMONIZED",
    "COPERNICUS/S2_SR",
    "COPERNICUS/S2_SR_HARMONIZED",
]


def qa60_workflow(dataset: str, start: str, end: str) -> str:
    return f'''import ee
s2 = ee.ImageCollection("{dataset}").filterDate("{start}", "{end}")

def mask_clouds(image):
    qa = image.select("QA60")
    return image.updateMask(qa.eq(0))

clean = s2.map(mask_clouds)
'''


def test_ewl501_interval_fully_inside_gap() -> None:
    report = analyze(qa60_workflow(S2_SR, "2023-01-01", "2024-01-01"))
    assert codes(report) == ["EWL501"]
    evidence = report.findings[0].evidence_dict()
    assert evidence["dataset_id"] == S2_SR
    assert evidence["requested_start"] == "2023-01-01"
    assert evidence["requested_end"] == "2024-01-01"
    assert evidence["qa60_gap_start"] == "2022-01-26"
    assert evidence["qa60_gap_end"] == "2024-02-28"


def test_ewl501_through_inline_select_without_map() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
qa = s2.first().select("QA60")
'''
    )
    assert codes(report) == ["EWL501"]


def test_ewl501_through_mapped_lambda() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == ["EWL501"]


@pytest.mark.parametrize("dataset", SUPPORTED_S2)
def test_all_supported_sentinel2_collections(dataset: str) -> None:
    report = analyze(qa60_workflow(dataset, "2023-01-01", "2023-06-01"))
    assert codes(report) == ["EWL501"]


def test_ewl502_starts_before_gap_ends_inside() -> None:
    report = analyze(qa60_workflow(S2_SR, "2021-06-01", "2023-01-01"))
    assert codes(report) == ["EWL502"]


def test_ewl502_starts_inside_gap_ends_after() -> None:
    report = analyze(qa60_workflow(S2_SR, "2023-01-01", "2025-01-01"))
    assert codes(report) == ["EWL502"]


def test_ewl502_spans_the_entire_gap() -> None:
    report = analyze(qa60_workflow(S2_SR, "2021-01-01", "2025-01-01"))
    assert codes(report) == ["EWL502"]


def test_negative_interval_entirely_before_gap() -> None:
    report = analyze(qa60_workflow(S2_SR, "2019-01-01", "2020-01-01"))
    assert codes(report) == []


def test_negative_interval_entirely_after_gap() -> None:
    report = analyze(qa60_workflow(S2_SR, "2024-03-01", "2025-01-01"))
    assert codes(report) == []


# Boundary matrix around the two normative cutoffs: 2022-01-26 and 2024-02-28.
# The interval model is closed-open, [start, end).
@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # Immediately before the gap start.
        ("2022-01-24", "2022-01-25", []),
        ("2022-01-25", "2022-01-26", []),  # ends exactly at the exclusive gap start
        ("2022-01-25", "2022-01-27", ["EWL502"]),
        # Exactly at the gap start.
        ("2022-01-26", "2022-01-27", ["EWL501"]),
        ("2022-01-26", "2024-02-28", ["EWL501"]),  # exactly the whole gap
        ("2022-01-26", "2024-03-01", ["EWL502"]),
        # Immediately before the gap end.
        ("2024-02-26", "2024-02-27", ["EWL501"]),
        ("2024-02-27", "2024-02-28", ["EWL501"]),
        ("2024-02-27", "2024-02-29", ["EWL502"]),
        # Exactly at and after the gap end.
        ("2024-02-28", "2024-03-01", []),
        ("2024-02-29", "2024-03-01", []),
    ],
)
def test_temporal_boundaries(start: str, end: str, expected: list[str]) -> None:
    report = analyze(qa60_workflow(S2_SR, start, end))
    assert codes(report) == expected


def test_datetime_forms_are_accepted() -> None:
    report = analyze(qa60_workflow(S2_SR, "2023-01-01T00:00:00Z", "2023-06-01T00:00:00"))
    assert codes(report) == ["EWL501"]


def test_sub_day_precision_is_preserved_at_the_boundary() -> None:
    """An interval ending after midnight on the gap end date is only an overlap."""
    report = analyze(qa60_workflow(S2_SR, "2024-02-27", "2024-02-28T12:00:00Z"))
    assert codes(report) == ["EWL502"]


def test_negative_non_qa60_band() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
clean = s2.map(lambda image: image.select("B4"))
'''
    )
    assert codes(report) == []


def test_negative_non_sentinel2_dataset() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
qa = img.select("QA60")
'''
    )
    assert codes(report) == []


def test_unknown_temporal_scope_produces_coverage_not_a_finding() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}")
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == []
    assert report.coverage.unresolved_temporal_scope_count == 1


def test_single_argument_filter_date_leaves_temporal_scope_unresolved() -> None:
    """SPECIFICATION §8.8 — a single-argument filterDate is outside v0.1.0 temporal reasoning."""
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01")
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == []
    assert report.coverage.unresolved_temporal_scope_count == 1


def test_dynamic_filter_date_leaves_temporal_scope_unresolved() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate(start_date, end_date)
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == []
    assert report.coverage.unresolved_temporal_scope_count == 1


def test_chained_filter_date_intersects_intervals() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2021-01-01", "2025-01-01").filterDate("2023-01-01", "2023-06-01")
clean = s2.map(lambda image: image.select("QA60"))
'''
    )
    assert codes(report) == ["EWL501"]


def test_qa60_inside_a_selection_list() -> None:
    report = analyze(
        f'''import ee
s2 = ee.ImageCollection("{S2_SR}").filterDate("2023-01-01", "2023-06-01")
bands = s2.first().select(["B4", "QA60"])
'''
    )
    assert codes(report) == ["EWL501"]
