"""Earth Engine analysis-scale rule: EWL401 (SPECIFICATION §10.5)."""

from __future__ import annotations

from ..models import Finding
from . import build_finding, rule_meta

__all__ = ["SUPPORTED_REDUCTIONS", "check_region_reduction"]

#: Region-reduction calls covered by v0.1.0.
SUPPORTED_REDUCTIONS = ("reduceRegion", "reduceRegions")


def check_region_reduction(
    operation: str,
    scale_explicit: bool,
    crs_transform_explicit: bool,
    line: int,
    column: int,
) -> Finding | None:
    """EWL401 checks explicitness, never whether a supplied scale is appropriate."""
    if scale_explicit or crs_transform_explicit:
        return None

    meta = rule_meta("EWL401")
    assert meta is not None
    return build_finding(
        meta,
        line,
        column,
        {
            "operation": operation,
            "scale_explicit": scale_explicit,
            "crs_transform_explicit": crs_transform_explicit,
        },
    )
