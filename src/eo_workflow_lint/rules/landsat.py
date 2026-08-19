"""Landsat Collection 2 Level-2 rules: EWL201, EWL202, EWL203 (SPECIFICATION §10.1-§10.3)."""

from __future__ import annotations

from .. import catalog
from ..lineage import BandFamily, ImageState, ScaleState
from ..models import Finding
from . import build_finding, rule_meta

__all__ = ["check_normalized_difference", "check_scale_transform"]


def _all_sr_bands(bands: tuple[str, ...]) -> bool:
    return len(bands) == 2 and all(catalog.landsat_sr_band(name) for name in bands)


def check_normalized_difference(
    state: ImageState, bands: tuple[str, ...] | None, line: int, column: int
) -> Finding | None:
    """EWL201 / EWL203 decision for a ``normalizedDifference()`` call.

    ``bands`` is the statically proven two-band input, or ``None`` when band
    identity could not be proven.
    """
    if state.family != catalog.FAMILY_LANDSAT_C2_L2:
        return None
    if bands is None or not _all_sr_bands(bands):
        return None

    evidence = {
        "dataset_id": state.dataset_id,
        "bands": bands,
        "sr_scale_state": state.sr_scale.value,
    }

    if state.sr_scale is ScaleState.RAW:
        meta = rule_meta("EWL201")
        assert meta is not None
        return build_finding(meta, line, column, evidence)

    if state.sr_scale is ScaleState.CORRECTLY_SCALED:
        meta = rule_meta("EWL203")
        assert meta is not None
        return build_finding(meta, line, column, evidence)

    # ScaleState.UNKNOWN: not proven either way, emit nothing (SPECIFICATION §8.1).
    return None


def check_scale_transform(
    state: ImageState,
    scale: float,
    offset: float,
    line: int,
    column: int,
) -> Finding | None:
    """EWL202 decision for a completed ``multiply(scale).add(offset)`` chain.

    ``state`` is the state of the receiver the chain was applied to, so its
    ``band_family`` is the proven selection the transform targets.
    """
    if state.family != catalog.FAMILY_LANDSAT_C2_L2:
        return None

    constants = catalog.landsat_constants()
    is_sr_transform = scale == constants.sr_scale and offset == constants.sr_offset
    is_st_transform = scale == constants.st_scale and offset == constants.st_offset

    # Trigger A: documented SR transform applied to a proven ST band.
    if is_sr_transform and state.band_family is BandFamily.ST:
        expected = "SR"
    # Trigger B: documented ST transform applied to proven SR bands.
    elif is_st_transform and state.band_family is BandFamily.SR:
        expected = "ST"
    else:
        # Deliberately a cross-family mismatch detector, not a generic
        # "unexpected scale" detector (SPECIFICATION §10.2).
        return None

    meta = rule_meta("EWL202")
    assert meta is not None
    return build_finding(
        meta,
        line,
        column,
        {
            "dataset_id": state.dataset_id,
            "band_family": state.band_family.value,
            "applied_scale": scale,
            "applied_offset": offset,
            "expected_family_for_transform": expected,
        },
    )
