"""Static date/interval handling for Earth Engine ``filterDate`` (SPECIFICATION §8.8).

Earth Engine end-date semantics are modelled as exclusive, so every interval in
this package is closed-open: ``[start, end)``.
"""

from __future__ import annotations

import re
from datetime import datetime

__all__ = ["Interval", "contains", "format_instant", "intersects", "parse_ee_date"]

Interval = tuple[datetime, datetime]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$")


def parse_ee_date(text: str) -> datetime | None:
    """Parse the ISO-like date forms required by v0.1.0, else ``None``."""
    if _DATE_RE.match(text):
        try:
            return datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    if _DATETIME_RE.match(text):
        try:
            return datetime.strptime(text.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    return None


def format_instant(value: datetime) -> str:
    """Normalised, deterministic rendering used in finding evidence."""
    if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
        return value.date().isoformat()
    return value.replace(microsecond=0).isoformat()


def contains(inner: Interval, outer: Interval) -> bool:
    """True if closed-open ``inner`` lies entirely within closed-open ``outer``."""
    return inner[0] >= outer[0] and inner[1] <= outer[1]


def intersects(left: Interval, right: Interval) -> bool:
    """True if two closed-open intervals overlap."""
    return left[0] < right[1] and left[1] > right[0]
