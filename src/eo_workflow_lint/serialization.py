"""Deterministic text and JSON rendering (SPECIFICATION §14, §15, §16)."""

from __future__ import annotations

import json

from .models import Report, Verdict

__all__ = ["PASS_LIMITATION", "to_json", "to_text"]

PASS_LIMITATION = (
    "note: PASS means no supported v0.1.0 rule produced a finding in the statically "
    "resolved portion of this source. It does not prove that the workflow, analysis, "
    "or conclusion is scientifically correct."
)


def to_json(report: Report) -> str:
    """Render the report as deterministic JSON.

    The object contains no path, timestamp, hostname, or other environment-derived
    value, and key order follows the schema order in SPECIFICATION §15.
    """
    payload = {
        "schema_version": report.schema_version,
        "tool_version": report.tool_version,
        "catalog_version": report.catalog_version,
        "input": report.input.to_json_obj(),
        "verdict": report.verdict.value,
        "findings": [finding.to_json_obj() for finding in report.findings],
        "analysis": report.coverage.to_json_obj(),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def to_text(report: Report, path: str | None = None) -> str:
    """Render the concise developer-facing text report."""
    lines: list[str] = [report.verdict.value]
    if path is not None:
        lines.append(f"file: {path}")

    for finding in report.findings:
        lines.append("")
        lines.append(f"{finding.code} {finding.name}")
        lines.append(f"line {finding.line}: {finding.message}")
        lines.append(f"source: {', '.join(finding.source_ids)}")

    fails, conditionals = report.counts()
    coverage = report.coverage
    lines.append("")
    lines.append(
        f"{_plural(len(report.findings), 'finding')}: {fails} FAIL, {conditionals} CONDITIONAL"
    )
    lines.append(
        "coverage: "
        + ", ".join(
            [
                _plural(coverage.recognized_dataset_count, "recognized dataset"),
                _plural(coverage.supported_operation_check_count, "supported operation check"),
                _plural(
                    coverage.unresolved_lineage_count, "unresolved lineage", "unresolved lineage"
                ),
                _plural(
                    coverage.unresolved_temporal_scope_count,
                    "unresolved temporal scope",
                ),
                _plural(coverage.suppressed_finding_count, "suppressed finding"),
            ]
        )
    )
    if report.verdict is Verdict.PASS:
        lines.append(PASS_LIMITATION)

    return "\n".join(lines) + "\n"
