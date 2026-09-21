"""EWL203 — NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK (SPECIFICATION §10.3, §21.4)."""

from __future__ import annotations

import json

from eo_workflow_lint.rules import RULES, rule_meta
from eo_workflow_lint.serialization import MAX_HINT_LINES, to_json, to_text
from support import LC08_ASSET, LC08_COLLECTION, S1_GRD, analyze, codes, run_cli


def test_correctly_scaled_and_overwritten_then_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]
    assert report.findings[0].evidence_dict()["sr_scale_state"] == "CORRECTLY_SCALED"


def test_positional_overwrite_form_is_recognised() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
optical = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(optical, None, True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]


def test_correctly_scaled_two_band_selection_then_normalized_difference() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
scaled = img.select(["SR_B5", "SR_B4"]).multiply(0.0000275).add(-0.2)
ndvi = scaled.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]


def test_negative_raw_surface_reflectance_reports_ewl201_only() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_negative_expression_form() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
nir = img.select("SR_B5")
red = img.select("SR_B4")
ndvi = img.expression("(nir - red) / (nir + red)", {{"nir": nir, "red": red}})
'''
    )
    assert codes(report) == []


def test_negative_unknown_scale_state() -> None:
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
transformed = img.pow(2)
ndvi = transformed.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == []


def test_negative_overwrite_not_proven_leaves_original_state() -> None:
    """SPECIFICATION §9.4 — without proven overwrite the original state is not replaced."""
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201"]


def test_negative_non_landsat_product() -> None:
    report = analyze(
        f'''import ee
s1 = ee.ImageCollection("{S1_GRD}")
ndvi = s1.first().normalizedDifference(["VV", "VH"])
'''
    )
    assert codes(report) == []


# --------------------------------------------------------------------------
# EWL203 v2: actionable scientific-choice framing (SPECIFICATION v0.1.1 §10.3)
# --------------------------------------------------------------------------

SCALED_SOURCE = f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''


def test_severity_remains_conditional() -> None:
    report = analyze(SCALED_SOURCE)
    assert codes(report) == ["EWL203"]
    assert report.findings[0].severity.value == "CONDITIONAL"
    assert report.verdict.value == "CONDITIONAL"


def test_message_frames_an_explicit_scientific_choice() -> None:
    message = rule_meta("EWL203").message
    # What happens.
    assert "masks output pixels when either input band is negative" in message
    # Why it matters.
    assert "silently change which pixels contribute" in message
    # Conditional framing: the decision is the user's.
    assert "scientific/workflow choice" in message
    assert "should be explicit" in message
    # Both branches are named; neither is mandated.
    assert "Keep normalizedDifference() if this masking is intentional" in message
    assert "explicit expression" in message
    assert "explain EWL203" in message


def test_message_does_not_overclaim() -> None:
    lowered = rule_meta("EWL203").message.lower()
    for forbidden in (
        "is wrong",
        "incorrect result",
        "always",
        "must be retained",
        "must preserve",
    ):
        assert forbidden not in lowered


def test_remediation_communicates_the_four_ideas() -> None:
    meta = rule_meta("EWL203")
    assert meta.remediation
    joined = " ".join(meta.remediation).lower()
    # A. keeping normalizedDifference() is acceptable when intentional.
    assert "keeping normalizeddifference() is acceptable" in joined
    assert "suppress ewl203" in joined
    # B. explicit expression when retaining negatives.
    assert "ee.image.expression()" in joined
    # C. deliberate denominator handling.
    assert "near-zero denominator" in joined
    # D. preserve existing masks; no unmask() workaround.
    assert "existing input masks are preserved" in joined
    assert "do not unmask()" in joined


def test_only_ewl203_carries_remediation_in_this_pass() -> None:
    with_remediation = {meta.code for meta in RULES if meta.remediation}
    assert with_remediation == {"EWL203"}
    for meta in RULES:
        if meta.code != "EWL203":
            assert meta.remediation == ()
            assert meta.remediation_example == ""


def test_explain_renders_remediation_section_with_guarded_example() -> None:
    code, out, _ = run_cli(["explain", "EWL203"])
    assert code == 0
    assert "\nremediation:\n" in out
    # The remediation section sits between the message and the sources.
    assert out.index("message:") < out.index("remediation:") < out.index("sources:")
    # Expression-based alternative on correctly scaled inputs.
    assert ".multiply(0.0000275).add(-0.2)" in out
    assert ".expression(" in out
    # Explicit denominator variable, configurable guard, framed as a workflow choice.
    assert "denominator = nir.add(red)" in out
    assert "DENOMINATOR_EPSILON" in out
    assert "workflow choice" in out
    # Mask preservation through updateMask(), and no unmask() workaround.
    assert ".updateMask(denominator.abs().gte(DENOMINATOR_EPSILON))" in out
    assert "unmask()" in out and ".unmask(" not in out
    # No undocumented division-by-zero claim.
    assert "division by zero" not in out.lower()
    assert "returns 0" not in out.lower()


def test_explain_for_rules_without_remediation_has_no_section() -> None:
    for code in ("EWL201", "EWL202", "EWL301", "EWL401", "EWL501", "EWL502"):
        exit_code, out, _ = run_cli(["explain", code])
        assert exit_code == 0
        assert "remediation:" not in out


def test_check_text_output_includes_concise_hints_only() -> None:
    text = to_text(analyze(SCALED_SOURCE))
    hint_lines = [line for line in text.splitlines() if line.startswith("hint: ")]
    assert 1 <= len(hint_lines) <= MAX_HINT_LINES <= 3
    joined = " ".join(hint_lines).lower()
    assert "intentional" in joined
    assert "expression()" in joined and "denominator" in joined
    assert "existing input masks are preserved" in joined
    # The full example is reserved for ``explain``; hints follow the source line.
    assert "DENOMINATOR_EPSILON" not in text
    assert text.index("source: ") < text.index("hint: ")


def test_rules_without_remediation_gain_no_hint_lines() -> None:
    report = analyze(
        f'''import ee
