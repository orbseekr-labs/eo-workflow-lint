"""The FROZEN specification must never be modified within the 0.1.x series.

Release preparation uncovered a real way this could happen silently: newer ruff
versions format Python code blocks inside Markdown files, and `ruff format`
would have rewritten SPECIFICATION.md. Ruff is now configured to exclude
Markdown, and this test is the backstop for any other tool that tries.

If the specification owner deliberately revises the specification, this test is
expected to fail loudly and the recorded digest must be updated as part of that
authorised change.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECIFICATION = REPO_ROOT / "SPECIFICATION.md"

#: SHA-256 of the v0.1.0 FROZEN specification, recorded at independent review.
FROZEN_SHA256 = "778edb8482f6ce8836db59b997a39df052579eddbe9551dff02cf529a49a0bdd"


def _require_specification() -> Path:
    if not SPECIFICATION.exists():
        pytest.skip("SPECIFICATION.md is not present in this checkout")
    return SPECIFICATION


def test_specification_digest_is_unchanged() -> None:
    path = _require_specification()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == FROZEN_SHA256, (
        "SPECIFICATION.md has been modified. The v0.1.x specification is frozen; "
        "revising it requires an authorised specification change."
    )


def test_ruff_is_configured_not_to_rewrite_markdown() -> None:
    """Guards the specific tooling defect found during release preparation."""
    import tomllib

    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml is not present in this checkout")
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    excluded = config["tool"]["ruff"].get("extend-exclude", [])
    assert "*.md" in excluded, "ruff must not be allowed to format Markdown files"
