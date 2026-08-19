"""Command-line interface (SPECIFICATION §17, §18).

The CLI is offline, non-interactive, requires no credentials, and never executes
the analyzed source.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, catalog
from .analyzer import AnalysisError, analyze_source
from .rules import RULES, rule_meta
from .serialization import to_json, to_text

__all__ = ["main"]

PROGRAM = "eo-workflow-lint"

#: SPECIFICATION §3.1 — a source file larger than 5 MiB is invalid input.
MAX_INPUT_BYTES = 5 * 1024 * 1024

EXIT_OK = 0
EXIT_THRESHOLD_REACHED = 1
EXIT_INVALID_INPUT = 2
EXIT_INTERNAL_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Deterministic, offline static analyzer for scientifically unsafe "
            "Google Earth Engine Python workflows."
        ),
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="analyze one Earth Engine Python file")
    check.add_argument("file", help="path to a local .py source file")
    check.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format (default: text)"
    )
    check.add_argument(
        "--fail-on",
        choices=("fail", "conditional"),
        default="fail",
        dest="fail_on",
        help="severity threshold that causes exit code 1 (default: fail)",
    )

    subparsers.add_parser("rules", help="list the v0.1.0 reason codes")

    explain = subparsers.add_parser("explain", help="explain one reason code")
    explain.add_argument("code", help="reason code, e.g. EWL301")

    subparsers.add_parser("sources", help="list the bundled catalog source registry")

    return parser


def _read_input(raw_path: str) -> bytes:
    path = Path(raw_path)
    if not path.exists():
        raise AnalysisError(f"no such file: {raw_path}")
    if not path.is_file():
        raise AnalysisError(f"not a regular file: {raw_path}")
    if path.suffix != ".py":
        raise AnalysisError(f"unsupported file extension {path.suffix!r}; expected '.py'")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise AnalysisError(f"input exceeds the {MAX_INPUT_BYTES} byte limit")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AnalysisError(f"cannot read {raw_path}: {exc.strerror}") from exc


def _run_check(args: argparse.Namespace, stdout, stderr) -> int:
    data = _read_input(args.file)
    report = analyze_source(data)

    for warning in report.warnings:
        print(f"{PROGRAM}: warning: {warning}", file=stderr)

    if args.format == "json":
        stdout.write(to_json(report))
    else:
        stdout.write(to_text(report, args.file))

    fails, conditionals = report.counts()
    reached = fails > 0 or (args.fail_on == "conditional" and conditionals > 0)
    return EXIT_THRESHOLD_REACHED if reached else EXIT_OK


def _run_rules(stdout) -> int:
    stdout.write(f"eo-workflow-lint {__version__} — catalog {catalog.CATALOG_VERSION}\n\n")
    for meta in RULES:
        stdout.write(f"{meta.code}  {meta.severity.value:<11}  {meta.name}\n")
        stdout.write(f"          {meta.intent}\n")
    return EXIT_OK


def _run_explain(code: str, stdout) -> int:
    meta = rule_meta(code)
    if meta is None:
        raise AnalysisError(f"unknown reason code: {code}")

    stdout.write(f"{meta.code} {meta.name}\n")
    stdout.write(f"severity: {meta.severity.value}\n")
    stdout.write(f"catalog: {catalog.CATALOG_VERSION}\n\n")
    stdout.write(f"intent:\n  {meta.intent}\n\n")
    stdout.write("triggers only when all of:\n")
    for item in meta.trigger:
        stdout.write(f"  - {item}\n")
    stdout.write("\ndoes not trigger when:\n")
    for item in meta.non_triggers:
        stdout.write(f"  - {item}\n")
    stdout.write(f"\nmessage:\n  {meta.message}\n\nsources:\n")
    for source_id in sorted(meta.source_ids):
        source = catalog.source_by_id(source_id)
        if source is None:  # pragma: no cover - registry is frozen and complete
            continue
        stdout.write(f"  {source.id}\n    {source.title}\n    {source.url}\n")
    return EXIT_OK


def _run_sources(stdout) -> int:
    stdout.write(f"catalog version: {catalog.CATALOG_VERSION}\n\n")
    for source in catalog.sources():
        stdout.write(f"{source.id}\n  {source.title}\n  {source.url}\n")
        for fact in source.facts:
            stdout.write(f"  - {fact}\n")
        stdout.write("\n")
    return EXIT_OK


def main(argv: list[str] | None = None, stdout=None, stderr=None) -> int:
    """Entry point. Returns the process exit code; never raises for user input."""
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            return _run_check(args, stdout, stderr)
        if args.command == "rules":
            return _run_rules(stdout)
        if args.command == "explain":
            return _run_explain(args.code, stdout)
        if args.command == "sources":
            return _run_sources(stdout)
    except AnalysisError as exc:
        print(f"{PROGRAM}: error: {exc}", file=stderr)
        return EXIT_INVALID_INPUT
    except Exception as exc:
        print(f"{PROGRAM}: internal error: {type(exc).__name__}: {exc}", file=stderr)
        return EXIT_INTERNAL_ERROR

    parser.error(f"unknown command: {args.command}")  # pragma: no cover
    return EXIT_INVALID_INPUT  # pragma: no cover


def run() -> None:  # pragma: no cover - thin console-script wrapper
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    run()
