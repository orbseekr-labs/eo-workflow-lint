"""Determinism requirements (SPECIFICATION §11 of the task brief, §14, §21.1)."""

from __future__ import annotations

from pathlib import Path

from eo_workflow_lint.serialization import to_json, to_text
from support import LC08_ASSET, S1_GRD, S2_SR, analyze, run_cli

WORKFLOW = f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
s1 = ee.ImageCollection("{S1_GRD}")
db = s1.first().log10().multiply(10)
s2 = ee.ImageCollection("{S2_SR}").filterDate("2021-01-01", "2025-01-01")
clean = s2.map(lambda image: image.select("QA60"))
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''


def test_repeated_analysis_produces_identical_json() -> None:
    outputs = {to_json(analyze(WORKFLOW)) for _ in range(20)}
    assert len(outputs) == 1


def test_repeated_analysis_produces_identical_text() -> None:
    outputs = {to_text(analyze(WORKFLOW), "workflow.py") for _ in range(20)}
    assert len(outputs) == 1


def test_identical_bytes_in_different_directories_produce_identical_json(tmp_path: Path) -> None:
    first_dir = tmp_path / "alpha"
    second_dir = tmp_path / "beta" / "nested"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)

    first = first_dir / "workflow.py"
    second = second_dir / "different_name.py"
    first.write_bytes(WORKFLOW.encode("utf-8"))
    second.write_bytes(WORKFLOW.encode("utf-8"))

    _, first_out, _ = run_cli(["check", str(first), "--format", "json"])
    _, second_out, _ = run_cli(["check", str(second), "--format", "json"])
    assert first_out == second_out


def test_cli_json_is_byte_identical_across_runs(tmp_path: Path) -> None:
    target = tmp_path / "workflow.py"
    target.write_bytes(WORKFLOW.encode("utf-8"))
    outputs = {run_cli(["check", str(target), "--format", "json"])[1] for _ in range(10)}
    assert len(outputs) == 1


def test_finding_order_is_stable_regardless_of_dict_ordering() -> None:
    first = [f.dedup_key for f in analyze(WORKFLOW).findings]
    second = [f.dedup_key for f in analyze(WORKFLOW).findings]
    assert first == second
