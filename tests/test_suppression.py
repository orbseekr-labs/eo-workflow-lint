"""Source-level suppression directives (SPECIFICATION §12)."""

from __future__ import annotations

from support import LC08_ASSET, analyze, codes

BASE = f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
'''


def test_directive_suppresses_the_following_line() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL201
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []
    assert report.verdict.value == "PASS"
    assert report.coverage.suppressed_finding_count == 1


def test_multiple_codes_may_be_comma_separated() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL203,EWL401
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
"""
    )
    assert codes(report) == []
    assert report.coverage.suppressed_finding_count == 1


def test_directive_does_not_suppress_other_codes() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL401
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]
    assert report.coverage.suppressed_finding_count == 0


def test_directive_does_not_suppress_a_later_line() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL201
x = 1
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]


def test_blank_line_breaks_the_directive_association() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL201

ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]


def test_malformed_directive_does_not_suppress() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]
    assert report.coverage.suppressed_finding_count == 0
    assert any("malformed" in warning for warning in report.warnings)


def test_malformed_directive_with_empty_code_list_does_not_suppress() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL201,
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]


def test_unknown_reason_code_warns_without_changing_the_verdict() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL999
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]
    assert report.verdict.value == "FAIL"
    assert any("EWL999" in warning for warning in report.warnings)


def test_unknown_code_alongside_a_known_code_still_suppresses_the_known_one() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL999,EWL201
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []
    assert report.coverage.suppressed_finding_count == 1


def test_directive_inside_a_string_literal_is_not_a_directive() -> None:
    report = analyze(
        BASE
        + """note = "# ewl: ignore-next-line=EWL201"
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == ["EWL201"]


def test_trailing_comment_directive_is_supported() -> None:
    report = analyze(
        BASE
        + """x = 1  # ewl: ignore-next-line=EWL201
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    assert codes(report) == []


def test_suppressed_findings_do_not_affect_the_exit_threshold() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL201
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
"""
    )
    fails, conditionals = report.counts()
    assert (fails, conditionals) == (0, 0)


def test_directive_suppresses_a_multi_line_call() -> None:
    report = analyze(
        BASE
        + """# ewl: ignore-next-line=EWL401
stats = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=aoi,
)
"""
    )
    assert codes(report) == []
    assert report.coverage.suppressed_finding_count == 1
