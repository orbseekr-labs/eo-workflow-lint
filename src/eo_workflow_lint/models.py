"""Core data models and deterministic finding representation (SPECIFICATION §5, §14, §15)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "SEVERITY_RANK",
    "Coverage",
    "Finding",
    "InputInfo",
    "Report",
    "Severity",
    "Verdict",
]


class Severity(StrEnum):
    """Finding severity. v0.1.0 has exactly two finding severities."""

    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"


class Verdict(StrEnum):
    """Top-level verdict (SPECIFICATION §4). There is no UNKNOWN verdict in v0.1.0."""

    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


#: Severity ordering rank used by the deterministic sort (SPECIFICATION §14).
SEVERITY_RANK: dict[Severity, int] = {Severity.FAIL: 0, Severity.CONDITIONAL: 1}


@dataclass(frozen=True)
class Finding:
    """A single statically proven rule violation (SPECIFICATION §5)."""

    code: str
    severity: Severity
    name: str
    line: int  # 1-based
    column: int  # 0-based
    message: str
    source_ids: tuple[str, ...]
    evidence: tuple[tuple[str, Any], ...]

    def evidence_dict(self) -> dict[str, Any]:
        """Evidence as a JSON-ready mapping.

        Evidence is stored as a hashable tuple of pairs so that findings can be
        de-duplicated; sequence values are widened back to lists here.
        """
        return {
            key: list(value) if isinstance(value, tuple) else value for key, value in self.evidence
        }

    @property
    def sort_key(self) -> tuple[int, int, int, str, str]:
        return (
            SEVERITY_RANK[self.severity],
            self.line,
            self.column,
            self.code,
            self.name,
        )

    @property
    def dedup_key(self) -> tuple[str, int, int, tuple[tuple[str, Any], ...]]:
        """De-duplication identity (SPECIFICATION §5): (code, line, column, evidence)."""
        return (self.code, self.line, self.column, self.evidence)

    def to_json_obj(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "name": self.name,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "source_ids": list(self.source_ids),
            "evidence": self.evidence_dict(),
        }


@dataclass
class Coverage:
    """Analysis coverage counters (SPECIFICATION §13). Informational only."""

    recognized_dataset_count: int = 0
    supported_operation_check_count: int = 0
    unresolved_lineage_count: int = 0
    unresolved_temporal_scope_count: int = 0
    suppressed_finding_count: int = 0

    def to_json_obj(self) -> dict[str, int]:
        return {
            "recognized_dataset_count": self.recognized_dataset_count,
            "supported_operation_check_count": self.supported_operation_check_count,
            "unresolved_lineage_count": self.unresolved_lineage_count,
            "unresolved_temporal_scope_count": self.unresolved_temporal_scope_count,
            "suppressed_finding_count": self.suppressed_finding_count,
        }


@dataclass(frozen=True)
class InputInfo:
    """Path-free description of the analyzed bytes (SPECIFICATION §3.3, §15)."""

    sha256: str
    byte_length: int

    def to_json_obj(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "byte_length": self.byte_length}


@dataclass
class Report:
    """Complete analysis result."""

    schema_version: str
    tool_version: str
    catalog_version: str
    input: InputInfo
    findings: list[Finding] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    warnings: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        """Verdict precedence FAIL > CONDITIONAL > PASS (SPECIFICATION §4.4)."""
        severities = {f.severity for f in self.findings}
        if Severity.FAIL in severities:
            return Verdict.FAIL
        if Severity.CONDITIONAL in severities:
            return Verdict.CONDITIONAL
        return Verdict.PASS

    def counts(self) -> tuple[int, int]:
        fails = sum(1 for f in self.findings if f.severity is Severity.FAIL)
        conditionals = sum(1 for f in self.findings if f.severity is Severity.CONDITIONAL)
        return fails, conditionals
