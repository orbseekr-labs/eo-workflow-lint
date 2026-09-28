#!/usr/bin/env python3
"""Re-run the real-world validation benchmark (developer tool, needs network).

This script is NOT part of the offline test suite and is not shipped in the
package. It reads ``validation/manifest.json``, fetches each pinned public
repository at its exact commit into a git-ignored cache (``validation/.cache``)
using sparse, shallow ``git`` fetches, verifies the SHA-256 of every listed
file, runs one or more ``eo-workflow-lint`` executables over the files, and
classifies every finding against the human-reviewed expectations.

No third-party source is stored in this repository: the manifest holds only
repository names, commit SHAs, paths, line numbers and file digests.

Usage::

    python validation/run_benchmark.py
    python validation/run_benchmark.py --linter current=eo-workflow-lint \\
        --linter v0.1.2=/path/to/v0.1.2/venv/bin/eo-workflow-lint
    python validation/run_benchmark.py --offline   # reuse the cache, no fetch

Outputs ``<out>/results.json`` and ``<out>/results.md`` (default out dir:
``validation/.cache/results``). Classification per linter:

* ``detected``   - an expected target (code, line) was reported;
* ``missed``     - an expected target was not reported (split into in-scope
  misses, which would be bugs, and misses the manifest documents as outside
  the specification's static scope, i.e. coverage-unresolved);
* adjudicated findings - a human already labelled the finding
  ``true_positive`` or ``false_positive``;
* ``unadjudicated`` - any other finding; it needs human review and is a
  potential false positive.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "manifest.json"
DEFAULT_CACHE = HERE / ".cache"


# --------------------------------------------------------------------- fetch


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout


def checkout_dir(cache: Path, repo: str, commit: str) -> Path:
    return cache / "repos" / repo.replace("/", "__") / commit


def fetch_repo(entry: dict, cache: Path) -> Path:
    """Shallow, sparse fetch of ``entry['repo']`` at ``entry['commit']``."""
    target = checkout_dir(cache, entry["repo"], entry["commit"])
    marker = target / ".ewl-fetched"
    if marker.exists():
        return target
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    patterns = [f"/{f['path']}" for f in entry.get("files", [])]
    for glob in entry.get("sweep", {}).get("include", []):
        # Manifest globs use fnmatch semantics ("**.py" = any depth); translate
        # them to git's non-cone sparse-checkout (gitignore) syntax.
        prefix = glob.removesuffix("**.py")
        patterns += [f"/{prefix}*.py", f"/{prefix}**/*.py"] if prefix != glob else [f"/{glob}"]
    _git("init", "-q", cwd=target)
    _git("remote", "add", "origin", f"https://github.com/{entry['repo']}.git", cwd=target)
    _git("sparse-checkout", "set", "--no-cone", *patterns, cwd=target)
    _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", entry["commit"], cwd=target)
    _git("checkout", "-q", "FETCH_HEAD", cwd=target)
    head = _git("rev-parse", "HEAD", cwd=target).strip()
    if head != entry["commit"]:
        raise RuntimeError(f"{entry['repo']}: fetched {head}, expected {entry['commit']}")
    marker.write_text(head + "\n", encoding="utf-8")
    return target


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(entry: dict, root: Path) -> list[str]:
    """Listed files plus every ``.py`` file matched by the sweep globs."""
    paths = {f["path"] for f in entry.get("files", [])}
    sweep = entry.get("sweep")
    if sweep:
        for candidate in root.rglob("*.py"):
            rel = candidate.relative_to(root).as_posix()
            if rel.startswith(".git/"):
                continue
            if not any(fnmatch.fnmatch(rel, g) for g in sweep["include"]):
                continue
            if any(fnmatch.fnmatch(rel, g) for g in sweep.get("exclude", [])):
                continue
            paths.add(rel)
    return sorted(paths)


# ----------------------------------------------------------------------- run


@dataclass
class FileResult:
    path: str
    exit_code: int
    verdict: str | None
    findings: list[tuple[str, int]]
    coverage: dict = field(default_factory=dict)
    error: str | None = None


def run_linter(command: list[str], path: Path) -> FileResult:
    proc = subprocess.run(
        [*command, "check", str(path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        error = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        return FileResult(path.name, proc.returncode, None, [], error=error)
    findings = [(f["code"], f["line"]) for f in report["findings"]]
    return FileResult(
        path.name, proc.returncode, report["verdict"], findings, report.get("analysis", {})
    )


def linter_version(command: list[str]) -> str:
    proc = subprocess.run([*command, "--version"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() or proc.stderr.strip()


# ------------------------------------------------------------------ classify


def classify(entry: dict, rel: str, result: FileResult) -> dict:
    """Classify one file's findings against the manifest expectations."""
    spec = next((f for f in entry.get("files", []) if f["path"] == rel), {})
    expected = spec.get("expected", [])
    adjudicated = {
        (a["code"], a["line"]): a for a in entry.get("adjudicated_findings", []) if a["path"] == rel
    }
    reported = set(result.findings)
    out: dict = {
        "path": rel,
        "exit_code": result.exit_code,
        "verdict": result.verdict,
        "findings": [list(f) for f in result.findings],
        "detected": [],
        "missed_in_scope": [],
        "missed_out_of_scope": [],
        "true_positive": [],
        "false_positive": [],
        "unadjudicated": [],
        "error": result.error,
    }
    for target in expected:
        key = (target["code"], target["line"])
        if key in reported:
            out["detected"].append(list(key))
        elif target.get("static_scope") == "out":
            out["missed_out_of_scope"].append(list(key))
        else:
            out["missed_in_scope"].append(list(key))
    targets = {(t["code"], t["line"]) for t in expected}
    for finding in result.findings:
        if finding in targets:
            continue
        label = adjudicated.get(finding, {}).get("label")
        bucket = label if label in ("true_positive", "false_positive") else "unadjudicated"
        out[bucket].append(list(finding))
    expect_invalid = spec.get("expect_not_analyzable") or any(
        n["path"] == rel for n in entry.get("not_analyzable", [])
    )
    if result.verdict is None and not expect_invalid:
        out["unadjudicated"].append(["NOT_ANALYZABLE", 0])
    return out


