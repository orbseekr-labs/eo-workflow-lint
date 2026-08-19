"""Abstract image state and lineage value model (SPECIFICATION §8).

The model is deliberately conservative: whenever a property cannot be proven it
degrades to UNKNOWN so that rules requiring that property do not fire.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from . import catalog

__all__ = [
    "PASS_THROUGH_METHODS",
    "UNKNOWN_VALUE",
    "BandFamily",
    "ConstValue",
    "Domain",
    "ImageState",
    "ImageValue",
    "LogPending",
    "ScaleState",
    "UnknownValue",
    "Value",
    "classify_bands",
    "intersect_intervals",
    "merge_envs",
    "merge_states",
    "merge_values",
]


class ScaleState(StrEnum):
    """Landsat Collection 2 scale state (SPECIFICATION §8.2)."""

    RAW = "RAW"
    CORRECTLY_SCALED = "CORRECTLY_SCALED"
    UNKNOWN = "UNKNOWN"


class Domain(StrEnum):
    """Sentinel-1 numeric domain (SPECIFICATION §8.2)."""

    DB = "DB"
    LINEAR_POWER = "LINEAR_POWER"
    UNKNOWN = "UNKNOWN"


class BandFamily(StrEnum):
    """Semantic band family of a proven selection."""

    SR = "SR"
    ST = "ST"
    QA = "QA"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


#: Operations that preserve recognised dataset lineage (SPECIFICATION §8.5).
PASS_THROUGH_METHODS = frozenset(
    {
        "filterDate",
        "filter",
        "filterBounds",
        "select",
        "clip",
        "updateMask",
        "mask",
        "rename",
        "copyProperties",
    }
)


@dataclass(frozen=True)
class LogPending:
    """Records the numeric domain observed at the input of a ``.log10()`` call.

    EWL301 requires the domain *at the conversion input* to be proven DB
    (SPECIFICATION §10.4), so it is captured when ``log10()`` is applied rather
    than re-read afterwards.
    """

    dataset_id: str | None
    domain: Domain
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ImageState:
    """Abstract state of an Earth Engine image or image collection."""

    dataset_id: str | None = None
    family: str | None = None
    platform: str | None = None
    is_collection: bool = False
    bands: tuple[str, ...] | None = None
    band_family: BandFamily = BandFamily.UNKNOWN
    sr_scale: ScaleState = ScaleState.UNKNOWN
    st_scale: ScaleState = ScaleState.UNKNOWN
    domain: Domain = Domain.UNKNOWN
    interval: tuple[datetime, datetime] | None = None
    source_ids: tuple[str, ...] = ()
    pending_multiply: float | None = None
    pending_log10: LogPending | None = None

    @classmethod
    def from_dataset(cls, info: catalog.DatasetInfo, *, is_collection: bool) -> ImageState:
        """Initial state for a freshly constructed, recognised dataset."""
        sr_scale = ScaleState.UNKNOWN
        st_scale = ScaleState.UNKNOWN
        if info.family == catalog.FAMILY_LANDSAT_C2_L2:
            # Collection 2 Level-2 products are delivered as encoded digital numbers.
            sr_scale = ScaleState.RAW
            st_scale = ScaleState.RAW
        domain = Domain(info.domain) if info.domain else Domain.UNKNOWN
        return cls(
            dataset_id=info.dataset_id,
            family=info.family,
            platform=info.platform,
            is_collection=is_collection,
            sr_scale=sr_scale,
            st_scale=st_scale,
            domain=domain,
            source_ids=info.source_ids,
        )

    def element(self) -> ImageState:
        """The per-image state of a collection element (SPECIFICATION §8.9)."""
        return replace(self, is_collection=False, pending_multiply=None, pending_log10=None)

    def cleared(self, **changes: Any) -> ImageState:
        """Copy with the transient multiply/log10 markers cleared."""
        changes.setdefault("pending_multiply", None)
        changes.setdefault("pending_log10", None)
        return replace(self, **changes)

    def numerically_unknown(self) -> ImageState:
        """Copy whose numeric scale/domain state is conservatively UNKNOWN.

        Lineage (dataset, platform, bands, temporal interval) is preserved;
        only numeric semantics are invalidated (SPECIFICATION §8.6).
        """
        return self.cleared(
            sr_scale=ScaleState.UNKNOWN,
            st_scale=ScaleState.UNKNOWN,
            domain=Domain.UNKNOWN,
        )


@dataclass(frozen=True)
class ImageValue:
    """An expression proven to be an Earth Engine image/collection-like value."""

    state: ImageState


@dataclass(frozen=True)
class ConstValue:
    """A statically resolved Python constant (str, number, bool, None, or tuple)."""

    value: Any


@dataclass(frozen=True)
class UnknownValue:
    """A value the analyzer cannot resolve."""


UNKNOWN_VALUE = UnknownValue()

Value = ImageValue | ConstValue | UnknownValue


def classify_bands(names: tuple[str, ...], platform: str | None) -> BandFamily:
    """Classify a proven band selection into a semantic family."""
    if not names:
        return BandFamily.UNKNOWN
    families: set[BandFamily] = set()
    for name in names:
        if catalog.landsat_sr_band(name):
            families.add(BandFamily.SR)
        elif catalog.is_landsat_st_band(name, platform):
            families.add(BandFamily.ST)
        elif name.startswith("QA"):
            families.add(BandFamily.QA)
        else:
            return BandFamily.UNKNOWN
    if len(families) == 1:
        return families.pop()
    return BandFamily.MIXED


def _merge_scalar(left: Any, right: Any, unknown: Any) -> Any:
    return left if left == right else unknown


def merge_states(left: ImageState, right: ImageState) -> ImageState:
    """Merge two branch states; conflicting properties become UNKNOWN (SPECIFICATION §8.10)."""
    if left == right:
        return left
    same_dataset = left.dataset_id == right.dataset_id
    return ImageState(
        dataset_id=left.dataset_id if same_dataset else None,
        family=_merge_scalar(left.family, right.family, None),
        platform=_merge_scalar(left.platform, right.platform, None),
        is_collection=left.is_collection and right.is_collection,
        bands=_merge_scalar(left.bands, right.bands, None),
        band_family=_merge_scalar(left.band_family, right.band_family, BandFamily.UNKNOWN),
        sr_scale=_merge_scalar(left.sr_scale, right.sr_scale, ScaleState.UNKNOWN),
        st_scale=_merge_scalar(left.st_scale, right.st_scale, ScaleState.UNKNOWN),
        domain=_merge_scalar(left.domain, right.domain, Domain.UNKNOWN),
        interval=_merge_scalar(left.interval, right.interval, None),
        source_ids=left.source_ids if left.source_ids == right.source_ids else (),
        pending_multiply=None,
        pending_log10=None,
    )


def merge_values(left: Value, right: Value) -> Value:
    """Merge two branch values conservatively."""
    if left == right:
        return left
    if isinstance(left, ImageValue) and isinstance(right, ImageValue):
        return ImageValue(merge_states(left.state, right.state))
    return UNKNOWN_VALUE


def merge_envs(left: dict[str, Value], right: dict[str, Value]) -> dict[str, Value]:
    """Merge two branch environments (SPECIFICATION §8.10)."""
    merged: dict[str, Value] = {}
    for name in sorted(set(left) | set(right)):
        if name in left and name in right:
            merged[name] = merge_values(left[name], right[name])
        else:
            merged[name] = UNKNOWN_VALUE
    return merged


def intersect_intervals(
    left: tuple[datetime, datetime] | None, right: tuple[datetime, datetime] | None
) -> tuple[datetime, datetime] | None:
    """Intersect two closed-open intervals; ``None`` means unknown or empty."""
    if left is None:
        return right
    if right is None:
        return left
    start = max(left[0], right[0])
    end = min(left[1], right[1])
    if start >= end:
        return None
    return (start, end)
