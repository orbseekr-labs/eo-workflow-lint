"""Sentinel-2 QA60 temporal rules: EWL501, EWL502 (SPECIFICATION §10.6-§10.7)."""

from __future__ import annotations

from .. import catalog
from ..lineage import ImageState
from ..models import Finding
from ..temporal import contains, format_instant, intersects
from . import build_finding, rule_meta

__all__ = ["check_qa60_use"]


def check_qa60_use(state: ImageState, line: int, column: int) -> tuple[Finding | None, bool]:
    """EWL501 / EWL502 decision for a proven Sentinel-2 QA60 use.

    Returns ``(finding, temporal_unresolved)``. When the requested interval
    cannot be statically proven, no finding is emitted and the caller must
    increment ``unresolved_temporal_scope_count`` instead (SPECIFICATION §10.7).
    """
    if state.family != catalog.FAMILY_SENTINEL2:
        return None, False

    if state.interval is None:
        return None, True

    gap = catalog.qa60_gap()
    evidence = {
        "dataset_id": state.dataset_id,
        "requested_start": format_instant(state.interval[0]),
        "requested_end": format_instant(state.interval[1]),
        "qa60_gap_start": format_instant(gap[0]),
        "qa60_gap_end": format_instant(gap[1]),
    }

    # EWL501 wins over EWL502 when the interval is fully inside the gap.
    if contains(state.interval, gap):
        meta = rule_meta("EWL501")
        assert meta is not None
        return build_finding(meta, line, column, evidence), False

    if intersects(state.interval, gap):
        meta = rule_meta("EWL502")
        assert meta is not None
        return build_finding(meta, line, column, evidence), False

    return None, False