aoi = ee.Geometry.Point(0, 0)
img = ee.Image("{LC08_ASSET}")
stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL201", "EWL401"]
    text = to_text(report)
    assert "hint:" not in text
    # Each finding still renders as exactly the three pre-v2 lines.
    block = text.split("\n\n")[1:3]
    assert all(len(part.splitlines()) == 3 for part in block)


def test_json_finding_schema_is_unchanged() -> None:
    payload = json.loads(to_json(analyze(SCALED_SOURCE)))
    finding = payload["findings"][0]
    assert list(finding) == [
        "code",
        "severity",
        "name",
        "line",
        "column",
        "message",
        "source_ids",
        "evidence",
    ]
    assert "remediation" not in json.dumps(payload)
    assert "hint" not in json.dumps(payload)
    assert list(finding["evidence"]) == ["dataset_id", "bands", "sr_scale_state"]


def test_practitioner_map_scale_then_map_normalized_difference() -> None:
    """The collection form reported by a Landsat practitioner is covered."""
    report = analyze(
        f'''import ee

def apply_scale_factors(image):
    optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
    return image.addBands(optical, None, True)

collection = ee.ImageCollection("{LC08_COLLECTION}").map(apply_scale_factors)
ndvi = collection.map(lambda image: image.normalizedDifference(["SR_B5", "SR_B4"]))
'''
    )
    assert codes(report) == ["EWL203"]
    assert report.findings[0].line == 8


def test_explicit_upstream_negative_masking_still_fires() -> None:
    """Documented conservative behaviour, not a defect.

    ``updateMask()`` is a lineage pass-through (SPECIFICATION §8.5) and the
    analyzer does not interpret the mask predicate, so it cannot prove that
    negative inputs were already excluded on purpose. Under §8.1 the rule keeps
    firing; the CONDITIONAL severity and the "keep it if intentional" hint make
    that acceptable, and the author can suppress the call site (§12).
    """
    report = analyze(
        f'''import ee
img = ee.Image("{LC08_ASSET}")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
img = img.updateMask(img.select("SR_B5").gte(0)).updateMask(img.select("SR_B4").gte(0))
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
'''
    )
    assert codes(report) == ["EWL203"]
    assert report.findings[0].line == 6


def test_guarded_expression_alternative_does_not_trigger() -> None:
    """The remediation example itself is clean under every v0.1 rule."""
    example = "import ee\n" + rule_meta("EWL203").remediation_example
    report = analyze(example)
    assert codes(report) == []
    assert report.verdict.value == "PASS"
