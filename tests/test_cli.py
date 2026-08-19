"""CLI contract: commands, options, and exit codes (SPECIFICATION §17, §18)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eo_workflow_lint.cli import MAX_INPUT_BYTES
from support import LC08_ASSET, analyze, run_cli

FAIL_SOURCE = f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''

CONDITIONAL_SOURCE = f'''import ee
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=None)
'''

PASS_SOURCE = 'import ee\nimg = ee.Image("UNKNOWN/PRODUCT")\n'


def write(tmp_path: Path, source: str, name: str = "workflow.py") -> str:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return str(target)


def test_check_pass_exits_zero(tmp_path: Path) -> None:
    code, out, err = run_cli(["check", write(tmp_path, PASS_SOURCE)])
    assert code == 0
    assert out.startswith("PASS\n")
    assert err == ""


def test_check_fail_exits_one(tmp_path: Path) -> None:
    code, out, _ = run_cli(["check", write(tmp_path, FAIL_SOURCE)])
    assert code == 1
    assert out.startswith("FAIL\n")


def test_conditional_exits_zero_with_default_threshold(tmp_path: Path) -> None:
    code, out, _ = run_cli(["check", write(tmp_path, CONDITIONAL_SOURCE)])
    assert code == 0
    assert out.startswith("CONDITIONAL\n")


def test_conditional_exits_one_with_fail_on_conditional(tmp_path: Path) -> None:
    code, _, _ = run_cli(["check", write(tmp_path, CONDITIONAL_SOURCE), "--fail-on", "conditional"])
    assert code == 1


def test_pass_exits_zero_with_fail_on_conditional(tmp_path: Path) -> None:
    code, _, _ = run_cli(["check", write(tmp_path, PASS_SOURCE), "--fail-on", "conditional"])
    assert code == 0


def test_fail_exits_one_with_fail_on_conditional(tmp_path: Path) -> None:
    code, _, _ = run_cli(["check", write(tmp_path, FAIL_SOURCE), "--fail-on", "conditional"])
    assert code == 1


def test_suppressed_finding_does_not_reach_the_threshold(tmp_path: Path) -> None:
    source = f'''import ee
img = ee.Image("{LC08_ASSET}")
# ewl: ignore-next-line=EWL201
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    code, out, _ = run_cli(["check", write(tmp_path, source), "--fail-on", "conditional"])
    assert code == 0
    assert out.startswith("PASS\n")


def test_json_format(tmp_path: Path) -> None:
    code, out, _ = run_cli(["check", write(tmp_path, FAIL_SOURCE), "--format", "json"])
    assert code == 1
    payload = json.loads(out)
    assert payload["verdict"] == "FAIL"
    assert payload["findings"][0]["code"] == "EWL201"


def test_missing_file_exits_two(tmp_path: Path) -> None:
    code, out, err = run_cli(["check", str(tmp_path / "absent.py")])
    assert code == 2
    assert out == ""
    assert "no such file" in err


def test_directory_argument_exits_two(tmp_path: Path) -> None:
    code, _, err = run_cli(["check", str(tmp_path)])
    assert code == 2
    assert "not a regular file" in err


def test_unsupported_extension_exits_two(tmp_path: Path) -> None:
    target = tmp_path / "workflow.js"
    target.write_text("var x = 1;\n", encoding="utf-8")
    code, _, err = run_cli(["check", str(target)])
    assert code == 2
    assert "unsupported file extension" in err


def test_syntax_error_exits_two(tmp_path: Path) -> None:
    code, out, err = run_cli(["check", write(tmp_path, "def broken(:\n")])
    assert code == 2
    assert out == ""
    assert "syntax error" in err


def test_invalid_utf8_exits_two(tmp_path: Path) -> None:
    target = tmp_path / "workflow.py"
    target.write_bytes(b'x = "\xff\xfe"\n')
    code, _, err = run_cli(["check", str(target)])
    assert code == 2
    assert "UTF-8" in err


def test_oversized_file_exits_two(tmp_path: Path) -> None:
    target = tmp_path / "big.py"
    target.write_bytes(b"# padding\n" * ((MAX_INPUT_BYTES // 10) + 1))
    assert target.stat().st_size > MAX_INPUT_BYTES
    code, _, err = run_cli(["check", str(target)])
    assert code == 2
    assert "limit" in err


def test_file_at_the_size_limit_is_accepted(tmp_path: Path) -> None:
    target = tmp_path / "boundary.py"
    target.write_bytes(b"#" + b"x" * (MAX_INPUT_BYTES - 2) + b"\n")
    assert target.stat().st_size == MAX_INPUT_BYTES
    code, out, _ = run_cli(["check", str(target)])
    assert code == 0
    assert out.startswith("PASS\n")


def test_internal_failure_exits_three(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import eo_workflow_lint.cli as cli_module

    def boom(_data: bytes):
        raise RuntimeError("synthetic analyzer failure")

    monkeypatch.setattr(cli_module, "analyze_source", boom)
    code, out, err = run_cli(["check", write(tmp_path, PASS_SOURCE)])
    assert code == 3
    assert out == ""
    assert "internal error" in err


def test_rules_command_lists_every_reason_code() -> None:
    code, out, _ = run_cli(["rules"])
    assert code == 0
    for reason in ("EWL201", "EWL202", "EWL203", "EWL301", "EWL401", "EWL501", "EWL502"):
        assert reason in out
    assert "EWL999" not in out


def test_explain_command() -> None:
    code, out, _ = run_cli(["explain", "EWL301"])
    assert code == 0
    assert "SENTINEL1_GRD_REDUNDANT_DB_CONVERSION" in out
    assert "severity: FAIL" in out
    assert "SRC-GEE-S1-GRD" in out
    assert "developers.google.com" in out


def test_explain_unknown_code_exits_two() -> None:
    code, out, err = run_cli(["explain", "EWL999"])
    assert code == 2
    assert out == ""
    assert "unknown reason code" in err


def test_sources_command_lists_the_registry() -> None:
    code, out, _ = run_cli(["sources"])
    assert code == 0
    assert "catalog version: 2026-08-19.1" in out
    for source_id in (
        "SRC-GEE-LANDSAT-C1-C2",
        "SRC-GEE-NORMALIZED-DIFFERENCE",
        "SRC-GEE-REDUCE-REGION",
        "SRC-GEE-REDUCE-REGIONS",
        "SRC-GEE-S1-GRD",
        "SRC-GEE-S2-HARMONIZED",
        "SRC-GEE-S2-SR-HARMONIZED",
        "SRC-USGS-LANDSAT-C2-SCALE",
    ):
        assert source_id in out


def test_invalid_option_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run_cli(["check", write(tmp_path, PASS_SOURCE), "--format", "yaml"])
    assert excinfo.value.code == 2


def test_missing_command_exits_two() -> None:
    with pytest.raises(SystemExit) as excinfo:
        run_cli([])
    assert excinfo.value.code == 2


def test_unknown_command_exits_two() -> None:
    with pytest.raises(SystemExit) as excinfo:
        run_cli(["lint", "x.py"])
    assert excinfo.value.code == 2


def test_suppression_warning_goes_to_stderr_not_stdout(tmp_path: Path) -> None:
    source = f'''import ee
img = ee.Image("{LC08_ASSET}")
# ewl: ignore-next-line=EWL999
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    code, out, err = run_cli(["check", write(tmp_path, source), "--format", "json"])
    assert code == 1
    assert "EWL999" in err
    json.loads(out)


def test_text_and_json_agree_on_the_verdict(tmp_path: Path) -> None:
    target = write(tmp_path, FAIL_SOURCE)
    _, text_out, _ = run_cli(["check", target])
    _, json_out, _ = run_cli(["check", target, "--format", "json"])
    assert text_out.startswith(json.loads(json_out)["verdict"])
    assert analyze(FAIL_SOURCE).verdict.value == json.loads(json_out)["verdict"]