def summarize(cases: list[dict], per_file: dict[str, list[dict]]) -> dict:
    s = {
        "candidate_cases": 0,
        "candidate_cases_detected": 0,
        "candidate_cases_missed": 0,
        "candidate_cases_missed_coverage_unresolved": 0,
        "target_sites": 0,
        "target_sites_detected": 0,
        "target_sites_missed_in_scope": 0,
        "target_sites_missed_out_of_scope": 0,
        "control_findings_false_positive": 0,
        "findings_true_positive_adjudicated": 0,
        "findings_false_positive_adjudicated": 0,
        "findings_unadjudicated": 0,
        "files_analyzed": 0,
        "files_not_analyzable": 0,
    }
    for case in cases:
        files = per_file[case["id"]]
        detected = sum(len(f["detected"]) for f in files)
        missed_in = sum(len(f["missed_in_scope"]) for f in files)
        missed_out = sum(len(f["missed_out_of_scope"]) for f in files)
        s["target_sites"] += detected + missed_in + missed_out
        s["target_sites_detected"] += detected
        s["target_sites_missed_in_scope"] += missed_in
        s["target_sites_missed_out_of_scope"] += missed_out
        if case["role"] == "candidate":
            s["candidate_cases"] += 1
            if detected:
                s["candidate_cases_detected"] += 1
            else:
                s["candidate_cases_missed"] += 1
                if not missed_in:
                    s["candidate_cases_missed_coverage_unresolved"] += 1
        for f in files:
            s["files_analyzed"] += 1
            if f["verdict"] is None:
                s["files_not_analyzable"] += 1
            s["findings_true_positive_adjudicated"] += len(f["true_positive"])
            s["findings_false_positive_adjudicated"] += len(f["false_positive"])
            s["findings_unadjudicated"] += len(f["unadjudicated"])
            if case["role"] == "control":
                s["control_findings_false_positive"] += len(f["false_positive"]) + len(
                    f["unadjudicated"]
                )
    return s


# -------------------------------------------------------------------- report


