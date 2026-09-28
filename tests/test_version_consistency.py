"""Versions stated in the package, specification and README must agree.

Release hygiene only: these tests read repository files and never touch the
network. They exist because v0.2.0 shipped with SPECIFICATION §0 still naming
v0.1.0 and the README still calling the specification "frozen for the 0.1.x
series".
"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

from eo_workflow_lint import SCHEMA_VERSION, __version__, catalog
from eo_workflow_lint.rules import RULES

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    path = REPO_ROOT / name
    if not path.exists():
        pytest.skip(f"{name} is not present in this checkout")
    return path.read_text(encoding="utf-8")


def test_version_has_a_single_source_of_truth() -> None:
    config = tomllib.loads(_read("pyproject.toml"))
    assert "version" not in config["project"], "pyproject must not repeat the version"
    assert config["project"]["dynamic"] == ["version"]
    assert config["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "eo_workflow_lint.__version__"
    }


def test_installed_metadata_matches_package_version() -> None:
    try:
        installed = metadata.version("eo-workflow-lint")
    except metadata.PackageNotFoundError:  # pragma: no cover - source-only checkout
        pytest.skip("eo-workflow-lint is not installed")
    assert installed == __version__


def test_specification_authority_names_the_current_series() -> None:
    spec = _read("SPECIFICATION.md")
    header = re.search(r"^\*\*Specification version:\*\* (\S+)", spec, re.MULTILINE)
    assert header is not None
    spec_version = header.group(1)
    assert spec.startswith(f"# eo-workflow-lint Specification v{spec_version}\n")
    assert f"| {spec_version} |" in spec, "every revision must have a Revision history row"
    series = ".".join(spec_version.split(".")[:2])
    authority = spec.split("## 0. Specification authority", 1)[1].split("\n## 1.", 1)[0]
    assert f"`eo-workflow-lint` v{series}.x" in authority
    assert "normative specification for `eo-workflow-lint` v0.1.0." not in authority
    assert __version__.startswith(f"{series}."), "tool and specification series must match"


def test_specification_catalog_version_matches_bundled_catalog() -> None:
    spec = _read("SPECIFICATION.md")
    section = spec.split("### 6.1 Catalog identity", 1)[1].split("### 6.2", 1)[0]
    assert f"`{catalog.CATALOG_VERSION}`" in section
    example = spec.split("## 15. JSON output schema", 1)[1].split("## 16.", 1)[0]
    assert f'"catalog_version": "{catalog.CATALOG_VERSION}"' in example
    assert f'"schema_version": "{SCHEMA_VERSION}"' in example


def test_readme_states_the_real_versions() -> None:
    readme = _read("README.md")
    assert f"- Version: **{__version__}**" in readme
    assert f"- JSON report `schema_version`: `{SCHEMA_VERSION}`" in readme
    assert f"- Catalog version: `{catalog.CATALOG_VERSION}`" in readme
    assert f'"tool_version": "{__version__}"' in readme
    assert f'"schema_version": "{SCHEMA_VERSION}"' in readme
    assert "0.1.x series" not in readme
    tags = set(re.findall(r"eo-workflow-lint(?:\.git)?@(v[0-9][^\s\"]*)", readme))
    assert tags == {f"v{__version__}"}, f"install/Action examples must pin v{__version__}: {tags}"


def test_readme_reason_code_table_matches_registry() -> None:
    readme = _read("README.md")
    rows = re.findall(r"^\| `(EWL\d{3})` \| (FAIL|CONDITIONAL) \| `([A-Z0-9_]+)` \|", readme, re.M)
    assert sorted(rows) == sorted((meta.code, meta.severity.value, meta.name) for meta in RULES)
    assert f"- Reason codes: {len(RULES)} " in readme
