"""GitHub Action runner for eo-workflow-lint.

This is the integration layer behind ``action.yml``. It is deliberately kept
outside the ``eo_workflow_lint`` package: the package's runtime is forbidden
(SPECIFICATION §19, ``tests/test_security.py``) from touching the process
environment or opening files it was not asked to analyze, while this runner
must read ``GITHUB_STEP_SUMMARY`` / ``GITHUB_OUTPUT`` and write to them.

Everything here uses only the public library API (``analyze_source``,
``AnalysisError``, ``Report``); no analyzer logic is duplicated. Analysis runs
entirely on the runner. Nothing is transmitted anywhere, and the only files
written are the two GitHub-provided output files.

Input: NUL-separated, workspace-relative file paths on stdin, as produced by
``git ls-files -z``. Only ``.py`` paths are analyzed; other matches are ignored.

Exit code precedence: 3 (internal failure) > 2 (an input could not be
analyzed) > 1 (finding threshold reached) > 0.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TextIO

from eo_workflow_lint import __version__, catalog
from eo_workflow_lint.analyzer import AnalysisError, analyze_source
from eo_workflow_lint.cli import _read_input
from eo_workflow_lint.models import Report, Severity, Verdict

__all__ = [
    "EXIT_INTERNAL_ERROR",
    "EXIT_INVALID_INPUT",
    "EXIT_OK",
    "EXIT_THRESHOLD_REACHED",
    "ActionResult",
    "FileResult",
    "analyze_files",
    "emit_annotations",
    "main",
    "paths_from_stdin",
    "run",
    "write_outputs",
    "write_summary",
]

REPO_URL = "https://github.com/orbseekr-labs/eo-workflow-lint"

EXIT_OK = 0
EXIT_THRESHOLD_REACHED = 1
EXIT_INVALID_INPUT = 2
EXIT_INTERNAL_ERROR = 3

FAIL_ON_CHOICES = ("fail", "conditional")

#: Findings listed individually in the Step Summary; the totals are always complete.
MAX_SUMMARY_ROWS = 200


@dataclass
class FileResult:
    """Outcome for one discovered file. Exactly one of the three fields is set."""

    path: str  # workspace-relative, forward slashes, as given by git
    report: Report | None = None
    invalid_input: str | None = None  # AnalysisError text (CLI exit 2 semantics)
    internal_error: str | None = None  # unexpected exception (CLI exit 3 semantics)


@dataclass
class ActionResult:
    fail_on: str
    files: list[FileResult] = field(default_factory=list)

    @property
    def analyzed(self) -> list[FileResult]:
        return [f for f in self.files if f.report is not None]

    @property
    def not_analyzable(self) -> list[FileResult]:
        return [f for f in self.files if f.invalid_input is not None]

    @property
    def internal_failures(self) -> list[FileResult]:
        return [f for f in self.files if f.internal_error is not None]

    def verdict_counts(self) -> dict[Verdict, int]:
        counts = dict.fromkeys(Verdict, 0)
        for item in self.analyzed:
            assert item.report is not None
            counts[item.report.verdict] += 1
        return counts

    def finding_counts(self) -> tuple[int, int]:
        fails = conditionals = 0
        for item in self.analyzed:
            assert item.report is not None
            f, c = item.report.counts()
            fails += f
            conditionals += c
        return fails, conditionals

    @property
    def suppressed_count(self) -> int:
        return sum(f.report.coverage.suppressed_finding_count for f in self.analyzed if f.report)

    @property
    def verdict(self) -> Verdict:
        """Overall verdict with the CLI precedence FAIL > CONDITIONAL > PASS."""
        counts = self.verdict_counts()
        if counts[Verdict.FAIL]:
            return Verdict.FAIL
        if counts[Verdict.CONDITIONAL]:
            return Verdict.CONDITIONAL
        return Verdict.PASS

    @property
    def exit_code(self) -> int:
        if self.internal_failures:
            return EXIT_INTERNAL_ERROR
        if self.not_analyzable:
            return EXIT_INVALID_INPUT
        fails, conditionals = self.finding_counts()
        if fails or (self.fail_on == "conditional" and conditionals):
            return EXIT_THRESHOLD_REACHED
        return EXIT_OK


# ------------------------------------------------------------------ discovery


def paths_from_stdin(stream) -> list[str]:
    """Decode a NUL-separated path list (``git ls-files -z``) from a binary stream."""
    raw = stream.read()
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def _is_python_path(path: str) -> bool:
    return PurePosixPath(path).suffix == ".py"


# ------------------------------------------------------------------- analysis


def analyze_files(paths: list[str], workspace: Path) -> list[FileResult]:
    """Analyze each ``.py`` path with the library API; never raises."""
    results: list[FileResult] = []
    for rel in paths:
        if not _is_python_path(rel):
            continue
        result = FileResult(path=rel)
        try:
            # Same input validation as the CLI (extension, size, regular file).
            data = _read_input(str(workspace / rel))
            result.report = analyze_source(data)
        except AnalysisError as exc:
            result.invalid_input = str(exc)
        except Exception as exc:  # mapped to exit 3, as the CLI does
            result.internal_error = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results


# ---------------------------------------------------------------- annotations


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _annotation(level: str, message: str, **props: object) -> str:
    rendered = ",".join(f"{k}={_escape_property(str(v))}" for k, v in props.items() if v != "")
    return (
        f"::{level} {rendered}::{_escape_data(message)}"
        if rendered
        else f"::{level}::{_escape_data(message)}"
    )


def emit_annotations(result: ActionResult, out: TextIO) -> None:
    """Write GitHub workflow-command annotations, one per finding or failure."""
    for item in result.files:
        if item.report is not None:
            for finding in item.report.findings:
                level = "error" if finding.severity is Severity.FAIL else "warning"
                out.write(
                    _annotation(
                        level,
                        finding.message,
                        file=item.path,
                        line=finding.line,
                        col=finding.column + 1,  # GitHub columns are 1-based
                        title=f"{finding.code} {finding.name}",
                    )
                    + "\n"
                )
            for warning in item.report.warnings:
                out.write(
                    _annotation(
                        "notice", warning, file=item.path, title="eo-workflow-lint directive"
                    )
                    + "\n"
                )
        elif item.invalid_input is not None:
            out.write(
                _annotation(
                    "error",
                    f"eo-workflow-lint could not analyze this file: {item.invalid_input}",
                    file=item.path,
                    title="eo-workflow-lint: not analyzable",
                )
                + "\n"
            )
        elif item.internal_error is not None:
            out.write(
                _annotation(
                    "error",
                    f"eo-workflow-lint internal analyzer failure: {item.internal_error}",
                    file=item.path,
                    title="eo-workflow-lint: internal error",
                )
                + "\n"
            )


# -------------------------------------------------------------------- summary


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_summary(result: ActionResult) -> str:
    """Markdown for the GitHub Step Summary. Contains no analyzed source text."""
    counts = result.verdict_counts()
    fails, conditionals = result.finding_counts()
    total = fails + conditionals
    lines = [
        "## eo-workflow-lint",
        "",
        "Static analysis ran locally on this runner. No Earth Engine credentials were "
        "used and no source code was transmitted.",
        "",
        "| | |",
        "|---|---|",
        f"| Python files checked | {len(result.analyzed)} |",
        f"| PASS / CONDITIONAL / FAIL | {counts[Verdict.PASS]} / "
        f"{counts[Verdict.CONDITIONAL]} / {counts[Verdict.FAIL]} |",
        f"| Findings | {total} ({fails} FAIL, {conditionals} CONDITIONAL) |",
        f"| Suppressed findings | {result.suppressed_count} |",
        f"| Not analyzable | {len(result.not_analyzable)} |",
    ]
    if result.internal_failures:
        lines.append(f"| Internal failures | {len(result.internal_failures)} |")
    lines += [
        f"| Verdict | **{result.verdict.value}** |",
        f"| fail-on | `{result.fail_on}` |",
        f"| Exit code | {result.exit_code} |",
        f"| Version | eo-workflow-lint {__version__}, catalog {catalog.CATALOG_VERSION} |",
        "",
    ]

    rows = [
        (item.path, finding)
        for item in result.analyzed
        if item.report is not None
        for finding in item.report.findings
    ]
    if rows:
        lines += ["### Findings", "", "| File | Line | Code | Severity |", "|---|---|---|---|"]
        for path, finding in rows[:MAX_SUMMARY_ROWS]:
            lines.append(
                f"| `{_md_cell(path)}` | {finding.line} | {finding.code} | {finding.severity.value} |"
            )
        if len(rows) > MAX_SUMMARY_ROWS:
            lines.append(f"| … | | {len(rows) - MAX_SUMMARY_ROWS} more | |")
        lines.append("")

    problems = result.not_analyzable + result.internal_failures
    if problems:
        lines += ["### Not analyzable", "", "| File | Reason |", "|---|---|"]
        for item in problems:
            reason = item.invalid_input or item.internal_error or ""
            lines.append(f"| `{_md_cell(item.path)}` | {_md_cell(reason)} |")
        lines.append("")

    lines += [
        f"Run `eo-workflow-lint explain <CODE>` for triggers, sources and remediation. "
        f"[Documentation]({REPO_URL}#readme)",
        "",
    ]
    return "\n".join(lines)


def write_summary(result: ActionResult, path: Path | None) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(render_summary(result))


def write_outputs(result: ActionResult, path: Path | None) -> None:
    if path is None:
        return
    fails, conditionals = result.finding_counts()
    values = {
        "verdict": result.verdict.value,
        "files-checked": len(result.analyzed),
        "findings": fails + conditionals,
        "fail-count": fails,
        "conditional-count": conditionals,
        "not-analyzable": len(result.not_analyzable),
        "exit-code": result.exit_code,
    }
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


# ----------------------------------------------------------------------- main


def run(
    paths: list[str],
    *,
    fail_on: str,
    workspace: Path,
    summary_path: Path | None,
    outputs_path: Path | None,
    out: TextIO,
) -> int:
    if fail_on not in FAIL_ON_CHOICES:
        out.write(
            _annotation(
                "error",
                f"invalid fail-on value {fail_on!r}; expected fail or conditional",
                title="eo-workflow-lint",
            )
            + "\n"
        )
        return EXIT_INVALID_INPUT
    result = ActionResult(fail_on=fail_on, files=analyze_files(sorted(set(paths)), workspace))
    emit_annotations(result, out)
    write_summary(result, summary_path)
    write_outputs(result, outputs_path)
    fails, conditionals = result.finding_counts()
    out.write(
        f"eo-workflow-lint {__version__}: {len(result.analyzed)} Python file(s) checked, "
        f"verdict {result.verdict.value}, {fails} FAIL, {conditionals} CONDITIONAL, "
        f"{len(result.not_analyzable)} not analyzable, exit {result.exit_code}\n"
    )
    return result.exit_code


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fail-on", default="fail")
    parser.add_argument("--workspace", default=os.environ.get("GITHUB_WORKSPACE") or ".")
    args = parser.parse_args(argv)

    return run(
        paths_from_stdin(sys.stdin.buffer),
        fail_on=args.fail_on,
        workspace=Path(args.workspace),
        summary_path=_env_path("GITHUB_STEP_SUMMARY"),
        outputs_path=_env_path("GITHUB_OUTPUT"),
        out=sys.stdout,
    )


if __name__ == "__main__":
    sys.exit(main())
