"""Offline checks for the real-world validation benchmark (validation/).

The live benchmark needs network access and is a manual developer command
(``python validation/run_benchmark.py``). These tests never fetch anything:
they validate the manifest's structure and the runner's classification logic.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from eo_workflow_lint.rules import RULE_CODES

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "validation" / "manifest.json"
RUNNER = REPO_ROOT / "validation" / "run_benchmark.py"

SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip("validation/manifest.json is not present in this checkout")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runner():
    if not RUNNER.exists():
        pytest.skip("validation/run_benchmark.py is not present in this checkout")
    spec = importlib.util.spec_from_file_location("ewl_run_benchmark", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_cases_are_pinned_and_well_formed(manifest: dict) -> None:
    ids = [case["id"] for case in manifest["cases"]]
    assert len(ids) == len(set(ids))
    for case in manifest["cases"]:
        assert REPO.match(case["repo"]), case["id"]
        assert SHA1.match(case["commit"]), f"{case['id']}: commit must be a full 40-hex SHA"
        assert case["role"] in {"candidate", "control", "sweep"}
        assert case["human_review_note"].strip()
        for spec in case.get("files", []):
            assert SHA256.match(spec["sha256"]), f"{case['id']}: {spec['path']}"
            assert not spec["path"].startswith("/") and ".." not in spec["path"]
            for target in spec["expected"]:
                assert target["code"] in RULE_CODES
                assert isinstance(target["line"], int) and target["line"] > 0
                assert target["static_scope"] in {"in", "out"}
                if target["static_scope"] == "out":
                    assert target["scope_gap"].strip()
        for finding in case.get("adjudicated_findings", []):
            assert finding["code"] in RULE_CODES
            assert finding["label"] in {"true_positive", "false_positive"}
            assert finding["note"].strip()


def test_candidates_have_targets_and_controls_expect_nothing(manifest: dict) -> None:
    for case in manifest["cases"]:
        targets = [t for f in case.get("files", []) for t in f["expected"]]
        if case["role"] == "candidate":
            assert targets, case["id"]
        else:
            assert targets == [], case["id"]


def test_original_benchmark_is_preserved(manifest: dict) -> None:
    """The eight v0.2.0 release-note candidates and the Open-ET control stay pinned."""
    original = {c["repo"]: c for c in manifest["cases"] if c["group"] == "original-2026-09-22"}
    assert len(original) == 9
    assert sum(c["role"] == "candidate" for c in original.values()) == 8
    assert original["Open-ET/openet-core"]["role"] == "control"


def test_manifest_holds_no_source_code_or_local_paths(manifest: dict) -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    assert "import ee" not in text
    assert "/Users/" not in text and "/home/" not in text
    assert "@" not in text.replace("@v", ""), "no e-mail addresses"


def _file_result(runner, findings, verdict="CONDITIONAL"):
    return runner.FileResult("x.py", 0, verdict, findings)


def test_classification_buckets(runner) -> None:
    entry = {
        "files": [
            {
                "path": "a.py",
                "expected": [
                    {"code": "EWL203", "line": 10, "static_scope": "in"},
                    {"code": "EWL203", "line": 20, "static_scope": "in"},
                    {"code": "EWL203", "line": 30, "static_scope": "out", "scope_gap": "x"},
                ],
            }
        ],
        "adjudicated_findings": [
            {"path": "a.py", "code": "EWL401", "line": 5, "label": "false_positive"},
            {"path": "a.py", "code": "EWL201", "line": 6, "label": "true_positive"},
        ],
    }
    result = runner.classify(
        entry,
        "a.py",
        _file_result(runner, [("EWL203", 10), ("EWL401", 5), ("EWL201", 6), ("EWL502", 7)]),
    )
    assert result["detected"] == [["EWL203", 10]]
    assert result["missed_in_scope"] == [["EWL203", 20]]
    assert result["missed_out_of_scope"] == [["EWL203", 30]]
    assert result["false_positive"] == [["EWL401", 5]]
    assert result["true_positive"] == [["EWL201", 6]]
    assert result["unadjudicated"] == [["EWL502", 7]]


def test_unexpected_invalid_input_needs_review(runner) -> None:
    entry = {"not_analyzable": [{"path": "known.py", "note": "IPython magic"}]}
    known = runner.classify(entry, "known.py", _file_result(runner, [], verdict=None))
    other = runner.classify(entry, "other.py", _file_result(runner, [], verdict=None))
    assert known["unadjudicated"] == []
    assert other["unadjudicated"] == [["NOT_ANALYZABLE", 0]]


def test_candidate_counts_distinguish_bugs_from_coverage_gaps(runner) -> None:
    cases = [
        {"id": "hit", "role": "candidate"},
        {"id": "gap", "role": "candidate"},
        {"id": "bug", "role": "candidate"},
        {"id": "ctl", "role": "control"},
    ]

    def row(**buckets):
        base = {
            "verdict": "PASS",
            "detected": [],
            "missed_in_scope": [],
            "missed_out_of_scope": [],
            "true_positive": [],
            "false_positive": [],
            "unadjudicated": [],
        }
        base.update(buckets)
        return [base]

    summary = runner.summarize(
        cases,
        {
            "hit": row(detected=[["EWL203", 1]]),
            "gap": row(missed_out_of_scope=[["EWL203", 1]]),
            "bug": row(missed_in_scope=[["EWL203", 1]]),
            "ctl": row(false_positive=[["EWL401", 2]]),
        },
    )
    assert summary["candidate_cases"] == 3
    assert summary["candidate_cases_detected"] == 1
    assert summary["candidate_cases_missed"] == 2
    assert summary["candidate_cases_missed_coverage_unresolved"] == 1
    assert summary["target_sites_missed_in_scope"] == 1
    assert summary["control_findings_false_positive"] == 1
