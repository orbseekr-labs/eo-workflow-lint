"""Landsat Collection 2 Level-2 rules: EWL201, EWL202, EWL203 (SPECIFICATION §10.1-§10.3)."""

from __future__ import annotations

from .. import catalog
from ..lineage import BandFamily, ImageState, ScaleState
from ..models import Finding
from . import build_finding, rule_meta

__all__ = ["check_normalized_difference", "check_scale_transform"]


def _every_reading_is_an_sr_pair(arguments: tuple[tuple[str, ...], ...]) -> bool:
    """True when every cross-product reading is a two-band proven SR pair."""
    return len(arguments) == 2 and all(
        catalog.landsat_sr_band(name) for options in arguments for name in options
    )


def check_normalized_difference(
    state: ImageState,
    arguments: tuple[tuple[str, ...], ...] | None,
    line: int,
    column: int,
) -> Finding | None:
    """EWL201 / EWL203 decision for a ``normalizedDifference()`` call.

    ``arguments`` gives the possible values of each band argument: a single name
    per argument for an ordinary literal pair, or the finite alternative set
    proven from merged branches (SPECIFICATION v0.2.0 §8.10.1). It is ``None``
    when band identity could not be proven.

    A finding is emitted only if *every* cross-product reading is a two-band
    proven SR pair, so the rule never fires on an unproven reading. Branch
    correlation between the two arguments is not tracked, which is why the
    evidence reports the per-argument possibilities rather than pairs it cannot
    prove are reachable.
    """
    if state.family != catalog.FAMILY_LANDSAT_C2_L2:
        return None
    if not arguments or not _every_reading_is_an_sr_pair(arguments):
        return None

    evidence: dict[str, object] = {"dataset_id": state.dataset_id}
    if all(len(options) == 1 for options in arguments):
        evidence["bands"] = tuple(options[0] for options in arguments)
    else:
        # Never both keys: the evidence states exactly what was proven (§10.1, §10.3).
        evidence["band_argument_alternatives"] = tuple(
            tuple(sorted(options)) for options in arguments
        )
    evidence["sr_scale_state"] = state.sr_scale.value

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
