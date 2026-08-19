"""Bundled static Earth-observation product catalog (SPECIFICATION §6, §7).

Catalog facts are frozen at build time and MUST NOT be refreshed at runtime.
No network access occurs in this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

__all__ = [
    "CATALOG_VERSION",
    "LANDSAT_SOURCE_IDS",
    "QA60_BAND",
    "S1_BACKSCATTER_BANDS",
    "SENTINEL1_SOURCE_IDS",
    "SENTINEL2_SOURCE_IDS",
    "SR_REGEX_SELECTOR",
    "DatasetInfo",
    "LandsatConstants",
    "Source",
    "is_landsat_st_band",
    "landsat_constants",
    "landsat_sr_band",
    "landsat_st_band_for_platform",
    "qa60_gap",
    "recognize_dataset",
    "source_by_id",
    "sources",
]

#: Family identifiers used by the abstract state model.
FAMILY_LANDSAT_C2_L2 = "LANDSAT_C2_L2"
FAMILY_SENTINEL1 = "SENTINEL1"
FAMILY_SENTINEL2 = "SENTINEL2"

#: Landsat SR band names recognised by v0.1.0 (SPECIFICATION §7.1).
_SR_BAND_RE = re.compile(r"^SR_B[1-7]$")

SR_REGEX_SELECTOR = "SR_B."
QA60_BAND = "QA60"


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    text = (
        resources.files("eo_workflow_lint.data")
        .joinpath("catalog.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


CATALOG_VERSION: str = _raw()["catalog_version"]


@dataclass(frozen=True)
class Source:
    """A provenance record from the frozen source registry (SPECIFICATION §6.2)."""

    id: str
    title: str
    url: str
    facts: tuple[str, ...]


@dataclass(frozen=True)
class DatasetInfo:
    """A statically recognised Earth Engine dataset."""

    dataset_id: str  #: the recognised collection ID (not the concrete asset ID)
    family: str
    platform: str | None = None  #: Landsat platform code, e.g. "LC08"
    domain: str | None = None  #: Sentinel-1 numeric domain, "DB" or "LINEAR_POWER"
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LandsatConstants:
    """Documented Collection 2 Level-2 scale/offset pairs (SPECIFICATION §6.2)."""

    sr_scale: float
    sr_offset: float
    st_scale: float
    st_offset: float


@lru_cache(maxsize=1)
def sources() -> tuple[Source, ...]:
    """All registry sources, sorted lexicographically by ID (deterministic)."""
    entries = [
        Source(
            id=item["id"],
            title=item["title"],
            url=item["url"],
            facts=tuple(item["facts"]),
        )
        for item in _raw()["sources"]
    ]
    return tuple(sorted(entries, key=lambda s: s.id))


def source_by_id(source_id: str) -> Source | None:
    for source in sources():
        if source.id == source_id:
            return source
    return None


@lru_cache(maxsize=1)
def landsat_constants() -> LandsatConstants:
    block = _raw()["landsat_c2_l2"]
    return LandsatConstants(
        sr_scale=block["surface_reflectance_scale"],
        sr_offset=block["surface_reflectance_offset"],
        st_scale=block["surface_temperature_scale"],
        st_offset=block["surface_temperature_offset"],
    )


LANDSAT_SOURCE_IDS: tuple[str, ...] = tuple(sorted(_raw()["landsat_c2_l2"]["source_ids"]))
SENTINEL1_SOURCE_IDS: tuple[str, ...] = tuple(sorted(_raw()["sentinel1"]["source_ids"]))
SENTINEL2_SOURCE_IDS: tuple[str, ...] = tuple(sorted(_raw()["sentinel2"]["source_ids"]))
S1_BACKSCATTER_BANDS: tuple[str, ...] = tuple(_raw()["sentinel1"]["backscatter_bands"])


@lru_cache(maxsize=1)
def qa60_gap() -> tuple[datetime, datetime]:
    """The v0.1.0 conservative QA60 gap as a closed-open interval (SPECIFICATION §7.3)."""
    block = _raw()["sentinel2"]
    return (
        datetime.fromisoformat(block["qa60_gap_start"]),
        datetime.fromisoformat(block["qa60_gap_end"]),
    )


def landsat_sr_band(name: str) -> bool:
    """True if ``name`` is a recognised Landsat Collection 2 SR band."""
    return bool(_SR_BAND_RE.match(name))


def landsat_st_band_for_platform(platform: str | None) -> str | None:
    """Platform-appropriate surface-temperature band name (SPECIFICATION §7.1)."""
    if platform is None:
        return None
    return _raw()["landsat_c2_l2"]["surface_temperature_band"].get(platform)


def is_landsat_st_band(name: str, platform: str | None) -> bool:
    """True if ``name`` is the platform-appropriate ST band.

    When the platform is unknown the band identity cannot be proven and this
    returns False (SPECIFICATION §8.1 conservative proof rule).
    """
    expected = landsat_st_band_for_platform(platform)
    return expected is not None and name == expected


def recognize_dataset(dataset_id: str) -> DatasetInfo | None:
    """Recognise a statically known Earth Engine dataset/asset ID.

    Returns ``None`` when the ID is not part of the frozen v0.1.0 catalog.
    """
    raw = _raw()

    landsat = raw["landsat_c2_l2"]["collections"]
    platform = landsat.get(dataset_id)
    if platform is not None:
        return DatasetInfo(
            dataset_id=dataset_id,
            family=FAMILY_LANDSAT_C2_L2,
            platform=platform,
            source_ids=LANDSAT_SOURCE_IDS,
        )
    # A concrete image asset under a recognised collection (SPECIFICATION §7.1).
    for collection_id, plat in sorted(landsat.items()):
        if dataset_id.startswith(collection_id + "/"):
            return DatasetInfo(
                dataset_id=collection_id,
                family=FAMILY_LANDSAT_C2_L2,
                platform=plat,
                source_ids=LANDSAT_SOURCE_IDS,
            )

    domain = raw["sentinel1"]["domains"].get(dataset_id)
    if domain is not None:
        return DatasetInfo(
            dataset_id=dataset_id,
            family=FAMILY_SENTINEL1,
            domain=domain,
            source_ids=SENTINEL1_SOURCE_IDS,
        )

    if dataset_id in raw["sentinel2"]["collections"]:
        return DatasetInfo(
            dataset_id=dataset_id,
            family=FAMILY_SENTINEL2,
            source_ids=SENTINEL2_SOURCE_IDS,
        )

    return None