def render_markdown(manifest: dict, results: dict) -> str:
    names = list(results["linters"])
    lines = [
        "# eo-workflow-lint real-world benchmark results",
        "",
        f"Manifest validated: {manifest['last_validated']}",
        "",
        "| Linter | Version |",
        "|---|---|",
    ]
    lines += [f"| {n} | {results['linters'][n]['version']} |" for n in names]
    lines += ["", "## Summary", "", "| Metric | " + " | ".join(names) + " |"]
    lines.append("|---|" + "---|" * len(names))
    for key in results["linters"][names[0]]["summary"]:
        row = [str(results["linters"][n]["summary"][key]) for n in names]
        lines.append(f"| {key} | " + " | ".join(row) + " |")
    lines += ["", "## Target sites", ""]
    lines.append("| Case | Role | File:line | Expected | " + " | ".join(names) + " |")
    lines.append("|---|---|---|---|" + "---|" * len(names))
    for case in manifest["cases"]:
        for spec in case.get("files", []):
            for target in spec.get("expected", []):
                cells = []
                for n in names:
                    file_result = next(
                        f
                        for f in results["linters"][n]["cases"][case["id"]]
                        if f["path"] == spec["path"]
                    )
                    key = [target["code"], target["line"]]
                    cells.append("detected" if key in file_result["detected"] else "missed")
                lines.append(
                    f"| {case['id']} | {case['role']} | `{spec['path']}:{target['line']}` "
                    f"| {target['code']} ({target.get('static_scope', 'in')} scope) | "
                    + " | ".join(cells)
                    + " |"
                )
    lines += ["", "## Findings outside the targets", ""]
    lines.append("| Linter | Case | File | Finding | Label |")
    lines.append("|---|---|---|---|---|")
    any_other = False
    for n in names:
        for case_id, files in results["linters"][n]["cases"].items():
            for f in files:
                for bucket in ("true_positive", "false_positive", "unadjudicated"):
                    for code, line in f[bucket]:
                        any_other = True
                        lines.append(
                            f"| {n} | {case_id} | `{f['path']}` | {code}:{line} | {bucket} |"
                        )
    if not any_other:
        lines.append("| - | - | - | none | - |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- main


def parse_linters(values: list[str] | None) -> dict[str, list[str]]:
    if not values:
        exe = shutil.which("eo-workflow-lint")
        if exe is None:
            sys.exit("eo-workflow-lint is not on PATH; pass --linter NAME=PATH")
        return {"current": [exe]}
    linters: dict[str, list[str]] = {}
    for value in values:
        name, _, command = value.partition("=")
        if not command:
            name, command = Path(value).name, value
        linters[name] = command.split()
    return linters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--linter", action="append", help="NAME=COMMAND (repeatable)")
    parser.add_argument("--offline", action="store_true", help="do not fetch; use the cache")
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    linters = parse_linters(args.linter)
    out_dir = args.out or args.cache / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    roots: dict[str, Path] = {}
    file_lists: dict[str, list[str]] = {}
    integrity_errors = []
    for case in manifest["cases"]:
        root = checkout_dir(args.cache, case["repo"], case["commit"])
        if not args.offline:
            root = fetch_repo(case, args.cache)
        roots[case["id"]] = root
        for spec in case.get("files", []):
            path = root / spec["path"]
            if not path.exists():
                integrity_errors.append(f"{case['id']}: missing {spec['path']}")
            elif sha256_of(path) != spec["sha256"]:
                integrity_errors.append(f"{case['id']}: sha256 mismatch for {spec['path']}")
        file_lists[case["id"]] = discover(case, root)
    if integrity_errors:
        print("\n".join(integrity_errors), file=sys.stderr)
        return 2

    results: dict = {"manifest_last_validated": manifest["last_validated"], "linters": {}}
    for name, command in linters.items():
        per_case: dict[str, list[dict]] = {}
        for case in manifest["cases"]:
            per_case[case["id"]] = [
                classify(case, rel, run_linter(command, roots[case["id"]] / rel))
                for rel in file_lists[case["id"]]
            ]
        results["linters"][name] = {
            "version": linter_version(command),
            "summary": summarize(manifest["cases"], per_case),
            "cases": per_case,
        }

    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "results.md").write_text(render_markdown(manifest, results), encoding="utf-8")
    for name in linters:
        print(name, json.dumps(results["linters"][name]["summary"], sort_keys=True))
    print(f"wrote {out_dir / 'results.json'} and {out_dir / 'results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
