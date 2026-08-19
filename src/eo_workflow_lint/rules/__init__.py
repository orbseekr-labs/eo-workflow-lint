"""Stable reason-code registry (SPECIFICATION §24) and rule metadata.

No reason code outside this registry may exist in v0.1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Severity

if TYPE_CHECKING:  # pragma: no cover
    from ..models import Finding

__all__ = ["RULES", "RULE_CODES", "RuleMeta", "build_finding", "rule_meta"]


@dataclass(frozen=True)
class RuleMeta:
    """Frozen, specification-derived description of one reason code."""

    code: str
    severity: Severity
    name: str
    intent: str
    trigger: tuple[str, ...]
    non_triggers: tuple[str, ...]
    message: str
    source_ids: tuple[str, ...]


RULES: tuple[RuleMeta, ...] = (
    RuleMeta(
        code="EWL201",
        severity=Severity.FAIL,
        name="LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE",
        intent=(
            "Detect normalized-difference computation over encoded Landsat Collection 2 "
            "Level-2 SR digital numbers before the documented additive offset has been applied."
        ),
        trigger=(
            "the receiver image is LANDSAT_C2_L2",
            "the two normalized-difference inputs are Landsat SR bands",
            "the relevant SR state is RAW",
            "the operation is normalizedDifference()",
            "the two input bands are statically known from the explicit argument "
            "or from an immediately known two-band receiver selection",
        ),
        non_triggers=(
            "SR scaling is proven correct and overwritten/applied before the operation",
            "product identity is unknown",
            "band identity is unknown",
            "expression() is used instead of normalizedDifference()",
            "the data are Landsat TOA rather than Collection 2 Level-2 SR",
            "the operation is on non-SR bands",
        ),
        message=(
            "Landsat Collection 2 Level-2 surface-reflectance bands are encoded with scale "
            "0.0000275 and additive offset -0.2. normalizedDifference() is being applied "
            "before the documented SR scaling is proven."
        ),
        source_ids=("SRC-GEE-LANDSAT-C1-C2", "SRC-USGS-LANDSAT-C2-SCALE"),
    ),
    RuleMeta(
        code="EWL202",
        severity=Severity.FAIL,
        name="LANDSAT_C2_BAND_SCALE_MISMATCH",
        intent=(
            "Detect application of the documented Landsat Collection 2 SR transform to a "
            "proven ST band, or the documented ST transform to proven SR bands."
        ),
        trigger=(
            "Trigger A: LANDSAT_C2_L2 receiver, proven ST band family, "
            "applied chain is exactly multiply(0.0000275).add(-0.2)",
            "Trigger B: LANDSAT_C2_L2 receiver, proven SR band family, "
            "applied chain is exactly multiply(0.00341802).add(149.0)",
        ),
        non_triggers=(
            "arbitrary other numeric arithmetic",
            "correct SR scaling on SR bands",
            "correct ST scaling on ST bands",
            "unknown band selection",
        ),
        message="A documented Landsat Collection 2 scale/offset pair is being applied to the wrong band family.",
        source_ids=("SRC-GEE-LANDSAT-C1-C2", "SRC-USGS-LANDSAT-C2-SCALE"),
    ),
    RuleMeta(
        code="EWL203",
        severity=Severity.CONDITIONAL,
        name="NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK",
        intent=(
            "Warn when correctly scaled Landsat Collection 2 SR values are passed to "
            "normalizedDifference(), because the Earth Engine API masks output pixels "
            "when either input value is negative."
        ),
        trigger=(
            "product is LANDSAT_C2_L2",
            "the two inputs are SR bands",
            "SR scaling state is CORRECTLY_SCALED",
            "operation is normalizedDifference()",
            "the relevant band identities are statically known",
        ),
        non_triggers=(
            "RAW Landsat SR; EWL201 covers that case",
            "expression() normalized-difference formulas",
            "scale state is unknown",
            "non-Landsat products in v0.1.0",
        ),
        message=(
            "ee.Image.normalizedDifference() masks a pixel when either input band is negative. "
            "Correctly scaled Landsat surface reflectance can contain negative physical values; "
            "review whether silent masking is acceptable or use expression() when negatives must be retained."
        ),
        source_ids=("SRC-GEE-NORMALIZED-DIFFERENCE", "SRC-USGS-LANDSAT-C2-SCALE"),
    ),
    RuleMeta(
        code="EWL301",
        severity=Severity.FAIL,
        name="SENTINEL1_GRD_REDUNDANT_DB_CONVERSION",
        intent=(
            "Detect an additional explicit 10*log10() conversion applied to Earth Engine "
            "COPERNICUS/S1_GRD, whose backscatter values are already exposed in dB."
        ),
        trigger=(
            "lineage is proven to originate from COPERNICUS/S1_GRD",
            "numeric domain at the conversion input is proven DB",
            "the analyzer recognizes one of the v0.1.0 explicit dB conversion forms",
        ),
        non_triggers=(
            "COPERNICUS/S1_GRD_FLOAT",
            "a standalone .log10()",
            "an unsupported arithmetic/nonlinear transformation made the domain UNKNOWN",
            "non-Sentinel-1 datasets",
        ),
        message=(
            "COPERNICUS/S1_GRD is already log-scaled in dB. A second explicit 10*log10() "
            "conversion is being applied. Use the dB values directly, or use "
            "COPERNICUS/S1_GRD_FLOAT when linear power is required."
        ),
        source_ids=("SRC-GEE-S1-GRD",),
    ),
    RuleMeta(
        code="EWL401",
        severity=Severity.CONDITIONAL,
        name="ANALYSIS_SCALE_UNSPECIFIED",
        intent="Warn when Earth Engine region reduction relies on implicit analysis scale/transform.",
        trigger=(
            "the call is reduceRegion() or reduceRegions()",
            "neither scale nor crsTransform is statically supplied with a non-None value",
        ),
        non_triggers=(
            "keyword scale=<non-None expression>",
            "keyword crsTransform=<non-None expression>",
            "positional non-None scale (third positional argument)",
            "positional non-None crsTransform (fifth positional argument)",
        ),
        message=(
            "Region reduction does not explicitly define scale or crsTransform. Earth Engine "
            "recommends explicitly defining analysis scale/transform to avoid unexpected "
            "results from defaults."
        ),
        source_ids=("SRC-GEE-REDUCE-REGION", "SRC-GEE-REDUCE-REGIONS"),
    ),
    RuleMeta(
        code="EWL501",
        severity=Severity.FAIL,
        name="SENTINEL2_QA60_UNAVAILABLE",
        intent=(
            "Detect a workflow that statically selects Sentinel-2 QA60 when its entire known "
            "analysis interval is inside the documented QA60 gap."
        ),
        trigger=(
            "lineage is one of the supported Sentinel-2 collections",
            "band QA60 is selected or directly referenced",
            "a closed-open requested interval [start, end) is statically known",
            "[start, end) is entirely contained within [2022-01-26, 2024-02-28)",
        ),
        non_triggers=(
            "the interval is not entirely inside the gap",
            "temporal scope cannot be statically proven",
            "non-QA60 bands",
            "non-Sentinel-2 datasets",
        ),
        message=(
            "The workflow relies on Sentinel-2 QA60 for a period entirely inside the documented "
            "QA60 availability gap (the conservative 2022-01-26 to 2024-02-28 interval in the "
            "v0.1 catalog)."
        ),
        source_ids=("SRC-GEE-S2-HARMONIZED", "SRC-GEE-S2-SR-HARMONIZED"),
    ),
    RuleMeta(
        code="EWL502",
        severity=Severity.CONDITIONAL,
        name="SENTINEL2_QA60_GAP_OVERLAP",
        intent=(
            "Warn when a statically known Sentinel-2 analysis interval overlaps the QA60 gap "
            "but is not entirely contained within it."
        ),
        trigger=(
            "supported Sentinel-2 lineage is proven",
            "QA60 use is proven",
            "[start, end) is statically known",
            "the interval intersects [2022-01-26, 2024-02-28)",
            "EWL501 does not apply",
        ),
        non_triggers=(
            "the interval is entirely inside the gap; EWL501 applies instead",
            "temporal scope cannot be proven; unresolved_temporal_scope_count is incremented instead",
            "non-QA60 bands",
            "non-Sentinel-2 datasets",
        ),
        message=(
            "The workflow relies on Sentinel-2 QA60 across a time range that overlaps the "
            "documented QA60 availability gap. Review temporal cloud-mask consistency."
        ),
        source_ids=("SRC-GEE-S2-HARMONIZED", "SRC-GEE-S2-SR-HARMONIZED"),
    ),
)

RULE_CODES: tuple[str, ...] = tuple(rule.code for rule in RULES)

_BY_CODE: dict[str, RuleMeta] = {rule.code: rule for rule in RULES}


def rule_meta(code: str) -> RuleMeta | None:
    return _BY_CODE.get(code)


def build_finding(meta: RuleMeta, line: int, column: int, evidence: dict[str, object]) -> Finding:
    """Construct a deterministic finding for ``meta`` (SPECIFICATION §5, §14)."""
    from ..models import Finding

    return Finding(
        code=meta.code,
        severity=meta.severity,
        name=meta.name,
        line=line,
        column=column,
        message=meta.message,
        source_ids=tuple(sorted(meta.source_ids)),
        evidence=tuple(evidence.items()),
    )
