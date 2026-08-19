"""Sentinel-1 GRD rule: EWL301 (SPECIFICATION §10.4)."""

from __future__ import annotations

from ..lineage import Domain, LogPending
from ..models import Finding
from . import build_finding, rule_meta

__all__ = ["check_db_conversion"]

#: The Earth Engine collection that is already exposed in dB.
_S1_GRD_DB = "COPERNICUS/S1_GRD"


def check_db_conversion(
    pending: LogPending, pattern: str, line: int, column: int
) -> Finding | None:
    """EWL301 decision for a recognised explicit ``10*log10()`` conversion.

    ``pending`` carries the lineage and numeric domain observed at the input of
    the ``log10()`` call, which is where the specification requires the domain
    to be proven ``DB``.
    """
    if pending.dataset_id != _S1_GRD_DB:
        return None
    if pending.domain is not Domain.DB:
        return None

    meta = rule_meta("EWL301")
    assert meta is not None
    return build_finding(
        meta,
        line,
        column,
        {
            "dataset_id": pending.dataset_id,
            "numeric_domain": pending.domain.value,
            "conversion_pattern": pattern,
        },
    )
